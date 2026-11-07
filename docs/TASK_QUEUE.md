# SIQVA Task Queue

Resume instruction for future sessions:
> "Read docs/TASK_QUEUE.md and continue with the first unchecked task."

| Task | Description | Status / Notes |
| :--- | :--- | :--- |
| [x] **Q1** | Finish the Task C branch (investigate 146 profiles vs 100 cap, pytest, push task-c-parser-history, PR info, docs drift check) | DONE (commit `b801808`, 198 passed) |
| [x] **Q2** | Crash and safety fixes (SQLite closing, Ollama fast failure, HTML escaping, gsw guard in plots, DECISIONS.md entries) | DONE (commit `6c32b52`, tag `done-Q2`, 199 passed) |
| [x] **Q3** | Pacific cost messages and regions (investigate gazetteer, actionable oversized message, named Pacific sub-regions, Pacific warning) | DONE (commit `9263d22`, tag `done-Q3`, 222 passed) |
| [x] **Q4** | Cleanup and safety net (dead code in fetcher, tz-aware UTC, requirements.txt, all-module import test, AppTest smoke test, docs sync) | DONE (tag `done-Q4`, 241 passed) |
| [x] **Q3b** | Large-query chunking (calendar-month chunking under 15,000 cap, row/chunk limits, shared caching, assembly, tests) | DONE (tag `done-Q3b`, 252 passed) |
| [x] **Q5** | Operations core for data questions (OperationSpec, execute statistics, deterministic answer template, no LLM, hand-computed tests) | DONE (tag `done-Q5`, 260 passed) |
| [x] **Q8** | Glossary mechanism (glossary.py, data/glossary.json, exact/fuzzy lookup, source attribution, no definitions written, guide) | DONE (tag `done-Q8`, 268 passed) |
| [ ] **Q6** | Router and chat interface (route() classifier, constrained fallback, monthly fetch/cache, st.chat_message UI, tests) | Pending |
| [ ] **Q7** | Follow-ups and meta questions (ConversationState, conversational edits, meta queries from card/state, tests) | Pending |
| [ ] **Q9** | Comparison questions (dual OperationSpecs execution, difference reporting without anomaly claims, router detection, tests) | Pending |
| [ ] **Q10** | Cold start (example gallery from JSON, non-blocking Ollama background warm-up, st.status progress stages, tests) | Pending |
| [ ] **Q11** | History reload and privacy (cache-based plot reload, session ID isolation, privacy docs/tests) | Pending |
| [ ] **Q13** | Benchmark infrastructure (benchmark/questions.jsonl, run_eval.py runner, accuracy/latency scoring, tests) | Pending |
| [ ] **Q14** | Documentation (comprehensive README.md, AGENTS.md, CODE_FLOW.md, limitations, reproducible query cards) | Pending |
