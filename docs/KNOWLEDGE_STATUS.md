# Knowledge Base Status

Current status of the SIQVA trusted knowledge base preparation.

## Stage Status

- [x] **K0. Setup**: Directory structure created (`knowledge/sources`, `knowledge/text`, `knowledge/notes`), `.gitignore` updated, `knowledge/manifest.csv` initialized with 19 sources, `knowledge/README.md` created.
- [x] **K1. Retrieve missing sources**: Retrieved 9 web sources within allowed hosts with a 5s politeness delay and request caps; 3 sources could not be retrieved and require manual download by owner.
- [x] **K2. Extract text**: `scripts/extract_sources.py` created and verified. Extracted all 16 present sources into `knowledge/text/` with `=== PAGE n ===` and `=== SECTION: heading ===` markers.
- [ ] **K3. Notes generated from our own code**: `scripts/build_own_notes.py` generating `knowledge/notes/own_generated.yaml` with regression test.
- [ ] **K4. Draft source-derived notes**: `knowledge/notes/argo_notes.yaml` with grounded notes citing page/section numbers (`verified: false`).
- [ ] **K5. Scope, questions, checker, review tool**: `knowledge/scope.md`, `knowledge/questions.jsonl` (40 dev questions), `scripts/check_knowledge.py`, `scripts/review_note.py`, tests.
- [ ] **K6. Status and finish**: Summary report, checklist for owner verification, push `task-knowledge`.

---

## Sources Summary (Stage K2)

- Total defined sources: 19
- Present locally & extracted: 16
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

- Scanned / Empty Check: Zero files flagged as scanned or empty. All 16 files contain full machine-readable text with intact section/page markers.

- Not retrieved (owner must download by hand): 3
  1. `argo-gdac-doi` (`https://doi.org/10.17882/42182`): Redirects to `seanoe.org` (outside allowed hosts).
  2. `mld-deboyer2004` (`https://doi.org/10.1029/2004JC002378`): Redirects to Wiley Online Library (`agupubs.onlinelibrary.wiley.com`, commercial paywall).
  3. `teos10-manual` (`https://repository.oceanbestpractices.org/handle/11329/286`): OceanBestPractices repository requires client-side JavaScript execution to reach the IOC Manual 56 PDF.

---

## Suspicious Content Log

*(No suspicious content or injected prompts observed in retrieved files).*

---

## Knowledge Gaps

1. `mld-deboyer2004`: Full text of de Boyer Montégut et al. (2004) was not retrieved due to publisher paywall. Notes requiring specific MLD threshold citations must rely on definitions verified in our code or wait for owner manual download.
2. `argo-gdac-doi`: GDAC citation details rely on Wong et al. (2020) and `argo-data-gdacs.html` until owner downloads the SEANOE metadata landing page.
