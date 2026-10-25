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

from .gazetteer import RegionStatus, resolve_region
from .llm_parser import (
    DEFAULT_MODEL,
    extract_date_range_llm,
    extract_depth_range_llm,
    extract_intent_llm,
    extract_region_name_llm,
    extract_variables_llm,
)
from .rules_parser import RulesParseResult, parse_rules
from .spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable
from .validator import OversizedRequestError, SpecValidationError, validate_spec

logger = logging.getLogger(__name__)


class ClarificationNeeded(BaseModel):
    """Returned when a query cannot be safely and unambiguously resolved into a QuerySpec."""

    model_config = ConfigDict(frozen=True)

    message: str
    missing_fields: list[str] = Field(default_factory=list)
    ambiguous_fields: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ParseOutcome(BaseModel):
    """Comprehensive parse outcome with the resolved spec or clarification, plus field provenance."""

    model_config = ConfigDict(frozen=True)

    spec: Optional[QuerySpec] = None
    clarification: Optional[ClarificationNeeded] = None
    provenance: dict[str, str] = Field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.spec is not None


def parse_detailed(
    question: str,
    today: Optional[date] = None,
    llm_client: Any = None,
    allow_llm: bool = True,
    model: str = DEFAULT_MODEL,
) -> ParseOutcome:
    """Parse natural language question into QuerySpec with provenance tracking and LLM fallback."""
    provenance: dict[str, str] = {}
    missing_fields: list[str] = []
    ambiguous_fields: list[str] = []
    suggestions: list[str] = []

    # 1. Deterministic rules pass
    rules_res: RulesParseResult = parse_rules(question, today=today)

    for item in rules_res.ambiguous:
        base = item.split()[0].split("(")[0].strip()
        if base and base not in ambiguous_fields:
            ambiguous_fields.append(base)

    # 2. Region resolution
    region: Optional[BoundingBox] = rules_res.region
    if region is not None:
        provenance["region"] = "rules"
    else:
        # Check if rules captured a candidate name
        if rules_res.region_name:
            res_reg = resolve_region(rules_res.region_name)
            if res_reg.status == RegionStatus.RESOLVED and res_reg.bbox is not None:
                region = res_reg.bbox
                provenance["region"] = "rules"

        # Fallback to LLM for region name if still missing
        if region is None and allow_llm:
            llm_region_name = extract_region_name_llm(question, client=llm_client, model=model)
            if llm_region_name:
                res_reg = resolve_region(llm_region_name)
                if res_reg.status == RegionStatus.RESOLVED and res_reg.bbox is not None:
                    region = res_reg.bbox
                    provenance["region"] = "llm"

        if region is None:
            missing_fields.append("region")
            suggestions.append("Please specify an ocean region (e.g. 'Arabian Sea', 'North Atlantic') or coordinates.")

    # 3. Date range resolution
    date_range: Optional[DateRange] = rules_res.date_range
    if date_range is not None:
        provenance["date_range"] = "rules"
    elif "date_range" in ambiguous_fields:
        # Never guess ambiguous relative dates ("March" without year, "recent", "last month")
        suggestions.append(
            "Date is ambiguous or missing a year. Please specify an exact year or date range (e.g. 'March 2022' or '2022-01-01 to 2022-01-15')."
        )
    else:
        # Fallback to LLM for date range
        if allow_llm:
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
        if allow_llm:
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
        if allow_llm:
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
        if allow_llm:
            llm_intent = extract_intent_llm(question, client=llm_client, model=model)
            if llm_intent is not None:
                intent = llm_intent
                provenance["intent"] = "llm"

        if intent is None:
            intent = Intent.PROFILE
            provenance["intent"] = "default"

    # 8. Check for mandatory missing or ambiguous fields
    if missing_fields or ambiguous_fields or region is None or date_range is None or not variables:
        reasons = []
        if missing_fields:
            reasons.append(f"Missing required fields: {', '.join(missing_fields)}.")
        if ambiguous_fields:
            reasons.append(f"Ambiguous fields requiring confirmation: {', '.join(ambiguous_fields)}.")
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
        )

    # 9. Build candidate spec and validate
    candidate_spec = QuerySpec(
        region=region,
        date_range=date_range,
        variables=variables,
        depth_range=depth_range,
        mode=mode,
        intent=intent,
    )

    try:
        validate_spec(candidate_spec)
        return ParseOutcome(spec=candidate_spec, clarification=None, provenance=provenance)
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
                validate_spec(fixed_spec)
                provenance["date_range"] = f"{provenance.get('date_range', 'rules')}_swapped"
                return ParseOutcome(spec=fixed_spec, clarification=None, provenance=provenance)
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
