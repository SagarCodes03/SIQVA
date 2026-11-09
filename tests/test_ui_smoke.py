"""UI smoke tests using streamlit.testing.v1.AppTest without network or live Ollama."""

from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.spec import DepthRange

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")


@pytest.fixture
def sample_fetch_result() -> FetchResult:
    df_fixture = pd.read_parquet(FIXTURE_PATH)
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-07T12:00:00Z",
        row_count=len(df_fixture),
        profile_count=2,
        data_hash="dummyhash",
        fetch_key="dummykey",
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key="dummykey",
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
    )


UI_PATH = str(Path(__file__).resolve().parent.parent / "app" / "ui.py")


def test_ui_starts_without_exception():
    """Proves the Streamlit application starts and renders default layout without exceptions."""
    at = AppTest.from_file(UI_PATH)
    at.run(timeout=30)
    assert len(at.exception) == 0


def test_ui_runs_rules_only_query_against_mock_fetcher(sample_fetch_result):
    """Proves a natural language query runs end-to-end through UI against mock fetcher with 0 exceptions."""
    with patch("siqva.pipeline.fetch", return_value=sample_fetch_result):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Input query and submit
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)

        # Confirm no unhandled exceptions were raised in UI
        assert len(at.exception) == 0
