"""Streamlit application for ArgoCard (FloatChat-R).

Deterministic oceanographic query interface with QC-explicit cards, interactive plots,
and reproducible script generation under the Deep Ocean dark theme.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st

from argocard.analyzer import AnalysisResult
from argocard.card import DiffSummary, QueryCard, generate_script, list_cards, load_card, rerun
from argocard.fetcher import FetchResult, FetchStatus
from argocard.parser import ClarificationNeeded, ParseOutcome, parse_detailed
from argocard.pipeline import PipelineResult, PipelineStatus, run, run_spec
from argocard.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)

# Page configuration
st.set_page_config(
    page_title="ArgoCard — Reproducible Ocean Data",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Deep Ocean Styling
st.markdown(
    """
    <style>
    .main {
        background-color: #0B1F2A;
        color: #E6F1F5;
    }
    .stMetric {
        background-color: #12303F;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #1E4558;
    }
    .card-box {
        background-color: #12303F;
        border: 1px solid #1E4558;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    }
    .badge-cached {
        background-color: #2EC4B6;
        color: #0B1F2A;
        font-weight: bold;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.85em;
    }
    .badge-live {
        background-color: #3B82F6;
        color: #FFFFFF;
        font-weight: bold;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.85em;
    }
    .banner-warning {
        background-color: #2D2714;
        border-left: 4px solid #FFB703;
        padding: 12px 16px;
        border-radius: 4px;
        margin-bottom: 16px;
        color: #FFD166;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# Sidebar controls and card history
st.sidebar.title("🌊 ArgoCard")
st.sidebar.caption("Validated, QC-explicit Argo Ocean Float Queries")

mode_selection = st.sidebar.selectbox(
    "Default Delivery Mode",
    options=["research", "standard", "expert"],
    index=0,
    help="Research (delayed-mode QC=1), Standard (near real-time QC 1-2), Expert (all flags).",
)

st.sidebar.divider()
st.sidebar.subheader("Recent Query Cards")
try:
    recent_cards = list_cards(limit=10)
except Exception:
    recent_cards = []

if recent_cards:
    for c in recent_cards:
        if st.sidebar.button(
            f"📦 {c.card_id[:8]} ({c.mode.value})",
            key=f"card_btn_{c.card_id}",
            help=f"Spec: {c.spec_hash[:8]} | Data: {c.data_hash[:8]}",
        ):
            st.session_state["loaded_card_id"] = c.card_id
else:
    st.sidebar.caption("No stored query cards yet.")

# Main title
st.title("ArgoCard: FloatChat-R")
st.markdown(
    "Query global ocean Argo float observations using natural language. "
    "Every query is parsed into a validated spec, fetched via `argopy`, and documented with a verifiable **QueryCard**."
)

# Example query prompts
examples = [
    "temperature and salinity profiles in Arabian Sea between 2022-01-01 and 2022-01-10",
    "top 200m temperature near Azores in January 2022",
    "salinity against temperature in North Atlantic in summer 2021",
    "temperature in Mediterranean during 2020 near real-time",
    "salinity profiles in Weddell Sea in March",
    "sst in Arabian Sea in January 2022",
]

col_ex1, col_ex2 = st.columns([1, 4])
with col_ex1:
    st.markdown("**Sample Queries:**")
with col_ex2:
    selected_example = st.selectbox(
        "Choose an example query",
        options=["(Select a query to test...)"] + examples,
        label_visibility="collapsed",
    )

default_query = ""
if selected_example and selected_example != "(Select a query to test...)":
    default_query = selected_example

# Question input form
with st.form("query_form"):
    question = st.text_input(
        "Enter oceanographic question:",
        value=default_query,
        placeholder="e.g. temperature profiles in Arabian Sea in January 2022",
    )
    col_submit, col_force = st.columns([1, 4])
    with col_submit:
        submitted = st.form_submit_button("Run Query", type="primary")
    with col_force:
        force_refresh = st.checkbox("Bypass local Parquet cache (force remote fetch)", value=False)

if submitted and question:
    with st.spinner("Parsing query and validating spec..."):
        pipeline_res = run(question=question, force_refresh=force_refresh)
        st.session_state["pipeline_res"] = pipeline_res
        st.session_state["loaded_card_id"] = None

# Display loaded card if selected from sidebar
if st.session_state.get("loaded_card_id"):
    card = load_card(st.session_state["loaded_card_id"])
    if card:
        st.session_state["current_card"] = card

# Render Pipeline Results
res: Optional[PipelineResult] = st.session_state.get("pipeline_res")

if res:
    if res.status == PipelineStatus.CLARIFICATION_NEEDED:
        clarification: ClarificationNeeded = res.clarification
        st.markdown(
            f"""
            <div class="banner-warning">
                <h4>⚠️ Clarification Required</h4>
                <p>{clarification.message}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if clarification.missing_fields:
            st.info(f"**Missing Parameters**: {', '.join(clarification.missing_fields)}")
        if clarification.ambiguous_fields:
            st.warning(f"**Ambiguous Parameters**: {', '.join(clarification.ambiguous_fields)}")
        if clarification.suggestions:
            st.markdown("**Suggestions:**")
            for sug in clarification.suggestions:
                st.markdown(f"- {sug}")

    elif res.status in (PipelineStatus.EMPTY, PipelineStatus.OVERSIZED, PipelineStatus.TIMEOUT, PipelineStatus.ERROR):
        icon = "⏳" if res.status == PipelineStatus.TIMEOUT else "ℹ️"
        st.error(f"{icon} **Execution {res.status.value.upper()}**: {res.error_message}")
        if res.spec:
            with st.expander("Inspected Spec Parameters"):
                st.json(res.spec.model_dump())

    elif res.status == PipelineStatus.SUCCESS:
        st.session_state["current_card"] = res.card

        # Summary Metrics Bar
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Rows", f"{res.card.row_count:,}")
        with c2:
            st.metric("Profiles", f"{res.card.profile_count:,}")
        with c3:
            badge_text = "CACHE HIT" if res.card.is_cached else "REMOTE FETCH"
            st.metric("Source", f"{res.card.source.upper()} ({badge_text})")
        with c4:
            st.metric("Mode", res.card.mode.value)
        with c5:
            depth_str = f"{res.card.effective_depth_range.min_depth:.0f}–{res.card.effective_depth_range.max_depth:.0f} dbar"
            st.metric("Depth", depth_str)

        # Tabbed visualizers
        tab_plots, tab_stats, tab_card, tab_script = st.tabs(
            ["📊 Visualizations", "📋 Summary & Statistics", "📦 Query Card", "🐍 Python Script"]
        )

        with tab_plots:
            col_left, col_right = st.columns([1, 1])
            if "map" in res.figures:
                with col_left:
                    st.plotly_chart(res.figures["map"], use_container_width=True)
            if "profile" in res.figures:
                with col_right:
                    st.plotly_chart(res.figures["profile"], use_container_width=True)
            if "ts" in res.figures:
                st.plotly_chart(res.figures["ts"], use_container_width=True)

        with tab_stats:
            if res.analysis:
                st.markdown(res.analysis.summary_markdown)
                if res.analysis.depth_bins:
                    st.subheader("Depth-Bin Statistics")
                    bin_data = []
                    for b in res.analysis.depth_bins:
                        row = {
                            "Depth Bin": b.bin_name,
                            "Observations": b.n_obs,
                        }
                        if b.temp_mean is not None:
                            row["TEMP Mean (°C)"] = f"{b.temp_mean:.2f}"
                        if b.psal_mean is not None:
                            row["PSAL Mean (PSU)"] = f"{b.psal_mean:.2f}"
                        bin_data.append(row)
                    st.dataframe(pd.DataFrame(bin_data), use_container_width=True)

        with tab_card:
            card: QueryCard = res.card
            st.markdown(f"**Card ID**: `{card.card_id}` | **Fetch Key**: `{card.fetch_key}`")
            st.markdown(f"**Data SHA-256**: `{card.data_hash}`")
            st.markdown(
                f"**Environment**: argopy `{card.argopy_version}`, xarray `{card.xarray_version}` | **Timestamp**: `{card.fetch_timestamp}`"
            )
            st.info(f"**QC Filter Applied**: {card.qc_filter_description}")

            # Re-run & Diff check
            st.subheader("Reproducibility Check")
            if st.button("🔄 Re-run Fetch & Compute Diff"):
                with st.spinner("Re-fetching remote data and comparing hashes..."):
                    diff: DiffSummary = rerun(card)
                    if diff.is_same and not diff.version_changed:
                        st.success(f"✅ {diff.summary}")
                    elif diff.is_same and diff.version_changed:
                        st.warning(f"⚠️ {diff.summary}")
                    else:
                        st.error(f"⚠️ {diff.summary}")
                        if diff.new_profiles:
                            st.write(f"New profiles: {diff.new_profiles}")
                        if diff.missing_profiles:
                            st.write(f"Missing profiles: {diff.missing_profiles}")

        with tab_script:
            st.caption("Standalone reproducible Python script to re-fetch this exact dataset:")
            st.code(res.script, language="python")
            st.download_button(
                label="📥 Download Python Script",
                data=res.script,
                file_name=f"argocard_{card.card_id}.py",
                mime="text/x-python",
            )

