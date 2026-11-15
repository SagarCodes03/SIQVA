"""UI automation and overflow audit script for SIQVA chat interface.

Starts the Streamlit app on port 8765 in a subprocess (headless, SIQVA_STREAM=0),
drives a multi-turn conversation, captures screenshots at 1400, 1000, and 600 px
into scripts/ui_screens/, and audits the DOM for visual overflow.
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path

SCREENSHOT_DIR = Path(__file__).resolve().parent / "ui_screens"


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed in the current Python environment.")
        print("To install playwright: pip install playwright && playwright install chromium")
        return 1

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    port = 8765
    env = os.environ.copy()
    env["SIQVA_STREAM"] = "0"
    env.pop("SIQVA_KNOWLEDGE_INCLUDE_UNVERIFIED", None)

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app/ui.py",
        "--server.port",
        str(port),
        "--server.headless",
        "true",
    ]

    print(f"Starting Streamlit app on port {port}...")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(4)

    test_questions = [
        "hi",
        "thank you",
        "what is qc",
        "how to build a llm",
        "temperature in the Arabian Sea in March",
        "salinity in the South Atlantic in 2021",
        "https://example.com/" + "a" * 180,
        "will it be warmer next year",
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for width in [1400, 1000, 600]:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.goto(f"http://localhost:{port}")
                page.wait_for_timeout(2000)

                for q in test_questions:
                    chat_input = page.locator("textarea[data-testid='stChatInputTextArea']")
                    if chat_input.count() > 0:
                        chat_input.fill(q)
                        chat_input.press("Enter")
                        page.wait_for_timeout(1500)

                page.screenshot(path=str(SCREENSHOT_DIR / f"chat_{width}px.png"), full_page=True)

                # Overflow audit
                overflows = page.evaluate("""() => {
                    const issues = [];
                    const elements = document.querySelectorAll(
                        '[data-testid="stChatMessage"], [data-testid="stSidebar"], .siqva-chat-header, button'
                    );
                    for (const el of elements) {
                        if (el.scrollWidth > el.clientWidth + 1) {
                            issues.push({
                                tag: el.tagName,
                                testid: el.getAttribute('data-testid') || '',
                                text: (el.innerText || '').slice(0, 40),
                                scrollWidth: el.scrollWidth,
                                clientWidth: el.clientWidth,
                            });
                        }
                    }
                    return issues;
                }""")
                if overflows:
                    print(f"Found {len(overflows)} overflow issues at {width}px: {overflows}")
            browser.close()
    finally:
        proc.terminate()
        proc.wait(timeout=5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
