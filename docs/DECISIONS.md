# Architecture & Implementation Decisions

Format: `Date | Task | Decision | Reason`

- 2026-11-07 | Q2 | Retain conservative rejection for unquantified relative date phrases ("last month", "recent") requiring clarification; allow only explicit numeric counts ("past N days/months") with `today` anchor | Matches AGENTS.md principle that date ranges are never guessed when ambiguous.
- 2026-11-07 | Q2 | Research-mode 146 profiles returned with DEFAULT_MAX_PROFILE_COUNT=100 because snapshot coverage was NOT_COVERED/PARTIAL, so profile ceiling guard was skipped and profile_count_verified was set to False | Pre-fetch count ceiling applies strictly when snapshot coverage is FULL.
- 2026-11-07 | Q4 | Removed unused FastAPI/uvicorn dependencies and pinned all installed packages in requirements.txt (including gsw); updated AGENTS.md | No api.py exists or is planned for Streamlit UI architecture.
- 2026-11-07 | Q3b | Decompose multi-month queries exceeding 15,000 cost cap into calendar months up to SIQVA_MAX_CHUNKS (default 24); refuse if any single month exceeds cap or total rows exceed SIQVA_MAX_TOTAL_ROWS (3,000,000) | Ensures bounded ERDDAP load, shared monthly Parquet caching across queries, and memory safety.
- 2026-11-07 | Q5 | Implement OperationSpec and deterministic calculation templates in operations.py with zero LLM imports | Guarantees all numbers in answers come strictly from code without LLM hallucination.
- 2026-11-07 | Q8 | Glossary entries loaded strictly from data/glossary.json with mandatory peer-reviewed scientific citations; no agent-authored definitions | Prevents unverified or hallucinated physical oceanography definitions.
- 2026-11-07 | Q6 | Router uses rules-first classification without LLM fallback for GLOSSARY and META intents; DATA_FETCH, OPERATION, COMPARISON always go through run() pipeline | LLM never sees routed glossary text or meta card data; determinism preserved.





