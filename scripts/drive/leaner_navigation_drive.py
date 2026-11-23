"""Acceptance drive for `leaner-navigation-fewer-project-tabs-and-a-visible-side-panel-toggle`
(LNFPT-1), 2026-11-22: the `drive-leaner-navigation` criterion of FR-1, written failing first,
before anything is built. LNFPT-5 runs it green.

Drives the trial Hub (:8010, project proj-d85a82bf4216) with a real browser. It never drives :8000.
The Hub must already be serving this branch's built UI (`hub/hub/static/ui`); the drive does not
start or restart one.

Seeding: the drive first creates whatever is missing, and reuses what an earlier run left:
  - a Haiku runner, and a read-only agent `lnav-drive` bound to it;
  - a thread of that agent with a run that has a trace: one quiet Haiku turn (no tools, no files);
  - at least one checkpoint in that thread: the project's checkpoint runner is set to the Haiku
    runner only when none is set, then the operator's "checkpoint now" route is called;
  - a job of that agent, created disabled so it never fires (it shows in the Running tab, paused).

The steps, in order. Every one runs, so a baseline names each check's own failure:
  top-bar             the top bar's tabs are exactly Overview, Tasks, Profiles, Spec, Vault,
                      Dashboards, in that order.
  retired-activity    ?tab=activity opens Project settings > Budgets with the ledger.
  retired-jobs        ?tab=jobs opens Project settings > Jobs.
  retired-checkpoints ?tab=checkpoints&ckptConversation=C opens thread C with its Checkpoints panel
                      tab; ?tab=checkpoints&checkpoint=X opens X's thread with X opened there.
  retired-thread      ?tab=thread opens the Chapters view, with Overview highlighted in the bar.
  shortcut            Ctrl+Alt+B with focus in the composer hides, then shows, the side panel, and
                      types nothing into the composer.
  panel-checkpoints   ... > Checkpoints (N) adds a panel tab that was not in the row, showing the
                      thread's checkpoints, and the URL stays on the thread.
  panel-trace         ... > Trace of this thread adds a panel tab that was not in the row, showing
                      a trace, and the URL stays on the thread.
  spend-ledger        the Overview's spend button opens Project settings > Budgets with the ledger.
  running-job         opening the seeded job from the side panel's Running tab opens Project
                      settings > Jobs with that job expanded.

The page contract it probes (LNFPT-2..5 may rename these; then the drive changes, not the spec):
`nav[aria-label="Project views"] [data-testid^=project-tab-]`; `project-settings-<section>`;
`project-ledger`; `conversation-pane`; `conversation-toggle-panel` (aria-label Hide/Show side
panel); `panel-shell`; `panel-tab-<id>` in `panel-tab-strip`; `conversation-more`,
`conversation-checkpoints-toggle`, `conversation-trace-open`; `checkpoints-panel` (data-view
list|detail); `conversation-trace` (a thread's trace) or `trace-view`/`trace-subject`/
`trace-waterfall` (a run's); `composer-input`; `.aw-loom` or
`.aw-thread-note` for Chapters; `.aw-overview-spend` for the spend button; `running-tab` rows
`button.aw-run-row` titled "Open <name>"; a job row `.aw-job-item[data-open]` with `.aw-job-name`.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. A screenshot per step goes to
testbed/ui-judge/leaner-navigation/drive/.

    py -3.11 scripts/drive/leaner_navigation_drive.py --hub http://127.0.0.1:8010 --project proj-d85a82bf4216
"""

import argparse
import json
import pathlib
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
OUT = REPO / "testbed" / "ui-judge" / "leaner-navigation" / "drive"
TRIAL = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial"
HAIKU = "claude-haiku-4-5-20251001"
AGENT = "lnav-drive"
JOB_NAME = "Leaner navigation drive job (never fires)"
QUIET_TURN = (
    "This is a navigation test. Reply with the single word READY and nothing else. "
    "Do not call any tool, do not read, create, edit or delete any file, and do not run any command."
)
TOP_BAR = ["Overview", "Tasks", "Profiles", "Spec", "Vault", "Dashboards"]
ORDER = [
    "top-bar",
    "retired-activity",
    "retired-jobs",
    "retired-checkpoints",
    "retired-thread",
    "shortcut",
    "panel-checkpoints",
    "panel-trace",
    "spend-ledger",
    "running-job",
]
TURN_WAIT = 240

checks = {}  # key -> (reached, failed, detail)


class Setup(Exception):
    """The data the drive needs could not be created: no check is reached."""


class Unreached(Exception):
    """A step could not get as far as its own assertion."""


def record(key, reached, ok, detail):
    checks[key] = (reached, not ok, detail)
    print(f"{'PASS' if ok else 'FAIL'} {key} -- {detail}", flush=True)


# --------------------------------------------------------------------------- Hub access


class Hub:
    def __init__(self, url, key, project, db):
        self.url, self.key, self.pid, self.db = url.rstrip("/"), key, project, db
        self.base = f"/projects/{project}"

    def call(self, method, path, body=None, timeout=90):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + self.key, "Content-Type": "application/json"}
        request = urllib.request.Request(self.url + "/api/v1" + path, data, headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read() or b"null")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:2000]
            try:
                return exc.code, json.loads(text)
            except ValueError:
                return exc.code, text
        except (urllib.error.URLError, OSError) as exc:
            return 0, str(exc)

    def ro(self, sql, args=()):
        con = sqlite3.connect(f"file:{self.db.as_posix()}?mode=ro", uri=True)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()


def items(out, *keys):
    """A list route's rows, whether the route answers a list or wraps it."""
    if isinstance(out, list):
        return out
    if isinstance(out, dict):
        for key in keys:
            if isinstance(out.get(key), list):
                return out[key]
    return []


def poll(predicate, seconds, every=1.0):
    end = time.time() + seconds
    while time.time() < end:
        got = predicate()
        if got:
            return got
        time.sleep(every)
    return None


# --------------------------------------------------------------------------- seeding


def haiku_runner(hub):
    code, out = hub.call("GET", f"{hub.base}/runners")
    if code != 200:
        raise Setup(f"runners: {code} {str(out)[:300]}")
    for runner in items(out, "runners"):
        if runner.get("cli") == "claude" and "haiku" in str(runner.get("model") or "").lower():
            return runner["id"]
    code, out = hub.call("POST", f"{hub.base}/runners", {"name": "Haiku (leaner-navigation drive)", "cli": "claude", "model": HAIKU})
    if code not in (200, 201):
        raise Setup(f"create runner: {code} {str(out)[:300]}")
    return out["id"]


def drive_agent(hub, runner_id):
    code, out = hub.call("GET", f"{hub.base}/agents")
    if code != 200:
        raise Setup(f"agents: {code} {str(out)[:300]}")
    if any(a.get("name") == AGENT for a in items(out, "agents")):
        return
    code, out = hub.call("POST", f"{hub.base}/agents", {"name": AGENT, "runner_id": runner_id})
    if code not in (200, 201):
        raise Setup(f"create agent {AGENT}: {code} {str(out)[:300]}")
    code, out = hub.call("PATCH", f"{hub.base}/agents/{AGENT}", {"config": {"read_only": True}})
    if code != 200:
        raise Setup(f"{AGENT} read-only: {code} {str(out)[:300]}")


def traced_thread(hub):
    """(conversation id, run id) of a finished run of the drive's agent that has a trace."""
    rows = hub.ro(
        "select r.conversation_id, r.id from runs r where r.project_id=? and r.agent=? "
        "and r.conversation_id is not null and r.status not in ('running','queued','starting') "
        "and exists (select 1 from trace_spans t where t.run_id=r.id) "
        "order by r.started_at desc limit 1",
        (hub.pid, AGENT),
    )
    return rows[0] if rows else None


def run_quiet_turn(hub):
    before = hub.ro("select count(*) from runs where project_id=? and agent=?", (hub.pid, AGENT))[0][0]
    code, out = hub.call("POST", f"{hub.base}/agent/trigger", {"agent": AGENT, "message": QUIET_TURN})
    if code != 200:
        raise Setup(f"trigger {AGENT}: {code} {str(out)[:300]}")

    def ended():
        rows = hub.ro(
            "select id, status from runs where project_id=? and agent=? order by started_at desc limit 1",
            (hub.pid, AGENT),
        )
        count = hub.ro("select count(*) from runs where project_id=? and agent=?", (hub.pid, AGENT))[0][0]
        return count > before and rows and rows[0][1] not in ("running", "queued", "starting", "pending")

    if not poll(ended, TURN_WAIT, every=2):
        raise Setup(f"{AGENT}'s turn did not end within {TURN_WAIT}s")
    found = poll(lambda: traced_thread(hub), 30, every=2)
    if not found:
        raise Setup(f"{AGENT}'s turn ended without a trace")
    return found


def thread_checkpoints(hub, conversation):
    code, out = hub.call("GET", f"{hub.base}/conversations/{conversation}/checkpoints")
    if code != 200:
        raise Setup(f"checkpoints of {conversation}: {code} {str(out)[:300]}")
    return items(out, "checkpoints")


def ensure_checkpoint(hub, conversation, runner_id):
    existing = thread_checkpoints(hub, conversation)
    if existing:
        return existing[0]["id"]
    code, settings = hub.call("GET", f"{hub.base}/settings")
    if code != 200:
        raise Setup(f"project settings: {code} {str(settings)[:300]}")
    if not settings.get("checkpoint_runner_id"):
        # The settings route merges a partial body onto what is stored.
        code, out = hub.call("PUT", f"{hub.base}/settings", {"checkpoint_runner_id": runner_id})
        if code != 200:
            raise Setup(f"set checkpoint runner: {code} {str(out)[:300]}")
    code, out = hub.call("POST", f"{hub.base}/conversations/{conversation}/checkpoint", timeout=300)
    if code not in (200, 201):
        raise Setup(f"take checkpoint: {code} {str(out)[:300]}")
    return out["id"]


def ensure_job(hub):
    code, out = hub.call("GET", f"{hub.base}/jobs")
    if code != 200:
        raise Setup(f"jobs: {code} {str(out)[:300]}")
    for job in items(out, "jobs"):
        if job.get("name") == JOB_NAME and not job.get("archived_at"):
            return job["id"]
    body = {"name": JOB_NAME, "agent": AGENT, "message": QUIET_TURN, "cron": "0 3 1 1 *", "enabled": False}
    code, out = hub.call("POST", f"{hub.base}/jobs", body)
    if code not in (200, 201):
        raise Setup(f"create job: {code} {str(out)[:300]}")
    return out["id"]


def seed(hub):
    runner_id = haiku_runner(hub)
    drive_agent(hub, runner_id)
    found = traced_thread(hub) or run_quiet_turn(hub)
    conversation, run_id = found
    checkpoint = ensure_checkpoint(hub, conversation, runner_id)
    job = ensure_job(hub)
    state = {"conversation": conversation, "run": run_id, "checkpoint": checkpoint, "job": job}
    print(f"seeded: {state}", flush=True)
    return state


# --------------------------------------------------------------------------- browser helpers


def new_page(browser, hub):
    context = browser.new_context(viewport={"width": 1440, "height": 940}, device_scale_factor=1)
    context.add_init_script(
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s); } catch (e) {}"
        % (json.dumps(hub.key), json.dumps(hub.url), json.dumps(hub.pid))
    )
    return context.new_page()


def go(page, hub, **params):
    query = urllib.parse.urlencode({"project": hub.pid, **params})
    for attempt in (1, 2):
        page.goto(f"{hub.url}/?{query}", wait_until="domcontentloaded")
        try:
            # A cold Hub's first page can take a while: its project list and bundle load first.
            page.get_by_test_id("topbar").wait_for(timeout=45000)
            break
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise Unreached("the app did not render its top bar")
    page.wait_for_timeout(1200)


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path))
    return path


def url_params(page):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


def visible(page, selector, timeout=8000):
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 -- a timeout is the answer "not visible"
        return False


def top_bar_labels(page):
    tabs = page.locator('nav[aria-label="Project views"] [data-testid^="project-tab-"]:not([data-testid="project-tab-more"])')
    return [re.sub(r"\s*\d+$", "", t.strip()) for t in tabs.all_inner_texts()]


def active_tab(page):
    active = page.locator('nav[aria-label="Project views"] [data-active="true"]')
    return active.first.get_attribute("data-testid") if active.count() else None


def in_thread(params, conversation):
    return params.get("conversation") == conversation and "tab" not in params


def open_thread(page, hub, state):
    go(page, hub, agent=AGENT, conversation=state["conversation"])
    if not visible(page, '[data-testid="conversation-pane"]', 20000):
        raise Unreached("the thread did not open")


def panel_open(page):
    return page.locator('[data-testid="panel-shell"]').first.is_visible() if page.locator('[data-testid="panel-shell"]').count() else False


def ensure_panel(page):
    toggle = page.get_by_test_id("conversation-toggle-panel")
    if not toggle.count():
        raise Unreached("no side-panel toggle in the thread bar")
    if not panel_open(page):
        toggle.first.click()
        page.wait_for_timeout(600)
    if not panel_open(page):
        raise Unreached("the side panel could not be opened")


def panel_tab_ids(page):
    ids = page.locator(
        '[data-testid="panel-tab-strip"] [data-testid^="panel-tab-"]'
        ':not([data-testid^="panel-tab-close-"]):not([data-testid="panel-tab-add"])'
    )
    return [i.replace("panel-tab-", "", 1) for i in (ids.nth(n).get_attribute("data-testid") for n in range(ids.count())) if i]


def thread_menu(page, item_testid):
    more = page.get_by_test_id("conversation-more")
    if not more.count():
        raise Unreached("no ... menu in the thread bar")
    more.first.click()
    item = page.get_by_test_id(item_testid)
    try:
        item.first.wait_for(state="visible", timeout=5000)
    except Exception:  # noqa: BLE001
        page.keyboard.press("Escape")
        raise Unreached(f"the ... menu holds no {item_testid}")
    item.first.click()
    page.wait_for_timeout(1500)


# --------------------------------------------------------------------------- the steps


def step_top_bar(page, hub, state):
    go(page, hub)
    labels = top_bar_labels(page)
    shot(page, "01-top-bar")
    return labels == TOP_BAR, f"top bar tabs {labels}, want {TOP_BAR}"


def step_retired_activity(page, hub, state):
    go(page, hub, tab="activity")
    ok = visible(page, '[data-testid="project-settings-budgets"]') and visible(page, '[data-testid="project-settings-budgets"] [data-testid="project-ledger"]', 4000)
    shot(page, "02-retired-activity")
    return ok, f"tab=activity landed on {url_params(page)}; Budgets with ledger shown: {ok}"


def step_retired_jobs(page, hub, state):
    go(page, hub, tab="jobs")
    ok = visible(page, '[data-testid="project-settings-jobs"]')
    shot(page, "03-retired-jobs")
    return ok, f"tab=jobs landed on {url_params(page)}; Settings > Jobs shown: {ok}"


def step_retired_checkpoints(page, hub, state):
    conversation, checkpoint = state["conversation"], state["checkpoint"]
    go(page, hub, tab="checkpoints", ckptConversation=conversation)
    page.wait_for_timeout(1500)
    by_conversation = in_thread(url_params(page), conversation) and visible(page, '[data-testid="panel-tab-content"] [data-testid="checkpoints-panel"]')
    first = url_params(page)
    shot(page, "04a-retired-checkpoints-conversation")
    go(page, hub, tab="checkpoints", checkpoint=checkpoint)
    page.wait_for_timeout(2000)
    by_checkpoint = in_thread(url_params(page), conversation) and visible(page, '[data-testid="panel-tab-content"] [data-testid="checkpoints-panel"][data-view="detail"]')
    shot(page, "04b-retired-checkpoints-checkpoint")
    return by_conversation and by_checkpoint, (
        f"ckptConversation landed on {first} (thread + Checkpoints tab: {by_conversation}); "
        f"checkpoint={checkpoint} landed on {url_params(page)} (thread + that checkpoint open: {by_checkpoint})"
    )


def step_retired_thread(page, hub, state):
    go(page, hub, tab="thread")
    chapters = visible(page, ".aw-loom, .aw-thread-note", 10000)
    active = active_tab(page)
    shot(page, "05-retired-thread")
    ok = chapters and active == "project-tab-overview"
    return ok, f"tab=thread: Chapters view shown: {chapters}; highlighted tab {active}, want project-tab-overview"


def step_shortcut(page, hub, state):
    open_thread(page, hub, state)
    ensure_panel(page)
    composer = page.get_by_test_id("composer-input")
    if not composer.count():
        raise Unreached("no composer in the thread")
    # A contenteditable textbox, not a <textarea>: its text is what was typed.
    composer.first.click()
    before_text = composer.first.inner_text()
    page.keyboard.press("Control+Alt+KeyB")
    page.wait_for_timeout(700)
    hidden = not panel_open(page)
    shot(page, "06a-shortcut-hidden")
    composer.first.click()
    page.keyboard.press("Control+Alt+KeyB")
    page.wait_for_timeout(700)
    shown = panel_open(page)
    after_text = composer.first.inner_text()
    shot(page, "06b-shortcut-shown")
    ok = hidden and shown and after_text == before_text
    return ok, f"first press hid the panel: {hidden}; second showed it: {shown}; composer unchanged: {after_text == before_text} ({after_text!r})"


def step_panel_checkpoints(page, hub, state):
    open_thread(page, hub, state)
    ensure_panel(page)
    before = panel_tab_ids(page)
    thread_menu(page, "conversation-checkpoints-toggle")
    after = panel_tab_ids(page) if panel_open(page) else []
    added = [t for t in after if t not in before]
    stayed = in_thread(url_params(page), state["conversation"])
    listed = visible(page, '[data-testid="panel-tab-content"] [data-testid="checkpoints-panel"]', 5000)
    shot(page, "07-panel-checkpoints")
    ok = bool(added) and stayed and listed
    return ok, f"tabs before {before}, after {after} (added {added}); checkpoints listed in panel: {listed}; URL stayed on the thread: {stayed} ({url_params(page)})"


def step_panel_trace(page, hub, state):
    open_thread(page, hub, state)
    ensure_panel(page)
    before = panel_tab_ids(page)
    thread_menu(page, "conversation-trace-open")
    after = panel_tab_ids(page) if panel_open(page) else []
    added = [t for t in after if t not in before]
    stayed = in_thread(url_params(page), state["conversation"])
    traced = visible(page, '[data-testid="panel-tab-content"] :is([data-testid="conversation-trace"], [data-testid="trace-view"], [data-testid="trace-subject"], [data-testid="trace-waterfall"])', 8000)
    shot(page, "08-panel-trace")
    ok = bool(added) and stayed and traced
    return ok, f"tabs before {before}, after {after} (added {added}); trace shown in panel: {traced}; URL stayed on the thread: {stayed} ({url_params(page)})"


def step_spend_ledger(page, hub, state):
    go(page, hub)
    spend = page.locator("button.aw-overview-spend")
    if not visible(page, "button.aw-overview-spend", 10000):
        shot(page, "09-spend-ledger")
        raise Unreached("no spend button on the Overview")
    spend.first.click()
    page.wait_for_timeout(1500)
    ok = visible(page, '[data-testid="project-settings-budgets"]') and visible(page, '[data-testid="project-settings-budgets"] [data-testid="project-ledger"]', 4000)
    shot(page, "09-spend-ledger")
    return ok, f"spend button landed on {url_params(page)}; Budgets with ledger shown: {ok}"


def step_running_job(page, hub, state):
    open_thread(page, hub, state)
    ensure_panel(page)
    running = page.get_by_test_id("panel-tab-running")
    if running.count():
        running.first.click()
    elif page.get_by_test_id("panel-launch-running").count():
        page.get_by_test_id("panel-launch-running").first.click()
    else:
        raise Unreached("no Running tab in the side panel")
    if not visible(page, '[data-testid="running-tab"]', 8000):
        raise Unreached("the Running tab did not show")
    row = page.locator(f'[data-testid="running-tab"] button.aw-run-row[title="Open {JOB_NAME}"]')
    if not visible(page, f'[data-testid="running-tab"] button.aw-run-row[title="Open {JOB_NAME}"]', 8000):
        shot(page, "10-running-job")
        raise Unreached(f"the Running tab lists no row for {JOB_NAME!r}")
    row.first.click()
    page.wait_for_timeout(2000)
    section = visible(page, '[data-testid="project-settings-jobs"]')
    expanded = page.locator('[data-testid="project-settings-jobs"] .aw-job-item[data-open="true"]').filter(has_text=JOB_NAME)
    is_expanded = section and expanded.count() > 0
    shot(page, "10-running-job")
    return is_expanded, f"opening the job landed on {url_params(page)}; Settings > Jobs shown: {section}; {JOB_NAME!r} expanded: {is_expanded}"


STEPS = {
    "top-bar": step_top_bar,
    "retired-activity": step_retired_activity,
    "retired-jobs": step_retired_jobs,
    "retired-checkpoints": step_retired_checkpoints,
    "retired-thread": step_retired_thread,
    "shortcut": step_shortcut,
    "panel-checkpoints": step_panel_checkpoints,
    "panel-trace": step_panel_trace,
    "spend-ledger": step_spend_ledger,
    "running-job": step_running_job,
}


# --------------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hub", required=True, help="the trial Hub, e.g. http://127.0.0.1:8010")
    parser.add_argument("--project", required=True, help="e.g. proj-d85a82bf4216")
    parser.add_argument("--key", default="", help="the Hub's key (default: the trial profile's bootstrap key)")
    parser.add_argument("--db", default="", help="the Hub's SQLite, read only (default: the trial profile's)")
    parser.add_argument("--only", default="", help="comma-separated step keys")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    if urllib.parse.urlparse(args.hub).port == 8000:
        sys.exit("REFUSING: :8000 is the operator's real instance")
    key = args.key or (TRIAL / "bootstrap-key.txt").read_text(encoding="utf-8").strip()
    db = pathlib.Path(args.db) if args.db else TRIAL / "agentweave.db"
    hub = Hub(args.hub, key, args.project, db)
    wanted = [k for k in ORDER if not args.only or k in args.only.split(",")]

    code, out = hub.call("GET", hub.base)
    if code != 200:
        sys.exit(f"the Hub at {hub.url} does not answer for {hub.pid}: {code} {str(out)[:300]}")

    try:
        state = seed(hub)
    except Setup as exc:
        for key_ in wanted:
            record(key_, False, False, f"setup failed: {exc}")
        return report()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed)
        try:
            for key_ in wanted:
                page = new_page(browser, hub)
                try:
                    ok, detail = STEPS[key_](page, hub, state)
                    record(key_, True, ok, detail)
                except Unreached as exc:
                    record(key_, False, False, f"not reached: {exc}")
                except Exception as exc:  # noqa: BLE001 -- a broken step must not hide the others
                    record(key_, False, False, f"not reached: {type(exc).__name__}: {str(exc)[:300]}")
                finally:
                    page.context.close()
        finally:
            browser.close()
    return report()


def report():
    print()
    for key in ORDER:
        if key in checks:
            reached, failed, detail = checks[key]
            print(f"check {key}: reached={'yes' if reached else 'no'} failed_at_assertion={'yes' if reached and failed else 'no'} -- {detail}")
    failed = [k for k, (_r, f, _d) in checks.items() if f]
    print(f"\nscreenshots: {OUT}")
    print(f"{len(checks) - len(failed)} passed, {len(failed)} failed" + (f": {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
