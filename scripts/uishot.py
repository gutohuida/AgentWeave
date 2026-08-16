"""Headless screenshot harness for the Hub UI.

This driver has no MCP preview tools (`.mcp.json` does not exist here and ~/.claude.json's
mcpServers is empty both globally and for this project), so a headless `claude -p` firing cannot
screenshot the running app the way an interactive session can. Playwright plus the Read tool closes
the same loop: this script renders a page to a PNG, and `Read` on that PNG is the visual read.

Points at whatever URL you give it — the live Hub on :8010 serves `hub/hub/static/ui`, a COMMITTED
BUILD ARTEFACT (see CLAUDE.md), so a UI source change will not show up here until
`cd hub/ui && npm run build && python scripts/refresh_ui_bundle.py`, or you point --url at the Vite
dev server (`npm run dev`, :5173) instead. Check which one you used before trusting a capture.

    python scripts/uishot.py --url http://127.0.0.1:8010 --theme dark --width 1280 --out shot.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from playwright.sync_api import sync_playwright


def capture(
    url: str,
    theme: Literal["light", "dark"],
    width: int,
    height: int,
    out: Path,
    wait_selector: str | None,
) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                # This ONLY affects the `prefers-color-scheme` media query, which the app does
                # not read — its light/dark mode is app state (configStore's `mode`, persisted
                # to localStorage and flipped by a button), not an OS preference. Kept here
                # because it costs nothing and is correct for any future component that *does*
                # key off the media query; the real switch below is what actually changes theme.
                color_scheme=theme,
            )
            page = context.new_page()
            # Not "networkidle": the app holds an SSE connection open for live updates, so the
            # network is never idle and that wait condition would time out on every real page.
            page.goto(url, wait_until="load")
            page.wait_for_timeout(500)
            if theme == "dark":
                toggle = page.get_by_role("button", name="Switch to dark mode")
                if toggle.count() > 0:
                    toggle.first.click()
                    page.wait_for_timeout(200)
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=10_000)
            else:
                page.wait_for_timeout(500)
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), full_page=True)
        finally:
            browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="page to capture, e.g. http://127.0.0.1:8010/")
    parser.add_argument("--theme", choices=["light", "dark"], default="light")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--wait-selector",
        default=None,
        help="CSS selector to wait for before capturing, if the page renders asynchronously",
    )
    args = parser.parse_args()

    try:
        capture(args.url, args.theme, args.width, args.height, args.out, args.wait_selector)
    except Exception as exc:  # noqa: BLE001 - report and exit non-zero rather than a raw traceback
        print(f"uishot failed: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
