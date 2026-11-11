"""Tests for the seven key questions across the real parse -> plan -> run_spec -> build_card pipeline."""

from unittest.mock import MagicMock
import pandas as pd
import pytest

from siqva.pipeline import PipelineStatus, run
from siqva.planner import PlanKind, plan_request
from siqva.spec import Intent


FIXTURE_PATH = pytest.importorskip("pathlib").Path(__file__).resolve().parent / "fixtures" / "sample_argo_standard.parquet"


class MockPipelineEngine:
    """Mock argopy DataFetcher that returns recorded fixture data without network access."""

    def __init__(self, mode: str = "standard", src: str = "erddap", **kwargs):
        self.mode = mode
        self.src = src

    def region(self, box):
        return self

    def profile(self, wmo, cyc):
        return self

    def to_dataframe(self):
        df = pd.read_parquet(FIXTURE_PATH).copy()
        df["DATA_MODE"] = "D"
        return df


@pytest.fixture
def mock_fetcher():
    engine = MockPipelineEngine()
    return MagicMock(return_value=engine)


def test_q1_show_floats_in_pacific_ocean():
    """Q1: Metadata float location query in Pacific Ocean."""
    res = run("show floats in the Pacific Ocean", force_refresh=False)
    assert res.status == PipelineStatus.SUCCESS
    assert res.spec.intent == Intent.MAP
    assert res.spec.basin == "Pacific Ocean"
    assert res.card is not None
    assert "Pacific Ocean" in res.card.region_name


def test_q2_how_many_profiles_in_pacific_ocean_in_2023():
    """Q2: Metadata count query in Pacific Ocean."""
    res = run("how many profiles in the Pacific Ocean in 2023", force_refresh=False)
    assert res.status == PipelineStatus.SUCCESS
    assert res.spec.intent == Intent.MAP
    assert res.spec.basin == "Pacific Ocean"
    assert res.card is not None


def test_q3_show_floats_in_indian_ocean_in_january_2023():
    """Q3: Metadata float location query in Indian Ocean."""
    res = run("show floats in the Indian Ocean in January 2023", force_refresh=False)
    assert res.status == PipelineStatus.SUCCESS
    assert res.spec.intent == Intent.MAP
    assert res.spec.basin == "Indian Ocean"
    assert res.card is not None


def test_q4_temperature_profiles_in_indian_ocean_in_january_2023(mock_fetcher):
    """Q4: Basin observation request in Indian Ocean -> planner decision (SAMPLE)."""
    with pytest.MonkeyPatch.context() as mp:
        import argopy
        mp.setattr(argopy, "DataFetcher", mock_fetcher)
        res = run("temperature profiles in the Indian Ocean in January 2023", force_refresh=False)
        assert res.status == PipelineStatus.SUCCESS
        assert res.spec.basin == "Indian Ocean"
        assert res.fetch_result.is_sample is True
        assert res.card is not None


def test_q5_temperature_profiles_in_pacific_ocean_in_january_2023(mock_fetcher):
    """Q5: Basin observation request in Pacific Ocean -> planner decision (SAMPLE)."""
    with pytest.MonkeyPatch.context() as mp:
        import argopy
        mp.setattr(argopy, "DataFetcher", mock_fetcher)
        res = run("temperature profiles in the Pacific Ocean in January 2023", force_refresh=False)
        assert res.status == PipelineStatus.SUCCESS
        assert res.spec.basin == "Pacific Ocean"
        assert res.fetch_result.is_sample is True
        assert res.card is not None


def test_q6_temperature_profiles_in_arabian_sea_in_january_2023(mock_fetcher):
    """Q6: Control question on bounded region (Arabian Sea) -> full path."""
    with pytest.MonkeyPatch.context() as mp:
        import argopy
        mp.setattr(argopy, "DataFetcher", mock_fetcher)
        res = run("temperature profiles in the Arabian Sea in January 2023", force_refresh=False)
        assert res.status == PipelineStatus.SUCCESS
        assert res.spec.region is not None
        assert res.card is not None


def test_q7_hovmoller_diagram_of_indian_ocean_in_2023():
    """Q7: FULL_REQUIRED module on ocean basin -> refusal with options."""
    res = run("Hovmoller diagram of the Indian Ocean in 2023", force_refresh=False)
    assert res.status in (PipelineStatus.OVERSIZED, PipelineStatus.CLARIFICATION_NEEDED)
    assert res.spec.basin == "Indian Ocean"
    assert res.warnings or (res.clarification and res.clarification.suggestions)

