"""Comprehensive AppTests for persistent chat interface (ChatGPT/Claude style).

Covers:
- 3 successive questions produce 6 conversation messages (scrollable history).
- Clarification button click submits next turn without overwriting earlier turns.
- 'Show plots' toggle on older result renders plots and metrics on demand.
- 'Clear chat' empties conversation.
- HTML escaping protects against injection attacks.
- Browser refresh via st.query_params["session_id"] restores conversation from SQLite.
- Sidebar navigation: Plot Graph and Compare Runs pages continue to render cleanly.
"""

from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.spec import DepthRange

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
        data_hash="dummyhash_chat",
        fetch_key="dummykey_chat",
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key="dummykey_chat",
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
    )


def test_chat_successive_questions_scrollable_history(tmp_path, sample_fetch_result):
    """3 successive questions produce 6 conversation messages in a scrollable thread."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Turn 1: Argo data query
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.session_state["chat_messages"]) == 2

        # Turn 2: Follow-up question (salinity)
        at.text_area[0].input("what about salinity?")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.session_state["chat_messages"]) == 4

        # Turn 3: Knowledge question
        at.text_area[0].input("what is teos-10?")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.session_state["chat_messages"]) == 6

        # Verify chat messages alternate user / assistant
        roles = [m.role for m in at.session_state["chat_messages"]]
        assert roles == ["user", "assistant", "user", "assistant", "user", "assistant"]

        # Verify all 6 messages are rendered in chat message blocks
        assert len(at.chat_message) >= 6


def test_chat_clarification_button_click_without_overwriting(tmp_path, sample_fetch_result):
    """Clarification button click submits next turn without overwriting earlier turns."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Query missing a date range -> triggers date clarification with options
        at.text_area[0].input("temperature in the Arabian Sea")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Must have 2 messages: user query + assistant clarification
        assert len(at.session_state["chat_messages"]) == 2
        clarif_msg = at.session_state["chat_messages"][1]
        assert clarif_msg.kind == "clarification"
        assert len(clarif_msg.options) > 0

        # Click the first suggestion button (e.g. '> 2023' or similar)
        opt_btns = [b for b in at.button if b.key.startswith("opt_btn_")]
        assert len(opt_btns) > 0
        first_btn = opt_btns[0]
        chosen_label = first_btn.label.replace("> ", "").strip()

        first_btn.click().run(timeout=30)
        assert len(at.exception) == 0

        # Conversation must now have 4 messages, retaining earlier turns
        messages = at.session_state["chat_messages"]
        assert len(messages) == 4
        assert messages[0].text == "temperature in the Arabian Sea"
        assert messages[1].kind == "clarification"
        assert messages[2].role == "user"
        assert chosen_label in messages[2].text
        assert messages[3].role == "assistant"


def test_chat_show_plots_toggle_on_older_result(tmp_path, sample_fetch_result):
    """'Show plots' toggle on older result renders plots and metrics on demand."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Query 1
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        first_card_id = at.session_state["chat_messages"][1].card_id

        # Query 2: Makes Query 1 an older result
        at.text_area[0].input("salinity in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.session_state["chat_messages"]) == 4

        # Find 'Show plots' button for the older result
        toggle_btn = next((b for b in at.button if b.label == "Show plots"), None)
        assert toggle_btn is not None

        # Click 'Show plots'
        toggle_btn.click().run(timeout=30)
        assert len(at.exception) == 0

        # Now button label becomes 'Hide plots'
        hide_btn = next((b for b in at.button if b.label == "Hide plots"), None)
        assert hide_btn is not None

        # Clicking 'Hide plots' collapses the view
        hide_btn.click().run(timeout=30)
        assert len(at.exception) == 0
        assert any(b.label == "Show plots" for b in at.button)


def test_chat_clear_chat_button(tmp_path, sample_fetch_result):
    """'Clear chat' empties conversation history and resets session state."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)

        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.session_state["chat_messages"]) == 2

        # Click top clear chat button
        clear_btn = at.button(key="top_clear_chat_btn")
        clear_btn.click().run(timeout=30)
        assert len(at.exception) == 0

        # Conversation is now empty
        assert len(at.session_state["chat_messages"]) == 0
        assert at.session_state["pipeline_res"] is None


def test_chat_html_escaping_protects_against_injection(tmp_path):
    """HTML tags in user query are safely escaped and not rendered as raw markup."""
    db_file = tmp_path / "cards.sqlite"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)

        # Inject script and html tags
        malicious_input = "<script>alert('xss')</script><b>bold injection</b>"
        at.text_area[0].input(malicious_input)
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        # Verify escaped representation in markdown or chat message
        all_md = [m.value for m in at.markdown]
        # Raw <script> tag should never appear unescaped in markdown elements
        assert not any("<script>alert('xss')</script>" in md for md in all_md)
        # Escaped &lt;script&gt; should be present
        assert any("&lt;script&gt;" in md for md in all_md)


def test_chat_browser_refresh_restores_conversation(tmp_path, sample_fetch_result):
    """Browser refresh via st.query_params['session_id'] restores conversation from SQLite."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result):

        at1 = AppTest.from_file(UI_PATH)
        at1.run(timeout=30)

        at1.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at1.button(key="send_query_btn").click().run(timeout=30)
        assert len(at1.session_state["chat_messages"]) == 2
        active_session_id = at1.session_state["session_id"]
        assert active_session_id is not None

        # Simulate fresh browser session opening URL with ?session_id=<active_session_id>
        at2 = AppTest.from_file(UI_PATH)
        at2.query_params["session_id"] = active_session_id
        at2.run(timeout=30)
        assert len(at2.exception) == 0

        # Conversation restored from SQLite
        assert len(at2.session_state["chat_messages"]) == 2
        assert at2.session_state["session_id"] == active_session_id
        assert at2.session_state["chat_messages"][0].text == "temperature in the Arabian Sea between 2022-01-01 and 2022-01-05"


def test_chat_navigation_to_plot_graph_and_compare_runs(tmp_path):
    """Sidebar navigation: Plot Graph and Compare Runs pages continue to render cleanly."""
    db_file = tmp_path / "cards.sqlite"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Switch to Plot Graph
        at.button(key="nav_plot_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert at.session_state["active_page"] == "plots"

        # Switch to Compare Runs
        at.button(key="nav_compare_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert at.session_state["active_page"] == "compare"

        # Switch back to Chat
        at.button(key="nav_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        assert at.session_state["active_page"] == "query"
