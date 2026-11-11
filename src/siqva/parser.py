"""Hybrid parser: deterministic rules first, constrained LLM fallback for unfilled fields.

Public interface:
    parse(question) -> QuerySpec | ClarificationNeeded
    parse_detailed(question) -> ParseOutcome (includes provenance per field)

Follows AGENTS.md Section 6:
- Hybrid: rules first, LLM only for what rules leave unfilled.
- Swappable LLM backend.
- Validation before returning; retry once if invalid.
- Never guess a region, date range, or QC mode.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from .gazetteer import KNOWN_REGIONS, RegionStatus, resolve_region
from .llm_parser import (
    DEFAULT_MODEL,
    check_llm_availability,
    extract_date_range_llm,
    extract_depth_range_llm,
    extract_intent_llm,
    extract_region_name_llm,
    extract_variables_llm,
)
from .rules_parser import RulesParseResult, parse_rules
from .spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable
from .validator import (
    DEFAULT_MAX_REQUEST_SIZE,
    OversizedRequestError,
    SpecValidationError,
    validate_spec,
    validate_structure,
)

logger = logging.getLogger(__name__)


class ClarificationNeeded(BaseModel):
    """Returned when a query cannot be safely and unambiguously resolved into a QuerySpec."""

    model_config = ConfigDict(frozen=True)

    message: str
    missing_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class UnderstoodQuery(BaseModel):
    """Fields resolved during parsing, including those available before clarification."""

    model_config = ConfigDict(frozen=True)

    region: Optional[BoundingBox] = None
    basin: Optional[str] = None
    region_name: Optional[str] = None
    date_range: Optional[DateRange] = None
    variables: Optional[list[Variable]] = None
    depth_range: Optional[DepthRange] = None
    mode: Optional[DataMode] = None
    intent: Optional[Intent] = None


class ParseOutcome(BaseModel):
    """Comprehensive parse outcome with the resolved spec or clarification, plus field provenance."""

    model_config = ConfigDict(frozen=True)

    spec: Optional[QuerySpec] = None
    clarification: Optional[ClarificationNeeded] = None
    provenance: dict[str, str] = Field(default_factory=dict)
    understood: UnderstoodQuery = Field(default_factory=UnderstoodQuery)

    @property
    def is_success(self) -> bool:
        return self.spec is not None


def parse_detailed(
    question: str,
    today: Optional[date] = None,
    llm_client: Any = None,
    allow_llm: bool = True,
    model: str = DEFAULT_MODEL,
    max_request_size: Optional[float] = DEFAULT_MAX_REQUEST_SIZE,
) -> ParseOutcome:
    """Parse natural language question into QuerySpec with provenance tracking and LLM fallback."""
    provenance: dict[str, str] = {}
    missing_fields: list[str] = []
    ambiguous_fields: list[str] = []
    suggestions: list[str] = []

    # LLM availability state (checked at most once before first fallback)
    llm_checked = False
    llm_available = False

    def can_use_llm() -> bool:
        nonlocal llm_checked, llm_available
        if not allow_llm:
            return False
        if not llm_checked:
            llm_checked = True
            llm_available = check_llm_availability(client=llm_client)
        return llm_available

    # 1. Deterministic rules pass
    rules_res: RulesParseResult = parse_rules(question, today=today)

    for item in rules_res.ambiguous:
        base = item.split()[0].split("(")[0].strip()
        if base and base not in ambiguous_fields:
            ambiguous_fields.append(base)

    # 2. Region resolution
    region: Optional[BoundingBox] = rules_res.region
    region_name: Optional[str] = rules_res.region_name
    region_issue = rules_res.region_resolution
    if region is not None:
        provenance["region"] = "rules"
    elif region_issue is not None:
        if region_issue.status == RegionStatus.AMBIGUOUS:
            ambiguous_fields.append("region")
            candidates = ", ".join(region_issue.candidates)
            suggestions.append(
                f"The region '{region_issue.query}' is ambiguous. Candidates: {candidates}. "
                "Please choose one region or provide coordinates."
            )
        elif region_issue.clarification_request and "too large" in region_issue.clarification_request:
            suggestions.append(region_issue.clarification_request)
        elif region_issue.query.strip().lower() in (
            "pacific",
            "the pacific",
            "pacific ocean",
            "the pacific ocean",
        ):
            suggestions.append(
                "The Pacific Ocean as a whole is too large for one query and crosses the 180° meridian. "
                "Supported Pacific regions: Eastern equatorial Pacific, Nino 3.4, Nino 3, Nino 1+2. "
                "Or provide coordinates like '5S-5N, 170W-120W'."
            )
        else:
            supported = ", ".join(KNOWN_REGIONS)
            suggestions.append(
                f"The mentioned region '{region_issue.query}' is not supported. "
                f"Supported regions: {supported}. Or provide coordinates."
            )
    else:
        # Check if rules captured a candidate name
        if rules_res.region_name:
            res_reg = resolve_region(rules_res.region_name)
            if res_reg.status == RegionStatus.RESOLVED and res_reg.bbox is not None:
                region = res_reg.bbox
                region_name = res_reg.region_name
                provenance["region"] = "rules"

        # Fallback to LLM for region name if still missing
        if region is None and can_use_llm():
            llm_region_name = extract_region_name_llm(question, client=llm_client, model=model)
            if llm_region_name:
                res_reg = resolve_region(llm_region_name)
                if res_reg.status == RegionStatus.RESOLVED and res_reg.bbox is not None:
                    region = res_reg.bbox
                    region_name = res_reg.region_name
                    provenance["region"] = "llm"

        if region is None:
            missing_fields.append("region")
            suggestions.append(
                "No region was mentioned. Please specify an ocean region "
                "(e.g. 'Arabian Sea', 'North Atlantic') or coordinates."
            )

    # 3. Date range resolution
    date_range: Optional[DateRange] = rules_res.date_range
    if date_range is not None:
        provenance["date_range"] = "rules"
    elif "date_range" in ambiguous_fields:
        # Never guess ambiguous relative dates ("March" without year, "recent", "last month")
        suggestions.extend(
            item for item in rules_res.ambiguous if item.startswith("date_range")
        )
        suggestions.append(
            "Date is ambiguous or missing a year. Please specify an exact year or date range (e.g. 'March 2022' or '2022-01-01 to 2022-01-15')."
        )
    else:
        # Fallback to LLM for date range
        if can_use_llm():
            llm_dates = extract_date_range_llm(question, client=llm_client, model=model)
            if llm_dates is not None:
                try:
                    date_range = DateRange(start=llm_dates[0], end=llm_dates[1])
                    provenance["date_range"] = "llm"
                except Exception:
                    date_range = None

        if date_range is None:
            missing_fields.append("date_range")
            suggestions.append("Please specify a time period (e.g. 'in year 2021' or '2022-01-01 to 2022-01-10').")

    # 4. Variables resolution
    variables: Optional[list[Variable]] = rules_res.variables
    if variables:
        provenance["variables"] = "rules"
    elif "variables" in ambiguous_fields:
        suggestions.append(
            "'SST' (Sea Surface Temperature) differs from Argo subsurface temperature profiles (which start at 2–5 dbar). Please confirm if you want Argo subsurface temperature (TEMP)."
        )
    else:
        if can_use_llm():
            llm_vars = extract_variables_llm(question, client=llm_client, model=model)
            if llm_vars:
                variables = llm_vars
                provenance["variables"] = "llm"

        if not variables:
            missing_fields.append("variables")
            suggestions.append("Please specify ocean variables to measure (e.g. 'temperature', 'salinity', 'pressure').")

    # 5. Depth range resolution
    depth_range: Optional[DepthRange] = rules_res.depth_range
    if depth_range is not None:
        provenance["depth_range"] = "rules"
    else:
        if can_use_llm():
            llm_depth = extract_depth_range_llm(question, client=llm_client, model=model)
            if llm_depth is not None:
                depth_range = llm_depth
                provenance["depth_range"] = "llm"

        if depth_range is None:
            # Default to 0-500 dbar when unspecified, as mandated by Section 7/workflow
            depth_range = DepthRange(min_depth=0.0, max_depth=500.0)
            provenance["depth_range"] = "default"

    # 6. Mode resolution (defaults to research; override only on unambiguous phrases)
    mode: DataMode = rules_res.mode
    q_lower = question.lower()
    has_explicit_mode = any(
        phrase in q_lower
        for phrase in [
            "real-time",
            "near real-time",
            "include all data",
            "including unchecked",
            "raw data",
        ]
    )
    provenance["mode"] = "rules" if has_explicit_mode else "default"

    # 7. Intent resolution
    intent: Optional[Intent] = rules_res.intent
    if intent is not None:
        provenance["intent"] = "rules"
    else:
        if can_use_llm():
            llm_intent = extract_intent_llm(question, client=llm_client, model=model)
            if llm_intent is not None:
                intent = llm_intent
                provenance["intent"] = "llm"

        if intent is None:
            intent = Intent.PROFILE
            provenance["intent"] = "default"

    basin = getattr(rules_res, "basin", None)

    # For METADATA intent (Map), no dates or variables required
    if intent == Intent.MAP:
        if date_range is None:
            from datetime import timedelta
            from .floatindex import load_float_index

            idx = load_float_index()
            snap_date = idx.max_date if (idx and idx.is_available and idx.max_date) else date.today()
            date_range = DateRange(start=snap_date - timedelta(days=30), end=snap_date)
            provenance["date_range"] = "default"
            if "date_range" in missing_fields:
                missing_fields.remove("date_range")
        if not variables:
            variables = [Variable.TEMP]
            provenance["variables"] = "default"
            if "variables" in missing_fields:
                missing_fields.remove("variables")
        if region is None and basin:
            region_name = basin
            if "region" in missing_fields:
                missing_fields.remove("region")
            if ambiguous_fields:
                ambiguous_fields = [f for f in ambiguous_fields if "Pacific Ocean" not in f and "crosses the 180" not in f]

    # Surface maps and drift velocity only require surface layer coordinates; default to 0-20 dbar
    if provenance.get("depth_range") == "default" and intent in (Intent.MAP, getattr(Intent, "DRIFT", None)):
        depth_range = DepthRange(min_depth=0.0, max_depth=20.0)

    understood = UnderstoodQuery(
        region=region,
        basin=basin,
        region_name=region_name,
        date_range=date_range,
        variables=variables,
        depth_range=depth_range,
        mode=mode,
        intent=intent,
    )

    # 8. Check for mandatory missing or ambiguous fields
    has_location = (region is not None) or (basin is not None)
    if missing_fields or ambiguous_fields or not has_location or date_range is None or not variables:
        reasons = []
        if llm_checked and not llm_available:
            reasons.append("The language model is not available.")
        if missing_fields:
            reasons.append(f"Missing required fields: {', '.join(missing_fields)}.")
        if ambiguous_fields:
            reasons.append(f"Ambiguous fields requiring confirmation: {', '.join(ambiguous_fields)}.")
        if llm_checked and not llm_available:
            reasons.append("Please specify the missing parameters or fill them in the spec panel.")
            suggestions.append("You can manually configure missing parameters in the spec panel.")
        full_message = " ".join(reasons + suggestions)
        return ParseOutcome(
            spec=None,
            clarification=ClarificationNeeded(
                message=full_message,
                missing_fields=missing_fields,
                ambiguous_fields=ambiguous_fields,
                suggestions=suggestions,
            ),
            provenance=provenance,
            understood=understood,
        )

    # 9. Build candidate spec and validate
    candidate_spec = QuerySpec(
        region=region,
        basin=basin,
        date_range=date_range,
        variables=variables,
        depth_range=depth_range,
        mode=mode,
        intent=intent,
    )

    try:
        if intent == Intent.MAP:
            validate_structure(candidate_spec, allow_antimeridian=True)
        else:
            validate_spec(candidate_spec, max_request_size=max_request_size, allow_chunking=True)
        return ParseOutcome(
            spec=candidate_spec,
            clarification=None,
            provenance=provenance,
            understood=understood,
        )
    except OversizedRequestError as err:
        return ParseOutcome(
            spec=None,
            clarification=ClarificationNeeded(
                message=f"Request exceeds allowable size cap ({err.size:.0f} > {err.max_size:.0f} cost units). {err.suggestion}",
                missing_fields=[],
                ambiguous_fields=[],
                suggestions=[err.suggestion],
            ),
            provenance=provenance,
            understood=understood,
        )
    except SpecValidationError as err:
        # Retry once: check if dates were simply inverted start > end
        if candidate_spec.date_range.start > candidate_spec.date_range.end:
            try:
                fixed_dates = DateRange(
                    start=candidate_spec.date_range.end,
                    end=candidate_spec.date_range.start,
                )
                fixed_spec = candidate_spec.model_copy(update={"date_range": fixed_dates})
                validate_spec(fixed_spec, max_request_size=max_request_size, allow_chunking=True)
                provenance["date_range"] = f"{provenance.get('date_range', 'rules')}_swapped"
                return ParseOutcome(
                    spec=fixed_spec,
                    clarification=None,
                    provenance=provenance,
                    understood=understood.model_copy(update={"date_range": fixed_dates}),
                )
            except Exception:
                pass

        return ParseOutcome(
            spec=None,
            clarification=ClarificationNeeded(
                message=f"Spec validation error: {err}",
                missing_fields=[],
                ambiguous_fields=[],
                suggestions=["Please refine query bounds or date range."],
            ),
            provenance=provenance,
            understood=understood,
        )


def parse(
    question: str,
    today: Optional[date] = None,
    llm_client: Any = None,
    allow_llm: bool = True,
    model: str = DEFAULT_MODEL,
) -> Union[QuerySpec, ClarificationNeeded]:
    """Single public entry point parsing natural language question into QuerySpec or ClarificationNeeded."""
    outcome = parse_detailed(
        question,
        today=today,
        llm_client=llm_client,
        allow_llm=allow_llm,
        model=model,
    )
    if outcome.spec is not None:
        return outcome.spec
    assert outcome.clarification is not None
    return outcome.clarification
