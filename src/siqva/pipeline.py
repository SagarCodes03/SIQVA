"""End-to-end execution pipeline connecting parsing, validation, fetching, QC, analysis, and cards."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import pandas as pd
import plotly.graph_objects as go
import argopy
import xarray as xr

from .analyzer import AnalysisResult, analyze
from .card import QueryCard, build_card, generate_script, save_card
from .floatindex import load_float_index
from .gazetteer import KNOWN_REGIONS
from . import fetcher
from .fetcher import FetchMetadata, FetchResult, FetchStatus

# Module attribute so patch("siqva.pipeline.fetch") works at test time
fetch = fetcher.fetch
_original_fetch = fetcher.fetch


def _resolve_fetcher(fetcher_fn: Any = None) -> Any:
    """Resolve fetch function at call time, respecting mocks on pipeline.fetch or fetcher.fetch."""
    if fetcher_fn is not None:
        return fetcher_fn

    import sys
    pipeline_mod = sys.modules.get("siqva.pipeline")
    p_fetch = getattr(pipeline_mod, "fetch", None)
    f_fetch = getattr(fetcher, "fetch", None)

    # 1. Did someone patch siqva.pipeline.fetch?
    if p_fetch is not _original_fetch and p_fetch is not None:
        return p_fetch

    # 2. Did someone patch siqva.fetcher.fetch?
    if f_fetch is not _original_fetch and f_fetch is not None:
        return f_fetch

    # 3. Default to current siqva.fetcher.fetch
    return f_fetch or _original_fetch
from .parser import ClarificationNeeded, ParseOutcome, parse_detailed
from .plots import (
    plot_acoustic_profile,
    plot_bgc_omz_profile,
    plot_cyclone_tchp,
    plot_depth_profile,
    plot_float_drift_velocity,
    plot_hovmoller_section,
    plot_position_map,
    plot_regional_climatology_envelope,
    plot_stability_buoyancy,
    plot_thermocline_and_barrier,
    plot_ts_diagram,
    plot_ts_with_isopycnals,
    render_index_overview_map,
)
from .spec import DepthRange, Intent, QuerySpec, Variable
from .validator import DEFAULT_MAX_REQUEST_SIZE
import traceback
import uuid

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
_log_file = LOGS_DIR / "siqva.log"
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setLevel(logging.ERROR)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == str(_log_file.resolve()) for h in logger.handlers):
    logger.addHandler(_file_handler)


class PipelineStatus(str, Enum):
    """Overall status of pipeline execution."""

    SUCCESS = "success"
    CLARIFICATION_NEEDED = "clarification_needed"
    EMPTY = "empty"
    OVERSIZED = "oversized"
    TIMEOUT = "timeout"
    ERROR = "error"
    INTERNAL_ERROR = "internal_error"


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
    warning: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    render_time_s: Optional[float] = None

    @property
    def is_success(self) -> bool:
        return self.status == PipelineStatus.SUCCESS


def _run_spec_impl(
    spec: QuerySpec,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    db_path: Optional[Path] = None,
    fetcher_fn: Any = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE,
    wall_clock_budget: Optional[float] = None,
    **fetch_kwargs: Any,
) -> PipelineResult:
    """Execute a fully formed QuerySpec through fetcher, QC, analysis, plots, and card generation."""
    from .chunking import fetch_chunked, is_chunked_spec
    from .fetcher import get_wall_clock_budget

    if wall_clock_budget is None:
        wall_clock_budget = get_wall_clock_budget()

    # Metadata requests (Float Position Map) use local FloatIndex directly; no remote fetcher call
    if spec.intent == Intent.MAP:
        index = load_float_index()
        if index is None or not index.is_available:
            return PipelineResult(
                status=PipelineStatus.ERROR,
                spec=spec,
                error_message="Local float index snapshot (data/float_index.parquet) is not available. Float position maps require the local float index.",
            )

        target_loc = spec.basin or spec.region
        profile_count = index.count_profiles(target_loc, date_range=spec.date_range)
        last_pos = index.last_positions(target_loc, date_range=spec.date_range)
        float_count = len(last_pos)

        fig, render_time_s, display_mode = render_index_overview_map(index, spec)
        snapshot_date_str = str(index.metadata.get("build_date") or index.max_date or "unknown")[:10]
        age_days = index.snapshot_age_days()

        region_label = spec.basin or (next((name for name, b in KNOWN_REGIONS.items() if b == spec.region), None) or "custom coordinates")
        summary = (
            f"**Argo Float Position Map Overview**\n\n"
            f"- **Region / Basin**: {region_label}\n"
            f"- **Period**: {spec.date_range.start} to {spec.date_range.end}\n"
            f"- **Active Floats**: {float_count:,}\n"
            f"- **Total Profiles**: {profile_count:,}\n"
            f"- **Index Snapshot**: {snapshot_date_str} ({age_days} days old)\n"
            f"- **Map Render Time**: {render_time_s:.3f} s\n\n"
            f"{display_mode}"
        )

        analysis = AnalysisResult(
            profile_count=profile_count,
            observation_count=0,
            date_start=spec.date_range.start.isoformat(),
            date_end=spec.date_range.end.isoformat(),
            mode=spec.mode,
            qc_filter_description="metadata snapshot (local float index)",
            effective_depth_range=DepthRange(min_depth=0.0, max_depth=0.0),
            is_default_depth=True,
            is_cached=True,
            profile_count_verified=True,
            summary=summary,
            summary_markdown=summary,
            intent=spec.intent,
        )

        meta = FetchMetadata(
            src="float_index",
            source="local_float_index",
            argopy_version=getattr(argopy, "__version__", "1.5.0"),
            xarray_version=getattr(xr, "__version__", "2026.9.0"),
            fetch_timestamp=datetime.now(timezone.utc).isoformat(),
            row_count=0,
            profile_count=profile_count,
            data_hash="metadata_only",
            fetch_key=spec.fetch_key(),
        )

        fetch_res = FetchResult(
            status=FetchStatus.SUCCESS,
            data=last_pos,
            is_cached=True,
            cache_key=spec.fetch_key(),
            metadata=meta,
            effective_depth_range=DepthRange(min_depth=0.0, max_depth=0.0),
            profile_count_verified=True,
            profile_count=profile_count,
        )

        card = build_card(spec, fetch_res, analysis, question=question, session_id=session_id)
        script = generate_script(card)

        return PipelineResult(
            status=PipelineStatus.SUCCESS,
            spec=spec,
            fetch_result=fetch_res,
            analysis=analysis,
            figures={"map": fig},
            card=card,
            script=script,
            render_time_s=render_time_s,
        )

    resolved_fetcher = _resolve_fetcher(fetcher_fn)

    from .planner import plan_request, PlanKind
    index = load_float_index()
    plan_decision = plan_request(spec, index=index)

    if plan_decision.plan == PlanKind.REFUSE:
        error_msg = plan_decision.reasons[0] if plan_decision.reasons else "Query exceeds allowable regional bounds."
        option_labels = [opt.label for opt in plan_decision.options]
        warning_text = "\n".join(f"- {lbl}" for lbl in option_labels) if option_labels else None
        return PipelineResult(
            status=PipelineStatus.OVERSIZED,
            spec=spec,
            error_message=error_msg,
            warning=warning_text,
            warnings=option_labels,
        )
    elif plan_decision.plan == PlanKind.SAMPLE:
        from .fetcher import fetch_sample
        sample_engine = fetch_kwargs.pop("fetcher_engine", None)
        if sample_engine is None and isinstance(fetcher_fn, type):
            sample_engine = fetcher_fn
        fetch_res: FetchResult = fetch_sample(
            spec,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
            wall_clock_budget=wall_clock_budget,
            fetcher_engine=sample_engine,
            float_index=index,
            **fetch_kwargs,
        )
    elif plan_decision.plan == PlanKind.CHUNKED or is_chunked_spec(spec, max_request_size=max_request_size):
        fetch_res: FetchResult = fetch_chunked(
            spec,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
            fetcher_fn=resolved_fetcher,
            max_request_size=max_request_size,
            wall_clock_budget=wall_clock_budget,
            **fetch_kwargs,
        )
    else:
        fetch_res: FetchResult = resolved_fetcher(
            spec,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
            max_request_size=max_request_size,
            wall_clock_budget=wall_clock_budget,
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

    # Profile figure (for standard profile and trend intents)
    if spec.intent in (Intent.PROFILE, Intent.TREND):
        primary_var = spec.variables[0] if spec.variables else Variable.TEMP
        try:
            figures["profile"] = plot_depth_profile(fetch_res.data, variable=primary_var)
        except Exception:
            pass

    # T-S figure (for ts intent, or profile intent when both TEMP and PSAL are requested)
    if spec.intent in (Intent.TS, Intent.PROFILE):
        if Variable.TEMP in spec.variables and Variable.PSAL in spec.variables:
            try:
                figures["ts"] = plot_ts_diagram(fetch_res.data)
            except Exception:
                pass

    # TEOS-10 Ocean Physics figures (built ONLY when specifically requested by physics intent)
    if analysis.physics_summaries:
        rep_profile = max(analysis.physics_summaries, key=lambda s: s.max_depth_m)
        if spec.intent == Intent.THERMOCLINE:
            try:
                figures["thermocline"] = plot_thermocline_and_barrier(fetch_res.data, rep_profile)
            except Exception:
                pass
        elif spec.intent == Intent.TCHP:
            try:
                figures["tchp"] = plot_cyclone_tchp(fetch_res.data, rep_profile)
            except Exception:
                pass
        elif spec.intent == Intent.ACOUSTIC:
            try:
                figures["acoustic"] = plot_acoustic_profile(fetch_res.data, rep_profile)
            except Exception:
                pass

    # Additional specialized and oceanographic figures
    if spec.intent == Intent.HOVMOLLER:
        try:
            param = "TEMP" if Variable.TEMP in spec.variables else ("PSAL" if Variable.PSAL in spec.variables else "TEMP")
            figures["hovmoller"] = plot_hovmoller_section(fetch_res.data, param=param)
        except Exception:
            pass
    elif spec.intent == Intent.BUOYANCY:
        try:
            mid_lat = (spec.region.lat_min + spec.region.lat_max) / 2.0 if spec.region else (float(fetch_res.data["LATITUDE"].mean()) if (fetch_res.data is not None and "LATITUDE" in fetch_res.data) else 0.0)
            mid_lon = (spec.region.lon_min + spec.region.lon_max) / 2.0 if spec.region else (float(fetch_res.data["LONGITUDE"].mean()) if (fetch_res.data is not None and "LONGITUDE" in fetch_res.data) else 0.0)
            figures["buoyancy"] = plot_stability_buoyancy(
                fetch_res.data,
                lat=mid_lat,
                lon=mid_lon,
            )
        except Exception:
            pass
    elif spec.intent == Intent.TS_ISOPYCNAL:
        try:
            mid_lat = (spec.region.lat_min + spec.region.lat_max) / 2.0 if spec.region else (float(fetch_res.data["LATITUDE"].mean()) if (fetch_res.data is not None and "LATITUDE" in fetch_res.data) else 0.0)
            mid_lon = (spec.region.lon_min + spec.region.lon_max) / 2.0 if spec.region else (float(fetch_res.data["LONGITUDE"].mean()) if (fetch_res.data is not None and "LONGITUDE" in fetch_res.data) else 0.0)
            figures["ts_isopycnal"] = plot_ts_with_isopycnals(
                fetch_res.data,
                lon=mid_lon,
                lat=mid_lat,
            )
        except Exception:
            pass
    elif spec.intent == Intent.CLIMATOLOGY:
        try:
            param = "TEMP" if Variable.TEMP in spec.variables else ("PSAL" if Variable.PSAL in spec.variables else "TEMP")
            figures["climatology"] = plot_regional_climatology_envelope(fetch_res.data, param=param)
        except Exception:
            pass
    elif spec.intent == Intent.OMZ:
        try:
            figures["omz"] = plot_bgc_omz_profile(fetch_res.data)
        except Exception:
            pass
    elif spec.intent == Intent.DRIFT:
        try:
            figures["drift"] = plot_float_drift_velocity(fetch_res.data)
        except Exception:
            pass

    # 3. Query card and script persistence
    card = build_card(spec, fetch_res, analysis, question=question, session_id=session_id)
    warning_msg: Optional[str] = None
    try:
        if db_path is not None:
            save_card(card, db_path=db_path)
        else:
            save_card(card)
    except Exception as exc:
        logger.error("Failed to save query card to history: %s", exc, exc_info=True)
        warning_msg = "Result could not be saved to history"

    script = generate_script(card)

    return PipelineResult(
        status=PipelineStatus.SUCCESS,
        spec=spec,
        fetch_result=fetch_res,
        analysis=analysis,
        figures=figures,
        card=card,
        script=script,
        warning=warning_msg,
        warnings=[warning_msg] if warning_msg else [],
    )


def run_spec(
    spec: QuerySpec,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    db_path: Optional[Path] = None,
    fetcher_fn: Any = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE,
    wall_clock_budget: Optional[float] = None,
    **fetch_kwargs: Any,
) -> PipelineResult:
    """Execute a fully formed QuerySpec through fetcher, QC, analysis, plots, and card generation."""
    try:
        return _run_spec_impl(
            spec=spec,
            cache_dir=cache_dir,
            force_refresh=force_refresh,
            db_path=db_path,
            fetcher_fn=fetcher_fn,
            question=question,
            session_id=session_id,
            max_request_size=max_request_size,
            wall_clock_budget=wall_clock_budget,
            **fetch_kwargs,
        )
    except Exception as exc:
        ref_id = uuid.uuid4().hex[:8]
        logger.error(
            "Internal run_spec error (ref: %s) on spec %r: %s\n%s",
            ref_id,
            spec,
            exc,
            traceback.format_exc(),
        )
        return PipelineResult(
            status=PipelineStatus.INTERNAL_ERROR,
            spec=spec,
            question=question,
            error_message=(
                f"An unexpected internal error occurred (Reference ID: {ref_id}). "
                "Our team has logged the details. Please try rephrasing your request."
            ),
        )


def run(
    question: str,
    today: Optional[date] = None,
    cache_dir: Optional[Path] = None,
    force_refresh: bool = False,
    llm_client: Any = None,
    allow_llm: bool = True,
    db_path: Optional[Path] = None,
    max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE,
    wall_clock_budget: Optional[float] = None,
    fetcher_fn: Any = None,
    **kwargs: Any,
) -> PipelineResult:
    """Execute end-to-end question processing: parse -> validate -> fetch -> analyze -> card."""
    try:
        outcome: ParseOutcome = parse_detailed(
            question,
            today=today,
            llm_client=llm_client,
            allow_llm=allow_llm,
            max_request_size=max_request_size,
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
            fetcher_fn=fetcher_fn,
            question=question,
            max_request_size=max_request_size,
            wall_clock_budget=wall_clock_budget,
            **kwargs,
        )
        res.question = question
        res.parse_outcome = outcome
        return res
    except Exception as exc:
        ref_id = uuid.uuid4().hex[:8]
        logger.error(
            "Internal pipeline error (ref: %s) on question %r: %s\n%s",
            ref_id,
            question,
            exc,
            traceback.format_exc(),
        )
        return PipelineResult(
            status=PipelineStatus.INTERNAL_ERROR,
            question=question,
            error_message=(
                f"An unexpected internal error occurred (Reference ID: {ref_id}). "
                "Our team has logged the details. Please try rephrasing your request."
            ),
        )
