"""AppTests for knowledge retrieval in the persistent chat interface and UI.

Covers:
- 'how does floats work' with switch ON returns answer with citation and unverified tag.
- 'how does floats work' with switch OFF returns the not-in-notes sentence + 'See sources' button.
- 'what is qc' with switch ON returns answer with citation.
- 'will it be warmer next year' returns Category 1 refusal.
- 'hello' returns greeting.
- Mixed query ('temperature in Arabian Sea in 2022 and will it be warmer next year') returns data result message followed by refusal message.
- Sources list renders in UI without errors.
- 0 exceptions and unique widget keys across all interactions.
"""

from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.spec import DepthRange
from siqva.knowledge import reset_knowledge_index

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")
UI_PATH = str(Path(__file__).resolve().parent.parent / "app" / "ui.py")


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
        data_hash="dummyhash_knowledge",
        fetch_key="dummykey_knowledge",
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key="dummykey_knowledge",
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
    )


def test_knowledge_chat_switch_on_how_does_floats_work(tmp_path, sample_fetch_result, monkeypatch):
    """'how does floats work' with switch ON returns answer with citation and unverified tag."""
    monkeypatch.setenv("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED", "1")
    reset_knowledge_index()

    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("how does floats work")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        msgs = at.session_state["chat_messages"]
        assert len(msgs) == 2
        user_msg, asst_msg = msgs[0], msgs[1]
        assert user_msg.role == "user"
        assert asst_msg.role == "assistant"
        assert asst_msg.kind == "knowledge"
        assert "[Unverified note]" in asst_msg.text
        assert "*Sources*:" in asst_msg.text
        assert "10-day" in asst_msg.text


def test_knowledge_chat_switch_off_how_does_floats_work(tmp_path, sample_fetch_result, monkeypatch):
    """'how does floats work' with switch OFF returns the not-in-notes sentence + 'See sources' button."""
    monkeypatch.setenv("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED", "0")
    reset_knowledge_index()

    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("how does floats work")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        msgs = at.session_state["chat_messages"]
        assert len(msgs) == 2
        asst_msg = msgs[1]
        assert asst_msg.kind == "knowledge"
        assert "I cannot answer this specific question because it is not covered in my verified knowledge notes" in asst_msg.text
        assert len(asst_msg.options) >= 1
        assert any(opt.action_type == "sources" and opt.label == "See sources" for opt in asst_msg.options)


def test_knowledge_chat_switch_on_what_is_qc(tmp_path, sample_fetch_result, monkeypatch):
    """'what is qc' with switch ON returns answer with citation."""
    monkeypatch.setenv("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED", "1")
    reset_knowledge_index()

    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("what is qc")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        msgs = at.session_state["chat_messages"]
        assert len(msgs) == 2
        asst_msg = msgs[1]
        assert asst_msg.kind == "knowledge"
        assert "quality control" in asst_msg.text.lower()
        assert "*Sources*:" in asst_msg.text


def test_chat_will_it_be_warmer_next_year_refusal(tmp_path, sample_fetch_result):
    """'will it be warmer next year' returns Category 1 refusal."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("will it be warmer next year")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        msgs = at.session_state["chat_messages"]
        assert len(msgs) == 2
        asst_msg = msgs[1]
        assert asst_msg.kind == "refusal"
        assert "cannot provide future weather or climate forecasts" in asst_msg.text


def test_chat_hello_greeting(tmp_path, sample_fetch_result):
    """'hello' returns greeting message."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("hello")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        msgs = at.session_state["chat_messages"]
        assert len(msgs) == 2
        asst_msg = msgs[1]
        assert asst_msg.kind == "text"
        assert "Hello! I am SIQVA" in asst_msg.text


def test_chat_mixed_query_data_and_refusal(tmp_path, sample_fetch_result):
    """Mixed query returns data result message followed by refusal message."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("temperature in Arabian Sea in 2022 and will it be warmer next year")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        msgs = at.session_state["chat_messages"]
        # User message + data result message + refusal message = 3
        assert len(msgs) == 3
        assert msgs[0].role == "user"
        assert msgs[1].role == "assistant"
        assert msgs[1].kind == "result"
        assert msgs[2].role == "assistant"
        assert msgs[2].kind == "refusal"
        assert "cannot provide future weather or climate forecasts" in msgs[2].text


def test_sources_page_and_navigation(tmp_path):
    """Sources list renders in UI without errors and navigation functions cleanly."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Click the Sources nav button
        at.button(key="nav_sources_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert at.session_state["active_page"] == "sources"
        assert len(at.dataframe) >= 1

        # Check return to query terminal
        at.button(key="nav_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert at.session_state["active_page"] == "query"


def test_chat_see_sources_button_action(tmp_path, sample_fetch_result, monkeypatch):
    """Clicking 'See sources' option button switches to Sources view."""
    monkeypatch.setenv("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED", "0")
    reset_knowledge_index()

    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        at.text_area[0].input("how does floats work")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        asst_msg = at.session_state["chat_messages"][1]
        assert asst_msg.options[0].label == "See sources"

        # Find the rendered button with key matching opt_btn_know_{asst_msg.id}_0
        btn_key = f"opt_btn_know_{asst_msg.id}_0"
        at.button(key=btn_key).click().run(timeout=30)
        assert len(at.exception) == 0
        assert at.session_state["active_page"] == "sources"
        assert at.session_state["show_sources_expander"] is True
        assert len(at.dataframe) >= 1

