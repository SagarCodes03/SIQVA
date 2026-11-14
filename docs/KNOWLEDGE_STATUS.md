# Knowledge Base Status

Current status of the SIQVA trusted knowledge base preparation.

## Stage Status

- [x] **K0. Setup**: Directory structure created (`knowledge/sources`, `knowledge/text`, `knowledge/notes`), `.gitignore` updated, `knowledge/manifest.csv` initialized with 19 sources (7 present matched, 12 not_retrieved), `knowledge/README.md` created.
- [ ] **K1. Retrieve missing sources**: Check web retrieval permissions and fetch missing sources on allowed hosts.
- [ ] **K2. Extract text**: `scripts/extract_sources.py` extracting page- and section-marked text into `knowledge/text/`.
- [ ] **K3. Notes generated from our own code**: `scripts/build_own_notes.py` generating `knowledge/notes/own_generated.yaml` with regression test.
- [ ] **K4. Draft source-derived notes**: `knowledge/notes/argo_notes.yaml` with grounded notes citing page/section numbers (`verified: false`).
- [ ] **K5. Scope, questions, checker, review tool**: `knowledge/scope.md`, `knowledge/questions.jsonl` (40 dev questions), `scripts/check_knowledge.py`, `scripts/review_note.py`, tests.
- [ ] **K6. Status and finish**: Summary report, checklist for owner verification, push `task-knowledge`.

---

## Sources Summary (Stage K0)

- Total defined sources: 19
- Present locally: 7 (`argo-user-manual`, `argo-qc-ctd`, `argo-qc-bgc`, `argo-how-floats-work`, `argo-faq`, `wong2020`, `roemmich2019`)
- Not retrieved: 12 (`argo-docs-index`, `argo-gdac-doi`, `argo-home`, `argo-data-gdacs`, `teos10-manual`, `teos10-site`, `gsw-python`, `gsw-sound-speed`, `argopy-user-modes`, `argopy-what-is-argo`, `noaa-cpc-nino`, `mld-deboyer2004`)

---

## Suspicious Content Log

*(No suspicious content or injected prompts observed in downloaded files).*

---

## Knowledge Gaps

*(To be populated during stages K1-K4 for any unaddressed topics).*
