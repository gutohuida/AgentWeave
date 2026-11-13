"""Acceptance drive for the Running tab (SPSRT-3), part 4: a question answered, and the next task taken.

Adds an "Ask again" flow build to the drive's project whose one task tells Asker to call ask_user
(blocking) first. Page A shows Running at the narrowest width and is never reloaded after the watch
starts. The drive fires the flow; when "Ask again" reads Needs you, page A and a light-mode page are
screenshotted, then a second page (B) opens Running, presses the row's Answer, checks the question is
shown, picks "Lower" and presses Submit answer. Page A must then drop the row out of Needs you by
itself. Meanwhile it keeps the "Two notes" flow firing and waits for its worker line and progress to
move to the second task (FR-9 ac-live), on page A, without a reload.

    py -3.11 scripts/drive/d1112_running_question.py
"""

import json
import sys
import time
import urllib.parse

import d1029_build_plan_in_spec as d
import d1112_running_look as look
import d1112_running_setup as setup
from playwright.sync_api import sync_playwright

LIMIT = 25 * 60
import os
SUFFIX = os.environ.get("ASK_SUFFIX") or time.strftime("%H%M")
PATH = f"spec/changes/ask-again-{SUFFIX}/spec.json"
TITLE = f"Ask again {SUFFIX}"
QUESTION = "Should the iota note be written in lower case?"


def make_build(state):
    base = state["base"]
    if os.environ.get("ASK_SUFFIX"):  # reuse a build made by an earlier run
        loop = d.ro("select t.loop_id from tasks t join spec_documents s on t.spec_document_id=s.id "
                    "where s.project_id=? and s.path=?", (state["pid"], PATH))[0][0]
        return d.ro("select job_id from loops where id=?", (loop,))[0][0]
    tasks = [setup.note("iota", "Ask, then write the iota note", "Asker", first=(
        f"Before anything else, call the ask_user tool once, blocking, with the single question \"{QUESTION}\" "
        "(header \"Case\", options \"Lower\" and \"Upper\"), and wait for the answer. Then: "))]
    quoted = urllib.parse.quote(PATH)
    code, out = d.api("POST", f"{base}/project/documents", {"title": TITLE, "kind": "change-spec", "path": PATH})
    d.check("ask-again: created", code == 201, f"{code}", fatal=True)
    code, out = d.api("PUT", f"{base}/project/documents/{PATH}/content", {"document": setup.doc(TITLE, tasks)})
    d.check("ask-again: saved", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    _, read = d.api("GET", f"{base}/project/spec?path={quoted}")
    code, out = d.api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                      {"reason": "drive", "approve_anyway": True, "content_version": read.get("content_version")})
    d.check("ask-again: approved", code == 200, f"{code}", fatal=True)
    code, out = d.api("POST", f"{base}/project/documents/build?path={quoted}", setup.BUILDS["question"])
    d.check("ask-again: built", code == 200, f"{code} {str(out)[:300]}", fatal=True)
    loop = d.ro("select t.loop_id from tasks t join spec_documents s on t.spec_document_id=s.id "
                "where s.project_id=? and s.path=?", (state["pid"], PATH))[0][0]
    return d.ro("select job_id from loops where id=?", (loop,))[0][0]


def stamp(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def main():
    state = json.loads((look.OUT / "state.json").read_text(encoding="utf-8"))
    base, pid = state["base"], state["pid"]
    flow_job = state["builds"]["flow"]["job"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        a = browser.new_page(viewport={"width": 1280, "height": 900})
        errors = []
        a.on("pageerror", lambda e: errors.append(str(e)))
        box = look.open_narrow(a, state, "dark")
        stamp(f"page A: Running at {box and round(box['width'])}px")
        loads = a.evaluate("performance.getEntriesByType('navigation').length")
        ask_job = make_build(state)
        seen = {}

        def watch():
            for title in ("Two notes", TITLE):
                text = look_row(a, title)
                if text != seen.get(title):
                    seen[title] = text
                    stamp(f"{title}: {text}")

        watch()
        if not os.environ.get("ASK_SUFFIX"):
            d.fire(base, ask_job)
        start = time.time()
        asked_at = answered_at = None
        left_needs_you = False
        last_fire = time.time()
        while time.time() - start < LIMIT:
            watch()
            row = seen.get(TITLE) or ""
            if asked_at is None and row.startswith("needs-you"):
                asked_at = time.time()
                a.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "narrow-question-dark.png"))
                light = browser.new_page(viewport={"width": 1280, "height": 900})
                look.open_narrow(light, state, "light")
                light.wait_for_timeout(1500)
                light.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "narrow-question-light.png"))
                light.close()
                b = browser.new_page(viewport={"width": 1280, "height": 900})
                look.open_narrow(b, state, "dark")
                item = b.locator("li.aw-run-item", has=b.locator(".aw-run-title", has_text=TITLE))
                d.check("ac-question: the row offers Answer", item.get_by_role("button", name="Answer").count() == 1,
                        item.inner_text().replace("\n", " / "))
                item.get_by_role("button", name="Answer").click()
                b.get_by_text(QUESTION).first.wait_for(timeout=15000)
                d.check("ac-question: Answer shows that question", True, b.url)
                forms = b.locator("article.question-row:not(.is-stale)").filter(has_text=QUESTION)
                stamp(f"{forms.count()} open copies of the question shown")
                for i in range(forms.count()):
                    form = b.locator("article.question-row:not(.is-stale)").filter(has_text=QUESTION).first
                    form.get_by_text("Lower", exact=True).first.click()
                    form.get_by_role("button", name="Submit answer to Asker").click()
                    b.wait_for_timeout(1500)
                b.wait_for_timeout(1500)
                b.screenshot(path=str(look.OUT / "question-submitted.png"))
                answered_at = time.time()
                q = d.ro("select answered, answer from questions where project_id=? and question=?", (pid, QUESTION))
                d.check("ac-question: the question is answered where Answer led", q and all(r[0] == 1 for r in q), str(q))
                b.close()
            if answered_at and not left_needs_you and not row.startswith("needs-you"):
                left_needs_you = True
                d.check("FR-9: the answered build leaves Needs you on page A without a reload",
                        a.evaluate("performance.getEntriesByType('navigation').length") == loads,
                        f"{time.time() - answered_at:.1f}s after the answer: {row}")
            flow_row = seen.get("Two notes") or ""
            if "1/2" in flow_row and "beta" in flow_row:
                a.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "live-next-task.png"))
                d.check("ac-live: Two notes moved to its next task (worker and progress) on page A without a reload",
                        a.evaluate("performance.getEntriesByType('navigation').length") == loads, flow_row)
                if left_needs_you or answered_at is None:
                    break
            if time.time() - last_fire > 45 and not d.runs_busy(pid):
                d.fire(base, flow_job)
                d.fire(base, ask_job)
                last_fire = time.time()
            time.sleep(2)
        d.check("the question was asked within the limit", asked_at is not None)
        d.check("no page errors on page A", not errors, str(errors[:3]))
        a.get_by_test_id("running-tab").screenshot(path=str(look.OUT / "question-end.png"))
        browser.close()
    bad = [n for n, ok in d.results if not ok]
    print(f"\n{len(d.results) - len(bad)} passed, {len(bad)} failed")
    sys.exit(1 if bad else 0)


def look_row(page, title):
    return page.evaluate(
        "(t) => { for (const li of document.querySelectorAll('[data-testid=running-tab] li.aw-run-item')) {"
        " if (li.querySelector('.aw-run-title')?.textContent === t) return li.dataset.phase + ' | ' + li.innerText.replace(/\\n/g, ' / '); }"
        " return null }", title)


if __name__ == "__main__":
    main()
