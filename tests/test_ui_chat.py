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


def test_chat_empty_state_renders_clean_without_suggested_queries(tmp_path):
    """Empty state renders clean header and prompt dock without cluttered suggested queries."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch.dict("os.environ", {"SIQVA_STREAM": "0"}):

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Suggested starter buttons are completely removed
        starter_buttons = [b for b in at.button if b.key and b.key.startswith("quick_starter_")]
        assert len(starter_buttons) == 0, f"Expected 0 example starter buttons, got {len(starter_buttons)}"


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


def test_no_button_label_over_28_characters_ast_and_runtime(tmp_path):
    """AST scan and runtime check: no button label anywhere is longer than 28 characters."""
    # 1. AST scan on app/chat_ui.py and app/ui.py
    for py_file in [
        Path(__file__).resolve().parent.parent / "app" / "chat_ui.py",
        Path(__file__).resolve().parent.parent / "app" / "ui.py",
    ]:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                is_st_button = isinstance(node.func, ast.Attribute) and node.func.attr == "button"
                if is_st_button and node.args:
                    first_arg = node.args[0]
                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                        assert len(first_arg.value) <= 28, (
                            f"Hardcoded button label '{first_arg.value}' in {py_file.name} "
                            f"at line {node.lineno} exceeds 28 characters ({len(first_arg.value)})"
                        )

    # 2. Runtime check on live rendered widgets
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch.dict("os.environ", {"SIQVA_STREAM": "0", "SIQVA_ADMIN": "1"}):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0
        for btn in at.button:
            assert len(btn.label) <= 28, f"Rendered button '{btn.label}' (key={btn.key}) exceeds 28 characters"


def test_clarification_shows_no_duplicated_sentence(tmp_path):
    """Clarification messages show a single plain sentence without duplicate text or whole sentence buttons."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch.dict("os.environ", {"SIQVA_STREAM": "0"}):
        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Ask query missing year
        at.text_area[0].input("temperature in the Arabian Sea")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0

        msgs = at.session_state["chat_messages"]
        assert len(msgs) == 2
        clarif = msgs[1]
        assert clarif.kind == "clarification"

        # Verify message text is a single plain sentence
        clean_sentence = clarif.text.replace("e.g.", "eg")
        sentences = [s.strip() for s in clean_sentence.split(".") if s.strip()]
        assert len(sentences) == 1, f"Expected 1 sentence, got: {clarif.text}"
        assert "Please specify a year or date range" in clarif.text

        # Verify options are short tokens (years), not full sentences
        assert len(clarif.options) == 5
        for opt in clarif.options:
            assert len(opt.label) <= 28
            assert len(opt.label) == 4  # Year string like '2026'

        # Verify pills are rendered and no duplicate suggestion header exists
        assert len(at.pills) >= 1
        pill_options = at.pills[0].options
        assert len(pill_options) == 5
        for popt in pill_options:
            assert len(popt) <= 28


def test_mlops_page_and_toggle_hidden_without_admin(tmp_path):
    """When SIQVA_ADMIN is not set, MLOps nav button, sidebar toggle, and page are inaccessible."""
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    # 1. Without SIQVA_ADMIN (default)
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch.dict("os.environ", {"SIQVA_STREAM": "0"}, clear=False):
        import os
        os.environ.pop("SIQVA_ADMIN", None)

        at = AppTest.from_file(UI_PATH)
        at.run(timeout=30)
        assert len(at.exception) == 0

        # Nav button and toggle must NOT exist
        mlops_btns = [b for b in at.button if b.key == "nav_mlops_btn"]
        assert len(mlops_btns) == 0, "nav_mlops_btn must be hidden without SIQVA_ADMIN"
        guardrail_toggles = [t for t in at.toggle if t.key == "sidebar_guardrail_toggle"]
        assert len(guardrail_toggles) == 0, "sidebar_guardrail_toggle must be hidden without SIQVA_ADMIN"

    # 2. With SIQVA_ADMIN=1
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir), \
         patch.dict("os.environ", {"SIQVA_STREAM": "0", "SIQVA_ADMIN": "1"}):

        at_admin = AppTest.from_file(UI_PATH)
        at_admin.run(timeout=30)
        assert len(at_admin.exception) == 0

        admin_btns = [b for b in at_admin.button if b.key == "nav_mlops_btn"]
        assert len(admin_btns) == 1, "nav_mlops_btn must be visible with SIQVA_ADMIN=1"
        admin_toggles = [t for t in at_admin.toggle if t.key == "sidebar_guardrail_toggle"]
        assert len(admin_toggles) == 1, "sidebar_guardrail_toggle must be visible with SIQVA_ADMIN=1"

