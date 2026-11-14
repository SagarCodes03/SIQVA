"""AppTest reproduction for C1 duplicate plotly_chart bug.

Tests:
(a) the same question asked twice in a row
(b) two different questions
(c) a question followed by 'same for salinity'
(d) a question then 'Show plots' on an older result (both diff question and identical question)
"""

from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tests.test_ui_smoke import MockProfileEngine

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")
UI_PATH = str(Path(__file__).resolve().parent.parent / "app" / "ui.py")


def test_scenario_a_same_question_twice(tmp_path):
    """(a) The same question asked twice in a row (default collapsed older result)."""
    MockProfileEngine.all_recorded_calls = []
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("argopy.DataFetcher", MockProfileEngine), \
         patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Turn 1
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Turn 2: Same question
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0


def test_scenario_b_two_different_questions(tmp_path):
    """(b) Two different questions."""
    MockProfileEngine.all_recorded_calls = []
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("argopy.DataFetcher", MockProfileEngine), \
         patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Turn 1
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Turn 2: Different question
        at.text_area[0].input("salinity in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0


def test_scenario_c_question_then_same_for_salinity(tmp_path):
    """(c) A question followed by 'same for salinity'."""
    MockProfileEngine.all_recorded_calls = []
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("argopy.DataFetcher", MockProfileEngine), \
         patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Turn 1
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Turn 2: Follow-up 'same for salinity'
        at.text_area[0].input("same for salinity")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0


def test_scenario_d_show_plots_on_older_result_diff_question(tmp_path):
    """(d1) A question then 'Show plots' on an older result with different query."""
    MockProfileEngine.all_recorded_calls = []
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("argopy.DataFetcher", MockProfileEngine), \
         patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Turn 1: Query 1
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Turn 2: Query 2
        at.text_area[0].input("salinity in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Turn 3: Click 'Show plots' on older result
        toggle_btn = next((b for b in at.button if b.label == "Show plots"), None)
        assert toggle_btn is not None
        toggle_btn.click().run(timeout=30)
        assert len(at.exception) == 0


def test_scenario_d_show_plots_on_older_result_same_question(tmp_path):
    """(d2) Same question asked twice and 'Show plots' clicked on older result.
    
    Before adding explicit keys to plotly_chart, this triggers:
    StreamlitDuplicateElementId: multiple plotly_chart elements with the same auto-generated ID.
    """
    MockProfileEngine.all_recorded_calls = []
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("argopy.DataFetcher", MockProfileEngine), \
         patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Turn 1: Query 1
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Turn 2: Same Query
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Turn 3: Click 'Show plots' on older result
        toggle_btn = next((b for b in at.button if b.label == "Show plots"), None)
        assert toggle_btn is not None
        toggle_btn.click().run(timeout=30)
        # Without key_prefix on plotly_chart, this triggers StreamlitDuplicateElementId!
        assert len(at.exception) == 0
