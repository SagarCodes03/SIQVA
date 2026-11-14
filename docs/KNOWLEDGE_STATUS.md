# Knowledge Base Status

Current status of the SIQVA trusted knowledge base preparation.

## Stage Status

- [x] **K0. Setup**: Directory structure created (`knowledge/sources`, `knowledge/text`, `knowledge/notes`), `.gitignore` updated, `knowledge/manifest.csv` initialized with 19 sources, `knowledge/README.md` created.
- [x] **K1. Retrieve missing sources**: Retrieved 9 web sources within allowed hosts with a 5s politeness delay and request caps; 3 sources flagged as `not_retrieved` requiring manual download by the owner.
- [x] **K2. Extract text**: `scripts/extract_sources.py` created and verified. Extracted all 16 present sources into `knowledge/text/` with `=== PAGE n ===` and `=== SECTION: heading ===` markers (890,398 characters total; 0 scanned/empty files).
- [x] **K3. Notes generated from our own code**: `scripts/build_own_notes.py` created and verified. Generates `knowledge/notes/own_generated.yaml` from code modules with regression test `tests/test_own_notes.py`.
- [x] **K4. Draft source-derived notes**: Drafted 23 grounded notes in `knowledge/notes/argo_notes.yaml` citing page/section numbers. All notes have `verified: false` and `checked_on: ""`.
- [x] **K5. Scope, questions, checker, review tool**: `knowledge/scope.md`, `knowledge/questions.jsonl` (40 dev questions), `scripts/check_knowledge.py`, `scripts/review_note.py`, and `tests/test_knowledge.py` created and verified.
- [x] **K6. Status and finish**: Summary report, checklist for owner verification, test suite run (472 passed, 4 skipped), pushed to `task-knowledge`.

---

## Owner Verification Checklist (Top 10 Priority Notes)

The owner can audit each drafted note alongside the original extracted document snippet by running:
```bash
python scripts/review_note.py <note_id>
```
If the drafted text accurately reflects the source document, edit `knowledge/notes/argo_notes.yaml` to set `verified: true` and `checked_on: "YYYY-MM-DD"`. Then run `python scripts/check_knowledge.py` to confirm.

| # | Note ID | Source ID | Cited Section / Page | Owner Action |
|---|---|---|---|---|
| 1 | `argo-one-paragraph` | `argopy-what-is-argo` | Section "What is Argo ?" | Run `python scripts/review_note.py argo-one-paragraph`. Verify array size (~4000 floats), 10-day cycle, 2000m depth, and 24h data availability. |
| 2 | `float-cycle-and-depth` | `argo-how-floats-work` | Section "What does an Argo float do?" | Run `python scripts/review_note.py float-cycle-and-depth`. Verify 10-day cycle, 1000m drift for ~9 days, 2000m profile ascent, and surface telemetry. |
| 3 | `qc-flag-scale` | `argo-user-manual` | Page 76 (Reference Table 2) | Run `python scripts/review_note.py qc-flag-scale`. Verify 0–9 numerical scale and primary definitions (1 = good, 4 = bad). |
| 4 | `data-modes-rad` | `argo-user-manual` | Page 19–20 (Section 2.3) | Run `python scripts/review_note.py data-modes-rad`. Verify definitions of Real-time (R), Adjusted (A), and Delayed-mode (D). |
| 5 | `delayed-mode-timing` | `wong2020` | Page 8 (Section 3.2.1) | Run `python scripts/review_note.py delayed-mode-timing`. Verify requirement of ~12-month time series accumulation for sensor drift calibration. |
| 6 | `realtime-vs-delayed-qc` | `wong2020` | Page 8 (Section 3.1 & 3.2) | Run `python scripts/review_note.py realtime-vs-delayed-qc`. Verify 24h automated tests vs. expert scientific review with reference climatologies. |
| 7 | `profile-quality-flags` | `argo-user-manual` | Page 77 (Reference Table 2a) | Run `python scripts/review_note.py profile-quality-flags`. Verify whole-profile quality letter grades A through F (A = 100% good, B = 75-99% good). |
| 8 | `adjusted-vs-raw-variables` | `argo-user-manual` | Page 19–20 (Section 2.3) | Run `python scripts/review_note.py adjusted-vs-raw-variables`. Verify recommendation that scientific analyses use `<PARAM>_ADJUSTED` in delayed mode. |
| 9 | `argopy-user-modes-overview` | `argopy-user-modes` | Section "User modes" | Run `python scripts/review_note.py argopy-user-modes-overview`. Verify research (delayed-mode only, QC=1), standard (QC 1 & 2), and expert (all data) modes. |
| 10 | `argo-data-policy-and-citation` | `wong2020` | Page 18 (Section 7) | Run `python scripts/review_note.py argo-data-policy-and-citation`. Verify public data access policy and dynamic monthly snapshot DOI structure (`10.17882/42182#snapshot`). |

---

## Sources Inventory Summary

- **Total defined sources**: 19
- **Retrieved & extracted locally**: 16 sources (5 PDFs, 9 HTML web pages, 2 Word `.docx` documents)
  1. `argo-user-manual` (PDF v3.44.0): 99 pages, 292,571 characters
  2. `argo-qc-ctd` (PDF v3.9): 118 pages, 233,322 characters
  3. `argo-qc-bgc` (PDF v1.1): 34 pages, 62,155 characters
  4. `argo-docs-index` (HTML): 8 sections, 5,386 characters
  5. `argo-home` (HTML): 24 sections, 10,700 characters
  6. `argo-how-floats-work` (DOCX): 3 sections, 3,715 characters
  7. `argo-faq` (DOCX): 18 sections, 12,661 characters
  8. `argo-data-gdacs` (HTML): 7 sections, 8,468 characters
  9. `wong2020` (PDF): 23 pages, 107,301 characters
  10. `roemmich2019` (PDF): 28 pages, 143,558 characters
  11. `teos10-site` (HTML): 3 sections, 8,504 characters
  12. `gsw-python` (HTML): 3 sections, 1,736 characters
  13. `gsw-sound-speed` (HTML): 3 sections, 2,723 characters
  14. `argopy-user-modes` (HTML): 8 sections, 36,318 characters
  15. `argopy-what-is-argo` (HTML): 5 sections, 9,447 characters
  16. `noaa-cpc-nino` (HTML): 2 sections, 7,150 characters

- **Not retrieved (owner must download manually)**: 3 sources
  1. `argo-gdac-doi` (`https://doi.org/10.17882/42182`):
     - *Issue*: DOI redirects to `seanoe.org` which is outside the strict allowed-hosts whitelist.
     - *Action for Owner*: Visit `https://doi.org/10.17882/42182` in your web browser, save the landing page HTML as `knowledge/sources/argo-gdac-doi.html`, update `knowledge/manifest.csv` with SHA-256 and status `present`, and run `python scripts/extract_sources.py`.
  2. `mld-deboyer2004` (`https://doi.org/10.1029/2004JC002378`):
     - *Issue*: Resolves to Wiley Online Library (`agupubs.onlinelibrary.wiley.com`), behind a commercial publisher paywall.
     - *Action for Owner*: Download the paper PDF ("Mixed layer depth over the global ocean: An examination of profile data and a profile-based climatology", de Boyer Montégut et al., 2004) through your institutional/university library, save to `knowledge/sources/mld-deboyer2004.pdf`, update `knowledge/manifest.csv`, and run `python scripts/extract_sources.py`.
  3. `teos10-manual` (`https://repository.oceanbestpractices.org/handle/11329/286`):
     - *Issue*: OceanBestPractices repository requires dynamic client-side JavaScript execution to access the PDF link.
     - *Action for Owner*: Download the IOC Manual 56 PDF directly from `https://teos-10.org/pubs/TEOS-10_Manual.pdf`, save as `knowledge/sources/teos10-manual.pdf`, update `knowledge/manifest.csv`, and run `python scripts/extract_sources.py`.

---

## Text Extraction Summary

- Total text extracted: **890,398 characters** across 16 files in `knowledge/text/`.
- Scanned / image-only / empty files: **0**. Every extracted file contains structured, searchable text with `=== PAGE n ===` or `=== SECTION: heading ===` boundary markers.

---

## Knowledge Gaps

1. **Mixed Layer Depth (MLD) Criterion (Topic 15)**:
   - Because `mld-deboyer2004` was behind a commercial paywall, drafting of the formal literature note for de Boyer Montégut et al. (2004) was deferred.
   - *Next step*: Once the owner places `mld-deboyer2004.pdf` into `knowledge/sources/` and runs extraction, a note citing the exact 0.2°C temperature difference and 0.03 kg/m³ potential density threshold should be added to `knowledge/notes/argo_notes.yaml`.
2. **GDAC DOI Snapshot Metadata**:
   - `argo-gdac-doi` details currently reference citations in Wong et al. (2020) and `argo-data-gdacs.html` until the SEANOE landing page HTML is placed in `knowledge/sources/`.

---

## Verification Policy

- **All notes derived from documents must be created with `verified: false` and `checked_on: ""`.**
- Agents (including Codex, Antigravity, or other assistants) are **never** permitted to mark document notes as `verified: true`.
- Only the human repository owner may verify a note after reviewing the original text using `python scripts/review_note.py <note_id>`.
- `scripts/check_knowledge.py` and `tests/test_knowledge.py` enforce this invariant in CI: any document-derived note marked `verified: true` will immediately fail automated tests unless approved by the owner.

---

## Suspicious Content Log

*(No suspicious content, prompt injections, or unauthorized instructions were encountered in any retrieved or extracted source text).*
