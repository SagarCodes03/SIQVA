"""Regression test ensuring knowledge/notes/own_generated.yaml matches code definitions."""

from pathlib import Path
import yaml

from scripts.build_own_notes import OUTPUT_PATH, build_own_notes_data
from scripts.build_own_sentences import (
    OUTPUT_PATH as SENTENCES_OUTPUT_PATH,
    build_own_sentences_data,
)


def test_own_notes_matches_code():
    """Verify committed own_generated.yaml exactly matches live code definitions."""
    assert OUTPUT_PATH.exists(), f"Missing generated notes: {OUTPUT_PATH}"

    # Load committed file data
    committed_raw = OUTPUT_PATH.read_text(encoding="utf-8")
    committed_data = yaml.safe_load(committed_raw)

    # Re-generate from live code
    fresh_data = build_own_notes_data()

    # Compare structured dictionaries
    assert committed_data == fresh_data, (
        "knowledge/notes/own_generated.yaml is out of date with source code definitions. "
        "Run 'python scripts/build_own_notes.py' to regenerate."
    )


def test_own_notes_origins_are_generated():
    """Verify every top-level section in own_generated.yaml specifies origin: generated."""
    data = build_own_notes_data()
    for section_name, section in data.items():
        if isinstance(section, dict):
            assert section.get("origin") == "generated", f"Section '{section_name}' missing origin: generated"
            assert "source_code_path" in section, f"Section '{section_name}' missing source_code_path"


def test_generated_sample_label_matches_code_constant():
    """Verify that generated sample label equals the label constant defined in code."""
    from siqva.analyzer import FULL_LABEL_TEMPLATE, SAMPLE_LABEL_TEMPLATE
    from siqva.spec import DataMode, QuerySpec

    data = build_own_notes_data()
    sampling_config = data["sampling"]["config"]
    assert sampling_config["sample_label_template"] == SAMPLE_LABEL_TEMPLATE
    assert sampling_config["full_label_template"] == FULL_LABEL_TEMPLATE

    # Verify default mode equals spec default
    data_modes = data["data_modes"]
    assert data_modes["default_mode"] == QuerySpec.model_fields["mode"].default.value
    assert data_modes["default_mode"] == DataMode.RESEARCH.value
    assert "standard" in data_modes["argopy_default_mode_note"]


def test_own_sentences_matches_code():
    """Verify committed own_sentences.yaml exactly matches live code definitions."""
    assert SENTENCES_OUTPUT_PATH.exists(), f"Missing generated notes: {SENTENCES_OUTPUT_PATH}"

    committed_raw = SENTENCES_OUTPUT_PATH.read_text(encoding="utf-8")
    committed_data = yaml.safe_load(committed_raw)

    fresh_data = build_own_sentences_data()

    assert committed_data == fresh_data, (
        "knowledge/notes/own_sentences.yaml is out of date with source code definitions. "
        "Run 'python scripts/build_own_sentences.py' to regenerate."
    )


def test_own_sentences_metadata_and_developer_fields():
    """Verify own_sentences.yaml has origin: code and leaves personal developer fields empty for owner."""
    data = build_own_sentences_data()
    metadata = data.get("metadata", {})
    assert metadata.get("origin") == "code"
    assert metadata.get("developer_name") == ""
    assert metadata.get("developer_affiliation") == ""
    assert metadata.get("developer_email") == ""


def test_own_sentences_notes_and_code_constants():
    """Verify all 9 topics exist in own_sentences.yaml and contain imported code constants."""
    from siqva.chunking import DEFAULT_MAX_CHUNKS, DEFAULT_MAX_TOTAL_ROWS
    from siqva.floatindex import SAMPLE_DEFAULT, SAMPLE_MAX
    from siqva.planner import DEFAULT_MAX_FULL_ROWS
    from siqva.validator import DEFAULT_MAX_REQUEST_SIZE, MAX_DEPTH_DBAR

    data = build_own_sentences_data()
    notes = {n["id"]: n for n in data["notes"]}

    expected_ids = [
        "siqva-sample-explanation",
        "siqva-understood-as-depth",
        "siqva-qc-data-modes",
        "siqva-delayed-mode-timing",
        "siqva-data-sources-caching",
        "siqva-reproduce-query-card",
        "siqva-llm-data-privacy",
        "siqva-known-limits",
        "siqva-plan-decisions-refusal",
    ]
    for eid in expected_ids:
        assert eid in notes, f"Missing expected sentence note: {eid}"
        assert notes[eid]["origin"] == "code"
        assert len(notes[eid]["question_examples"]) >= 2
        assert len(notes[eid]["answer"]) > 50

    # Check imported numbers are in text
    sample_ans = notes["siqva-sample-explanation"]["answer"]
    assert str(SAMPLE_DEFAULT) in sample_ans
    assert str(SAMPLE_MAX) in sample_ans

    depth_ans = notes["siqva-understood-as-depth"]["answer"]
    assert "0 to 500 dbar" in depth_ans
    assert str(int(MAX_DEPTH_DBAR)) in depth_ans

    plan_ans = notes["siqva-plan-decisions-refusal"]["answer"]
    assert f"{DEFAULT_MAX_FULL_ROWS:,}" in plan_ans
    assert f"{int(DEFAULT_MAX_REQUEST_SIZE):,}" in plan_ans
    assert str(DEFAULT_MAX_CHUNKS) in plan_ans
    assert f"{DEFAULT_MAX_TOTAL_ROWS:,}" in plan_ans

    privacy_ans = notes["siqva-llm-data-privacy"]["answer"]
    assert "never sees oceanographic data" in privacy_ans
