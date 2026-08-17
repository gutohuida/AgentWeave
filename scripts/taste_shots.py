"""Capture the spec document for the taste pass, in both themes, and measure the frame background.

`uishot.py` captures a URL, but the Hub UI is state-driven rather than routed, so reaching a
specific document needs driving. This seeds sessionStorage/localStorage (skipping the setup modal
and pre-selecting the project), clicks through to the document, screenshots it, and reads the
*computed* background inside the spec iframe — which is the objective half of F2.

    python scripts/taste_shots.py --key aw_live_... --project proj-5e960453
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# From SpecFrame.tsx's HUB_NEUTRALS — what the frame background is supposed to equal.
EXPECTED_BG = {"light": "rgb(250, 250, 250)", "dark": "rgb(10, 10, 11)"}


def run(url: str, key: str, project: str, theme: str, out: Path) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, color_scheme=theme)
            ctx.add_init_script(
                "window.sessionStorage.setItem('agentweave-session', %s);"
                "window.localStorage.setItem('agentweave-selected-project', %s);"
                % (
                    json.dumps(json.dumps({"apiKey": key, "hubUrl": url})),
                    json.dumps(project),
                )
            )
            page = ctx.new_page()
            page.goto(url, wait_until="load")
            page.wait_for_timeout(1500)

            if theme == "dark":
                toggle = page.get_by_role("button", name="Switch to dark mode")
                if toggle.count() > 0:
                    toggle.first.click()
                    page.wait_for_timeout(400)

            # Into the spec surface. The topmost "Spec" is the tab in the project header; a second
            # one lower down is a summary card, and clicking that does not navigate — measured, not
            # assumed (the first attempt at this captured Overview and reported one frame).
            tabs = page.get_by_text("Spec", exact=True)
            target = None
            for el in tabs.all():
                box = el.bounding_box()
                if box and box["y"] < 120:
                    target = el
                    break
            if target is not None:
                target.click()
                page.wait_for_timeout(1500)

            # Open the seeded document if a picker is showing.
            doc = page.get_by_text("Quiet hours", exact=False)
            if doc.count() > 0:
                doc.first.click()
                page.wait_for_timeout(2000)

            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), full_page=True)

            result = {"theme": theme, "shot": str(out), "frames": len(page.frames)}

            # The objective half of F2: computed background inside the rendered document.
            for fr in page.frames:
                try:
                    bg = fr.evaluate("getComputedStyle(document.body).backgroundColor")
                    has_modal = fr.evaluate(
                        "!!document.querySelector('.aw-modal-must, .aw-modal-should, .aw-modal-may')"
                    )
                    colours = fr.evaluate(
                        "Array.from(document.querySelectorAll('.aw-modal')).slice(0,6)"
                        ".map(e => e.textContent.trim() + '=' + getComputedStyle(e).color)"
                    )
                    if bg and bg != "rgba(0, 0, 0, 0)":
                        result["frame_bg"] = bg
                        result["expected_bg"] = EXPECTED_BG[theme]
                        result["bg_matches"] = bg == EXPECTED_BG[theme]
                        result["modal_classes_present"] = has_modal
                        result["modal_colours"] = colours
                except Exception:
                    continue
            return result
        finally:
            browser.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8010")
    ap.add_argument("--key", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--outdir", type=Path, default=Path(".claude/taste-shots"))
    args = ap.parse_args()

    for theme in ("light", "dark"):
        res = run(args.url, args.key, args.project, theme, args.outdir / f"spec-{theme}.png")
        print(json.dumps(res, indent=1))
    return 0


sys.exit(main())
