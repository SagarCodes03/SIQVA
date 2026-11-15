"""Streamlit application for SIQVA (Oceanic Retro-Terminal Interface).

Deterministic oceanographic query interface with QC-explicit cards, interactive plots,
reproducible script generation, and zero emojis under the Oceanic Retro-Terminal theme.
"""

from __future__ import annotations

import html
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_root_dir = str(Path(__file__).resolve().parent.parent)
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from siqva.analyzer import AnalysisResult, FULL_LABEL_TEMPLATE, SAMPLE_LABEL_TEMPLATE
from siqva.capabilities import get_capability_profile, resolve_effective_depth
from siqva.validator import DEFAULT_MAX_REQUEST_SIZE, is_size_guardrail_enabled
from siqva.card import (
    DiffSummary,
    QueryCard,
    format_history_label,
    generate_script,
    list_cards,
    load_card,
    rerun,
)
from siqva.fetcher import FetchResult, FetchStatus
from siqva.floatindex import SAMPLE_STEPS
from siqva.gazetteer import KNOWN_REGIONS
from siqva.interpretation import build_understood_from_spec, format_understood_as
from siqva.llm_parser import (
    SESSION_CALL_LIMIT_PER_HOUR,
    get_daily_calls,
    get_llm_config,
    get_session_calls_past_hour,
    is_hosted_backend_active,
)
from siqva.parser import ClarificationNeeded, ParseOutcome, parse_detailed
from siqva.pipeline import PipelineResult, PipelineStatus, run, run_spec
from siqva.planner import PlanKind, plan_request
from siqva.router import RouteTarget, route
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
    get_location_info,
)

# ---------------------------------------------------------------------------
# Streamlit Page Configuration (Zero Emojis)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SIQVA // OCEAN TERMINAL",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Enterprise Minimalist Dark Theme (Linear / Vercel Aesthetic)
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

    :root {
        --bg-canvas: #090C10;       /* Deep matte slate-black */
        --bg-sidebar: #06080B;      /* Slightly darker sidebar */
        --bg-surface: #0F141C;      /* Card surface */
        --bg-surface-hover: #151C26;/* Subtle hover elevation */
        --border-hairline: #1E2733; /* Crisp 1px structural border */
        --border-hover: #334155;    /* Muted steel hover border */
        --accent-primary: #E2E8F0;  /* Crisp high-contrast slate-white */
        --accent-ocean: #38BDF8;    /* Muted oceanic sky-blue for tags only */
        --text-primary: #F1F5F9;    /* Clean white-slate */
        --text-secondary: #94A3B8;  /* Muted neutral grey */
        --text-muted: #64748B;      /* Subtle caption grey */
        --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        --font-mono: 'JetBrains Mono', monospace;
    }

    /* 1. Typography: Inter for UI, JetBrains Mono only for code, metrics & tags */
    html, body, .stMarkdown, .stButton button, input, textarea, select, p, h1, h2, h3, h4, h5, h6 {
        font-family: var(--font-sans) !important;
        -webkit-font-smoothing: antialiased;
    }
    code, pre, [data-testid="stMetricValue"], .graph-card-tag {
        font-family: var(--font-mono) !important;
    }

    /* 2. Flat Matte Background (Zero neon glows or radial gradients) */
    .main, .stApp {
        background-color: var(--bg-canvas) !important;
        background-image: none !important;
        color: var(--text-primary) !important;
    }

    .block-container {
        padding-top: 1.4rem !important;
        padding-bottom: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 1440px !important;
    }

    [data-testid="stHeader"], .stDeployButton, [data-testid="stDeployButton"] {
        background-color: transparent !important;
        height: 2.0rem !important;
    }

    /* 3. Clean Sidebar with 1px Hairline Border */
    [data-testid="stSidebar"] {
        background-color: var(--bg-sidebar) !important;
        border-right: 1px solid var(--border-hairline) !important;
    }
    [data-testid="stSidebar"] hr {
        border-color: var(--border-hairline) !important;
        margin: 0.75rem 0 !important;
    }

    /* Top row: SIQVA brand box and << collapse button aligned side-by-side */
    [data-testid="stSidebarHeader"] {
        position: absolute !important;
        top: 0.65rem !important;
        right: 0.75rem !important;
        height: 36px !important;
        min-height: unset !important;
        padding: 0 !important;
        margin: 0 !important;
        background: transparent !important;
        z-index: 100 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    [data-testid="stSidebarCollapseButton"] {
        margin: 0 !important;
        padding: 0 !important;
    }
    [data-testid="stSidebarCollapseButton"] button {
        position: relative !important;
        height: 36px !important;
        width: 36px !important;
        min-height: 36px !important;
        border-radius: 6px !important;
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-hairline) !important;
        color: var(--text-secondary) !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: background-color 0.12s ease, border-color 0.12s ease !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebarCollapseButton"] button:hover {
        background-color: var(--bg-surface-hover) !important;
        border-color: var(--border-hover) !important;
        color: var(--text-primary) !important;
    }
    [data-testid="stSidebarCollapseButton"] button span,
    [data-testid="stExpandSidebarButton"] span,
    [data-testid="stExpandSidebarButton"] button span {
        display: none !important;
    }
    [data-testid="stSidebarCollapseButton"] button::after {
        content: "<<" !important;
        font-family: var(--font-mono) !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        color: var(--accent-ocean) !important;
        letter-spacing: -1px !important;
    }
    [data-testid="stExpandSidebarButton"]::after,
    [data-testid="stExpandSidebarButton"] button::after {
        content: ">>" !important;
        font-family: var(--font-mono) !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        color: var(--accent-ocean) !important;
        letter-spacing: -1px !important;
    }

    /* Content container starts at top without gap */
    [data-testid="stSidebarContent"],
    [data-testid="stSidebarUserContent"],
    [data-testid="stSidebar"] > div:first-child,
    [data-testid="stSidebar"] > div:nth-child(2) {
        padding-top: 0.65rem !important;
        padding-left: 0.75rem !important;
        padding-right: 0.75rem !important;
    }

    /* Brand Home Button ("SIQVA"): Top row next to << button, centered text */
    [data-testid="stSidebar"] .st-key-brand_home_btn {
        width: calc(100% - 44px) !important;
        margin-top: 0 !important;
        margin-bottom: 0 !important;
    }
    [data-testid="stSidebar"] .st-key-brand_home_btn > button,
    [data-testid="stSidebar"] .st-key-brand_home_btn button {
        background-color: #11161D !important;
        border: 1px solid #1E2733 !important;
        color: #F1F5F9 !important;
        width: 100% !important;
        min-height: 36px !important;
        height: 36px !important;
        border-radius: 6px !important;
        justify-content: center !important;
        text-align: center !important;
        letter-spacing: 0.08em !important;
        font-size: 0.88rem !important;
        font-weight: 700 !important;
        box-shadow: none !important;
        transition: background-color 0.12s ease, border-color 0.12s ease !important;
    }
    [data-testid="stSidebar"] .st-key-brand_home_btn button:hover {
        background-color: #161F2C !important;
        border-color: #334155 !important;
        color: #FFFFFF !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] .st-key-brand_home_btn button * {
        justify-content: center !important;
        text-align: center !important;
    }

    /* Sidebar Navigation Buttons (Query, Plot Graph, Compare Runs): Box stays same, words & dot strictly LEFT-ALIGNED */
    [data-testid="stSidebar"] .st-key-nav_query_btn,
    [data-testid="stSidebar"] .st-key-nav_plot_btn,
    [data-testid="stSidebar"] .st-key-nav_compare_btn {
        width: 100% !important;
    }
    [data-testid="stSidebar"] .st-key-nav_query_btn button,
    [data-testid="stSidebar"] .st-key-nav_plot_btn button,
    [data-testid="stSidebar"] .st-key-nav_compare_btn button,
    [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        text-align: left !important;
        padding-left: 14px !important;
        padding-right: 14px !important;
        min-height: 36px !important;
        height: 36px !important;
        margin-bottom: 4px !important;
        width: 100% !important;
        border-radius: 6px !important;
    }
    [data-testid="stSidebar"] .st-key-nav_query_btn button *,
    [data-testid="stSidebar"] .st-key-nav_plot_btn button *,
    [data-testid="stSidebar"] .st-key-nav_compare_btn button *,
    [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) * {
        justify-content: flex-start !important;
        text-align: left !important;
    }
    [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) div[data-testid="stMarkdownContainer"] {
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        text-align: left !important;
        width: 100% !important;
        margin: 0 !important;
    }
    [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) div[data-testid="stMarkdownContainer"] p {
        display: flex !important;
        justify-content: flex-start !important;
        align-items: center !important;
        text-align: left !important;
        width: 100% !important;
        margin: 0 !important;
        font-size: 0.84rem !important;
        font-weight: 500 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    /* History List Items: Left-aligned and compact single-line */
    [data-testid="stSidebar"] div[class*="st-key-hist_"] button {
        min-height: 32px !important;
        height: 32px !important;
        padding: 4px 10px !important;
        border-radius: 6px !important;
        margin-bottom: 3px !important;
        justify-content: flex-start !important;
        text-align: left !important;
        background-color: transparent !important;
        border: 1px solid transparent !important;
    }
    [data-testid="stSidebar"] div[class*="st-key-hist_"] button:hover {
        background-color: var(--bg-surface-hover) !important;
        border-color: var(--border-hairline) !important;
    }
    [data-testid="stSidebar"] div[class*="st-key-hist_"] button div[data-testid="stMarkdownContainer"] p {
        font-size: 0.78rem !important;
        font-weight: 400 !important;
        color: var(--text-secondary) !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        line-height: 1.2 !important;
        text-align: left !important;
    }
    [data-testid="stSidebar"] div[class*="st-key-hist_"] button:hover div[data-testid="stMarkdownContainer"] p {
        color: var(--text-primary) !important;
    }

    /* 4. Minimalist Header (Clean bottom hairline border, no thick left bar) */
    .terminal-header-wrap {
        display: flex;
        flex-direction: column;
        padding-bottom: 12px;
        margin-bottom: 16px;
        border-bottom: 1px solid var(--border-hairline);
    }
    .terminal-header-title {
        font-family: var(--font-sans) !important;
        font-size: 1.15rem;
        font-weight: 600;
        color: var(--text-primary);
        letter-spacing: -0.01em;
        margin: 0;
    }
    .terminal-header-sub {
        font-size: 0.82rem;
        color: var(--text-secondary);
        margin-top: 3px;
    }

    /* 5. Restrained Enterprise Buttons (Zero Neon Box-Shadows) */
    .stButton button {
        border-radius: 6px !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.01em !important;
        height: 36px !important;
        transition: background-color 0.12s ease, border-color 0.12s ease !important;
        box-shadow: none !important;
    }
    .stButton button:not([kind="primary"]) {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-hairline) !important;
        color: var(--text-secondary) !important;
    }
    .stButton button:not([kind="primary"]):hover {
        background-color: var(--bg-surface-hover) !important;
        border-color: var(--border-hover) !important;
        color: var(--text-primary) !important;
        box-shadow: none !important;
    }
    /* High-contrast neutral primary button (Linear / Vercel style) */
    .stButton button[kind="primary"] {
        background-color: var(--text-primary) !important;
        border: 1px solid var(--text-primary) !important;
        color: #090C10 !important;
        font-weight: 600 !important;
        box-shadow: none !important;
    }
    .stButton button[kind="primary"]:hover {
        background-color: #CBD5E1 !important;
        border-color: #CBD5E1 !important;
        color: #090C10 !important;
    }

    /* Download Buttons */
    .stDownloadButton button {
        border-radius: 6px !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        height: 36px !important;
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-hairline) !important;
        color: var(--text-secondary) !important;
        box-shadow: none !important;
    }
    .stDownloadButton button:hover {
        background-color: var(--bg-surface-hover) !important;
        border-color: var(--border-hover) !important;
        color: var(--text-primary) !important;
    }

    /* 6. Clean Prompt Container */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-hairline) !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:focus-within {
        border-color: var(--border-hover) !important;
        box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="stTextArea"] {
        margin-bottom: 6px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] textarea {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: var(--text-primary) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.92rem !important;
        line-height: 1.5 !important;
        resize: none !important;
        padding: 2px 0px !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] textarea::placeholder {
        color: var(--text-muted) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] textarea:focus {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }

    /* 7. Minimalist Graph Cards (Uniform 1px border, no left stripe) */
    .graph-card {
        background: var(--bg-surface);
        border: 1px solid var(--border-hairline);
        border-radius: 8px;
        padding: 16px;
        min-height: 108px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        transition: border-color 0.15s ease, background-color 0.15s ease;
        margin-bottom: 6px;
        box-shadow: none;
    }
    .graph-card:hover {
        border-color: var(--border-hover);
        background: var(--bg-surface-hover);
    }
    .graph-card-tag {
        color: var(--accent-ocean);
        font-family: var(--font-mono) !important;
        font-size: 0.70rem;
        font-weight: 500;
        letter-spacing: 0.04em;
    }
    .graph-card-title {
        color: var(--text-primary);
        font-family: var(--font-sans) !important;
        font-weight: 600;
        font-size: 0.92rem;
        margin-top: 6px;
    }
    .graph-card-desc {
        color: var(--text-secondary);
        font-family: var(--font-sans) !important;
        font-size: 0.78rem;
        margin-top: 4px;
        line-height: 1.4;
    }

    /* 8. Minimalist Metric Boxes */
    [data-testid="stMetric"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-hairline) !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
    }
    [data-testid="stMetricLabel"] {
        color: var(--text-muted) !important;
        font-family: var(--font-sans) !important;
        font-size: 0.70rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.05em !important;
    }
    [data-testid="stMetricValue"] {
        color: var(--text-primary) !important;
        font-family: var(--font-mono) !important;
        font-size: 1.15rem !important;
        font-weight: 600 !important;
    }

    /* 9. Clean Inputs, Tabs & Modals */
    button[data-baseweb="tab"] {
        font-family: var(--font-sans) !important;
        color: var(--text-secondary) !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.01em !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--text-primary) !important;
        border-bottom-color: var(--text-primary) !important;
        font-weight: 600 !important;
    }
    [data-testid="stSelectbox"] > div > div,
    [data-testid="stTextInput"] input,
    [data-testid="stDateInput"] input {
        background-color: var(--bg-canvas) !important;
        border: 1px solid var(--border-hairline) !important;
        color: var(--text-primary) !important;
        border-radius: 6px !important;
        font-size: 0.84rem !important;
        box-shadow: none !important;
    }
    [data-testid="stSelectbox"] > div > div:focus-within,
    [data-testid="stTextInput"] input:focus,
    [data-testid="stDateInput"] input:focus {
        border-color: var(--border-hover) !important;
        box-shadow: none !important;
    }
    div[data-testid="stDialog"] > div:first-child, div[role="dialog"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-hover) !important;
        border-radius: 10px !important;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6) !important;
        color: var(--text-primary) !important;
    }
    .banner-clarification {
        background-color: #0E1724;
        border: 1px solid #1E2E44;
        border-radius: 8px;
        padding: 14px 18px;
        color: #E2E8F0;
        margin-bottom: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Graph Definitions (Zero Emojis — Retro Terminal Tags)
# ---------------------------------------------------------------------------
GRAPH_TYPES = [
    {
        "key": "temp_profile",
        "tag": "[TEMP // Z]",
        "title": "Temperature vs Depth",
        "desc": "Vertical temperature profile",
        "intent": Intent.PROFILE,
        "variables": [Variable.TEMP, Variable.PRES],
        "nl_hint": "e.g. temperature profiles in Bay of Bengal in January 2022",
    },
    {
        "key": "sal_profile",
        "tag": "[PSAL // Z]",
        "title": "Salinity vs Depth",
        "desc": "Vertical salinity profile",
        "intent": Intent.PROFILE,
        "variables": [Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. salinity profiles in Arabian Sea in March 2022",
    },
    {
        "key": "ts_diagram",
        "tag": "[TEMP // PSAL]",
        "title": "Temperature vs Salinity",
        "desc": "T-S diagram colored by pressure",
        "intent": Intent.TS,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. temperature vs salinity in North Atlantic summer 2021",
    },
    {
        "key": "position_map",
        "tag": "[GEO // TRACK]",
        "title": "Float Position Map",
        "desc": "Geographic float tracks",
        "intent": Intent.MAP,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. float positions in Mediterranean Sea in 2022",
    },
    {
        "key": "thermocline",
        "tag": "[TEOS-10 // MLD]",
        "title": "Thermocline & Barrier Layer",
        "desc": "MLD, ILD, BLT, Z20 via TEOS-10",
        "intent": Intent.THERMOCLINE,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. thermocline and barrier layer in Bay of Bengal April 2022",
    },
    {
        "key": "tchp",
        "tag": "[CYCLONE // TCHP]",
        "title": "Cyclone Heat Potential",
        "desc": "Z26 isotherm & heat content",
        "intent": Intent.TCHP,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. cyclone heat potential TCHP in Arabian Sea May 2022",
    },
    {
        "key": "acoustic",
        "tag": "[SONAR // SOFAR]",
        "title": "Acoustic Sound Speed",
        "desc": "SLD & SOFAR channel via TEOS-10",
        "intent": Intent.ACOUSTIC,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. acoustic sound speed profile Arabian Sea January 2022",
    },
    {
        "key": "hovmoller",
        "tag": "[TIME // HOV]",
        "title": "Hovmöller Diagram",
        "desc": "Depth vs time 2D contour evolution",
        "intent": Intent.HOVMOLLER,
        "variables": [Variable.TEMP, Variable.PRES],
        "nl_hint": "e.g. hovmoller depth vs time temperature in Arabian Sea 2022",
    },
    {
        "key": "buoyancy",
        "tag": "[TEOS-10 // N2]",
        "title": "Buoyancy & Stability",
        "desc": "Brunt-Väisälä N² & pycnocline core",
        "intent": Intent.BUOYANCY,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. buoyancy frequency N2 and stability in Bay of Bengal April 2022",
    },
    {
        "key": "ts_isopycnal",
        "tag": "[TEOS-10 // TS-SIGMA]",
        "title": "T-S with Isopycnals",
        "desc": "Conservative T-S with σ₀ contours",
        "intent": Intent.TS_ISOPYCNAL,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. temperature vs salinity with isopycnals in North Atlantic 2021",
    },
    {
        "key": "climatology",
        "tag": "[STAT // ENVELOPE]",
        "title": "Climatology Envelope",
        "desc": "Regional mean & ±1σ spread",
        "intent": Intent.CLIMATOLOGY,
        "variables": [Variable.TEMP, Variable.PRES],
        "nl_hint": "e.g. regional temperature climatology envelope in Arabian Sea May 2022",
    },
    {
        "key": "omz",
        "tag": "[BGC // OMZ]",
        "title": "Oxygen Minimum Zone",
        "desc": "Dissolved oxygen & hypoxic ceiling",
        "intent": Intent.OMZ,
        "variables": [Variable.DOXY, Variable.PRES],
        "nl_hint": "e.g. oxygen minimum zone dissolved oxygen in Arabian Sea 2022",
    },
    {
        "key": "drift",
        "tag": "[DYN // DRIFT]",
        "title": "Float Drift Velocity",
        "desc": "Lagrangian speed & eddy detection",
        "intent": Intent.DRIFT,
        "variables": [Variable.TEMP, Variable.PSAL, Variable.PRES],
        "nl_hint": "e.g. float drift velocity in Arabian Sea 2022",
    },
]

_ALL_REGION_NAMES = sorted(KNOWN_REGIONS.keys())

# ---------------------------------------------------------------------------
# Session State Initialization & Navigation State Handlers
# ---------------------------------------------------------------------------
if "active_page" not in st.session_state:
    st.session_state["active_page"] = "query"
if "delivery_mode" not in st.session_state:
    st.session_state["delivery_mode"] = "research"
if "query_input_key" not in st.session_state:
    st.session_state["query_input_key"] = 0
if "pipeline_res" not in st.session_state:
    st.session_state["pipeline_res"] = None
if "active_plot_res" not in st.session_state:
    st.session_state["active_plot_res"] = None
if "active_plot_title" not in st.session_state:
    st.session_state["active_plot_title"] = None
if "session_id" not in st.session_state:
    import uuid

    qp_sid = st.query_params.get("session_id")
    if qp_sid:
        st.session_state["session_id"] = qp_sid
    else:
        st.session_state["session_id"] = uuid.uuid4().hex[:12]
        st.query_params["session_id"] = st.session_state["session_id"]
else:
    if st.query_params.get("session_id") != st.session_state["session_id"]:
        st.query_params["session_id"] = st.session_state["session_id"]

if "chat_messages" not in st.session_state:
    from siqva.chat import load_chat_messages, MAX_STORED_MESSAGES

    st.session_state["chat_messages"] = load_chat_messages(
        session_id=st.session_state["session_id"],
        limit=MAX_STORED_MESSAGES,
    )
if "loaded_card_id" not in st.session_state:
    st.session_state["loaded_card_id"] = None
if "chat_message" not in st.session_state:
    st.session_state["chat_message"] = None
if "conversation_state" not in st.session_state:
    from siqva.followup import ConversationState

    st.session_state["conversation_state"] = ConversationState()
if "ollama_warmed" not in st.session_state:
    from siqva.llm_parser import warmup_ollama_async

    warmup_ollama_async()
    st.session_state["ollama_warmed"] = True


def _reset_to_new_query() -> None:
    """Reset to a fresh Query page and clear active pipeline results."""
    st.session_state["active_page"] = "query"
    st.session_state["pipeline_res"] = None
    st.session_state["chat_message"] = None
    st.session_state["loaded_card_id"] = None
    st.session_state["query_input_key"] += 1


def _switch_or_reset_plot_page() -> None:
    """Switch to Plot Graph page or reset existing plot results if already active."""
    st.session_state["active_page"] = "plots"
    st.session_state["active_plot_res"] = None
    st.session_state["active_plot_title"] = None


# ---------------------------------------------------------------------------
# Helper: HTML Escaping & Card/Banner Builders
# ---------------------------------------------------------------------------
def build_clarification_banner_html(message: str) -> str:
    """Build sanitized HTML banner for clarification messages (zero emojis)."""
    safe_msg = html.escape(str(message))
    return (
        f'<div class="banner-clarification">\n'
        f'    <div style="font-weight:600; font-size:0.86rem; letter-spacing:0.04em; color:#38BDF8;">Clarification Required</div>\n'
        f'    <div style="margin-top:6px; font-size:0.84rem; color:#F1F5F9; line-height:1.45;">{safe_msg}</div>\n'
        f'</div>'
    )


def build_graph_card_html(tag: str, title: str, desc: str) -> str:
    """Build sanitized HTML for retro terminal graph selector cards."""
    safe_tag = html.escape(str(tag))
    safe_title = html.escape(str(title))
    safe_desc = html.escape(str(desc))
    return (
        f'<div class="graph-card">\n'
        f'    <div class="graph-card-header">\n'
        f'        <div class="graph-card-tag">{safe_tag}</div>\n'
        f'    </div>\n'
        f'    <div class="graph-card-title">{safe_title}</div>\n'
        f'    <div class="graph-card-desc">{safe_desc}</div>\n'
        f'</div>'
    )


def _style_fig(fig: go.Figure, is_map: bool = False) -> go.Figure:
    """Apply minimalist enterprise layout styling to Plotly charts."""
    if not isinstance(fig, go.Figure):
        return fig

    if is_map:
        fig.update_layout(
            height=490,
            paper_bgcolor="#0F141C",
            plot_bgcolor="#0F141C",
            showlegend=False,
            font=dict(
                family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                color="#F1F5F9",
            ),
            margin=dict(l=10, r=10, t=40, b=10),
            title=dict(
                font=dict(
                    family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                    color="#F1F5F9",
                    size=13,
                ),
            ),
        )
        fig.update_geos(
            bgcolor="#0F141C",
            oceancolor="#151C26",
            landcolor="#1E2733",
            coastlinecolor="#38BDF8",
            countrycolor="#1E2733",
            showocean=True,
            showland=True,
            showcountries=True,
            showcoastlines=True,
        )
    else:
        fig.update_layout(
            height=490,
            paper_bgcolor="#0F141C",
            plot_bgcolor="#0F141C",
            font=dict(
                family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                color="#94A3B8",
            ),
            margin=dict(l=55, r=30, t=65, b=50),
            title=dict(
                font=dict(
                    family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                    color="#F1F5F9",
                    size=13,
                ),
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(
                    family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                    color="#94A3B8",
                    size=10,
                ),
                bgcolor="rgba(15, 20, 28, 0.85)",
                bordercolor="#1E2733",
                borderwidth=1,
            ),
        )
        fig.update_xaxes(
            gridcolor="#1E2733",
            zerolinecolor="#1E2733",
            tickfont=dict(
                family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                color="#94A3B8",
            ),
            title_font=dict(
                family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                color="#F1F5F9",
            ),
        )
        fig.update_yaxes(
            gridcolor="#1E2733",
            zerolinecolor="#1E2733",
            tickfont=dict(
                family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                color="#94A3B8",
            ),
            title_font=dict(
                family="'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
                color="#F1F5F9",
            ),
        )
    return fig


@st.dialog("Terminal Preferences & Diagnostics")
def open_terminal_settings_modal() -> None:
    st.markdown("**Execution & Cache Controls**")
    st.session_state["force_refresh_global"] = st.toggle(
        "Force refresh (bypass local cache)",
        value=st.session_state.get("force_refresh_global", False),
    )
    guardrail_off = not is_size_guardrail_enabled()
    new_guardrail_off = st.toggle(
        "Bypass size guardrails (allow unlimited basin area & length)",
        value=guardrail_off,
    )
    st.session_state["disable_size_guardrail"] = new_guardrail_off
    if new_guardrail_off:
        os.environ["SIQVA_DISABLE_SIZE_GUARDRAIL"] = "1"
    else:
        os.environ.pop("SIQVA_DISABLE_SIZE_GUARDRAIL", None)
    st.markdown("**Gazetteer Regions Loaded**")
    st.code(", ".join(_ALL_REGION_NAMES), language="text")

    st.markdown("**Session & History Management**")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Clear Active Workspace", use_container_width=True):
            _reset_to_new_query()
            st.rerun()
    with c2:
        if st.button("Purge Streamlit Cache", use_container_width=True):
            st.cache_data.clear()
            st.success("Memory cache purged.")


def _ui_max_request_size() -> Optional[float]:
    """Return None to allow unlimited size in UI only when guardrails are explicitly bypassed, or 15,000 when enabled."""
    if not is_size_guardrail_enabled():
        return None
    return DEFAULT_MAX_REQUEST_SIZE


def _render_top_bar(title_text: str, subtitle_text: str, settings_key: str) -> None:
    """Render top-left aligned terminal header next to sidebar with far-right menu button."""
    top_left, top_right = st.columns([14, 1], vertical_alignment="top")
    with top_left:
        st.markdown(
            f'<div class="terminal-header-wrap">'
            f'  <div class="terminal-header-title">{html.escape(title_text)}</div>'
            f'  <div class="terminal-header-sub">{html.escape(subtitle_text)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with top_right:
        if st.button("⋮", key=settings_key, help="Terminal Preferences & Diagnostics"):
            open_terminal_settings_modal()

    if not is_size_guardrail_enabled():
        st.warning(
            "Size guardrails bypassed (SIQVA_DISABLE_SIZE_GUARDRAIL=1). "
            "Large regional queries may experience remote timeouts or high memory usage."
        )


def _render_pipeline_result(
    res: PipelineResult,
    key_prefix: str = "",
    show_understood: bool = True,
) -> None:
    """Render a PipelineResult with metrics, tabs, plots, stats, card, and script (Zero Emojis)."""
    prefix = key_prefix if key_prefix else (res.card.card_id if (res.card and res.card.card_id) else "live")

    if show_understood:
        if res.parse_outcome is not None:
            st.caption(
                format_understood_as(
                    res.parse_outcome.understood,
                    res.parse_outcome.provenance,
                )
            )
        elif res.spec is not None:
            understood, provenance = build_understood_from_spec(res.spec)
            st.caption(format_understood_as(understood, provenance))

    if res.status == PipelineStatus.CLARIFICATION_NEEDED:
        clarification: ClarificationNeeded = res.clarification
        st.markdown(
            build_clarification_banner_html(clarification.message),
            unsafe_allow_html=True,
        )
        if clarification.missing_fields:
            st.info(f"Missing fields: {', '.join(clarification.missing_fields)}")
        if clarification.ambiguous_fields:
            st.warning(f"Ambiguous fields: {', '.join(clarification.ambiguous_fields)}")
        if clarification.suggestions:
            st.markdown("**Suggested Resolutions — Click to Execute**")
            sug_cols = st.columns(min(len(clarification.suggestions), 3))
            for idx, sug in enumerate(clarification.suggestions):
                with sug_cols[idx % len(sug_cols)]:
                    if st.button(f"> {sug}", key=f"clarify_sug_{prefix}_{idx}", use_container_width=True):
                        with st.spinner("Executing suggested spec..."):
                            st.session_state["pipeline_res"] = run(question=sug, force_refresh=False, max_request_size=_ui_max_request_size())
                            st.rerun()
        return

    if res.status in (PipelineStatus.EMPTY, PipelineStatus.OVERSIZED, PipelineStatus.TIMEOUT, PipelineStatus.ERROR, PipelineStatus.INTERNAL_ERROR):
        tag = f"[{res.status.value.upper()}]"
        st.error(f"{tag} Execution halted: {res.error_message}")

        # Structured options for OVERSIZED queries (replaces mechanical auto-shrink)
        if res.status == PipelineStatus.OVERSIZED and res.spec is not None:
            opts = []
            if res.plan_decision and res.plan_decision.options:
                opts = res.plan_decision.options
            else:
                opts = plan_request(res.spec).options

            if opts:
                st.markdown("**Actionable Options to Fit Constraints — Click to Execute**")
                cols = st.columns(min(len(opts), 3))
                for idx, opt in enumerate(opts):
                    with cols[idx % len(cols)]:
                        if st.button(f"> {opt.label}", key=f"plan_opt_{prefix}_{idx}", use_container_width=True, help=opt.description):
                            with st.spinner(f"Executing: {opt.label}..."):
                                new_res = run_spec(opt.spec, force_refresh=False, max_request_size=_ui_max_request_size())
                                if st.session_state.get("active_page") == "query":
                                    st.session_state["pipeline_res"] = new_res
                                    from siqva.chat import ChatMessage, save_chat_message
                                    sid = st.session_state.get("session_id", "default")
                                    u_msg = ChatMessage(role="user", kind="text", text=opt.label)
                                    a_msg = ChatMessage(
                                        role="assistant",
                                        kind="result",
                                        text=new_res.analysis.summary if (new_res.analysis and new_res.analysis.summary) else f"Executed {opt.label}.",
                                        card_id=new_res.card.card_id if new_res.card else None,
                                        understood_as=f"Understood as: {opt.label}",
                                    )
                                    save_chat_message(u_msg, session_id=sid)
                                    save_chat_message(a_msg, session_id=sid)
                                    if "chat_messages" in st.session_state:
                                        st.session_state["chat_messages"].extend([u_msg, a_msg])
                                else:
                                    st.session_state["active_plot_res"] = new_res
                                st.rerun()

        if res.spec:
            with st.expander("Inspected Spec Parameters", key=f"exp_spec_inspect_{prefix}"):
                st.json(res.spec.model_dump())
        return

    if res.status != PipelineStatus.SUCCESS:
        return

    if res.warning:
        st.warning(f"Notice: {res.warning}")

    if res.card and res.card.chunks and len(res.card.chunks) > 1:
        st.info(f"Result assembled from {len(res.card.chunks)} monthly chunks.")

    # Spec Inspection and Override Drawer
    if res.spec is not None:
        with st.expander("Spec Parameters & Overrides", expanded=False, key=f"exp_spec_params_{prefix}"):
            with st.form(key=f"override_spec_form_{prefix}"):
                oc1, oc2, oc3, oc4 = st.columns(4)
                with oc1:
                    intent_opts = [i.value for i in Intent]
                    intent_idx = intent_opts.index(res.spec.intent.value) if res.spec.intent.value in intent_opts else 0
                    new_intent = st.selectbox(
                        "Intent",
                        options=intent_opts,
                        index=intent_idx,
                        key=f"sel_intent_{prefix}",
                    )
                with oc2:
                    mode_opts = [m.value for m in DataMode]
                    mode_idx = mode_opts.index(res.spec.mode.value) if res.spec.mode.value in mode_opts else 0
                    new_mode = st.selectbox(
                        "Data Mode",
                        options=mode_opts,
                        index=mode_idx,
                        key=f"sel_mode_{prefix}",
                    )
                with oc3:
                    cur_min_z = float(res.spec.depth_range.min_depth) if res.spec.depth_range else 0.0
                    new_min_z = st.number_input("Min Depth (dbar)", value=cur_min_z, min_value=0.0, max_value=2000.0, step=10.0, key=f"num_min_z_{prefix}")
                with oc4:
                    cur_max_z = float(res.spec.depth_range.max_depth) if res.spec.depth_range else 1000.0
                    new_max_z = st.number_input("Max Depth (dbar)", value=cur_max_z, min_value=10.0, max_value=6000.0, step=50.0, key=f"num_max_z_{prefix}")

                od1, od2 = st.columns(2)
                with od1:
                    cur_start = res.spec.date_range.start
                    new_start_dt = st.date_input("Start Date", value=cur_start, min_value=date(1999, 1, 1), max_value=date.today(), key=f"date_start_{prefix}")
                with od2:
                    cur_end = res.spec.date_range.end
                    new_end_dt = st.date_input("End Date", value=cur_end, min_value=date(1999, 1, 1), max_value=date.today(), key=f"date_end_{prefix}")

                force_ref = st.checkbox("Bypass Cache (Force Live Fetch)", value=False, key=f"chk_force_ref_{prefix}")
                if st.form_submit_button("Re-execute with Updated Spec", type="primary"):
                    if new_start_dt > new_end_dt:
                        new_start_dt, new_end_dt = new_end_dt, new_start_dt
                    updated_spec = res.spec.model_copy(
                        update={
                            "intent": Intent(new_intent),
                            "mode": DataMode(new_mode),
                            "date_range": DateRange(start=new_start_dt, end=new_end_dt),
                            "depth_range": DepthRange(min_depth=new_min_z, max_depth=new_max_z),
                        }
                    )
                    with st.spinner("Re-computing pipeline with overridden spec..."):
                        new_res = run_spec(updated_spec, force_refresh=force_ref, max_request_size=_ui_max_request_size())
                        if st.session_state["active_page"] == "query":
                            st.session_state["pipeline_res"] = new_res
                        else:
                            st.session_state["active_plot_res"] = new_res
                        st.rerun()

    # Summary Metrics Bar
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Total Rows", f"{res.card.row_count:,}")
    with c2:
        if res.fetch_result and res.fetch_result.is_sample:
            n_avail = getattr(res.fetch_result, "n_available", None)
            if n_avail:
                st.metric("Float Profiles", f"Sample: {res.card.profile_count} of {n_avail:,}")
            else:
                st.metric("Float Profiles", f"Sample: {res.card.profile_count}")
        else:
            st.metric("Float Profiles", FULL_LABEL_TEMPLATE.format(n_profiles=f"{res.card.profile_count:,}"))
    with c3:
        cache_str = "CACHED" if res.card.is_cached else "LIVE"
        st.metric("Source", f"{res.card.source.upper()} [{cache_str}]")
    with c4:
        st.metric("Data Mode", res.card.mode.value.title())
    with c5:
        depth_str = f"{res.card.effective_depth_range.min_depth:.0f}–{res.card.effective_depth_range.max_depth:.0f} dbar"
        st.metric("Depth Span", depth_str)

    # Tabbed visualizers
    tab_plots, tab_stats, tab_card, tab_script, tab_export = st.tabs(
        ["Visualizations", "Summary & Statistics", "Query Card", "Python Script", "Export Artifacts"],
        key=f"tabs_{prefix}",
    )

    with tab_plots:
        has_map = "map" in res.figures
        analytical_keys = [
            k for k in [
                "profile", "thermocline", "tchp", "acoustic", "ts",
                "hovmoller", "buoyancy", "ts_isopycnal", "climatology", "omz", "drift"
            ] if k in res.figures
        ]
        other_keys = [k for k in res.figures if k not in analytical_keys and k != "map"]
        all_analytical = analytical_keys + other_keys

        if res.fetch_result and res.fetch_result.is_sample:
            # S7 SAMPLE display: (1) Overview map, then (2) sample plots with required label, then (3) actions
            if has_map:
                st.plotly_chart(_style_fig(res.figures["map"], is_map=True), use_container_width=True, theme=None, key=f"plot_sample_map_{prefix}")

            n_avail = getattr(res.fetch_result, "n_available", None) or res.card.profile_count
            st.info(SAMPLE_LABEL_TEMPLATE.format(n_selected=res.card.profile_count, n_available=f"{n_avail:,}"))

            for key in all_analytical:
                st.plotly_chart(_style_fig(res.figures[key], is_map=False), use_container_width=True, theme=None, key=f"plot_sample_{key}_{prefix}")

            # Interactive Action Buttons
            st.markdown("**Sample Actions & Alternatives**")
            cur_n = res.card.profile_count
            next_n = None
            for step in SAMPLE_STEPS:
                if step > cur_n:
                    next_n = step
                    break

            opts = []
            if res.plan_decision and res.plan_decision.options:
                opts = res.plan_decision.options
            elif res.spec:
                opts = plan_request(res.spec).options

            action_items: list[dict[str, Any]] = []
            if next_n is not None:
                action_items.append({
                    "label": f"Bigger sample ({next_n} profiles)",
                    "spec": res.spec,
                    "sample_n": next_n,
                    "help": f"Fetch a denser sample of {next_n} profiles.",
                })

            for opt in opts:
                if opt.option_type in ("smaller_region", "subregion"):
                    action_items.append({
                        "label": opt.label,
                        "spec": opt.spec,
                        "help": opt.description,
                    })
                elif opt.option_type == "narrow_period":
                    action_items.append({
                        "label": opt.label,
                        "spec": opt.spec,
                        "help": opt.description,
                    })
                elif opt.option_type == "float_map":
                    action_items.append({
                        "label": "Float map only",
                        "spec": opt.spec,
                        "help": opt.description,
                    })

            # Run full (only when allowed)
            is_run_full_allowed = False
            if res.spec.basin is None and res.spec.region is not None:
                dec = plan_request(res.spec, force_full=True)
                if dec.plan in (PlanKind.FULL, PlanKind.CHUNKED):
                    is_run_full_allowed = True

            if is_run_full_allowed:
                action_items.append({
                    "label": "Run full (all profiles)",
                    "spec": res.spec,
                    "force_full": True,
                    "help": "Download complete observation dataset across all matching profiles.",
                })

            if action_items:
                def _on_sample_action_click(act: dict[str, Any]) -> None:
                    f_kw: dict[str, Any] = {}
                    if act.get("sample_n") is not None:
                        f_kw["sample_n"] = act["sample_n"]
                    if act.get("force_full"):
                        f_kw["force_full"] = True
                    new_res = run_spec(
                        act["spec"],
                        force_refresh=False,
                        max_request_size=_ui_max_request_size(),
                        **f_kw,
                    )
                    if st.session_state.get("active_page") == "query":
                        st.session_state["pipeline_res"] = new_res
                        from siqva.chat import ChatMessage, save_chat_message
                        sid = st.session_state.get("session_id", "default")
                        u_msg = ChatMessage(role="user", kind="text", text=act["label"])
                        a_msg = ChatMessage(
                            role="assistant",
                            kind="result",
                            text=new_res.analysis.summary if (new_res.analysis and new_res.analysis.summary) else f"Executed {act['label']}.",
                            card_id=new_res.card.card_id if new_res.card else None,
                            understood_as=f"Understood as: {act['label']}",
                        )
                        save_chat_message(u_msg, session_id=sid)
                        save_chat_message(a_msg, session_id=sid)
                        if "chat_messages" in st.session_state:
                            st.session_state["chat_messages"].extend([u_msg, a_msg])
                    else:
                        st.session_state["active_plot_res"] = new_res

                act_cols = st.columns(min(len(action_items), 4))
                for a_idx, act in enumerate(action_items):
                    with act_cols[a_idx % len(act_cols)]:
                        st.button(
                            act["label"],
                            key=f"sample_act_{prefix}_{a_idx}",
                            use_container_width=True,
                            help=act.get("help"),
                            on_click=_on_sample_action_click,
                            args=(act,),
                        )

        elif has_map and all_analytical:
            primary_key = all_analytical[0]
            c_map, c_plot = st.columns(2)
            with c_map:
                map_chart_key = f"map_chart_{prefix}"
                map_event = st.plotly_chart(
                    _style_fig(res.figures["map"], is_map=True),
                    use_container_width=True,
                    theme=None,
                    on_select="rerun",
                    selection_mode="points",
                    key=map_chart_key,
                )

            selected_wmo = None
            if map_event and isinstance(map_event, dict) and "selection" in map_event:
                sel_pts = map_event["selection"].get("points", [])
                if sel_pts:
                    curve_idx = sel_pts[0].get("curve_number", 0)
                    if curve_idx < len(res.figures["map"].data):
                        tr_name = res.figures["map"].data[curve_idx].name or ""
                        if "WMO" in tr_name:
                            selected_wmo = tr_name.replace("WMO", "").strip().split()[0]

            with c_plot:
                if selected_wmo:
                    st.caption(f"[CROSS-FILTER ACTIVE: ISOLATED FLOAT WMO {selected_wmo}]")
                st.plotly_chart(_style_fig(res.figures[primary_key], is_map=False), use_container_width=True, theme=None, key=f"plot_primary_{primary_key}_{prefix}")

            for extra_key in all_analytical[1:]:
                st.plotly_chart(_style_fig(res.figures[extra_key], is_map=False), use_container_width=True, theme=None, key=f"plot_extra_{extra_key}_{prefix}")

        elif has_map and not all_analytical:
            st.plotly_chart(_style_fig(res.figures["map"], is_map=True), use_container_width=True, theme=None, key=f"plot_map_only_{prefix}")

        elif not has_map and all_analytical:
            if len(all_analytical) == 1:
                st.plotly_chart(_style_fig(res.figures[all_analytical[0]], is_map=False), use_container_width=True, theme=None, key=f"plot_single_{all_analytical[0]}_{prefix}")
            else:
                for i in range(0, len(all_analytical), 2):
                    cols = st.columns(2)
                    with cols[0]:
                        st.plotly_chart(_style_fig(res.figures[all_analytical[i]], is_map=False), use_container_width=True, theme=None, key=f"plot_grid_{all_analytical[i]}_{prefix}")
                    if i + 1 < len(all_analytical):
                        with cols[1]:
                            st.plotly_chart(_style_fig(res.figures[all_analytical[i + 1]], is_map=False), use_container_width=True, theme=None, key=f"plot_grid_{all_analytical[i + 1]}_{prefix}")
        else:
            st.info("[NO FIGURES GENERATED FOR THIS SPEC]")

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
                            "SST (deg C)": f"{s.sst_c:.2f}",
                            "SSS (PSU)": f"{s.sss_psu:.2f}",
                        }
                        if res.spec.intent == Intent.THERMOCLINE:
                            row["Density MLD (m)"] = f"{s.mld_dens_m:.1f}" if s.mld_dens_m is not None else "N/A"
                            row["Temp ILD (m)"] = f"{s.ild_temp_m:.1f}" if s.ild_temp_m is not None else "N/A"
                            row["Barrier Layer (m)"] = f"{s.barrier_layer_m:.1f}" if s.barrier_layer_m is not None else "N/A"
                            row["Z20 (m)"] = f"{s.z20_isotherm_m:.1f}" if s.z20_isotherm_m is not None else "N/A"
                        elif res.spec.intent == Intent.TCHP:
                            row["Z26 (m)"] = f"{s.z26_isotherm_m:.1f}" if s.z26_isotherm_m is not None else "N/A"
                            row["TCHP (kJ/cm2)"] = f"{s.tchp_kj_cm2:.1f}"
                        elif res.spec.intent == Intent.ACOUSTIC:
                            row["SLD (m)"] = f"{s.sld_m:.1f}" if s.sld_m is not None else "N/A"
                            row["SOFAR Axis (m)"] = f"{s.sofar_axis_m:.1f}" if s.sofar_axis_m is not None else "N/A"
                        phys_data.append(row)
                    st.dataframe(pd.DataFrame(phys_data), use_container_width=True, key=f"df_phys_{prefix}")
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
                        row["TEMP Mean (deg C)"] = f"{b.temp_mean:.2f}"
                    if b.psal_mean is not None:
                        row["PSAL Mean (PSU)"] = f"{b.psal_mean:.2f}"
                    bin_data.append(row)
                st.dataframe(pd.DataFrame(bin_data), use_container_width=True, key=f"df_bins_{prefix}")

    with tab_card:
        card: QueryCard = res.card
        st.markdown(f"**Card ID**: `{card.card_id}` | **Fetch Key**: `{card.fetch_key}`")
        st.markdown(f"**Data SHA-256**: `{card.data_hash}`")
        st.markdown(
            f"**Environment**: argopy `{card.argopy_version}`, xarray `{card.xarray_version}` | **Timestamp**: `{card.fetch_timestamp}`"
        )
        st.info(f"**QC Filter Applied**: {card.qc_filter_description}")

        st.subheader("Reproducibility Check")
        if st.button("Re-run Fetch & Diff", key=f"rerun_btn_{prefix}"):
            with st.spinner("Re-fetching remote data and comparing hashes..."):
                diff: DiffSummary = rerun(card)
                if diff.is_same and not diff.version_changed:
                    st.success(f"[OK] {diff.summary}")
                elif diff.is_same and diff.version_changed:
                    st.warning(f"[WARN] {diff.summary}")
                else:
                    st.error(f"[DIFF DETECTED] {diff.summary}")
                    if diff.new_profiles:
                        st.write(f"New profiles: {diff.new_profiles}")
                    if diff.missing_profiles:
                        st.write(f"Missing profiles: {diff.missing_profiles}")

    with tab_script:
        st.caption("Standalone reproducible Python script to re-fetch this exact dataset:")
        st.code(res.script, language="python")
        st.download_button(
            label="Download Python Script",
            data=res.script,
            file_name=f"siqva_{card.card_id}.py",
            mime="text/x-python",
            key=f"dl_script_{prefix}",
        )

    with tab_export:
        st.markdown("**Download Research Artifacts**")
        ex1, ex2, ex3 = st.columns(3)
        with ex1:
            card_json = json.dumps(res.card.model_dump(mode="json"), indent=2)
            st.download_button(
                label="Download Query Card (.json)",
                data=card_json,
                file_name=f"siqva_card_{res.card.card_id}.json",
                mime="application/json",
                use_container_width=True,
                key=f"dl_card_{prefix}",
            )
        with ex2:
            if res.analysis and res.analysis.physics_summaries:
                phys_df = pd.DataFrame([s.__dict__ for s in res.analysis.physics_summaries])
                st.download_button(
                    label="Download Physics Metrics (.csv)",
                    data=phys_df.to_csv(index=False),
                    file_name=f"siqva_physics_{res.card.card_id}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"dl_phys_{prefix}",
                )
            else:
                st.caption("No TEOS-10 physics summary to export")
        with ex3:
            if res.figures:
                first_fig_key = next(iter(res.figures))
                html_bytes = res.figures[first_fig_key].to_html(include_plotlyjs="cdn").encode("utf-8")
                st.download_button(
                    label="Download Interactive Plot (.html)",
                    data=html_bytes,
                    file_name=f"siqva_{first_fig_key}_{res.card.card_id}.html",
                    mime="text/html",
                    use_container_width=True,
                    key=f"dl_plot_{prefix}",
                )
            else:
                st.caption("No active figure to export")


# ---------------------------------------------------------------------------
# SIDEBAR: Brand Reset, Left-Aligned Navigation, & History
# ---------------------------------------------------------------------------
with st.sidebar:
    if st.button("SIQVA", use_container_width=True, key="brand_home_btn"):
        _reset_to_new_query()
        st.rerun()

    st.divider()

    is_query = st.session_state["active_page"] == "query"
    is_plots = st.session_state["active_page"] == "plots"
    is_compare = st.session_state["active_page"] == "compare"
    is_sources = st.session_state["active_page"] == "sources"
    is_mlops = st.session_state["active_page"] == "mlops"

    q_label = "●  New chat" if is_query else "○  New chat"
    p_label = "●  Plot Graph" if is_plots else "○  Plot Graph"
    c_label = "●  Compare Runs" if is_compare else "○  Compare Runs"
    s_label = "●  Sources" if is_sources else "○  Sources"
    m_label = "●  MLOps & Telemetry" if is_mlops else "○  MLOps & Telemetry"

    active_nav_key = "nav_query_btn" if is_query else ("nav_plot_btn" if is_plots else ("nav_compare_btn" if is_compare else ("nav_sources_btn" if is_sources else "nav_mlops_btn")))
    st.markdown(
        f"""
        <style>
        [data-testid="stSidebar"] .st-key-{active_nav_key} button {{
            background-color: #151C26 !important;
            border: 1px solid #334155 !important;
            color: #F1F5F9 !important;
            font-weight: 600 !important;
            box-shadow: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    if st.button(q_label, use_container_width=True, key="nav_query_btn"):
        if st.session_state["active_page"] == "query":
            _reset_to_new_query()
        else:
            st.session_state["active_page"] = "query"
        st.rerun()

    if st.button(p_label, use_container_width=True, key="nav_plot_btn"):
        if st.session_state["active_page"] == "plots":
            _switch_or_reset_plot_page()
        else:
            st.session_state["active_page"] = "plots"
        st.rerun()

    if st.button(c_label, use_container_width=True, key="nav_compare_btn"):
        st.session_state["active_page"] = "compare"
        st.rerun()

    if st.button(s_label, use_container_width=True, key="nav_sources_btn"):
        st.session_state["active_page"] = "sources"
        st.rerun()

    if st.button(m_label, use_container_width=True, key="nav_mlops_btn"):
        st.session_state["active_page"] = "mlops"
        st.rerun()

    st.divider()
    c_new_chat, c_clear_chat = st.columns(2)
    with c_new_chat:
        if st.button("+ New", key="sidebar_new_chat_btn", use_container_width=True, help="Start new chat"):
            import uuid
            new_sid = uuid.uuid4().hex[:12]
            st.session_state["session_id"] = new_sid
            st.query_params["session_id"] = new_sid
            st.session_state["chat_messages"] = []
            st.session_state["conversation_state"] = ConversationState()
            st.session_state["pipeline_res"] = None
            st.session_state["active_page"] = "query"
            st.rerun()
    with c_clear_chat:
        if st.button("Clear", key="sidebar_clear_chat_btn", use_container_width=True, help="Clear chat"):
            from siqva.chat import clear_chat_messages
            clear_chat_messages(session_id=st.session_state.get("session_id", "default"))
            st.session_state["chat_messages"] = []
            st.session_state["conversation_state"] = ConversationState()
            st.session_state["pipeline_res"] = None
            st.session_state["active_page"] = "query"
            st.rerun()

    st.markdown(
        "<div style='color: #64748B; font-size: 0.70rem; font-weight: 600; letter-spacing: 0.06em; margin: 12px 0 4px 2px;'>DELIVERY MODE</div>",
        unsafe_allow_html=True,
    )
    st.session_state["delivery_mode"] = st.selectbox(
        "Mode",
        options=["research", "standard", "expert"],
        index=["research", "standard", "expert"].index(st.session_state.get("delivery_mode", "research")),
        label_visibility="collapsed",
        key="sidebar_delivery_mode_selector",
    )

    st.markdown(
        "<div style='color: #64748B; font-size: 0.70rem; font-weight: 600; letter-spacing: 0.06em; margin: 12px 0 4px 2px;'>MLOPS GUARDRAIL</div>",
        unsafe_allow_html=True,
    )
    st.session_state["enable_mlops_guardrail"] = st.toggle(
        "MLflow Guardrail",
        value=st.session_state.get("enable_mlops_guardrail", True),
        key="sidebar_guardrail_toggle",
        help="Toggle MLflow guardrail classification, drift tracking, and active learning logging on/off.",
    )

    st.markdown(
        "<div style='color: #64748B; font-size: 0.70rem; font-weight: 600; letter-spacing: 0.06em; margin: 12px 0 6px 2px;'>QUICK TEMPLATES</div>",
        unsafe_allow_html=True,
    )
    try:
        from app.chat_ui import handle_user_turn
    except ImportError:
        from chat_ui import handle_user_turn
    s_templates = [
        ("thermocline and barrier layer in Bay of Bengal April 2022", "MLD: Bay of Bengal"),
        ("cyclone heat potential tchp in Arabian Sea May 2022", "TCHP: Arabian Sea"),
        ("acoustic sound speed profile in Arabian Sea January 2022", "SOFAR: Arabian Sea"),
    ]
    for idx, (t_text, t_label) in enumerate(s_templates):
        if st.button(f"> {t_label}", key=f"sidebar_template_{idx}", use_container_width=True):
            handle_user_turn(t_text)
            st.session_state["active_page"] = "query"
            st.rerun()

    st.divider()
    st.markdown(
        "<div style='color: #64748B; font-size: 0.70rem; font-weight: 600; letter-spacing: 0.06em; margin: 12px 0 6px 2px;'>HISTORY</div>",
        unsafe_allow_html=True,
    )
    try:
        recent_cards = list_cards(limit=10, session_id=st.session_state.get("session_id"))
    except Exception:
        recent_cards = []

    if recent_cards:
        for c in recent_cards:
            if st.button(
                format_history_label(c),
                key=f"hist_{c.card_id}",
                use_container_width=True,
            ):
                st.session_state["loaded_card_id"] = c.card_id
                st.session_state["active_page"] = "query"
                st.rerun()
    else:
        st.caption("• no recorded sessions")

    st.divider()
    with st.expander("Grounded Sources", expanded=st.session_state.get("show_sources_expander", False)):
        try:
            from siqva.knowledge import list_sources
            src_list = list_sources()
            for s_idx, src in enumerate(src_list):
                s_title = src.get("title", "Untitled")
                s_link = src.get("link") or src.get("url")
                s_ver = src.get("version") or "N/A"
                s_ret = src.get("retrieved_on") or "N/A"
                s_lic = src.get("license") or src.get("license_as_seen") or "N/A"
                link_md = f"[{s_title}]({s_link})" if s_link else s_title
                st.markdown(
                    f"**{link_md}**\n\n- Version: `{s_ver}`\n- Retrieved: `{s_ret}`\n- License: `{s_lic}`",
                    unsafe_allow_html=False,
                )
        except Exception:
            st.caption("Unable to load sources manifest.")

    if os.environ.get("SIQVA_DEBUG") in ("1", "true", "True"):
        st.divider()
        st.markdown(
            "<div style='color: #64748B; font-size: 0.70rem; font-weight: 600; letter-spacing: 0.06em; margin: 12px 0 6px 2px;'>DEBUG · LLM USAGE</div>",
            unsafe_allow_html=True,
        )
        h_calls = get_session_calls_past_hour()
        d_calls = get_daily_calls()
        cfg_debug = get_llm_config()
        st.caption(f"Calls this hour: {h_calls}/{SESSION_CALL_LIMIT_PER_HOUR} · Calls today: {d_calls}/{cfg_debug.daily_cap}")


# ---------------------------------------------------------------------------
# FLOATING MODAL DIALOG FOR PLOT GRAPHS (@st.dialog)
# ---------------------------------------------------------------------------
@st.dialog("Configure Plot", width="large")
def open_graph_parameter_modal(gt_def: dict) -> None:
    st.markdown(f"**{gt_def['tag']} — {gt_def['title']}**")
    st.caption(gt_def["desc"])

    tab_nl, tab_manual, tab_float = st.tabs([
        "Natural Language",
        "Manual Parameters",
        "Float Identifier",
    ])

    with tab_nl:
        st.caption(gt_def["nl_hint"])
        with st.form(f"modal_nl_{gt_def['key']}"):
            nl_query = st.text_input("Query", placeholder=gt_def["nl_hint"])
            nl_submit = st.form_submit_button("Generate Plot", type="primary")
        if nl_submit and nl_query:
            with st.spinner("Executing query spec..."):
                res = run(question=nl_query, force_refresh=False, max_request_size=_ui_max_request_size())
                st.session_state["active_plot_res"] = res
                st.session_state["active_plot_title"] = gt_def["title"]
                st.rerun()

    with tab_manual:
        with st.form(f"modal_manual_{gt_def['key']}"):
            region_name = st.selectbox(
                "Region",
                options=_ALL_REGION_NAMES,
                index=0,
                key=f"modal_manual_region_{gt_def['key']}",
            )
            c1, c2 = st.columns(2)
            with c1:
                start_dt = st.date_input(
                    "Start Date",
                    value=date(2022, 1, 1),
                    min_value=date(1999, 1, 1),
                    max_value=date.today(),
                    key=f"modal_manual_start_{gt_def['key']}",
                )
            with c2:
                # Default to 14 days for manual modal selection
                end_dt = st.date_input(
                    "End Date",
                    value=date(2022, 1, 14),
                    min_value=date(1999, 1, 1),
                    max_value=date.today(),
                    key=f"modal_manual_end_{gt_def['key']}",
                )
            c3, c4 = st.columns(2)
            with c3:
                cap_prof = get_capability_profile(gt_def["intent"])
                default_max_z = cap_prof.default_depth.max_depth if cap_prof.default_depth else 500.0
                max_z = st.number_input(
                    "Max Depth (dbar)",
                    value=float(default_max_z),
                    min_value=10.0,
                    max_value=2000.0,
                    step=50.0 if default_max_z >= 50.0 else 5.0,
                    key=f"modal_manual_depth_{gt_def['key']}",
                )
            with c4:
                manual_mode = st.selectbox(
                    "Mode",
                    options=["research", "standard", "expert"],
                    index=0,
                    key=f"modal_manual_mode_{gt_def['key']}",
                )
            manual_submit = st.form_submit_button("Generate Plot", type="primary")
        if manual_submit:
            if start_dt > end_dt:
                start_dt, end_dt = end_dt, start_dt
            bbox = KNOWN_REGIONS[region_name]
            spec = QuerySpec(
                region=bbox,
                date_range=DateRange(start=start_dt, end=end_dt),
                depth_range=DepthRange(min_depth=0.0, max_depth=float(max_z)),
                variables=gt_def["variables"],
                mode=DataMode(manual_mode),
                intent=gt_def["intent"],
            )
            with st.spinner("Fetching Argo data & rendering..."):
                res = run_spec(spec, force_refresh=False, max_request_size=_ui_max_request_size())
                st.session_state["active_plot_res"] = res
                st.session_state["active_plot_title"] = gt_def["title"]
                st.rerun()

    with tab_float:
        with st.form(f"modal_float_{gt_def['key']}"):
            float_wmo = st.text_input(
                "WMO Float ID",
                placeholder="e.g. 2901623",
                key=f"modal_float_wmo_{gt_def['key']}",
            )
            c1, c2 = st.columns(2)
            with c1:
                float_start = st.date_input(
                    "Start Date",
                    value=date(2022, 1, 1),
                    min_value=date(1999, 1, 1),
                    max_value=date.today(),
                    key=f"modal_float_start_{gt_def['key']}",
                )
            with c2:
                float_end = st.date_input(
                    "End Date",
                    value=date(2022, 12, 31),
                    min_value=date(1999, 1, 1),
                    max_value=date.today(),
                    key=f"modal_float_end_{gt_def['key']}",
                )
            float_mode = st.selectbox(
                "Mode",
                options=["research", "standard", "expert"],
                index=0,
                key=f"modal_float_mode_{gt_def['key']}",
            )
            float_submit = st.form_submit_button("Generate Plot", type="primary")
        if float_submit and float_wmo:
            nl = f"{gt_def['title'].lower()} for float {float_wmo.strip()} between {float_start.isoformat()} and {float_end.isoformat()}"
            with st.spinner("Fetching float profile..."):
                res = run(question=nl, force_refresh=False, max_request_size=_ui_max_request_size())
                if res.spec and res.spec.mode == DataMode.RESEARCH and float_mode != "research":
                    res = run_spec(
                        res.spec.model_copy(update={"mode": DataMode(float_mode)}),
                        force_refresh=False,
                        question=nl,
                        max_request_size=_ui_max_request_size(),
                    )
                st.session_state["active_plot_res"] = res
                st.session_state["active_plot_title"] = gt_def["title"]
                st.rerun()


# ---------------------------------------------------------------------------
# PAGE 1: PERSISTENT CHAT QUERY INTERFACE
# ---------------------------------------------------------------------------
if st.session_state["active_page"] == "query":
    try:
        from app.chat_ui import render_chat_page
    except ImportError:
        from chat_ui import render_chat_page

    render_chat_page(_render_pipeline_result, _render_top_bar)


# ---------------------------------------------------------------------------
# PAGE 2: PLOT GRAPHS (Top-Left Header -> 3-Col Grid -> Modal -> Output Below)
# ---------------------------------------------------------------------------
elif st.session_state["active_page"] == "plots":
    _render_top_bar(
        "SIQVA // PLOT GRAPHS",
        "Select a graph module below to launch the floating parameter terminal",
        "settings_plots_btn",
    )
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    cols_per_row = 3
    for row_start in range(0, len(GRAPH_TYPES), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, gt in enumerate(GRAPH_TYPES[row_start : row_start + cols_per_row]):
            with cols[col_idx]:
                st.markdown(
                    build_graph_card_html(gt["tag"], gt["title"], gt["desc"]),
                    unsafe_allow_html=True,
                )
                if st.button("Configure & Plot", key=f"gen_{gt['key']}", use_container_width=True):
                    open_graph_parameter_modal(gt)

    if st.session_state.get("active_plot_res"):
        st.divider()
        st.markdown(f"### {st.session_state.get('active_plot_title', 'Graph Result')}")
        _render_pipeline_result(st.session_state["active_plot_res"])


# ---------------------------------------------------------------------------
# PAGE 3: COMPARE RUNS (Side-by-Side Dual-Card A/B Comparator)
# ---------------------------------------------------------------------------
elif st.session_state["active_page"] == "compare":
    _render_top_bar(
        "SIQVA // RUN COMPARATOR",
        "Side-by-side A/B comparative analysis of historical query cards",
        "settings_compare_btn",
    )
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    try:
        all_cards = list_cards(limit=25)
    except Exception:
        all_cards = []

    if len(all_cards) < 2:
        st.info("Insufficient history for comparison: need at least 2 saved query runs. Execute queries from the Query Terminal to generate cards.")
    else:
        card_labels = [f"{format_history_label(c)} [{c.card_id[:6]}]" for c in all_cards]
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Baseline Run (A)**")
            idx_a = st.selectbox("Select Run A", options=range(len(all_cards)), format_func=lambda i: card_labels[i], index=0, key="compare_select_run_a")
        with col_b:
            st.markdown("**Comparison Run (B)**")
            idx_b = st.selectbox("Select Run B", options=range(len(all_cards)), format_func=lambda i: card_labels[i], index=min(1, len(all_cards) - 1), key="compare_select_run_b")

        card_a = all_cards[idx_a]
        card_b = all_cards[idx_b]

        st.divider()

        # Delta Metrics Table
        st.markdown("### Comparative Metrics Delta")
        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            d_rows = card_b.row_count - card_a.row_count
            st.metric("Rows", f"{card_b.row_count:,}", delta=f"{d_rows:,} vs A")
        with m2:
            d_prof = card_b.profile_count - card_a.profile_count
            st.metric("Profiles", f"{card_b.profile_count:,}", delta=f"{d_prof:,} vs A")
        with m3:
            st.metric("QC Mode", f"{card_a.mode.value.title()} / {card_b.mode.value.title()}")
        with m4:
            st.metric("Intent", f"{card_a.spec.intent.value.title()} / {card_b.spec.intent.value.title()}")
        with m5:
            st.metric("Depth B", f"{card_b.effective_depth_range.min_depth:.0f}–{card_b.effective_depth_range.max_depth:.0f} dbar")

        # Load results for both cards to render visualizations
        with st.spinner("Loading dual run visualizations..."):
            try:
                res_a = run_spec(card_a.spec, force_refresh=False, max_request_size=_ui_max_request_size())
            except Exception:
                res_a = None
            try:
                res_b = run_spec(card_b.spec, force_refresh=False, max_request_size=_ui_max_request_size())
            except Exception:
                res_b = None

        st.markdown("### Side-by-Side Visualizations")
        v_col_a, v_col_b = st.columns(2)
        with v_col_a:
            st.markdown(f"**Run A: {html.escape(card_a.question or card_a.card_id[:8])}**")
            if res_a and res_a.figures:
                fig_key_a = next((k for k in ["profile", "thermocline", "tchp", "acoustic", "ts", "map"] if k in res_a.figures), next(iter(res_a.figures)))
                st.plotly_chart(_style_fig(res_a.figures[fig_key_a]), use_container_width=True, theme=None, key=f"compare_chart_a_{card_a.card_id}")
            else:
                st.info("No figure available for Run A")

        with v_col_b:
            st.markdown(f"**Run B: {html.escape(card_b.question or card_b.card_id[:8])}**")
            if res_b and res_b.figures:
                fig_key_b = next((k for k in ["profile", "thermocline", "tchp", "acoustic", "ts", "map"] if k in res_b.figures), next(iter(res_b.figures)))
                st.plotly_chart(_style_fig(res_b.figures[fig_key_b]), use_container_width=True, theme=None, key=f"compare_chart_b_{card_b.card_id}")
            else:
                st.info("No figure available for Run B")


# ---------------------------------------------------------------------------
# PAGE 4: GROUNDED SOURCES (Literature, Standards, and System Manifest)
# ---------------------------------------------------------------------------
elif st.session_state["active_page"] == "sources":
    _render_top_bar(
        "SIQVA // GROUNDED SOURCES",
        "Authoritative peer-reviewed literature, specifications, and code sources",
        "settings_sources_btn",
    )
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    try:
        from siqva.knowledge import list_sources
        sources = list_sources()
        table_rows = []
        for s in sources:
            table_rows.append({
                "Title": s.get("title", "Untitled"),
                "Version": s.get("version") or "N/A",
                "Retrieved On": s.get("retrieved_on") or "N/A",
                "License": s.get("license") or s.get("license_as_seen") or "N/A",
                "Link": s.get("link") or s.get("url") or "N/A",
            })
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Failed to load sources: {e}")


# ---------------------------------------------------------------------------
# PAGE 5: MLOPS GOVERNANCE & TELEMETRY
# ---------------------------------------------------------------------------
elif st.session_state["active_page"] == "mlops":
    c_mhead, c_mtog = st.columns([3, 1])
    with c_mhead:
        _render_top_bar(
            "SIQVA // MLOPS GOVERNANCE & TELEMETRY",
            "Production Guardrail Lineage, Calibrated Confidence, and Live Drift Telemetry",
            "settings_mlops_btn",
        )
    with c_mtog:
        st.session_state["enable_mlops_guardrail"] = st.toggle(
            "Enable MLflow Guardrail",
            value=st.session_state.get("enable_mlops_guardrail", True),
            key="page_mlops_toggle_btn",
            help="Toggle MLflow guardrail and drift telemetry on/off globally",
        )

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    from siqva.mlops_guardrail import get_model_metadata, get_telemetry_summary, is_guardrail_enabled
    meta = get_model_metadata()
    telemetry = get_telemetry_summary()
    guardrail_on = is_guardrail_enabled()

    # 1. High-level metric cards
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        status_label = "● ACTIVE" if guardrail_on else "○ BYPASSED"
        st.metric("Guardrail Status", status_label, f"SHA-256: {meta.get('dataset_version', 'N/A')}")
    with m2:
        f1_val = meta.get("macro_f1", 0.0)
        st.metric("Test Macro F1", f"{f1_val:.3f}", "Quality Gate >= 0.90")
    with m3:
        lat_val = meta.get("latency_ms", 0.0)
        st.metric("Inference Latency", f"{lat_val:.2f} ms", "Quality Gate < 5.0 ms")
    with m4:
        total_q = telemetry.get("total_queries", 0)
        flagged_q = telemetry.get("flagged_count", 0)
        st.metric("Live Queries Logged", f"{total_q:,}", f"{flagged_q} flagged for review")

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # 2. Real-time drift & MLflow overview
    col_left, col_right = st.columns([1, 1])

    with col_left:
        avg_conf_pct = f"{telemetry.get('avg_confidence', 1.0) * 100:.1f}%"
        avg_oov_pct = f"{telemetry.get('avg_oov_ratio', 0.0) * 100:.1f}%"
        st.markdown(
            f"""
            <div style="background-color: var(--bg-surface); border: 1px solid var(--border-hairline); border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <div style="color: var(--text-secondary); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 8px;">
                    [ DRIFT & CONFIDENCE SIGNALS ]
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid var(--border-hairline); padding-bottom: 6px;">
                    <span style="color: var(--text-muted); font-size: 0.85rem;">Average Confidence:</span>
                    <span style="color: var(--text-primary); font-family: var(--font-mono); font-weight: 600;">{avg_conf_pct}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid var(--border-hairline); padding-bottom: 6px;">
                    <span style="color: var(--text-muted); font-size: 0.85rem;">Vocabulary OOV Drift Rate:</span>
                    <span style="color: var(--text-primary); font-family: var(--font-mono); font-weight: 600;">{avg_oov_pct}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px; border-bottom: 1px solid var(--border-hairline); padding-bottom: 6px;">
                    <span style="color: var(--text-muted); font-size: 0.85rem;">Drift Alert Threshold:</span>
                    <span style="color: #38BDF8; font-family: var(--font-mono); font-weight: 600;">OOV &gt; 65% or Conf &lt; 70%</span>
                </div>
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: var(--text-muted); font-size: 0.85rem;">Telemetry Database:</span>
                    <span style="color: var(--text-primary); font-family: var(--font-mono); font-size: 0.80rem;">data/telemetry.sqlite</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Class distribution
        class_dist = telemetry.get("class_distribution", {})
        if class_dist:
            dist_df = pd.DataFrame([{"Class": k, "Inference Count": v} for k, v in class_dist.items()])
            st.caption("Live Inference Class Distribution")
            st.dataframe(dist_df, use_container_width=True, hide_index=True)

    with col_right:
        st.markdown(
            """
            <div style="background-color: var(--bg-surface); border: 1px solid var(--border-hairline); border-radius: 8px; padding: 16px; margin-bottom: 16px;">
                <div style="color: var(--text-secondary); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; margin-bottom: 8px;">
                    [ MLOPS ARCHITECTURE & EXPERIMENT TRACKING ]
                </div>
                <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5; margin-bottom: 12px;">
                    Lightweight, cloud-free MLOps stack for enterprise scientific computing:
                    <ul style="margin: 6px 0 0 16px; padding: 0;">
                        <li><strong>Data Versioning:</strong> SHA-256 dataset hashing directly into MLflow (replaces multi-GB DVC).</li>
                        <li><strong>Guardrail Model:</strong> TF-IDF (Word + Char-WB) + Calibrated LinearSVC (150 KB joblib, &lt; 1 ms).</li>
                        <li><strong>Experiment Tracking:</strong> Local SQLite MLflow store at <code>sqlite:///mlflow.db</code>.</li>
                        <li><strong>CI/CD Gate:</strong> <code>tests/test_mlops_gate.py</code> enforcing Macro F1 &ge; 0.90.</li>
                    </ul>
                </div>
                <div style="color: var(--text-muted); font-size: 0.75rem; font-family: var(--font-mono); background: #06080B; border: 1px solid #1E2733; padding: 8px 12px; border-radius: 6px;">
                    # Launch MLflow Dashboard in terminal:<br>
                    mlflow ui --backend-store-uri sqlite:///mlflow.db
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 3. Active Learning Review Queue
    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
    st.markdown(
        "<div style='font-size: 0.95rem; font-weight: 600; color: var(--text-primary); margin-bottom: 6px;'>Active Learning Review Queue (Flagged Uncertain Queries)</div>",
        unsafe_allow_html=True,
    )
    st.caption("Queries flagged due to low confidence (< 70%) or high out-of-vocabulary drift (> 65%). Inspect these to expand dataset for retraining.")

    al_queue = telemetry.get("active_learning_queue", [])
    if al_queue:
        al_df = pd.DataFrame(al_queue)
        al_df.rename(columns={
            "timestamp": "Timestamp",
            "query_text": "Query",
            "predicted_class": "Predicted Class",
            "confidence": "Confidence",
            "oov_ratio": "OOV Ratio",
            "latency_ms": "Latency (ms)",
        }, inplace=True)
        st.dataframe(al_df, use_container_width=True, hide_index=True)
    else:
        st.info("No queries currently flagged for active learning. All recent queries operated within normal confidence boundaries.")

    # Retrain button
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
    c_btn1, c_btn2 = st.columns([1, 3])
    with c_btn1:
        if st.button("Retrain Guardrail Pipeline", key="mlops_retrain_btn", use_container_width=True):
            with st.spinner("Retraining guardrail with MLflow tracking..."):
                try:
                    from scripts.train_guardrail import train_and_register
                    res_train = train_and_register()
                    st.success(f"Retrained and Promoted! New F1={res_train['macro_f1']} | SHA={res_train['dataset_version']}")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Retraining failed: {ex}")
