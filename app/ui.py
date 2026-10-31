"""Streamlit application for SIQVA (formerly ArgoCard / FloatChat-R).

Deterministic oceanographic query interface with QC-explicit cards, interactive plots,
and reproducible script generation under the Deep Ocean dark theme.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import pandas as pd
import streamlit as st

_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from siqva.analyzer import AnalysisResult
from siqva.card import DiffSummary, QueryCard, generate_script, list_cards, load_card, rerun
from siqva.fetcher import FetchResult, FetchStatus
from siqva.gazetteer import KNOWN_REGIONS
from siqva.parser import ClarificationNeeded, ParseOutcome, parse_detailed
from siqva.pipeline import PipelineResult, PipelineStatus, run, run_spec
from siqva.spec import (
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
    page_title="SIQVA — Ask questions about Argo ocean data",
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
    /* Graph-type button cards */
    .graph-card {
        background: linear-gradient(135deg, #12303F 0%, #1a3d50 100%);
        border: 1px solid #1E4558;
        border-radius: 12px;
        padding: 20px 16px;
        text-align: center;
        transition: all 0.2s ease;
        cursor: pointer;
        min-height: 120px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .graph-card:hover {
        border-color: #2EC4B6;
        box-shadow: 0 4px 20px rgba(46, 196, 182, 0.15);
    }
    .graph-card-icon {
        font-size: 2em;
        margin-bottom: 8px;
    }
    .graph-card-title {
        color: #E6F1F5;
        font-weight: 600;
        font-size: 0.95em;
    }
    .graph-card-desc {
        color: #8FA9B8;
        font-size: 0.78em;
        margin-top: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Graph type definitions: each maps to an existing plot pipeline
# ---------------------------------------------------------------------------
GRAPH_TYPES = [
    {
        "key": "temp_profile",
        "icon": "🌡️",
        "title": "Temperature vs Depth",
        "desc": "Vertical temperature profile",
        "intent": Intent.PROFILE,
        "variables": [Variable.TEMP, Variable.PRES],
        "needs_region": True,
        "needs_date": True,
        "needs_float_id": True,
        "nl_hint": "e.g. temperature profiles in Bay of Bengal in January 2022",
    },
    {
        "key": "sal_profile",
        "icon": "🧂",
        "title": "Salinity vs Depth",
        "desc": "Vertical salinity profile",
        "intent": Intent.PROFILE,
        "variables": [Variable.PSAL, Variable.PRES],
        "needs_region": True,
        "needs_date": True,
        "needs_float_id": True,
        "nl_hint": "e.g. salinity profiles in Arabian Sea in March 2022",
    },
    {
        "key": "ts_diagram",
        "icon": "📈",
        "title": "Temperature vs Salinity",
        "desc": "T-S diagram colored by pressure",
        "intent": Intent.TS,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "needs_region": True,
        "needs_date": True,
        "needs_float_id": True,
        "nl_hint": "e.g. temperature vs salinity in North Atlantic summer 2021",
    },
    {
        "key": "position_map",
        "icon": "🗺️",
        "title": "Float Position Map",
        "desc": "Geographic float tracks",
        "intent": Intent.MAP,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "needs_region": True,
        "needs_date": True,
        "needs_float_id": True,
        "nl_hint": "e.g. float positions in Mediterranean Sea in 2022",
    },
    {
        "key": "thermocline",
        "icon": "🌊",
        "title": "Thermocline & Barrier Layer",
        "desc": "MLD, ILD, BLT, Z₂₀ via TEOS-10",
        "intent": Intent.THERMOCLINE,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "needs_region": True,
        "needs_date": True,
        "needs_float_id": True,
        "nl_hint": "e.g. thermocline and barrier layer in Bay of Bengal April 2022",
    },
    {
        "key": "tchp",
        "icon": "🌀",
        "title": "Cyclone Heat Potential (TCHP)",
        "desc": "Z₂₆ isotherm & heat content",
        "intent": Intent.TCHP,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "needs_region": True,
        "needs_date": True,
        "needs_float_id": True,
        "nl_hint": "e.g. cyclone heat potential TCHP in Arabian Sea May 2022",
    },
    {
        "key": "acoustic",
        "icon": "🔊",
        "title": "Acoustic Sound Speed",
        "desc": "SLD & SOFAR channel via TEOS-10",
        "intent": Intent.ACOUSTIC,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "needs_region": True,
        "needs_date": True,
        "needs_float_id": True,
        "nl_hint": "e.g. acoustic sound speed profile Arabian Sea January 2022",
    },
]

# Pre-sorted region names for dropdown
_ALL_REGION_NAMES = sorted(KNOWN_REGIONS.keys())


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🌊 SIQVA")
st.sidebar.caption("Ask questions about Argo ocean data")

mode_selection = st.sidebar.selectbox(
    "Default Delivery Mode",
    options=["research", "standard", "expert"],
    index=0,
    help="Research (delayed-mode QC=1), Standard (near real-time QC 1-2), Expert (all flags).",
)

# Page navigation
st.sidebar.divider()
page = st.sidebar.radio(
    "Navigation",
    options=["🔍 Query", "📊 Plot Graphs"],
    index=0,
    label_visibility="collapsed",
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


# =====================================================================
# Helper: render pipeline results (shared by both pages)
# =====================================================================
def _render_pipeline_result(res: PipelineResult) -> None:
    """Render a PipelineResult with metrics, tabs, plots, stats, card, and script."""
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
        return

    if res.status in (PipelineStatus.EMPTY, PipelineStatus.OVERSIZED, PipelineStatus.TIMEOUT, PipelineStatus.ERROR):
        icon = "⏳" if res.status == PipelineStatus.TIMEOUT else "ℹ️"
        st.error(f"{icon} **Execution {res.status.value.upper()}**: {res.error_message}")
        if res.spec:
            with st.expander("Inspected Spec Parameters"):
                st.json(res.spec.model_dump())
        return

    if res.status != PipelineStatus.SUCCESS:
        return

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
        if "thermocline" in res.figures:
            st.plotly_chart(res.figures["thermocline"], use_container_width=True)
        if "tchp" in res.figures:
            st.plotly_chart(res.figures["tchp"], use_container_width=True)
        if "acoustic" in res.figures:
            st.plotly_chart(res.figures["acoustic"], use_container_width=True)

    with tab_stats:
        if res.analysis:
            st.markdown(res.analysis.summary_markdown)

            is_phys = res.spec and res.spec.intent in (Intent.THERMOCLINE, Intent.TCHP, Intent.ACOUSTIC)
            if is_phys:
                st.subheader("TEOS-10 Profile Physics Metrics")
                if res.analysis.physics_summaries:
                    phys_data = []
                    for s in res.analysis.physics_summaries:
                        row = {
                            "WMO": s.wmo_id,
                            "Cycle": s.cycle,
                            "Date": s.date,
                            "SST (°C)": f"{s.sst_c:.2f}",
                            "SSS (PSU)": f"{s.sss_psu:.2f}",
                        }
                        if res.spec.intent == Intent.THERMOCLINE:
                            row["Density MLD (m)"] = f"{s.mld_dens_m:.1f}" if s.mld_dens_m is not None else "N/A"
                            row["Temp ILD (m)"] = f"{s.ild_temp_m:.1f}" if s.ild_temp_m is not None else "N/A"
                            row["Barrier Layer (m)"] = f"{s.barrier_layer_m:.1f}" if s.barrier_layer_m is not None else "N/A"
                            row["Z20 (m)"] = f"{s.z20_isotherm_m:.1f}" if s.z20_isotherm_m is not None else "N/A"
                        elif res.spec.intent == Intent.TCHP:
                            row["Z26 (m)"] = f"{s.z26_isotherm_m:.1f}" if s.z26_isotherm_m is not None else "N/A"
                            row["TCHP (kJ/cm²)"] = f"{s.tchp_kj_cm2:.1f}"
                        elif res.spec.intent == Intent.ACOUSTIC:
                            row["SLD (m)"] = f"{s.sld_m:.1f}" if s.sld_m is not None else "N/A"
                            row["SOFAR Axis (m)"] = f"{s.sofar_axis_m:.1f}" if s.sofar_axis_m is not None else "N/A"
                        phys_data.append(row)
                    st.dataframe(pd.DataFrame(phys_data), use_container_width=True)
                else:
                    reason = res.analysis.physics_skipped_reason or "All profiles were skipped or lacked sufficient upper-ocean observations."
                    st.info(f"Physics not computed: {reason}")

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
        if st.button("🔄 Re-run Fetch & Compute Diff", key="rerun_btn"):
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
            file_name=f"siqva_{card.card_id}.py",
            mime="text/x-python",
        )


# =====================================================================
# Helper: build a QuerySpec from manual / float-ID form inputs
# =====================================================================
def _build_spec_from_manual(
    *,
    region_name: str,
    start_date: date,
    end_date: date,
    intent: Intent,
    variables: list[Variable],
    mode_str: str,
) -> QuerySpec:
    """Construct a QuerySpec from manual UI selections."""
    bbox = KNOWN_REGIONS[region_name]
    return QuerySpec(
        region=bbox,
        date_range=DateRange(start=start_date, end=end_date),
        variables=variables,
        mode=DataMode(mode_str),
        intent=intent,
    )


# =====================================================================
# PAGE: 🔍 Query (original query interface)
# =====================================================================
if page == "🔍 Query":
    st.title("SIQVA – Smart Interface of Query and Visualization of Argo data")
    st.caption("Ask questions about Argo ocean data")
    st.markdown(
        "Query global ocean Argo float observations using natural language. "
        "Every query is parsed into a validated spec, fetched via `argopy`, and documented with a verifiable **QueryCard**."
    )

    # Example query prompts
    examples = [
        "thermocline and barrier layer in Bay of Bengal between 2022-04-01 and 2022-04-15",
        "cyclone heat potential tchp in Arabian Sea in May 2022",
        "acoustic sound speed profile in Arabian Sea between 2022-01-01 and 2022-01-10",
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
        _render_pipeline_result(res)


# =====================================================================
# PAGE: 📊 Plot Graphs
# =====================================================================
elif page == "📊 Plot Graphs":
    st.title("📊 Plot Graphs")
    st.markdown("Select a graph type below, then provide parameters via **natural language**, **manual selection**, or **Float ID**.")

    # --- Render graph-type buttons as a grid ---
    cols_per_row = 4
    for row_start in range(0, len(GRAPH_TYPES), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, gt in enumerate(GRAPH_TYPES[row_start : row_start + cols_per_row]):
            with cols[col_idx]:
                # Styled card button
                st.markdown(
                    f"""
                    <div class="graph-card">
                        <div class="graph-card-icon">{gt['icon']}</div>
                        <div class="graph-card-title">{gt['title']}</div>
                        <div class="graph-card-desc">{gt['desc']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(f"Generate", key=f"btn_{gt['key']}", use_container_width=True):
                    st.session_state["selected_graph"] = gt["key"]

    st.divider()

    # --- If a graph type is selected, show the parameter input dialog ---
    selected_key = st.session_state.get("selected_graph")
    if selected_key:
        # Find the graph definition
        gt_def = next((g for g in GRAPH_TYPES if g["key"] == selected_key), None)
        if gt_def:
            st.subheader(f"{gt_def['icon']}  {gt_def['title']}")

            tab_nl, tab_manual, tab_float = st.tabs([
                "💬 Natural Language",
                "🎛️ Manual Selection",
                "🔢 Float ID",
            ])

            # ── Tab 1: Natural Language ──
            with tab_nl:
                st.caption(gt_def["nl_hint"])
                with st.form(f"nl_form_{selected_key}"):
                    nl_query = st.text_input(
                        "Describe your query:",
                        placeholder=gt_def["nl_hint"],
                        key=f"nl_input_{selected_key}",
                    )
                    nl_submit = st.form_submit_button("🚀 Generate Graph", type="primary")

                if nl_submit and nl_query:
                    with st.spinner("Parsing natural language query and fetching data..."):
                        pipeline_res = run(question=nl_query, force_refresh=False)
                        st.session_state[f"plot_res_{selected_key}"] = pipeline_res

            # ── Tab 2: Manual Selection ──
            with tab_manual:
                with st.form(f"manual_form_{selected_key}"):
                    # Region selector with search
                    region_name = st.selectbox(
                        "🌍 Region",
                        options=_ALL_REGION_NAMES,
                        index=0,
                        key=f"manual_region_{selected_key}",
                    )

                    # Date range
                    col_d1, col_d2 = st.columns(2)
                    with col_d1:
                        start_dt = st.date_input(
                            "📅 Start Date",
                            value=date(2022, 1, 1),
                            key=f"manual_start_{selected_key}",
                        )
                    with col_d2:
                        end_dt = st.date_input(
                            "📅 End Date",
                            value=date(2022, 1, 31),
                            key=f"manual_end_{selected_key}",
                        )

                    # Mode
                    manual_mode = st.selectbox(
                        "Delivery Mode",
                        options=["research", "standard", "expert"],
                        index=0,
                        key=f"manual_mode_{selected_key}",
                    )

                    manual_submit = st.form_submit_button("🚀 Generate Graph", type="primary")

                if manual_submit:
                    try:
                        spec = _build_spec_from_manual(
                            region_name=region_name,
                            start_date=start_dt,
                            end_date=end_dt,
                            intent=gt_def["intent"],
                            variables=gt_def["variables"],
                            mode_str=manual_mode,
                        )
                        with st.spinner("Fetching data and generating graph..."):
                            pipeline_res = run_spec(spec, force_refresh=False)
                            st.session_state[f"plot_res_{selected_key}"] = pipeline_res
                    except Exception as exc:
                        st.error(f"❌ Could not build query: {exc}")

            # ── Tab 3: Float ID ──
            with tab_float:
                with st.form(f"float_form_{selected_key}"):
                    float_wmo = st.text_input(
                        "🔢 WMO Float ID",
                        placeholder="e.g. 2901623",
                        key=f"float_wmo_{selected_key}",
                    )

                    col_fd1, col_fd2 = st.columns(2)
                    with col_fd1:
                        float_start = st.date_input(
                            "📅 Start Date (optional)",
                            value=date(2022, 1, 1),
                            key=f"float_start_{selected_key}",
                        )
                    with col_fd2:
                        float_end = st.date_input(
                            "📅 End Date (optional)",
                            value=date(2022, 12, 31),
                            key=f"float_end_{selected_key}",
                        )

                    float_mode = st.selectbox(
                        "Delivery Mode",
                        options=["research", "standard", "expert"],
                        index=0,
                        key=f"float_mode_{selected_key}",
                    )

                    float_submit = st.form_submit_button("🚀 Generate Graph", type="primary")

                if float_submit and float_wmo:
                    # Build a natural language query using the float ID
                    # The pipeline parser supports float WMO numbers in free-text
                    nl = f"{gt_def['title'].lower()} for float {float_wmo.strip()}"
                    if float_start and float_end:
                        nl += f" between {float_start.isoformat()} and {float_end.isoformat()}"
                    with st.spinner("Fetching data for float and generating graph..."):
                        pipeline_res = run(question=nl, force_refresh=False)
                        st.session_state[f"plot_res_{selected_key}"] = pipeline_res

            # ── Show results ──
            plot_res: Optional[PipelineResult] = st.session_state.get(f"plot_res_{selected_key}")
            if plot_res:
                st.divider()
                _render_pipeline_result(plot_res)
