"""Pure chat dispatcher, message models, and SQLite persistence for SIQVA (C1).

Provides:
- ChatMessage and ChatOption models
- Pure dispatch(question, conversation_state, ...) routing user questions to assistant responses
- SQLite persistence in table chat_messages using closing(sqlite3.connect(...)) pattern
- Zero Streamlit imports; fully testable offline with mocked fetcher
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field

from .card import DEFAULT_DB_PATH, _resolve_db_path, is_history_shared
from .followup import ConversationState, try_resolve_followup
from .interpretation import build_understood_from_spec, format_understood_as
from .pipeline import PipelineResult, PipelineStatus, run, run_spec
from .router import RouteTarget, has_domain_signal, route
from .spec import DataMode

MAX_QUESTION_LENGTH: int = 500
MAX_STORED_MESSAGES: int = 100


class ChatOption(BaseModel):
    """Structured interactive alternative action inside a chat message."""

    model_config = ConfigDict(frozen=True)

    label: str
    action_type: str = "query"  # "query", "plan_option", "clarification"
    query_text: str = ""


class ChatMessage(BaseModel):
    """Immutable chat turn in the persistent conversation."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    role: str  # "user" | "assistant"
    kind: str  # "text" | "result" | "clarification" | "refusal" | "error" | "knowledge" | "options"
    text: str
    card_id: Optional[str] = None
    understood_as: Optional[str] = None
    options: list[ChatOption] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )


# ==============================================================================
# GREETINGS & REFUSAL LOADERS (DYNAMIC FROM FILES)
# ==============================================================================


def _load_greetings_from_scope() -> dict[str, str]:
    """Dynamically load fixed greeting and courtesy sentences from knowledge/scope.md."""
    scope_path = Path("knowledge/scope.md")
    greeting = (
        "Hello! I am SIQVA, an assistant for exploring Argo ocean float data and "
        "physical oceanography. How can I help you today?"
    )
    courtesy = "You are welcome! Let me know if you have more questions about Argo ocean data."
    if scope_path.exists():
        try:
            content = scope_path.read_text(encoding="utf-8")
            m_g = re.search(r'Fixed Greeting Reply Sentence:\s*\n\s*>\s*"(.*?)"', content)
            if m_g:
                greeting = m_g.group(1).strip()
            m_c = re.search(r'Fixed Courtesy Reply Sentence:\s*\n\s*>\s*"(.*?)"', content)
            if m_c:
                courtesy = m_c.group(1).strip()
        except Exception:
            pass
    return {"greeting": greeting, "courtesy": courtesy}


def _load_refusal_categories() -> list[dict[str, Any]]:
    """Dynamically load refusal categories and standard sentences from data/refusal_categories.json."""
    cat_file = Path("data/refusal_categories.json")
    if cat_file.exists():
        try:
            with open(cat_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("categories", [])
        except Exception:
            pass
    return []


# Refusal keyword triggers mapped to refusal category numbers (1-9)
_REFUSAL_TRIGGERS: list[tuple[int, list[re.Pattern]]] = [
    (
        1,
        [
            re.compile(r"\b(forecast|predict|prediction|next week|next month|next year|late 202\d|in 202[7-9])\b", re.IGNORECASE),
            re.compile(r"\b(will there be|will it cause|temperature.*be next)\b", re.IGNORECASE),
        ],
    ),
    (
        2,
        [
            re.compile(r"\b(why did cyclone|why did the .* form|did global warming (?:directly )?cause|caused by global warming)\b", re.IGNORECASE),
            re.compile(r"\b(causal attribution|directly trigger cyclone)\b", re.IGNORECASE),
        ],
    ),
    (
        3,
        [
            re.compile(r"\b(satellite\s+sst|modis|era5|reanalysis|surface drifter|global drifter program|gdp drifter|hycom)\b", re.IGNORECASE),
        ],
    ),
    (
        4,
        [
            re.compile(r"\b(antibiotic|prescribe|open wound|medical advice|clinical advice|jellyfish sting|vibrio)\b", re.IGNORECASE),
        ],
    ),
    (
        5,
        [
            re.compile(r"\b(poem about|french revolution|world cup|fifa|who won|election|stock market)\b", re.IGNORECASE),
        ],
    ),
    (
        6,
        [
            re.compile(r"\b(woce|go-ship|glider|marine mammal|shipboard ctd|bottle data)\b", re.IGNORECASE),
        ],
    ),
    (
        7,
        [
            re.compile(r"\b(ship navigation|marine navigation|search and rescue|voyage planning|navigational hazard)\b", re.IGNORECASE),
        ],
    ),
    (
        8,
        [
            re.compile(r"\b(cod abundance|fish abundance|fish stock|fisheries management|coral reef ecology)\b", re.IGNORECASE),
        ],
    ),
    (
        9,
        [
            re.compile(r"\b(ignore (?:all )?previous instructions|system prompt|reveal internal|override (?:safety|validation))\b", re.IGNORECASE),
        ],
    ),
]

_GREETING_PATTERNS = [
    re.compile(r"^\s*(hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening)\b", re.IGNORECASE),
]

_COURTESY_PATTERNS = [
    re.compile(r"^\s*(thank\s+you|thanks|thx|much\s+appreciated)\b", re.IGNORECASE),
    re.compile(r"^\s*(ok|okay|cool|great|got\s+it)[\.!\s]*$", re.IGNORECASE),
]


def _match_refusal(text: str) -> Optional[str]:
    """Return standard refusal sentence if question matches a refusal category."""
    cats = _load_refusal_categories()
    cat_by_num = {c["category_number"]: c["refusal_sentence"] for c in cats if "category_number" in c}

    for cat_num, patterns in _REFUSAL_TRIGGERS:
        for pat in patterns:
            if pat.search(text):
                return cat_by_num.get(cat_num)
    return None


# ==============================================================================
# SQLITE PERSISTENCE
# ==============================================================================


def _init_chat_db(conn: sqlite3.Connection) -> None:
    """Initialize chat_messages table and indices in SQLite."""
    with conn:
        conn.execute(
            """
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
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages (session_id, position)"
        )


def save_chat_message(
    msg: ChatMessage,
    session_id: str = "default",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """Persist a single chat message to SQLite store."""
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(path)) as conn:
        _init_chat_db(conn)
        with conn:
            cur = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM chat_messages WHERE session_id = ?",
                (session_id,),
            )
            pos = cur.fetchone()[0]

            options_json = json.dumps([opt.model_dump() for opt in msg.options], ensure_ascii=False)
            conn.execute(
                """
                INSERT OR REPLACE INTO chat_messages (
                    session_id, position, message_id, role, kind, text, card_id, understood_as, options_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    pos,
                    msg.id,
                    msg.role,
                    msg.kind,
                    msg.text,
                    msg.card_id,
                    msg.understood_as,
                    options_json,
                    msg.created_at,
                ),
            )


def load_chat_messages(
    session_id: str = "default",
    limit: int = MAX_STORED_MESSAGES,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[ChatMessage]:
    """Load ordered chat messages for a session from SQLite store."""
    path = _resolve_db_path(db_path)
    if not path.exists():
        return []

    messages: list[ChatMessage] = []

    with closing(sqlite3.connect(path)) as conn:
        _init_chat_db(conn)
        query = (
            "SELECT message_id, role, kind, text, card_id, understood_as, options_json, created_at "
            "FROM chat_messages WHERE session_id = ? ORDER BY position ASC LIMIT ?"
        )
        cur = conn.execute(query, (session_id, limit))

        for row in cur.fetchall():
            m_id, role, kind, text, card_id, understood_as, opt_json, created_at = row
            opts: list[ChatOption] = []
            if opt_json:
                try:
                    raw_opts = json.loads(opt_json)
                    opts = [ChatOption(**o) for o in raw_opts]
                except Exception:
                    pass
            messages.append(
                ChatMessage(
                    id=m_id,
                    role=role,
                    kind=kind,
                    text=text,
                    card_id=card_id,
                    understood_as=understood_as,
                    options=opts,
                    created_at=created_at,
                )
            )
    return messages


def clear_chat_messages(
    session_id: str = "default",
    db_path: Path | str = DEFAULT_DB_PATH,
) -> None:
    """Delete chat messages for a session from SQLite store."""
    path = _resolve_db_path(db_path)
    if not path.exists():
        return

    with closing(sqlite3.connect(path)) as conn:
        _init_chat_db(conn)
        with conn:
            conn.execute("DELETE FROM chat_messages WHERE session_id = ?", (session_id,))


# ==============================================================================
# PURE DISPATCHER
# ==============================================================================


def _extract_understood_as(res: PipelineResult) -> Optional[str]:
    """Extract deterministic 'Understood as' line from a pipeline result.

    Returns None if no query field came from the question (provenance rules or llm).
    """
    prov: dict[str, str] = {}
    if res.parse_outcome is not None and getattr(res.parse_outcome, "provenance", None):
        prov = dict(res.parse_outcome.provenance)
    elif res.spec is not None:
        _, prov = build_understood_from_spec(res.spec)

    has_question_field = any(
        isinstance(v, str) and (v.startswith("rules") or v.startswith("llm"))
        for k, v in prov.items()
        if k in ("region", "date_range", "variables", "intent")
    )
    if not has_question_field:
        return None

    if res.parse_outcome is not None and getattr(res.parse_outcome, "understood", None) is not None:
        try:
            return format_understood_as(res.parse_outcome.understood, res.parse_outcome.provenance)
        except Exception:
            pass
    if res.spec is not None:
        try:
            understood, prov_built = build_understood_from_spec(res.spec)
            return format_understood_as(understood, prov_built)
        except Exception:
            pass
    return None


def _load_welcome_example_options() -> list[ChatOption]:
    """Load 4 example pills from data/examples.json."""
    ex_file = Path(__file__).resolve().parent.parent.parent / "data" / "examples.json"
    options: list[ChatOption] = []
    if ex_file.exists():
        try:
            with open(ex_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for ex in data.get("examples", [])[:4]:
                lbl = ex.get("label", "").replace("[", "").replace("]", "").replace("//", "·").strip()
                if len(lbl) > 28:
                    lbl = lbl[:27] + "…"
                options.append(
                    ChatOption(
                        label=lbl or ex["region"],
                        action_type="clarification",
                        query_text=ex["question"],
                    )
                )
        except Exception:
            pass
    if not options:
        options = [
            ChatOption(label="MLD · Bay of Bengal", action_type="clarification", query_text="thermocline and barrier layer in Bay of Bengal April 2022"),
            ChatOption(label="TCHP · Arabian Sea", action_type="clarification", query_text="cyclone heat potential tchp in Arabian Sea May 2022"),
            ChatOption(label="SOFAR · Arabian Sea", action_type="clarification", query_text="acoustic sound speed profile in Arabian Sea January 2022"),
            ChatOption(label="T-S · Bay of Bengal", action_type="clarification", query_text="temperature and salinity profiles in Bay of Bengal January 2022"),
        ]
    return options


def _build_clarification_message_and_options(
    question: str,
    res: PipelineResult,
) -> tuple[str, list[ChatOption], Optional[str]]:
    """Build a clean single-sentence clarification message and targeted pills per Step 2."""
    from datetime import date

    prov = getattr(res.parse_outcome, "provenance", {}) or {}
    clarification = res.clarification

    missing = list(clarification.missing_fields) if clarification and clarification.missing_fields else []
    ambiguous = list(clarification.ambiguous_fields) if clarification and clarification.ambiguous_fields else []

    has_any_signal = any(
        isinstance(v, str) and (v.startswith("rules") or v.startswith("llm"))
        for k, v in prov.items()
        if k in ("region", "date_range", "variables", "intent")
    )

    # 1. Nothing understood: 4 welcome examples from data/examples.json, no "Understood as"
    if not has_any_signal:
        msg_text = "Please specify an ocean region, variable, and time period (e.g. 'temperature in the Arabian Sea in 2022')."
        return msg_text, _load_welcome_example_options(), None

    understood_as = _extract_understood_as(res)

    # 2. Unsupported or ambiguous region
    if ambiguous or (clarification and any("unsupported" in s.lower() or "pacific" in s.lower() for s in clarification.suggestions)):
        msg_text = "The requested region is unsupported; please choose a supported basin or coordinates (e.g. 'in the Arabian Sea')."
        region_names = ["Arabian Sea", "Bay of Bengal", "Indian Ocean", "North Atlantic", "Mediterranean Sea", "Nino 3.4"]
        options = []
        for r_name in region_names:
            q_text = re.sub(r"\bin\s+[a-zA-Z0-9_\s\+\-]+", f"in {r_name}", question, flags=re.IGNORECASE) if "in " in question.lower() else f"{question} in {r_name}"
            options.append(ChatOption(label=r_name, action_type="clarification", query_text=q_text))
        return msg_text, options, understood_as

    # 3. Only date_range / year missing
    if "date_range" in missing and "region" not in missing and "variables" not in missing:
        msg_text = "Please specify a year or date range (e.g. 'in 2022')."
        curr_year = date.today().year
        year_options = [str(curr_year - i) for i in range(5)]
        options = [
            ChatOption(label=y, action_type="clarification", query_text=f"{question} in {y}")
            for y in year_options
        ]
        return msg_text, options, understood_as

    # 4. Region missing
    if "region" in missing and "variables" not in missing:
        if "date_range" in missing:
            msg_text = "Please specify a region and date range (e.g. 'temperature in the Arabian Sea in 2022')."
            region_names = ["Arabian Sea", "Bay of Bengal", "Indian Ocean", "North Atlantic", "Mediterranean Sea"]
            options = [
                ChatOption(label=r_name, action_type="clarification", query_text=f"{question} in {r_name} in 2022")
                for r_name in region_names
            ]
        else:
            msg_text = "Please specify a region or coordinates (e.g. 'in the Arabian Sea')."
            region_names = ["Arabian Sea", "Bay of Bengal", "Indian Ocean", "North Atlantic", "Mediterranean Sea", "Nino 3.4"]
            options = [
                ChatOption(label=r_name, action_type="clarification", query_text=f"{question} in {r_name}")
                for r_name in region_names
            ]
        return msg_text, options, understood_as

    # 5. Variables missing
    if "variables" in missing:
        msg_text = "Please specify an ocean variable such as temperature or salinity (e.g. 'temperature in the Arabian Sea in 2022')."
        options = [
            ChatOption(label=v, action_type="clarification", query_text=f"{v.lower()} {question}")
            for v in ["TEMP", "PSAL", "PRES"]
        ]
        return msg_text, options, understood_as

    # Generic fallback
    missing_desc = ", ".join(missing) if missing else "required query parameters"
    msg_text = f"Please specify {missing_desc} (e.g. 'temperature in the Arabian Sea in 2022')."
    curr_year = date.today().year
    options = [
        ChatOption(label=str(curr_year - i), action_type="clarification", query_text=f"{question} in {curr_year - i}")
        for i in range(5)
    ]
    return msg_text, options, understood_as


def dispatch(
    question: str,
    conversation_state: Optional[ConversationState] = None,
    mode: Optional[DataMode] = None,
    max_request_size: Optional[float] = None,
    force_refresh: bool = False,
    session_id: Optional[str] = None,
    fetcher_fn: Any = None,
    on_result: Optional[Any] = None,
) -> tuple[list[ChatMessage], ConversationState]:
    """Pure dispatcher: routes a user question to assistant responses without Streamlit dependencies.

    Args:
        question: User query string.
        conversation_state: Prior conversation context for follow-up query resolution.
        mode: Explicit DataMode override (defaults to research).
        max_request_size: Optional size cap override.
        force_refresh: Bypass Parquet cache if True.
        session_id: Session identifier for multi-session isolation.
        fetcher_fn: Optional fetcher callable or class for offline testing.
        on_result: Optional callback invoked with the raw PipelineResult if a pipeline was executed.

    Returns:
        tuple[list[ChatMessage], ConversationState]: Generated assistant messages and updated state.
    """
    c_state = conversation_state or ConversationState()
    q_clean = question.strip()

    # 1. Safety length cap check (must be rejected before any other work)
    if len(q_clean) > MAX_QUESTION_LENGTH:
        msg = ChatMessage(
            role="assistant",
            kind="error",
            text=f"Your question is too long ({len(q_clean)} characters). Please condense your query to under {MAX_QUESTION_LENGTH} characters.",
        )
        return [msg], c_state

    # 2. Conversational greetings and courtesy checks
    greetings = _load_greetings_from_scope()
    for pat in _GREETING_PATTERNS:
        if pat.match(q_clean):
            msg = ChatMessage(role="assistant", kind="text", text=greetings["greeting"])
            return [msg], c_state

    for pat in _COURTESY_PATTERNS:
        if pat.match(q_clean):
            msg = ChatMessage(role="assistant", kind="text", text=greetings["courtesy"])
            return [msg], c_state

    # 2.5 MLOps Guardrail & Telemetry Drift Monitor
    guardrail_res = None
    try:
        from .mlops_guardrail import GuardrailRouter, is_guardrail_enabled
        if is_guardrail_enabled():
            guardrail_res = GuardrailRouter().predict_and_log(q_clean)
            # Block adversarial prompt injection immediately
            if guardrail_res.get("raw_label") == "ADVERSARIAL_INJECTION" and not guardrail_res.get("flagged"):
                cats = _load_refusal_categories()
                cat9 = next((c["refusal_sentence"] for c in cats if c.get("category_number") == 9), None)
                ref_msg = cat9 or "SIQVA cannot reveal hidden system prompts or developer instructions, nor can safety boundaries and validation rules be overridden."
                msg = ChatMessage(role="assistant", kind="refusal", text=ref_msg)
                return [msg], c_state
    except Exception:
        pass

    # 3. Standard refusal check (Categories 1-9) vs Mixed Request
    pure_refusal = _match_refusal(q_clean)
    from .knowledge import is_data_query
    is_mixed = bool(pure_refusal and is_data_query(q_clean))

    if pure_refusal and not is_mixed:
        msg = ChatMessage(role="assistant", kind="refusal", text=pure_refusal)
        return [msg], c_state

    # 4. Follow-up check against existing ConversationState
    if c_state.last_spec is not None:
        followup = try_resolve_followup(q_clean, c_state)
        if followup.resolved and followup.spec is not None:
            target_spec = followup.spec
            if mode is not None and target_spec.mode != mode:
                target_spec = target_spec.model_copy(update={"mode": mode})

            res = run_spec(
                target_spec,
                fetcher_fn=fetcher_fn,
                force_refresh=force_refresh,
                question=q_clean,
                max_request_size=max_request_size,
                session_id=session_id,
            )
            if on_result is not None:
                try:
                    on_result(res)
                except Exception:
                    pass
            msgs, new_state = _convert_pipeline_result(res, q_clean, c_state)
            if is_mixed and pure_refusal:
                msgs.append(ChatMessage(role="assistant", kind="refusal", text=pure_refusal))
            return msgs, new_state

    # 5. Routing classification
    route_res = route(q_clean)

    if route_res.target == RouteTarget.META:
        card = None
        if c_state.last_card_id:
            from .card import load_card
            card = load_card(c_state.last_card_id, session_id=session_id)
        if card is not None:
            text = (
                f"Last query: **{card.spec.intent.value.title()}** in {card.region_name} | "
                f"Mode: **{card.mode.value}** | Profiles: **{card.profile_count:,}** | Rows: **{card.row_count:,}** | "
                f"argopy: `{card.argopy_version}` | xarray: `{card.xarray_version}`"
            )
        else:
            text = "No query has been run in this session yet."
        msg = ChatMessage(role="assistant", kind="text", text=text)
        return [msg], c_state

    # 5.5 In-domain gate (pure rules): require at least one ocean/Argo domain signal
    if not has_domain_signal(q_clean, state=c_state):
        cats = _load_refusal_categories()
        cat5 = next((c["refusal_sentence"] for c in cats if c.get("category_number") == 5), None)
        ref_msg = cat5 or "SIQVA only answers questions regarding physical oceanography and the international Argo float array; general non-marine topics are not supported."
        msg = ChatMessage(role="assistant", kind="refusal", text=ref_msg)
        return [msg], c_state

    # 6. Knowledge & Glossary route (Grounded verbatim answers, 0 LLM calls)
    is_conceptual = bool(
        re.search(r"^\s*(what is|what are|how does|how do|why does|why do|explain|tell me about)\b", q_clean, re.IGNORECASE)
    )
    if (route_res.target == RouteTarget.GLOSSARY or is_conceptual) and not is_data_query(q_clean):
        from .knowledge import answer as knowledge_answer

        ans = knowledge_answer(q_clean)
        if ans.kind == "answer":
            prefix = "[Unverified note]\n\n" if ans.status == "unverified" else ""
            sources_md = ""
            if ans.citations:
                from .knowledge import format_citation
                cits = [format_citation(cit, status=ans.status) for cit in ans.citations]
                sources_md = f"\n\n*Sources*: {'; '.join(cits)}"
            full_text = f"{prefix}{ans.text}{sources_md}"

            options: list[ChatOption] = []
            if len(ans.note_ids) > 1:
                for nid in ans.note_ids[1:3]:
                    label = nid.replace("-", " ").title()
                    options.append(ChatOption(label=label, action_type="knowledge", query_text=f"what is {label.lower()}"))

            msg = ChatMessage(role="assistant", kind="knowledge", text=full_text, options=options)
            return [msg], c_state

        elif ans.kind == "refusal":
            msg = ChatMessage(role="assistant", kind="refusal", text=ans.text)
            return [msg], c_state

        elif ans.kind == "not_in_notes":
            opt = ChatOption(label="See sources", action_type="sources", query_text="")
            msg = ChatMessage(role="assistant", kind="knowledge", text=ans.text, options=[opt])
            return [msg], c_state

    # 7. Primary Data Pipeline (DATA_FETCH, OPERATION, COMPARISON, CLARIFICATION)
    res = run(
        question=q_clean,
        fetcher_fn=fetcher_fn,
        force_refresh=force_refresh,
        max_request_size=max_request_size,
        session_id=session_id,
    )
    if res.spec and mode is not None and res.spec.mode != mode:
        res = run_spec(
            res.spec.model_copy(update={"mode": mode}),
            fetcher_fn=fetcher_fn,
            force_refresh=force_refresh,
            question=q_clean,
            max_request_size=max_request_size,
            session_id=session_id,
        )

    if on_result is not None:
        try:
            on_result(res)
        except Exception:
            pass

    msgs, new_state = _convert_pipeline_result(res, q_clean, c_state)
    if is_mixed and pure_refusal:
        msgs.append(ChatMessage(role="assistant", kind="refusal", text=pure_refusal))
    return msgs, new_state


def _convert_pipeline_result(
    res: PipelineResult,
    question: str,
    c_state: ConversationState,
) -> tuple[list[ChatMessage], ConversationState]:
    """Convert a PipelineResult into a ChatMessage and update ConversationState."""
    understood_as = _extract_understood_as(res)
    new_state = c_state
    if res.spec is not None:
        new_state = c_state.with_new_query(
            res.spec,
            question=question,
            card_id=res.card.card_id if res.card else None,
        )

    # 1. OVERSIZED -> options message
    if res.status == PipelineStatus.OVERSIZED or (res.plan_decision and res.plan_decision.plan.value == "refuse"):
        err_msg = res.error_message or "Query exceeds safe single-request data limits."
        options: list[ChatOption] = []
        if res.plan_decision and res.plan_decision.options:
            for opt in res.plan_decision.options:
                options.append(ChatOption(label=opt.label, action_type="plan_option", query_text=opt.description or opt.label))

        msg = ChatMessage(
            role="assistant",
            kind="options",
            text=err_msg,
            understood_as=understood_as,
            options=options,
        )
        return [msg], new_state

    # 2. CLARIFICATION_NEEDED -> clarification message
    if res.status == PipelineStatus.CLARIFICATION_NEEDED:
        clarify_text, clarify_options, clarify_understood = _build_clarification_message_and_options(
            question=question,
            res=res,
        )
        msg = ChatMessage(
            role="assistant",
            kind="clarification",
            text=clarify_text,
            understood_as=clarify_understood,
            options=clarify_options,
        )
        return [msg], new_state

    # 3. ERROR -> error message
    if res.status == PipelineStatus.ERROR:
        ref_id = uuid.uuid4().hex[:8]
        err_text = res.error_message or f"An error occurred while processing the request (Ref: {ref_id})."
        msg = ChatMessage(
            role="assistant",
            kind="error",
            text=err_text,
            understood_as=understood_as,
        )
        return [msg], new_state

    # 4. SUCCESS -> result message
    summary_text = ""
    if res.analysis and res.analysis.summary:
        summary_text = res.analysis.summary
    elif res.card:
        summary_text = f"Retrieved {res.card.row_count:,} rows across {res.card.profile_count:,} profiles for {res.card.region_name}."
    else:
        summary_text = "Query completed successfully."

    options: list[ChatOption] = []
    if res.plan_decision and res.plan_decision.options:
        for opt in res.plan_decision.options:
            options.append(ChatOption(label=opt.label, action_type="plan_option", query_text=opt.description or opt.label))

    msg = ChatMessage(
        role="assistant",
        kind="result",
        text=summary_text,
        card_id=res.card.card_id if res.card else None,
        understood_as=understood_as,
        options=options,
    )
    return [msg], new_state
