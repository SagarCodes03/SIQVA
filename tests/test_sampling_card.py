"""Tests for QueryCard sampling records, honest script generation, rerun, and backward compatibility (Task S8)."""

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from siqva.card import QueryCard, build_card, generate_script, load_card, rerun, save_card
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

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")


@pytest.fixture
def sample_spec() -> QuerySpec:
    return QuerySpec(
        basin="Indian Ocean",
        date_range=DateRange(start=date(2023, 1, 1), end=date(2023, 1, 31)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )


@pytest.fixture
def sample_fetch_result(sample_spec) -> FetchResult:
    df_fixture = pd.read_parquet(FIXTURE_PATH)
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-07T12:00:00Z",
        row_count=len(df_fixture),
        profile_count=2,
        data_hash="sample_hash_12345",
        fetch_key=sample_spec.fetch_key(),
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key=sample_spec.fetch_key(),
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
        is_sample=True,
        n_selected=2,
        n_available=989,
        method="grid x time stratification",
        seed=424242,
        index_build_date="2026-01-01",
        sample_picks=[(2901001, 1), (2901002, 2)],
    )


def test_card_records_plan_decision_and_sample_metadata(sample_spec, sample_fetch_result):
    """Verify that QueryCard records plan decision, sample picks, method, seed, index build date, and counts."""
    card = build_card(sample_spec, sample_fetch_result)

    assert card.is_sample is True
    assert card.plan_kind == "sample"
    assert card.sample_picks == [(2901001, 1), (2901002, 2)]
    assert card.sample_method == "grid x time stratification"
    assert card.sample_seed == 424242
    assert card.sample_index_build_date == "2026-01-01"
    assert card.sample_n_available == 989
    assert card.sample_n_selected == 2
    assert card.profile_count == 2


def test_generate_script_reproduces_sample_honestly_and_compiles(sample_spec, sample_fetch_result):
    """Verify generated script states it reproduces the sample not the region, has no index dependency, and compiles."""
    card = build_card(sample_spec, sample_fetch_result)
    script = generate_script(card)

    # Honest header: reproduces ONLY the sample, not the region
    assert "NOTE: This script reproduces ONLY the deterministic profile sample, NOT the entire region." in script
    assert "deterministic profile sample" in script

    # Contains exact sample picks
    assert "sample_picks = [(2901001, 1), (2901002, 2)]" in script

    # Does NOT require the float index
    assert "from siqva.floatindex" not in script
    assert "load_float_index" not in script

    # Compiles as valid, runnable Python
    compiled = compile(script, "<string>", "exec")
    assert compiled is not None


def test_generate_script_compiles_for_all_query_types(sample_spec, sample_fetch_result):
    """Verify scripts generated for all card types (metadata, chunked, full, sample) compile cleanly."""
    # 1. Sample card
    card_sample = build_card(sample_spec, sample_fetch_result)
    assert compile(generate_script(card_sample), "<sample_script>", "exec") is not None

    # 2. Metadata card
    meta_spec = sample_spec.model_copy(update={"intent": Intent.MAP})
    fetch_meta = FetchResult(
        status=FetchStatus.SUCCESS,
        data=pd.DataFrame([{"PLATFORM_NUMBER": 2901001, "LATITUDE": 5.0, "LONGITUDE": 70.0}]),
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=0.0),
        metadata=FetchMetadata(
            src="float_index",
            source="float_index",
            argopy_version="1.5.0",
            xarray_version="2026.9.0",
            fetch_timestamp="2026-11-07T12:00:00Z",
            row_count=1,
            profile_count=1,
            data_hash="meta_hash",
            fetch_key=meta_spec.fetch_key(),
        ),
    )
    card_meta = build_card(meta_spec, fetch_meta)
    assert compile(generate_script(card_meta), "<meta_script>", "exec") is not None

    # 3. Chunked card
    chunk_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 3, 31)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )
    card_chunk = build_card(chunk_spec, sample_fetch_result, chunks=[("2022-01", "Jan 2022"), ("2022-02", "Feb 2022")])
    assert compile(generate_script(card_chunk), "<chunk_script>", "exec") is not None

    # 4. Standard full card
    full_spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 7)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.STANDARD,
        intent=Intent.PROFILE,
    )
    full_fetch = sample_fetch_result.model_copy(update={"is_sample": False, "sample_picks": None})
    card_full = build_card(full_spec, full_fetch)
    assert compile(generate_script(card_full), "<full_script>", "exec") is not None


def test_rerun_compares_same_sample(sample_spec, sample_fetch_result):
    """Verify that rerun() on a sample card re-fetches the identical sample picks and reports diff."""
    card = build_card(sample_spec, sample_fetch_result)

    with patch("siqva.fetcher.fetch_sample", return_value=sample_fetch_result) as mock_fetch_sample:
        diff = rerun(card)

        # Confirm fetch_sample was called with the exact picks from the card
        assert mock_fetch_sample.called
        call_kwargs = mock_fetch_sample.call_args.kwargs
        assert "picks" in call_kwargs
        passed_picks = [
            (p[0], p[1]) if isinstance(p, (tuple, list)) else (p.wmo, p.cycle)
            for p in call_kwargs["picks"]
        ]
        assert passed_picks == [(2901001, 1), (2901002, 2)]

        # Diff reports same data
        assert diff.is_same is True
        assert diff.old_data_hash == card.data_hash
        assert diff.new_data_hash == card.data_hash
        assert diff.row_diff == 0
        assert diff.profile_diff == 0


def test_old_cards_still_load_without_sample_fields(tmp_path):
    """Proves backward compatibility: legacy card JSON missing new sampling fields deserializes and loads cleanly."""
    legacy_card_json = """{
        "card_id": "legacy_card_001",
        "spec": {
            "region": {"lon_min": 60.0, "lon_max": 65.0, "lat_min": 10.0, "lat_max": 15.0},
            "date_range": {"start": "2022-01-01", "end": "2022-01-05"},
            "variables": ["TEMP"],
            "depth_range": {"min_depth": 0.0, "max_depth": 500.0},
            "mode": "standard",
            "intent": "profile"
        },
        "spec_json": "{}",
        "spec_hash": "legacy_hash_001",
        "fetch_key": "legacy_key_001",
        "mode": "standard",
        "qc_filter_description": "Standard QC",
        "effective_depth_range": {"min_depth": 0.0, "max_depth": 500.0},
        "source": "erddap",
        "src": "erddap",
        "argopy_version": "1.5.0",
        "xarray_version": "2026.9.0",
        "fetch_timestamp": "2026-11-01T00:00:00Z",
        "is_cached": true,
        "row_count": 100,
        "profile_count": 2,
        "profile_count_verified": true,
        "data_hash": "legacy_dhash_001",
        "created_at": "2026-11-01T00:00:00Z"
    }"""

    # 1. Pydantic deserialization
    card = QueryCard.model_validate_json(legacy_card_json)
    assert card.card_id == "legacy_card_001"
    assert card.is_sample is False
    assert card.plan_kind is None
    assert card.sample_picks is None
    assert card.sample_method is None

    # 2. SQLite roundtrip
    db_file = tmp_path / "legacy_cards.sqlite"
    save_card(card, db_path=db_file)
    loaded = load_card("legacy_card_001", db_path=db_file)

    assert loaded is not None
    assert loaded.card_id == "legacy_card_001"
    assert loaded.is_sample is False
    assert loaded.sample_picks is None
