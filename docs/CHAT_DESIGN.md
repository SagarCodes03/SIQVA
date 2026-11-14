# SIQVA Chat Architecture & Design (C1)

## 1. Overview and Goals

SIQVA transitions its Query page from a single-result replacement view to a persistent, scrollable chat interface (similar to modern assistant interfaces such as Claude or ChatGPT). Users can scroll up to view past exchanges, compare successive results, and click interactive buttons without overwriting conversation history.

The Plot Graph and Compare Runs pages remain completely decoupled and unchanged.

---

## 2. Module Boundaries & Responsibilities

To maintain clean separation of concerns and touch `app/ui.py` minimally:

1. **`src/siqva/chat.py` (Pure Dispatcher & Persistence Logic)**:
   - Framework-agnostic pure Python module.
   - Defines `ChatMessage` and `ChatOption` structured models.
   - Implements `dispatch()`: pure function routing user input to data fetches, operations, follow-ups, comparisons, glossary, meta, greetings, or refusals.
   - Implements SQLite persistence in table `chat_messages` using the exact `closing(sqlite3.connect(...))` pattern from `card.py`.
   - Zero Streamlit imports; fully testable in offline unit tests with mocked fetcher.

2. **`app/chat_ui.py` (Streamlit Chat View & Widget Interaction)**:
   - Streamlit rendering module for the Query page.
   - Renders scrollable history using `st.chat_message("user")` and `st.chat_message("assistant")`.
   - Renders input docked at the bottom using `st.chat_input`.
   - Renders "New chat" and "Clear chat" controls.
   - Controls performance: auto-renders full plots only for the newest result message; older result messages render a compact card with an on-demand "Show plots" toggle.
   - Manages widget state for interactive buttons (clarification options, plan options, quick templates) so clicks append new conversational turns.
   - Synchronizes `session_id` with `st.query_params` for refresh restoration.

3. **`app/ui.py` (Minimal Bridge)**:
   - When `active_page == "query"`, calls `render_chat_page()`.
   - Retains sidebar delivery mode selector and session state defaults.
   - Leaves Plot Graph and Compare Runs pages untouched.

---

## 3. Data Models

### `ChatOption` (Structured Interactive Action)
```python
class ChatOption(BaseModel):
    model_config = ConfigDict(frozen=True)
    label: str               # Button label shown to user, e.g. "Use 2023", "Bigger sample (24)"
    action_type: str         # "query", "plan_option", "clarification"
    query_text: str          # Text submitted on click, e.g. "in 2023"
```

### `ChatMessage` (Chat Turn Representation)
```python
class ChatMessage(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str                  # Unique message UUID
    role: str                # "user" | "assistant"
    kind: str                # "text" | "result" | "clarification" | "refusal" | "error" | "knowledge" | "options"
    text: str                # Human-readable message or summary text
    card_id: Optional[str] = None       # ID of saved QueryCard (for results only; plots never stored)
    understood_as: Optional[str] = None # Provenance line: e.g. "Understood as: TEMP profile in Arabian Sea [rules]..."
    options: list[ChatOption] = Field(default_factory=list) # Structured clickable alternatives
    created_at: str          # ISO 8601 UTC timestamp
```

---

## 4. Plot Rendering & Parquet Cache Boundary

**Hard Rule**: Plotly figure dictionaries and observation arrays are **never** stored in `ChatMessage` objects or the SQLite database.
- A `kind="result"` message stores only its `card_id`.
- When rendering:
  - If the message is the **newest result**, full tabs and Plotly figures are automatically re-rendered from the local Parquet cache via `restore_card_result(card)`.
  - If the message is an **older result**, it renders in compact mode (showing `understood_as`, observation counts, and answer text) alongside a "Show plots" button. Clicking this button dynamically restores figures for that card.
  - If the local Parquet file is missing, the card displays metadata and a notice: *"Data expired, re-run to see plots"*.

---

## 5. Persistence & Multi-Session Isolation

1. **SQLite Storage (`data/cards.sqlite`)**:
   Table: `chat_messages`
   ```sql
   CREATE TABLE IF NOT EXISTS chat_messages (
       session_id TEXT NOT NULL,
       position INTEGER NOT NULL,
       message_id TEXT PRIMARY KEY,
       role TEXT NOT NULL,
       kind TEXT NOT NULL,
       text TEXT NOT NULL,
       card_id TEXT,
       understood_as TEXT,
       options_json TEXT,
       created_at TEXT NOT NULL
   );
   CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages (session_id, position);
   ```

2. **Session Semantics**:
   - Respects `SIQVA_SHARED_HISTORY`:
     - If `SIQVA_SHARED_HISTORY=1` (default): messages are visible across runs unless a specific `session_id` is assigned.
     - If `SIQVA_SHARED_HISTORY=0`: conversations are isolated strictly by `session_id`.
   - Browser URL sync: `st.query_params["session_id"] = session_id` ensures browser refreshes restore the active conversation.

3. **Message Capacity**:
   - `MAX_STORED_MESSAGES = 100`.
   - Displays up to 100 messages; earlier messages are retained in SQLite and can be loaded via a "Load earlier messages" button.

---

## 6. Safety & Sanitization

1. **Length Capping**:
   - Questions exceeding `MAX_QUESTION_LENGTH = 500` characters are rejected immediately before dispatch:
     *"Your question is too long (over 500 characters). Please condense your query."*
2. **XSS Prevention**:
   - All user inputs and model outputs rendered in HTML contexts must pass through `html.escape()`.
   - No user-controlled strings are rendered via `unsafe_allow_html=True`.
3. **Traceback Suppression**:
   - Unexpected exceptions generate a short random reference ID (`ref_id = uuid.uuid4().hex[:8]`), logging details to `logs/siqva.log` while displaying:
     *"An internal error occurred while processing your request (Ref: {ref_id}). Please try again."*
