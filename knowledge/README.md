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

1. Inspect the note in `knowledge/notes/argo_notes.yaml`.
2. Run the note review helper tool:
   ```bash
   python scripts/review_note.py <note_id>
   ```
   This displays the drafted note side-by-side with the surrounding extracted source text at the cited page or section.
3. If the note accurately represents the source text:
   - Change `verified: false` to `verified: true`.
   - Set `checked_on: "YYYY-MM-DD"`.
4. If the note is inaccurate or unsupported, revise or discard it.

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
