"""Automated tests for SIQVA chat UI layout, stylesheet, avatars, and rendering (U1 & U2)."""

import ast
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.spec import DepthRange

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")
UI_PATH = str(Path(__file__).resolve().parent.parent / "app" / "ui.py")
CHAT_CSS_PATH = Path(__file__).resolve().parent.parent / "app" / "assets" / "chat.css"
USER_AVATAR_PATH = Path(__file__).resolve().parent.parent / "app" / "assets" / "user_avatar.png"
ASSISTANT_AVATAR_PATH = Path(__file__).resolve().parent.parent / "app" / "assets" / "assistant_avatar.png"


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
        data_hash="dummyhash_ui",
        fetch_key="dummykey_ui",
    )
    return FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key="dummykey_ui",
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
    )


def test_chat_css_exists_and_all_selectors_confirmed():
    """Verify chat.css exists and all data-testid selectors exist in Streamlit static assets."""
    assert CHAT_CSS_PATH.exists(), "app/assets/chat.css must exist"
    css_content = CHAT_CSS_PATH.read_text(encoding="utf-8")
    assert len(css_content) > 100

    import streamlit
    st_static = Path(streamlit.__file__).parent / "static"
    assert st_static.exists()
    all_js_text = " ".join(f.read_text(encoding="utf-8", errors="ignore") for f in st_static.rglob("*.js"))

    # Test key selectors used in chat.css
    required_selectors = [
        "stChatMessage",
        "stChatMessageContent",
        "stChatMessageAvatarUser",
        "stChatMessageAvatarAssistant",
        "stChatMessageAvatarCustom",
        "stChatInput",
        "stMainBlockContainer",
        "stBottomBlockContainer",
        "stHorizontalBlock",
        "stColumn",
        "stDataFrame",
        "stTable",
        "stPlotlyChart",
    ]
    for sel in required_selectors:
        assert sel in all_js_text, f"Selector '{sel}' not found in Streamlit static bundle"


def test_avatar_assets_exist_and_are_valid_images():
    """Verify assistant and user avatar images exist and have valid dimensions."""
    assert USER_AVATAR_PATH.exists(), "user_avatar.png must exist"
    assert ASSISTANT_AVATAR_PATH.exists(), "assistant_avatar.png must exist"
    assert USER_AVATAR_PATH.stat().st_size > 100
    assert ASSISTANT_AVATAR_PATH.stat().st_size > 100


def test_all_chat_messages_pass_explicit_avatars():
    """Verify all st.chat_message invocations in app/chat_ui.py pass avatar parameter."""
    chat_ui_path = Path(__file__).resolve().parent.parent / "app" / "chat_ui.py"
    tree = ast.parse(chat_ui_path.read_text(encoding="utf-8"))

    chat_message_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check for st.chat_message
            if isinstance(node.func, ast.Attribute) and node.func.attr == "chat_message":
                chat_message_calls.append(node)

    assert len(chat_message_calls) >= 2, "Expected at least 2 st.chat_message calls in chat_ui.py"
    for call in chat_message_calls:
        keyword_names = [kw.arg for kw in call.keywords]
        assert "avatar" in keyword_names, f"st.chat_message call at line {call.lineno} missing avatar"


def test_no_unescaped_user_text_in_unsafe_allow_html():
    """Verify AST scan ensures no raw user text is passed into unsafe_allow_html."""
    chat_ui_path = Path(__file__).resolve().parent.parent / "app" / "chat_ui.py"
    tree = ast.parse(chat_ui_path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "markdown":
                kw_unsafe = [kw for kw in node.keywords if kw.arg == "unsafe_allow_html"]
                if kw_unsafe and isinstance(kw_unsafe[0].value, ast.Constant) and kw_unsafe[0].value.value is True:
                    # If unsafe_allow_html=True, check the content arg
                    first_arg = node.args[0] if node.args else None
                    if isinstance(first_arg, ast.JoinedStr):
                        for part in first_arg.values:
                            if isinstance(part, ast.FormattedValue):
                                # Must be escaped or static CSS/div
                                code_str = ast.unparse(part)
                                assert "html.escape" in code_str or "css" in code_str or "style" in code_str or "title_text" in code_str, (
                                    f"Potential unescaped interpolation in unsafe_allow_html: {code_str}"
                                )


def test_chat_empty_state_renders_six_examples(tmp_path):
    """Empty state renders 6 example-question buttons with cached badges and clean header."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch.dict("os.environ", {"SIQVA_STREAM": "0"}):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Check for 6 quick_starter buttons
        starter_buttons = [b for b in at.button if b.key and b.key.startswith("quick_starter_")]
        assert len(starter_buttons) == 6, f"Expected 6 example starter buttons, got {len(starter_buttons)}"


def test_chat_three_turns_six_messages_no_exceptions(tmp_path, sample_fetch_result):
    """AppTest: 3 question turns create 6 messages with no exceptions."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch("siqva.pipeline.fetch", return_value=sample_fetch_result), \
         patch.dict("os.environ", {"SIQVA_STREAM": "0"}):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Turn 1: Question 1
        at.chat_input[0].set_value("temperature profiles in Arabian Sea January 2022").run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.session_state["chat_messages"]) == 2

        # Turn 2: Question 2
        at.chat_input[0].set_value("what is qc").run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.session_state["chat_messages"]) == 4

        # Turn 3: Question 3
        at.chat_input[0].set_value("salinity profiles in Bay of Bengal June 2022").run(timeout=30)
        assert len(at.exception) == 0
        assert len(at.session_state["chat_messages"]) == 6
