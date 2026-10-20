"""Traces sweep 2026-10-20, UI: Environment -> Settings -> Traces (kinds, open a trace, span detail,
download, clear), a conversation turn's trace button, the task story's, and the Activity feed's gap
notice while the page's main thread is held and the Hub floods its stream. Real browser, served
bundle on the scratch Hub (hub-up 8141).

  py -3.11 scripts/drive/s1020_traces_ui.py [all|gap|clear]
"""

import json
import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.argv = sys.argv[:1] + ["none"] + sys.argv[1:]
import s1020_traces as T  # noqa: E402
from s1020_traces import S, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]
WHAT = sys.argv[2] if len(sys.argv) > 2 else "all"


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def conv_of(run):
    return T.ro("select conversation_id from runs where id=?", (run,))[0]["conversation_id"]


with Judge("s1020-traces", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT in ("all",):
        page = j.page(P, mode="light", query="tab=environment&section=settings")
        page.wait_for_timeout(5000)
        print("COUNTS:", txt(page.get_by_test_id("trace-counts")))
        print("EXPORT STATUS:", txt(page.get_by_test_id("trace-export-status")))
        recent = page.get_by_test_id("recent-traces")
        recent.scroll_into_view_if_needed()
        for kind in ("invoke_agent", "chat", "aw.request", "aw.work", "aw.event", "all"):
            page.get_by_test_id(f"trace-kind-{kind}").click()
            page.wait_for_timeout(1200)
            print(f"KIND {kind}:", txt(recent)[:600])
        page.get_by_test_id("trace-kind-invoke_agent").click()
        page.wait_for_timeout(1200)
        j.shot(page, "01_traces_section", locator=recent)
        # Open the permission run's trace from the list.
        st, listed = T.api("GET", "~/traces?run_id=" + S["RUN2"])
        tid = listed["traces"][0]["trace_id"]
        page.get_by_test_id(f"recent-trace-{tid}").click()
        page.wait_for_timeout(2500)
        view = page.get_by_test_id("trace-view")
        print("TRACE VIEW:", txt(view)[:1500])
        rows = page.locator("[data-testid^='trace-row-']")
        print("ROWS:", [(rows.nth(i).get_attribute("data-status"), " ".join((rows.nth(i).text_content() or "").split())[:60]) for i in range(rows.count())])
        j.shot(page, "02_trace_drawer")
        perm = page.locator("[data-testid^='trace-row-']", has_text="permission_wait")
        if perm.count():
            perm.first.click()
            page.wait_for_timeout(800)
            detail = txt(page.get_by_test_id("trace-span-detail"))
            print("PERM SPAN DETAIL:", detail[:800])
            print("token on screen:", "Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4" in detail)
            j.shot(page, "03_permission_span")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        print("drawer after Escape:", page.get_by_test_id("trace-view").count())
        # Download.
        with page.expect_download(timeout=20000) as dl:
            page.get_by_role("button", name="Download OTLP JSON").click()
        path = dl.value.path()
        body = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        spans = body["resourceSpans"][0]["scopeSpans"][0]["spans"]
        logs = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        print("DOWNLOAD:", dl.value.suggested_filename, len(spans), "spans", len(logs), "logs")
        print("token in download:", "Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4" in pathlib.Path(path).read_text(encoding="utf-8"))
        print("errors so far:", j.errors[:5])

        # The conversation turn's trace button (the stopped run).
        for label, run in (("stopped", S["RUN3"]), ("perm", S["RUN2"])):
            page = j.page(P, mode="light", query=f"agent=tracer&conversation={conv_of(run)}")
            page.wait_for_timeout(5000)
            btn = page.get_by_test_id(f"turn-trace-{run}")
            print(label, "turn trace button:", btn.count())
            if btn.count():
                btn.first.click()
                page.wait_for_timeout(2500)
                print(label, "TRACE VIEW:", txt(page.get_by_test_id("trace-view"))[:700])
                j.shot(page, f"04_turn_trace_{label}")
                page.keyboard.press("Escape")
            ends = page.locator("text=/stopped|Stopped/")
            print(label, "turn-end label:", [txt(ends.nth(i))[:120] for i in range(min(ends.count(), 4))])

        # The task story's trace button.
        page = j.page(P, mode="light", query="tab=tasks")
        page.wait_for_timeout(4000)
        page.get_by_text("Guard div against zero").first.click()
        page.wait_for_timeout(2500)
        sbtn = page.get_by_test_id(f"story-run-trace-{S['RUN4']}")
        print("story trace button:", sbtn.count())
        if sbtn.count():
            sbtn.first.scroll_into_view_if_needed()
            sbtn.first.click()
            page.wait_for_timeout(2500)
            print("STORY TRACE VIEW:", txt(page.get_by_test_id("trace-view"))[:700])
            j.shot(page, "05_story_trace")
        print("errors:", j.errors[:10])

    if WHAT in ("gap",):
        page = j.page(P, mode="light", query="tab=activity")
        page.wait_for_timeout(5000)
        feed_btn = page.get_by_role("button", name="Activity")
        print("activity view buttons:", feed_btn.count())
        page.get_by_test_id("activity-subview-activity").click()
        page.wait_for_timeout(2000)
        print("feed before:", " ".join((page.locator("main").first.text_content() or "").split())[:300])

        def flood():
            for i in range(900):
                e2e.request("POST", f"/projects/{P}/tasks", {"title": f"gap {i} " + "x" * 200, "description": "y" * 4000})

        t = threading.Thread(target=flood)
        t.start()
        # Hold the page's main thread while the stream fills.
        page.evaluate("() => { const end = Date.now() + 45000; while (Date.now() < end) {} }")
        t.join()
        page.wait_for_timeout(8000)
        body = " ".join((page.locator("body").text_content() or "").split())
        i = body.find("fell behind")
        print("GAP NOTICE:", body[max(0, i - 100): i + 250] if i >= 0 else "<absent>")
        j.shot(page, "06_gap_notice")
        feed = " ".join((page.locator("body").text_content() or "").split())
        print("P feed shows 'gap 899'?:", "gap 899" in feed, "| 'gap 0 '?:", "gap 0 " in feed)
        # F419: the other project's Activity and Overview must not show P's flood.
        for q in ("tab=activity", ""):
            p2 = j.page(S["P2"], mode="light", query=q)
            p2.wait_for_timeout(5000)
            body2 = " ".join((p2.locator("body").text_content() or "").split())
            print(f"P2 [{q or 'overview'}] shows P's flood?:", "gap 1" in body2, "| fell behind?:", "fell behind" in body2)
            j.shot(p2, f"06b_p2_{q or 'overview'}")

    if WHAT in ("clear",):
        page = j.page(P, mode="light", query="tab=environment&section=settings")
        page.wait_for_timeout(5000)
        print("COUNTS before:", txt(page.get_by_test_id("trace-counts")))
        page.get_by_role("button", name="Clear traces…").click()
        page.wait_for_timeout(800)
        dlg = page.get_by_role("dialog")
        print("DIALOG:", txt(dlg))
        print("focused:", page.evaluate("() => document.activeElement && document.activeElement.textContent"))
        dlg.get_by_role("button", name="Clear traces").click()
        page.wait_for_timeout(2500)
        print("RESULT:", txt(page.locator("[role='status']", has_text="Cleared")))
        print("COUNTS after:", txt(page.get_by_test_id("trace-counts")))
        print("RECENT after:", txt(page.get_by_test_id("recent-traces"))[:400])
        j.shot(page, "07_cleared")
        st, tr = T.api("GET", f"~/traces/by-run/{S['RUN2']}")
        print("by-run after clear:", st)
        page = j.page(P, mode="light", query=f"agent=tracer&conversation={conv_of(S['RUN2'])}")
        page.wait_for_timeout(5000)
        btn = page.get_by_test_id(f"turn-trace-{S['RUN2']}")
        print("turn trace button after clear:", btn.count())
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(2000)
            dr = page.get_by_role("dialog")
            print("DRAWER after clear:", txt(dr)[:400])
            j.shot(page, "08_turn_trace_after_clear")
        print("errors:", j.errors[:10])
