#!/usr/bin/env python3
"""Headless browser regression checks for ReData's primary chart workflow."""
from __future__ import annotations

import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            response = page.goto(
                f"http://127.0.0.1:{server.server_port}/",
                wait_until="domcontentloaded",
            )
            assert response is not None and response.status == 200, "ReData page did not load"

            # The bundled sample dataset should make the visualization studio usable
            # without a file upload, so this covers the main rendering regression.
            page.locator('button[data-view="visualize"]').first.click()
            chart = page.locator("#chartHost svg")
            chart.wait_for(state="visible", timeout=10_000)
            assert chart.count() > 0, "Visualization studio did not render an SVG chart"

            # Regression assertion: the chart-help paragraph must be a real div.hint,
            # not a malformed custom tag such as <div<div ...>.
            help_text = page.locator("div.hint").filter(
                has_text="Hover or tap a mark to inspect its value."
            )
            assert help_text.count() == 1, "Chart-help markup is missing or malformed"

            page.get_by_role("button", name="Update chart").click()
            page.locator("#chartHost svg").wait_for(state="visible", timeout=10_000)
            assert not errors, "Uncaught browser errors: " + "; ".join(errors)
            print("PASS: page loads in Chromium")
            print("PASS: visualization studio renders an SVG chart")
            print("PASS: chart-help paragraph is valid div.hint markup")
            print("PASS: Update chart re-renders without uncaught JavaScript errors")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
