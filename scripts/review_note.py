#!/usr/bin/env python3
"""
SIQVA Note Review Tool (scripts/review_note.py)

Displays a drafted knowledge note alongside the raw source text extracted
from the cited document, allowing the owner to verify that the drafted note
accurately represents the source text without extrapolation.

Usage:
    python scripts/review_note.py <note_id>
    python scripts/review_note.py --list
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


def extract_context_snippet(text: str, citation: str, max_lines: int = 25) -> str:
    """Find the best context snippet matching the section or page citation."""
    lines = text.splitlines()
    if not lines:
        return "(Extracted source text file is empty)"

    # Clean citation to search key (e.g. 'Section "What is Argo ?"' -> 'What is Argo ?')
    search_terms = []
    # If quote in citation
    quoted = re.findall(r'"([^"]+)"', citation)
    if quoted:
        search_terms.extend(quoted)

    # Page citation like "Page 15" or "p. 15"
    page_match = re.search(r'\b(?:page|p\.)\s*(\d+)', citation, re.IGNORECASE)
    if page_match:
        page_num = page_match.group(1)
        search_terms.append(f"=== PAGE {page_num} ===")

    # Add raw citation as fallback
    search_terms.append(citation.strip())

    match_idx = -1
    for term in search_terms:
        term_clean = term.lower().strip()
        for idx, line in enumerate(lines):
            if term_clean in line.lower():
                match_idx = idx
                break
        if match_idx != -1:
            break

    if match_idx == -1:
        # Fallback to start of text
        snippet_lines = lines[:max_lines]
        header = f"(Citation '{citation}' not directly matched as a header; showing first {len(snippet_lines)} lines):\n"
        return header + "\n".join(snippet_lines)

    start = max(0, match_idx - 2)
    end = min(len(lines), match_idx + max_lines)
    snippet_lines = lines[start:end]
    header = f"(Context snippet around line {match_idx + 1}):\n"
    return header + "\n".join(snippet_lines)


def load_all_notes(repo_root: Path) -> dict[str, dict]:
    """Load all document-derived notes from knowledge/notes/*.yaml."""
    notes_dir = repo_root / "knowledge" / "notes"
    notes_by_id: dict[str, dict] = {}
    if not notes_dir.exists():
        return notes_by_id

    for y_file in notes_dir.glob("*.yaml"):
        with open(y_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if isinstance(data, list):
            for note in data:
                if isinstance(note, dict) and "id" in note:
                    notes_by_id[note["id"]] = note
    return notes_by_id


def review_note(repo_root: Path, note_id: str) -> int:
    notes = load_all_notes(repo_root)
    if note_id not in notes:
        print(f"[ERROR] Note ID '{note_id}' not found.")
        print("\nAvailable note IDs:")
        for nid in sorted(notes.keys()):
            print(f"  - {nid}")
        return 1

    note = notes[note_id]
    source_id = note.get("source_id", "")
    citation = note.get("section_or_page", "")
    answer = note.get("answer", "").strip()
    questions = note.get("question_examples", [])
    limits = note.get("limits", "")
    verified = note.get("verified", False)
    checked_on = note.get("checked_on", "")

    # Load source text if available
    text_path = repo_root / "knowledge" / "text" / f"{source_id}.txt"
    if text_path.exists():
        with open(text_path, "r", encoding="utf-8") as f:
            source_raw = f.read()
        source_snippet = extract_context_snippet(source_raw, citation)
    else:
        source_snippet = f"[NOTICE] Extracted source text not found at {text_path.name}.\n(Either raw source was not retrieved or extraction was skipped)."

    print("=" * 80)
    print(f"SIQVA KNOWLEDGE NOTE AUDIT: {note_id}")
    print("=" * 80)
    print(f"Status:      {'[VERIFIED]' if verified else '[UNVERIFIED / DRAFT]'}")
    if checked_on:
        print(f"Checked on:  {checked_on}")
    print(f"Source ID:   {source_id}")
    print(f"Citation:    {citation}")
    if note.get("source_version"):
        print(f"Doc Version: {note.get('source_version')}")

    print("\n" + "-" * 80)
    print("USER QUESTIONS TARGETING THIS NOTE:")
    print("-" * 80)
    for q in questions:
        print(f"  ? {q}")

    print("\n" + "-" * 80)
    print("DRAFTED NOTE ANSWER (Paraphrased, verified-ready):")
    print("-" * 80)
    print(answer)

    if limits:
        print("\n" + "-" * 80)
        print("EXPLICIT BOUNDS & LIMITS:")
        print("-" * 80)
        print(limits)

    print("\n" + "=" * 80)
    print(f"EXTRACTED SOURCE TEXT EVIDENCE ({source_id}.txt):")
    print("=" * 80)
    print(source_snippet)
    print("=" * 80)

    print("\nINSTRUCTIONS FOR THE OWNER:")
    print("1. Compare the drafted answer with the source text evidence above.")
    print("2. Confirm all facts, numbers, and definitions match the source exactly.")
    print("3. To mark as verified, edit knowledge/notes/argo_notes.yaml:")
    print(f"     verified: true")
    print(f'     checked_on: "YYYY-MM-DD"')
    print("4. Run 'python scripts/check_knowledge.py' to re-verify integrity.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Review and audit SIQVA knowledge notes against raw source text.")
    parser.add_argument("note_id", nargs="?", help="ID of the note to review")
    parser.add_argument("--list", action="store_true", help="List all available note IDs")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    if args.list or not args.note_id:
        notes = load_all_notes(repo_root)
        print(f"Available Notes ({len(notes)} total):")
        for nid, note in sorted(notes.items()):
            ver_str = "VERIFIED" if note.get("verified") else "DRAFT"
            print(f"  [{ver_str:8s}] {nid:30s} (Source: {note.get('source_id')})")
        if not args.note_id:
            print("\nRun 'python scripts/review_note.py <note_id>' to inspect a note.")
        return 0

    return review_note(repo_root, args.note_id)


if __name__ == "__main__":
    sys.exit(main())
