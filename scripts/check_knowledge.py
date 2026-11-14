#!/usr/bin/env python3
"""
SIQVA Knowledge Base Validator (scripts/check_knowledge.py)

Validates:
1. knowledge/manifest.csv (headers, unique IDs, status, SHA256)
2. knowledge/notes/*.yaml (required fields, unique IDs, source_id in manifest,
   verified: false on document notes, 2-5 sentences, <= 1 quotation < 15 words)
3. knowledge/questions.jsonl (valid JSON, required fields, unique IDs,
   referenced note IDs exist)

Exits with code 0 on success, code 1 on validation errors.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


def count_sentences(text: str) -> int:
    """Count sentences in prose text, handling common abbreviations."""
    clean = re.sub(
        r"\b(e\.g\.|i\.e\.|vs\.|approx\.|et al\.|no\.|dr\.|prof\.)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    # Replace decimal numbers (e.g. 1.25) so dots don't split sentences
    clean = re.sub(r"\b\d+\.\d+\b", "NUM", clean)
    sentences = [
        s.strip() for s in re.split(r"[\.\?!]+(?:\s+|$)", clean) if s.strip()
    ]
    return len(sentences)


def find_quotations(text: str) -> list[str]:
    """Extract quoted substrings from text (supports standard and curly quotes)."""
    # Matches "..." or “...”
    matches = re.findall(r'"([^"]+)"|“([^”]+)”', text)
    quotes: list[str] = []
    for m in matches:
        q = m[0] or m[1]
        if q.strip():
            quotes.append(q.strip())
    return quotes


def validate_manifest(
    manifest_path: Path,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """Validate knowledge/manifest.csv and return {source_id: row}."""
    errors: list[str] = []
    sources: dict[str, dict[str, str]] = {}

    if not manifest_path.exists():
        return sources, [f"Manifest file not found: {manifest_path}"]

    expected_headers = [
        "id",
        "title",
        "version",
        "doc_date",
        "url_or_doi",
        "license_as_seen",
        "retrieved_on",
        "local_path",
        "sha256",
        "status",
        "notes",
    ]

    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != expected_headers:
            errors.append(
                f"Manifest headers mismatch.\nExpected: {expected_headers}\nFound: {reader.fieldnames}"
            )

        for line_num, row in enumerate(reader, start=2):
            source_id = row.get("id", "").strip()
            if not source_id:
                errors.append(f"Manifest line {line_num}: missing source id.")
                continue

            if source_id in sources:
                errors.append(
                    f"Manifest line {line_num}: duplicate source id '{source_id}'."
                )

            status = row.get("status", "").strip()
            if status not in {"present", "not_retrieved"}:
                errors.append(
                    f"Manifest source '{source_id}': invalid status '{status}' (expected 'present' or 'not_retrieved')."
                )

            sha = row.get("sha256", "").strip()
            if status == "present":
                if len(sha) != 64 or not all(
                    c in "0123456789abcdefABCDEF" for c in sha
                ):
                    errors.append(
                        f"Manifest source '{source_id}': status is 'present' but sha256 is invalid ('{sha}')."
                    )
                local_path = row.get("local_path", "").strip()
                if not local_path:
                    errors.append(
                        f"Manifest source '{source_id}': status is 'present' but local_path is empty."
                    )

            sources[source_id] = row

    return sources, errors


def validate_notes(
    notes_dir: Path, manifest_sources: dict[str, dict[str, str]]
) -> tuple[set[str], list[str]]:
    """Validate YAML note files in knowledge/notes/."""
    errors: list[str] = []
    all_note_ids: set[str] = set()

    if not notes_dir.exists():
        return all_note_ids, [f"Notes directory not found: {notes_dir}"]

    yaml_files = sorted(notes_dir.glob("*.yaml"))
    if not yaml_files:
        errors.append(f"No YAML files found in {notes_dir}")
        return all_note_ids, errors

    for yaml_path in yaml_files:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            errors.append(f"{yaml_path.name}: file is empty.")
            continue

        # Distinguish code-derived dictionary from document-derived list of notes
        if isinstance(data, dict):
            metadata = data.get("metadata", {})
            if metadata.get("origin") != "generated":
                errors.append(
                    f"{yaml_path.name}: dictionary format expected origin: 'generated'."
                )
            # Register top-level keys as available concepts (e.g. supported_regions, capabilities, data_modes)
            for key in data.keys():
                if key != "metadata":
                    all_note_ids.add(key)
            continue

        if not isinstance(data, list):
            errors.append(
                f"{yaml_path.name}: expected list of notes or dict with metadata."
            )
            continue

        required_fields = {
            "id",
            "question_examples",
            "answer",
            "source_id",
            "section_or_page",
            "source_version",
            "limits",
            "related",
            "verified",
            "checked_on",
        }

        for idx, note in enumerate(data):
            if not isinstance(note, dict):
                errors.append(
                    f"{yaml_path.name}[{idx}]: note must be a dictionary."
                )
                continue

            note_id = note.get("id", "").strip()
            if not note_id:
                errors.append(f"{yaml_path.name}[{idx}]: missing note id.")
                continue

            if note_id in all_note_ids:
                errors.append(
                    f"{yaml_path.name}: duplicate note id '{note_id}'."
                )
            all_note_ids.add(note_id)

            missing_fields = required_fields - set(note.keys())
            if missing_fields:
                errors.append(
                    f"{yaml_path.name}[{note_id}]: missing required fields: {sorted(missing_fields)}"
                )

            # Verification rule: Document-derived notes MUST have verified: false
            is_verified = note.get("verified")
            if is_verified is True:
                errors.append(
                    f"{yaml_path.name}[{note_id}]: 'verified' is set to True. "
                    "Agents may NEVER set verified: true on document notes (only the owner may verify)."
                )
            elif is_verified is not False:
                errors.append(
                    f"{yaml_path.name}[{note_id}]: 'verified' must be boolean False."
                )

            # Source citation must match manifest
            src_id = note.get("source_id", "").strip()
            if src_id not in manifest_sources:
                errors.append(
                    f"{yaml_path.name}[{note_id}]: source_id '{src_id}' not found in manifest."
                )

            sec = str(note.get("section_or_page", "")).strip()
            if not sec:
                errors.append(
                    f"{yaml_path.name}[{note_id}]: section_or_page citation cannot be empty."
                )

            # Answer length and quotations
            answer = str(note.get("answer", "")).strip()
            if not answer:
                errors.append(
                    f"{yaml_path.name}[{note_id}]: answer cannot be empty."
                )
            else:
                sent_count = count_sentences(answer)
                if not (2 <= sent_count <= 5):
                    errors.append(
                        f"{yaml_path.name}[{note_id}]: answer sentence count ({sent_count}) is outside allowed range (2-5 sentences)."
                    )

                quotes = find_quotations(answer)
                if len(quotes) > 1:
                    errors.append(
                        f"{yaml_path.name}[{note_id}]: answer contains {len(quotes)} quotations (maximum allowed is 1)."
                    )
                for q in quotes:
                    word_len = len(q.split())
                    if word_len >= 15:
                        errors.append(
                            f"{yaml_path.name}[{note_id}]: quotation has {word_len} words (must be under 15 words): '{q}'"
                        )

    return all_note_ids, errors


def validate_questions(
    questions_path: Path, valid_note_ids: set[str]
) -> list[str]:
    """Validate knowledge/questions.jsonl benchmark file."""
    errors: list[str] = []
    seen_ids: set[str] = set()

    if not questions_path.exists():
        return [f"Questions file not found: {questions_path}"]

    required_fields = {
        "id",
        "question",
        "type",
        "split",
        "expected_note_ids",
        "expected_facts",
        "expected_behavior",
        "needs_review",
    }
    allowed_types = {"knowledge", "refuse", "not_in_notes", "data", "meta"}
    allowed_splits = {"dev", "heldout", "train", "test"}

    with open(questions_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue

            try:
                item = json.loads(line_str)
            except Exception as e:
                errors.append(
                    f"Line {line_num} in {questions_path.name}: invalid JSON: {e}"
                )
                continue

            if not isinstance(item, dict):
                errors.append(
                    f"Line {line_num} in {questions_path.name}: record must be a JSON object."
                )
                continue

            qid = item.get("id", "").strip()
            if not qid:
                errors.append(
                    f"Line {line_num} in {questions_path.name}: missing question id."
                )
                continue

            if qid in seen_ids:
                errors.append(
                    f"Duplicate question id '{qid}' at line {line_num}."
                )
            seen_ids.add(qid)

            missing = required_fields - set(item.keys())
            if missing:
                errors.append(
                    f"Question '{qid}' missing required fields: {sorted(missing)}"
                )

            qtype = item.get("type", "")
            if qtype not in allowed_types:
                errors.append(
                    f"Question '{qid}': invalid type '{qtype}' (allowed: {sorted(allowed_types)})"
                )

            split = item.get("split", "")
            if split not in allowed_splits:
                errors.append(
                    f"Question '{qid}': invalid split '{split}' (allowed: {sorted(allowed_splits)})"
                )

            note_ids = item.get("expected_note_ids", [])
            if not isinstance(note_ids, list):
                errors.append(
                    f"Question '{qid}': expected_note_ids must be a list."
                )
            else:
                for nid in note_ids:
                    if nid not in valid_note_ids:
                        errors.append(
                            f"Question '{qid}': referenced note id '{nid}' does not exist in knowledge notes."
                        )

            facts = item.get("expected_facts", [])
            if not isinstance(facts, list):
                errors.append(
                    f"Question '{qid}': expected_facts must be a list of strings."
                )

    return errors


def check_knowledge_base(repo_root: Path | None = None) -> list[str]:
    """Run all validation checks and return list of error strings."""
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    manifest_path = repo_root / "knowledge" / "manifest.csv"
    notes_dir = repo_root / "knowledge" / "notes"
    questions_path = repo_root / "knowledge" / "questions.jsonl"

    all_errors: list[str] = []

    sources, manifest_errors = validate_manifest(manifest_path)
    all_errors.extend(manifest_errors)

    note_ids, notes_errors = validate_notes(notes_dir, sources)
    all_errors.extend(notes_errors)

    questions_errors = validate_questions(questions_path, note_ids)
    all_errors.extend(questions_errors)

    return all_errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    print("=" * 60)
    print("SIQVA Knowledge Base Integrity Checker")
    print("=" * 60)

    errors = check_knowledge_base(repo_root)

    if errors:
        print(f"\n[FAILED] Found {len(errors)} validation issue(s):")
        for err in errors:
            print(f"  - {err}")
        print("\nPlease resolve these issues and rerun scripts/check_knowledge.py.")
        return 1

    manifest_path = repo_root / "knowledge" / "manifest.csv"
    sources, _ = validate_manifest(manifest_path)
    notes_dir = repo_root / "knowledge" / "notes"
    note_ids, _ = validate_notes(notes_dir, sources)
    questions_path = repo_root / "knowledge" / "questions.jsonl"
    with open(questions_path, "r", encoding="utf-8") as f:
        q_count = sum(1 for line in f if line.strip())

    print("\n[PASSED] Knowledge base verification successful!")
    print(f"  - Sources in manifest: {len(sources)}")
    print(f"  - Registered note concepts: {len(note_ids)}")
    print(f"  - Verified flag: all document-derived notes are verified: false")
    print(f"  - Questions verified: {q_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
