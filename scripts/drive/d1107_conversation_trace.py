"""Acceptance drive 'drive' for `a-trace-of-a-whole-conversation` (TWC), 2026-11-07.

Written, and recorded failing on today's code, before the build. It starts its own Hub from source on
:8113 with a fresh database (never :8000, and not the shared trial :8010), serving the bundle in
hub/hub/static/ui. One project, one agent bound to Haiku (`alpha`), then:

  setup  conversation A holds four real Haiku turns; one of them is back-dated (its run row and every
         span of its trace moved 9 hours earlier, in the drive's own database -- a gap cannot be made
         by waiting) so A has one long idle stretch; A is checkpointed and carried over by handoff to
         a successor B (no runs yet), then B takes one real turn;
  1      conversation B before its turn offers no 'Trace of this conversation'; A's menu offers it, and
         the Traces view narrowed to A offers 'open as one trace'; both open the same view   (FR-1)
  2      the turns are numbered in start order (the traces route returns them newest first), each bar
         starts after the previous one, 'from you' is shown, and one folded break labelled
         '<n>h <m>m later' separates turn 1 from turn 2 only                                 (FR-2, FR-3)
  3      totals agree with /traces/totals for the same conversation                          (FR-6)
  4      a turn unfolds to its spans on its own scale (with a line saying so), a span is
         selected and its detail shows; unfolding reads that turn's spans                     (FR-4)
  5      narrowing to turns 2..4 redraws turns, breaks and totals and the totals equal
         /traces/totals for the same since/until; a start choice with no turn says so and
         offers every turn again                                                              (FR-5)
  6      B's trace shows only B's turn, names A and 'Continued from' opens A's trace          (FR-7)
  7      screenshots of the view in dark and light.

Contract the build must honour (test ids; durations in seconds, money in micro-dollars):
  conversation menu item          role=menuitem name 'Trace of this conversation' (under conversation-more)
  Traces view                     `traces-open-conversation-trace` shown while narrowed to one conversation
  `conversation-trace`            the view (data-conversation-id)
  `conversation-turn`             one per turn, in start order (data-run-id, data-number); wraps the turn's
                                  row, its scale note and its span rows
  `conversation-turn-bar`         inside a turn: its bar on the shared axis (data-left and data-width, as
                                  0..1 fractions of the axis)
  `conversation-turn-from-you`    inside a turn the operator started
  `conversation-turn-toggle`      inside a turn: unfolds / folds it
  `conversation-turn-scale-note`  inside an unfolded turn: the line saying spans use the turn's own scale
  `conversation-span`             one per span of an unfolded turn (data-span-id, data-left: 0..1 of the turn)
  `conversation-break`            a folded stretch (data-label, e.g. '9h 0m later')
  `conversation-detail`           the selected turn's or span's detail, below the timeline
  `conversation-totals`           data-turns, data-of, data-working-seconds, data-cost-usd-micros,
                                  data-unpriced, data-failed, data-model-calls, data-tool-calls
  `conversation-trace-from` / `conversation-trace-to`     selects of turn numbers (values '1'..'N')
  `conversation-trace-since`      select: values 'any', '24h', '6h', '1h'
  `conversation-trace-show-all`   offered while narrowed
  `conversation-trace-empty`      the line saying no turn matches
  `conversation-trace-continued`  link to the earlier conversation's trace (data-conversation-id)

    py -3.11 scripts/drive/d1107_conversation_trace.py

Costs five Haiku turns and one checkpoint generation. Stops at the first failing check, so a red run
costs the setup turns only.
"""

import datetime as dt
import os
import pathlib
import re
import sys
import tempfile
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import d1011_project_steps as base  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

base.PORT = 8113
base.HUB = f"http://127.0.0.1:{base.PORT}"
base.TMP = base.REPO / "testbed" / "drive1107-conversation-trace" / base.STAMP
base.DB = base.TMP / "hub.db"
SHOTS = base.TMP / "shots"
HAIKU = base.HAIKU
ALPHA = "alpha"
BACKDATE_HOURS = 9
check, api, ro, poll = base.check, base.api, base.ro, base.poll


def turn(pid, agent, message, conversation=None):
    """One real turn; waits for it to end. Returns (run id, conversation id)."""
    body = {"agent": agent, "message": message}
    if conversation:
        body["conversation_id"] = conversation
    code, res = api("POST", f"/projects/{pid}/agent/trigger", body)
    check("a turn started", code < 300 and isinstance(res, dict) and bool(res.get("run_id")), f"{code} {res}")
    run_id = res["run_id"]
    live = ("running", "queued", "starting", "pending")
    poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0] not in live, 300)
    status = ro("select status from runs where id=?", (run_id,))[0][0]
    check(f"{agent}'s turn finished", status == "completed", f"{run_id} {status}")
    return run_id, ro("select conversation_id from runs where id=?", (run_id,))[0][0]


def shift_run(run_id, hours):
    """Move a run's row and every span of its trace `hours` earlier, in the drive's own database."""
    import sqlite3

    def moved(value):
        if value is None:
            return None
        sep = " " if " " in value else "T"
        return (dt.datetime.fromisoformat(value) - dt.timedelta(hours=hours)).isoformat(sep=sep)

    con = sqlite3.connect(base.DB.as_posix(), timeout=30)
    try:
        for table, cols, where in (
            ("runs", ("started_at", "ended_at"), "id"),
            ("trace_spans", ("start_time", "end_time", "trace_started_at"), "run_id"),
        ):
            rows = con.execute(f"select rowid, {', '.join(cols)} from {table} where {where}=?", (run_id,)).fetchall()
            for row in rows:
                sets = ", ".join(f"{c}=?" for c in cols)
                con.execute(f"update {table} set {sets} where rowid=?", (*[moved(v) for v in row[1:]], row[0]))
        con.commit()
    finally:
        con.close()


def runs_of(pid, conversation):
    """The conversation's runs oldest first, from the traces route (which returns them newest first)."""
    code, body = api("GET", f"/projects/{pid}/traces?conversation_id={conversation}&limit=200")
    check("the traces route answers", code == 200, f"{code} {str(body)[:200]}")
    return list(reversed(body["traces"]))


def num(page, testid, attr):
    return float(page.get_by_test_id(testid).get_attribute(attr))


def totals_agree(page, pid, conversation, since=None, until=None, label=""):
    params = {"conversation_id": conversation}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    query = urllib.parse.urlencode(params)  # '+00:00' must be encoded or the Hub reads a space
    code, want = api("GET", f"/projects/{pid}/traces/totals?{query}")
    check(f"{label}/traces/totals answers", code == 200, f"{code} {str(want)[:200]}")
    want = want["totals"]
    t = page.get_by_test_id("conversation-totals")
    got = {k: t.get_attribute(f"data-{k}") for k in
           ("turns", "working-seconds", "cost-usd-micros", "unpriced", "failed", "model-calls", "tool-calls")}
    check(f"{label}the turn count equals /traces/totals", int(got["turns"]) == want["count"], f"{got} {want['count']}")
    check(f"{label}the working time equals /traces/totals",
          abs(float(got["working-seconds"]) - want["duration_seconds"]) <= max(1.0, want["count"]), f"{got} {want['duration_seconds']}")
    micros = want["cost_usd_micros"]
    check(f"{label}the cost equals /traces/totals",
          (micros is None and got["cost-usd-micros"] in (None, "", "null")) or
          (micros is not None and got["cost-usd-micros"] not in (None, "", "null") and int(got["cost-usd-micros"]) == micros),
          f"{got['cost-usd-micros']} vs {micros}")
    check(f"{label}unpriced turns equal /traces/totals", int(got["unpriced"]) == want["unpriced"], f"{got['unpriced']} vs {want['unpriced']}")
    check(f"{label}failed turns equal /traces/totals", int(got["failed"]) == want["error_kinds"]["failed"] + want["error_kinds"]["stopped"],
          f"{got['failed']} vs {want['error_kinds']}")
    check(f"{label}model and tool calls equal /traces/totals",
          int(got["model-calls"]) == want["model_calls"] and int(got["tool-calls"]) == want["tool_calls"],
          f"{got} vs {want['model_calls']}/{want['tool_calls']}")


def empty_conversation(pid, conversation):
    """FR-1: a conversation with no run (the successor, before its first turn) offers no trace."""
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (base.KEY, base.HUB, pid))
    with sync_playwright() as p:
        chromium = p.chromium.launch()
        page = chromium.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.goto(f"{base.HUB}/?project={pid}&agent={ALPHA}&conversation={conversation}", wait_until="domcontentloaded")
        page.get_by_test_id("conversation-more").click()
        poll(lambda: page.get_by_role("menuitem").count() >= 1, 10)
        check("1 a conversation with no run offers no trace of itself",
              page.get_by_role("menuitem", name="Trace of this conversation").count() == 0, "menu offers it")
        page.goto(f"{base.HUB}/?project={pid}&tab=activity", wait_until="domcontentloaded")
        page.get_by_role("radio", name="Traces").click()
        page.get_by_test_id("traces-filter-conversation").fill(conversation)
        page.wait_for_timeout(2000)  # let the narrowed list settle; there is nothing to wait for
        check("1 the Traces view narrowed to it offers no 'open as one trace'",
              page.get_by_test_id("traces-open-conversation-trace").count() == 0, "button shown")
        chromium.close()


def browser(pid, conv_a, conv_b):
    runs = runs_of(pid, conv_a)
    check("setup: conversation A holds four runs", len(runs) == 4, str(len(runs)))
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (base.KEY, base.HUB, pid))
    SHOTS.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        chromium = p.chromium.launch()
        ctx = chromium.new_context(viewport={"width": 1400, "height": 900}, color_scheme="dark")
        ctx.add_init_script(seed)
        page = ctx.new_page()

        def conversation_page(conversation):
            page.goto(f"{base.HUB}/?project={pid}&agent={ALPHA}&conversation={conversation}", wait_until="domcontentloaded")
            page.get_by_test_id("conversation-more").click()

        # 1. opening
        item = page.get_by_role("menuitem", name="Trace of this conversation")
        conversation_page(conv_a)
        check("1 a conversation's menu offers 'Trace of this conversation'", poll(lambda: item.count() == 1, 15),
              "no such menu item")
        item.click()
        view = page.get_by_test_id("conversation-trace")
        check("1 the menu item opens the conversation trace", poll(lambda: view.count() == 1, 20))
        check("1 it is the conversation asked for", view.get_attribute("data-conversation-id") == conv_a)
        turns = page.get_by_test_id("conversation-turn")
        check("1 it shows the conversation's four turns", poll(lambda: turns.count() == 4, 20), f"{turns.count()}")
        page.goto(f"{base.HUB}/?project={pid}&tab=activity", wait_until="domcontentloaded")
        page.get_by_role("radio", name="Traces").click()
        page.get_by_test_id("traces-filter-conversation").fill(conv_a)
        openbtn = page.get_by_test_id("traces-open-conversation-trace")
        check("1 the Traces view narrowed to a conversation offers to open it as one trace",
              poll(lambda: openbtn.count() == 1, 15), "no button")
        openbtn.click()
        check("1 it opens the same view", poll(lambda: page.get_by_test_id("conversation-trace").count() == 1
                                               and page.get_by_test_id("conversation-trace").get_attribute("data-conversation-id") == conv_a
                                               and page.get_by_test_id("conversation-turn").count() == 4, 20))

        # 2. order, from you, the folded break
        ids = [r["run_id"] for r in runs]
        shown = [t.get_attribute("data-run-id") for t in turns.all()]
        check("2 turn 1 is the earliest run and the last turn the newest", shown == ids, f"{shown} vs {ids}")
        lefts = [float(t.get_by_test_id("conversation-turn-bar").get_attribute("data-left")) for t in turns.all()]
        check("2 each bar starts after the previous turn's start", all(a < b for a, b in zip(lefts, lefts[1:])), str(lefts))
        check("2 turns the operator started read 'from you'",
              page.get_by_test_id("conversation-turn-from-you").count() == 4)
        breaks = page.get_by_test_id("conversation-break")
        check("2 one folded break separates turn 1 from turn 2", breaks.count() == 1, f"{breaks.count()} breaks")
        label = breaks.first.get_attribute("data-label") or ""
        check("2 it is labelled with the length of the gap", re.fullmatch(r"(8|9)h \d{1,2}m later", label) is not None, label)
        bar1 = turns.nth(0).get_by_test_id("conversation-turn-bar").bounding_box()
        bar2 = turns.nth(1).get_by_test_id("conversation-turn-bar").bounding_box()
        brk = breaks.first.bounding_box()
        check("2 the break sits between turn 1 and turn 2",
              bool(bar1 and bar2 and brk)
              and brk["x"] + brk["width"] / 2 > bar1["x"] + bar1["width"] / 2
              and brk["x"] + brk["width"] / 2 < bar2["x"] + bar2["width"] / 2,
              f"{bar1} {brk} {bar2}")
        width = float(turns.first.get_by_test_id("conversation-turn-bar").get_attribute("data-width"))
        check("2 the first turn's bar is wider than 10% of the axis", width > 0.10, f"{width}")

        # 3. totals
        totals_agree(page, pid, conv_a, label="3 ")
        page.screenshot(path=str(SHOTS / "conversation-trace-dark.png"), full_page=True)

        # 4. unfold a turn and select a span
        turn2 = turns.nth(1)
        turn2.get_by_test_id("conversation-turn-toggle").click()
        spans = turn2.get_by_test_id("conversation-span")
        check("4 unfolding a turn lists its spans", poll(lambda: spans.count() >= 1, 15), f"{spans.count()}")
        check("4 a line says they use the turn's own scale",
              turn2.get_by_test_id("conversation-turn-scale-note").count() == 1)
        code, trace = api("GET", f"/projects/{pid}/traces/by-run/{runs[1]['run_id']}")
        check("4 the by-run route has the turn's spans", code == 200, f"{code}")
        recorded = len(trace.get("spans", []))
        # the root span is the turn's own row; the others are listed under it
        check("4 as many spans are listed as were recorded below the root", spans.count() == recorded - 1, f"{spans.count()} vs {recorded - 1}")
        lefts_in = [float(sp.get_attribute("data-left")) for sp in spans.all()]
        check("4 the spans are placed within the turn's own track", all(0 <= x <= 1 for x in lefts_in) and lefts_in == sorted(lefts_in), str(lefts_in))
        spans.nth(min(1, spans.count() - 1)).click()
        check("4 selecting a span shows its detail below", poll(lambda: page.get_by_test_id("conversation-detail").count() == 1, 10))

        # 5. narrowing
        page.get_by_test_id("conversation-trace-from").select_option("2")
        check("5 narrowing to turns 2-4 draws three turns", poll(lambda: turns.count() == 3, 10), f"{turns.count()}")
        check("5 the break before turn 1 is no longer drawn", page.get_by_test_id("conversation-break").count() == 0)
        check("5 the totals read '3 of 4'", page.get_by_test_id("conversation-totals").get_attribute("data-turns") == "3"
              and page.get_by_test_id("conversation-totals").get_attribute("data-of") == "4")
        narrowed = runs[1:]
        since = narrowed[0]["start_time"]
        last_start = dt.datetime.fromisoformat(narrowed[-1]["start_time"]) + dt.timedelta(seconds=1)
        totals_agree(page, pid, conv_a, since=since, until=last_start.isoformat(), label="5 ")  # encoded in totals_agree
        check("5 a narrowed view offers every turn again", page.get_by_test_id("conversation-trace-show-all").count() == 1)
        page.get_by_test_id("conversation-trace-show-all").click()
        check("5 showing every turn draws four again", poll(lambda: turns.count() == 4, 10))
        page.get_by_test_id("conversation-trace-since").select_option("1h")
        check("5 'last hour' drops the back-dated turn", poll(lambda: turns.count() == 3, 10), f"{turns.count()}")
        page.get_by_test_id("conversation-trace-show-all").click()
        page.get_by_test_id("conversation-trace-from").select_option("1")
        page.get_by_test_id("conversation-trace-to").select_option("1")
        page.get_by_test_id("conversation-trace-since").select_option("1h")
        check("5 a narrowing that leaves no turn says so", poll(lambda: page.get_by_test_id("conversation-trace-empty").count() == 1, 10))
        page.get_by_test_id("conversation-trace-show-all").click()
        check("5 and every turn can be shown again", poll(lambda: turns.count() == 4, 10))

        # light screenshot of the same view
        light = chromium.new_context(viewport={"width": 1400, "height": 900}, color_scheme="light")
        light.add_init_script(seed)
        lp = light.new_page()
        lp.goto(f"{base.HUB}/?project={pid}&tab=activity", wait_until="domcontentloaded")
        lp.get_by_role("radio", name="Traces").click()
        lp.get_by_test_id("traces-filter-conversation").fill(conv_a)
        lp.get_by_test_id("traces-open-conversation-trace").click()
        poll(lambda: lp.get_by_test_id("conversation-turn").count() == 4, 20)
        lp.screenshot(path=str(SHOTS / "conversation-trace-light.png"), full_page=True)
        light.close()

        # 6. carried over
        page.goto(f"{base.HUB}/?project={pid}&agent={ALPHA}&conversation={conv_b}", wait_until="domcontentloaded")
        page.get_by_test_id("conversation-more").click()
        page.get_by_role("menuitem", name="Trace of this conversation").click()
        check("6 the successor's trace shows only its own turn", poll(lambda: turns.count() == 1, 20), f"{turns.count()}")
        link = page.get_by_test_id("conversation-trace-continued")
        check("6 it names the conversation it continued", link.count() == 1 and
              link.get_attribute("data-conversation-id") == conv_a)
        link.click()
        check("6 following it opens the earlier conversation's trace",
              poll(lambda: page.get_by_test_id("conversation-trace").get_attribute("data-conversation-id") == conv_a
                   and turns.count() == 4, 20))
        chromium.close()


def main():
    hub = base.start_hub()
    try:
        base.TMP.mkdir(parents=True, exist_ok=True)
        root = pathlib.Path(tempfile.mkdtemp(prefix="aw-convtrace-drive-")) / "proj"
        root.mkdir(parents=True)
        (root / "README.md").write_text("# d1107\n\nChecked by the conversation-trace drive.\n", encoding="utf-8")
        base.git(root, "init", "-q", "-b", "master")
        base.git(root, "add", "-A")
        base.git(root, "commit", "-q", "-m", "init")
        code, project = api("POST", "/projects/open", {"path": str(root)})
        check("the project opened", code < 300, f"{code} {project}")
        pid = project["id"]
        code, runner = api("POST", f"/projects/{pid}/runners", {"name": f"haiku {base.STAMP}", "cli": "claude", "model": HAIKU})
        check("a Haiku runner", code < 300, f"{code} {runner}")
        code, res = api("POST", f"/projects/{pid}/agents", {"name": ALPHA, "runner_id": runner["id"]})
        check("agent alpha", code < 300, f"{code} {res}")
        code, settings = api("GET", f"/projects/{pid}/settings")
        settings.update(checkpoint_mode="off", checkpoint_runner_id=runner["id"], checkpoint_model=HAIKU,
                        checkpoint_auto_continue=False)
        code, _ = api("PUT", f"/projects/{pid}/settings", settings)
        check("checkpoint runner set", code == 200, str(code))

        first, conv_a = turn(pid, ALPHA, "Read README.md and reply with its first line, nothing else.")
        for message in ("Now say in one sentence what that file is for.", "Reply with the word 'two'.", "Reply with the word 'three'."):
            turn(pid, ALPHA, message, conv_a)
        shift_run(first, BACKDATE_HOURS)
        code, cp = api("POST", f"/projects/{pid}/conversations/{conv_a}/checkpoint", timeout=300)
        check("the checkpoint was taken", code == 201 and cp.get("status") == "ready", f"{code} {str(cp)[:200]}")
        code, cut = api("POST", f"/projects/{pid}/checkpoints/{cp['id']}/cutover")
        check("the conversation was carried over", code == 200, f"{code} {cut}")
        conv_b = cut["successor_conversation_id"]
        # The successor has no run yet: look at it empty first, then it takes its turn.
        empty_conversation(pid, conv_b)
        turn(pid, ALPHA, "Reply with the word 'carried'.", conv_b)
        browser(pid, conv_a, conv_b)
    except base.Stop:
        pass
    finally:
        base.stop_hub(hub)
    failed = [n for n, ok in base.results if not ok]
    print("FAILED: " + ", ".join(failed) if failed else "ALL PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
