#!/usr/bin/env python3
"""
SIQVA Note Verification Tool (scripts/verify_note.py)

Interactive and batch verification manager for SIQVA knowledge notes.
Verifies notes in knowledge/notes/argo_notes.yaml, knowledge/notes/own_sentences.yaml,
and data/glossary.json.

Invariants:
- All edits are text-preserving: only the targeted entry's lines are modified.
- Comments, quoting styles, and non-target entries remain 100% byte-identical.
- Requires explicit typed confirmation from the repository owner before setting verified: true.
- Requires valid evidence file (for document notes) or claims list (for own notes).

Usage:
    python scripts/verify_note.py --list
    python scripts/verify_note.py <note_id>
    python scripts/verify_note.py --ids a,b,c
    python scripts/verify_note.py --unverify <note_id>
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional


# -----------------------------------------------------------------------------
# DISCOVERY & INSPECTION
# -----------------------------------------------------------------------------

def load_manifest_dict(manifest_path: Path) -> dict[str, dict[str, str]]:
    """Load manifest.csv into a dictionary keyed by source id."""
    manifest: dict[str, dict[str, str]] = {}
    if not manifest_path.exists():
        return manifest
    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = row.get("id", "").strip()
            if sid:
                manifest[sid] = row
    return manifest


def discover_entries(
    repo_root: Path,
    argo_notes_path: Optional[Path] = None,
    own_sentences_path: Optional[Path] = None,
    glossary_path: Optional[Path] = None,
    evidence_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> dict[str, dict[str, Any]]:
    """Discover all knowledge entries across argo_notes, own_sentences, and glossary."""
    if argo_notes_path is None:
        argo_notes_path = repo_root / "knowledge" / "notes" / "argo_notes.yaml"
    if own_sentences_path is None:
        own_sentences_path = repo_root / "knowledge" / "notes" / "own_sentences.yaml"
    if glossary_path is None:
        glossary_path = repo_root / "data" / "glossary.json"
    if evidence_dir is None:
        evidence_dir = repo_root / "knowledge" / "notes" / "evidence"
    if manifest_path is None:
        manifest_path = repo_root / "knowledge" / "manifest.csv"

    manifest = load_manifest_dict(manifest_path)
    entries: dict[str, dict[str, Any]] = {}

    # 1. Document notes (argo_notes.yaml)
    if argo_notes_path.exists():
        import yaml
        with open(argo_notes_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        for item in data:
            if isinstance(item, dict) and "id" in item:
                nid = item["id"].strip()
                ev_file = evidence_dir / f"{nid}.md"
                src_id = item.get("source_id", "").strip()
                m_row = manifest.get(src_id, {})
                entries[nid] = {
                    "id": nid,
                    "kind": "document",
                    "file_path": argo_notes_path,
                    "rel_file": "knowledge/notes/argo_notes.yaml",
                    "verified": bool(item.get("verified", False)),
                    "checked_on": str(item.get("checked_on") or ""),
                    "verified_by": str(item.get("verified_by") or ""),
                    "applied_via": str(item.get("applied_via") or ""),
                    "answer": str(item.get("answer", "")).strip(),
                    "limits": str(item.get("limits") or "").strip(),
                    "source_id": src_id,
                    "source_version": item.get("source_version") or m_row.get("version", ""),
                    "retrieved_on": item.get("retrieved_on") or m_row.get("retrieved_on", ""),
                    "evidence_file": ev_file,
                    "evidence_present": ev_file.exists(),
                    "claims": [],
                    "claims_present": False,
                }

    # 2. Own system notes (own_sentences.yaml)
    if own_sentences_path.exists():
        import yaml
        with open(own_sentences_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        notes_list = data.get("notes", []) if isinstance(data, dict) else []
        for item in notes_list:
            if isinstance(item, dict) and "id" in item:
                nid = item["id"].strip()
                claims = item.get("claims", [])
                entries[nid] = {
                    "id": nid,
                    "kind": "code",
                    "file_path": own_sentences_path,
                    "rel_file": "knowledge/notes/own_sentences.yaml",
                    "verified": bool(item.get("verified", False)),
                    "checked_on": str(item.get("checked_on") or ""),
                    "verified_by": str(item.get("verified_by") or ""),
                    "applied_via": str(item.get("applied_via") or ""),
                    "answer": str(item.get("answer", "")).strip(),
                    "limits": str(item.get("limits") or "").strip(),
                    "source_id": "siqva-code",
                    "source_version": "2.0",
                    "retrieved_on": "2026-11-14",
                    "evidence_file": None,
                    "evidence_present": False,
                    "claims": claims if isinstance(claims, list) else [],
                    "claims_present": bool(isinstance(claims, list) and len(claims) > 0),
                }

    # 3. Scientific glossary (glossary.json)
    if glossary_path.exists():
        try:
            with open(glossary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            terms = data.get("terms", []) if isinstance(data, dict) else []
            for t in terms:
                if isinstance(t, dict) and "term" in t:
                    term_key = t["term"].strip()
                    entries[term_key] = {
                        "id": term_key,
                        "kind": "glossary",
                        "file_path": glossary_path,
                        "rel_file": "data/glossary.json",
                        "verified": bool(t.get("verified", False)),
                        "checked_on": str(t.get("checked_on") or ""),
                        "verified_by": str(t.get("verified_by") or ""),
                        "applied_via": str(t.get("applied_via") or ""),
                        "answer": str(t.get("definition", "")).strip(),
                        "limits": "",
                        "source_id": f"glossary-{term_key.lower()}",
                        "source_version": str(t.get("source", {}).get("year", "")),
                        "retrieved_on": "2026-11-14",
                        "evidence_file": None,
                        "evidence_present": False,
                        "claims": [],
                        "claims_present": False,
                    }
        except Exception:
            pass

    return entries


# -----------------------------------------------------------------------------
# TEXT-PRESERVING MODIFICATION
# -----------------------------------------------------------------------------

def edit_yaml_note_in_file(
    file_path: Path,
    note_id: str,
    verified: bool,
    checked_on: str,
    verified_by: Optional[str] = None,
    applied_via: Optional[str] = None,
) -> bool:
    """Modify verified fields in a YAML note file while keeping all other lines byte-identical."""
    if not file_path.exists():
        return False

    raw_text = file_path.read_text(encoding="utf-8")
    lines = raw_text.splitlines(keepends=True)

    # Locate start of target note
    id_pattern = re.compile(r"^\s*-\s+id:\s+['\"]?" + re.escape(note_id) + r"['\"]?\s*$")
    start_idx = -1
    for idx, line in enumerate(lines):
        if id_pattern.match(line):
            start_idx = idx
            break

    if start_idx == -1:
        return False

    # Locate end of note (next - id: or end of list/file)
    next_id_pattern = re.compile(r"^\s*-\s+id:\s+")
    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if next_id_pattern.match(lines[idx]):
            end_idx = idx
            break

    block = lines[start_idx:end_idx]
    new_block: list[str] = []

    # Detect indent from existing keys in block
    indent = "  "
    for l in block:
        m = re.match(r"^(\s+)[a-zA-Z0-9_]+:", l)
        if m and not l.strip().startswith("- id:"):
            indent = m.group(1)
            break

    # We will rewrite verified, checked_on, verified_by, applied_via
    has_verified = False
    has_checked_on = False
    has_verified_by = False
    has_applied_via = False

    for line in block:
        if re.match(r"^\s*verified:\s*", line):
            has_verified = True
            new_block.append(f"{indent}verified: {'true' if verified else 'false'}\n")
        elif re.match(r"^\s*checked_on:\s*", line):
            has_checked_on = True
            new_block.append(f"{indent}checked_on: '{checked_on}'\n" if checked_on else f"{indent}checked_on: ''\n")
            if verified and verified_by:
                new_block.append(f"{indent}verified_by: {verified_by}\n")
                has_verified_by = True
            if verified and applied_via:
                new_block.append(f'{indent}applied_via: "{applied_via}"\n')
                has_applied_via = True
        elif re.match(r"^\s*verified_by:\s*", line):
            # Handled above
            continue
        elif re.match(r"^\s*applied_via:\s*", line):
            # Handled above
            continue
        else:
            new_block.append(line)

    # In case verified or checked_on were not present in original block
    if not has_verified:
        new_block.append(f"{indent}verified: {'true' if verified else 'false'}\n")
    if not has_checked_on:
        new_block.append(f"{indent}checked_on: '{checked_on}'\n" if checked_on else f"{indent}checked_on: ''\n")
        if verified and verified_by and not has_verified_by:
            new_block.append(f"{indent}verified_by: {verified_by}\n")
        if verified and applied_via and not has_applied_via:
            new_block.append(f'{indent}applied_via: "{applied_via}"\n')

    lines[start_idx:end_idx] = new_block
    new_text = "".join(lines)
    file_path.write_text(new_text, encoding="utf-8")
    return True


def edit_json_glossary_term(
    file_path: Path,
    term_key: str,
    verified: bool,
    checked_on: str,
    verified_by: Optional[str] = None,
    applied_via: Optional[str] = None,
) -> bool:
    """Modify verified fields in glossary.json while preserving all comments, indentation, and order."""
    if not file_path.exists():
        return False

    raw_text = file_path.read_text(encoding="utf-8")

    # Locate term object
    term_pattern = re.compile(
        r'(\{\s*"term":\s*"' + re.escape(term_key) + r'"[\s\S]*?\n\s*\})',
        re.IGNORECASE,
    )
    m = term_pattern.search(raw_text)
    if not m:
        return False

    orig_block = m.group(1)
    new_block = orig_block

    if verified:
        new_block = re.sub(r'"verified":\s*false', '"verified": true', new_block)
        if '"checked_on":' in new_block:
            new_block = re.sub(r'"checked_on":\s*"[^"]*"', f'"checked_on": "{checked_on}"', new_block)
        else:
            new_block = re.sub(
                r'("verified":\s*true)',
                f'\\1,\n      "checked_on": "{checked_on}"',
                new_block,
            )
        if verified_by:
            if '"verified_by":' in new_block:
                new_block = re.sub(r'"verified_by":\s*"[^"]*"', f'"verified_by": "{verified_by}"', new_block)
            else:
                new_block = re.sub(
                    rf'("checked_on":\s*"{checked_on}")',
                    f'\\1,\n      "verified_by": "{verified_by}"',
                    new_block,
                )
        if applied_via:
            if '"applied_via":' in new_block:
                new_block = re.sub(r'"applied_via":\s*"[^"]*"', f'"applied_via": "{applied_via}"', new_block)
            else:
                target_prev = f'"verified_by": "{verified_by}"' if verified_by else f'"checked_on": "{checked_on}"'
                new_block = re.sub(
                    re.escape(target_prev),
                    f'{target_prev},\n      "applied_via": "{applied_via}"',
                    new_block,
                )
    else:
        new_block = re.sub(r'"verified":\s*true', '"verified": false', new_block)
        new_block = re.sub(r',\s*"checked_on":\s*"[^"]*"', '', new_block)
        new_block = re.sub(r',\s*"verified_by":\s*"[^"]*"', '', new_block)
        new_block = re.sub(r',\s*"applied_via":\s*"[^"]*"', '', new_block)

    updated_text = raw_text[:m.start(1)] + new_block + raw_text[m.end(1):]
    file_path.write_text(updated_text, encoding="utf-8")
    return True


def edit_entry_in_file(
    repo_root: Path,
    note_id: str,
    verified: bool,
    checked_on: str,
    verified_by: Optional[str] = None,
    applied_via: Optional[str] = None,
    argo_notes_path: Optional[Path] = None,
    own_sentences_path: Optional[Path] = None,
    glossary_path: Optional[Path] = None,
    evidence_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> bool:
    """Find and edit note entry in its containing file, preserving all other lines byte-identical."""
    entries = discover_entries(
        repo_root,
        argo_notes_path=argo_notes_path,
        own_sentences_path=own_sentences_path,
        glossary_path=glossary_path,
        evidence_dir=evidence_dir,
        manifest_path=manifest_path,
    )
    if note_id not in entries:
        return False

    entry = entries[note_id]
    f_path = entry["file_path"]

    if entry["kind"] in ("document", "code"):
        return edit_yaml_note_in_file(
            f_path,
            note_id,
            verified=verified,
            checked_on=checked_on,
            verified_by=verified_by,
            applied_via=applied_via,
        )
    elif entry["kind"] == "glossary":
        return edit_json_glossary_term(
            f_path,
            note_id,
            verified=verified,
            checked_on=checked_on,
            verified_by=verified_by,
            applied_via=applied_via,
        )
    return False


# -----------------------------------------------------------------------------
# COMMAND HANDLERS
# -----------------------------------------------------------------------------

def handle_list(entries: dict[str, dict[str, Any]], out: Any = None) -> int:
    """Print a clean table of all entries across argo_notes, own_sentences, and glossary."""
    out_stream = out or sys.stdout
    print("=" * 105, file=out_stream)
    print(f"{'ID':<38} {'FILE':<30} {'VERIFIED':<10} {'CHECKED_ON':<12} {'BY':<8} {'EVIDENCE/CLAIMS'}", file=out_stream)
    print("=" * 105, file=out_stream)

    for nid, e in sorted(entries.items()):
        v_str = "true" if e["verified"] else "false"
        chk_str = e["checked_on"] or "-"
        by_str = e["verified_by"] or "-"
        if e["kind"] == "document":
            ev_str = "evidence: present" if e["evidence_present"] else "evidence: MISSING"
        elif e["kind"] == "code":
            ev_str = f"claims: {len(e['claims'])}" if e["claims_present"] else "claims: MISSING"
        else:
            ev_str = "citation only"

        print(f"{nid:<38} {e['rel_file']:<30} {v_str:<10} {chk_str:<12} {by_str:<8} {ev_str}", file=out_stream)

    print("=" * 105, file=out_stream)
    print(f"Total entries: {len(entries)}", file=out_stream)
    return 0


def list_all_entries(repo_root: Path, out: Any = None) -> int:
    """Convenience helper to list all entries for repo_root and return total count."""
    entries = discover_entries(repo_root)
    handle_list(entries, out=out)
    return len(entries)


def verify_single_note(
    repo_root: Path,
    note_id: str,
    confirm_input: Optional[str] = None,
    applied_via: Optional[str] = None,
) -> bool:
    """Verify single note programmatically or interactively."""
    entries = discover_entries(repo_root)
    res = verify_single(repo_root, note_id, entries, confirm_input=confirm_input, applied_via=applied_via)
    return res == 0


def apply_batch_verification(
    repo_root: Path,
    note_ids: list[str] | str,
    confirm_phrase: Optional[str] = None,
    applied_via: Optional[str] = None,
) -> bool:
    """Verify batch of notes programmatically or interactively."""
    if isinstance(note_ids, list):
        for nid in note_ids:
            if nid in ("*", "all", "all notes") or any(c in nid for c in ("*", "?", "[", "]")):
                raise ValueError("Wildcards, ranges, or bulk keywords are forbidden")
        ids_raw = ",".join(note_ids)
    else:
        ids_raw = str(note_ids)
        if ids_raw.strip().lower() in ("*", "all", "all notes") or any(c in ids_raw for c in ("*", "?", "[", "]")):
            raise ValueError("Wildcards, ranges, or bulk keywords are forbidden")

    entries = discover_entries(repo_root)
    res = verify_batch(repo_root, ids_raw, entries, confirm_phrase=confirm_phrase, applied_via=applied_via)
    return res == 0


def unverify_note(repo_root: Path, note_id: str) -> bool:
    """Unverify single note programmatically."""
    entries = discover_entries(repo_root)
    res = unverify_single(repo_root, note_id, entries)
    return res == 0


def format_note_answer_display(entry: dict[str, Any]) -> str:
    """Format note answer text exactly as users see it (including limits)."""
    text = entry["answer"]
    if entry.get("limits"):
        text += f"\n\n*Limits*: {entry['limits']}"
    return text


def inspect_entry(entry: dict[str, Any]) -> None:
    """Print note answer, evidence lines or claims, and manifest metadata."""
    nid = entry["id"]
    print("=" * 80)
    print(f"SIQVA KNOWLEDGE NOTE VERIFICATION REVIEW: {nid}")
    print("=" * 80)
    print(f"File:        {entry['rel_file']}")
    print(f"Source ID:   {entry.get('source_id')}")
    print(f"Doc Version: {entry.get('source_version') or 'N/A'}")
    print(f"Retrieved:   {entry.get('retrieved_on') or 'N/A'}")
    print(f"Current:     {'[VERIFIED]' if entry['verified'] else '[UNVERIFIED / DRAFT]'}")
    if entry.get("checked_on"):
        print(f"Checked on:  {entry['checked_on']} (by: {entry.get('verified_by', 'N/A')})")

    print("\n" + "-" * 80)
    print("ANSWER TEXT (As seen by users in responses):")
    print("-" * 80)
    print(format_note_answer_display(entry))

    print("\n" + "-" * 80)
    if entry["kind"] == "document":
        ev_file: Optional[Path] = entry.get("evidence_file")
        if ev_file and ev_file.exists():
            print(f"EVIDENCE LINES ({ev_file.name}):")
            print("-" * 80)
            print(ev_file.read_text(encoding="utf-8").strip())
        else:
            print("EVIDENCE LINES:")
            print("-" * 80)
            print("[ERROR] Evidence file is missing!")
    elif entry["kind"] == "code":
        print("CLAIMS LIST (Mapped statements, code paths, and constants):")
        print("-" * 80)
        claims = entry.get("claims", [])
        if claims:
            for idx, c in enumerate(claims, 1):
                stmt = c.get("statement", "")
                cpath = c.get("code_path", "")
                const = c.get("constant", "")
                print(f"  {idx}. Statement: {stmt}")
                print(f"     Path:      {cpath} ({const})")
        else:
            print("[ERROR] Claims list is empty or missing!")
    else:
        print("GLOSSARY SOURCE CITATION:")
        print("-" * 80)
        print(f"Term: {nid}")

    print("=" * 80)


def verify_single(
    repo_root: Path,
    note_id: str,
    entries: dict[str, dict[str, Any]],
    argo_notes_path: Optional[Path] = None,
    own_sentences_path: Optional[Path] = None,
    glossary_path: Optional[Path] = None,
    evidence_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    confirm_input: Optional[str] = None,
    applied_via: Optional[str] = None,
) -> int:
    """Review single note and require typing the note ID before setting verified: true."""
    if note_id not in entries:
        print(f"[ERROR] Note ID '{note_id}' not found.")
        return 1

    entry = entries[note_id]
    inspect_entry(entry)

    # Validate evidence or claims
    if entry["kind"] == "document" and not entry["evidence_present"]:
        print(f"[ABORT] Cannot verify note '{note_id}': evidence file is missing.")
        return 1
    if entry["kind"] == "code" and not entry["claims_present"]:
        print(f"[ABORT] Cannot verify note '{note_id}': claims list is missing or empty.")
        return 1

    if confirm_input is None:
        typed = input(f"\nType '{note_id}' to verify this note: ").strip()
    else:
        typed = confirm_input.strip()

    if typed != note_id:
        print(f"[ABORT] Confirmation mismatch ('{typed}' != '{note_id}'). No changes made.")
        return 1

    today = datetime.date.today().isoformat()
    success = edit_entry_in_file(
        repo_root,
        note_id,
        verified=True,
        checked_on=today,
        verified_by="owner",
        applied_via=applied_via,
        argo_notes_path=argo_notes_path,
        own_sentences_path=own_sentences_path,
        glossary_path=glossary_path,
        evidence_dir=evidence_dir,
        manifest_path=manifest_path,
    )

    if success:
        print(f"[SUCCESS] Verified note '{note_id}' on {today} by owner.")
        return 0
    else:
        print(f"[ERROR] Failed to update file for note '{note_id}'.")
        return 1


def verify_batch(
    repo_root: Path,
    ids_raw: str,
    entries: dict[str, dict[str, Any]],
    argo_notes_path: Optional[Path] = None,
    own_sentences_path: Optional[Path] = None,
    glossary_path: Optional[Path] = None,
    evidence_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    confirm_phrase: Optional[str] = None,
    applied_via: Optional[str] = None,
) -> int:
    """Verify comma-separated list of IDs with exact phrase confirmation."""
    # Disallow wildcards, flags, or empty lists
    if any(c in ids_raw for c in ("*", "?", "[", "]")) or "--all" in ids_raw:
        print("[ERROR] Wildcards and --all are not allowed in --ids. Must be explicit comma-separated IDs.")
        return 1

    id_list = [x.strip() for x in ids_raw.split(",") if x.strip()]
    if not id_list:
        print("[ERROR] No note IDs provided in --ids.")
        return 1

    # Check that all IDs exist
    missing_ids = [nid for nid in id_list if nid not in entries]
    if missing_ids:
        print(f"[ABORT] Unknown note ID(s): {missing_ids}. Aborting with no changes.")
        return 1

    # Check evidence / claims for all
    lacking_evidence = []
    for nid in id_list:
        e = entries[nid]
        if e["kind"] == "document" and not e["evidence_present"]:
            lacking_evidence.append(f"{nid} (missing evidence file)")
        elif e["kind"] == "code" and not e["claims_present"]:
            lacking_evidence.append(f"{nid} (missing claims)")
    if lacking_evidence:
        print(f"[ABORT] Note(s) lack required evidence/claims: {lacking_evidence}. Aborting with no changes.")
        return 1

    # Print each note
    print(f"\nReviewing batch of {len(id_list)} notes:\n")
    for nid in id_list:
        inspect_entry(entries[nid])
        print()

    count = len(id_list)
    expected_phrase = f"I reviewed these {count} notes"

    if confirm_phrase is None:
        typed = input(f'Type exactly "{expected_phrase}" to confirm verification of {count} notes: ').strip()
    else:
        typed = confirm_phrase.strip()

    if typed != expected_phrase:
        print(f"[ABORT] Confirmation mismatch. Expected exactly: '{expected_phrase}'. Aborted with no changes.")
        return 1

    today = datetime.date.today().isoformat()
    for nid in id_list:
        edit_entry_in_file(
            repo_root,
            nid,
            verified=True,
            checked_on=today,
            verified_by="owner",
            applied_via=applied_via,
            argo_notes_path=argo_notes_path,
            own_sentences_path=own_sentences_path,
            glossary_path=glossary_path,
            evidence_dir=evidence_dir,
            manifest_path=manifest_path,
        )

    print(f"[SUCCESS] Successfully verified {count} notes on {today} by owner.")
    return 0


def unverify_single(
    repo_root: Path,
    note_id: str,
    entries: dict[str, dict[str, Any]],
    argo_notes_path: Optional[Path] = None,
    own_sentences_path: Optional[Path] = None,
    glossary_path: Optional[Path] = None,
    evidence_dir: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> int:
    """Set note to verified: false and clear checked_on, verified_by, applied_via."""
    if note_id not in entries:
        print(f"[ERROR] Note ID '{note_id}' not found.")
        return 1

    success = edit_entry_in_file(
        repo_root,
        note_id,
        verified=False,
        checked_on="",
        verified_by=None,
        applied_via=None,
        argo_notes_path=argo_notes_path,
        own_sentences_path=own_sentences_path,
        glossary_path=glossary_path,
        evidence_dir=evidence_dir,
        manifest_path=manifest_path,
    )

    if success:
        print(f"[SUCCESS] Unverified note '{note_id}'. Cleared checked_on, verified_by, applied_via.")
        return 0
    else:
        print(f"[ERROR] Failed to unverify note '{note_id}'.")
        return 1


# -----------------------------------------------------------------------------
# MAIN CLI
# -----------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="SIQVA Note Verification Tool")
    parser.add_argument("note_id", nargs="?", help="Single note ID to review and verify")
    parser.add_argument("--list", action="store_true", help="List all notes and their verification status")
    parser.add_argument("--ids", type=str, help="Explicit comma-separated list of note IDs to batch verify")
    parser.add_argument("--unverify", type=str, help="Note ID to revert to unverified")
    parser.add_argument("--confirm-phrase", type=str, help="Confirmation phrase for non-interactive / scripted calls")
    parser.add_argument("--applied-via", type=str, help="Optional provenance metadata for applied_via field")

    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parent.parent

    entries = discover_entries(repo_root)

    if args.list:
        return handle_list(entries)

    if args.unverify:
        return unverify_single(repo_root, args.unverify, entries)

    if args.ids:
        return verify_batch(
            repo_root,
            args.ids,
            entries,
            confirm_phrase=args.confirm_phrase,
            applied_via=args.applied_via,
        )

    if args.note_id:
        return verify_single(
            repo_root,
            args.note_id,
            entries,
            confirm_input=args.confirm_phrase,
            applied_via=args.applied_via,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
