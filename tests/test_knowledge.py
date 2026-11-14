"""
Unit tests for SIQVA Knowledge Base integrity and validation checks.
Tests operate strictly offline without external network access.
"""

from pathlib import Path
import pytest
from scripts.check_knowledge import (
    check_knowledge_base,
    count_sentences,
    find_quotations,
    validate_manifest,
    validate_notes,
    validate_questions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_knowledge_base_clean():
    """Verify that current repo knowledge base passes all validation checks."""
    errors = check_knowledge_base(REPO_ROOT)
    assert errors == [], f"Knowledge base checks failed with errors:\n" + "\n".join(errors)


def test_sentence_counter_handles_abbreviations():
    """Verify sentence counting handles abbreviations and decimal numbers properly."""
    text = (
        "Argo floats drift at 1000 dbar for approx. 9 days (e.g. standard cycle). "
        "Then they descend to 2000.5 meters and rise. "
        "Data are relayed within 24 hours."
    )
    assert count_sentences(text) == 3


def test_quotation_extractor():
    """Verify quotation extraction handles standard and curly quotes."""
    text = 'The flag is "good data" and mode is “research”.'
    quotes = find_quotations(text)
    assert quotes == ["good data", "research"]


def test_verified_true_rejection(tmp_path):
    """Verify that document notes with verified: true are strictly rejected."""
    notes_dir = tmp_path / "notes"
    notes_dir.mkdir()
    bad_note_yaml = notes_dir / "bad_note.yaml"
    bad_note_yaml.write_text(
        """
- id: test-note
  question_examples: ["Test?"]
  answer: "First sentence here. Second sentence here."
  source_id: argo-home
  section_or_page: "Home"
  source_version: ""
  limits: "None"
  related: []
  verified: true
  checked_on: "2026-11-14"
""",
        encoding="utf-8",
    )
    manifest_sources = {"argo-home": {"id": "argo-home"}}
    _, errors = validate_notes(notes_dir, manifest_sources)
    assert any("verified: true" in err or "'verified' is set to True" in err for err in errors)


def test_question_unknown_note_rejection(tmp_path):
    """Verify questions referencing non-existent note IDs fail validation."""
    questions_file = tmp_path / "questions.jsonl"
    questions_file.write_text(
        '{"id": "q1", "question": "test", "type": "knowledge", "split": "dev", '
        '"expected_note_ids": ["non-existent-note-id"], "expected_facts": [], '
        '"expected_behavior": "test", "needs_review": true}\n',
        encoding="utf-8",
    )
    errors = validate_questions(questions_file, valid_note_ids={"argo-one-paragraph"})
    assert any("non-existent-note-id" in err for err in errors)
