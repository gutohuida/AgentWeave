"""Acceptance drive 'drive-traces-end-to-end' for `a-traces-view-with-filters-grouping-and-stats`.

Starts its own Hub from source on :8112 with a fresh database (never :8000, and not the shared
trial :8010, so the drive owns its data), serving the bundle in hub/hub/static/ui. One project, two
agents bound to Haiku (`alpha`, `beta`), then, in a real browser:

  1. Activity has a Traces view (`Activity view` segment named Traces) -- FAILS today, and the
     drive stops here, so a red run spends no agent turn;
  2. real turns: alpha works a task, beta answers once, and one run is stopped part-way (the
     error that can be made on demand; a stopped run counts as an error, FR-6);
  3. the view first lists runs only (every row [data-testid=trace-row] is a run), filtering to alpha
     over the last hour leaves only alpha's runs, grouping by agent shows for alpha the run count,
     total cost equal to the sum of those runs' recorded cost (turn_usage, read from the DB), total and
     average duration, and the errors count -- and the three headline stats precede any other;
  4. opening a listed row shows that run's trace; the conversation's own "Latest trace" control and
     the task's run row each open the trace of the run the Hub says is latest / the task's run.

Contract the build must honour (test ids): `traces-view`, `traces-filter-agent`, `traces-filter-range`,
`traces-group-by` (select), `trace-row` (data-run-id), `trace-group` (data-group), within a group
`stat-cost`, `stat-duration`, `stat-avg-duration`, `stat-errors` in that DOM order, plus `stat-count` (data-value; durations are
seconds in data-value) and before any
other `[data-testid^=stat-]`; `trace-detail` (data-run-id); `conversation-latest-trace`;
`task-run-trace`.

    py -3.11 scripts/drive/d1102_traces_end_to_end.py
"""

import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import d1011_project_steps as d  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

d.PORT = 8112
d.HUB = f"http://127.0.0.1:{d.PORT}"
d.TMP = d.REPO / "testbed" / "drive1102-traces" / time.strftime("%H%M%S")
d.DB = d.TMP / "hub.db"
d.SHOT = d.TMP / "shot"


def turn(base, agent, message, task=None, conversation=None, stop_after=None):
    body = {"agent": agent, "message": message}
    if task:
        body["task_id"] = task
    if conversation:
        body["conversation_id"] = conversation
    code, run = d.api("POST", f"{base}/agent/trigger", body)
    d.check(f"{agent} turn starts", code in (200, 202), f"{code} {str(run)[:200]}")
    run_id = run["run_id"]
    if stop_after:
        # Stop once the run is seen running (not after a fixed sleep: a short turn would be over).
        d.poll(lambda: d.ro("select status from runs where id=?", (run_id,))[0][0] == "running", 60)
        time.sleep(stop_after)
        code, out = d.api("POST", f"{base}/agent/{agent}/stop")
        d.check(f"{agent} run is stopped", code in (200, 202), f"{code} {str(out)[:200]}")
    end = time.time() + 600
    while time.time() < end:
        (state,) = d.ro("select status from runs where id=?", (run_id,))[0]
        if state not in ("running", "queued", "starting"):
            return run_id, state
        time.sleep(3)
    d.check("turn ends within budget", False, run_id)


def drive():
    root = pathlib.Path(tempfile.mkdtemp(prefix="aw-traces-drive-")) / "proj"
    root.mkdir(parents=True)
    d.git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny service.\n", encoding="utf-8")
    d.git(root, "add", "README.md")
    d.git(root, "commit", "-q", "-m", "seed")
    code, project = d.api("POST", "/projects/open", {"path": str(root), "name": "traces"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    for name in ("alpha", "beta"):
        code, out = d.api("POST", f"{base}/agents",
                          {"name": name, "provider": "claude", "model": d.HAIKU})
        d.check(f"0 {name} is created on Haiku", code in (200, 201), f"{code} {str(out)[:200]}")
    code, task = d.api("POST", f"{base}/tasks", {"title": "say hi", "assignee": "alpha"})
    d.check("0 the task is created", code in (200, 201), f"{code} {str(task)[:200]}")

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (d.KEY, d.HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.goto(f"{d.HUB}/?project={pid}&tab=activity", wait_until="domcontentloaded")
        traces = page.get_by_role("radio", name="Traces")
        d.check("1 Activity has a Traces view", d.poll(lambda: traces.count() >= 1, 20),
                "no Traces segment beside Ledger, Activity and Logs")
        traces.first.click()
        d.check("1 the view opens", d.poll(lambda: page.get_by_test_id("traces-view").count() == 1))

        # 2. real runs
        a1, _ = turn(base, "alpha", "Reply with the single word ok.", task=task["id"])
        (conv,) = d.ro("select conversation_id from runs where id=?", (a1,))[0]
        d.check("2 the first turn has a conversation", bool(conv))
        b1, _ = turn(base, "beta", "Reply with the single word ok.")
        a2, _ = turn(base, "alpha", "Reply with the single word ok.", conversation=conv)
        # The 'failed run': a run cannot be made to fail on demand, so one is stopped part-way;
        # a stopped run counts as an error (FR-6). It is also the conversation's latest of three.
        a3, a3_state = turn(base, "alpha", "Count from 1 to 20000, one number per line, and do not stop early.",
                            conversation=conv, stop_after=3)
        d.check("2 the stopped run ended stopped", a3_state in ("stopped", "cancelled", "interrupted"),
                a3_state)
        cols = "id, agent, status, conversation_id, task_id"
        runs = [dict(zip(cols.split(", "), r)) for r in d.ro(f"select {cols} from runs")]
        by_id = {r["id"]: r for r in runs}
        d.check("2 the runs exist", {a1, b1, a2, a3} <= set(by_id))
        d.check("2 the conversation holds three runs",
                len([r for r in runs if r["conversation_id"] == conv]) == 3)
        # Recorded cost: turn_usage.api_equivalent_usd_micros is this run's settled cost.
        for r in runs:
            r["cost_usd"] = 0.0
        for rid, micros in d.ro("select run_id, api_equivalent_usd_micros from turn_usage"):
            if rid in by_id and micros is not None:
                by_id[rid]["cost_usd"] += micros / 1e6
        # Duration in seconds: ended_at - started_at (runs still open count as 0).
        for rid, secs in d.ro(
                "select id, (julianday(ended_at) - julianday(started_at)) * 86400.0 from runs"):
            by_id[rid]["duration_s"] = float(secs or 0.0)
        alpha_runs = [r for r in runs if r["agent"] == "alpha"]

        # 3. runs only, filter, group, stats
        page.reload(wait_until="domcontentloaded")
        page.get_by_role("radio", name="Traces").click()
        rows = page.get_by_test_id("trace-row")
        d.check("3 runs are listed", d.poll(lambda: rows.count() == len(runs)), f"rows={rows.count()}")
        page.get_by_test_id("traces-filter-agent").select_option("alpha")
        page.get_by_test_id("traces-filter-range").select_option("1h")
        d.check("3 the filter leaves alpha's runs",
                d.poll(lambda: rows.count() == len(alpha_runs)), f"rows={rows.count()}")
        page.get_by_role("radio", name="Agent", exact=True).click()
        group = page.locator('[data-testid=traces-group][data-key=alpha]')
        d.check("3 the alpha group is shown", d.poll(lambda: group.count() == 1))
        cost = sum(float(r.get("cost_usd") or 0) for r in alpha_runs)
        shown = float(group.get_by_test_id("traces-group-cost").get_attribute("data-value"))
        d.check("3 total cost is the sum of the runs' recorded costs", abs(shown - cost) < 1e-6,
                f"shown={shown} sum={cost}")
        d.check("3 the group shows the run count",
                int(group.get_by_test_id("traces-group-count").get_attribute("data-value")) == len(alpha_runs))
        # data-value of stat-duration / stat-avg-duration is in seconds; tolerance 1s per run
        # (the view may round each run's duration to whole seconds).
        total_s = sum(r["duration_s"] for r in alpha_runs)
        tol = 1.0 * len(alpha_runs)
        shown_total = float(group.get_by_test_id("traces-group-duration").get_attribute("data-value"))
        d.check("3 total duration matches started_at/ended_at", abs(shown_total - total_s) <= tol,
                f"shown={shown_total} expected={total_s} tol={tol}")
        shown_avg = float(group.get_by_test_id("traces-group-duration").get_attribute("data-avg"))
        d.check("3 average duration matches", abs(shown_avg - total_s / len(alpha_runs)) <= 1.0,
                f"shown={shown_avg} expected={total_s / len(alpha_runs)}")
        errors = sum(1 for r in alpha_runs if r["status"] in ("failed", "cancelled", "interrupted", "stopped"))
        d.check("3 errors counts the stopped run",
                int(group.get_by_test_id("traces-group-errors").get_attribute("data-value")) == errors == 1)

        # 4. entry points
        rows.first.click()
        detail = page.get_by_test_id("trace-detail")
        d.check("4 a listed run opens its trace", d.poll(lambda: detail.count() == 1))
        opened = detail.get_attribute("data-run-id")
        d.check("4 it is the run that was clicked", opened in {r["id"] for r in alpha_runs})
        page.goto(f"{d.HUB}/?project={pid}&agent=alpha&conversation={conv}", wait_until="domcontentloaded")
        page.get_by_test_id("conversation-more").click()
        page.get_by_role("menuitem", name="Trace of the latest run").click()
        d.check("4 the conversation's control opens its latest (third) run",
                d.poll(lambda: page.get_by_test_id("trace-detail").count() == 1
                       and page.get_by_test_id("trace-detail").get_attribute("data-run-id") == a3))
        # The task's run count opens Activity -> Traces filtered to the task; its run opens there.
        page.goto(f"{d.HUB}/?project={pid}&tab=tasks", wait_until="domcontentloaded")
        page.get_by_test_id(f"task-open-{task['id']}").click()
        page.get_by_test_id(f"task-story-runs-open-{task['id']}").click()
        d.check("4 the task's runs open filtered in Traces",
                d.poll(lambda: page.get_by_test_id("trace-row").count()
                       == len([r for r in runs if r["task_id"] == task["id"]])),
                f"rows={page.get_by_test_id('trace-row').count()} url={page.url}")
        page.screenshot(path=str(d.SHOT) + "_task.png", full_page=True)
        page.locator(f'[data-testid=trace-row][data-run-id={a1}]').click()
        d.check("4 the task's run opens that run's trace",
                d.poll(lambda: page.get_by_test_id("trace-detail").count() == 1
                       and page.get_by_test_id("trace-detail").get_attribute("data-run-id") == a1))
        page.screenshot(path=str(d.SHOT) + "_traces.png", full_page=True)
        browser.close()


if __name__ == "__main__":
    d.main = d.main  # keep the shared start/stop/report loop
    d.drive = drive
    d.main()
