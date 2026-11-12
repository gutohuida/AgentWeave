"""Acceptance drive for the Running tab (SPSRT-3), part 3: live, without a reload.

With Running open beside the Lead's conversation (one page load, never reloaded), fires the
"Two notes" and "Ask first" flows on the trial Hub and watches the tab: every change to the
"Two notes" and "Ask first" rows is printed with its time. When "Ask first" reads Needs you, it
screenshots, presses Answer, screenshots what Answer shows, and answers the question there. It keeps
watching until "Two notes" has a task done and its worker is on the next one, or LIMIT passes.

    py -3.11 scripts/drive/d1112_running_live.py
"""

import json
import sys
import time

import d1029_build_plan_in_spec as d
import d1112_running_look as look
from playwright.sync_api import sync_playwright

LIMIT = 30 * 60


def row_text(page, title):
    return page.evaluate(
        "(t) => { for (const li of document.querySelectorAll('[data-testid=running-tab] li.aw-run-item')) {"
        " if (li.querySelector('.aw-run-title')?.textContent === t) return li.dataset.phase + ' | ' + li.innerText.replace(/\\n/g, ' / '); }"
        " return null }", title)


def main():
    state = json.loads((look.OUT / "state.json").read_text(encoding="utf-8"))
    base = state["base"]
    flow, ask = state["builds"]["flow"], state["builds"]["question"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        look.open_running(page, state, "dark")
        if not page.get_by_test_id("running-tab").count():
            page.get_by_role("button", name="More conversation actions").click()
            page.get_by_test_id("conversation-toggle-panel").click()
            page.wait_for_timeout(800)
            page.get_by_text("Running", exact=True).last.click()
        page.get_by_test_id("running-tab").wait_for(timeout=15000)
        loads = page.evaluate("performance.getEntriesByType('navigation').length")
        seen = {}

        def watch():
            for title in ("Two notes", "Ask first"):
                text = row_text(page, title)
                if text != seen.get(title):
                    seen[title] = text
                    print(f"{time.strftime('%H:%M:%S')} {title}: {text}", flush=True)

        watch()
        d.fire(base, flow["job"])
        d.fire(base, ask["job"])
        start = time.time()
        answered = False
        shots = 0
        while time.time() - start < LIMIT:
            watch()
            ask_row = seen.get("Ask first") or ""
            if not answered and ask_row.startswith("needs-you"):
                page.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "question-needs-you.png"))
                item = page.locator("li.aw-run-item", has=page.locator(".aw-run-title", has_text="Ask first"))
                item.get_by_role("button", name="Answer").click()
                page.wait_for_timeout(2500)
                page.screenshot(path=str(look.OUT / "question-answer-pressed.png"))
                body = page.locator("body").inner_text()
                shown = "Should the gamma note be written in lower case?" in body
                d.check("ac-question: Answer shows the question", shown, body[:400].replace("\n", " / "))
                # Answer it where Answer led: pick Lower, then send.
                try:
                    page.get_by_text("Lower", exact=True).first.click()
                    for name in ("Submit", "Answer", "Send", "Submit answer", "Send answer"):
                        btn = page.get_by_role("button", name=name, exact=True)
                        if btn.count():
                            btn.last.click()
                            break
                    page.wait_for_timeout(1500)
                    page.screenshot(path=str(look.OUT / "question-answered.png"))
                except Exception as exc:  # noqa: BLE001 -- reported
                    d.check("question answered in the app", False, str(exc)[:300])
                # Back to Running, still the same page load.
                page.keyboard.press("Escape")
                answered = True
            flow_row = seen.get("Two notes") or ""
            if "1/2" in flow_row and "beta" in flow_row and shots < 1:
                page.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "live-next-task.png"))
                shots += 1
                break
            if "Write the alpha note" in flow_row and "building" in flow_row and shots == 0 and not (look.OUT / "live-building.png").exists():
                page.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "live-building.png"))
            # The flow needs firing to move past each step (its cron never fires).
            if int(time.time() - start) % 60 < 3 and not d.runs_busy(state["pid"]):
                for job in (flow["job"], ask["job"]):
                    d.fire(base, job)
            time.sleep(2)
        d.check("no reload: one navigation for the whole watch",
                page.evaluate("performance.getEntriesByType('navigation').length") == loads)
        d.check("no page errors", not errors, str(errors[:3]))
        page.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "live-end.png"))
        browser.close()
    bad = [n for n, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
