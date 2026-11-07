"""Scientific oceanographic glossary lookup mechanism with literature attribution (Q8)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GLOSSARY_PATH = PROJECT_ROOT / "data" / "glossary.json"


class GlossaryEntry(BaseModel):
    """Scientific definition of an oceanographic term with source literature attribution."""

    model_config = ConfigDict(frozen=True)

    term: str
    canonical_name: str
    definition: str
    source: str
    formula: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)


class GlossarySearchResult(BaseModel):
    """Result of searching the oceanographic glossary."""

    model_config = ConfigDict(frozen=True)

    found: bool
    entry: Optional[GlossaryEntry] = None
    suggestions: list[str] = Field(default_factory=list)
    message: str


def load_glossary(glossary_path: Optional[Path | str] = None) -> list[GlossaryEntry]:
    """Load verified glossary entries from JSON store."""
    path = Path(glossary_path) if glossary_path is not None else DEFAULT_GLOSSARY_PATH
    if not path.is_absolute():
        path = PROJECT_ROOT / path

    if not path.exists():
        logger.warning("Glossary file not found at %s", path)
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        terms_data = data.get("terms", [])
        return [GlossaryEntry(**t) for t in terms_data]
    except Exception as err:
        logger.error("Failed loading glossary from %s: %s", path, err)
        return []


def lookup_glossary(query: str, glossary_path: Optional[Path | str] = None) -> GlossarySearchResult:
    """Look up an oceanographic term via exact key, alias list, and fuzzy matching."""
    entries = load_glossary(glossary_path=glossary_path)
    if not entries:
        return GlossarySearchResult(
            found=False,
            entry=None,
            suggestions=[],
            message="Glossary is empty or could not be loaded. See docs/GLOSSARY_GUIDE.md to add entries.",
        )

    q_clean = query.strip().lower()

    # 1. Exact term or alias match
    for entry in entries:
        if q_clean == entry.term.lower() or q_clean == entry.canonical_name.lower():
            return GlossarySearchResult(
                found=True,
                entry=entry,
                suggestions=[],
                message=f"Found exact definition for '{entry.term}'.",
            )
        for alias in entry.aliases:
            if q_clean == alias.lower():
                return GlossarySearchResult(
                    found=True,
                    entry=entry,
                    suggestions=[],
                    message=f"Found definition for '{entry.term}' matching alias '{alias}'.",
                )

    # 2. Fuzzy match against term, canonical name, and aliases
    candidates_map: dict[str, GlossaryEntry] = {}
    for entry in entries:
        candidates_map[entry.term] = entry
        candidates_map[entry.canonical_name] = entry
        for alias in entry.aliases:
            candidates_map[alias] = entry

    candidate_strings = list(candidates_map.keys())
    match = process.extractOne(
        q_clean,
        candidate_strings,
        scorer=fuzz.WRatio,
        score_cutoff=80.0,
    )

    if match:
        matched_str, score, _ = match
        matched_entry = candidates_map[matched_str]
        return GlossarySearchResult(
            found=True,
            entry=matched_entry,
            suggestions=[],
            message=f"Found definition for '{matched_entry.term}' (fuzzy match with '{matched_str}', score {score:.0f}).",
        )

    # 3. Partial / suggestion search
    close_matches = process.extract(
        q_clean,
        candidate_strings,
        scorer=fuzz.WRatio,
        score_cutoff=55.0,
        limit=3,
    )
    if close_matches:
        suggested_terms = list(dict.fromkeys(candidates_map[m[0]].term for m in close_matches))
        return GlossarySearchResult(
            found=False,
            entry=None,
            suggestions=suggested_terms,
            message=(
                f"Term '{query}' not found in glossary. Did you mean: "
                f"{', '.join(repr(s) for s in suggested_terms)}? "
                "See docs/GLOSSARY_GUIDE.md to add verified definitions."
            ),
        )

    available = ", ".join(repr(e.term) for e in entries)
    return GlossarySearchResult(
        found=False,
        entry=None,
        suggestions=[],
        message=(
            f"Term '{query}' not found in oceanographic glossary. "
            f"Available terms: {available}. See docs/GLOSSARY_GUIDE.md to add verified scientific definitions."
        ),
    )
