"""Acceptance drive for `background-manager-work-you-can-see` (BWYCS-1), 2026-11-23: the
`acceptance-drive` criterion of FR-1, with the steps FR-3, FR-5, FR-6 and FR-8 name, written
failing first, before anything is built. BWYCS-7 runs it green.

Drives the trial Hub (:8010, project proj-d85a82bf4216) with a real browser. It never drives :8000.
The Hub must already be serving the built UI (`hub/hub/static/ui`); the drive does not start or
restart one.

Seeding: the spec-vault-check job is turned on with a Haiku runner and its model set to Haiku (the
job's previous choice is put back at the end). The document checked is `--document`, by default a
one-requirement change; the vault must hold current facts (the drive refuses to start otherwise).
Every check costs one Haiku call over the vault's facts; the failure steps cost nothing, because a
model that does not exist never reaches a provider.

The model that does not exist: `PATCH /manager/jobs/spec-vault-check` refuses an undeclared model
(F630), so the failure steps write the job's `model` straight into the trial Hub's database
(`manager_jobs`), and put the stored value back after. `prepare` reads the row at each check, so
no restart is involved. This is the only write the drive makes outside the Hub's routes.

The steps, in order. Every one runs, so a baseline names each check's own failure:
  working-icon      Check now on the spec's vault warnings: within 5 s the
                    `manager-icon` inside `spec-vault-warnings` has data-state=working.
  indicator-count   `manager-indicator-count` reads 1 while that run is in progress.
  popover-running   hovering `manager-indicator` opens `manager-popover`, whose row
                    `manager-popover-run-<run_id>` names Spec vault check, the spec's title and an
                    elapsed time that grows.
  ended             when the run ends (its `manager_job_fired` firing appears): the icon is idle,
                    the warnings list shows what the warnings route answers, the count is gone, and
                    the popover row is listed as finished; clicking it lands on Settings > Manager
                    with run=<run_id>.
  settings-log      Settings > Manager lists `manager-run-<run_id>` with Spec vault check, the
                    trigger (`requested`), 'manual', a duration and `manager-run-<run_id>-cost`.
  reload-mid-run    a check started ~10 s before a reload shows after it in the count, and its
                    popover row's elapsed time is counted from the run's start.
  failure           with the model that does not exist, a check started while the browser is on
                    another page fails; after a reload, opening the spec shows the icon failed, and
                    `manager-run-<run_id>-reason` holds the reason.
  failure-seen-a    a fresh failure; opening the spec's warnings marks it seen: it leaves
                    `GET /manager/runs/unseen-failures`, and after a reload the icon is not failed.
  failure-seen-b    a fresh failure; hovering the top-bar indicator while it is listed marks it
                    seen, the same two ways.
  failure-seen-c    a fresh failure; pressing Check now again sends the icon straight from failed
                    to working, never through idle.

The page contract it probes is the design's Contract (`spec.json`, "UI addresses and test ids"):
`spec-vault-warnings`, `spec-vault-warnings-check`, `manager-icon` (data-state idle|working|failed,
data-job), `manager-indicator`, `manager-indicator-count`, `manager-popover`,
`manager-popover-run-<run_id>`, `manager-run-<run_id>`, `manager-run-<run_id>-reason`,
`manager-run-<run_id>-cost`; `project-settings-manager`; and the routes `GET /manager/runs/running`,
`GET /manager/runs`, `GET /manager/runs/unseen-failures`. The spec's warnings open from the health
line: `spec-health-vault` > "Show details" > `spec-detail-vault`.

Prints one line per check in the `drive_baseline` shape:
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
and exits 1 if any check failed. A screenshot per step goes to
testbed/ui-judge/background-work/drive/.

    py -3.11 scripts/drive/background_work_drive.py --assert
    py -3.11 scripts/drive/background_work_drive.py --assert --only working-icon,indicator-count
"""

import argparse
import datetime
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
OUT = REPO / "testbed" / "ui-judge" / "background-work" / "drive"
TRIAL = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial"
JOB = "spec-vault-check"
JOB_TITLE = "Spec vault check"
TRIGGER = "requested"
HAIKU = "claude-haiku-4-5-20251001"
NO_SUCH_MODEL = "claude-no-such-model-bwycs"
DEFAULT_DOCUMENT = "spec/changes/the-model-catalog-tracks-the-newest-clis/spec.json"
ORDER = [
    "working-icon",
    "indicator-count",
    "popover-running",
    "ended",
    "settings-log",
    "reload-mid-run",
    "failure",
    "failure-seen-a",
    "failure-seen-b",
    "failure-seen-c",
]
RUN_WAIT = 300
ICON = '[data-testid="spec-vault-warnings"] [data-testid="manager-icon"]'
FINISHED = re.compile(r"finish|ended|done|wrote|written|empty|no conflict|conflicts? kept", re.I)

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

    def write_job_model(self, model):
        """The one write outside the routes: a model the PATCH route would refuse (F630)."""
        con = sqlite3.connect(str(self.db), timeout=30)
        try:
            con.execute("update manager_jobs set model=? where project_id=? and job=?", (model, self.pid, JOB))
            con.commit()
        finally:
            con.close()


def items(out, *keys):
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


def hub_seconds(iso):
    """Seconds since an ISO-8601 Hub time (UTC when it names no zone)."""
    value = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - value).total_seconds()


def seconds_in(text):
    """The largest elapsed time written in *text* ('12s', '1m 05s', '1:05', '2 min'), or None."""
    found = []
    for m in re.finditer(r"(\d+):(\d{2})(?::(\d{2}))?", text):
        parts = [int(p) for p in m.groups() if p is not None]
        found.append(parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1])
    for m in re.finditer(r"(?:(\d+)\s*h\s*)?(?:(\d+)\s*m(?:in)?\s*)?(\d+)\s*s\b", text):
        h, mnt, s = (int(p) if p else 0 for p in m.groups())
        found.append(h * 3600 + mnt * 60 + s)
    for m in re.finditer(r"(\d+)\s*min\b", text):
        found.append(int(m.group(1)) * 60)
    return max(found) if found else None


# --------------------------------------------------------------------------- the job and its runs


def firings(hub):
    code, out = hub.call("GET", f"{hub.base}/manager/activity?job={JOB}&limit=20")
    if code != 200:
        raise Unreached(f"manager activity: {code} {str(out)[:200]}")
    return items(out, "firings")


def last_firing_id(hub):
    rows = firings(hub)
    return rows[0]["id"] if rows else None


def wait_for_firing(hub, document, after_id, seconds=RUN_WAIT):
    """The first firing on *document* newer than *after_id*: the run's end, as recorded today."""

    def found():
        for row in firings(hub):
            if row["id"] == after_id:
                return None
            if (row.get("subject") or {}).get("document") == document:
                return row
        return None

    return poll(found, seconds, every=2)


def running_runs(hub):
    """`GET /manager/runs/running`'s rows, or None when the route is absent."""
    code, out = hub.call("GET", f"{hub.base}/manager/runs/running")
    return items(out, "runs") if code == 200 else None


def running_run_on(hub, document, seconds=5):
    def found():
        for run in running_runs(hub) or []:
            if run.get("job") == JOB and (run.get("subject") or {}).get("document") == document:
                return run
        return None

    return poll(found, seconds, every=0.5)


def unseen_failures(hub):
    code, out = hub.call("GET", f"{hub.base}/manager/runs/unseen-failures")
    return [f.get("run_id") for f in items(out, "failures")] if code == 200 else None


def start_check(hub, document):
    code, out = hub.call("POST", f"{hub.base}/vault/warnings/check?path={urllib.parse.quote(document)}")
    if code != 202:
        raise Unreached(f"POST vault/warnings/check: {code} {str(out)[:300]}")


def warnings_on(hub, document):
    code, out = hub.call("GET", f"{hub.base}/vault/warnings?path={urllib.parse.quote(document)}")
    if code != 200:
        raise Unreached(f"GET vault/warnings: {code} {str(out)[:200]}")
    return items(out, "warnings")


def haiku_runner(hub):
    code, out = hub.call("GET", f"{hub.base}/runners")
    if code != 200:
        raise Setup(f"runners: {code} {str(out)[:300]}")
    for runner in items(out, "runners"):
        if runner.get("cli") == "claude" and "haiku" in str(runner.get("model") or "").lower():
            return runner["id"]
    code, out = hub.call("POST", f"{hub.base}/runners", {"name": "Haiku (background-work drive)", "cli": "claude", "model": HAIKU})
    if code not in (200, 201):
        raise Setup(f"create runner: {code} {str(out)[:300]}")
    return out["id"]


def seed(hub, document):
    code, out = hub.call("GET", f"{hub.base}/manager/jobs")
    if code != 200:
        raise Setup(f"manager jobs: {code} {str(out)[:300]}")
    job = next((j for j in items(out, "jobs") if j.get("key") == JOB), None)
    if job is None:
        raise Setup(f"no {JOB} job on this Hub")
    previous = {"enabled": bool(job.get("enabled")), "runner_id": job.get("runner_id"), "model": job.get("model")}
    runner_id = haiku_runner(hub)
    code, out = hub.call("PATCH", f"{hub.base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": runner_id, "model": HAIKU})
    if code != 200:
        raise Setup(f"turn {JOB} on with Haiku: {code} {str(out)[:300]}")
    rows = hub.ro(
        "select d.title, count(r.id) from spec_documents d left join spec_requirements r "
        "on r.document_id=d.id and r.state='active' where d.project_id=? and d.path=? group by d.id",
        (hub.pid, document),
    )
    if not rows or not rows[0][1]:
        raise Setup(f"{document} is not a document with requirements in {hub.pid}")
    code, out = hub.call("GET", f"{hub.base}/vault/map")
    facts = [e for e in items(out, "entries") if e.get("type") == "fact" and not e.get("archived")]
    if not facts:
        raise Setup("the vault holds no current fact, so Check now would refuse")
    state = {"document": document, "title": rows[0][0], "runner": runner_id, "previous": previous}
    print(f"seeded: {JOB} on with {runner_id}/{HAIKU}; {document} ({rows[0][1]} requirements), {len(facts)} facts", flush=True)
    return state


def restore(hub, state):
    previous = state["previous"]
    hub.write_job_model(previous["model"])
    # Null clears the runner, as on the settings route.
    body = {"enabled": previous["enabled"], "runner_id": previous["runner_id"]}
    code, out = hub.call("PATCH", f"{hub.base}/manager/jobs/{JOB}", body)
    print(f"restored {JOB} to {previous}: {code}", flush=True)


# --------------------------------------------------------------------------- browser helpers


UI_DIR = None  # set by main: a bundle served in place of the Hub's own, or None
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
         ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2", ".json": "application/json"}


def serve_bundle(route):
    """Answer a page request from UI_DIR on the Hub's own origin; the API still reaches the Hub."""
    path = urllib.parse.urlparse(route.request.url).path
    if path.startswith("/api/") or path == "/health":
        return route.continue_()
    target = (UI_DIR / path.lstrip("/")).resolve()
    if not target.is_file() or UI_DIR.resolve() not in target.parents:
        target = UI_DIR / "index.html"
    route.fulfill(status=200, body=target.read_bytes(), content_type=TYPES.get(target.suffix, "application/octet-stream"))


def new_page(browser, hub):
    context = browser.new_context(viewport={"width": 1440, "height": 940}, device_scale_factor=1)
    if UI_DIR is not None:
        context.route(f"{hub.url}/**", serve_bundle)
    context.add_init_script(
        "try { sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %s, hubUrl: %s}));"
        "localStorage.setItem('agentweave-selected-project', %s); } catch (e) {}"
        % (json.dumps(hub.key), json.dumps(hub.url), json.dumps(hub.pid))
    )
    # The trial Hub holds ~200 projects and the sidebar reads each one's threads, so a fresh page
    # queued well over a hundred requests behind the browser's six connections to one host
    # (BWYCS-7: Check now's POST waited 14 s in that queue). Other projects' reads are refused, so
    # the page loads as it does for an operator with one project, and `settle` waits for what is
    # left to drain before a timed step, so its clock measures this change rather than that fan-out.
    context.route(re.compile(r".*/api/v1/projects/(?!%s)[^/?]+/.*" % re.escape(hub.pid)), lambda route: route.abort())
    page = context.new_page()
    INFLIGHT[page] = set()
    page.on("request", lambda r: INFLIGHT[page].add(r))
    page.on("requestfinished", lambda r: INFLIGHT[page].discard(r))
    page.on("requestfailed", lambda r: INFLIGHT[page].discard(r))
    return page


INFLIGHT = {}


def settle(page, under=6, seconds=120):
    """Wait until fewer than *under* requests are in flight (the event stream is one), or *seconds*."""
    end = time.time() + seconds
    while time.time() < end:
        if len([r for r in INFLIGHT.get(page, ()) if "/events" not in r.url]) < under:
            return True
        page.wait_for_timeout(250)
    return False


def go(page, hub, **params):
    query = urllib.parse.urlencode({"project": hub.pid, **params})
    for attempt in (1, 2):
        page.goto(f"{hub.url}/?{query}", wait_until="domcontentloaded")
        try:
            page.get_by_test_id("topbar").wait_for(timeout=45000)
            break
        except Exception:  # noqa: BLE001
            if attempt == 2:
                raise Unreached("the app did not render its top bar")
    page.wait_for_timeout(1200)
    settle(page)


def shot(page, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path))
    return path


def visible(page, selector, timeout=8000):
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=timeout)
        return True
    except Exception:  # noqa: BLE001 -- a timeout is the answer "not visible"
        return False


def url_params(page):
    return dict(urllib.parse.parse_qsl(urllib.parse.urlparse(page.url).query))


def open_warnings(page, hub, document):
    """The spec page with its vault warnings open in place."""
    go(page, hub, tab="spec", document=document)
    fact = page.get_by_test_id("spec-health-vault")
    try:
        fact.first.wait_for(state="visible", timeout=20000)
    except Exception:  # noqa: BLE001
        raise Unreached("the spec's health line has no vault fact")
    if not page.get_by_test_id("spec-vault-warnings").count():
        fact.first.click()
        item = page.get_by_role("menuitem", name="Show details")
        try:
            item.first.wait_for(state="visible", timeout=5000)
        except Exception:  # noqa: BLE001
            page.keyboard.press("Escape")
            raise Unreached("the vault fact's menu has no Show details")
        item.first.click()
    if not visible(page, '[data-testid="spec-vault-warnings"]', 10000):
        raise Unreached("the spec's vault warnings did not open")
    settle(page)


def icon_state(page):
    icon = page.locator(ICON)
    return icon.first.get_attribute("data-state") if icon.count() else None


def wait_icon(page, want, seconds):
    end = time.time() + seconds
    seen = []
    while time.time() < end:
        state = icon_state(page)
        if not seen or seen[-1] != state:
            seen.append(state)
        if state == want:
            return True, seen
        page.wait_for_timeout(100)
    return False, seen


def count_text(page):
    count = page.get_by_test_id("manager-indicator-count")
    if not count.count() or not count.first.is_visible():
        return None
    return count.first.inner_text().strip()


def hover_indicator(page):
    """The popover, opened by hovering the top-bar indicator, or None when there is none to hover."""
    indicator = page.get_by_test_id("manager-indicator")
    if not indicator.count():
        return None
    indicator.first.hover()
    if not visible(page, '[data-testid="manager-popover"]', 4000):
        return None
    return page.get_by_test_id("manager-popover").first


def press_check(page):
    button = page.get_by_test_id("spec-vault-warnings-check")
    if not button.count():
        raise Unreached("no Check now on the spec's vault warnings")
    if button.first.is_disabled():
        raise Unreached("Check now is disabled")
    button.first.click()


def run_id_of(firing):
    return (firing or {}).get("run_id")


# --------------------------------------------------------------------------- the steps
# Steps share `state`: the run the first step starts is the run the next four watch.


def step_working_icon(page, hub, state):
    open_warnings(page, hub, state["document"])
    state["before"] = last_firing_id(hub)
    press_check(page)
    state["pressed_at"] = time.time()
    ok, seen = wait_icon(page, "working", 5)
    shot(page, "01-working-icon")
    running = running_run_on(hub, state["document"], seconds=30)
    state["run"] = running
    state["page"] = page
    return ok, f"manager-icon states seen inside spec-vault-warnings within 5 s: {seen}, want working; running-now row: {running}"


def step_indicator_count(page, hub, state):
    page = state.get("page") or page
    text = None
    end = time.time() + 5
    while time.time() < end and text != "1":
        text = count_text(page)
        page.wait_for_timeout(200)
    shot(page, "02-indicator-count")
    return text == "1", f"manager-indicator-count reads {text!r}, want '1'"


def step_popover_running(page, hub, state):
    page = state.get("page") or page
    popover = hover_indicator(page)
    if popover is None:
        shot(page, "03-popover-running")
        return False, "no manager-indicator to hover, or hovering it opened no manager-popover"
    run = state.get("run")
    row = page.get_by_test_id(f"manager-popover-run-{run['run_id']}") if run else popover
    first = row.first.inner_text() if row.count() else ""
    page.wait_for_timeout(2500)
    second = row.first.inner_text() if row.count() else ""
    shot(page, "03-popover-running")
    a, b = seconds_in(first), seconds_in(second)
    names = JOB_TITLE in second and state["title"] in second
    grows = a is not None and b is not None and b > a
    ok = bool(run) and names and grows
    return ok, f"popover row for run {run and run.get('run_id')}: {second[:200]!r}; names job and spec: {names}; elapsed {a} -> {b} grows: {grows}"


def step_ended(page, hub, state):
    page = state.get("page") or page
    if "pressed_at" not in state:
        raise Unreached("working-icon never pressed Check now, so there is no run to watch end")
    firing = wait_for_firing(hub, state["document"], state.get("before"))
    if firing is None:
        raise Unreached(f"the check did not end within {RUN_WAIT}s")
    state["firing"] = firing
    page.wait_for_timeout(5000)  # the 5 s the requirement allows for the end to be seen
    idle = icon_state(page) == "idle"
    wanted = warnings_on(hub, state["document"])
    shown = page.locator('[data-testid="spec-vault-warnings"] [data-testid^="spec-vault-warning-"]:not([data-testid="spec-vault-warnings-check"])').count()
    stale = page.get_by_text("reload the list", exact=False).count() > 0
    listed = shown == len(wanted) and not stale
    gone = count_text(page) is None
    run_id = run_id_of(firing)
    popover = hover_indicator(page)
    row = page.get_by_test_id(f"manager-popover-run-{run_id}") if run_id and popover is not None else None
    row_text = row.first.inner_text() if row is not None and row.count() else ""
    finished = bool(row_text) and bool(FINISHED.search(row_text))
    shot(page, "04-ended")
    landed = False
    if finished:
        row.first.click()
        page.wait_for_timeout(1500)
        params = url_params(page)
        landed = params.get("run") == run_id and visible(page, '[data-testid="project-settings-manager"]', 5000)
    ok = idle and listed and gone and finished and landed
    return ok, (
        f"run {run_id} ended {firing.get('outcome')!r}; icon idle: {idle} ({icon_state(page)!r}); warnings shown {shown} of the route's "
        f"{len(wanted)}, 'reload' hint shown: {stale}; count gone: {gone}; popover row {row_text[:120]!r} finished: {finished}; "
        f"click landed on the run: {landed} ({url_params(page)})"
    )


def step_settings_log(page, hub, state):
    firing = state.get("firing")
    if firing is None:
        raise Unreached("no ended run from the earlier steps")
    run_id = run_id_of(firing)
    go(page, hub, tab="environment", section="manager")
    if not visible(page, '[data-testid="project-settings-manager"]', 15000):
        raise Unreached("Settings > Manager did not open")
    row = page.get_by_test_id(f"manager-run-{run_id}") if run_id else None
    text = row.first.inner_text() if row is not None and visible(page, f'[data-testid="manager-run-{run_id}"]', 8000) else ""
    cost = page.get_by_test_id(f"manager-run-{run_id}-cost") if run_id else None
    cost_text = cost.first.inner_text().strip() if cost is not None and cost.count() else ""
    shot(page, "05-settings-log")
    has = {
        "job": JOB_TITLE in text,
        "trigger": TRIGGER in text.lower(),
        "manual": "manual" in text.lower(),
        "duration": seconds_in(text) is not None or bool(re.search(r"\d+\s*ms\b", text)),
        "cost": bool(cost_text),
    }
    return bool(run_id) and all(has.values()), f"row manager-run-{run_id}: {text[:200]!r}; cost {cost_text!r}; {has}"


def step_reload_mid_run(page, hub, state):
    before = last_firing_id(hub)
    started = time.time()
    start_check(hub, state["document"])
    page.wait_for_timeout(10000)
    if wait_for_firing(hub, state["document"], before, seconds=0.1):
        raise Unreached("the check ended before the reload, so nothing was in progress")
    go(page, hub)  # the reload: a fresh page load mid-run
    text = None
    end = time.time() + 5
    while time.time() < end and not (text or "").isdigit():
        text = count_text(page)
        page.wait_for_timeout(200)
    counted = text is not None and text.isdigit() and int(text) >= 1
    run = running_run_on(hub, state["document"], seconds=10)
    expect = hub_seconds(run["started_at"]) if run else time.time() - started
    popover = hover_indicator(page)
    row = page.get_by_test_id(f"manager-popover-run-{run['run_id']}") if run and popover is not None else None
    row_text = row.first.inner_text() if row is not None and row.count() else ""
    elapsed = seconds_in(row_text)
    close = elapsed is not None and abs(elapsed - expect) <= 5
    shot(page, "06-reload-mid-run")
    wait_for_firing(hub, state["document"], before)  # let it end before the failure steps
    ok = counted and bool(run) and close
    return ok, f"after reload count {text!r} (includes the run: {counted}); run {run and run.get('run_id')}; popover row {row_text[:120]!r} elapsed {elapsed}s vs {expect:.0f}s since start: {close}"


def fresh_failure(hub, document):
    """A failed check started while no page shows the spec; its firing."""
    hub.write_job_model(NO_SUCH_MODEL)
    before = last_firing_id(hub)
    start_check(hub, document)
    firing = wait_for_firing(hub, document, before, seconds=120)
    if firing is None:
        raise Unreached("the failing check did not end within 120s")
    if firing.get("outcome") != "failed":
        raise Unreached(f"the check with {NO_SUCH_MODEL} ended {firing.get('outcome')!r}, not failed")
    return firing


def step_failure(page, hub, state):
    go(page, hub)  # another page
    firing = fresh_failure(hub, state["document"])
    run_id = run_id_of(firing)
    go(page, hub)  # the reload
    open_warnings(page, hub, state["document"])
    failed = icon_state(page) == "failed"
    shot(page, "07a-failure")
    go(page, hub, tab="environment", section="manager")
    reason = page.get_by_test_id(f"manager-run-{run_id}-reason") if run_id else None
    reason_text = reason.first.inner_text().strip() if reason is not None and visible(page, f'[data-testid="manager-run-{run_id}-reason"]', 8000) else ""
    shot(page, "07b-failure-reason")
    ok = failed and bool(reason_text)
    return ok, f"run {run_id} failed ({firing.get('detail', '')[:100]!r}); icon after reload: {icon_state_text(failed)}; reason shown: {reason_text[:120]!r}"


def icon_state_text(failed):
    return "failed" if failed else "not failed"


def step_failure_seen_a(page, hub, state):
    go(page, hub)
    firing = fresh_failure(hub, state["document"])
    run_id = run_id_of(firing)
    open_warnings(page, hub, state["document"])
    first = icon_state(page)
    page.wait_for_timeout(2000)
    unseen = unseen_failures(hub)
    open_warnings(page, hub, state["document"])  # a reload
    after = icon_state(page)
    shot(page, "08-failure-seen-a")
    ok = first == "failed" and unseen is not None and run_id not in unseen and after in ("idle",)
    return ok, f"run {run_id}: icon on opening {first!r}, want failed; unseen failures after opening {unseen}; icon after reload {after!r}, want idle"


def step_failure_seen_b(page, hub, state):
    go(page, hub)
    firing = fresh_failure(hub, state["document"])
    run_id = run_id_of(firing)
    go(page, hub)
    popover = hover_indicator(page)
    listed = popover is not None and run_id is not None and visible(page, f'[data-testid="manager-popover-run-{run_id}"]', 5000)
    page.wait_for_timeout(2000)
    unseen = unseen_failures(hub)
    shot(page, "09a-failure-seen-b")
    go(page, hub)  # a reload
    open_warnings(page, hub, state["document"])
    after = icon_state(page)
    shot(page, "09b-failure-seen-b")
    ok = listed and unseen is not None and run_id not in unseen and after == "idle"
    return ok, f"run {run_id}: listed in the popover on hover: {listed}; unseen failures after hovering {unseen}; icon after reload {after!r}, want idle"


def step_failure_seen_c(page, hub, state):
    go(page, hub)
    fresh_failure(hub, state["document"])
    open_warnings(page, hub, state["document"])
    first = icon_state(page)
    press_check(page)
    ok_working, seen = wait_icon(page, "working", 5)
    shot(page, "10-failure-seen-c")
    straight = ok_working and "idle" not in seen[1:seen.index("working")]
    ok = first == "failed" and straight
    return ok, f"icon before Check now {first!r}, want failed; states after pressing {seen}, want working with no idle between"


STEPS = {
    "working-icon": step_working_icon,
    "indicator-count": step_indicator_count,
    "popover-running": step_popover_running,
    "ended": step_ended,
    "settings-log": step_settings_log,
    "reload-mid-run": step_reload_mid_run,
    "failure": step_failure,
    "failure-seen-a": step_failure_seen_a,
    "failure-seen-b": step_failure_seen_b,
    "failure-seen-c": step_failure_seen_c,
}
# The steps that watch the run `working-icon` started keep its page open between them.
SHARED_PAGE = {"working-icon", "indicator-count", "popover-running", "ended"}


# --------------------------------------------------------------------------- main


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--assert", dest="assert_", action="store_true", help="run the checks and exit 1 if any fails")
    parser.add_argument("--hub", default="http://127.0.0.1:8010", help="the trial Hub")
    parser.add_argument("--project", default="proj-d85a82bf4216")
    parser.add_argument("--document", default=DEFAULT_DOCUMENT, help="a spec with requirements")
    parser.add_argument("--key", default="", help="the Hub's key (default: the trial profile's bootstrap key)")
    parser.add_argument("--db", default="", help="the Hub's SQLite (default: the trial profile's)")
    parser.add_argument("--only", default="", help="comma-separated step keys")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument(
        "--ui",
        choices=("auto", "hub", "checkout"),
        default="auto",
        help="whose UI bundle the browser loads: the Hub's, this checkout's hub/hub/static/ui "
        "(served on the Hub's origin by request interception), or the checkout's only when the "
        "Hub serves none (auto)",
    )
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
    global UI_DIR
    if args.ui != "hub":
        try:
            with urllib.request.urlopen(hub.url + "/", timeout=10) as response:
                served = b"<html" in response.read(4096).lower()
        except urllib.error.HTTPError:
            served = False
        if args.ui == "checkout" or not served:
            UI_DIR = REPO / "hub" / "hub" / "static" / "ui"
            if not (UI_DIR / "index.html").is_file():
                sys.exit(f"no built UI at {UI_DIR}")
    try:
        with urllib.request.urlopen(hub.url + "/health", timeout=10) as response:
            health = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        health = "?"
    print(f"Hub {hub.url}: {health}; UI from {UI_DIR or 'the Hub'}", flush=True)

    try:
        state = seed(hub, args.document)
    except Setup as exc:
        for key_ in wanted:
            record(key_, False, False, f"setup failed: {exc}")
        return report(args.assert_)

    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not args.headed)
            shared = None
            try:
                for key_ in wanted:
                    if key_ in SHARED_PAGE:
                        shared = shared or new_page(browser, hub)
                        page = shared
                    else:
                        if shared is not None:
                            shared.context.close()
                            shared = state["page"] = None
                        page = new_page(browser, hub)
                    try:
                        ok, detail = STEPS[key_](page, hub, state)
                        record(key_, True, ok, detail)
                    except Unreached as exc:
                        record(key_, False, False, f"not reached: {exc}")
                    except Exception as exc:  # noqa: BLE001 -- a broken step must not hide the others
                        record(key_, False, False, f"not reached: {type(exc).__name__}: {str(exc)[:300]}")
                    finally:
                        if key_ not in SHARED_PAGE:
                            page.context.close()
                        if key_.startswith("failure"):
                            hub.write_job_model(HAIKU)
            finally:
                if shared is not None:
                    shared.context.close()
                browser.close()
    finally:
        restore(hub, state)
    return report(args.assert_)


def report(assert_):
    print()
    for key in ORDER:
        if key in checks:
            reached, failed, detail = checks[key]
            print(f"check {key}: reached={'yes' if reached else 'no'} failed_at_assertion={'yes' if reached and failed else 'no'} -- {detail}")
    failed = [k for k, (_r, f, _d) in checks.items() if f]
    print(f"\nscreenshots: {OUT}")
    print(f"{len(checks) - len(failed)} passed, {len(failed)} failed" + (f": {failed}" if failed else ""))
    return 1 if failed and assert_ else 0


if __name__ == "__main__":
    sys.exit(main())
