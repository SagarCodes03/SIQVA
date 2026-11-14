# Knowledge Base Status

Current status of the SIQVA trusted knowledge base preparation.

## Stage Status

- [x] **K0. Setup**: Directory structure created (`knowledge/sources`, `knowledge/text`, `knowledge/notes`), `.gitignore` updated, `knowledge/manifest.csv` initialized with 19 sources, `knowledge/README.md` created.
- [x] **K1. Retrieve missing sources**: Retrieved 9 web sources within allowed hosts with a 5s politeness delay and request caps; 3 sources could not be retrieved and require manual download by owner.
- [x] **K2. Extract text**: `scripts/extract_sources.py` created and verified. Extracted all 16 present sources into `knowledge/text/` with `=== PAGE n ===` and `=== SECTION: heading ===` markers.
- [x] **K3. Notes generated from our own code**: `scripts/build_own_notes.py` created and verified. Generates `knowledge/notes/own_generated.yaml` from code modules with regression test `tests/test_own_notes.py`.
- [x] **K4. Draft source-derived notes**: Drafted 23 grounded notes in `knowledge/notes/argo_notes.yaml` citing page/section numbers. All notes have `verified: false` and `checked_on: ""`.
- [x] **K5. Scope, questions, checker, review tool**: `knowledge/scope.md`, `knowledge/questions.jsonl` (40 dev questions), `scripts/check_knowledge.py`, `scripts/review_note.py`, and `tests/test_knowledge.py` created and verified.
- [ ] **K6. Status and finish**: Summary report, checklist for owner verification, push `task-knowledge`.

---

## Sources Summary (Stage K4)

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

- Not retrieved (owner must download by hand): 3
  1. `argo-gdac-doi` (`https://doi.org/10.17882/42182`): Redirects to `seanoe.org` (outside allowed hosts).
  2. `mld-deboyer2004` (`https://doi.org/10.1029/2004JC002378`): Redirects to Wiley Online Library (`agupubs.onlinelibrary.wiley.com`, commercial paywall).
  3. `teos10-manual` (`https://repository.oceanbestpractices.org/handle/11329/286`): OceanBestPractices repository requires client-side JavaScript execution to reach the IOC Manual 56 PDF.

---

## Source-Derived Notes Summary (Stage K4)

23 notes drafted in `knowledge/notes/argo_notes.yaml` covering:
1. `argo-one-paragraph`: Global array summary (source: `argopy-what-is-argo`)
2. `float-cycle-and-depth`: Standard 10-day park-and-profile cycle (source: `argo-how-floats-work`)
3. `qc-flag-scale`: Numerical QC flag scale 0–9 (source: `argo-user-manual` Page 76)
4. `data-modes-rad`: Real-time, adjusted, and delayed mode definitions (source: `argo-user-manual` Page 19-20)
5. `delayed-mode-timing`: 12-month lag rationale for delayed-mode calibration (source: `wong2020` Page 8)
6. `realtime-vs-delayed-qc`: Automated screening vs. expert climatology analysis (source: `wong2020` Page 8)
7. `profile-quality-flags`: Overall profile letter grades A–F (source: `argo-user-manual` Page 77)
8. `adjusted-vs-raw-variables`: Separation of raw vs. adjusted netCDF variables (source: `argo-user-manual` Page 19-20)
9. `argopy-user-modes-overview`: Research, standard, and expert user mode filtering (source: `argopy-user-modes`)
10. `argo-data-policy-and-citation`: Free data policy and dynamic DOI snapshot citations (source: `wong2020` Page 18)
11. `what-is-teos-10`: IOC Gibbs potential thermodynamic formulation (source: `teos10-site`)
12. `practical-vs-absolute-salinity`: Conductivity-based PSS-78 vs. mass-fraction g/kg salinity (source: `teos10-site`)
13. `conservative-temperature`: Potential enthalpy heat content conservation (source: `teos10-site`)
14. `gsw-sound-speed-inputs`: Inputs for 75-term sound speed calculation (source: `gsw-sound-speed`)
15. `noaa-cpc-nino-definitions`: Bounding boxes for Nino 1+2, 3, 3.4, and 4 (source: `noaa-cpc-nino`)
16. `argo-array-size-and-coverage`: 4000 active floats and 3°×3° spatial grid (source: `argopy-what-is-argo`)
17. `float-telemetry-and-surface`: Argos unidirectional vs. Iridium bidirectional satellite telemetry (source: `wong2020` Page 6)
18. `core-argo-parameters`: CTD physical parameters (pressure, temperature, conductivity) (source: `argo-how-floats-work`)
19. `bgc-argo-parameters`: Six core biogeochemical parameters (source: `argo-qc-bgc` Page 5)
20. `deep-argo-depth`: Abyssal sampling down to 6000 meters (source: `roemmich2019` Page 2)
21. `qc-flag-1-definition`: Criteria for flag 1 in real-time and delayed mode (source: `argo-user-manual` Page 76)
22. `qc-flag-4-definition`: Criteria for flag 4 bad data (source: `argo-user-manual` Page 76)
23. `argo-gdac-structure`: Dual mirror GDAC architecture (Coriolis and US GDAC) (source: `wong2020` Page 7)

All notes have `verified: false` and `checked_on: ""` awaiting owner verification.

---

## Suspicious Content Log

*(No suspicious content or injected prompts observed in retrieved files).*

---

## Knowledge Gaps

1. `mld-deboyer2004` (Topic 15 - Mixed Layer Depth Criterion): Skipped drafting the formal literature note for de Boyer Montégut et al. (2004) because the document was paywalled on Wiley Online Library. When the owner provides the PDF, a note citing the exact 0.2°C temperature threshold and 0.03 kg/m³ density criterion should be added.
2. `argo-gdac-doi`: GDAC citation details currently cite Wong et al. (2020) and `argo-data-gdacs.html` until the owner downloads the SEANOE metadata landing page.
