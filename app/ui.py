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

_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from siqva.analyzer import AnalysisResult
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
from siqva.gazetteer import KNOWN_REGIONS
from siqva.interpretation import format_understood_as
from siqva.parser import ClarificationNeeded, ParseOutcome, parse_detailed
from siqva.pipeline import PipelineResult, PipelineStatus, run, run_spec
from siqva.router import RouteTarget, route
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
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

    st.session_state["session_id"] = uuid.uuid4().hex[:12]
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


def _render_pipeline_result(res: PipelineResult) -> None:
    """Render a PipelineResult with metrics, tabs, plots, stats, card, and script (Zero Emojis)."""
    if res.parse_outcome is not None:
        st.caption(
            format_understood_as(
                res.parse_outcome.understood,
                res.parse_outcome.provenance,
            )
        )

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
                    if st.button(f"> {sug}", key=f"clarify_sug_{idx}", use_container_width=True):
                        with st.spinner("Executing suggested spec..."):
                            st.session_state["pipeline_res"] = run(question=sug, force_refresh=False, max_request_size=_ui_max_request_size())
                            st.rerun()
        return

    if res.status in (PipelineStatus.EMPTY, PipelineStatus.OVERSIZED, PipelineStatus.TIMEOUT, PipelineStatus.ERROR):
        tag = f"[{res.status.value.upper()}]"
        st.error(f"{tag} Execution halted: {res.error_message}")

        # Auto-clamp button for OVERSIZED queries
        if res.status == PipelineStatus.OVERSIZED and res.spec is not None:
            if st.button("Auto-shrink Query to Fit Cost Limit & Re-run", type="primary", key="auto_clamp_btn"):
                # If it's a Map or Drift plot, clamp depth to 0-20 dbar; otherwise clamp date window to fit cost cap
                if res.spec.intent in (Intent.MAP, getattr(Intent, "DRIFT", None)):
                    clamped_spec = res.spec.model_copy(
                        update={"depth_range": DepthRange(min_depth=0.0, max_depth=20.0)}
                    )
                else:
                    from datetime import timedelta

                    area = (res.spec.region.lon_max - res.spec.region.lon_min) * (res.spec.region.lat_max - res.spec.region.lat_min)
                    cur_span = (res.spec.depth_range.max_depth - res.spec.depth_range.min_depth) if res.spec.depth_range else 500.0
                    depth_factor = cur_span / 500.0
                    cost_per_day = area * depth_factor
                    max_fitting_days = max(1, int(15_000.0 / cost_per_day)) if cost_per_day > 0 else 14
                    clamped_days = min(max_fitting_days, 14)
                    new_end = res.spec.date_range.start + timedelta(days=clamped_days)
                    if new_end > res.spec.date_range.end:
                        new_end = res.spec.date_range.end
                    clamped_spec = res.spec.model_copy(
                        update={"date_range": DateRange(start=res.spec.date_range.start, end=new_end)}
                    )
                with st.spinner("Re-executing with clamped parameters..."):
                    new_res = run_spec(clamped_spec, force_refresh=False, max_request_size=_ui_max_request_size())
                    if st.session_state["active_page"] == "query":
                        st.session_state["pipeline_res"] = new_res
                    else:
                        st.session_state["active_plot_res"] = new_res
                    st.rerun()

        if res.spec:
            with st.expander("Inspected Spec Parameters"):
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
        with st.expander("Spec Parameters & Overrides", expanded=False):
            with st.form(key=f"override_spec_form_{res.card.card_id if res.card else 'live'}"):
                oc1, oc2, oc3, oc4 = st.columns(4)
                with oc1:
                    intent_opts = [i.value for i in Intent]
                    intent_idx = intent_opts.index(res.spec.intent.value) if res.spec.intent.value in intent_opts else 0
                    new_intent = st.selectbox(
                        "Intent",
                        options=intent_opts,
                        index=intent_idx,
                    )
                with oc2:
                    mode_opts = [m.value for m in DataMode]
                    mode_idx = mode_opts.index(res.spec.mode.value) if res.spec.mode.value in mode_opts else 0
                    new_mode = st.selectbox(
                        "Data Mode",
                        options=mode_opts,
                        index=mode_idx,
                    )
                with oc3:
                    cur_min_z = float(res.spec.depth_range.min_depth) if res.spec.depth_range else 0.0
                    new_min_z = st.number_input("Min Depth (dbar)", value=cur_min_z, min_value=0.0, max_value=2000.0, step=10.0)
                with oc4:
                    cur_max_z = float(res.spec.depth_range.max_depth) if res.spec.depth_range else 1000.0
                    new_max_z = st.number_input("Max Depth (dbar)", value=cur_max_z, min_value=10.0, max_value=6000.0, step=50.0)

                od1, od2 = st.columns(2)
                with od1:
                    cur_start = res.spec.date_range.start
                    new_start_dt = st.date_input("Start Date", value=cur_start, min_value=date(1999, 1, 1), max_value=date.today())
                with od2:
                    cur_end = res.spec.date_range.end
                    new_end_dt = st.date_input("End Date", value=cur_end, min_value=date(1999, 1, 1), max_value=date.today())

                force_ref = st.checkbox("Bypass Cache (Force Live Fetch)", value=False)
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
        st.metric("Float Profiles", f"{res.card.profile_count:,}")
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
        ["Visualizations", "Summary & Statistics", "Query Card", "Python Script", "Export Artifacts"]
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

        if has_map and all_analytical:
            primary_key = all_analytical[0]
            c_map, c_plot = st.columns(2)
            with c_map:
                map_chart_key = f"map_chart_{res.card.card_id if res.card else 'live'}"
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
                st.plotly_chart(_style_fig(res.figures[primary_key], is_map=False), use_container_width=True, theme=None)

            for extra_key in all_analytical[1:]:
                st.plotly_chart(_style_fig(res.figures[extra_key], is_map=False), use_container_width=True, theme=None)

        elif has_map and not all_analytical:
            st.plotly_chart(_style_fig(res.figures["map"], is_map=True), use_container_width=True, theme=None)

        elif not has_map and all_analytical:
            if len(all_analytical) == 1:
                st.plotly_chart(_style_fig(res.figures[all_analytical[0]], is_map=False), use_container_width=True, theme=None)
            else:
                for i in range(0, len(all_analytical), 2):
                    cols = st.columns(2)
                    with cols[0]:
                        st.plotly_chart(_style_fig(res.figures[all_analytical[i]], is_map=False), use_container_width=True, theme=None)
                    if i + 1 < len(all_analytical):
                        with cols[1]:
                            st.plotly_chart(_style_fig(res.figures[all_analytical[i + 1]], is_map=False), use_container_width=True, theme=None)
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
                        row["TEMP Mean (deg C)"] = f"{b.temp_mean:.2f}"
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

        st.subheader("Reproducibility Check")
        if st.button("Re-run Fetch & Diff", key="rerun_btn"):
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

    q_label = "●  Query" if is_query else "○  Query"
    p_label = "●  Plot Graph" if is_plots else "○  Plot Graph"
    c_label = "●  Compare Runs" if is_compare else "○  Compare Runs"

    active_nav_key = "nav_query_btn" if is_query else ("nav_plot_btn" if is_plots else "nav_compare_btn")
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
                default_max_z = 20.0 if gt_def["intent"] in (Intent.MAP, getattr(Intent, "DRIFT", None)) else 500.0
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
# PAGE 1: QUERY INTERFACE (Top-Left Header + Bottom-Anchored Query Dock)
# ---------------------------------------------------------------------------
if st.session_state["active_page"] == "query":
    if st.session_state.get("loaded_card_id"):
        from siqva.card import restore_card_result

        card = load_card(
            st.session_state["loaded_card_id"],
            session_id=st.session_state.get("session_id"),
        )
        if card:
            st.session_state["pipeline_res"] = restore_card_result(card)
        st.session_state["loaded_card_id"] = None

    # Top-Left Aligned Header Bar (flush near sidebar)
    _render_top_bar(
        "SIQVA // QUERY TERMINAL",
        "Ask questions about Argo ocean data via deterministic QC-explicit spec engine",
        "settings_placeholder_btn",
    )

    has_active_res = st.session_state.get("pipeline_res") is not None
    has_chat_message = st.session_state.get("chat_message") is not None

    # If results exist, render them in the upper workspace first, or keep input compact
    if has_active_res:
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        _render_pipeline_result(st.session_state["pipeline_res"])
        st.divider()
    elif has_chat_message:
        cm = st.session_state["chat_message"]
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        with st.chat_message("assistant"):
            if cm["type"] == "glossary":
                st.markdown(f"**{cm['canonical_name']}** (`{cm['term']}`)")
                st.markdown(cm["definition"])
                if cm.get("formula"):
                    st.markdown(f"*Formula*: {cm['formula']}")
                st.caption(f"Source: {cm['source']}")
            elif cm["type"] == "glossary_unverified":
                st.warning(f"**{cm.get('term', '')}**: {cm['message']}")
                if cm.get("source"):
                    st.caption(f"Preliminary literature citation: {cm['source']}")
            elif cm["type"] == "glossary_not_found":
                st.info(cm["message"])
            elif cm["type"] == "meta":
                st.markdown(cm["message"])
        st.divider()
    else:
        # Push the input box and trial templates near the bottom of the screen while keeping everything visible
        st.markdown("<div style='height: 34vh; min-height: 150px; max-height: 310px;'></div>", unsafe_allow_html=True)

    # Centered Bottom Query Dock + Trial Templates Below Input
    _, prompt_col, _ = st.columns([1.2, 6.6, 1.2])
    with prompt_col:
        with st.container(border=True):
            user_question = st.text_area(
                "Query Input",
                placeholder="Ask an oceanographic question (e.g. thermocline and barrier layer in Bay of Bengal April 2022)...",
                label_visibility="collapsed",
                height=68,
                key=f"claude_query_box_{st.session_state['query_input_key']}",
            )
            # Bottom toolbar inside prompt box: [+] on left, [mode] and [↑] on right
            b_attach, b_spacer, b_mode, b_send = st.columns([0.7, 4.9, 2.4, 0.9])
            with b_attach:
                with st.popover("+", help="Attach spatial/depth constraints to query"):
                    st.markdown("**[ATTACH QUERY CONSTRAINTS]**")
                    pin_region = st.selectbox("PIN REGION", options=["(None)"] + _ALL_REGION_NAMES, index=0)
                    pin_wmo = st.text_input("PIN WMO ID (OPTIONAL)", placeholder="e.g. 2902269")
                    c_z1, c_z2 = st.columns(2)
                    with c_z1:
                        pin_min_d = st.number_input("MIN dbar", value=0, min_value=0, max_value=2000, step=50)
                    with c_z2:
                        pin_max_d = st.number_input("MAX dbar", value=500, min_value=10, max_value=6000, step=50)
                    pin_force = st.checkbox("FORCE LIVE ERDDAP/ARGOVIS FETCH", value=False)
            with b_mode:
                st.session_state["delivery_mode"] = st.selectbox(
                    "Mode",
                    options=["research", "standard", "expert"],
                    index=["research", "standard", "expert"].index(st.session_state["delivery_mode"]),
                    label_visibility="collapsed",
                )
            with b_send:
                send_clicked = st.button("↑", key="send_query_btn", type="primary", use_container_width=True)

        if send_clicked and user_question.strip():
            question_text = user_question.strip()
            if pin_region != "(None)" and pin_region.lower() not in question_text.lower():
                question_text += f" in {pin_region}"
            if pin_wmo.strip():
                question_text += f" for float {pin_wmo.strip()}"

            from siqva.followup import ConversationState, try_resolve_followup

            c_state: ConversationState = st.session_state.get("conversation_state") or ConversationState()
            followup = try_resolve_followup(question_text, c_state)

            if followup.resolved and followup.spec is not None:
                st.session_state["chat_message"] = None
                with st.spinner("APPLYING FOLLOW-UP EDITS & FETCHING..."):
                    target_spec = followup.spec
                    updates = {}
                    if pin_min_d > 0 or pin_max_d != 500:
                        updates["depth_range"] = DepthRange(min_depth=float(pin_min_d), max_depth=float(pin_max_d))
                    if updates:
                        target_spec = target_spec.model_copy(update=updates)
                    pipeline_res = run_spec(
                        target_spec,
                        force_refresh=pin_force,
                        question=question_text,
                        max_request_size=_ui_max_request_size(),
                    )
                    st.session_state["pipeline_res"] = pipeline_res
                    if pipeline_res.spec is not None:
                        st.session_state["conversation_state"] = c_state.with_new_query(
                            pipeline_res.spec, question=question_text
                        )
                    st.rerun()
                    st.session_state["pipeline_res"] = pipeline_res
                    if pipeline_res.spec is not None:
                        st.session_state["conversation_state"] = c_state.with_new_query(
                            pipeline_res.spec, question=question_text
                        )
                    st.rerun()

            route_res = route(question_text)

            if route_res.target == RouteTarget.GLOSSARY:
                from siqva.glossary import lookup_glossary

                entity = route_res.extracted_entity or question_text
                gloss_res = lookup_glossary(entity)
                if gloss_res.found and gloss_res.entry is not None:
                    e = gloss_res.entry
                    st.session_state["chat_message"] = {
                        "type": "glossary",
                        "term": html.escape(e.term),
                        "canonical_name": html.escape(e.canonical_name),
                        "definition": html.escape(e.definition),
                        "source": html.escape(str(e.source)),
                        "formula": html.escape(e.formula or ""),
                    }
                elif gloss_res.found and gloss_res.entry is None:
                    st.session_state["chat_message"] = {
                        "type": "glossary_unverified",
                        "term": html.escape(gloss_res.term_name or ""),
                        "message": html.escape(gloss_res.message),
                        "source": html.escape(gloss_res.source_citation or ""),
                    }
                else:
                    st.session_state["chat_message"] = {
                        "type": "glossary_not_found",
                        "message": html.escape(gloss_res.message),
                    }
                st.session_state["pipeline_res"] = None
                st.rerun()

            elif route_res.target == RouteTarget.META:
                meta_card = None
                if st.session_state.get("pipeline_res") and st.session_state["pipeline_res"].card:
                    meta_card = st.session_state["pipeline_res"].card
                meta_msg = "No query has been run in this session yet."
                if meta_card is not None:
                    meta_msg = (
                        f"Last query: **{html.escape(meta_card.spec.intent.value.title())}** "
                        f"| Mode: **{html.escape(meta_card.mode.value)}** "
                        f"| Profiles: **{meta_card.profile_count:,}** "
                        f"| Rows: **{meta_card.row_count:,}** "
                        f"| argopy: `{html.escape(meta_card.argopy_version)}` "
                        f"| xarray: `{html.escape(meta_card.xarray_version)}`"
                    )
                st.session_state["chat_message"] = {
                    "type": "meta",
                    "message": meta_msg,
                }
                st.rerun()

            else:
                # DATA_FETCH, OPERATION, COMPARISON, CLARIFICATION — all go through run()
                st.session_state["chat_message"] = None
                with st.spinner("PARSING SPEC & FETCHING QC-VERIFIED PROFILES..."):
                    pipeline_res = run(question=question_text, force_refresh=pin_force, max_request_size=_ui_max_request_size())
                    if pipeline_res.spec:
                        updates = {}
                        if pipeline_res.spec.mode == DataMode.RESEARCH and st.session_state["delivery_mode"] != "research":
                            updates["mode"] = DataMode(st.session_state["delivery_mode"])
                        if pin_min_d > 0 or pin_max_d != 500:
                            updates["depth_range"] = DepthRange(min_depth=float(pin_min_d), max_depth=float(pin_max_d))
                        if updates:
                            pipeline_res = run_spec(
                                pipeline_res.spec.model_copy(update=updates),
                                force_refresh=pin_force,
                                question=question_text,
                                max_request_size=_ui_max_request_size(),
                            )
                    st.session_state["pipeline_res"] = pipeline_res
                    if pipeline_res.spec is not None:
                        st.session_state["conversation_state"] = c_state.with_new_query(
                            pipeline_res.spec, question=question_text
                        )
                    st.rerun()

        # Dynamic Quick Query Templates loaded from data/examples.json
        st.markdown(
            "<div style='margin-top: 14px; margin-bottom: 8px; color: #64748B; font-size: 0.70rem; letter-spacing: 0.06em; font-weight: 600;'>QUICK QUERY TEMPLATES</div>",
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

        # Render 3 columns per row for examples
        num_cols = min(3, len(sample_queries))
        q_cols = st.columns(num_cols)
        for idx, (sq_text, sq_label) in enumerate(sample_queries[:num_cols]):
            with q_cols[idx]:
                if st.button(sq_label, key=f"quick_{sq_label}", use_container_width=True):
                    with st.status("Processing oceanographic query...", expanded=False) as status_box:
                        st.write("1. Parsing natural language and resolving bounding box...")
                        st.write("2. Checking Parquet cache and fetching Argo observations...")
                        pipeline_res = run(question=sq_text, force_refresh=False, max_request_size=_ui_max_request_size())
                        st.write("3. Auditing Quality Control and constructing visualization cards...")
                        status_box.update(label="Query completed", state="complete")
                    st.session_state["pipeline_res"] = pipeline_res
                    st.rerun()


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
            idx_a = st.selectbox("Select Run A", options=range(len(all_cards)), format_func=lambda i: card_labels[i], index=0)
        with col_b:
            st.markdown("**Comparison Run (B)**")
            idx_b = st.selectbox("Select Run B", options=range(len(all_cards)), format_func=lambda i: card_labels[i], index=min(1, len(all_cards) - 1))

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
                st.plotly_chart(_style_fig(res_a.figures[fig_key_a]), use_container_width=True, theme=None)
            else:
                st.info("No figure available for Run A")

        with v_col_b:
            st.markdown(f"**Run B: {html.escape(card_b.question or card_b.card_id[:8])}**")
            if res_b and res_b.figures:
                fig_key_b = next((k for k in ["profile", "thermocline", "tchp", "acoustic", "ts", "map"] if k in res_b.figures), next(iter(res_b.figures)))
                st.plotly_chart(_style_fig(res_b.figures[fig_key_b]), use_container_width=True, theme=None)
            else:
                st.info("No figure available for Run B")
