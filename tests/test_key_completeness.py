"""Static AST scanner and AppTest assertions for Streamlit key completeness.

Ensures that:
1. Every call to st.plotly_chart, st.button, st.download_button, st.data_editor,
   and st.selectbox inside app/chat_ui.py and _render_pipeline_result in app/ui.py
   has an explicit key argument.
2. In AppTest runs, 0 exception elements are raised and the number of rendered
   plotly_chart elements strictly equals the expected number of figures drawn.
"""

import ast
from pathlib import Path
from unittest.mock import patch
import pytest
from streamlit.testing.v1 import AppTest

from tests.test_ui_smoke import MockProfileEngine

CHAT_UI_PATH = Path("app/chat_ui.py")
UI_PATH = Path("app/ui.py")
TARGET_ELEMENTS = {
    "plotly_chart",
    "button",
    "download_button",
    "data_editor",
    "selectbox",
}


def count_plotly_charts(at: AppTest) -> int:
    """Count rendered plotly_chart elements in the AppTest element tree."""
    return len([e for e in at._tree if getattr(e, "type", None) == "plotly_chart"])


def _check_ast_keys(tree: ast.AST, filename: str, filter_func_name: str | None = None) -> list[str]:
    """Walk AST tree and return descriptions of target st calls missing key= keyword."""
    violations: list[str] = []

    def _is_target_call(node: ast.Call) -> tuple[bool, str]:
        if isinstance(node.func, ast.Attribute):
            # Check st.<target>
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "st":
                if node.func.attr in TARGET_ELEMENTS:
                    return True, f"st.{node.func.attr}"
        return False, ""

    nodes_to_check = []
    if filter_func_name:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == filter_func_name:
                nodes_to_check.append(node)
                break
    else:
        nodes_to_check.append(tree)

    for root in nodes_to_check:
        for node in ast.walk(root):
            if isinstance(node, ast.Call):
                is_target, name = _is_target_call(node)
                if is_target:
                    has_key = any(kw.arg == "key" for kw in node.keywords if kw.arg is not None)
                    if not has_key:
                        violations.append(f"{filename}:{node.lineno} -> {name} called without explicit key=")

    return violations


def test_ast_chat_ui_keys():
    """Ensure every target Streamlit widget/chart in app/chat_ui.py has key=."""
    tree = ast.parse(CHAT_UI_PATH.read_text(encoding="utf-8"), filename=str(CHAT_UI_PATH))
    violations = _check_ast_keys(tree, str(CHAT_UI_PATH))
    assert not violations, f"Missing key= in chat_ui.py:\n" + "\n".join(violations)


def test_ast_render_pipeline_result_keys():
    """Ensure every target Streamlit widget/chart in _render_pipeline_result has key=."""
    tree = ast.parse(UI_PATH.read_text(encoding="utf-8"), filename=str(UI_PATH))
    violations = _check_ast_keys(tree, str(UI_PATH), filter_func_name="_render_pipeline_result")
    assert not violations, f"Missing key= in _render_pipeline_result:\n" + "\n".join(violations)


def test_apptest_chart_counts_and_zero_exceptions(tmp_path):
    """AppTest verifying 0 exceptions and exact plotly_chart element count."""
    MockProfileEngine.all_recorded_calls = []
    db_file = tmp_path / "cards.sqlite"
    cache_dir = tmp_path / "cache"

    with patch("argopy.DataFetcher", MockProfileEngine), \
         patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.fetcher.DEFAULT_CACHE_DIR", cache_dir):

        at = AppTest.from_file(str(UI_PATH))
        at.run(timeout=30)
        assert len(at.exception) == 0
        assert count_plotly_charts(at) == 0

        # Turn 1: Profile query (produces 2 figures: map + profile)
        at.text_area[0].input("temperature in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        # Active result renders 2 charts (map and primary profile)
        assert count_plotly_charts(at) == 2

        # Turn 2: Salinity query (produces 2 figures: map + profile)
        at.text_area[0].input("salinity in the Arabian Sea between 2022-01-01 and 2022-01-05")
        at.button(key="send_query_btn").click().run(timeout=30)
        assert len(at.exception) == 0
        # Older result is collapsed, newest result has 2 charts
        assert count_plotly_charts(at) == 2

        # Turn 3: Open 'Show plots' on older result
        toggle_btn = next((b for b in at.button if b.label == "Show plots"), None)
        assert toggle_btn is not None
        toggle_btn.click().run(timeout=30)
        assert len(at.exception) == 0
        # Now BOTH results are rendering their figures: 2 + 2 = 4 charts!
        assert count_plotly_charts(at) == 4
