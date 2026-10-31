"""SIQVA: reproducible, deterministic natural-language Argo query pipeline."""

from .analyzer import (
    AnalysisResult,
    DepthBinStats,
    analyze,
)
from .card import (
    DiffSummary,
    QueryCard,
    build_card,
    generate_script,
    list_cards,
    load_card,
    rerun,
    save_card,
)
from .fetcher import (
    DEFAULT_CACHE_DIR,
    DEFAULT_MAX_PROFILE_COUNT,
    FetchMetadata,
    FetchResult,
    FetchStatus,
    compute_canonical_data_hash,
    fetch,
)
from .gazetteer import (
    KNOWN_REGIONS,
    REGION_ALIASES,
    RegionResolution,
    RegionStatus,
    resolve_region,
)
from .parser import (
    ClarificationNeeded,
    ParseOutcome,
    parse,
    parse_detailed,
)
from .pipeline import (
    PipelineResult,
    PipelineStatus,
    run,
    run_spec,
)
from .qc import (
    QCReport,
    VariableQCStats,
    audit_qc,
    get_mode_description,
    get_qc_filter_description,
)
from .rules_parser import (
    RulesParseResult,
    parse_rules,
)
from .spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)
from .validator import (
    DEFAULT_MAX_REQUEST_SIZE,
    OversizedRequestError,
    SpecValidationError,
    validate_spec,
)

__all__ = [
    "BoundingBox",
    "DataMode",
    "DateRange",
    "DepthRange",
    "Intent",
    "QuerySpec",
    "Variable",
    "DEFAULT_MAX_REQUEST_SIZE",
    "OversizedRequestError",
    "SpecValidationError",
    "validate_spec",
    "KNOWN_REGIONS",
    "REGION_ALIASES",
    "RegionResolution",
    "RegionStatus",
    "resolve_region",
    "RulesParseResult",
    "parse_rules",
    "DEFAULT_CACHE_DIR",
    "DEFAULT_MAX_PROFILE_COUNT",
    "FetchMetadata",
    "FetchResult",
    "FetchStatus",
    "compute_canonical_data_hash",
    "fetch",
    "QCReport",
    "VariableQCStats",
    "audit_qc",
    "get_mode_description",
    "get_qc_filter_description",
    "AnalysisResult",
    "DepthBinStats",
    "analyze",
    "DiffSummary",
    "QueryCard",
    "build_card",
    "generate_script",
    "list_cards",
    "load_card",
    "rerun",
    "save_card",
    "ClarificationNeeded",
    "ParseOutcome",
    "parse",
    "parse_detailed",
    "PipelineResult",
    "PipelineStatus",
    "run",
    "run_spec",
]
