"""Extract text from present knowledge base sources with citation markers.

Supports:
- PDF (via PyMuPDF / fitz): emits '=== PAGE n ===' markers.
- HTML (via beautifulsoup4): emits '=== SECTION: heading ===' markers.
- DOCX (via zipfile XML): emits '=== SECTION: heading ===' markers.

Outputs:
- knowledge/text/<source_id>.txt
- Summary report of pages, characters, and scanned/empty checks.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

import fitz  # PyMuPDF
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("extract_sources")

MANIFEST_PATH = Path("knowledge/manifest.csv")
TEXT_OUT_DIR = Path("knowledge/text")


def extract_pdf(pdf_path: Path) -> tuple[str, int, int]:
    """Extract text from PDF with '=== PAGE n ===' markers.

    Returns:
        (text, page_count, char_count)
    """
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    parts = []

    for idx, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        parts.append(f"=== PAGE {idx} ===\n{text}\n")

    doc.close()
    full_text = "\n".join(parts)
    return full_text, page_count, len(full_text)


def extract_html(html_path: Path) -> tuple[str, int, int]:
    """Extract text from HTML with '=== SECTION: heading ===' markers.

    Returns:
        (text, section_count, char_count)
    """
    raw_html = html_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw_html, "html.parser")

    # Remove script, style, noscript, svg
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()

    sections = []
    current_heading = "Introduction"
    current_lines: list[str] = []

    # Traverse elements under body or document
    body = soup.body or soup

    for elem in body.descendants:
        if elem.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            heading_text = elem.get_text().strip()
            if heading_text:
                if current_lines:
                    text_block = "\n".join(current_lines).strip()
                    if text_block:
                        sections.append(f"=== SECTION: {current_heading} ===\n{text_block}\n")
                    current_lines = []
                current_heading = re.sub(r"\s+", " ", heading_text)
        elif elem.name in ("p", "li", "td", "th", "div"):
            # Only direct text or text of leaf-like containers
            text = elem.get_text(separator=" ", strip=True)
            # Avoid duplicating parent/child blocks: if string is already in current lines, skip
            if text and (not current_lines or text != current_lines[-1]):
                # Add if not excessively long child duplicate
                if len(text) > 3 and not any(text in line for line in current_lines[-3:]):
                    current_lines.append(text)

    if current_lines:
        text_block = "\n".join(current_lines).strip()
        if text_block:
            sections.append(f"=== SECTION: {current_heading} ===\n{text_block}\n")

    if not sections:
        # Fallback to plain stripped text
        plain = body.get_text(separator="\n", strip=True)
        sections.append(f"=== SECTION: Document ===\n{plain}\n")

    full_text = "\n".join(sections)
    return full_text, len(sections), len(full_text)


def extract_docx(docx_path: Path) -> tuple[str, int, int]:
    """Extract text from DOCX with '=== SECTION: heading ===' markers.

    Returns:
        (text, section_count, char_count)
    """
    with zipfile.ZipFile(docx_path) as z:
        xml_content = z.read("word/document.xml")

    tree = ET.fromstring(xml_content)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    sections = []
    current_heading = "Overview"
    current_lines = []

    for p in tree.iter(f"{{{ns['w']}}}p"):
        p_text = "".join(node.text for node in p.iter(f"{{{ns['w']}}}t") if node.text).strip()
        if not p_text:
            continue

        # Check if paragraph has heading style or looks like a question/heading
        is_heading = False
        pStyle = p.find(f".//{{{ns['w']}}}pStyle")
        if pStyle is not None:
            val = pStyle.attrib.get(f"{{{ns['w']}}}val", "").lower()
            if "heading" in val or "title" in val:
                is_heading = True

        if is_heading or (p_text.endswith("?") and len(p_text) < 120):
            if current_lines:
                text_block = "\n".join(current_lines).strip()
                if text_block:
                    sections.append(f"=== SECTION: {current_heading} ===\n{text_block}\n")
                current_lines = []
            current_heading = p_text
        else:
            current_lines.append(p_text)

    if current_lines:
        text_block = "\n".join(current_lines).strip()
        if text_block:
            sections.append(f"=== SECTION: {current_heading} ===\n{text_block}\n")

    full_text = "\n".join(sections)
    return full_text, len(sections), len(full_text)


def extract_all_sources(
    manifest_path: Path = MANIFEST_PATH,
    output_dir: Path = TEXT_OUT_DIR,
) -> list[dict]:
    """Extract text from all sources marked 'present' in the manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report = []

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))

    for row in reader:
        if row["status"] != "present":
            continue

        source_id = row["id"]
        local_path = Path(row["local_path"])

        if not local_path.exists():
            logger.warning("File missing for [%s]: %s", source_id, local_path)
            report.append({
                "id": source_id,
                "status": "missing_file",
                "units": 0,
                "chars": 0,
                "empty_warning": True,
            })
            continue

        suffix = local_path.suffix.lower()
        try:
            if suffix == ".pdf":
                text, units, chars = extract_pdf(local_path)
                unit_label = "pages"
            elif suffix in (".html", ".htm"):
                text, units, chars = extract_html(local_path)
                unit_label = "sections"
            elif suffix == ".docx":
                text, units, chars = extract_docx(local_path)
                unit_label = "sections"
            elif suffix in (".txt", ".md"):
                raw = local_path.read_text(encoding="utf-8", errors="ignore")
                text = f"=== SECTION: Full Document ===\n{raw}\n"
                units, chars = 1, len(text)
                unit_label = "sections"
            else:
                logger.warning("Unsupported file extension for [%s]: %s", source_id, suffix)
                continue

            out_file = output_dir / f"{source_id}.txt"
            out_file.write_text(text, encoding="utf-8")

            is_scanned_or_empty = chars < 150
            if is_scanned_or_empty:
                logger.warning(
                    "Warning: Source [%s] has only %d characters. Possible scanned/empty file.",
                    source_id,
                    chars,
                )

            logger.info("Extracted [%s] -> %d %s, %d characters", source_id, units, unit_label, chars)
            report.append({
                "id": source_id,
                "suffix": suffix,
                "units": units,
                "unit_label": unit_label,
                "chars": chars,
                "empty_warning": is_scanned_or_empty,
            })

        except Exception as e:
            logger.error("Failed extracting [%s]: %s", source_id, e)
            report.append({
                "id": source_id,
                "status": f"error: {e}",
                "units": 0,
                "chars": 0,
                "empty_warning": True,
            })

    return report


if __name__ == "__main__":
    results = extract_all_sources()
    print("\n--- Extraction Report ---")
    for r in results:
        warn = " [WARNING: EMPTY/SCANNED?]" if r.get("empty_warning") else ""
        print(f"{r['id']:<22} | {r.get('units', 0):>3} {r.get('unit_label', 'units'):<8} | {r.get('chars', 0):>8} chars{warn}")

