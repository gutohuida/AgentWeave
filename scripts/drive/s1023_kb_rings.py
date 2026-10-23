"""Keyboard & dialogs, 2026-10-23: a close-up of the focus ring on each rail/top-bar stop whose ring
is not the app's teal box-shadow (the browser default outline, or a transparent one), in light and
dark mode. Reached by Tab only.

    py -3.11 scripts/drive/s1023_kb_rings.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402
from s1023_kb_lib import SHOTS, active, fmt, open_page  # noqa: E402

TARGETS = {"agent-menu-", "add-project", "pane-resizer", "Search"}

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    for mode in ("light", "dark"):
        page = open_page(browser)
        page.evaluate(
            "m => { localStorage.setItem('agentweave-prefs', JSON.stringify({mode: m}));"
            " document.documentElement.dataset.mode = m; }",
            mode,
        )
        page.wait_for_timeout(300)
        for i in range(22):
            page.keyboard.press("Tab")
            page.wait_for_timeout(150)
            a = active(page)
            name = a.get("testid") or a.get("aria") or ""
            if any(t in name for t in TARGETS):
                box = page.evaluate(
                    "() => { const r = document.activeElement.getBoundingClientRect();"
                    " return {x: r.x, y: r.y, w: r.width, h: r.height}; }"
                )
                clip = {
                    "x": max(0, box["x"] - 24),
                    "y": max(0, box["y"] - 16),
                    "width": box["w"] + 48,
                    "height": box["h"] + 32,
                }
                path = SHOTS / f"ring_{mode}_{name.replace(' ', '_')[:24]}.png"
                page.screenshot(path=str(path), clip=clip)
                styles = page.evaluate(
                    "() => { const s = getComputedStyle(document.activeElement);"
                    " return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.outlineOffset, s.boxShadow,"
                    " document.activeElement.matches(':focus-visible')]; }"
                )
                print(mode, fmt(a), styles, path.name)
        page.context.close()
    browser.close()
