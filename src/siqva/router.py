"""Deterministic query intent router classifying questions into specialized handlers (Q6).

Routes inputs to:
- DATA_FETCH: Standard Argo visual query (profiles, maps, TS diagrams, physics).
- OPERATION: Deterministic numerical statistical calculations (mean, min, max, count).
- COMPARISON: Dual-entity comparison across regions or time periods.
- GLOSSARY: Oceanographic concept definitions.
- META: Session, history, library version, or script queries.
- CLARIFICATION: Ambiguous or unsupported requests.
"""

from __future__ import annotations

from enum import Enum
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from .glossary import load_glossary


class RouteTarget(str, Enum):
    """Destination subsystem handling the user input."""

    DATA_FETCH = "data_fetch"
    OPERATION = "operation"
    COMPARISON = "comparison"
    GLOSSARY = "glossary"
    META = "meta"
    CLARIFICATION = "clarification"


class RouteResult(BaseModel):
    """Routing classification outcome."""

    model_config = ConfigDict(frozen=True)

    target: RouteTarget
    confidence: float = 1.0
    extracted_entity: Optional[str] = None
    provenance: str = "rules"
    reason: str = ""


# Regular expressions for deterministic rules-first classification
GLOSSARY_PATTERNS = [
    re.compile(r"^\s*(?:what\s+is|what\s+are|define|explain|meaning\s+of|definition\s+of)\s+([a-zA-Z0-9_\-\s\+]+)\??$", re.IGNORECASE),
    re.compile(r"^\s*(?:tell\s+me\s+about)\s+([a-zA-Z0-9_\-\s\+]+)\??$", re.IGNORECASE),
]

META_PATTERNS = [
    re.compile(r"\b(?:what\s+(?:query\s+)?did\s+i\s+(?:just\s+)?run|what\s+was\s+the\s+last\s+query)\b", re.IGNORECASE),
    re.compile(r"\b(?:show\s+(?:me\s+)?(?:the\s+)?(?:script|card|versions?|spec))\b", re.IGNORECASE),
    re.compile(r"\b(?:which|what)\s+version\b", re.IGNORECASE),
    re.compile(r"\b(?:what\s+mode\s+was\s+used|how\s+many\s+profiles\s+in\s+last\s+query)\b", re.IGNORECASE),
]

COMPARISON_PATTERNS = [
    re.compile(r"\b(?:compare|comparison\s+between|difference\s+between)\b", re.IGNORECASE),
    re.compile(r"\b(?:versus|\bvs\.?\b)\b", re.IGNORECASE),
]

OPERATION_PATTERNS = [
    re.compile(r"\b(?:what\s+is\s+the\s+(?:average|mean|max|maximum|min|minimum|median|std|count))\b", re.IGNORECASE),
    re.compile(r"\b(?:calculate|compute)\s+(?:the\s+)?(?:mean|average|max|maximum|min|minimum|median|std|count)\b", re.IGNORECASE),
    re.compile(r"\b(?:how\s+(?:warm|cold|salty|deep|many))\b", re.IGNORECASE),
    re.compile(r"\b(?:average|mean)\s+(?:temperature|salinity|pressure)\b", re.IGNORECASE),
    re.compile(r"\b(?:max|maximum|min|minimum)\s+(?:temperature|salinity|pressure)\b", re.IGNORECASE),
]


def route(question: str, glossary_path: Optional[str] = None) -> RouteResult:
    """Classify user question into specialized subsystem target. Rules-first."""
    q_clean = question.strip()
    if not q_clean:
        return RouteResult(
            target=RouteTarget.CLARIFICATION,
            confidence=1.0,
            provenance="rules",
            reason="Empty query string.",
        )

    # 1. Meta check
    for pat in META_PATTERNS:
        if pat.search(q_clean):
            return RouteResult(
                target=RouteTarget.META,
                confidence=1.0,
                provenance="rules",
                reason=f"Matched meta query pattern: {pat.pattern}",
            )

    # 2. Glossary check (phrased question or bare acronym)
    for pat in GLOSSARY_PATTERNS:
        m = pat.match(q_clean)
        if m:
            candidate = m.group(1).strip()
            # Do not classify "what is the temperature in Arabian Sea" as glossary!
            if not any(k in candidate.lower() for k in ["temperature", "salinity", "arabian", "bay of bengal", "indian ocean"]):
                return RouteResult(
                    target=RouteTarget.GLOSSARY,
                    confidence=0.95,
                    extracted_entity=candidate,
                    provenance="rules",
                    reason=f"Matched glossary phrasing for '{candidate}'",
                )

    # Check bare glossary terms
    entries = load_glossary(glossary_path=glossary_path)
    known_terms = {e.term.lower() for e in entries} | {a.lower() for e in entries for a in e.aliases}
    if q_clean.lower() in known_terms:
        return RouteResult(
            target=RouteTarget.GLOSSARY,
            confidence=1.0,
            extracted_entity=q_clean,
            provenance="rules",
            reason="Exact match with known glossary acronym/alias",
        )

    # 3. Comparison check
    for pat in COMPARISON_PATTERNS:
        if pat.search(q_clean):
            return RouteResult(
                target=RouteTarget.COMPARISON,
                confidence=0.9,
                provenance="rules",
                reason=f"Matched comparison pattern: {pat.pattern}",
            )

    # 4. Operation check
    for pat in OPERATION_PATTERNS:
        if pat.search(q_clean):
            return RouteResult(
                target=RouteTarget.OPERATION,
                confidence=0.9,
                provenance="rules",
                reason=f"Matched numerical operation pattern: {pat.pattern}",
            )

    # 5. Default to DATA_FETCH
    return RouteResult(
        target=RouteTarget.DATA_FETCH,
        confidence=0.8,
        provenance="rules",
        reason="Defaulted to standard Argo data visualization query",
    )
