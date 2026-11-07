"""UI smoke tests using streamlit.testing.v1.AppTest without network or live Ollama."""

from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from siqva.analyzer import analyze
from siqva.card import build_card, generate_script
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.pipeline import PipelineResult, PipelineStatus
from siqva.spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, QuerySpec, Variable

APP_PATH = str(Path(__file__).resolve().parents[1] / "app" / "ui.py")
FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_argo_standard.parquet"


@pytest.fixture
def sample_pipeline_result() -> PipelineResult:
    df_fixture = pd.read_parquet(FIXTURE_PATH)
    spec = QuerySpec(
        region=BoundingBox(lon_min=50.0, lon_max=77.0, lat_min=8.0, lat_max=25.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 5)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-07T12:00:00Z",
        row_count=len(df_fixture),
        profile_count=2,
        data_hash="dummyhash",
        fetch_key=spec.fetch_key(),
    )
    fetch_res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key=spec.fetch_key(),
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
    )
    analysis = analyze(df_fixture, spec, fetch_res)
    card = build_card(spec, fetch_res, analysis, question="temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
    return PipelineResult(
        status=PipelineStatus.SUCCESS,
        question="temperature in the Arabian Sea between 2022-01-01 and 2022-01-05",
        spec=spec,
        fetch_result=fetch_res,
        analysis=analysis,
        figures={},
        card=card,
        script=generate_script(card),
    )


def test_ui_starts_without_exception():
    """Proves the Streamlit application starts and renders default layout without exceptions."""
    with patch("siqva.llm_parser.check_llm_availability", return_value=False):
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.text_area) > 0
        assert any("SIQVA" in m.value for m in at.markdown)


def test_ui_runs_rules_only_query_against_mock_fetcher(sample_pipeline_result):
    """Proves a natural language query runs end-to-end through UI against mock fetcher with 0 exceptions."""
    with patch("siqva.pipeline.run", return_value=sample_pipeline_result), \
         patch("siqva.llm_parser.check_llm_availability", return_value=False):

        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Input query and submit
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)

        # Confirm no unhandled exceptions were raised in UI
        assert len(at.exception) == 0
        # Assert expected metrics and text appear
        assert len(at.metric) >= 4
        assert any(m.label == "PROFILES" and "2" in str(m.value) for m in at.metric)
        assert any(m.label == "ROWS" and "188" in str(m.value) for m in at.metric)
