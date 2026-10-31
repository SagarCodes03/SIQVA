"""Unit tests for app/ui.py helpers (HTML escaping and UI sanitization)."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ui import build_clarification_banner_html, build_graph_card_html


def test_clarification_banner_escapes_html_and_scripts():
    """Proves user-supplied clarification text containing scripts/tags is escaped to plain text."""
    malicious = "<script>alert(1)</script> and <b>x</b>"
    html_out = build_clarification_banner_html(malicious)

    # Must contain HTML-escaped characters
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_out
    assert "&lt;b&gt;x&lt;/b&gt;" in html_out

    # Must NOT contain raw unescaped script or HTML injection
    assert "<script>" not in html_out
    assert "</script>" not in html_out
    assert "<b>" not in html_out
    assert "</b>" not in html_out


def test_graph_card_escapes_html():
    """Proves graph card builder escapes dynamic text."""
    html_out = build_graph_card_html("🌊", "Title <img src=x onerror=alert(1)>", "Desc & 'test'")
    assert "&lt;img" in html_out
    assert "&amp;" in html_out
    assert "<img" not in html_out
