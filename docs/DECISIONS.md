# Architecture & Implementation Decisions

Format: `Date | Task | Decision | Reason`

- 2026-11-07 | Q2 | Retain conservative rejection for unquantified relative date phrases ("last month", "recent") requiring clarification; allow only explicit numeric counts ("past N days/months") with `today` anchor | Matches AGENTS.md principle that date ranges are never guessed when ambiguous.
- 2026-11-07 | Q2 | Research-mode 146 profiles returned with DEFAULT_MAX_PROFILE_COUNT=100 because snapshot coverage was NOT_COVERED/PARTIAL, so profile ceiling guard was skipped and profile_count_verified was set to False | Pre-fetch count ceiling applies strictly when snapshot coverage is FULL.
- 2026-11-07 | Q4 | Removed unused FastAPI/uvicorn dependencies and pinned all installed packages in requirements.txt (including gsw); updated AGENTS.md | No api.py exists or is planned for Streamlit UI architecture.

