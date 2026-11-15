"""Tests for word-level text streaming and pacing (U2)."""

import os
from unittest.mock import patch
import pytest

from siqva.streaming import (
    MIN_TYPING_MS,
    STREAM_MAX_SECONDS,
    STREAM_WORDS_PER_SECOND,
    chunk_text,
    is_streaming_enabled,
    stream_text,
)


def test_chunk_text_preserves_exact_text():
    sample_text = (
        "SIQVA queries the Argo array for oceanic profiles.\n\n"
        "Here is a table:\n"
        "| Variable | Units | Standard |\n"
        "|----------|-------|----------|\n"
        "| TEMP     | degC  | ITS-90   |\n"
        "| PSAL     | psu   | PSS-78   |\n\n"
        "Check [Argo Data Portal](https://argo.ucsd.edu) or run `argopy.DataFetcher`.\n"
        "```python\n"
        "import argopy\n"
        "ds = argopy.DataFetcher().region([50, 70, 10, 20, 0, 500, '2022-01-01', '2022-01-15']).to_xarray()\n"
        "```\n"
        "Conclusion: query successful."
    )
    chunks = chunk_text(sample_text)
    assert len(chunks) > 10
    assert "".join(chunks) == sample_text


def test_chunk_text_keeps_markdown_structures_intact():
    text = "Visit [Argo Floats](https://argo.ucsd.edu) and check `PLATFORM_NUMBER`."
    chunks = chunk_text(text)
    assert "[Argo Floats](https://argo.ucsd.edu)" in chunks
    assert "`PLATFORM_NUMBER`" in chunks
    assert "".join(chunks) == text


def test_chunk_text_keeps_code_fence_intact():
    code_block = "```python\ndef test():\n    return 42\n```"
    text = f"Before code\n{code_block}\nAfter code"
    chunks = chunk_text(text)
    assert code_block in chunks
    assert "".join(chunks) == text


def test_chunk_text_keeps_table_rows_intact():
    table_row = "| Bay of Bengal | 2022-04-01 | 42 |"
    text = f"Header\n{table_row}\nFooter"
    chunks = chunk_text(text)
    assert table_row in chunks
    assert "".join(chunks) == text


def test_chunk_text_empty():
    assert chunk_text("") == []


def test_stream_text_pacing_and_bounds():
    recorded_delays: list[float] = []

    def mock_sleep(d: float) -> None:
        recorded_delays.append(d)

    long_text = "Word " * 150  # 150 words
    chunks = list(stream_text(long_text, sleep_fn=mock_sleep))

    assert "".join(chunks) == long_text
    total_time = sum(recorded_delays)
    # Total time should not exceed STREAM_MAX_SECONDS (2.0s) + small epsilon
    assert total_time <= STREAM_MAX_SECONDS + 0.05
    # Total time should be at least MIN_TYPING_MS (0.4s)
    assert total_time >= (MIN_TYPING_MS / 1000.0) - 0.05


def test_stream_text_short_respects_min_duration():
    recorded_delays: list[float] = []

    def mock_sleep(d: float) -> None:
        recorded_delays.append(d)

    short_text = "Single small sentence."
    chunks = list(stream_text(short_text, sleep_fn=mock_sleep))

    assert "".join(chunks) == short_text
    total_time = sum(recorded_delays)
    # Should enforce MIN_TYPING_MS (0.4s) minimum
    assert total_time >= (MIN_TYPING_MS / 1000.0) - 0.05


def test_is_streaming_enabled_env_toggle():
    with patch.dict(os.environ, {"SIQVA_STREAM": "1"}):
        assert is_streaming_enabled() is True

    with patch.dict(os.environ, {"SIQVA_STREAM": "0"}):
        assert is_streaming_enabled() is False

    with patch.dict(os.environ, {"SIQVA_STREAM": "false"}):
        assert is_streaming_enabled() is False
