"""Tests for Plot Graph capability display, S3 plan enforcement, and Compare Runs sample restrictions (Task S9)."""

from datetime import date
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from siqva.card import QueryCard, build_card, save_card
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)

UI_PATH = str(Path(__file__).resolve().parent.parent / "app" / "ui.py")
FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")


@pytest.fixture
def sample_full_cards(tmp_path):
    """Create two completed FULL query cards saved into SQLite."""
    df_fixture = pd.read_parquet(FIXTURE_PATH)
    db_file = tmp_path / "cards.sqlite"

    spec_a = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 5)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )
    meta_a = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-01T00:00:00Z",
        row_count=len(df_fixture),
        profile_count=2,
        data_hash="hash_a",
        fetch_key=spec_a.fetch_key(),
    )
    res_a = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key=spec_a.fetch_key(),
        metadata=meta_a,
        profile_count_verified=True,
        profile_count=2,
        is_sample=False,
    )
    card_a = build_card(spec_a, res_a, question="Run A Full")
    save_card(card_a, db_path=db_file)

    spec_b = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 6), end=date(2022, 1, 10)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )
    meta_b = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-02T00:00:00Z",
        row_count=len(df_fixture),
        profile_count=2,
        data_hash="hash_b",
        fetch_key=spec_b.fetch_key(),
    )
    res_b = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key=spec_b.fetch_key(),
        metadata=meta_b,
        profile_count_verified=True,
        profile_count=2,
        is_sample=False,
    )
    card_b = build_card(spec_b, res_b, question="Run B Full")
    save_card(card_b, db_path=db_file)

    return db_file, card_a, card_b


@pytest.fixture
def sample_and_full_cards(sample_full_cards):
    """Create a database containing one sample card and one full card."""
    db_file, card_a, card_b = sample_full_cards
    df_fixture = pd.read_parquet(FIXTURE_PATH)

    spec_sample = QuerySpec(
        basin="Indian Ocean",
        date_range=DateRange(start=date(2023, 1, 1), end=date(2023, 1, 31)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    res_sample = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key=spec_sample.fetch_key(),
        metadata=FetchMetadata(
            src="erddap",
            source="erddap",
            argopy_version="1.5.0",
            xarray_version="2026.9.0",
            fetch_timestamp="2026-11-07T12:00:00Z",
            row_count=120,
            profile_count=12,
            data_hash="hash_sample",
            fetch_key=spec_sample.fetch_key(),
        ),
        profile_count_verified=True,
        profile_count=12,
        is_sample=True,
        sample_picks=[(2901001, 1), (2901002, 2)],
        n_available=989,
    )
    card_sample = build_card(spec_sample, res_sample, question="Run Sample Basin")
    save_card(card_sample, db_path=db_file)

    return db_file, card_sample, card_a


def test_plot_graphs_displays_capabilities():
    """Verify each 'Configure & Plot' card shows its capability (Metadata / Sample allowed / Full data required)."""
    at = AppTest.from_file(UI_PATH)
    at.session_state["active_page"] = "plots"
    at.run(timeout=30)

    assert len(at.exception) == 0

    markdown_all = " ".join(m.value for m in at.markdown)

    # Confirm all three capability labels appear in the rendered graph cards
    assert "Metadata" in markdown_all
    assert "Sample allowed" in markdown_all
    assert "Full data required" in markdown_all


def test_compare_runs_compares_two_full_runs(sample_full_cards):
    """Verify Compare Runs performs delta comparison when both sides are complete (FULL)."""
    db_file, card_a, card_b = sample_full_cards

    with patch("siqva.card.DEFAULT_DB_PATH", db_file):
        at = AppTest.from_file(UI_PATH)
        at.session_state["active_page"] = "compare"
        at.run(timeout=30)

        assert len(at.exception) == 0

        # Comparative Metrics Delta table is rendered
        metric_labels = [m.label for m in at.metric]
        assert "Rows" in metric_labels
        assert "Profiles" in metric_labels
        assert "QC Mode" in metric_labels

        # No sample restriction warning
        warning_texts = [w.value for w in at.warning]
        assert not any("sample" in w.lower() for w in warning_texts)


def test_compare_runs_refuses_when_side_is_sample(sample_and_full_cards):
    """Verify Compare Runs rejects comparison when a side is a sample, explains why, and offers options."""
    db_file, card_sample, card_full = sample_and_full_cards

    with patch("siqva.card.DEFAULT_DB_PATH", db_file):
        at = AppTest.from_file(UI_PATH)
        at.session_state["active_page"] = "compare"
        at.run(timeout=30)

        assert len(at.exception) == 0

        # Warning explaining comparison is restricted to FULL or CHUNKED runs
        warning_texts = [w.value for w in at.warning]
        assert any(
            "compares only complete observation datasets" in w or "FULL or CHUNKED" in w
            for w in warning_texts
        )

        # Error explaining which side is a sample and why it cannot be compared
        error_texts = [e.value for e in at.error]
        assert any("profile sample" in e and "A region-wide comparison needs all profiles" in e for e in error_texts)

        # Options buttons offered for the sample side
        btn_labels = [b.label for b in at.button]
        assert any("> A:" in lbl or "> B:" in lbl for lbl in btn_labels)

        # Delta metrics table is suppressed
        metric_labels = [m.label for m in at.metric]
        assert "Rows" not in metric_labels
