# SIQVA Full System & Performance Audit Report

This report evaluates SIQVA across performance, scientific rigor, architectural guarantees, code quality, and maintainability. It is written in plain English, defining key technical terms on first use.

## Review Checklist

- [x] **Phase 0: Inventory** (Branches, commits, sizes, line counts)
- [ ] **Phase 1: Slowdown Regression Hunt** (Root-cause timing, profile, version comparison)
- [ ] **Phase 2: Promise Audit** (LLM data leaks, deterministic numbers, scope, routing)
- [ ] **Phase 3: Correctness** (Chunking, operations, physics, caches, dates, coordinates)
- [ ] **Phase 4: Reliability and Safety** (Crash paths, concurrency, security, tracebacks)
- [ ] **Phase 5: Tests** (Test suite health, coverage, mock validity, execution speed)
- [ ] **Phase 6: Docs, Dependencies, Hygiene** (Spec mismatches, dead code, dependencies)
- [ ] **Phase 7: UI and Plots** (Render pipelines, layout wastes, visual clarity)
- [ ] **Phase 8: Benchmark Honesty** (Evaluation integrity, metric validation)
- [ ] **Phase 9: Synthesis** (Top findings, performance breakdown, prioritized 12-step plan)
- [ ] **Phase 10: Finish** (Test suite validation, branch verification, push)

---

## Phase 0: Inventory

### 1. Git Repository & Branch Status
- **Current Branch:** `review-full-audit` (branched from local `siqva-finish` directly after merging remote `origin/siqva-finish`).
- **Remote Tracking Status:**
  - `origin/main` is merged with `feature/ui-updates` (commit `f168d13`) and earlier pull requests.
  - Branches merged into `main`: `prototype-v1`, `siqva-rename-and-fixes`, `task-a-crash-safety`, `task-c-parser-history`, `task-q2-crash-safety`, `wip-task-b-partial`.
  - Unmerged remote branches: `siqva-finish` (which contains release `v0.9` and recent safety fixes), `task-q3-pacific-regions`.
- **Repository Size on Disk:** 45.69 MiB (git database: 3,175 objects).

### 2. Commits & Authorship Since Tag `done-Q14`

| Hash | Author | Date | Summary | Key Files Modified | Size Change |
|---|---|---|---|---|---|
| `864ac91` | Sagar Gowda H | 2026-11-09 | Merge remote-tracking branch origin/siqva-finish | Resolved merge conflicts in `llm_parser.py`, `test_ui_smoke.py` | Merge |
| `ba4d149` | Sangeen | 2026-11-09 | Release v0.9: Enterprise minimalist UI overhaul, multi-year query support, modal date fixes | `app/ui.py`, `old_ui_0.1.py`, `chunking.py`, `fetcher.py`, `validator.py`, `rules_parser.py` | +2214 / -392 |
| `d625a03` | Sangeen | 2026-11-08 | fix(ui): surface depth default for map intent, auto-shrink button, and sidebar layout aesthetics | `app/ui.py`, `parser.py`, `tests/test_parser.py` | +177 / -81 |
| `f168d13` | Sangeen | 2026-11-08 | Merge branch 'feature/ui-updates' into main | Merges extended plots feature branch | Merge |
| `9db4582` | Sagar Gowda H | 2026-11-07 | docs: update task queue with completed fixes | `docs/TASK_QUEUE.md` | +4 / -0 |
| `938d3f5` | Sagar Gowda H | 2026-11-07 | Docs and safety verification | `AGENTS.md`, `CODE_FLOW.md`, `tests/test_safety_checks.py` | +108 / -7 |
| `015f86c` | Sagar Gowda H | 2026-11-07 | Honest benchmark labelling and split field | `benchmark/run_eval.py`, `benchmark/questions.jsonl`, `test_benchmark.py` | +176 / -35 |
| `6e8794d` | Sagar Gowda H | 2026-11-07 | Glossary: utf-8 loading, verified flag | `data/glossary.json`, `glossary.py`, `test_glossary.py`, `ui.py` | +279 / -67 |
| `53e5445` | Sagar Gowda H | 2026-11-07 | Fix UI smoke test paths | `test_ui_smoke.py`, `llm_parser.py`, path fixtures across tests | +64 / -28 |
| `164e761` | Sagar Gowda H | 2026-11-07 | Merge pull request #9 from SagarCodes03/siqva-finish | Pull request merge | Merge |
| `3e5990f` | Sangeen | 2026-11-07 | feat(ui): add extended oceanographic plots and interactive terminal features | `app/ui.py`, `plots.py`, `pipeline.py`, `rules_parser.py`, `spec.py` | +1454 / -59 |
| `dff049f` | Sagar Gowda H | 2026-11-06 | Merge pull request #8 from SagarCodes03/task-q3-pacific-regions | Task Q3 merge | Merge |

#### Commit Touch Analysis on Critical Modules
- `src/siqva/fetcher.py`: Touched in `ba4d149` (added `fetch_key` parameter support).
- `src/siqva/chunking.py`: Heavily modified in `ba4d149` (rewrite of calendar chunking & multi-year fetching).
- `src/siqva/plots.py`: Heavily expanded in `3e5990f` (+848 lines: added multi-trace overlays, 3D scatters, contour interpolations).
- `src/siqva/pipeline.py`: Modified in `3e5990f` (forced plotting triggers) and `ba4d149` (pipeline status wrappers).
- `app/ui.py`: Completely overhauled across `3e5990f`, `d625a03`, and `ba4d149`.
- Added backup file `old_ui_0.1.py` (+1651 lines, 73 KB) directly into the tracked repository.

### 3. Tracked File Sizes & Binary Audit

**15 Largest Tracked Files in the Repository:**
1. `app/ui.py`: 79,382 bytes (~2,100 lines)
2. `old_ui_0.1.py`: 73,279 bytes (1,651 lines - *untracked dead backup file committed*)
3. `src/siqva/plots.py`: 60,852 bytes (1,402 lines)
4. `docs/CODE_FLOW.md`: 48,403 bytes
5. `src/siqva/fetcher.py`: 37,148 bytes (791 lines)
6. `tests/test_fetcher.py`: 31,307 bytes
7. `tests/test_physics.py`: 27,811 bytes
8. `app/old_ui.py`: 27,540 bytes (*another older UI backup file*)
9. `src/siqva/analyzer.py`: 24,705 bytes (472 lines)
10. `src/siqva/rules_parser.py`: 24,381 bytes (626 lines)
11. `tests/fixtures/sample_argo_expert.parquet`: 22,639 bytes (*binary test fixture*)
12. `src/siqva/card.py`: 22,495 bytes (529 lines)
13. `docs/AUDIT_REPORT.md`: 21,192 bytes
14. `tests/test_rules_parser.py`: 19,118 bytes
15. `src/siqva/physics.py`: 18,826 bytes (379 lines)

**Binary Objects in Git History:**
- Only small test fixtures (`tests/fixtures/sample_argo_expert.parquet` at 22 KB) exist. No massive accidental parquet dump or SQLite database files were committed.

### 4. Source Lines per Module (`src/siqva/`)

| Module | Lines of Code | Primary Role |
|---|---|---|
| `plots.py` | 1,402 | Plotly visualization rendering (profiles, T-S, trajectories, maps, contours) |
| `fetcher.py` | 791 | Data retrieval via argopy, Parquet caching, fetch key generation |
| `rules_parser.py` | 626 | Deterministic regex/dictionary parser for dates, regions, variables |
| `card.py` | 529 | Query card generation, SQLite persistence, script builder |
| `analyzer.py` | 472 | Dataset statistics (coverage, summary numbers, platform counts) |
| `gazetteer.py` | 428 | Geographic bounding box dictionaries & fuzzy matching |
| `llm_parser.py` | 385 | Ollama 3B constrained JSON schema parser fallback |
| `physics.py` | 379 | On-demand TEOS-10 calculations (MLD, ILD, TCHP, sound speed) |
| `parser.py` | 339 | Hybrid parser orchestrator & clarification handler |
| `chunking.py` | 309 | Large query calendar-month splitting and assembly |
| `pipeline.py` | 260 | Top-level execution pipeline orchestrating fetch -> analysis -> plots |
| `qc.py` | 199 | Quality control flag filtering (Research vs Standard vs Expert) |
| `operations.py` | 190 | Deterministic math operations (mean, min, max, anomaly) |
| `spec.py` | 182 | Pydantic QuerySpec schemas & Enums |
| `validator.py` | 171 | Spatial/temporal boundary checking, size caps, variable allow-list |
| `glossary.py` | 167 | Verified oceanographic term dictionary loader |
| `router.py` | 122 | Intent classification (DATA_FETCH, OPERATION, COMPARE, GLOSSARY) |
| `__init__.py` | 121 | Library public interface definitions |
| `followup.py` | 111 | Conversational session state and query delta adjustments |
| `comparison.py` | 88 | Dual dataset comparative statistics |
| `interpretation.py` | 47 | Deterministic "Understood as" query provenance formatter |
| **Total Core Code** | **6,748** | |
