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

        # Assert result tiles / metrics are rendered
        labels = [m.label for m in at.metric]
        assert "Total Rows" in labels
        assert "Float Profiles" in labels
        assert "Source" in labels
        assert "Data Mode" in labels
        assert "Depth Span" in labels

        rows_metric = next(m for m in at.metric if m.label == "Total Rows")
        assert rows_metric.value == f"{sample_fetch_result.metadata.row_count:,}"


def test_ui_indian_ocean_question_does_not_start_region_fetch():
    """Verify that 'temperature profiles in the Indian Ocean in January 2023' does NOT call regional fetch in UI."""
    with patch("siqva.pipeline.fetch") as spy_pipe_fetch, patch("siqva.fetcher.fetch") as spy_mod_fetch:
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Input oversized basin query and submit
        at.text_area[0].input("temperature profiles in the Indian Ocean in January 2023")
        at.button(key="send_query_btn").click().run(timeout=30)

        # UI completes without unhandled exceptions
        assert len(at.exception) == 0

        # Neither regional fetcher was called because sampling was used instead of full regional fetch
        spy_pipe_fetch.assert_not_called()
        spy_mod_fetch.assert_not_called()


class MockProfileEngine:
    all_recorded_calls = []
    fail_wmos = set()
    fail_first_n = 0
    fail_count = 0

    def __init__(self, mode="standard", src="erddap", **kwargs):
        self.mode = mode
        self.src = src
        self._cur_wmo = None
        self._cur_cyc = None
        self.cur_failing = False

    def profile(self, wmo, cyc):
        self._cur_wmo = wmo
        self._cur_cyc = cyc
        is_fail = (wmo in MockProfileEngine.fail_wmos) or (
            MockProfileEngine.fail_first_n > 0 and MockProfileEngine.fail_count < MockProfileEngine.fail_first_n
        )
        if is_fail:
            if MockProfileEngine.fail_first_n > 0 and MockProfileEngine.fail_count < MockProfileEngine.fail_first_n:
                MockProfileEngine.fail_count += 1
            self.cur_failing = True
            raise RuntimeError(f"Simulated network failure for float {wmo}")
        self.cur_failing = False
        MockProfileEngine.all_recorded_calls.append((wmo, cyc))
        return self

    def region(self, box):
        if self.cur_failing:
            raise RuntimeError("Simulated fallback network failure")
        return self

    def to_dataframe(self):
        if self.cur_failing:
            raise RuntimeError("Simulated network failure")
        df = pd.read_parquet(FIXTURE_PATH).copy()
        if self._cur_wmo is not None and self._cur_cyc is not None:
            df["PLATFORM_NUMBER"] = self._cur_wmo
            df["CYCLE_NUMBER"] = self._cur_cyc
            df["DATA_MODE"] = "D"
            df["LATITUDE"] = 5.0
            df["LONGITUDE"] = 70.0
        return df


def test_ui_s7_indian_ocean_temperature_profiles_sample_flow(tmp_path):
    """S7 AppTest 1: Indian Ocean temperature profiles (sample path, fetch calls = picks, label present)."""
    MockProfileEngine.all_recorded_calls = []
    MockProfileEngine.fail_wmos = set()

    with patch("argopy.DataFetcher", MockProfileEngine), patch("siqva.fetcher.DEFAULT_CACHE_DIR", tmp_path / "cache"):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("temperature profiles in the Indian Ocean in January 2023")
        at.button(key="send_query_btn").click().run(timeout=30)

        assert len(at.exception) == 0

        # Verify fetch calls equal picks count (12)
        assert len(MockProfileEngine.all_recorded_calls) == 12

        # Verify Float Profiles metric indicates sample
        prof_metric = next((m for m in at.metric if m.label == "Float Profiles"), None)
        assert prof_metric is not None
        assert "Sample: 12 of " in prof_metric.value

        # Verify mandatory sample banner label is present
        info_texts = [i.value for i in at.info]
        assert any(
            "Sample: 12 of " in text and "Not representative of the whole region." in text
            for text in info_texts
        )

        # Verify Understood as contains basin
        caption_texts = [c.value for c in at.caption]
        assert any("Basin: Indian Ocean" in text for text in caption_texts)


def test_ui_s7_hovmoller_indian_ocean_refuse_with_options():
    """S7 AppTest 2: Hovmoller on Indian Ocean (REFUSE with design sentence and options)."""
    at = AppTest.from_file(UI_PATH)
    at.run(timeout=30)
    assert len(at.exception) == 0

    at.text_area[0].input("Hovmoller diagram of the Indian Ocean in January 2023")
    at.button(key="send_query_btn").click().run(timeout=30)

    assert len(at.exception) == 0

    # Verify refused error contains the required design sentence
    error_texts = [e.value for e in at.error]
    assert any(
        "A region-wide statistic needs all profiles; a sample would not represent it." in text
        for text in error_texts
    )

    # Verify structured options buttons are rendered
    btn_labels = [b.label for b in at.button]
    assert any("> Sub-region:" in lbl or "> View float position map" in lbl for lbl in btn_labels)


def test_ui_s7_float_map_metadata_only():
    """S7 AppTest 3: float-map request without dates/variables renders without remote fetch."""
    MockProfileEngine.all_recorded_calls = []

    with patch("argopy.DataFetcher", MockProfileEngine):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("show floats in the Indian Ocean")
        at.button(key="send_query_btn").click().run(timeout=30)

        assert len(at.exception) == 0

        # No remote profile fetches were made
        assert len(MockProfileEngine.all_recorded_calls) == 0

        # Float Profiles metric is displayed
        prof_metric = next((m for m in at.metric if m.label == "Float Profiles"), None)
        assert prof_metric is not None


def test_ui_s7_bigger_sample_button_flow(tmp_path):
    """S7 AppTest 4: bigger-sample button re-runs with increased sample count."""
    MockProfileEngine.all_recorded_calls = []
    MockProfileEngine.fail_wmos = set()

    with patch("argopy.DataFetcher", MockProfileEngine), patch("siqva.fetcher.DEFAULT_CACHE_DIR", tmp_path / "cache"):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("temperature profiles in the Indian Ocean in January 2023")
        at.button(key="send_query_btn").click().run(timeout=30)

        assert len(at.exception) == 0
        assert len(MockProfileEngine.all_recorded_calls) == 12

        # Find and click the bigger sample button
        bigger_btn = next((b for b in at.button if "Bigger sample (24 profiles)" in b.label), None)
        assert bigger_btn is not None

        bigger_btn.click().run(timeout=30)
        assert len(at.exception) == 0

        # Total profile calls should now be 12 + 24 = 36
        assert len(MockProfileEngine.all_recorded_calls) == 36

        # Metric should now report 24 profiles
        prof_metric = next((m for m in at.metric if m.label == "Float Profiles"), None)
        assert prof_metric is not None
        assert "Sample: 24 of " in prof_metric.value


def test_ui_s7_small_arabian_sea_full_flow(sample_fetch_result):
    """S7 AppTest 5: small Arabian Sea request renders FULL path with Full label."""
    with patch("siqva.pipeline.fetch", return_value=sample_fetch_result):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("temperature profiles in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)

        assert len(at.exception) == 0

        # Verify metric shows Full: all
        prof_metric = next((m for m in at.metric if m.label == "Float Profiles"), None)
        assert prof_metric is not None
        assert "Full: all " in prof_metric.value

        # Verify sample warning banner is NOT present
        info_texts = [i.value for i in at.info]
        assert not any("Not representative of the whole region." in text for text in info_texts)


def test_ui_s7_sample_partial_failure(tmp_path):
    """S7 AppTest 6: partial failure during sample fetch handles missing profiles gracefully."""
    MockProfileEngine.all_recorded_calls = []
    MockProfileEngine.fail_wmos = set()
    MockProfileEngine.fail_first_n = 2
    MockProfileEngine.fail_count = 0

    with patch("argopy.DataFetcher", MockProfileEngine), patch("siqva.fetcher.DEFAULT_CACHE_DIR", tmp_path / "cache"):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("temperature profiles in the Indian Ocean in January 2023")
        at.button(key="send_query_btn").click().run(timeout=30)

        assert len(at.exception) == 0

        # Successful profiles (10 of 12) rendered
        prof_metric = next((m for m in at.metric if m.label == "Float Profiles"), None)
        assert prof_metric is not None
        assert "Sample: 10 of " in prof_metric.value

        # Notice about failed profiles in warning
        warning_texts = [w.value for w in at.warning]
        assert any("could not be loaded" in text or "Failures:" in text or "profiles fetched" in text for text in warning_texts)


def test_ui_s7_sample_budget_exceeded(tmp_path):
    """S7 AppTest 7: wall-clock budget exceeded during sample fetch displays partial profiles."""
    MockProfileEngine.all_recorded_calls = []
    MockProfileEngine.fail_wmos = set()

    with patch("argopy.DataFetcher", MockProfileEngine), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", tmp_path / "cache"), \
         patch("siqva.fetcher.get_wall_clock_budget", return_value=0.001), \
         patch("siqva.fetcher.time.sleep"):  # no delay
        # Patch monotonic so after 3 profiles it reports past budget
        real_monotonic = [0.0]
        call_count = [0]
        def fake_monotonic():
            call_count[0] += 1
            if call_count[0] <= 4:
                return 0.0
            return 100.0  # budget exceeded

        with patch("time.monotonic", side_effect=fake_monotonic):
            at = AppTest.from_file(UI_PATH)
            at.run(timeout=30)
            assert len(at.exception) == 0

            at.text_area[0].input("temperature profiles in the Indian Ocean in January 2023")
            at.button(key="send_query_btn").click().run(timeout=30)

            assert len(at.exception) == 0

            # Warning about budget exceeded
            warning_texts = [w.value for w in at.warning]
            assert any("budget exceeded" in text.lower() for text in warning_texts)



@pytest.mark.parametrize(
    "question",
    [
        "show floats in the Pacific Ocean",
        "how many profiles in the Pacific Ocean in 2023",
        "show floats in the Indian Ocean in January 2023",
    ],
)
def test_ui_basin_and_metadata_queries_no_exceptions(question: str):
    """Proves basin metadata questions render in Streamlit UI without any exception element."""
    at = AppTest.from_file(UI_PATH)
    at.run(timeout=30)
    assert len(at.exception) == 0

    at.text_area[0].input(question)
    at.button(key="send_query_btn").click().run(timeout=30)

    # Confirm there is NO exception element on the page
    assert len(at.exception) == 0

