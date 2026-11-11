"""Tests for pipeline safety net catching internal errors gracefully without tracebacks."""

import logging
from unittest.mock import MagicMock, patch
from datetime import date
from pathlib import Path
import pandas as pd

from siqva.fetcher import FetchStatus
from siqva.pipeline import PipelineStatus, run, run_spec
from siqva.spec import QuerySpec, Intent, Variable, DateRange, DepthRange, DataMode
from siqva.gazetteer import KNOWN_REGIONS


def test_internal_error_forced_in_build_card_returns_internal_error_status(tmp_path):
    """Forcing an exception in build_card must return INTERNAL_ERROR with ref_id and log to file."""
    # Build a minimal spec
    spec = QuerySpec(
        region=KNOWN_REGIONS["Arabian Sea"],
        date_range=DateRange(start=date(2023, 1, 1), end=date(2023, 1, 10)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=100.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    with patch("siqva.pipeline.build_card", side_effect=RuntimeError("Simulated build_card crash")):
        with patch("siqva.pipeline.fetch") as mock_fetch:
            mock_res = MagicMock()
            mock_res.status = FetchStatus.SUCCESS
            mock_res.data = pd.DataFrame({
                "PLATFORM_NUMBER": [1902345],
                "CYCLE_NUMBER": [1],
                "PRES": [10.0],
                "TEMP": [25.0],
                "TIME": ["2023-01-02"],
                "LATITUDE": [15.0],
                "LONGITUDE": [65.0],
            })
            mock_res.effective_depth_range = spec.depth_range
            mock_res.is_sample = False
            mock_res.is_cached = False
            mock_fetch.return_value = mock_res

            res = run_spec(spec)

            assert res.status == PipelineStatus.INTERNAL_ERROR
            assert "Reference ID:" in res.error_message
            assert "Simulated build_card crash" not in res.error_message
            assert "Traceback" not in res.error_message


def test_run_boundary_catches_all_unexpected_exceptions():
    """run() must catch unexpected errors from parser, planning, or execution."""
    with patch("siqva.pipeline.parse_detailed", side_effect=TypeError("Simulated parser explosion")):
        res = run("temperature profiles in the Arabian Sea in January 2023")

        assert res.status == PipelineStatus.INTERNAL_ERROR
        assert "Reference ID:" in res.error_message
        assert "Simulated parser explosion" not in res.error_message
        assert "Traceback" not in res.error_message

        # Verify logs/siqva.log recorded the exception
        log_file = Path("logs/siqva.log")
        assert log_file.exists()
        log_content = log_file.read_text(encoding="utf-8")
        assert "Simulated parser explosion" in log_content
