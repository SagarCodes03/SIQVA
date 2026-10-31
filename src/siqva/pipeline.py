"""End-to-end execution pipeline connecting parsing, validation, fetching, QC, analysis, and cards."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import pandas as pd
import plotly.graph_objects as go

from .analyzer import AnalysisResult, analyze
from .card import QueryCard, build_card, generate_script, save_card
from .fetcher import FetchResult, FetchStatus, fetch
from .parser import ClarificationNeeded, ParseOutcome, parse_detailed
from .plots import (
    plot_acoustic_profile,
    plot_cyclone_tchp,
    plot_depth_profile,
    plot_position_map,
    plot_thermocline_and_barrier,
    plot_ts_diagram,
)
from .spec import Intent, QuerySpec, Variable


class PipelineStatus(str, Enum):
    """Overall status of pipeline execution."""

    SUCCESS = "success"
    CLARIFICATION_NEEDED = "clarification_needed"
    EMPTY = "empty"
    OVERSIZED = "oversized"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class PipelineResult:
    """Consolidated result returned by the pipeline for consumption by the UI and API."""

    status: PipelineStatus
    question: Optional[str] = None
    spec: Optional[QuerySpec] = None
    parse_outcome: Optional[ParseOutcome] = None
    clarification: Optional[ClarificationNeeded] = None
    fetch_result: Optional[FetchResult] = None
    analysis: Optional[AnalysisResult] = None
    figures: dict[str, go.Figure] = field(default_factory=dict)
    card: Optional[QueryCard] = None
    script: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.status == PipelineStatus.SUCCESS


def run_spec(
    spec: QuerySpec,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    db_path: Optional[Path] = None,
    fetcher_fn: Any = fetch,
    **fetch_kwargs: Any,
) -> PipelineResult:
    """Execute a fully formed QuerySpec through fetcher, QC, analysis, plots, and card generation."""
    fetch_res: FetchResult = fetcher_fn(
        spec,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
        **fetch_kwargs,
    )

    if fetch_res.status == FetchStatus.EMPTY:
        return PipelineResult(
            status=PipelineStatus.EMPTY,
            spec=spec,
            fetch_result=fetch_res,
            error_message=fetch_res.error_message or "No Argo observations were found matching the query constraints.",
        )

    if fetch_res.status == FetchStatus.OVERSIZED:
        return PipelineResult(
            status=PipelineStatus.OVERSIZED,
            spec=spec,
            fetch_result=fetch_res,
            error_message=fetch_res.error_message or "Query exceeds allowable profile or size thresholds.",
        )

    if fetch_res.status == FetchStatus.TIMEOUT:
        return PipelineResult(
            status=PipelineStatus.TIMEOUT,
            spec=spec,
            fetch_result=fetch_res,
            error_message=fetch_res.error_message or "Data fetch timed out. Remote Argo server was unresponsive.",
        )

    if fetch_res.status == FetchStatus.ERROR or fetch_res.data is None:
        return PipelineResult(
            status=PipelineStatus.ERROR,
            spec=spec,
            fetch_result=fetch_res,
            error_message=fetch_res.error_message or "An unexpected error occurred while fetching Argo observations.",
        )

    # 1. Deterministic oceanographic analysis
    analysis = analyze(fetch_res.data, spec, fetch_res)

    # 2. Build figures
    figures: dict[str, go.Figure] = {}

    # Map figure
    try:
        figures["map"] = plot_position_map(fetch_res.data)
    except Exception:
        pass

    # Profile figure
    primary_var = spec.variables[0] if spec.variables else Variable.TEMP
    try:
        figures["profile"] = plot_depth_profile(fetch_res.data, variable=primary_var)
    except Exception:
        pass

    # T-S figure
    if Variable.TEMP in spec.variables and Variable.PSAL in spec.variables:
        try:
            figures["ts"] = plot_ts_diagram(fetch_res.data)
        except Exception:
            pass

    # TEOS-10 Ocean Physics figures
    if analysis.physics_summaries:
        rep_profile = max(analysis.physics_summaries, key=lambda s: s.max_depth_m)
        try:
            figures["thermocline"] = plot_thermocline_and_barrier(fetch_res.data, rep_profile)
        except Exception:
            pass
        try:
            figures["tchp"] = plot_cyclone_tchp(fetch_res.data, rep_profile)
        except Exception:
            pass
        try:
            figures["acoustic"] = plot_acoustic_profile(fetch_res.data, rep_profile)
        except Exception:
            pass

    # 3. Query card and script persistence
    card = build_card(spec, fetch_res, analysis)
    if db_path is not None:
        save_card(card, db_path=db_path)
    else:
        save_card(card)

    script = generate_script(card)

    return PipelineResult(
        status=PipelineStatus.SUCCESS,
        spec=spec,
        fetch_result=fetch_res,
        analysis=analysis,
        figures=figures,
        card=card,
        script=script,
    )


def run(
    question: str,
    today: Optional[date] = None,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    llm_client: Any = None,
    allow_llm: bool = True,
    db_path: Optional[Path] = None,
    **kwargs: Any,
) -> PipelineResult:
    """Execute end-to-end question processing: parse -> validate -> fetch -> analyze -> card."""
    outcome: ParseOutcome = parse_detailed(
        question,
        today=today,
        llm_client=llm_client,
        allow_llm=allow_llm,
    )

    if outcome.clarification is not None or outcome.spec is None:
        return PipelineResult(
            status=PipelineStatus.CLARIFICATION_NEEDED,
            question=question,
            parse_outcome=outcome,
            clarification=outcome.clarification,
            error_message=outcome.clarification.message if outcome.clarification else "Clarification required.",
        )

    res = run_spec(
        outcome.spec,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
        db_path=db_path,
        **kwargs,
    )
    res.question = question
    res.parse_outcome = outcome
    return res
