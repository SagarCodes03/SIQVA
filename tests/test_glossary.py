"""Tests for scientific glossary lookup mechanism with literature attribution (Q8 & FIX 2)."""

import json
from pathlib import Path
import pytest

from siqva.glossary import (
    DEFAULT_GLOSSARY_PATH,
    GlossaryEntry,
    GlossarySource,
    load_glossary,
    lookup_glossary,
)


def test_glossary_guide_exists():
    guide_path = Path(__file__).resolve().parent.parent / "docs" / "GLOSSARY_GUIDE.md"
    assert guide_path.exists(), "docs/GLOSSARY_GUIDE.md must exist"
    assert guide_path.stat().st_size > 100
    guide_text = guide_path.read_text(encoding="utf-8")
    assert "verified" in guide_text
    assert "checklist" in guide_text.lower()


def test_glossary_exact_utf8_characters_and_no_mojibake():
    entries = load_glossary()
    assert len(entries) >= 3

    # Verify "de Boyer Montégut"
    mld_entry = next(e for e in entries if e.term == "MLD")
    assert "de Boyer Montégut" in mld_entry.source.author
    assert "MontÃ©gut" not in str(mld_entry.source)
    assert "Montégut" in str(mld_entry.source)

    # Verify "Δ", "°", "³"
    assert "ΔT" in mld_entry.formula
    assert "°C" in mld_entry.formula
    assert "kg/m³" in mld_entry.formula
    assert "Î”" not in mld_entry.formula

    # Verify TCHP formula symbols "ρ", "∫"
    tchp_entry = next(e for e in entries if e.term == "TCHP")
    assert "ρ" in tchp_entry.formula
    assert "∫" in tchp_entry.formula


def test_glossary_sources_have_mandatory_fields():
    entries = load_glossary()
    for entry in entries:
        assert entry.term, "Term must not be empty"
        assert entry.canonical_name, "Canonical name must not be empty"
        assert entry.definition, "Definition must not be empty"
        assert len(entry.aliases) > 0, "Every glossary entry must have search aliases"

        src = entry.source
        assert isinstance(src, GlossarySource)
        assert src.title and src.title.strip(), f"Title missing for {entry.term}"
        assert src.author and src.author.strip(), f"Author missing for {entry.term}"
        assert src.year and str(src.year).strip(), f"Year missing for {entry.term}"
        assert src.url_or_doi and src.url_or_doi.strip(), f"url_or_doi missing for {entry.term}"


def test_unverified_flag_returns_unverified_message():
    # Currently MLD, TCHP, SOFAR have verified=False in data/glossary.json
    res = lookup_glossary("MLD")
    assert res.found is True
    assert res.term_name == "MLD"
    assert res.entry is None, "Must not return unverified definition as fact"
    assert res.definition is None
    assert "I do not have a verified definition for that term yet" in res.message
    assert res.source_citation is not None
    assert "de Boyer Montégut" in res.source_citation


def test_verified_term_in_fixture_returns_definition(tmp_path):
    fixture_data = {
        "terms": [
            {
                "term": "MLD",
                "canonical_name": "Mixed Layer Depth",
                "definition": "The depth below the ocean surface where density increases by 0.03 kg/m3.",
                "source": {
                    "author": "de Boyer Montégut et al.",
                    "year": 2004,
                    "title": "Mixed layer depth over the global ocean",
                    "journal": "JGR Oceans",
                    "url_or_doi": "https://doi.org/10.1029/2004JC002378",
                },
                "formula": "Δσθ = 0.03 kg/m³",
                "aliases": ["mld", "mixed layer"],
                "verified": True,
            }
        ]
    }
    fixture_file = tmp_path / "glossary.json"
    fixture_file.write_text(json.dumps(fixture_data), encoding="utf-8")

    res = lookup_glossary("MLD", glossary_path=fixture_file)
    assert res.found is True
    assert res.term_name == "MLD"
    assert res.entry is not None
    assert res.entry.verified is True
    assert res.definition == "The depth below the ocean surface where density increases by 0.03 kg/m3."
    assert "Found verified definition" in res.message


def test_alias_and_fuzzy_resolution_with_verified_fixture(tmp_path):
    fixture_data = {
        "terms": [
            {
                "term": "SOFAR",
                "canonical_name": "SOFAR Channel Axis",
                "definition": "Sound Fixing and Ranging channel minimum sound speed depth.",
                "source": {
                    "author": "Ewing & Worzel",
                    "year": 1948,
                    "title": "Long-range sound transmission",
                    "url_or_doi": "https://doi.org/10.1130/MEM27-p1",
                },
                "aliases": ["sofar", "sound channel", "deep sound channel"],
                "verified": True,
            }
        ]
    }
    fixture_file = tmp_path / "glossary.json"
    fixture_file.write_text(json.dumps(fixture_data), encoding="utf-8")

    # Alias lookup
    res_alias = lookup_glossary("sound channel", glossary_path=fixture_file)
    assert res_alias.found is True
    assert res_alias.entry.term == "SOFAR"

    # Fuzzy lookup with slight typo
    res_fuzzy = lookup_glossary("sound channl", glossary_path=fixture_file)
    assert res_fuzzy.found is True
    assert res_fuzzy.entry.term == "SOFAR"


def test_unknown_term_returns_do_not_have_message_and_suggestions():
    # Close match to MLD ("mlx")
    res = lookup_glossary("mlx")
    assert res.found is False
    assert "I do not have that term" in res.message
    assert "MLD" in res.suggestions
    assert "Did you mean" in res.message
    assert "Available terms" in res.message


def test_completely_unknown_term_does_not_invent_definition():
    # "what is a barrier layer" is not currently in data/glossary.json
    res = lookup_glossary("what is a barrier layer")
    assert res.found is False
    assert res.entry is None
    assert res.definition is None
    assert "I do not have that term" in res.message
    assert "Available terms:" in res.message
    assert "MLD" in res.message
    assert "docs/GLOSSARY_GUIDE.md" in res.message

    # Another completely unrelated term
    res2 = lookup_glossary("superconductivity")
    assert res2.found is False
    assert res2.entry is None
    assert "I do not have that term" in res2.message
