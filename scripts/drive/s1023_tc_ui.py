"""2026-10-23 Traces row, UI: real Chromium on the served bundle (scratch Hub :8120, profile tc1023).

  conv     the conversation's turn trace buttons: each drawer's header, waterfall rows, a tool span's detail
  story    the task drawer's story: each run's trace button, its drawer, and the story's spend line
  section  Project settings -> General -> Traces: counts, kind filter, the Work trace carrying the
           warning, download, clear (dialog, confirm, status line), clear again
  fail     breaker's conversation (three failed attempts): trace buttons and the not-delivered entry

  py -3.11 scripts/drive/s1023_tc_ui.py <what>
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
WHAT = sys.argv[1] if len(sys.argv) > 1 else "conv"
from s1023_tc_lib import GH, HALF1, KEY, P, S, e2e, req  # noqa: E402
from uiharness import Judge  # noqa: E402


def txt(loc):
    return " ".join((loc.first.text_content() or "").split()) if loc.count() else "<absent>"


def secrets_on(page):
    body = page.locator("body").text_content() or ""
    return [n for n, v in (("KEY", KEY), ("HALF1", HALF1), ("GH", GH), ("KEYbody", KEY[13:])) if v in body]


def read_drawer(j, page, label):
    view = page.get_by_test_id("trace-view")
    view.wait_for(timeout=15000)
    page.wait_for_timeout(800)
    header = txt(view.locator("> div").first)
    print(f"[{label}] header: {header}")
    rows = view.locator("[data-testid^='trace-row-']")
    print(f"[{label}] waterfall rows: {rows.count()}")
    for i in range(rows.count()):
        print(f"   row {i}: {txt(rows.nth(i))}")
    print(f"[{label}] secrets on page: {secrets_on(page)}")
    j.shot(page, f"{label}_drawer")
    return view, rows


def close(page):
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)


with Judge("s1023-traces", hub=e2e.hub(), key=e2e.key()) as j:
    if WHAT == "conv":
        page = j.page(P, mode="light", query=f"agent=tracer&conversation={S['CONV']}")
        page.wait_for_timeout(7000)
        buttons = page.locator("[data-testid^='turn-trace-']")
        ids = [buttons.nth(i).get_attribute("data-testid") for i in range(buttons.count())]
        print("turn trace buttons:", ids)
        for rid, label in ((S["RUN_OK"], "ok"), (S["RUN_STOP"], "stopped")):
            btn = page.get_by_test_id(f"turn-trace-{rid}")
            if not btn.count():
                print(f"[{label}] NO trace button for {rid}")
                continue
            btn.first.scroll_into_view_if_needed()
            btn.first.click()
            view, rows = read_drawer(j, page, label)
            for i in range(rows.count()):
                if "PowerShell" in txt(rows.nth(i)) and "tool" in txt(rows.nth(i)):
                    rows.nth(i).click()
                    page.wait_for_timeout(500)
                    print(f"[{label}] tool span detail: {txt(page.get_by_test_id('trace-span-detail'))[:1500]}")
                    break
            # the root span's detail (usage)
            rows.nth(0).click()
            page.wait_for_timeout(400)
            print(f"[{label}] root detail: {txt(page.get_by_test_id('trace-span-detail'))[:1200]}")
            j.shot(page, f"{label}_root_detail")
            close(page)
            print(f"[{label}] drawer open after Escape: {page.get_by_test_id('trace-view').count()}")
    elif WHAT == "story":
        page = j.page(P, mode="light", query="tab=tasks")
        page.wait_for_timeout(5000)
        page.get_by_text("Echo the fixtures").first.click()
        page.wait_for_timeout(4000)
        buttons = page.locator("[data-testid^='story-run-trace-']")
        ids = [buttons.nth(i).get_attribute("data-testid") for i in range(buttons.count())]
        print("story trace buttons:", ids)
        story = page.locator(".aw-tl-meta").all()
        print("story run lines:")
        for b in ids:
            item = page.get_by_test_id(b).locator("xpath=ancestor::*[contains(@class,'aw-tl')][1]")
            print("   ", b, "|", txt(item)[:300])
        j.shot(page, "story", full_page=True)
        st, story_api = req("GET", f"~/tasks/{S['TASK']}/story")
        runs = [e for e in story_api.get("events", []) if e.get("kind") == "run"]
        print("story API runs:", [(e["id"], e.get("status"), e.get("cost_usd")) for e in runs])
        if ids:
            page.get_by_test_id(ids[-1]).first.click()
            read_drawer(j, page, "story_last")
            close(page)
    elif WHAT == "fail":
        page = j.page(P, mode="light", query="agent=breaker")
        page.wait_for_timeout(7000)
        print("main text:", txt(page.locator("main"))[:1500])
        buttons = page.locator("[data-testid^='turn-trace-']")
        print("turn trace buttons:", [buttons.nth(i).get_attribute("data-testid") for i in range(buttons.count())])
        j.shot(page, "fail_conv", full_page=True)
        if buttons.count():
            buttons.last.click()
            read_drawer(j, page, "failed")
            close(page)
    elif WHAT == "section":
        page = j.page(P, mode="light", query="tab=environment&section=settings")
        page.wait_for_timeout(6000)
        counts = page.get_by_test_id("trace-counts")
        counts.scroll_into_view_if_needed()
        print("counts:", txt(counts))
        for op in ("invoke_agent", "chat", "aw.request", "aw.work", "aw.event", "all"):
            page.get_by_test_id(f"trace-kind-{op}").click()
            page.wait_for_timeout(1500)
            rows = page.get_by_test_id("recent-traces").locator("li")
            empty = txt(page.locator("[aria-label='Kind of trace']").locator("xpath=.."))[:200]
            print(f"kind {op}: {rows.count()} rows; first: {txt(rows) if rows.count() else empty}")
            if op == "invoke_agent":
                for i in range(rows.count()):
                    print("    ", txt(rows.nth(i)))
            if op == "aw.work":
                j.shot(page, "section_work")
                # open the inbound_queue trace that carries the warning (by its trace id)
                warned = [r for r in json.loads(json.dumps(req("GET", "~/traces?limit=50&operation=aw.work")[1]["traces"]))
                          if r["name"] == "inbound_queue"]
                for w in warned:
                    btn = page.get_by_test_id(f"recent-trace-{w['trace_id']}")
                    if btn.count():
                        _, wst = req("GET", f"~/traces/{w['trace_id']}")
                        has_log = any(e["name"] == "log" for s in wst["spans"] for e in s["events"])
                        if not has_log:
                            continue
                        btn.click()
                        view, wrows = read_drawer(j, page, "warned_work")
                        print("[warned_work] detail:", txt(page.get_by_test_id("trace-span-detail"))[:1500])
                        print("[warned_work] 'could not remove' on page:", page.get_by_text("could not remove", exact=False).count())
                        j.shot(page, "warned_work_detail")
                        close(page)
                        break
                else:
                    print("no warned inbound_queue trace on the first page of the Work list")
        # Download
        with page.expect_download(timeout=30000) as dl:
            page.get_by_role("button", name="Download OTLP JSON").click()
        path = dl.value.path()
        data = pathlib.Path(path).read_bytes()
        print("download:", dl.value.suggested_filename, len(data), "bytes; secrets:",
              [n for n, v in (("KEY", KEY), ("HALF1", HALF1), ("GH", GH)) if v.encode() in data])
        # Clear
        page.get_by_role("button", name="Clear traces…").click()
        page.wait_for_timeout(800)
        dialog = page.get_by_role("alertdialog").or_(page.get_by_role("dialog"))
        print("clear dialog:", txt(dialog))
        j.shot(page, "clear_dialog")
        _, before = req("GET", "~/traces/settings")
        dialog.get_by_role("button", name="Clear traces").click()
        page.wait_for_timeout(2500)
        _, after = req("GET", "~/traces/settings")
        print("before:", before["trace_count"], before["span_count"], "after:", after["trace_count"], after["span_count"])
        print("status line:", txt(page.get_by_role("status")))
        print("counts after:", txt(page.get_by_test_id("trace-counts")))
        j.shot(page, "after_clear")
        page.get_by_role("button", name="Clear traces…").click()
        page.wait_for_timeout(800)
        dialog = page.get_by_role("alertdialog").or_(page.get_by_role("dialog"))
        print("second clear dialog:", txt(dialog))
        dialog.get_by_role("button", name="Clear traces").click()
        page.wait_for_timeout(2500)
        print("second status line:", txt(page.get_by_role("status")))
        print("counts after second:", txt(page.get_by_test_id("trace-counts")))
        j.shot(page, "after_clear2")
