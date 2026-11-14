# Knowledge Base Status

Current status of the SIQVA trusted knowledge base preparation.

## Stage Status

- [x] **K0. Setup**: Directory structure created (`knowledge/sources`, `knowledge/text`, `knowledge/notes`), `.gitignore` updated, `knowledge/manifest.csv` initialized with 19 sources, `knowledge/README.md` created.
- [x] **K1. Retrieve missing sources**: Retrieved 9 web sources within allowed hosts with a 5s politeness delay and request caps; 3 sources could not be retrieved and require manual download by owner.
- [ ] **K2. Extract text**: `scripts/extract_sources.py` extracting page- and section-marked text into `knowledge/text/`.
- [ ] **K3. Notes generated from our own code**: `scripts/build_own_notes.py` generating `knowledge/notes/own_generated.yaml` with regression test.
- [ ] **K4. Draft source-derived notes**: `knowledge/notes/argo_notes.yaml` with grounded notes citing page/section numbers (`verified: false`).
- [ ] **K5. Scope, questions, checker, review tool**: `knowledge/scope.md`, `knowledge/questions.jsonl` (40 dev questions), `scripts/check_knowledge.py`, `scripts/review_note.py`, tests.
- [ ] **K6. Status and finish**: Summary report, checklist for owner verification, push `task-knowledge`.

---

## Sources Summary (Stage K1)

- Total defined sources: 19
- Present locally: 16
  1. `argo-user-manual` (`Argo User’s Manual.pdf` - PDF v3.44.0)
  2. `argo-qc-ctd` (`Argo Quality Control Manual.pdf` - PDF v3.9)
  3. `argo-qc-bgc` (`Argo QC Manual for Biogeochemical Data.pdf` - PDF v1.1)
  4. `argo-docs-index` (`argo-docs-index.html` - HTML documentation index)
  5. `argo-home` (`argo-home.html` - HTML UCSD portal homepage)
  6. `argo-how-floats-work` (`How do floats work.docx` - DOCX float mission)
  7. `argo-faq` (`Frequently Asked Questions.docx` - DOCX FAQ)
  8. `argo-data-gdacs` (`argo-data-gdacs.html` - HTML GDAC server access)
  9. `wong2020` (`fmars-07-00700.pdf` - PDF Frontiers 2020 review)
  10. `roemmich2019` (`fmars-06-00439.pdf` - PDF Frontiers 2019 OceanObs vision)
  11. `teos10-site` (`teos10-site.html` - HTML TEOS-10 website)
  12. `gsw-python` (`gsw-python.html` - HTML GSW-Python toolbox)
  13. `gsw-sound-speed` (`gsw-sound-speed.html` - HTML TEOS-10 sound speed documentation)
  14. `argopy-user-modes` (`argopy-user-modes.html` - HTML user mode guide)
  15. `argopy-what-is-argo` (`argopy-what-is-argo.html` - HTML Argo overview)
  16. `noaa-cpc-nino` (`noaa-cpc-nino.html` - HTML NOAA CPC Nino indices)

- Not retrieved (owner must download by hand): 3
  1. `argo-gdac-doi` (`https://doi.org/10.17882/42182`): Redirects to `seanoe.org` which is outside the allowed hosts list.
  2. `mld-deboyer2004` (`https://doi.org/10.1029/2004JC002378`): Redirects to Wiley Online Library (`agupubs.onlinelibrary.wiley.com`), a commercial paywall outside allowed hosts.
  3. `teos10-manual` (`https://repository.oceanbestpractices.org/handle/11329/286`): OceanBestPractices page is an Angular single-page application requiring JavaScript execution to obtain the IOC Manual 56 PDF.

---

## Suspicious Content Log

*(No suspicious content or injected prompts observed in retrieved files).*

---

## Knowledge Gaps

1. `mld-deboyer2004`: Full text of de Boyer Montégut et al. (2004) was not retrieved due to Wiley publisher paywall. Notes requiring specific MLD mathematical threshold citations must rely on definitions verified in our code or wait for owner manual download.
2. `argo-gdac-doi`: GDAC citation details will rely on Wong et al. (2020) and `argo-data-gdacs.html` until owner downloads the SEANOE metadata landing page.
