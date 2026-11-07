"""Tests for scientific glossary lookup mechanism with literature attribution (Q8)."""

from pathlib import Path
import pytest

from siqva.glossary import DEFAULT_GLOSSARY_PATH, load_glossary, lookup_glossary


def test_glossary_guide_exists():
    guide_path = Path(__file__).resolve().parent.parent / "docs" / "GLOSSARY_GUIDE.md"
    assert guide_path.exists(), "docs/GLOSSARY_GUIDE.md must exist"
    assert guide_path.stat().st_size > 100


def test_glossary_data_validity_and_citations():
    entries = load_glossary()
    assert len(entries) >= 3
    for entry in entries:
        assert entry.term, "Term must not be empty"
        assert entry.canonical_name, "Canonical name must not be empty"
        assert entry.definition, "Definition must not be empty"
        assert entry.source, "Every glossary entry must cite a scientific source"
        assert len(entry.aliases) > 0, "Every glossary entry must have search aliases"


def test_exact_lookup():
    res = lookup_glossary("MLD")
    assert res.found is True
    assert res.entry is not None
    assert res.entry.term == "MLD"
    assert "de Boyer Montégut" in res.entry.source


def test_alias_lookup():
    res = lookup_glossary("tropical cyclone heat potential")
    assert res.found is True
    assert res.entry is not None
    assert res.entry.term == "TCHP"
    assert "Shay" in res.entry.source


def test_fuzzy_lookup():
    # Minor misspelling "sound channl" -> SOFAR
    res = lookup_glossary("sound channl")
    assert res.found is True
    assert res.entry is not None
    assert res.entry.term == "SOFAR"


def test_unknown_term_returns_suggestions():
    # Close match to MLD ("mlx")
    res = lookup_glossary("mlx")
    assert res.found is False
    assert "MLD" in res.suggestions
    assert "Did you mean" in res.message


def test_completely_unknown_term():
    res = lookup_glossary("superconductivity")
    assert res.found is False
    assert res.entry is None
    assert "not found in oceanographic glossary" in res.message
    assert "docs/GLOSSARY_GUIDE.md" in res.message
