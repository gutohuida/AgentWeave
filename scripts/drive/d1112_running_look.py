"""Acceptance drive for the Running tab (SPSRT-3), part 2: look at it.

Opens the Lead's build conversation on the trial Hub with Running open in the side panel, sized to
the panel's narrowest width (360 px), and for each theme writes a screenshot and the tab's text to
`testbed/running-drive/<label>-<mode>.png|.txt`. Also reports whether anything scrolls sideways.

    py -3.11 scripts/drive/d1112_running_look.py <label> [dark|light|both] [filter]
"""

import json
import pathlib
import sys

import d1029_build_plan_in_spec as d
from playwright.sync_api import sync_playwright

OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed" / "running-drive"
NARROWEST = 360


def open_running(page, state, mode):
    pid = state["pid"]
    conv = d.ro("select id, agent from conversations where project_id=? order by created_at limit 1", (pid,))[0]
    page.add_init_script(
        f"sessionStorage.setItem('agentweave-session', JSON.stringify({{apiKey: {d.KEY!r}, hubUrl: {d.HUB!r}}}));"
        f"localStorage.setItem('agentweave-selected-project', {pid!r});"
        f"localStorage.setItem('agentweave-prefs', JSON.stringify({{mode: {mode!r}}}));")
    page.goto(f"{d.HUB}/?project={pid}&agent={conv[1]}&conversation={conv[0]}", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)


def panel_box(page):
    tab = page.get_by_test_id("running-tab")
    return tab.bounding_box() if tab.count() else None


def open_narrow(page, state, mode):
    """Running open in the panel, sized to the narrowest width; returns the tab's box."""
    open_running(page, state, mode)
    if not page.get_by_test_id("running-tab").count():
        # Open it the way the operator does: the panel's plus menu, then Running.
        if not page.get_by_role("region", name="Panel").count() and not page.locator("[aria-label=Panel]").count():
            page.get_by_role("button", name="More conversation actions").click()
            page.get_by_test_id("conversation-toggle-panel").click()
            page.wait_for_timeout(800)
        page.get_by_text("Running", exact=True).last.click()
        page.get_by_test_id("running-tab").wait_for(timeout=15000)
    # Narrowest: widen the conversation column until the panel is 360 px wide.
    box = panel_box(page)
    if box and box["width"] > NARROWEST + 1:
        prefs = json.loads(page.evaluate("localStorage.getItem('aw.spec.presentation.v1') || '{}'") or "{}")
        width = prefs.get("conversationWidth") or 480
        page.evaluate(f"localStorage.setItem('aw.spec.presentation.v1', JSON.stringify({{conversationWidth: "
                      f"{int(width + box['width'] - NARROWEST)}}}))")
        page.reload(wait_until="domcontentloaded")
        page.get_by_test_id("running-tab").wait_for(timeout=15000)
        page.wait_for_timeout(1500)
        box = panel_box(page)
    return box


def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "look"
    modes = ["dark", "light"] if (len(sys.argv) < 3 or sys.argv[2] == "both") else [sys.argv[2]]
    pick = sys.argv[3] if len(sys.argv) > 3 else None
    state = json.loads((OUT / "state.json").read_text(encoding="utf-8"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for mode in modes:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            box = open_narrow(page, state, mode)
            if pick:
                page.get_by_role("radio", name=pick).first.click() if page.get_by_role("radio", name=pick).count() \
                    else page.get_by_text(pick, exact=True).first.click()
                page.wait_for_timeout(500)
            tab = page.get_by_test_id("running-tab")
            sideways = page.evaluate(
                "() => { const t = document.querySelector('[data-testid=running-tab]');"
                " const out = []; for (const el of [t, ...t.querySelectorAll('*')]) {"
                "  if (el.scrollWidth > el.clientWidth + 1 && getComputedStyle(el).overflowX !== 'hidden'"
                "      && getComputedStyle(el).overflowX !== 'clip' && el.clientWidth > 0)"
                "   out.push((el.className || el.tagName) + ' ' + el.scrollWidth + '>' + el.clientWidth); }"
                " return out; }")
            text = tab.inner_text()
            name = f"{label}-{mode}"
            tab.screenshot(path=str(OUT / f"{name}.png"))
            page.screenshot(path=str(OUT / f"{name}-page.png"))
            (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
            print(f"== {name}: panel {box and round(box['width'])}px, sideways={sideways}, errors={errors[:2]}")
            print(text)
            page.close()
        browser.close()


if __name__ == "__main__":
    main()
