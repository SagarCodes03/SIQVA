"""Scientific oceanographic glossary lookup mechanism with literature attribution (Q8)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GLOSSARY_PATH = PROJECT_ROOT / "data" / "glossary.json"


class GlossarySource(BaseModel):
    """Primary literature source citation."""

    model_config = ConfigDict(frozen=True)

    title: str
    author: str
    year: int | str
    url_or_doi: str
    journal: Optional[str] = None

    def __contains__(self, item: str) -> bool:
        return item.lower() in str(self).lower()

    def __str__(self) -> str:
        j = f", {self.journal}" if self.journal else ""
        return f"{self.author} ({self.year}), {self.title}{j}, {self.url_or_doi}".strip(", ")


class GlossaryEntry(BaseModel):
    """Scientific definition of an oceanographic term with source literature attribution."""

    model_config = ConfigDict(frozen=True)

    term: str
    canonical_name: str
    definition: str
    source: GlossarySource
    formula: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    verified: bool = False

    @field_validator("source", mode="before")
    @classmethod
    def parse_source(cls, v: Any) -> Any:
        if isinstance(v, GlossarySource):
            return v
        if isinstance(v, dict):
            return GlossarySource(**v)
        if isinstance(v, str):
            return GlossarySource(
                title=v,
                author=v,
                year="",
                url_or_doi="",
            )
        return v


class GlossarySearchResult(BaseModel):
    """Result of searching the oceanographic glossary."""

    model_config = ConfigDict(frozen=True)

    found: bool
    term_name: Optional[str] = None
    entry: Optional[GlossaryEntry] = None
    definition: Optional[str] = None
    source_citation: Optional[str] = None
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
    q_target = re.sub(r"^(what\s+is\s+(an?|the)?|define|explain|meaning\s+of)\s+", "", q_clean).strip()
    if not q_target:
        q_target = q_clean

    def _format_result(entry: GlossaryEntry, match_info: str) -> GlossarySearchResult:
        if not entry.verified:
            return GlossarySearchResult(
                found=True,
                term_name=entry.term,
                entry=None,
                definition=None,
                source_citation=str(entry.source) if entry.source else None,
                suggestions=[],
                message="I do not have a verified definition for that term yet",
            )
        return GlossarySearchResult(
            found=True,
            term_name=entry.term,
            entry=entry,
            definition=entry.definition,
            source_citation=str(entry.source) if entry.source else None,
            suggestions=[],
            message=f"Found verified definition for '{entry.term}' ({match_info}).",
        )

    # 1. Exact term or alias match
    for target in [q_target, q_clean]:
        for entry in entries:
            if target == entry.term.lower() or target == entry.canonical_name.lower():
                return _format_result(entry, "exact match")
            for alias in entry.aliases:
                if target == alias.lower():
                    return _format_result(entry, f"matching alias '{alias}'")

    # 2. Fuzzy match against term, canonical name, and aliases
    candidates_map: dict[str, GlossaryEntry] = {}
    for entry in entries:
        candidates_map[entry.term] = entry
        candidates_map[entry.canonical_name] = entry
        for alias in entry.aliases:
            candidates_map[alias] = entry

    candidate_strings = list(candidates_map.keys())
    match = process.extractOne(
        q_target,
        candidate_strings,
        scorer=fuzz.WRatio,
        score_cutoff=80.0,
    )

    if match:
        matched_str, score, _ = match
        matched_entry = candidates_map[matched_str]
        return _format_result(matched_entry, f"fuzzy match with '{matched_str}', score {score:.0f}")

    # 3. Partial / suggestion search
    close_matches = process.extract(
        q_target,
        candidate_strings,
        scorer=fuzz.WRatio,
        score_cutoff=55.0,
        limit=3,
    )
    available = ", ".join(repr(e.term) for e in entries)
    if close_matches:
        suggested_terms = list(dict.fromkeys(candidates_map[m[0]].term for m in close_matches))
        return GlossarySearchResult(
            found=False,
            entry=None,
            suggestions=suggested_terms,
            message=(
                f"I do not have that term. Did you mean: "
                f"{', '.join(repr(s) for s in suggested_terms)}? "
                f"Available terms: {available}. "
                "See docs/GLOSSARY_GUIDE.md to add verified definitions."
            ),
        )

    return GlossarySearchResult(
        found=False,
        entry=None,
        suggestions=[],
        message=(
            f"I do not have that term. "
            f"Available terms: {available}. See docs/GLOSSARY_GUIDE.md to add verified scientific definitions."
        ),
    )
