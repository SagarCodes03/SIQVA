"""QueryCard model, reproducible script generation, SQLite persistence, and re-run diffing."""

from __future__ import annotations

import json
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

import argopy
import xarray as xr

from .analyzer import AnalysisResult
from .fetcher import (
    DEFAULT_CACHE_DIR,
    FetchResult,
    compute_canonical_data_hash,
    count_unique_profiles,
    fetch,
)
from .qc import get_qc_filter_description
from .spec import DataMode, DepthRange, Intent, QuerySpec
from .gazetteer import KNOWN_REGIONS

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "cards.sqlite"


def _resolve_db_path(db_path: Path | str) -> Path:
    """Resolve database path relative to project root if not absolute."""
    path = Path(db_path)
    if not path.is_absolute():
        return PROJECT_ROOT / path
    return path


class QueryCard(BaseModel):
    """Reproducible record of a completed query, its parameters, environment, and data provenance."""

    model_config = ConfigDict(frozen=True)

    card_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    spec: QuerySpec
    spec_json: str
    spec_hash: str
    fetch_key: str
    mode: DataMode
    qc_filter_description: str
    effective_depth_range: DepthRange
    source: str = "erddap"
    src: str = "erddap"
    argopy_version: str
    xarray_version: str
    fetch_timestamp: str
    is_cached: bool
    row_count: int
    profile_count: int
    profile_count_verified: bool
    data_hash: str
    created_at: str
    question: Optional[str] = None
    chunks: Optional[list[str]] = None
    session_id: Optional[str] = None
    guardrail_disabled: bool = False


class DiffSummary(BaseModel):
    """Deterministic diff comparison between an original QueryCard and a re-run fetch."""

    model_config = ConfigDict(frozen=True)

    is_same: bool
    old_data_hash: str
    new_data_hash: str
    old_row_count: int
    new_row_count: int
    row_diff: int
    old_profile_count: int
    new_profile_count: int
    profile_diff: int
    new_profiles: list[tuple[Any, Any]] = Field(default_factory=list)
    missing_profiles: list[tuple[Any, Any]] = Field(default_factory=list)
    version_changed: bool = False
    argopy_version_diff: Optional[tuple[str, str]] = None
    xarray_version_diff: Optional[tuple[str, str]] = None
    summary: str


def build_card(
    spec: QuerySpec,
    fetch_result: FetchResult,
    analysis: Optional[AnalysisResult] = None,
    card_id: Optional[str] = None,
    question: Optional[str] = None,
    session_id: Optional[str] = None,
    chunks: Optional[list[tuple[str, str]]] = None,
) -> QueryCard:
    """Build an immutable QueryCard from a spec, fetch result, and optional analysis."""
    meta = fetch_result.metadata

    source = meta.source if meta else "erddap"
    src = meta.src if meta else "erddap"
    argopy_ver = meta.argopy_version if meta else str(argopy.__version__)
    xarray_ver = meta.xarray_version if meta else str(xr.__version__)
    fetch_ts = meta.fetch_timestamp if meta else (datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    if meta and meta.data_hash:
        d_hash = meta.data_hash
    elif fetch_result.data is not None:
        d_hash = compute_canonical_data_hash(fetch_result.data)
    else:
        d_hash = ""
    r_count = meta.row_count if meta else (len(fetch_result.data) if fetch_result.data is not None else 0)

    if analysis:
        p_count = analysis.profile_count
        qc_desc = analysis.qc_filter_description
    elif meta:
        p_count = meta.profile_count
        qc_desc = get_qc_filter_description(spec.mode)
    else:
        p_count = 0
        qc_desc = get_qc_filter_description(spec.mode)

    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    c_id = card_id or f"{spec.spec_hash()[:8]}_{uuid.uuid4().hex[:8]}"

    chunks: Optional[list[str]] = None
    from .chunking import is_chunked_spec, split_date_range_into_months
    from .validator import is_size_guardrail_enabled

    guardrail_disabled = not is_size_guardrail_enabled()

    # Determine chunk labels: use provided chunks if given, otherwise compute from spec
    if chunks is None and is_chunked_spec(spec):
        chunks = [label for _, label in split_date_range_into_months(spec.date_range)]

    return QueryCard(
        card_id=c_id,
        spec=spec,
        spec_json=spec.normalized_json(),
        spec_hash=spec.spec_hash(),
        fetch_key=spec.fetch_key(),
        mode=spec.mode,
        qc_filter_description=qc_desc,
        effective_depth_range=fetch_result.effective_depth_range,
        source=source,
        src=src,
        argopy_version=argopy_ver,
        xarray_version=xarray_ver,
        fetch_timestamp=fetch_ts,
        is_cached=fetch_result.is_cached,
        row_count=r_count,
        profile_count=p_count,
        profile_count_verified=fetch_result.profile_count_verified,
        data_hash=d_hash,
        created_at=created_at,
        question=question,
        chunks=chunks,
        session_id=session_id,
        guardrail_disabled=guardrail_disabled,
    )


def format_history_label(card: QueryCard, max_question_length: int = 40) -> str:
    """Return a concise, deterministic sidebar label for a stored query card."""
    question = (card.question or "").strip() or f"{card.spec.intent.value.title()} query"
    if len(question) > max_question_length:
        question = f"{question[: max_question_length - 1].rstrip()}\u2026"

    region_name = next(
        (name for name, bbox in KNOWN_REGIONS.items() if bbox == card.spec.region),
        "custom coordinates",
    )
    return f"{question} \u00b7 {card.created_at[:10]} \u00b7 {region_name}"


UNSUPPORTED_SCRIPT_PLOT_INTENTS = {
    Intent.HOVMOLLER,
    Intent.BUOYANCY,
    Intent.TS_ISOPYCNAL,
    Intent.CLIMATOLOGY,
    Intent.OMZ,
    Intent.DRIFT,
}


def _get_reproduction_scope(intent: Intent) -> str:
    """Return explicit reproduction scope statement for the script header."""
    if intent in UNSUPPORTED_SCRIPT_PLOT_INTENTS:
        return "data fetch and counts only; plots for this intent are not included"
    return f"data fetch, QC filtering, and profile counts for {intent.value} analysis"


def generate_script(card: QueryCard) -> str:
    """Generate a standalone, runnable Python script reproducing this query via argopy."""
    spec = card.spec
    depth = card.effective_depth_range

    lon_min = float(spec.region.lon_min)
    lon_max = float(spec.region.lon_max)
    lat_min = float(spec.region.lat_min)
    lat_max = float(spec.region.lat_max)
    dpt_min = float(depth.min_depth)
    dpt_max = float(depth.max_depth)
    start_str = spec.date_range.start.isoformat()
    end_str = spec.date_range.end.isoformat()
    mode_str = card.mode.value
    src_str = card.src
    repro_scope = _get_reproduction_scope(spec.intent)
    guardrail_note = "\nGuardrails: Bypassed (SIQVA_DISABLE_SIZE_GUARDRAIL=1)" if card.guardrail_disabled else ""

    if card.chunks and len(card.chunks) > 1:
        from .chunking import split_date_range_into_months

        chunk_tuples = [
            (dr.start.isoformat(), dr.end.isoformat())
            for dr, _ in split_date_range_into_months(spec.date_range)
        ]
        script = f'''#!/usr/bin/env python3
"""Reproducible Argo data fetch script generated by SIQVA.

Card ID: {card.card_id}
Spec Hash: {card.spec_hash}
Intent: {spec.intent.value}
Reproduction: {repro_scope}
Data Mode: {mode_str} ({card.qc_filter_description})
Timestamp: {card.fetch_timestamp}
Expected Rows: {card.row_count}
Expected Profiles: {card.profile_count}
Chunked Fetch: {len(card.chunks)} monthly chunks{guardrail_note}
"""

import argopy
import pandas as pd

# 1. Initialize argopy DataFetcher with explicit mode
fetcher = argopy.DataFetcher(mode="{mode_str}", src="{src_str}")

# 2. Monthly chunk date ranges
chunks = {chunk_tuples!r}

# 3. Remote fetch with loop over monthly chunks
dfs = []
for start_d, end_d in chunks:
    box = [{lon_min}, {lon_max}, {lat_min}, {lat_max}, {dpt_min}, {dpt_max}, start_d, end_d]
    print(f"Fetching chunk {{start_d}} to {{end_d}}...")
    chunk_df = fetcher.region(box).to_dataframe()
    dfs.append(chunk_df)

df = pd.concat(dfs, ignore_index=True)
dedup_cols = [c for c in ["PLATFORM_NUMBER", "CYCLE_NUMBER", "PRES", "TIME"] if c in df.columns]
if dedup_cols:
    df = df.drop_duplicates(subset=dedup_cols).reset_index(drop=True)

# 4. Deterministic row and profile counting
row_count = len(df)
if "PLATFORM_NUMBER" in df and "CYCLE_NUMBER" in df:
    profile_count = int(df[["PLATFORM_NUMBER", "CYCLE_NUMBER"]].drop_duplicates().shape[0])
elif "CYCLE_NUMBER" in df:
    profile_count = int(df["CYCLE_NUMBER"].nunique())
else:
    profile_count = 1 if row_count > 0 else 0

print(f"Results: {{row_count}} rows across {{profile_count}} profiles.")
'''
        return script

    script = f'''#!/usr/bin/env python3
"""Reproducible Argo data fetch script generated by SIQVA.

Card ID: {card.card_id}
Spec Hash: {card.spec_hash}
Intent: {spec.intent.value}
Reproduction: {repro_scope}
Data Mode: {mode_str} ({card.qc_filter_description})
Timestamp: {card.fetch_timestamp}
Expected Rows: {card.row_count}
Expected Profiles: {card.profile_count}{guardrail_note}
"""

import argopy
import pandas as pd

# 1. Initialize argopy DataFetcher with explicit mode
fetcher = argopy.DataFetcher(mode="{mode_str}", src="{src_str}")

# 2. Verified region box format: [lon_min, lon_max, lat_min, lat_max, dpt_min, dpt_max, date_min, date_max]
box = [{lon_min}, {lon_max}, {lat_min}, {lat_max}, {dpt_min}, {dpt_max}, "{start_str}", "{end_str}"]

# 3. Remote fetch
print("Fetching Argo observations...")
df = fetcher.region(box).to_dataframe()

# 4. Deterministic row and profile counting
row_count = len(df)
if "PLATFORM_NUMBER" in df and "CYCLE_NUMBER" in df:
    profile_count = int(df[["PLATFORM_NUMBER", "CYCLE_NUMBER"]].drop_duplicates().shape[0])
elif "CYCLE_NUMBER" in df:
    profile_count = int(df["CYCLE_NUMBER"].nunique())
else:
    profile_count = 1 if row_count > 0 else 0

print(f"Results: {{row_count}} rows across {{profile_count}} profiles.")
'''
    return script


# ==============================================================================
# SQLITE PERSISTENCE (STDLIB SQLITE3)
# ==============================================================================


def _init_db(conn: sqlite3.Connection) -> None:
    """Initialize query card table and indices in SQLite."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS query_cards (
                card_id TEXT PRIMARY KEY,
                spec_hash TEXT NOT NULL,
                fetch_key TEXT NOT NULL,
                mode TEXT NOT NULL,
                created_at TEXT NOT NULL,
                card_json TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_spec_hash ON query_cards (spec_hash)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON query_cards (created_at DESC)")


def save_card(card: QueryCard, db_path: Path | str = DEFAULT_DB_PATH) -> str:
    """Save a QueryCard to the SQLite store."""
    path = _resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with closing(sqlite3.connect(path)) as conn:
        _init_db(conn)
        card_json = card.model_dump_json(indent=2)
        with conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO query_cards (card_id, spec_hash, fetch_key, mode, created_at, card_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    card.card_id,
                    card.spec_hash,
                    card.fetch_key,
                    card.mode.value,
                    card.created_at,
                    card_json,
                ),
            )
    return card.card_id


import os


def is_history_shared() -> bool:
    """Return whether query card history is shared across sessions or isolated."""
    val = os.getenv("SIQVA_SHARED_HISTORY", "1").lower().strip()
    return val not in ("0", "false", "no")


def load_card(
    card_id: str,
    session_id: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> Optional[QueryCard]:
    """Load a QueryCard from SQLite by card_id (or spec_hash fallback)."""
    path = _resolve_db_path(db_path)
    if not path.exists():
        return None

    with closing(sqlite3.connect(path)) as conn:
        _init_db(conn)
        cursor = conn.execute(
            "SELECT card_json FROM query_cards WHERE card_id = ? OR spec_hash = ? ORDER BY created_at DESC LIMIT 1",
            (card_id, card_id),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        card = QueryCard.model_validate_json(row[0])
        if not is_history_shared() and session_id is not None:
            if card.session_id and card.session_id != session_id:
                return None
        return card


def list_cards(
    limit: int = 50,
    session_id: Optional[str] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
) -> list[QueryCard]:
    """List newest cards, with one entry for each spec-hash and mode pair."""
    path = _resolve_db_path(db_path)
    if not path.exists():
        return []

    shared = is_history_shared()
    with closing(sqlite3.connect(path)) as conn:
        _init_db(conn)
        cursor = conn.execute("SELECT card_json FROM query_cards ORDER BY created_at DESC")
        rows = cursor.fetchall()
        cards: list[QueryCard] = []
        seen: set[tuple[str, DataMode]] = set()
        for row in rows:
            card = QueryCard.model_validate_json(row[0])
            if not shared and session_id is not None:
                if card.session_id and card.session_id != session_id:
                    continue
            dedupe_key = (card.spec_hash, card.mode)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            cards.append(card)
            if len(cards) == limit:
                break
        return cards


def restore_card_result(
    card: QueryCard,
    cache_dir: Optional[Path | str] = None,
) -> Any:
    """Reconstruct a full PipelineResult from cached Parquet on disk without network fetch."""
    from .analyzer import analyze
    from .fetcher import DEFAULT_CACHE_DIR, FetchMetadata, FetchResult, FetchStatus
    from .pipeline import PipelineResult, PipelineStatus
    from .plots import (
        plot_acoustic_profile,
        plot_cyclone_tchp,
        plot_depth_profile,
        plot_position_map,
        plot_thermocline_and_barrier,
        plot_ts_diagram,
    )
    from .spec import Intent, Variable

    if cache_dir is None:
        cache_dir = DEFAULT_CACHE_DIR
    cache_path = Path(cache_dir)
    parquet_path = cache_path / f"{card.fetch_key}.parquet"

    script = generate_script(card)

    if not parquet_path.exists():
        return PipelineResult(
            status=PipelineStatus.SUCCESS,
            spec=card.spec,
            card=card,
            script=script,
            warning="Cached data not on disk; click [RE-RUN FETCH & DIFF] to recompute.",
            warnings=["Cached data not on disk; click [RE-RUN FETCH & DIFF] to recompute."],
        )

    try:
        df = pd.read_parquet(parquet_path)
    except Exception as err:
        return PipelineResult(
            status=PipelineStatus.SUCCESS,
            spec=card.spec,
            card=card,
            script=script,
            warning=f"Could not read cached data: {err}. Click [RE-RUN FETCH & DIFF] to recompute.",
            warnings=[f"Could not read cached data: {err}."],
        )

    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=True,
        cache_key=card.fetch_key,
        effective_depth_range=card.effective_depth_range,
        profile_count=card.profile_count,
        profile_count_verified=card.profile_count_verified,
    )

    analysis = analyze(df, card.spec, fetch_res)

    figures: dict[str, Any] = {}
    try:
        figures["map"] = plot_position_map(df)
    except Exception:
        pass

    if card.spec.intent in (Intent.PROFILE, Intent.TREND):
        primary_var = card.spec.variables[0] if card.spec.variables else Variable.TEMP
        try:
            figures["profile"] = plot_depth_profile(df, variable=primary_var)
        except Exception:
            pass

    if card.spec.intent in (Intent.TS, Intent.PROFILE):
        if Variable.TEMP in card.spec.variables and Variable.PSAL in card.spec.variables:
            try:
                figures["ts"] = plot_ts_diagram(df)
            except Exception:
                pass

    if analysis.physics_summaries:
        rep_profile = max(analysis.physics_summaries, key=lambda s: s.max_depth_m)
        if card.spec.intent == Intent.THERMOCLINE:
            try:
                figures["thermocline"] = plot_thermocline_and_barrier(df, rep_profile)
            except Exception:
                pass
        elif card.spec.intent == Intent.TCHP:
            try:
                figures["tchp"] = plot_cyclone_tchp(df, rep_profile)
            except Exception:
                pass
        elif card.spec.intent == Intent.ACOUSTIC:
            try:
                figures["acoustic"] = plot_acoustic_profile(df, rep_profile)
            except Exception:
                pass

    return PipelineResult(
        status=PipelineStatus.SUCCESS,
        spec=card.spec,
        fetch_result=fetch_res,
        analysis=analysis,
        figures=figures,
        card=card,
        script=script,
    )


# ==============================================================================
# RE-RUN & DIFF COMPARISON
# ==============================================================================


def rerun(
    card: QueryCard,
    fetcher_fn: Callable[..., FetchResult] = fetch,
    cache_dir: Optional[Path] = None,
    **fetch_kwargs: Any,
) -> DiffSummary:
    """Re-run a query card by bypassing local cache and comparing the new data hash.

    A changed result is reported as a detailed diff summary, not an error.
    """
    if card.chunks and len(card.chunks) > 1 and fetcher_fn is fetch:
        from .chunking import fetch_chunked

        new_res = fetch_chunked(card.spec, cache_dir=cache_dir, force_refresh=True, **fetch_kwargs)
    else:
        new_res = fetcher_fn(card.spec, cache_dir=cache_dir, force_refresh=True, **fetch_kwargs)

    new_data = new_res.data
    new_meta = new_res.metadata

    new_hash = (
        new_meta.data_hash
        if (new_meta and new_meta.data_hash)
        else compute_canonical_data_hash(new_data)
    )
    new_rows = new_meta.row_count if new_meta else (len(new_data) if new_data is not None else 0)
    new_profs = new_meta.profile_count if new_meta else (count_unique_profiles(new_data) if new_data is not None else 0)

    new_argopy_ver = new_meta.argopy_version if new_meta else str(argopy.__version__)
    new_xarray_ver = new_meta.xarray_version if new_meta else str(xr.__version__)

    version_changed = False
    argopy_diff = None
    xarray_diff = None

    if card.argopy_version != new_argopy_ver:
        version_changed = True
        argopy_diff = (card.argopy_version, new_argopy_ver)
    if card.xarray_version != new_xarray_ver:
        version_changed = True
        xarray_diff = (card.xarray_version, new_xarray_ver)

    is_same = (card.data_hash == new_hash) and (card.data_hash != "")
    row_diff = new_rows - card.row_count
    prof_diff = new_profs - card.profile_count

    # Extract profiles if dataframes are available
    new_profile_set: set[tuple[Any, Any]] = set()
    old_profile_set: set[tuple[Any, Any]] = set()

    if new_data is not None and "PLATFORM_NUMBER" in new_data.columns and "CYCLE_NUMBER" in new_data.columns:
        new_profile_set = set(
            zip(new_data["PLATFORM_NUMBER"].tolist(), new_data["CYCLE_NUMBER"].tolist())
        )

    # Attempt to load old data from cache parquet to compare exact profile sets
    effective_cache_dir = cache_dir if cache_dir is not None else DEFAULT_CACHE_DIR
    if effective_cache_dir is not None:
        old_parquet = Path(effective_cache_dir) / f"{card.fetch_key}.parquet"
        if old_parquet.exists():
            try:
                old_df = pd.read_parquet(old_parquet)
                if "PLATFORM_NUMBER" in old_df.columns and "CYCLE_NUMBER" in old_df.columns:
                    old_profile_set = set(
                        zip(old_df["PLATFORM_NUMBER"].tolist(), old_df["CYCLE_NUMBER"].tolist())
                    )
            except Exception:
                pass

    new_profiles = sorted(list(new_profile_set - old_profile_set))
    missing_profiles = sorted(list(old_profile_set - new_profile_set))

    version_notes = []
    if argopy_diff:
        version_notes.append(f"argopy ({argopy_diff[0]} -> {argopy_diff[1]})")
    if xarray_diff:
        version_notes.append(f"xarray ({xarray_diff[0]} -> {xarray_diff[1]})")

    if is_same and not version_changed:
        summary = f"Data identical: SHA-256 hash ({card.data_hash[:12]}...) unchanged with {card.row_count} rows and {card.profile_count} profiles."
    elif is_same and version_changed:
        summary = f"Data identical (SHA-256 hash unchanged with {card.row_count} rows), but library versions changed: {', '.join(version_notes)}."
    else:
        parts = [f"Data modified (hash changed from {card.data_hash[:8]}... to {new_hash[:8]}...)."]
        if row_diff != 0:
            parts.append(f"Row count changed by {row_diff:+d} (from {card.row_count} to {new_rows}).")
        if prof_diff != 0:
            parts.append(f"Profile count changed by {prof_diff:+d} (from {card.profile_count} to {new_profs}).")
        if new_profiles:
            parts.append(f"New profiles detected: {len(new_profiles)} (e.g. {new_profiles[:3]}).")
        if missing_profiles:
            parts.append(f"Missing profiles: {len(missing_profiles)} (e.g. {missing_profiles[:3]}).")
        if version_changed:
            parts.append(f"Library versions changed: {', '.join(version_notes)}.")
        summary = " ".join(parts)

    return DiffSummary(
        is_same=is_same,
        old_data_hash=card.data_hash,
        new_data_hash=new_hash,
        old_row_count=card.row_count,
        new_row_count=new_rows,
        row_diff=row_diff,
        old_profile_count=card.profile_count,
        new_profile_count=new_profs,
        profile_diff=prof_diff,
        new_profiles=new_profiles,
        missing_profiles=missing_profiles,
        version_changed=version_changed,
        argopy_version_diff=argopy_diff,
        xarray_version_diff=xarray_diff,
        summary=summary,
    )
