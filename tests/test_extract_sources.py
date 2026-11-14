"""Unit tests for text extraction from PDF and HTML sources."""

from pathlib import Path
import fitz
import pytest

from scripts.extract_sources import extract_html, extract_pdf


def test_extract_pdf_markers(tmp_path: Path):
    """Verify PDF extraction includes === PAGE n === markers."""
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()

    p1 = doc.new_page()
    p1.insert_text((50, 50), "First page content for testing.")

    p2 = doc.new_page()
    p2.insert_text((50, 50), "Second page content for testing.")

    doc.save(pdf_path)
    doc.close()

    text, page_count, char_count = extract_pdf(pdf_path)

    assert page_count == 2
    assert "=== PAGE 1 ===" in text
    assert "First page content" in text
    assert "=== PAGE 2 ===" in text
    assert "Second page content" in text
    assert char_count > 50


def test_extract_html_markers(tmp_path: Path):
    """Verify HTML extraction emits === SECTION: heading === markers."""
    html_path = tmp_path / "sample.html"
    html_content = """<!DOCTYPE html>
    <html>
    <head><title>Test Document</title></head>
    <body>
      <h1>Overview</h1>
      <p>This is the initial overview paragraph describing the float.</p>
      <h2>Data Quality</h2>
      <p>Here are details on real-time and delayed-mode quality control.</p>
    </body>
    </html>
    """
    html_path.write_text(html_content, encoding="utf-8")

    text, section_count, char_count = extract_html(html_path)

    assert section_count >= 2
    assert "=== SECTION: Overview ===" in text
    assert "initial overview paragraph" in text
    assert "=== SECTION: Data Quality ===" in text
    assert "real-time and delayed-mode quality control" in text
    assert char_count > 50

