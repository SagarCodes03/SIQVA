"""Word-level text streaming and pacing for chat responses (U2).

Provides:
- Markdown-aware word-level chunking preserving links, code spans, code blocks, and table rows.
- Deterministic pacing with configurable words-per-second and min/max duration bounds.
- Injectable sleep function for deterministic testability without global sleep monkeypatching.
- Feature toggle via environment variable (SIQVA_STREAM) and session state.
"""

from __future__ import annotations

import os
import re
import time
from typing import Callable, Iterator, Optional

# Default pacing constants
STREAM_WORDS_PER_SECOND: float = 40.0
STREAM_MAX_SECONDS: float = 2.0
MIN_TYPING_MS: float = 400.0

# Regex pattern for markdown-aware tokenization:
# 1. Code blocks: ```...```
# 2. Table rows: ^\|[^\r\n]*\|$ (lines starting and ending with |)
# 3. Markdown links: \[...\]\(...\)
# 4. Inline code: `...`
# 5. Word with trailing whitespace: \S+\s*
# 6. Leading or standalone whitespace: \s+
_TOKEN_PATTERN = re.compile(
    r"(```[\s\S]*?```"
    r"|^\|[^\r\n]*\|$"
    r"|\[[^\]\r\n]*\]\([^\)\r\n]*\)"
    r"|`[^`\r\n]+`"
    r"|\S+\s*"
    r"|\s+)",
    re.MULTILINE,
)


def chunk_text(text: str) -> list[str]:
    """Split text into word-level chunks while preserving links, code, and table rows intact.

    Guarantees:
    - ''.join(chunk_text(text)) == text for any input string.
    - Code fences (```...```) remain in a single chunk.
    - Inline code (`...`) remains in a single chunk.
    - Markdown links ([title](url)) remain in a single chunk.
    - Markdown table rows (| col1 | col2 |) remain in a single chunk.
    """
    if not text:
        return []
    chunks = _TOKEN_PATTERN.findall(text)
    # Fallback safety in the unlikely event the regex misses anything
    if "".join(chunks) != text:
        return [text]
    return chunks


def stream_text(
    text: str,
    sleep_fn: Optional[Callable[[float], None]] = None,
    words_per_second: float = STREAM_WORDS_PER_SECOND,
    max_seconds: float = STREAM_MAX_SECONDS,
    min_ms: float = MIN_TYPING_MS,
) -> Iterator[str]:
    """Yield text chunks with controlled pacing within min/max time bounds.

    Args:
        text: Full markdown or text content to stream.
        sleep_fn: Sleep function to use for pacing delay (defaults to time.sleep).
        words_per_second: Approximate streaming speed in words/chunks per second.
        max_seconds: Upper bound on total streaming duration.
        min_ms: Lower bound on total streaming duration in milliseconds.

    Yields:
        Individual string chunks for use with st.write_stream or custom stream renderers.
    """
    chunks = chunk_text(text)
    if not chunks:
        return

    n_chunks = len(chunks)
    min_duration = min_ms / 1000.0
    # Determine target duration bounded by [min_duration, max_seconds]
    target_duration = min(max_seconds, max(min_duration, n_chunks / max(1.0, words_per_second)))
    delay = target_duration / max(1, n_chunks)

    sleeper = sleep_fn if sleep_fn is not None else time.sleep

    for chunk in chunks:
        if delay > 0:
            sleeper(delay)
        yield chunk


def is_streaming_enabled() -> bool:
    """Check if streaming presentation effect is enabled.

    Enabled by default, disabled if SIQVA_STREAM=0/false/no or disabled in session state.
    """
    env_val = os.environ.get("SIQVA_STREAM", "1").strip().lower()
    if env_val in ("0", "false", "no", "off"):
        return False

    try:
        import streamlit as st

        if hasattr(st, "session_state") and "enable_streaming" in st.session_state:
            return bool(st.session_state["enable_streaming"])
    except Exception:
        pass

    return True
