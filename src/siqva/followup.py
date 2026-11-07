"""Conversational follow-up and session state for SIQVA (Q7).

Implements ConversationState tracking and an edit layer allowing users to
say things like "same for salinity", "now 2023", "do it for Bay of Bengal".
Meta questions answered from session context. The LLM is never called here.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .spec import DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable


class ConversationState(BaseModel):
    """Minimal conversation context for follow-up resolution."""

    model_config = ConfigDict(frozen=True)

    last_spec: Optional[QuerySpec] = None
    last_question: Optional[str] = None
    turn_count: int = 0

    def with_new_query(self, spec: QuerySpec, question: Optional[str] = None) -> "ConversationState":
        """Return updated state after a successful data query."""
        return self.model_copy(update={
            "last_spec": spec,
            "last_question": question,
            "turn_count": self.turn_count + 1,
        })


# Patterns for conversational edits
_VARIABLE_SWAP_PATTERNS = [
    (re.compile(r"\b(?:same\s+for|do\s+it\s+for|now\s+for|what\s+about|how\s+about)\s+salinity\b", re.IGNORECASE), Variable.PSAL),
    (re.compile(r"\b(?:same\s+for|do\s+it\s+for|now\s+for|what\s+about|how\s+about)\s+temperature\b", re.IGNORECASE), Variable.TEMP),
    (re.compile(r"\b(?:same\s+for|do\s+it\s+for|now\s+for|what\s+about|how\s+about)\s+pressure\b", re.IGNORECASE), Variable.PRES),
]

_YEAR_SWAP_PATTERN = re.compile(
    r"\b(?:now|do\s+it\s+for|do\s+it|change\s+to|use|switch\s+to)\s+(?:year\s+)?(\d{4})\b",
    re.IGNORECASE,
)
_REGION_SWAP_PATTERN = re.compile(
    r"\b(?:do\s+it\s+for|same\s+for|now\s+for|now\s+in|switch\s+to|change\s+to|what\s+about|how\s+about)\s+([A-Za-z\s]+?)(?:\s+now|\s+in\s+\d{4}|\s+for\s+\d{4}|$)",
    re.IGNORECASE,
)


class FollowUpResult(BaseModel):
    """Result of attempting to resolve a follow-up against the conversation state."""

    model_config = ConfigDict(frozen=True)

    resolved: bool
    spec: Optional[QuerySpec] = None
    edit_summary: Optional[str] = None
    failure_reason: Optional[str] = None


def try_resolve_followup(
    question: str,
    state: ConversationState,
) -> FollowUpResult:
    """Attempt to interpret `question` as a conversational edit of the last spec.

    Rules applied in order (all deterministic, no LLM):
    1. Variable swap: "same for salinity", "now for temperature"
    2. Year swap: "now 2023", "do it for 2021"
    3. Region swap: "do it for Bay of Bengal", "same for Arabian Sea"

    Returns a FollowUpResult. If `resolved=False`, the question is not a follow-up
    and should be routed as a fresh query.
    """
    if state.last_spec is None:
        return FollowUpResult(
            resolved=False,
            failure_reason="No previous query to reference as follow-up context.",
        )

    spec = state.last_spec
    edits_applied: list[str] = []

    # 1. Variable swap
    new_variables = None
    for pattern, target_var in _VARIABLE_SWAP_PATTERNS:
        if pattern.search(question):
            new_variables = [target_var]
            edits_applied.append(f"variable → {target_var.value}")
            break

    # 2. Year swap
    new_date_range = None
    year_match = _YEAR_SWAP_PATTERN.search(question)
    if year_match:
        year = int(year_match.group(1))
        import calendar as cal_mod
        new_date_range = DateRange(
            start=__import__("datetime").date(year, 1, 1),
            end=__import__("datetime").date(year, 12, 31),
        )
        edits_applied.append(f"date_range → {year}-01-01 to {year}-12-31")

    # 3. Region swap
    new_region = None
    region_match = _REGION_SWAP_PATTERN.search(question)
    if region_match:
        from .gazetteer import RegionStatus, resolve_region

        region_name = region_match.group(1).strip()
        res = resolve_region(region_name)
        if res.status == RegionStatus.RESOLVED and res.bbox is not None:
            new_region = res.bbox
            edits_applied.append(f"region → {region_name}")

    if not edits_applied:
        return FollowUpResult(
            resolved=False,
            failure_reason="No follow-up edits recognised in the question.",
        )

    # Apply all discovered edits
    update_dict: dict[str, Any] = {}
    if new_variables is not None:
        update_dict["variables"] = new_variables
    if new_date_range is not None:
        update_dict["date_range"] = new_date_range
    if new_region is not None:
        update_dict["region"] = new_region

    edited_spec = spec.model_copy(update=update_dict)
    edit_summary = f"Follow-up applied: {'; '.join(edits_applied)}"

    return FollowUpResult(
        resolved=True,
        spec=edited_spec,
        edit_summary=edit_summary,
    )
