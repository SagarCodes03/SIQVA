"""Persistent chat interface and rendering for SIQVA Query Page (C1).

Provides:
- Scrollable chat message rendering with st.chat_message
- Full auto-render of tabs/plots/card ONLY for the newest result
- Compact summaries with on-demand 'Show plots' toggle for earlier results
- Interactive buttons for clarification options, plan options, and quick templates
- Bottom-pinned st.chat_input and compatibility query dock
- SQLite and st.session_state synchronization
"""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional
import uuid

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

logger = logging.getLogger(__name__)


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
            render_pipeline_result_fn(res)
        else:
            st.info("Cached card data is unavailable on disk.")


def render_chat_page(
    render_pipeline_result_fn: Callable[[Any], None],
    render_top_bar_fn: Callable[[str, str, str], None],
) -> None:
    """Render the persistent scrollable chat conversation interface."""
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
    top_col, right_col = st.columns([12, 3])
    with top_col:
        render_top_bar_fn(
            "SIQVA // CHAT TERMINAL",
            "Ask questions about Argo ocean data via deterministic QC-explicit spec engine",
            "settings_placeholder_btn",
        )
    with right_col:
        c_clear, c_new = st.columns(2)
        with c_clear:
            if st.button("Clear chat", key="top_clear_chat_btn", use_container_width=True, help="Clear conversation history"):
                clear_chat_messages(session_id=session_id)
                st.session_state["chat_messages"] = []
                st.session_state["conversation_state"] = ConversationState()
                st.session_state["pipeline_res"] = None
                st.rerun()
        with c_new:
            if st.button("New chat", key="top_new_chat_btn", use_container_width=True, help="Start a new chat session"):
                new_sid = uuid.uuid4().hex[:12]
                st.session_state["session_id"] = new_sid
                st.query_params["session_id"] = new_sid
                st.session_state["chat_messages"] = []
                st.session_state["conversation_state"] = ConversationState()
                st.session_state["pipeline_res"] = None
                st.rerun()

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    chat_messages: list[ChatMessage] = st.session_state.get("chat_messages", [])

    # Find the newest assistant message that is a result or has a card_id
    result_ids = [m.id for m in chat_messages if m.role == "assistant" and (m.kind == "result" or m.card_id is not None)]
    newest_result_id = result_ids[-1] if result_ids else None

    # 3. Render Conversation Messages
    for msg in chat_messages:
        if msg.role == "user":
            with st.chat_message("user"):
                st.markdown(html.escape(msg.text))
        elif msg.role == "assistant":
            with st.chat_message("assistant"):
                # Always render deterministic Understood as line if present
                if msg.understood_as:
                    st.caption(html.escape(msg.understood_as))

                if msg.kind == "text":
                    st.markdown(html.escape(msg.text))

                elif msg.kind == "refusal":
                    st.warning(html.escape(msg.text))

                elif msg.kind == "knowledge":
                    # Scientific concept text with markdown formatting
                    st.markdown(msg.text)

                elif msg.kind == "error":
                    st.error(html.escape(msg.text))

                elif msg.kind == "clarification":
                    st.warning(html.escape(msg.text))
                    if msg.options:
                        st.markdown("**Suggestions — Click to proceed:**")
                        cols = st.columns(min(len(msg.options), 3))
                        for idx, opt in enumerate(msg.options):
                            with cols[idx % min(len(msg.options), 3)]:
                                if st.button(f"> {opt.label}", key=f"opt_btn_{msg.id}_{idx}", use_container_width=True):
                                    handle_user_turn(opt.query_text or opt.label)
                                    st.rerun()

                elif msg.kind == "options":
                    st.error(html.escape(msg.text))
                    if msg.options:
                        st.markdown("**Actionable Options to Fit Constraints — Click to Execute:**")
                        cols = st.columns(min(len(msg.options), 3))
                        for idx, opt in enumerate(msg.options):
                            with cols[idx % min(len(msg.options), 3)]:
                                if st.button(f"> {opt.label}", key=f"opt_btn_{msg.id}_{idx}", use_container_width=True):
                                    handle_user_turn(opt.query_text or opt.label)
                                    st.rerun()

                elif msg.kind == "result":
                    is_newest = (msg.id == newest_result_id)
                    if is_newest:
                        # Auto-render full plots and tabs for newest result
                        active_res = st.session_state.get("pipeline_res")
                        if active_res is not None:
                            render_pipeline_result_fn(active_res)
                        elif msg.card_id:
                            card = load_card(msg.card_id, session_id=session_id)
                            if card:
                                res = restore_card_result(card)
                                render_pipeline_result_fn(res)
                            else:
                                st.markdown(html.escape(msg.text))
                        else:
                            st.markdown(html.escape(msg.text))
                    else:
                        # Compact summary + Show plots button for older results
                        render_compact_summary(msg, render_pipeline_result_fn, session_id)

    # 4. If conversation is empty, display Quick Query Starter Templates
    if not chat_messages:
        st.markdown("<div style='height: 15vh;'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div style='text-align: center; color: #94A3B8; margin-bottom: 24px;'>
                <div style='font-size: 1.25rem; font-weight: 700; color: #E2E8F0; margin-bottom: 6px;'>Explore Argo Ocean Float Data</div>
                <div style='font-size: 0.85rem;'>Ask natural-language questions about global ocean profiles, thermoclines, salinity, and sound speed.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='margin-bottom: 8px; color: #64748B; font-size: 0.70rem; letter-spacing: 0.06em; font-weight: 600;'>QUICK QUERY TEMPLATES</div>",
            unsafe_allow_html=True,
        )
        ex_file = Path(__file__).resolve().parent.parent / "data" / "examples.json"
        sample_queries = []
        if ex_file.exists():
            try:
                with open(ex_file, "r", encoding="utf-8") as f:
                    ex_data = json.load(f)
                sample_queries = [(e["question"], e["label"]) for e in ex_data.get("examples", [])]
            except Exception:
                pass
        if not sample_queries:
            sample_queries = [
                ("thermocline and barrier layer in Bay of Bengal April 2022", "[MLD // BAY OF BENGAL]"),
                ("cyclone heat potential tchp in Arabian Sea May 2022", "[TCHP // ARABIAN SEA]"),
                ("acoustic sound speed profile in Arabian Sea January 2022", "[SOFAR // ARABIAN SEA]"),
            ]

        num_cols = min(3, len(sample_queries))
        q_cols = st.columns(num_cols)
        for idx, (sq_text, sq_label) in enumerate(sample_queries[:num_cols]):
            with q_cols[idx]:
                if st.button(sq_label, key=f"quick_starter_{idx}", use_container_width=True):
                    handle_user_turn(sq_text)
                    st.rerun()

    # 5. Advanced Constraints & Compatibility Dock (allows pinning region/WMO/depth and maintains compatibility)
    with st.expander("Advanced Query Constraints & Pinning (Optional)", expanded=False):
        c_reg, c_wmo = st.columns(2)
        with c_reg:
            all_regions = ["(None)"] + sorted(KNOWN_REGIONS.keys())
            pin_region = st.selectbox("PIN REGION", options=all_regions, index=0)
        with c_wmo:
            pin_wmo = st.text_input("PIN WMO ID (OPTIONAL)", placeholder="e.g. 2902269")
        c_z1, c_z2, c_force = st.columns(3)
        with c_z1:
            pin_min_d = st.number_input("MIN dbar", value=0, min_value=0, max_value=2000, step=50)
        with c_z2:
            pin_max_d = st.number_input("MAX dbar", value=500, min_value=10, max_value=6000, step=50)
        with c_force:
            pin_force = st.checkbox("FORCE LIVE ERDDAP/ARGOVIS FETCH", value=False)

        user_input_area = st.text_area(
            "Query Input Box",
            placeholder="Ask an oceanographic question...",
            key=f"claude_query_box_{st.session_state['query_input_key']}",
            height=68,
        )
        if st.button("Send Query ↑", key="send_query_btn", type="primary"):
            if user_input_area.strip():
                final_q = user_input_area.strip()
                if pin_region != "(None)" and pin_region.lower() not in final_q.lower():
                    final_q += f" in {pin_region}"
                if pin_wmo.strip():
                    final_q += f" for float {pin_wmo.strip()}"
                depth_over = DepthRange(min_depth=float(pin_min_d), max_depth=float(pin_max_d)) if (pin_min_d > 0 or pin_max_d != 500) else None
                handle_user_turn(final_q, depth_override=depth_over, force_refresh=pin_force)
                st.rerun()

    # 6. Bottom Pinned Chat Input (ChatGPT / Claude style)
    chat_prompt = st.chat_input("Ask an oceanographic question (e.g. thermocline in Bay of Bengal April 2022)...")
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
