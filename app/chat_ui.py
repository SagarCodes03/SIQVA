"""Persistent chat interface and rendering for SIQVA Query Page (C1 & U1/U2).

Provides:
- Scrollable chat message rendering with st.chat_message with custom oceanic/user avatars.
- Deep Ocean styling with centered 900px column layout and overflow prevention.
- Word-level streaming for answer text on newest messages with rerun replay suppression.
- Deterministic 'Understood as' line formatted with provenance code chips.
- 6-button empty state gallery with cache-status badges.
- Full auto-render of tabs/plots/card ONLY for the newest result.
- Compact summaries with on-demand 'Show plots' toggle for earlier results.
- Interactive buttons for clarification options, plan options, and quick templates.
- Bottom-pinned st.chat_input and compatibility query dock.
- SQLite and st.session_state synchronization.
"""

from __future__ import annotations

import html
import json
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional
import uuid

_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import streamlit as st

from siqva.card import is_history_shared, load_card, restore_card_result
from siqva.chat import (
    MAX_QUESTION_LENGTH,
    MAX_STORED_MESSAGES,
    ChatMessage,
    ChatOption,
    clear_chat_messages,
    dispatch,
    load_chat_messages,
    save_chat_message,
)
from siqva.followup import ConversationState
from siqva.gazetteer import KNOWN_REGIONS
from siqva.llm_parser import is_hosted_backend_active
from siqva.spec import DataMode, DepthRange
from siqva.streaming import is_streaming_enabled, stream_text

logger = logging.getLogger(__name__)

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
USER_AVATAR = str(ASSETS_DIR / "user_avatar.png")
ASSISTANT_AVATAR = str(ASSETS_DIR / "assistant_avatar.png")


def load_chat_css() -> None:
    """Inject Deep Ocean chat stylesheet into the Streamlit app view."""
    css_path = ASSETS_DIR / "chat.css"
    if css_path.exists():
        try:
            css_content = css_path.read_text(encoding="utf-8")
            st.markdown(f"<style>\n{css_content}\n</style>", unsafe_allow_html=True)
        except Exception as e:
            logger.warning(f"Failed to load chat.css: {e}")


def short_label(text: str, max_chars: int = 28) -> str:
    """Shorten button label to at most max_chars, cutting at a word boundary."""
    s = text.strip()
    if len(s) <= max_chars:
        return s
    truncated = s[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 0:
        candidate = truncated[:last_space].rstrip()
    else:
        candidate = s[:max_chars - 1]
    if len(candidate) + 1 <= max_chars:
        return candidate + "…"
    return candidate[:max_chars - 1] + "…"


def format_provenance_chips(understood_text: str) -> str:
    """Format provenance labels [rules], [llm], [default] into clean markdown code chips."""
    return (
        understood_text
        .replace("[rules]", "`rules`")
        .replace("[llm]", "`llm`")
        .replace("[LLM]", "`llm`")
        .replace("[default]", "`default`")
    )


def is_example_cached(question: str) -> bool:
    """Check if a seed example's query parquet exists in the local cache directory."""
    try:
        from siqva.fetcher import DEFAULT_CACHE_DIR
        from siqva.parser import parse_detailed

        outcome = parse_detailed(question, allow_llm=False)
        if outcome.spec is not None:
            fetch_key = outcome.spec.fetch_key()
            parquet_path = Path(DEFAULT_CACHE_DIR) / f"{fetch_key}.parquet"
            return parquet_path.exists()
    except Exception:
        pass
    return False


def init_chat_session() -> str:
    """Initialize session state and query params for persistent chat."""
    # 1. Sync session_id with st.query_params
    if "session_id" not in st.session_state:
        qp_sid = st.query_params.get("session_id")
        if qp_sid:
            st.session_state["session_id"] = qp_sid
        else:
            new_sid = uuid.uuid4().hex[:12]
            st.session_state["session_id"] = new_sid
            st.query_params["session_id"] = new_sid
    else:
        # Keep query_params synchronized
        curr_sid = st.session_state["session_id"]
        if st.query_params.get("session_id") != curr_sid:
            st.query_params["session_id"] = curr_sid

    session_id = st.session_state["session_id"]

    # 2. Initialize chat messages from SQLite if not yet loaded in session_state
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = load_chat_messages(
            session_id=session_id,
            limit=MAX_STORED_MESSAGES,
        )

    # 3. Initialize conversation state for follow-ups
    if "conversation_state" not in st.session_state:
        st.session_state["conversation_state"] = ConversationState()

    # 4. Initialize delivery mode
    if "delivery_mode" not in st.session_state:
        st.session_state["delivery_mode"] = "research"

    if "query_input_key" not in st.session_state:
        st.session_state["query_input_key"] = 0

    # 5. Initialize set of streamed message IDs to prevent replay on rerun
    if "streamed_msg_ids" not in st.session_state:
        st.session_state["streamed_msg_ids"] = set()

    return session_id


def handle_user_turn(
    question_text: str,
    fetcher_fn: Any = None,
    depth_override: Optional[DepthRange] = None,
    force_refresh: bool = False,
) -> list[ChatMessage]:
    """Execute a single conversational turn: append user msg, dispatch, append assistant msgs."""
    session_id = init_chat_session()
    q_clean = question_text.strip()
    if not q_clean:
        return []

    # Enforce input length cap (truncate / record clean query)
    user_text = q_clean[:MAX_QUESTION_LENGTH]
    user_msg = ChatMessage(role="user", kind="text", text=user_text)

    # Persist and record in session_state
    save_chat_message(user_msg, session_id=session_id)
    st.session_state["chat_messages"].append(user_msg)

    # Resolve delivery mode
    mode_str = st.session_state.get("delivery_mode", "research")
    try:
        mode = DataMode(mode_str)
    except Exception:
        mode = DataMode.RESEARCH

    c_state: ConversationState = st.session_state.get("conversation_state") or ConversationState()

    def _store_res(r: Any) -> None:
        st.session_state["pipeline_res"] = r

    assistant_msgs: list[ChatMessage] = []
    try:
        assistant_msgs, new_state = dispatch(
            question=user_text,
            conversation_state=c_state,
            mode=mode,
            force_refresh=force_refresh,
            session_id=session_id,
            fetcher_fn=fetcher_fn,
            on_result=_store_res,
        )
        st.session_state["conversation_state"] = new_state
    except Exception as e:
        ref_id = uuid.uuid4().hex[:8]
        logger.error(f"Error executing chat turn [Ref: {ref_id}]: {e}", exc_info=True)
        err_msg = ChatMessage(
            role="assistant",
            kind="error",
            text=f"An unexpected error occurred while processing your request (Ref ID: {ref_id}). Please try again or rephrase.",
        )
        assistant_msgs = [err_msg]

    # Persist assistant responses and update session state
    for a_msg in assistant_msgs:
        save_chat_message(a_msg, session_id=session_id)
        st.session_state["chat_messages"].append(a_msg)
        # Fallback sync pipeline_res if not already populated by on_result
        if a_msg.card_id and st.session_state.get("pipeline_res") is None:
            try:
                card = load_card(a_msg.card_id, session_id=session_id)
                if card:
                    st.session_state["pipeline_res"] = restore_card_result(card)
            except Exception:
                pass

    return assistant_msgs


def render_compact_summary(
    msg: ChatMessage,
    render_pipeline_result_fn: Callable[[Any], None],
    session_id: str,
) -> None:
    """Render a compact summary of an earlier result with an on-demand 'Show plots' toggle."""
    card = None
    if msg.card_id:
        try:
            card = load_card(msg.card_id, session_id=session_id)
        except Exception:
            pass

    # Summary header info
    card_info = ""
    if card is not None:
        card_info = (
            f" • **Region**: {card.region_name} • **Profiles**: {card.profile_count:,} • "
            f"**Rows**: {card.row_count:,} • **Mode**: {card.mode.value} • **Date**: {card.created_at[:10]}"
        )
    st.markdown(f"**Result**: {html.escape(msg.text)}{card_info}")

    # On-demand plot view toggle
    toggle_key = f"show_plots_{msg.id}"
    is_open = st.session_state.get(toggle_key, False)

    col_btn, _ = st.columns([2.5, 9.5])
    with col_btn:
        btn_label = "Hide plots" if is_open else "Show plots"
        if st.button(btn_label, key=f"btn_toggle_plots_{msg.id}", use_container_width=True):
            st.session_state[toggle_key] = not is_open
            st.rerun()

    if is_open:
        st.markdown("<div style='margin-top: 8px;'></div>", unsafe_allow_html=True)
        if card is not None:
            res = restore_card_result(card)
            render_pipeline_result_fn(
                res,
                key_prefix=f"{msg.id}_{card.card_id}",
                show_understood=False,
            )
        else:
            st.info("Cached card data is unavailable on disk.")


def render_chat_page(
    render_pipeline_result_fn: Callable[[Any], None],
    render_top_bar_fn: Callable[[str, str, str], None],
) -> None:
    """Render the persistent scrollable chat conversation interface."""
    load_chat_css()
    session_id = init_chat_session()

    # 1. Handle sidebar history card restoration if selected
    if st.session_state.get("loaded_card_id"):
        target_card_id = st.session_state["loaded_card_id"]
        st.session_state["loaded_card_id"] = None
        card = load_card(target_card_id, session_id=session_id)
        if card:
            # Check if this card already exists in the conversation
            already_in = any(m.card_id == target_card_id for m in st.session_state["chat_messages"])
            if not already_in:
                q_label = card.question or f"{card.spec.intent.value.title()} in {card.region_name}"
                u_msg = ChatMessage(role="user", kind="text", text=q_label)
                a_msg = ChatMessage(
                    role="assistant",
                    kind="result",
                    text=f"Loaded query card: {card.region_name} ({card.profile_count:,} profiles, {card.row_count:,} rows).",
                    card_id=card.card_id,
                    understood_as=f"Understood as: {card.region_name}",
                )
                save_chat_message(u_msg, session_id=session_id)
                save_chat_message(a_msg, session_id=session_id)
                st.session_state["chat_messages"].extend([u_msg, a_msg])
            st.session_state[f"show_plots_{target_card_id}"] = True
            st.session_state["pipeline_res"] = restore_card_result(card)
            st.rerun()

    # 2. Header Bar
    st.markdown('<div class="siqva-chat-header">', unsafe_allow_html=True)
    top_col, right_col = st.columns([10, 5])
    with top_col:
        render_top_bar_fn(
            "SIQVA",
            "Argo ocean float question answering & physical oceanography",
            "settings_placeholder_btn",
        )
    with right_col:
        c_clear, c_new = st.columns(2)
        with c_clear:
            if st.button("🗑️ Clear", key="top_clear_chat_btn", use_container_width=True, help="Clear conversation history"):
                clear_chat_messages(session_id=session_id)
                st.session_state["chat_messages"] = []
                st.session_state["conversation_state"] = ConversationState()
                st.session_state["pipeline_res"] = None
                st.rerun()
        with c_new:
            if st.button("➕ New", key="top_new_chat_btn", use_container_width=True, help="Start a new chat session"):
                new_sid = uuid.uuid4().hex[:12]
                st.session_state["session_id"] = new_sid
                st.query_params["session_id"] = new_sid
                st.session_state["chat_messages"] = []
                st.session_state["conversation_state"] = ConversationState()
                st.session_state["pipeline_res"] = None
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    chat_messages: list[ChatMessage] = st.session_state.get("chat_messages", [])

    # Find the newest assistant message that is a result or has a card_id
    result_ids = [m.id for m in chat_messages if m.role == "assistant" and (m.kind == "result" or m.card_id is not None)]
    newest_result_id = result_ids[-1] if result_ids else None

    # Find newest assistant message overall for streaming
    assistant_ids = [m.id for m in chat_messages if m.role == "assistant"]
    newest_assistant_id = assistant_ids[-1] if assistant_ids else None

    streamed_ids = st.session_state.setdefault("streamed_msg_ids", set())

    # 3. Render Conversation Messages
    for msg in chat_messages:
        if msg.role == "user":
            with st.chat_message("user", avatar=USER_AVATAR):
                st.markdown(html.escape(msg.text))
        elif msg.role == "assistant":
            with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
                # Always render deterministic Understood as line if present
                if msg.understood_as:
                    st.caption(format_provenance_chips(html.escape(msg.understood_as)))

                should_stream = (
                    msg.id == newest_assistant_id
                    and msg.id not in streamed_ids
                    and is_streaming_enabled()
                )

                if msg.kind == "text":
                    if should_stream:
                        st.write_stream(stream_text(msg.text))
                        streamed_ids.add(msg.id)
                    else:
                        st.markdown(html.escape(msg.text))

                elif msg.kind == "refusal":
                    st.warning(html.escape(msg.text))

                elif msg.kind == "knowledge":
                    if should_stream:
                        st.write_stream(stream_text(msg.text))
                        streamed_ids.add(msg.id)
                    else:
                        # Scientific concept text with markdown formatting
                        st.markdown(msg.text)

                    if msg.options:
                        cols = st.columns(min(len(msg.options), 3))
                        for idx, opt in enumerate(msg.options):
                            with cols[idx % min(len(msg.options), 3)]:
                                s_lbl = short_label(opt.label, max_chars=28)
                                if st.button(s_lbl, key=f"opt_btn_know_{msg.id}_{idx}", use_container_width=True, help=opt.label):
                                    if opt.action_type == "sources":
                                        st.session_state["show_sources_expander"] = True
                                        st.session_state["active_page"] = "sources"
                                        st.rerun()
                                    else:
                                        handle_user_turn(opt.query_text or opt.label)
                                        st.rerun()

                elif msg.kind == "error":
                    st.error(html.escape(msg.text))

                elif msg.kind == "clarification":
                    st.warning(html.escape(msg.text))
                    if msg.options:
                        pill_options = [opt.label for opt in msg.options]
                        pill_map = {opt.label: (opt.query_text or opt.label) for opt in msg.options}
                        pill_key = f"clarify_pills_{msg.id}"

                        if hasattr(st, "pills"):
                            def _on_clarify_pill_change(pk=pill_key, p_map=pill_map):
                                selected_val = st.session_state.get(pk)
                                if selected_val and selected_val in p_map:
                                    handle_user_turn(p_map[selected_val])

                            st.pills(
                                "Clarification choices",
                                options=pill_options,
                                key=pill_key,
                                on_change=_on_clarify_pill_change,
                                label_visibility="collapsed",
                            )
                        else:
                            cols = st.columns(min(len(msg.options), 3))
                            for idx, opt in enumerate(msg.options):
                                with cols[idx % min(len(msg.options), 3)]:
                                    s_lbl = short_label(opt.label, max_chars=28)
                                    if st.button(s_lbl, key=f"opt_btn_{msg.id}_{idx}", use_container_width=True, help=opt.label):
                                        handle_user_turn(opt.query_text or opt.label)
                                        st.rerun()

                elif msg.kind == "options":
                    st.error(html.escape(msg.text))
                    if msg.options:
                        st.markdown("**Actionable Options to Fit Constraints — Click to Execute:**")
                        cols = st.columns(min(len(msg.options), 3))
                        for idx, opt in enumerate(msg.options):
                            with cols[idx % min(len(msg.options), 3)]:
                                s_lbl = short_label(opt.label, max_chars=28)
                                if st.button(s_lbl, key=f"opt_btn_plan_{msg.id}_{idx}", use_container_width=True, help=opt.label):
                                    handle_user_turn(opt.query_text or opt.label)
                                    st.rerun()

                elif msg.kind == "result":
                    streamed_ids.add(msg.id)
                    is_newest = (msg.id == newest_result_id)
                    if is_newest:
                        # Auto-render full plots and tabs for newest result
                        active_res = st.session_state.get("pipeline_res")
                        if active_res is not None:
                            cid = active_res.card.card_id if active_res.card else "res"
                            render_pipeline_result_fn(
                                active_res,
                                key_prefix=f"{msg.id}_{cid}",
                                show_understood=False,
                            )
                        elif msg.card_id:
                            card = load_card(msg.card_id, session_id=session_id)
                            if card:
                                res = restore_card_result(card)
                                render_pipeline_result_fn(
                                    res,
                                    key_prefix=f"{msg.id}_{card.card_id}",
                                    show_understood=False,
                                 )
                            else:
                                st.markdown(html.escape(msg.text))
                        else:
                            st.markdown(html.escape(msg.text))
                    else:
                        # Compact summary + Show plots button for older results
                        render_compact_summary(msg, render_pipeline_result_fn, session_id)

    # 4. If conversation is empty, display Quick Query Starter Templates (6 examples)
    if not chat_messages:
        st.markdown("<div style='height: 10vh;'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style='text-align: center; color: #94A3B8; margin-bottom: 24px;'>
                <div style='font-size: 1.35rem; font-weight: 700; color: #F1F5F9; margin-bottom: 6px;'>Explore Argo Ocean Float Data</div>
                <div style='font-size: 0.88rem; max-width: 520px; margin: 0 auto; line-height: 1.5;'>Ask natural-language questions about global ocean profiles, thermoclines, salinity, and sound speed.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='margin-bottom: 8px; color: #94A3B8; font-size: 0.72rem; letter-spacing: 0.05em; font-weight: 600; text-transform: uppercase;'>Example Queries</div>",
            unsafe_allow_html=True,
        )
        ex_file = Path(__file__).resolve().parent.parent / "data" / "examples.json"
        sample_queries: list[tuple[str, str, bool]] = []
        if ex_file.exists():
            try:
                with open(ex_file, "r", encoding="utf-8") as f:
                    ex_data = json.load(f)
                for e in ex_data.get("examples", []):
                    q_text = e["question"]
                    raw_label = e.get("label", "")
                    clean_label = raw_label.replace("[", "").replace("]", "").replace("//", "·").strip()
                    cached = is_example_cached(q_text)
                    sample_queries.append((q_text, clean_label, cached))
            except Exception:
                pass
        if not sample_queries:
            sample_queries = [
                ("thermocline and barrier layer in Bay of Bengal April 2022", "MLD · BAY OF BENGAL", True),
                ("cyclone heat potential tchp in Arabian Sea May 2022", "TCHP · ARABIAN SEA", False),
                ("acoustic sound speed profile in Arabian Sea January 2022", "SOFAR · ARABIAN SEA", False),
                ("temperature and salinity profiles in Bay of Bengal January 2022", "T-S · BAY OF BENGAL", False),
                ("temperature profiles in Arabian Sea January 2022", "TEMP · ARABIAN SEA 2022", False),
                ("salinity profiles in Bay of Bengal June 2022", "SAL · BAY OF BENGAL", False),
            ]

        # 6 example buttons in 2 rows of 3 columns
        row1 = sample_queries[:3]
        row2 = sample_queries[3:6]
        for r_idx, row_items in enumerate([row1, row2]):
            if not row_items:
                continue
            cols = st.columns(len(row_items))
            for c_idx, (sq_text, sq_label, is_cached) in enumerate(row_items):
                with cols[c_idx]:
                    tag = " • cached" if is_cached else ""
                    btn_text = short_label(f"{sq_label}{tag}", max_chars=28)
                    if st.button(btn_text, key=f"quick_starter_{r_idx}_{c_idx}", use_container_width=True, help=sq_text):
                        handle_user_turn(sq_text)
                        st.rerun()

    # 5. Advanced Constraints & Compatibility Dock (allows pinning region/WMO/depth and maintains compatibility)
    with st.expander("Advanced Query Constraints & Pinning (Optional)", expanded=False):
        c_reg, c_wmo = st.columns(2)
        with c_reg:
            all_regions = ["(None)"] + sorted(KNOWN_REGIONS.keys())
            st.selectbox("PIN REGION", options=all_regions, index=0, key="pin_region_select")
        with c_wmo:
            st.text_input("PIN WMO ID (OPTIONAL)", placeholder="e.g. 2902269", key="pin_wmo_input")
        c_z1, c_z2, c_force = st.columns(3)
        with c_z1:
            st.number_input("MIN dbar", value=0, min_value=0, max_value=2000, step=50, key="pin_min_dbar")
        with c_z2:
            st.number_input("MAX dbar", value=500, min_value=10, max_value=6000, step=50, key="pin_max_dbar")
        with c_force:
            st.checkbox("FORCE LIVE ERDDAP/ARGOVIS FETCH", value=False, key="pin_force_check")

        def _on_send_query_click() -> None:
            raw_q = st.session_state.get("claude_query_box", "").strip()
            if not raw_q:
                return
            p_reg = st.session_state.get("pin_region_select", "(None)")
            if p_reg != "(None)" and p_reg.lower() not in raw_q.lower():
                raw_q += f" in {p_reg}"
            p_wmo = st.session_state.get("pin_wmo_input", "").strip()
            if p_wmo:
                raw_q += f" for float {p_wmo}"
            p_min_z = float(st.session_state.get("pin_min_dbar", 0))
            p_max_z = float(st.session_state.get("pin_max_dbar", 500))
            p_force = bool(st.session_state.get("pin_force_check", False))
            d_over = DepthRange(min_depth=p_min_z, max_depth=p_max_z) if (p_min_z > 0 or p_max_z != 500) else None
            handle_user_turn(raw_q, depth_override=d_over, force_refresh=p_force)
            st.session_state["claude_query_box"] = ""

        st.text_area(
            "Query Input Box",
            placeholder="Ask an oceanographic question...",
            key="claude_query_box",
            height=68,
        )
        st.button("Send Query ↑", key="send_query_btn", type="primary", on_click=_on_send_query_click)

    # 6. Bottom Pinned Chat Input (ChatGPT / Claude style)
    is_streaming = bool(st.session_state.get("is_streaming", False))
    chat_prompt = st.chat_input(
        "Ask an oceanographic question (e.g. thermocline in Bay of Bengal April 2022)...",
        disabled=is_streaming,
    )
    if chat_prompt:
        handle_user_turn(chat_prompt)
        st.rerun()

    # 7. Privacy notice
    if is_hosted_backend_active():
        st.caption(
            html.escape(
                "Your question text is sent to a language model provider to interpret it. Data and results are never sent. Deterministic rules parse as much as possible first."
            )
        )
