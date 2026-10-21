"""Traces sweep 2026-10-21, UI (real Chromium, served bundle, scratch Hub hub-up 8156).

  all   Settings -> Traces list: the stopped run's badge (F792); the stopped turn's trace drawer
        header; the failed Copilot turn's conversation after three timed-out attempts (F789)
  gap   the Activity feed's stream_gap notice, with the page's network throttled over CDP so the
        Hub's stream really backs up (10-20 could not reach it: Chromium buffered the burst)

  py -3.11 scripts/drive/s1021_tr_traces_ui.py [all|gap]
"""

import pathlib
import sys
import threading

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "all"
import s1021_tr_traces as T  # noqa: E402
from s1021_tr_traces import S, e2e  # noqa: E402
from uiharness import Judge  # noqa: E402

P = S["P"]


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def conv_of(run):
    return T.ro("select conversation_id from runs where id=?", (run,))[0]["conversation_id"]


with Judge("s1021-traces", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "all":
        page = j.page(P, mode="light", query="tab=environment&section=settings")
        page.wait_for_timeout(5000)
        recent = page.get_by_test_id("recent-traces")
        recent.scroll_into_view_if_needed()
        page.get_by_test_id("trace-kind-invoke_agent").click()
        page.wait_for_timeout(1500)
        print("INVOKE_AGENT LIST:", txt(recent)[:900])
        st, listed = T.api("GET", "~/traces?run_id=" + S["RUN_STOP"])
        tid = listed["traces"][0]["trace_id"]
        row = page.get_by_test_id(f"recent-trace-{tid}")
        print("STOPPED ROW:", txt(row))
        st, listed = T.api("GET", "~/traces?run_id=" + S["RUN_COP"])
        ctid = listed["traces"][0]["trace_id"]
        print("COPILOT ROW:", txt(page.get_by_test_id(f"recent-trace-{ctid}")))
        j.shot(page, "01_traces_list", locator=recent)
        row.click()
        page.wait_for_timeout(2500)
        view = page.get_by_test_id("trace-view")
        print("STOPPED DRAWER:", txt(view)[:700])
        j.shot(page, "02_stopped_drawer")
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)

        page = j.page(P, mode="light", query=f"agent=tracer&conversation={conv_of(S['RUN_STOP'])}")
        page.wait_for_timeout(5000)
        btn = page.get_by_test_id(f"turn-trace-{S['RUN_STOP']}")
        print("turn trace button:", btn.count())
        if btn.count():
            btn.first.click()
            page.wait_for_timeout(2500)
            print("TURN DRAWER (stopped):", txt(page.get_by_test_id("trace-view"))[:500])
            j.shot(page, "03_turn_drawer_stopped")
            page.keyboard.press("Escape")

        page = j.page(P, mode="light", query=f"agent=slowcop&conversation={S['CONV_COP']}")
        page.wait_for_timeout(5000)
        main = page.locator("main").first
        print("COPILOT CONVERSATION:", " ".join((main.text_content() or "").split())[:1500])
        j.shot(page, "04_copilot_conversation")
        cbtn = page.locator("[data-testid^='turn-trace-']")
        print("copilot turn trace buttons:", cbtn.count())
        if cbtn.count():
            cbtn.last.click()
            page.wait_for_timeout(2500)
            print("COPILOT DRAWER:", txt(page.get_by_test_id("trace-view"))[:500])
            j.shot(page, "05_copilot_drawer")
        print("errors:", j.errors[:10])

    if WHAT == "gap":
        page = j.page(P, mode="light", query="tab=activity")
        page.wait_for_timeout(5000)
        page.locator("[aria-label='Activity view']").get_by_text("Activity", exact=True).click()
        page.wait_for_timeout(2000)
        cdp = page.context.new_cdp_session(page)
        cdp.send("Network.enable")
        # Throttling binds only connections opened after it: drop the stream, let it reconnect slow.
        cdp.send(
            "Network.emulateNetworkConditions",
            {"offline": True, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1},
        )
        page.wait_for_timeout(4000)
        cdp.send(
            "Network.emulateNetworkConditions",
            {"offline": False, "latency": 200, "downloadThroughput": 1500, "uploadThroughput": -1},
        )
        page.wait_for_timeout(8000)

        def flood():
            for i in range(900):
                e2e.request("POST", f"/projects/{P}/tasks", {"title": f"gap {i} " + "x" * 200, "description": "y" * 4000})

        t = threading.Thread(target=flood)
        t.start()
        page.evaluate("() => { const end = Date.now() + 45000; while (Date.now() < end) {} }")
        t.join()
        cdp.send(
            "Network.emulateNetworkConditions",
            {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1},
        )
        hits = None
        for _ in range(24):
            page.wait_for_timeout(5000)
            body = " ".join((page.locator("body").text_content() or "").split())
            i = body.find("fell behind")
            if i >= 0:
                hits = body[max(0, i - 100): i + 250]
                break
        print("GAP NOTICE:", hits or "<absent>")
        gap_events = T.ro("select count(*) n from event_logs where event_type='stream_gap'")
        print("stream_gap rows in event_logs (not expected: it is per-connection):", gap_events)
        j.shot(page, "06_gap_notice")
        print("errors:", j.errors[:10])
