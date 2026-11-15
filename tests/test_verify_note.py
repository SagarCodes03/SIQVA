"""
Tests for knowledge verification tooling and workflows (scripts/verify_note.py).

Uses temporary copies of YAML, JSON, manifest, and evidence files to verify:
1. --list table generation.
2. Single note verification with prompt matching and mismatch rejection.
3. Batch --ids verification with exact phrase requirement, unknown ID rejection,
   missing evidence rejection, and wildcard rejection.
4. Text-preserving edits preserving comments, ordering, and byte-identity of other entries.
5. --unverify functionality.
6. Validation enforcement in scripts/check_knowledge.py.
7. knowledge.answer verified vs unverified behavior.
"""

from __future__ import annotations

import datetime
import io
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.check_knowledge import check_knowledge
from scripts.verify_note import (
    apply_batch_verification,
    discover_entries,
    edit_entry_in_file,
    edit_json_glossary_term,
    edit_yaml_note_in_file,
    list_all_entries,
    unverify_note,
    verify_single_note,
)
from src.siqva.knowledge import (
    KnowledgeCitation,
    KnowledgeEntry,
    answer,
    format_citation,
    load_knowledge_entries,
    reset_knowledge_index,
)


@pytest.fixture
def mock_knowledge_repo(tmp_path: Path):
    """Create a temporary sandbox repo with temporary copies of real knowledge files."""
    repo_root = Path(__file__).resolve().parent.parent

    # Create directories
    (tmp_path / "knowledge" / "notes" / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "knowledge" / "text").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)

    # Copy files
    shutil.copy(repo_root / "knowledge" / "manifest.csv", tmp_path / "knowledge" / "manifest.csv")
    shutil.copy(repo_root / "knowledge" / "questions.jsonl", tmp_path / "knowledge" / "questions.jsonl")
    shutil.copy(repo_root / "knowledge" / "notes" / "argo_notes.yaml", tmp_path / "knowledge" / "notes" / "argo_notes.yaml")
    shutil.copy(repo_root / "knowledge" / "notes" / "own_sentences.yaml", tmp_path / "knowledge" / "notes" / "own_sentences.yaml")
    shutil.copy(repo_root / "data" / "glossary.json", tmp_path / "data" / "glossary.json")

    for ev in (repo_root / "knowledge" / "notes" / "evidence").glob("*.md"):
        shutil.copy(ev, tmp_path / "knowledge" / "notes" / "evidence" / ev.name)

    for txt in (repo_root / "knowledge" / "text").glob("*.txt"):
        shutil.copy(txt, tmp_path / "knowledge" / "text" / txt.name)

    return tmp_path


def test_list_all_entries(mock_knowledge_repo: Path):
    """Test --list output generates formatted table across YAML and JSON sources."""
    buf = io.StringIO()
    count = list_all_entries(repo_root=mock_knowledge_repo, out=buf)
    out_text = buf.getvalue()

    assert count == 39  # 26 doc notes + 10 own notes + 3 glossary terms
    assert "ID" in out_text and "VERIFIED" in out_text and "EVIDENCE/CLAIMS" in out_text
    assert "float-cycle-and-depth" in out_text
    assert "qc-flag-scale" in out_text
    assert "siqva-sample-explanation" in out_text
    assert "MLD" in out_text
    assert "Total entries: 39" in out_text


def test_verify_single_note_success(mock_knowledge_repo: Path):
    """Test verifying a single note with exact typed confirmation."""
    today = datetime.date.today().isoformat()
    note_id = "float-cycle-and-depth"
    success = verify_single_note(
        repo_root=mock_knowledge_repo,
        note_id=note_id,
        confirm_input=note_id,
    )
    assert success is True

    entries = discover_entries(mock_knowledge_repo)
    entry = entries[note_id]
    assert entry["verified"] is True
    assert entry["checked_on"] == today
    assert entry["verified_by"] == "owner"


def test_verify_single_note_mismatch_aborts(mock_knowledge_repo: Path):
    """Test that a mismatched confirmation input aborts without altering files."""
    orig_content = (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8")

    success = verify_single_note(
        repo_root=mock_knowledge_repo,
        note_id="float-cycle-and-depth",
        confirm_input="wrong-id",
    )
    assert success is False

    new_content = (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8")
    assert new_content == orig_content  # Byte-identical


def test_batch_verify_exact_phrase(mock_knowledge_repo: Path):
    """Test --ids with exact confirmation phrase verifies only the targeted notes."""
    today = datetime.date.today().isoformat()
    ids = ["float-cycle-and-depth", "qc-flag-scale"]

    success = apply_batch_verification(
        repo_root=mock_knowledge_repo,
        note_ids=ids,
        confirm_phrase="I reviewed these 2 notes",
        applied_via="agent on owner instruction",
    )
    assert success is True

    entries = discover_entries(mock_knowledge_repo)
    assert entries["float-cycle-and-depth"]["verified"] is True
    assert entries["float-cycle-and-depth"]["checked_on"] == today
    assert entries["qc-flag-scale"]["verified"] is True
    assert entries["qc-flag-scale"]["checked_on"] == today
    # Untouched note remains unverified
    assert entries["argo-one-paragraph"]["verified"] is False


def test_batch_verify_wrong_phrase_aborts(mock_knowledge_repo: Path):
    """Test --ids with wrong confirmation phrase aborts and leaves files untouched."""
    orig_yaml = (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8")

    success = apply_batch_verification(
        repo_root=mock_knowledge_repo,
        note_ids=["float-cycle-and-depth", "qc-flag-scale"],
        confirm_phrase="I reviewed 2 notes",  # Missing 'these'
    )
    assert success is False
    assert (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8") == orig_yaml


def test_batch_verify_unknown_id_aborts(mock_knowledge_repo: Path):
    """Test --ids with an unknown ID aborts with no file modifications."""
    orig_yaml = (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8")

    success = apply_batch_verification(
        repo_root=mock_knowledge_repo,
        note_ids=["float-cycle-and-depth", "non-existent-note"],
        confirm_phrase="I reviewed these 2 notes",
    )
    assert success is False
    assert (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8") == orig_yaml


def test_batch_verify_missing_evidence_aborts(mock_knowledge_repo: Path):
    """Test --ids aborts without changes if any note lacks an evidence file or claims list."""
    # Delete evidence file for qc-flag-scale
    (mock_knowledge_repo / "knowledge" / "notes" / "evidence" / "qc-flag-scale.md").unlink()
    orig_yaml = (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8")

    success = apply_batch_verification(
        repo_root=mock_knowledge_repo,
        note_ids=["float-cycle-and-depth", "qc-flag-scale"],
        confirm_phrase="I reviewed these 2 notes",
    )
    assert success is False
    assert (mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml").read_text(encoding="utf-8") == orig_yaml


def test_batch_verify_wildcard_rejection(mock_knowledge_repo: Path):
    """Test wildcard or keyword targets like '*' or 'all' raise ValueError."""
    with pytest.raises(ValueError, match="Wildcards, ranges, or bulk keywords are forbidden"):
        apply_batch_verification(
            repo_root=mock_knowledge_repo,
            note_ids=["*"],
            confirm_phrase="I reviewed these 1 notes",
        )

    with pytest.raises(ValueError, match="Wildcards, ranges, or bulk keywords are forbidden"):
        apply_batch_verification(
            repo_root=mock_knowledge_repo,
            note_ids=["all"],
            confirm_phrase="I reviewed these 1 notes",
        )


def test_text_preserving_edit_invariants(mock_knowledge_repo: Path):
    """Test that editing a note preserves all comments and byte-identical text of other entries."""
    argo_path = mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml"
    orig_text = argo_path.read_text(encoding="utf-8")

    # Verify first note
    edit_entry_in_file(
        repo_root=mock_knowledge_repo,
        note_id="float-cycle-and-depth",
        verified=True,
        checked_on="2026-11-15",
        verified_by="owner",
        applied_via="test-runner",
    )

    new_text = argo_path.read_text(encoding="utf-8")

    # Second note onwards must remain completely unchanged
    second_id = "- id: qc-flag-scale"
    note2_orig = orig_text[orig_text.index(second_id) :]
    note2_new = new_text[new_text.index(second_id) :]
    assert note2_orig == note2_new


def test_unverify_note(mock_knowledge_repo: Path):
    """Test unverify sets verified: false and clears metadata."""
    note_id = "float-cycle-and-depth"
    # First verify
    verify_single_note(
        repo_root=mock_knowledge_repo,
        note_id=note_id,
        confirm_input=note_id,
    )
    entries = discover_entries(mock_knowledge_repo)
    assert entries[note_id]["verified"] is True

    # Then unverify
    success = unverify_note(mock_knowledge_repo, note_id)
    assert success is True

    entries_after = discover_entries(mock_knowledge_repo)
    entry = entries_after[note_id]
    assert entry["verified"] is False
    assert entry["checked_on"] == ""
    assert entry["verified_by"] == ""


def test_check_knowledge_validation_rules(mock_knowledge_repo: Path):
    """Test check_knowledge enforcing verified rules."""
    note_id = "float-cycle-and-depth"
    # Initially all unverified: passes
    errors = check_knowledge(repo_root=mock_knowledge_repo)
    assert len(errors) == 0

    # Verify note properly
    verify_single_note(mock_knowledge_repo, note_id, confirm_input=note_id)
    errors = check_knowledge(repo_root=mock_knowledge_repo)
    assert len(errors) == 0

    # Corrupt checked_on in file directly
    argo_path = mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml"
    text = argo_path.read_text(encoding="utf-8")
    argo_path.write_text(text.replace("checked_on: '", "checked_on: 'invalid-date"), encoding="utf-8")

    errs = check_knowledge(repo_root=mock_knowledge_repo)
    assert any("valid YYYY-MM-DD date" in e for e in errs)

    # Corrupt verified_by
    argo_path.write_text(text.replace("verified_by: owner", "verified_by: assistant"), encoding="utf-8")
    errs = check_knowledge(repo_root=mock_knowledge_repo)
    assert any("verified_by must be 'owner'" in e for e in errs)

    # Missing evidence
    (mock_knowledge_repo / "knowledge" / "notes" / "evidence" / f"{note_id}.md").unlink()
    argo_path.write_text(text, encoding="utf-8")  # restore valid text
    errs = check_knowledge(repo_root=mock_knowledge_repo)
    assert any("evidence file" in e.lower() and "missing" in e.lower() for e in errs)


def test_knowledge_answer_verified_vs_unverified(mock_knowledge_repo: Path):
    """Test that verified notes are returned with switch off, showing 'checked <date>' without '[Unverified note]'."""
    reset_knowledge_index()

    # With switch unset and all unverified:
    entries = load_knowledge_entries(
        manifest_path=mock_knowledge_repo / "knowledge" / "manifest.csv",
        argo_notes_path=mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml",
        own_sentences_path=mock_knowledge_repo / "knowledge" / "notes" / "own_sentences.yaml",
        glossary_path=mock_knowledge_repo / "data" / "glossary.json",
    )
    with patch("src.siqva.knowledge.load_knowledge_entries", return_value=entries):
        with patch.dict(os.environ, {}, clear=True):
            ans = answer("How deep do Argo floats dive?")
            # Because note is unverified and switch is unset: returns not_in_notes
            assert ans.kind == "not_in_notes"

        # Now verify float-cycle-and-depth
        verify_single_note(mock_knowledge_repo, "float-cycle-and-depth", confirm_input="float-cycle-and-depth")
        verified_entries = load_knowledge_entries(
            manifest_path=mock_knowledge_repo / "knowledge" / "manifest.csv",
            argo_notes_path=mock_knowledge_repo / "knowledge" / "notes" / "argo_notes.yaml",
            own_sentences_path=mock_knowledge_repo / "knowledge" / "notes" / "own_sentences.yaml",
            glossary_path=mock_knowledge_repo / "data" / "glossary.json",
        )

        with patch("src.siqva.knowledge.load_knowledge_entries", return_value=verified_entries):
            reset_knowledge_index()
            # Switch unset: verified note IS returned!
            with patch.dict(os.environ, {}, clear=True):
                ans_verified = answer("How deep do Argo floats dive?")
                assert ans_verified.kind == "answer"
                assert ans_verified.status == "verified"
                assert "2000" in ans_verified.text
                assert "[Unverified note]" not in ans_verified.text

                # Check citation format
                cit_formatted = format_citation(ans_verified.citations[0], status=ans_verified.status)
                assert "checked" in cit_formatted
                assert datetime.date.today().isoformat() in cit_formatted

            # Switch set to 1: unverified notes also returned with [Unverified note]
            with patch.dict(os.environ, {"SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED": "1"}):
                reset_knowledge_index()
                ans_unverified = answer("What is real-time QC?")
                assert ans_unverified.kind == "answer"
                assert ans_unverified.status == "unverified"
