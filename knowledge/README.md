# SIQVA Trusted Knowledge Base

This directory contains the reference knowledge base for SIQVA's oceanographic and Argo question answering capabilities.

## Architecture

```
knowledge/
  manifest.csv      # Committed inventory of verified sources, versions, DOIs, hashes, and licenses
  README.md         # Instructions for adding sources, running extractions, and verifying notes
  notes/
    own_generated.yaml  # Code-derived verified definitions (regions, capabilities, QC modes, planner)
    argo_notes.yaml     # Source-derived notes (verified: false until verified by owner)
  scope.md          # Explicit answered vs. refused topic boundaries
  questions.jsonl   # Curated development questions for knowledge evaluation
  sources/          # Raw reference documents (PDF, DOCX, HTML) - GIT IGNORED
  text/             # Extracted text with page/section citations - GIT IGNORED
```

## Rules & Safety Invariants

1. **Deterministic & Grounded**: Notes derived from documents must come strictly from extracted text in `knowledge/text/`, citing the source ID and specific page or section. Never guess or hallucinate facts.
2. **Paraphrase**: Notes are paraphrased in plain English with at most one short quoted phrase (< 15 words) where exact wording is required.
3. **Verification Policy**: All notes derived from external documents default to `verified: false`. Only the repository owner may verify a note by checking it against the original document and setting `verified: true` with a `checked_on` date.
4. **License & Data Isolation**: Raw documents (`sources/`) and extracted text (`text/`) are untrusted data and strictly excluded from Git tracking via `.gitignore`. Never commit raw documents or extracted text.

## How to Add a Source

1. Place the source file in `knowledge/sources/<source_id>.<ext>`.
2. Add an entry to `knowledge/manifest.csv` recording:
   - `id`: Unique identifier (e.g., `argo-qc-ctd`)
   - `title`: Full official title
   - `version`: Version number (or blank if unversioned)
   - `doc_date`: Publication date (YYYY-MM-DD or YYYY-MM)
   - `url_or_doi`: Official DOI or URL
   - `license_as_seen`: License statement found in document (e.g. `CC BY 4.0` or `unverified`)
   - `retrieved_on`: Date downloaded (YYYY-MM-DD)
   - `local_path`: Relative path under `knowledge/sources/`
   - `sha256`: SHA-256 hash of the local file
   - `status`: Set to `present`
   - `notes`: Short description
3. Re-run text extraction:
   ```bash
   python scripts/extract_sources.py
   ```
4. Verify extraction output in `knowledge/text/<source_id>.txt`.

## How to Verify a Note

### Meaning of "Verified" in SIQVA
In SIQVA, **verified** denotes rigorous human attestation:
1. Every factual sentence in the note has been reviewed against its audit evidence file (`knowledge/notes/evidence/<id>.md`) and original source text.
2. Every number, threshold, QC flag, and unit matches authoritative documentation.
3. Zero hallucination or ungrounded synthesis is guaranteed.

### Authority
**Only the repository owner** may verify notes (`verified_by: "owner"`). Automated tools or coding agents may never set `verified: true` on their own judgment.

### Verification Tooling (`scripts/verify_note.py`)
All verification is performed and tracked via `scripts/verify_note.py`, which guarantees text-preserving edits (preserving all comments, quoting, and formatting in YAML/JSON):

1. **List all knowledge entries and their status**:
   ```bash
   python scripts/verify_note.py --list
   ```
2. **Review and verify a single note**:
   ```bash
   python scripts/verify_note.py <note_id>
   ```
   Prints the note's answer, evidence lines, source version, and retrieval date. Prompts the owner to type `<note_id>` to confirm verification (`verified: true`, `checked_on: YYYY-MM-DD`, `verified_by: "owner"`).
3. **Batch verify reviewed notes**:
   ```bash
   python scripts/verify_note.py --ids id1,id2,id3
   ```
   Requires explicit typing of `I reviewed these N notes`. Wildcards and bulk keywords are strictly rejected.
4. **Unverify a note**:
   ```bash
   python scripts/verify_note.py --unverify <note_id>
   ```

### Validation Rules (`scripts/check_knowledge.py`)
`scripts/check_knowledge.py` strictly enforces:
- `verified: true` is allowed ONLY when `checked_on` is a valid ISO date (`YYYY-MM-DD`).
- `verified_by` must equal `"owner"`.
- Document notes must have an existing evidence file with no `NO SUPPORT FOUND` markings.
- System code notes must have non-empty `claims` lists mapping to real code symbols.
- Citations in answers display `checked <date>` and omit `[Unverified note]`. Unverified notes are hidden in production unless `SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED=1`.

## How to Re-Run Extraction and Validation

- Extract text from all present sources:
  ```bash
  python scripts/extract_sources.py
  ```
- Re-generate code-derived notes:
  ```bash
  python scripts/build_own_notes.py
  ```
- Validate all knowledge base files (manifest, notes, questions):
  ```bash
  python scripts/check_knowledge.py
  ```

