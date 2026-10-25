"""Unit tests for argocard.card module (QueryCard, script generation, SQLite persistence, and diff re-run)."""

import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path
import pandas as pd
import pytest

from argocard.analyzer import analyze
from argocard.card import (
    DiffSummary,
    QueryCard,
    build_card,
    generate_script,
    list_cards,
    load_card,
    rerun,
    save_card,
)
from argocard.fetcher import (
    FetchMetadata,
    FetchResult,
    FetchStatus,
    compute_canonical_data_hash,
    fetch,
)
from argocard.spec import (
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
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=200.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )


@pytest.fixture
def sample_fetch_result(sample_spec) -> FetchResult:
    df = pd.read_parquet(FIXTURE_PATH)
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.4.0",
        xarray_version="2025.9.0",
        fetch_timestamp="2024-01-15T12:00:00Z",
        row_count=len(df),
        profile_count=2,
        data_hash="abc123mockhash456",
        fetch_key=sample_spec.fetch_key(),
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df,
        is_cached=False,
        cache_key=sample_spec.fetch_key(),
        metadata=meta,
        effective_depth_range=sample_spec.depth_range,
        profile_count_verified=True,
    )


def test_build_card_contains_all_provenance_and_spec_fields(sample_spec, sample_fetch_result):
    """Proves build_card populates all mandatory metadata, spec fields, versions, and hashes."""
    analysis = analyze(sample_fetch_result.data, sample_spec, sample_fetch_result)
    card = build_card(sample_spec, sample_fetch_result, analysis)

    assert card.spec == sample_spec
    assert card.spec_json == sample_spec.normalized_json()
    assert card.spec_hash == sample_spec.spec_hash()
    assert card.fetch_key == sample_spec.fetch_key()
    assert card.mode == DataMode.RESEARCH
    assert "Strict QC=1 only" in card.qc_filter_description
    assert card.effective_depth_range == sample_spec.depth_range
    assert card.source == "erddap"
    assert card.src == "erddap"
    assert card.argopy_version == "1.4.0"
    assert card.xarray_version == "2025.9.0"
    assert card.fetch_timestamp == "2024-01-15T12:00:00Z"
    assert card.is_cached is False
    assert card.row_count == 188
    assert card.profile_count == 2
    assert card.profile_count_verified is True
    assert card.data_hash == "abc123mockhash456"
    assert card.created_at != ""


def test_generate_script_compiles_cleanly_and_has_verified_format(sample_spec, sample_fetch_result):
    """Proves generate_script produces a valid Python script with verified box format and explicit mode."""
    card = build_card(sample_spec, sample_fetch_result)
    script_str = generate_script(card)

    # 1. Check verified box format: [lon_min, lon_max, lat_min, lat_max, dpt_min, dpt_max, date_min, date_max]
    assert "box = [-30.0, -28.0, 32.0, 34.0, 0.0, 200.0, \"2022-01-01\", \"2022-01-10\"]" in script_str
    # 2. Explicit mode passed
    assert 'mode="research"' in script_str
    assert 'src="erddap"' in script_str

    # 3. Compiles cleanly as valid python syntax
    compiled = compile(script_str, "<argopy_script>", "exec")
    assert compiled is not None

    # 4. Write to temporary file and compile from disk
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp:
        tmp.write(script_str)
        tmp_path = Path(tmp.name)

    try:
        with open(tmp_path, "r", encoding="utf-8") as f:
            disk_content = f.read()
        disk_compiled = compile(disk_content, str(tmp_path), "exec")
        assert disk_compiled is not None
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def test_sqlite_persistence_save_load_list(tmp_path, sample_spec, sample_fetch_result):
    """Proves SQLite save_card, load_card, and list_cards work reliably."""
    db_file = tmp_path / "cards.sqlite"
    card1 = build_card(sample_spec, sample_fetch_result, card_id="card_001")

    # Save
    saved_id = save_card(card1, db_path=db_file)
    assert saved_id == "card_001"
    assert db_file.exists()

    # Load by ID
    loaded = load_card("card_001", db_path=db_file)
    assert loaded is not None
    assert loaded.card_id == "card_001"
    assert loaded.spec_hash == card1.spec_hash
    assert loaded.data_hash == card1.data_hash
    assert loaded.row_count == card1.row_count

    # Load by spec_hash fallback
    loaded_by_hash = load_card(card1.spec_hash, db_path=db_file)
    assert loaded_by_hash is not None
    assert loaded_by_hash.card_id == "card_001"

    # Save a second card and list
    spec2 = sample_spec.model_copy(update={"mode": DataMode.STANDARD})
    card2 = build_card(spec2, sample_fetch_result, card_id="card_002")
    save_card(card2, db_path=db_file)

    cards = list_cards(limit=10, db_path=db_file)
    assert len(cards) == 2
    assert {c.card_id for c in cards} == {"card_001", "card_002"}


def test_rerun_identical_data_summary(tmp_path, sample_spec, sample_fetch_result):
    """Proves rerun with identical data reports is_same=True and unchanged summary."""
    card = build_card(sample_spec, sample_fetch_result)

    # Mock fetcher returning the same result
    def mock_fetcher(*args, **kwargs):
        return sample_fetch_result

    diff: DiffSummary = rerun(card, fetcher_fn=mock_fetcher)
    assert diff.is_same is True
    assert diff.row_diff == 0
    assert diff.profile_diff == 0
    assert "identical" in diff.summary.lower()


def test_rerun_modified_data_reports_diff_cleanly(tmp_path, sample_spec, sample_fetch_result):
    """Proves rerun with updated data reports row/profile diffs and new profiles without error."""
    card = build_card(sample_spec, sample_fetch_result)

    # Simulate remote dataset update with delayed-mode corrections: new rows and extra profile
    new_df = sample_fetch_result.data.copy()
    extra_row = new_df.iloc[0:1].copy()
    extra_row["PLATFORM_NUMBER"] = 7999999
    extra_row["CYCLE_NUMBER"] = 1
    new_df = pd.concat([new_df, extra_row], ignore_index=True)

    new_meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.4.0",
        xarray_version="2025.9.0",
        fetch_timestamp="2024-02-01T12:00:00Z",
        row_count=len(new_df),
        profile_count=3,
        data_hash="different_new_hash_999",
        fetch_key=sample_spec.fetch_key(),
    )
    new_result = FetchResult(
        status=FetchStatus.SUCCESS,
        data=new_df,
        is_cached=False,
        cache_key=sample_spec.fetch_key(),
        metadata=new_meta,
        effective_depth_range=sample_spec.depth_range,
        profile_count_verified=True,
    )

    diff: DiffSummary = rerun(card, fetcher_fn=lambda *a, **kw: new_result)
    assert diff.is_same is False
    assert diff.row_diff == 1
    assert diff.profile_diff == 1
    assert diff.old_data_hash == "abc123mockhash456"
    assert diff.new_data_hash == "different_new_hash_999"
    assert (7999999, 1) in diff.new_profiles
    assert "Data modified" in diff.summary
    assert "Row count changed by +1" in diff.summary


def test_canonical_data_hash_shuffled_rows_same_hash():
    """Proves row shuffling and column order permutations yield the exact same SHA-256 data hash."""
    df = pd.read_parquet(FIXTURE_PATH)
    hash_original = compute_canonical_data_hash(df)

    # Permute rows and reorder columns
    df_shuffled = df.sample(frac=1.0, random_state=42).copy()
    reversed_cols = list(reversed(df.columns.tolist()))
    df_reordered = df_shuffled[reversed_cols].copy()

    hash_shuffled = compute_canonical_data_hash(df_reordered)
    assert hash_original == hash_shuffled
    assert len(hash_original) == 64


def test_load_card_missing_returns_none(tmp_path):
    """Proves load_card returns None when the requested card_id does not exist."""
    db_file = tmp_path / "cards.sqlite"
    assert load_card("nonexistent_card_id", db_path=db_file) is None


def test_rerun_diff_reports_version_difference(sample_spec, sample_fetch_result):
    """Proves rerun flags version changes when installed library versions differ from card."""
    card = build_card(sample_spec, sample_fetch_result)

    # Mock fetcher returning the exact same data but newer library versions
    new_meta = sample_fetch_result.metadata.model_copy(
        update={"argopy_version": "1.5.0", "xarray_version": "2026.1.0"}
    )
    new_res = sample_fetch_result.model_copy(update={"metadata": new_meta})

    diff = rerun(card, fetcher_fn=lambda *a, **kw: new_res)
    assert diff.is_same is True
    assert diff.version_changed is True
    assert diff.argopy_version_diff == ("1.4.0", "1.5.0")
    assert diff.xarray_version_diff == ("2025.9.0", "2026.1.0")
    assert "library versions changed: argopy (1.4.0 -> 1.5.0), xarray (2025.9.0 -> 2026.1.0)" in diff.summary


def test_rerun_diff_reports_missing_profiles(tmp_path, sample_spec, sample_fetch_result):
    """Proves rerun detects missing profiles when compared against cached parquet."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)

    # Save original fixture data into cache_dir keyed by fetch_key
    sample_fetch_result.data.to_parquet(cache_dir / f"{sample_spec.fetch_key()}.parquet")
    card = build_card(sample_spec, sample_fetch_result)

    # Create new data where one profile is dropped
    df = sample_fetch_result.data.copy()
    unique_profs = df[["PLATFORM_NUMBER", "CYCLE_NUMBER"]].drop_duplicates().values.tolist()
    assert len(unique_profs) >= 2
    dropped_prof = tuple(unique_profs[0])
    keep_df = df[
        ~((df["PLATFORM_NUMBER"] == dropped_prof[0]) & (df["CYCLE_NUMBER"] == dropped_prof[1]))
    ].copy()

    new_meta = sample_fetch_result.metadata.model_copy(
        update={
            "row_count": len(keep_df),
            "profile_count": 1,
            "data_hash": "new_hash_missing_prof",
        }
    )
    new_res = sample_fetch_result.model_copy(update={"data": keep_df, "metadata": new_meta})

    diff = rerun(card, fetcher_fn=lambda *a, **kw: new_res, cache_dir=cache_dir)
    assert diff.is_same is False
    assert diff.profile_diff == -1
    assert dropped_prof in diff.missing_profiles
    assert "Missing profiles: 1" in diff.summary


@pytest.mark.skipif(
    not os.getenv("RUN_NETWORK_TESTS"),
    reason="Network test: skipped by default, set RUN_NETWORK_TESTS=1 to run",
)
def test_live_check_card_and_script(tmp_path):
    """Live network verification:

    Fetches box [-30, -28, 32, 34], 0-500 dbar, 2022-01-01 to 2022-01-10 in research mode.
    Proves rerun reports identical data, and generated script runs successfully via subprocess.
    """
    spec = QuerySpec(
        region=BoundingBox(lon_min=-30.0, lon_max=-28.0, lat_min=32.0, lat_max=34.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    cache_dir = tmp_path / "live_cache"
    db_file = tmp_path / "live_cards.sqlite"

    res = fetch(spec, cache_dir=cache_dir)
    assert res.status == FetchStatus.SUCCESS
    assert res.data is not None
    assert len(res.data) > 0

    analysis = analyze(res.data, spec, res)
    card = build_card(spec, res, analysis)
    save_card(card, db_path=db_file)

    # 1. Test rerun reports identical data
    diff = rerun(card, cache_dir=cache_dir)
    assert diff.is_same is True
    assert diff.row_diff == 0
    assert diff.profile_diff == 0
    assert "identical" in diff.summary.lower()

    # 2. Test generated script execution in subprocess
    script_str = generate_script(card)
    script_path = tmp_path / "reproduce_query.py"
    script_path.write_text(script_str, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert proc.returncode == 0, f"Script failed with stderr:\n{proc.stderr}"
    stdout = proc.stdout
    assert f"Results: {card.row_count} rows across {card.profile_count} profiles." in stdout

