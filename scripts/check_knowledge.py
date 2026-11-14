#!/usr/bin/env python3
"""
SIQVA Knowledge Base Validator (scripts/check_knowledge.py)

Validates:
1. knowledge/manifest.csv (headers, unique IDs, status, SHA256)
2. knowledge/notes/*.yaml (required fields, unique IDs, source_id in manifest,
   verified: false on document notes, 2-5 sentences, <= 1 quotation < 15 words,
   valid aliases)
3. knowledge/notes/evidence/<id>.md (evidence file exists for every note,
   evidence line for every sentence, no "NO SUPPORT FOUND", supporting phrase < 15 words
   and present in extracted text)
4. knowledge/questions.jsonl (valid JSON, required fields, unique IDs,
   referenced note IDs/aliases exist)

Exits with code 0 on success, code 1 on validation errors.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unicodedata
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


def split_sentences_list(text: str) -> list[str]:
    """Split prose text into list of individual sentences, handling common abbreviations."""
    clean = re.sub(
        r"\b(e\.g\.|i\.e\.|vs\.|approx\.|et al\.|no\.|dr\.|prof\.)",
        lambda m: m.group(0).replace(".", "@DOT@"),
        text,
        flags=re.IGNORECASE,
    )
    clean = re.sub(r"\b\d+\.\d+\b", lambda m: m.group(0).replace(".", "@DOT@"), clean)
    sentences = [
        s.replace("@DOT@", ".").strip()
        for s in re.split(r"(?<=[.?!])\s+", clean.strip())
        if s.strip()
    ]
    return sentences


def find_quotations(text: str) -> list[str]:
    """Extract quoted substrings from text (supports standard and curly quotes)."""
    matches = re.findall(r'"([^"]+)"|“([^”]+)”', text)
    quotes: list[str] = []
    for m in matches:
        q = m[0] or m[1]
        if q.strip():
            quotes.append(q.strip())
    return quotes


def check_phrase_in_source(text_file: Path, phrase: str) -> bool:
    """Check if phrase exists in extracted source text with flexible whitespace and unicode normalization."""
    if not text_file.exists():
        return False
    raw_content = text_file.read_text(encoding="utf-8")
    norm_content = unicodedata.normalize("NFKD", raw_content)
    norm_phrase = unicodedata.normalize("NFKD", phrase)
    pattern = r"\s+".join(re.escape(w) for w in norm_phrase.split())
    return bool(re.search(pattern, norm_content, re.IGNORECASE))


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


def validate_evidence_file(
    evidence_path: Path,
    note: dict[str, Any],
    source_text_file: Path,
) -> list[str]:
    """Validate a single knowledge/notes/evidence/<id>.md file."""
    errors: list[str] = []
    note_id = note.get("id", "")

    if not evidence_path.exists():
        return [f"Evidence file missing for note '{note_id}': {evidence_path.name}"]

    evidence_text = evidence_path.read_text(encoding="utf-8")

    sentences = split_sentences_list(str(note.get("answer", "")))
    if not sentences:
        errors.append(f"Evidence audit for '{note_id}': note answer has no sentences.")
        return errors

    # Check evidence sections for every sentence
    for s_idx, sent in enumerate(sentences, 1):
        s_marker = f"### Sentence {s_idx}"
        if s_marker not in evidence_text:
            errors.append(
                f"Evidence file '{evidence_path.name}': missing block for Sentence {s_idx}."
            )
            continue

        # Find block for this sentence
        idx_start = evidence_text.find(s_marker)
        next_marker = f"### Sentence {s_idx + 1}"
        idx_end = evidence_text.find(next_marker) if next_marker in evidence_text else len(evidence_text)
        block = evidence_text[idx_start:idx_end]

        if "NO SUPPORT FOUND" in block:
            errors.append(
                f"Evidence file '{evidence_path.name}': Sentence {s_idx} is marked 'NO SUPPORT FOUND'."
            )

        # Extract supporting phrase
        m_phrase = re.search(r'Supporting Phrase\*\*:\s*["“]([^"”]+)["”]', block)
        if not m_phrase:
            errors.append(
                f"Evidence file '{evidence_path.name}': Sentence {s_idx} missing 'Supporting Phrase'."
            )
        else:
            phrase = m_phrase.group(1).strip()
            w_count = len(phrase.split())
            if w_count >= 15:
                errors.append(
                    f"Evidence file '{evidence_path.name}': Sentence {s_idx} supporting phrase has {w_count} words (must be < 15)."
                )
            if source_text_file.exists() and not check_phrase_in_source(source_text_file, phrase):
                errors.append(
                    f"Evidence file '{evidence_path.name}': Sentence {s_idx} supporting phrase not found in extracted text: '{phrase}'"
                )

    return errors


def validate_notes(
    notes_dir: Path,
    manifest_sources: dict[str, dict[str, str]],
    repo_root: Path | None = None,
) -> tuple[set[str], list[str]]:
    """Validate YAML note files in knowledge/notes/ and their evidence files."""
    errors: list[str] = []
    all_note_ids: set[str] = set()

    if not notes_dir.exists():
        return all_note_ids, [f"Notes directory not found: {notes_dir}"]

    if repo_root is None:
        repo_root = notes_dir.resolve().parent.parent

    yaml_files = sorted(notes_dir.glob("*.yaml"))
    if not yaml_files:
        errors.append(f"No YAML files found in {notes_dir}")
        return all_note_ids, errors

    evidence_dir = notes_dir / "evidence"
    text_dir = repo_root / "knowledge" / "text"

    for yaml_path in yaml_files:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            errors.append(f"{yaml_path.name}: file is empty.")
            continue

        # Distinguish code-derived dictionary from document-derived list of notes
        if isinstance(data, dict):
            metadata = data.get("metadata", {})
            origin = metadata.get("origin")
            if origin not in ("generated", "code"):
                errors.append(
                    f"{yaml_path.name}: dictionary format expected origin: 'generated' or 'code'."
                )
            if origin == "code":
                if "developer_name" not in metadata:
                    errors.append(
                        f"{yaml_path.name}: missing 'developer_name' field in metadata."
                    )
                notes_list = data.get("notes", [])
                if not isinstance(notes_list, list) or len(notes_list) == 0:
                    errors.append(f"{yaml_path.name}: 'notes' must be a non-empty list.")
                for idx, entry in enumerate(notes_list):
                    if not isinstance(entry, dict):
                        errors.append(f"{yaml_path.name}[{idx}]: entry must be a dict.")
                        continue
                    eid = entry.get("id", "").strip()
                    if not eid:
                        errors.append(f"{yaml_path.name}[{idx}]: missing note id.")
                        continue
                    all_note_ids.add(eid)
                    ans = entry.get("answer", "")
                    s_count = count_sentences(ans)
                    if not (2 <= s_count <= 5):
                        errors.append(
                            f"{yaml_path.name}[{eid}]: answer sentence count ({s_count}) is outside allowed range (2-5 sentences)."
                        )
                    quotes = find_quotations(ans)
                    if len(quotes) > 1:
                        errors.append(
                            f"{yaml_path.name}[{eid}]: answer contains {len(quotes)} quotations (maximum allowed is 1)."
                        )
                    for q in quotes:
                        w_len = len(q.split())
                        if w_len >= 15:
                            errors.append(
                                f"{yaml_path.name}[{eid}]: quotation has {w_len} words (must be under 15 words): '{q}'"
                            )
            else:
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
            "retrieved_on",
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

            # Register any declared aliases
            aliases = note.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    alias_str = str(alias).strip()
                    if alias_str:
                        all_note_ids.add(alias_str)

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

            # Validate evidence file
            evidence_file = evidence_dir / f"{note_id}.md"
            source_txt_file = text_dir / f"{src_id}.txt"
            ev_errors = validate_evidence_file(evidence_file, note, source_txt_file)
            errors.extend(ev_errors)

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

    note_ids, notes_errors = validate_notes(notes_dir, sources, repo_root)
    all_errors.extend(notes_errors)

    questions_errors = validate_questions(questions_path, note_ids)
    all_errors.extend(questions_errors)

    return all_errors


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    print("=" * 60)
    print("SIQVA Knowledge Base Integrity Checker (with Evidence Audit)")
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
    note_ids, _ = validate_notes(notes_dir, sources, repo_root)
    questions_path = repo_root / "knowledge" / "questions.jsonl"
    with open(questions_path, "r", encoding="utf-8") as f:
        q_count = sum(1 for line in f if line.strip())

    evidence_files = list((notes_dir / "evidence").glob("*.md"))

    print("\n[PASSED] Knowledge base verification successful!")
    print(f"  - Sources in manifest: {len(sources)}")
    print(f"  - Registered note concepts & aliases: {len(note_ids)}")
    print(f"  - Verified flag: all document-derived notes are verified: false")
    print(f"  - Evidence audit files: {len(evidence_files)} verified (0 'NO SUPPORT FOUND')")
    print(f"  - Questions verified: {q_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
