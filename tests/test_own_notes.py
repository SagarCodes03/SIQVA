"""Regression test ensuring knowledge/notes/own_generated.yaml matches code definitions."""

from pathlib import Path
import yaml

from scripts.build_own_notes import OUTPUT_PATH, build_own_notes_data


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
