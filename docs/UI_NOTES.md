# UI Investigation & Design Notes: SIQVA Chat Interface

This document records the architectural investigation, CSS injection points, DOM structures, and overflow causes in the SIQVA chat interface for Streamlit 1.57.0.

---

## 1. CSS Injection Points & Message Containers

### Existing CSS Injection Locations
1. **`app/ui.py` (lines 78–250)**:
   - Primary dark theme stylesheet injected via `st.markdown("<style>...</style>", unsafe_allow_html=True)`.
   - Defines CSS variables (`--bg-canvas`, `--bg-surface`, `--accent-ocean`, etc.), fonts, sidebar hairline borders, and header adjustments.
   - Contains global monospace overrides for code blocks, metrics, and tags.
2. **`app/ui.py` (lines 1424–1437)**:
   - Dynamic sidebar navigation button highlight styling (`.st-key-{active_nav_key} button`).
3. **`app/old_ui.py` (lines 49–90)**:
   - Legacy standalone form UI stylesheet (deprecated, retained for reference only).

### Confirmed Message Containers (Streamlit 1.57.0)
Verified against installed static bundle (`site-packages/streamlit/static/static/js/src.D9MArGZj.js` and `index.D2ZqaFuW.js`):
- **Outer Message Row**: `[data-testid="stChatMessage"]` / `.stChatMessage`
  - Styled with `display: flex; align-items: flex-start; gap: 0.5rem; width: 100%;`
- **Avatar Container**:
  - Default User: `[data-testid="stChatMessageAvatarUser"]` (red background, `:material/face:`)
  - Default Assistant: `[data-testid="stChatMessageAvatarAssistant"]` (orange background, `:material/smart_toy:`)
  - Custom Avatar: `[data-testid="stChatMessageAvatarCustom"]` (renders custom image, emoji, or icon)
- **Message Content Bubble**: `[data-testid="stChatMessageContent"]` / `.stChatMessageContent`
  - Styled with `flex-grow: 1; min-width: 0; margin: auto; color: bodyText;`
- **Application Layout Shell**:
  - `[data-testid="stAppViewContainer"]`: Main outer app container.
  - `[data-testid="stMainBlockContainer"]`: Central content column.
  - `[data-testid="stBottomBlockContainer"]`: Fixed bottom area containing `st.chat_input`.

---

## 2. Overflow Causes and Structural Analysis

| Overflow Candidate | Why It Can Overflow in Streamlit | Mitigation in `chat.css` |
| :--- | :--- | :--- |
| **"Understood as" Caption** | Rendered via `st.caption` with long coordinate strings, dates, and provenance tags. In flex children without `min-width: 0` or if given nowrap styling, it stretches past the viewport. | Apply `overflow-wrap: anywhere; word-break: break-word;` and format provenance tags as inline chips. |
| **Citations and Long Links** | URLs (e.g. `https://doi.org/...` or `https://argopy.readthedocs.io/...`) contain no whitespace. In standard CSS, continuous character sequences do not wrap by default. | Set `a { overflow-wrap: anywhere; word-break: break-word; }` and ensure inline display inside bubbles. |
| **Long Hashes & IDs** | 64-character SHA-256 data hashes, spec keys, and cycle identifiers have no whitespace breakpoints. | Apply `word-break: break-all;` or `overflow-wrap: anywhere;` on monospace chip containers. |
| **DataFrames** | Streamlit DataFrames use Glide Data Grid with fixed column widths and minimum canvas sizing. | Constrain parent container with `max-width: 100%; overflow-x: auto;` to prevent spilling outside the bubble. |
| **Code Blocks (`<pre><code>`)** | Standard browser `<pre>` elements default to `white-space: pre;`. Long generated scripts or shell commands push out the right boundary. | Set `pre, code { white-space: pre-wrap !important; word-break: break-word !important; overflow-x: auto; }`. |
| **Markdown Tables (`<table>`)** | HTML tables default to sizing based on their content (`max-content`). Multi-column tables exceed 900px on narrow viewports. | Set `table { display: block; max-width: 100%; overflow-x: auto; }` so wide tables scroll horizontally inside the message bubble. |
| **Plotly Charts** | Plotly embeds SVG and WebGL canvases with fixed pixel layout dimensions. | Wrap in responsive containers with `max-width: 100% !important; overflow-x: auto;`. |
| **Option-Button Rows** | Using `st.columns(3)` inside chat messages creates parallel flex columns. Long button labels cannot shrink below their min-content width. | Replace rigid columns with a CSS flex-wrap container (`display: flex; flex-wrap: wrap; gap: 8px;`). |
| **Expanders** | `[data-testid="stExpander"]` can overflow if inner child elements lack `min-width: 0`. | Enforce `min-width: 0; max-width: 100%;` on expander details and summary. |

---

## 3. Theme & Palette Specifications
- **Theme Name**: Deep Ocean
- **Palette**:
  - Primary Accent (Teal): `#2EC4B6`
  - Background Canvas: `#0B1F2A`
  - Surface Panels / Assistant Bubbles: `#12303F`
  - User Bubble Tint: `#1A3B4D` (subtle teal-tinted border `#2EC4B6`)
  - Primary Text: `#E6F1F5`
  - Secondary / Muted Text: `#8EABC0`
  - Hairline Borders: `#1E4255`
- **Typography**:
  - Body: Modern Sans-Serif (`Inter`, -apple-system, BlinkMacSystemFont, `Segoe UI`, Roboto, sans-serif) at minimum 15px.
  - Monospace: `JetBrains Mono`, `Fira Code`, monospace strictly for code spans, provenance chips, and hashes.

---

## 4. Implementation Details (U1 & U2)

### U1: Look, Layout, and Styling
- **Stylesheet (`app/assets/chat.css`)**:
  - Centered 900px maximum column width on `stMainBlockContainer` and `stBottomBlockContainer`.
  - User bubble: right-aligned (`flex-direction: row-reverse; margin-left: auto; max-width: 82%`) with background `#1A3B4D` and teal border `rgba(46, 196, 182, 0.35)`.
  - Assistant bubble: left-aligned (`margin-right: auto; max-width: 95%`) with surface panel `#12303F` and border `#1E4255`.
  - Enforced `overflow-wrap: anywhere !important; word-break: break-word !important; min-width: 0 !important;` on message content.
  - Constrained `<pre>`, `<code>`, `[data-testid="stTable"]`, `[data-testid="stDataFrame"]`, and `[data-testid="stPlotlyChart"]` to 100% max-width with horizontal scroll.
- **Custom Avatars (`app/assets/assistant_avatar.png`, `app/assets/user_avatar.png`)**:
  - High-DPI theme-aligned avatars generated via PIL.
  - Assistant: Oceanic wave symbol in `#2EC4B6` on dark circle `#0B1F2A`.
  - User: Neutral person silhouette in soft white `#E6F1F5` on `#1A3B4D`.
  - Passed explicitly to every `st.chat_message` call (`avatar=USER_AVATAR`, `avatar=ASSISTANT_AVATAR`).
- **Header & Navigation**:
  - Minimal toolbar configured in `.streamlit/config.toml` (`client.toolbarMode = "minimal"`).
  - Top bar text decluttered to clean title ("SIQVA") and subtitle ("Argo ocean float question answering & physical oceanography").
  - Sidebar navigation updated to readable labels: `New chat`, `Plot Graph`, `Compare Runs`, `Sources`, and `History`.
  - Provenance labels formatted into clean inline code chips (`` `rules` ``, `` `llm` ``, `` `default` ``).
- **Empty State Gallery**:
  - Displays welcome header and 6 pre-validated example queries from `data/examples.json` arranged in a 2x3 grid.
  - Includes deterministic cache status badges (`• cached`) dynamically computed from local Parquet cache existence.

### U2: Processing Indicators & Word-Level Streaming
- **Module `src/siqva/streaming.py`**:
  - `chunk_text(text: str)`: Markdown-aware tokenizer preserving links, inline code spans, block code fences, and table rows intact while chunking normal text at word boundaries.
  - `stream_text(text, sleep_fn, words_per_second=40.0, max_seconds=2.0, min_ms=400.0)`: Paces output with bounded delays and injectable sleep function to avoid test starvation.
  - Toggle via `SIQVA_STREAM` environment variable (1 enabled, 0 disabled) and session state toggle.
- **Rendering & Replay Suppression**:
  - Newest assistant message streams answer text via `st.write_stream(stream_text(msg.text))`.
  - Tracks `streamed_msg_ids` in `st.session_state` so subsequent reruns never replay the stream.
  - Animated typing indicator styles supporting `prefers-reduced-motion` media queries.
  - `st.chat_input` disabled while streaming.

---

## 5. MLOps, Telemetry, and Guardrail Audit (U3 Investigation)

### Provenance and Origin
- **Commit**: `e5cb9dd93869e9b5c63a1b33e04e2a8f3fea6a4c` (Sun Nov 15 16:47:35 2026 +0530)
- **Author**: Sangeen (`sangeensingh2006@gmail.com`)
- **Stated Purpose**: Implements a lightweight MLOps workflow for query classification, data lineage via SHA-256 dataset hashing, calibrated TF-IDF + LinearSVC guardrail classifier, local SQLite telemetry tracking, and CI/CD quality gate (`tests/test_mlops_gate.py`).

### Privacy and Telemetry Findings
1. **What is recorded**:
   - `timestamp`: UTC ISO 8601 string.
   - `query_text`: The user's verbatim natural language query string. (If the user query mentions specific ocean regions or coordinates, those appear in the query string).
   - `predicted_class`: Output class label (e.g. `DATA_QUERY`, `CONCEPT_QUERY`, `ADVERSARIAL_INJECTION`, `REFUSAL_OUT_OF_SCOPE`).
   - `confidence`: Calibrated classification probability (float, 0.0 to 1.0).
   - `oov_ratio`: Out-of-vocabulary token ratio against training vocabulary.
   - `latency_ms`: Classification runtime in milliseconds.
   - `flagged_for_review`: Binary integer (0 or 1) indicating active learning triage.
2. **What is NOT recorded**:
   - **No profile data**: Profile values, salinity, temperature, pressure records, or Parquet datasets are NEVER logged.
   - **No file paths**: File paths on host or client machine are not logged.
   - **No API keys / secrets**: LLM keys, environment variables, or secrets are NEVER stored or passed to the telemetry table.
3. **Where it is stored**:
   - Stored in a local SQLite file at `data/telemetry.sqlite` (table `inference_logs`).
   - Database is local-only; file pattern `*.sqlite` is ignored in `.gitignore`.
4. **Network and Cloud Communication**:
   - **Zero external communication**: Model inference uses local `joblib` artifacts (`models/guardrail_prod.joblib`); database logging uses standard Python `sqlite3`. Nothing leaves the machine.
5. **Dependencies**:
   - `scikit-learn`, `joblib`, `numpy` (already installed in virtual environment).
6. **Test Coverage**:
   - Tested in `tests/test_mlops_gate.py` (verifying macro F1 >= 0.90, latency < 5 ms, injection blocking, and drift tracking).

### Gating and Administrative Controls
- **Admin Gating Requirement**: The MLOps page (`active_page == "mlops"`), the sidebar navigation button (`● MLOps & Telemetry`), and the sidebar guardrail toggle (`MLflow Guardrail`) are **completely hidden** unless the environment variable `SIQVA_ADMIN=1` is explicitly set.
- **Runtime Suppression**: When `SIQVA_ADMIN` is unset or not `"1"`:
  - `is_guardrail_enabled()` returns `False` immediately.
  - `GuardrailRouter` does NOT create or open `data/telemetry.sqlite`.
  - No predictions or telemetry logs are executed or written to disk.
  - Visitors and regular users see only the standard oceanographic interface.

---

## 6. Owner Visual Checklist (Manual Verification)

Because Playwright and browser binaries are not installed in the execution environment, automated browser screenshots could not be taken. The following manual inspection checklist covers visual layout and overflow verification across window sizes:

1. **Normal and Narrow Windows (1400 px, 1000 px, 600 px)**:
   - [ ] At 1400 px: Centered 900 px chat container with balanced margins.
   - [ ] At 1000 px: Header buttons (`🗑️ Clear`, `➕ New`) remain on a single line (`white-space: nowrap`) without wrapping.
   - [ ] At 600 px: Responsive wrap on message bubbles; user bubble right-aligned (max 82% width), assistant bubble left-aligned (max 95% width).
2. **Long Link and Continuous Strings**:
   - [ ] Submit a message containing a 200+ character URL or continuous hash (e.g. `https://example.com/` + 180 chars).
   - [ ] Verify URL wraps cleanly within message boundary (`overflow-wrap: anywhere`) without horizontal page blow-out.
3. **Clarification Messages**:
   - [ ] Submit `"temperature in the Arabian Sea"`.
   - [ ] Verify message shows a single clean warning sentence naming what is missing + one example.
   - [ ] Verify no duplicated text or repeated sentence headers.
   - [ ] Verify targeted year pills `['2026', '2025', '2024', '2023', '2022']` render cleanly, wrapping without button overflow.
   - [ ] Click a year pill (e.g. `2025`); verify turn appends as user query and runs.
4. **Out-of-Scope Refusal**:
   - [ ] Submit `"how to build a llm"`, `"write me a python script"`, or `"best pizza recipe"`.
   - [ ] Verify question is refused immediately with Category 5 refusal sentence (`"SIQVA only answers questions regarding physical oceanography..."`).
   - [ ] Verify it is NOT clarified or treated as a data query.
5. **Empty State Gallery**:
   - [ ] Open fresh chat session; verify empty state displays centered title and 6 clean starter buttons in a 2x3 grid.
   - [ ] Verify cache status indicators (`• cached`) render neatly.
6. **Typing Dots & Word-Level Streaming**:
   - [ ] With `SIQVA_STREAM=1`, verify word-level streaming flows smoothly on newest assistant response.
   - [ ] Verify typing dots animate during execution.
   - [ ] With `SIQVA_STREAM=0`, verify response appears instantly without delay or streaming.
   - [ ] On rerun, verify previous turns do not replay streaming animations.
7. **Button Labels**:
   - [ ] Verify all button labels are <= 28 characters with full descriptions in hover tooltips.
