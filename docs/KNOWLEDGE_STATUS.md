# Knowledge Base Status

Current status of the SIQVA trusted knowledge base preparation.

## Stage Status

- [x] **K0. Setup**: Directory structure created (`knowledge/sources`, `knowledge/text`, `knowledge/notes`), `.gitignore` updated, `knowledge/manifest.csv` initialized with 19 sources, `knowledge/README.md` created.
- [x] **K1. Retrieve missing sources**: Retrieved 9 web sources within allowed hosts with a 5s politeness delay and request caps; 3 sources flagged as `not_retrieved` requiring manual download by the owner.
- [x] **K2. Extract text**: `scripts/extract_sources.py` created and verified. Extracted all 16 present sources into `knowledge/text/` with `=== PAGE n ===` and `=== SECTION: heading ===` markers (890,398 characters total; 0 scanned/empty files).
- [x] **K3. Notes generated from our own code**: `scripts/build_own_notes.py` created and verified. Generates `knowledge/notes/own_generated.yaml` from code modules with regression test `tests/test_own_notes.py`.
- [x] **K4. Draft source-derived notes**: Drafted grounded notes in `knowledge/notes/argo_notes.yaml` citing page/section numbers. All notes have `verified: false` and `checked_on: ""`.
- [x] **K5. Scope, questions, checker, review tool**: `knowledge/scope.md`, `knowledge/questions.jsonl` (40 dev questions), `scripts/check_knowledge.py`, `scripts/review_note.py`, and `tests/test_knowledge.py` created and verified.
- [x] **K6. Status and finish**: Summary report, checklist for owner verification, test suite run (472 passed, 4 skipped), pushed to `task-knowledge`.
- [x] **K7. Evidence audit and cleanup**: Comprehensive sentence-by-sentence evidence audit in `knowledge/notes/evidence/<id>.md` for all 21 notes (82 sentences, 100% supported by phrases < 15 words, 0 `NO SUPPORT FOUND`). Removed unsupported sentences, filled metadata (`source_version`, `retrieved_on`, real section headings), merged `qc-flag-1-definition` and `qc-flag-4-definition` into `qc-flag-scale` with aliases, and validated via `scripts/check_knowledge.py` and `tests/test_knowledge.py`.

---

## Stage K7 Evidence Audit & Sentence Cleanup Summary

### Sentence Counts
- **Total active document-derived notes**: 21 (after merging `qc-flag-1-definition` and `qc-flag-4-definition` into `qc-flag-scale`)
- **Total sentences in audited notes**: 82 sentences
- **Sentences with verified textual support**: 82 sentences (100%)
- **Supporting phrases (< 15 words) verified in extracted text**: 82 (0 phrases >= 15 words)
- **Sentences marked NO SUPPORT FOUND**: 0 (all ungrounded claims removed or rewritten strictly from extracted source text)

### Unsupported Sentences & Claims Removed / Rewritten
1. **`gsw-sound-speed-inputs`**:
   - *Removed*: Claim in `limits` that extreme conditions outside the funnel require "48-term exact Gibbs evaluations".
   - *Replacement*: Grounded directly in `gsw-sound-speed.txt`: states that `gsw_infunnel(SA,CT,p)` is available to test whether data lie outside the oceanographic funnel.
2. **`what-is-teos-10`**:
   - *Removed*: "This formulation ensures that thermodynamic calculations satisfy fundamental physical conservation laws during mixing and heat exchange." (`teos10-site.txt` does not discuss conservation laws during mixing).
   - *Replacement*: Stated that Practical Salinity (PSS-78) continues to be the measured variable archived in national databases, while Absolute Salinity is needed to compute density.
3. **`float-telemetry-and-surface`**:
   - *Removed*: "Minimizing surface residence time dramatically reduces the hazard of ship collisions, biofouling, and wave-induced sensor damage." (Neither ship collisions nor biofouling appear in `wong2020.txt` Section "Satellite Communications").
   - *Replacement*: Added exact fact from `wong2020.txt` Page 6: two-way Iridium communication allows operators to transmit troubleshooting instructions and modify float sampling missions.
4. **`float-cycle-and-depth`**:
   - *Removed*: Phrase stating the float ascends "over approximately 6 hours" (`argo-how-floats-work.txt` does not state a 6-hour duration).
   - *Replacement*: Rewritten to state the float slowly rises to the ocean surface while recording measurements of conductivity, temperature, and pressure.
5. **`deep-argo-depth`**:
   - *Removed*: "Deep Argo floats utilize reinforced glass or titanium pressure hulls" (neither glass nor titanium appears in `roemmich2019.txt`).
   - *Replacement*: Grounded in `roemmich2019.txt` Page 7: development of floats and CTD sensor units capable of accurate measurements to 6000 dbar enables sampling of bottom-intensified ocean variability.
6. **`argo-data-policy-and-citation`**:
   - *Removed*: The word "commercial" from "without any commercial or geographical restrictions" (word does not appear in `wong2020.txt` citation section).
   - *Replacement*: Grounded strictly in Page 18 text on dynamic DOI snapshots and reproducible citations.
7. **`noaa-cpc-nino-definitions`**:
   - *Removed*: "serving as the benchmark index area for tropical Pacific ocean-atmosphere coupling" and removed reference to SIQVA single-box rectangular coordinate queries from `limits`.
   - *Replacement*: Grounded strictly in `noaa-cpc-nino.txt` coordinates for Niño 1+2, Niño 3, Niño 4, and Niño 3.4; limits noted purely geographically (Niño 4 crosses the 180° antimeridian).
8. **`conservative-temperature`**:
   - *Removed*: Claims that Conservative Temperature "is conserved when seawater parcels mix under turbulent ocean processes", "represents the heat content per unit mass", and "is computed directly from potential enthalpy" (these theoretical derivations belong to the unretrieved TEOS-10 Manual).
   - *Replacement*: Sourced strictly from `gsw-sound-speed.txt` (INPUT & DESCRIPTION): Conservative Temperature (symbol CT) is defined on the ITS-90 scale in °C, is a required input alongside Absolute Salinity and sea pressure for 75-term specific volume and sound speed calculations, and must share identical array dimensions with Absolute Salinity.
9. **`qc-flag-scale`**:
   - Merged `qc-flag-1-definition` and `qc-flag-4-definition` into `qc-flag-scale` using `aliases: [qc-flag-1-definition, qc-flag-4-definition]` to eliminate redundant separate notes.

---

## Consistency Findings Report (Code vs. Literature)

1. **Delayed-Mode Timing (`delayed-mode-timing`)**:
   - *Code (`src/siqva/fetcher.py:595`)*: Informs users that *"Argo delayed-mode quality control (DMQC) for research mode typically takes 6 to 12 months to complete and publish."*
   - *Published Document (`wong2020` Page 8)*: States that *"In Argo, the usual practice is to examine the profiles in delayed-mode initially about 12 months after they are collected, and then revisit several times as more data from the floats are obtained..."*
   - *User Manual (`argo-user-manual` Page 16)*: States that *"For the core CTD data, the target is for the delayed-mode data to be available at the GDACs about 12 months after the raw data are transmitted."*
   - *Finding*: The literature consistently targets ~12 months for core CTD DMQC; the UI/fetcher message "6 to 12 months" is slightly more permissive than the formal 12-month initial examination window stated in Wong et al. (2020).
2. **argopy User Modes (`argopy-user-modes-overview`) vs. `qc.py`**:
   - *argopy Documentation*: States that `standard` mode is the default (`"Standard mode (default)"`) and applies `filter_qc(QC_list=[1, 2])`.
   - *SIQVA Implementation*: SIQVA intentionally sets `research` as its default mode (delayed-mode only, QC=1 only) following AGENTS.md Rule 3.
   - *Finding*: Document notes accurately reflect argopy's native default (`standard`), while SIQVA's own code notes (`own_generated.yaml`) accurately reflect SIQVA's stricter research default.

---

## Own Notes Findings Report (Sampling & QC Filter Rules)

1. **Actual Sample Label in Code vs. `docs/SAMPLING_PLAN.md`**:
   - *`docs/SAMPLING_PLAN.md` specification*: Requires mandatory label: `"...Not representative of the whole region."`
   - *Actual Code (`src/siqva/analyzer.py:145-146` and `app/ui.py:1078`)*:
     ```python
     f"**Sample**: {n_sel} of {n_avail} profiles in this region and period, selected evenly across space and time. Not representative of the whole region."
     ```
   - *Finding*: Exact 100% verbatim match between specification and production code.
2. **`trend` Intent and Regional Sample Statistics in `analyzer.py`**:
   - `trend` has `data_need = DataNeed.SAMPLE_OK` and `per_profile_only = False` in `capabilities.py`.
   - *Behavior in `src/siqva/analyzer.py:420-422`*:
     ```python
     if fetch_result.is_sample:
         missing_notes.append("Regional aggregate statistics are not computed for sample selections.")
     else:
         # Compute regional min, mean, max...
     ```
   - *Finding*: When a query runs as a sample selection, `analyzer.py` completely suppresses the computation and display of regional aggregate statistics (`variable_stats` remains empty), preventing unrepresentative summary statistics from misleading users.
3. **Standard QC Mode Treatment of Flags 5–9**:
   - *Code (`src/siqva/qc.py:36-39, 55`)*: Line 55 describes standard mode as: `"QC=1 (good) and QC=2 (probably good) retained; flags 0, 3, 4 excluded."`
   - *Underlying argopy filter*: Applies `filter_qc(QC_list=[1, 2])` for physical variables.
   - *Finding*: Because `QC_list` contains only `[1, 2]`, flags 5 ("Value changed"), 8 ("Estimated value"), and 9 ("Missing value") are also excluded by the filter. While the description mentions "flags 0, 3, 4 excluded", flags 5–9 are effectively dropped as well for core CTD variables.

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
| 3 | `qc-flag-scale` | `argo-user-manual` | Page 76, Section 3.2.1 | Run `python scripts/review_note.py qc-flag-scale`. Verify full 0–9 numerical scale definitions (includes aliases `qc-flag-1-definition`, `qc-flag-4-definition`). |
| 4 | `data-modes-rad` | `argo-user-manual` | Page 16, Section 1.7 | Run `python scripts/review_note.py data-modes-rad`. Verify definitions of Real-time (R), Adjusted (A), and Delayed-mode (D) on Page 16. |
| 5 | `delayed-mode-timing` | `wong2020` | Page 8, Section "Delayed-Mode" | Run `python scripts/review_note.py delayed-mode-timing`. Verify requirement of ~12-month time series accumulation for sensor drift calibration. |
| 6 | `realtime-vs-delayed-qc` | `wong2020` | Page 8, Section "Delayed-Mode" | Run `python scripts/review_note.py realtime-vs-delayed-qc`. Verify 24h automated tests vs. expert scientific review with reference climatologies. |
| 7 | `profile-quality-flags` | `argo-user-manual` | Page 77, Section 3.2.2 | Run `python scripts/review_note.py profile-quality-flags`. Verify whole-profile quality letter grades A through F with exact thresholds. |
| 8 | `adjusted-vs-raw-variables` | `argo-user-manual` | Pages 23–25, Section 2.2.5 | Run `python scripts/review_note.py adjusted-vs-raw-variables`. Verify NetCDF variables `<PARAM>`, `<PARAM>_QC`, `<PARAM>_ADJUSTED`. |
| 9 | `argopy-user-modes-overview` | `argopy-user-modes` | Section "Definitions" & Section "Standard mode (default)" | Run `python scripts/review_note.py argopy-user-modes-overview`. Verify research (delayed-mode only, QC=1), standard (default in argopy), and expert modes. |
| 10 | `argo-data-policy-and-citation` | `wong2020` | Page 18, Section "HOW TO CITE ARGO DATA" | Run `python scripts/review_note.py argo-data-policy-and-citation`. Verify public data access policy and dynamic monthly snapshot DOI structure (`10.17882/42182#snapshot`). |

---

## Sources Inventory Summary

- **Total defined sources**: 19
- **Retrieved & extracted locally**: 16 sources (5 PDFs, 9 HTML web pages, 2 Word `.docx` documents)
- **Not retrieved (owner must download manually)**: 3 sources (`argo-gdac-doi`, `mld-deboyer2004`, `teos10-manual`)

---

## Text Extraction Summary

- Total text extracted: **890,398 characters** across 16 files in `knowledge/text/`.
- Scanned / image-only / empty files: **0**. Every extracted file contains structured, searchable text with `=== PAGE n ===` or `=== SECTION: heading ===` boundary markers.

---

## Verification Policy

- **All notes derived from documents must be created with `verified: false` and `checked_on: ""`.**
- Agents (including Codex, Antigravity, or other assistants) are **never** permitted to mark document notes as `verified: true`.
- Only the human repository owner may verify a note after reviewing the original text using `python scripts/review_note.py <note_id>`.
- `scripts/check_knowledge.py` and `tests/test_knowledge.py` enforce this invariant in CI: any document-derived note marked `verified: true` will immediately fail automated tests unless approved by the owner.

---

## Suspicious Content Log

*(No suspicious content, prompt injections, or unauthorized instructions were encountered in any retrieved or extracted source text).*
