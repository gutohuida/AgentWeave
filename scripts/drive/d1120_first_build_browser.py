"""First-build drive for `profiles-threads-and-builds-everywhere` (spdoc-02cb5580092b), 2026-11-20.

Criterion `first-build-drive` (FR-9): on a freshly created project, the operator uses the setup
offer to create a builder and a checker profile, submits and approves a one-task document, presses
Build choosing the two new profiles, and the build runs to its end on real Haiku turns -- the
builder builds the task, the checker checks it, the task is approved, the build finishes -- without
the drive ever opening profile creation.

The Hub. It starts its own Hub from this checkout's `hub/` on a fresh database on a scratch port
(:8138; never :8000 or :8010, and it refuses to run if the port answers), with no `HUB_URL`, `AW_*`
variable or tool-server on PATH inherited from the turn that runs it (they would send the trial
agents' tool calls to the operator's Hub). The project is a scratch git repository under the main
checkout's `testbed/` (the Hub refuses a project nested in a task checkout).

What is done how:
  - the project is opened and its Haiku runner made through the routes (a runner is not a profile,
    and the setup offer needs one to choose);
  - the setup offer is used in the browser: Overview -> "Add a builder and a checker" ->
    "Add both..." -> names Builder and Checker, the Haiku runner for each, no charter -> Create both;
  - the document is submitted and approved through the operator's routes; its criterion is
    confirmed as an agent (the Checker), since approval refuses unconfirmed criteria and only an
    agent may confirm them;
  - Build is pressed in the browser on the spec page, choosing Builder as default builder and
    Checker as default checker, at Reviewed, landing on main;
  - the build's flow is fired by hand (its cron is yearly, so nothing races a step) until its loop
    ends.

"Never opened profile creation" is read two ways for the whole browser session: no
POST /projects/{pid}/agents request was sent, and the profile-creation dialog
(`aria-labelledby="agent-create-title"`) never appeared.

Checks, printed in the `drive_baseline` shape
    check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>
  first-build-drive   the setup offer created Builder and Checker; the build was started with them;
                      Builder built the task, Checker reviewed it, the task is approved, its work is
                      on main, the build is finished; profile creation was never opened.

Screenshots (dark and light) of the offer, the Build dialog and the finished build go to
testbed/ui-judge/d1120-first-build/<HHMMSS>/. Exits 1 if the check failed. Takes 5-20 minutes.

    py -3.11 scripts/drive/d1120_first_build_browser.py
    py -3.11 scripts/drive/d1120_first_build_browser.py --keep   # leave the Hub up
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from uiharness import Judge  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8138
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
HAIKU = "claude-haiku-4-5-20251001"
DOC = "spec/changes/hello-file/spec.json"
TITLE = "Hello file"
TASK_TITLE = "Add hello.txt"
BUILDER, CHECKER = "Builder", "Checker"
LIMIT = 25 * 60
KEY_CHECK = "first-build-drive"


def _testbed():
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=REPO, capture_output=True, text=True).stdout.strip()
    return (pathlib.Path(common).parent if common else REPO) / "testbed"


TMP = _testbed() / "drive1120-first-build" / STAMP
DB = TMP / "hub.db"
problems: list[str] = []
steps: list[str] = []


class SetupError(Exception):
    """The scenario could not be built: the drive says nothing about the product."""


def need(ok, what, detail=""):
    if not ok:
        raise SetupError(f"{what}: {detail}")


def step(ok, what, detail=""):
    """One observation the check rests on; a false one is a failure of the product."""
    line = f"{'ok  ' if ok else 'FAIL'} {what}" + (f" -- {detail}" if detail else "")
    print(line, flush=True)
    (steps if ok else problems).append(what + (f" ({detail})" if detail and not ok else ""))
    return ok


# ── The Hub ─────────────────────────────────────────────────────────────────────────────────────


def api(method, path, body=None, timeout=60, key=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + (key or KEY), "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:4000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text
    except urllib.error.URLError as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a row not yet written, a locator mid-render
            pass
        time.sleep(every)
    return False


def start_hub():
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"refusing to run: something already answers on :{PORT}")
    TMP.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/")
    )
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 120):
        proc.kill()
        sys.exit(f"the Hub did not come up; see {TMP / 'hub.log'}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def git(root, *args):
    return subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout


def as_agent(pid, agent, method, path, body=None):
    """One agent-plane call as *agent*, through a run credential that lives for the call: a run
    row seeded as the Hub tests seed one, completed straight after."""
    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = "run-d1120fb-" + secrets.token_hex(4)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    con.execute(
        "insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
        "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
        (run_id, pid, agent, now, hashlib.sha256(token.encode()).hexdigest()))
    con.commit()
    try:
        return api(method, "/agent-actions" + path, body, key=token)
    finally:
        con.execute("update runs set status='completed', ended_at=? where id=?", (now, run_id))
        con.commit()
        con.close()


def runs_busy(pid):
    return ro("select id, agent from runs where project_id=? and status in "
              "('running', 'queued', 'starting') and id not like 'run-d1120fb-%'", (pid,))


def handouts(task_id, review):
    column = "review_task_id" if review else "task_id"
    extra = "" if review else " and review_task_id is null"
    return [a for (a,) in ro(f"select agent from inbound_queue_entries where {column}=?{extra} "
                             "order by sequence", (task_id,))]


# ── The scenario ────────────────────────────────────────────────────────────────────────────────


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": TITLE,
        "summary": "The repository says hello.",
        "problem": "The repository has no hello.txt.",
        "scope": {"in_scope": ["hello.txt"], "non_goals": ["Anything else"]},
        "requirements": [{"key": "hello", "modal": "MUST",
                          "statement": "The repository MUST hold hello.txt reading hello."}],
        "acceptance_criteria": [{
            "key": "says-hello", "requirement": "hello", "given": "the repository checked out",
            "when": "hello.txt is read", "then": "it reads hello", "how_to_check": "cat hello.txt",
            "checked_by": "agent"}],
        "tasks": [{
            "key": "t1", "title": TASK_TITLE,
            "description": ("Create the file hello.txt at the repository root holding the single "
                            "line `hello`. Change nothing else. Record evidence for the "
                            "requirement with the file's content, then move this task to "
                            "completed."),
            "requirements": ["hello"], "files": ["hello.txt"],
        }],
        # Names no checker, so the dialog's checker is the drive's choice, not a prefill.
        "delivery": {"mode": "flow", "agent": BUILDER, "stop_when_queue_empties": True,
                     "cron": "0 0 1 1 *",
                     "reasons": {"mode": "The drive.", "agent": "The drive."}},
    }


def open_project():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the first-build drive.\n",
                                    encoding="utf-8")
    (root / ".gitignore").write_text(".agentweave/\n", encoding="utf-8")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"first-{STAMP}"})
    need(code in (200, 201), "the project opens", f"{code} {project}")
    pid = project["id"]
    api("PATCH", f"/projects/{pid}", {"main_branch": "main"})
    code, runner = api("POST", f"/projects/{pid}/runners",
                       {"name": "Haiku", "cli": "claude", "model": HAIKU})
    need(code in (200, 201), "a Haiku runner", f"{code} {runner}")
    code, agents = api("GET", f"/projects/{pid}/agents")
    rows = agents if isinstance(agents, list) else (agents or {}).get("agents", [])
    need(not [a for a in rows if a.get("name") not in ("mender",)], "a fresh project has no profile",
         str([a.get("name") for a in rows]))
    return pid, root


def watch(page, pid, seen):
    """Note every sign of profile creation for the page's whole life."""
    agents_path = f"/api/v1/projects/{pid}/agents"

    def on_request(request):
        if request.method == "POST" and urllib.parse.urlsplit(request.url).path == agents_path:
            seen["agent_posts"].append(request.url)
        if "/project/documents/build" in request.url and request.method == "POST":
            seen["build_bodies"].append(request.post_data)

    page.on("request", on_request)


def creation_dialog_open(page):
    return page.locator('[aria-labelledby="agent-create-title"]').count() > 0


def choose(page, trigger, option):
    trigger.click()
    # An option's accessible name may carry its detail after the label ("Builder Haiku ...").
    item = page.get_by_role("menuitemradio", name=re.compile(rf"^{re.escape(option)}\b"))
    if not poll(lambda: item.count() > 0, 10):
        offered = page.get_by_role("menuitemradio").evaluate_all(
            "els => els.map(e => e.textContent)")
        raise SetupError(f"the option {option!r}: not offered; offered {offered}")
    item.first.click()
    page.wait_for_timeout(200)


def use_setup_offer(judge, pid, seen):
    page = judge.page(project=pid, mode="dark", query="tab=overview")
    watch(page, pid, seen)
    item = page.locator('[data-testid="setup-item-profiles"]')
    if not step(poll(lambda: item.count() == 1, 30), "the setup list offers a builder and a checker"):
        return page
    judge.shot(page, "offer_1440_dark", locator=page.locator('[data-testid="setup-list"]'))
    item.get_by_role("button", name=re.compile(r"^Add both")).click()
    dialog = page.get_by_role("dialog", name="Add a builder and a checker")
    if not step(poll(lambda: dialog.count() == 1, 10), "Add both opens the offer's dialog"):
        return page
    page.locator("#setup-profiles-builder-name").fill(BUILDER)
    page.locator("#setup-profiles-checker-name").fill(CHECKER)
    choose(page, page.locator('[data-testid="setup-profiles-builder-runner"]'), "Haiku")
    choose(page, page.locator('[data-testid="setup-profiles-checker-runner"]'), "Haiku")
    judge.shot(page, "offer_dialog_1440_dark")
    seen["dialog_seen"] = seen["dialog_seen"] or creation_dialog_open(page)
    page.get_by_role("button", name="Create both").click()
    created = poll(lambda: {a["name"] for a in _agents(pid)} >= {BUILDER, CHECKER}, 20)
    step(created, "Create both made Builder and Checker",
         str(sorted(a["name"] for a in _agents(pid))))
    gone = poll(lambda: item.count() == 0, 15)
    step(gone, "the offer is gone once used")
    seen["dialog_seen"] = seen["dialog_seen"] or creation_dialog_open(page)
    return page


def _agents(pid):
    _, out = api("GET", f"/projects/{pid}/agents")
    rows = out if isinstance(out, list) else (out or {}).get("agents", [])
    return [a for a in rows if a.get("name") != "mender"]


def submit_and_approve(pid):
    base = f"/projects/{pid}"
    quoted = urllib.parse.quote(DOC, safe="")
    code, out = api("POST", f"{base}/project/documents",
                    {"title": TITLE, "kind": "change-spec", "path": DOC})
    need(code == 201, "the document is created", f"{code} {out}")
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    need(code == 200, "the document is submitted", f"{code} {str(out)[:600]}")
    code, out = as_agent(pid, CHECKER, "POST", "/spec/documents/confirm-criteria",
                         {"path": DOC, "confirmations": [{"criterion": "says-hello",
                                                          "kind": "new"}]})
    need(code == 200, "the criterion is confirmed", f"{code} {str(out)[:400]}")
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "the first-build drive", "approve_anyway": True,
                     "content_version": read.get("content_version")})
    step(code == 200, "the document is approved", "" if code == 200 else f"{code} {str(out)[:600]}")
    return code == 200


def press_build(judge, page, pid, seen):
    quoted = urllib.parse.quote(DOC, safe="")
    page.goto(f"{HUB}/?project={pid}&tab=spec&document={quoted}", wait_until="domcontentloaded")
    button = page.get_by_role("button", name="Build…")
    if not step(poll(lambda: button.count() > 0, 30), "the approved document offers Build…"):
        return False
    button.first.click()
    dialog = page.get_by_role("dialog")
    need(poll(lambda: dialog.get_by_test_id("build-confirm").count() == 1, 15), "the Build dialog")
    choose(page, dialog.get_by_role("button", name="Default builder", exact=True), BUILDER)
    choose(page, dialog.get_by_role("button", name="Default checker", exact=True), CHECKER)
    for label in ("Reviewed", "The main branch"):
        option = dialog.get_by_role("radio", name=label, exact=True)
        if option.count():
            option.first.click()
    judge.shot(page, "build_dialog_1440_dark")
    seen["dialog_seen"] = seen["dialog_seen"] or creation_dialog_open(page)
    dialog.get_by_test_id("build-confirm").click()
    started = poll(lambda: _build(pid) is not None, 20)
    step(started, "Build started a build")
    if seen["build_bodies"]:
        body = json.loads(seen["build_bodies"][-1] or "{}")
        step(body.get("builder") == BUILDER and body.get("checker") == CHECKER,
             "the build was asked for with Builder building and Checker checking",
             json.dumps({k: body.get(k) for k in ("builder", "checker", "level", "landing")}))
    else:
        step(False, "the Build request was seen", "no POST /project/documents/build")
    return started


def _build(pid):
    rows = ro("select id, state, loop_id from builds where project_id=?", (pid,))
    return rows[0] if rows else None


def run_build(pid, root):
    base = f"/projects/{pid}"
    build_id, _, loop = _build(pid)
    ((own,),) = ro("select id from tasks where build_id=?", (build_id,))
    job = ro("select job_id from loops where id=?", (loop,))[0][0]
    print(f"build {build_id} task {own} loop {loop} job {job}", flush=True)
    start = time.time()
    while time.time() - start < LIMIT:
        code, out = api("POST", f"{base}/jobs/{job}/run")
        print(f"  fired: {code} {str(out)[:160]}", flush=True)
        time.sleep(3)
        poll(lambda: not runs_busy(pid), 10 * 60, every=3)
        status = ro("select status, assignee from tasks where id=?", (own,))[0]
        state = ro("select state from builds where id=?", (build_id,))[0][0]
        ended = ro("select ending_state from loops where id=?", (loop,))[0][0]
        print(f"  {int(time.time() - start)}s task {status} build {state} loop {ended}", flush=True)
        if state != "running" or ended:
            # The loop's end is what stops the build; give it a moment to settle.
            poll(lambda: ro("select state from builds where id=?", (build_id,))[0][0] != "running",
                 30)
            break
        time.sleep(5)
    status = ro("select status from tasks where id=?", (own,))[0][0]
    state = ro("select state from builds where id=?", (build_id,))[0][0]
    builders = handouts(own, review=False)
    checkers = handouts(own, review=True)
    step(BUILDER in builders and CHECKER not in builders, "Builder built the task",
         f"build hand-outs {builders}")
    step(checkers[:1] == [CHECKER] and BUILDER not in checkers, "Checker checked it",
         f"review hand-outs {checkers}")
    ran = {a for (a,) in ro("select distinct agent from runs where project_id=? and "
                            "id not like 'run-d1120fb-%'", (pid,))}
    step({BUILDER, CHECKER} <= ran, "both profiles ran real turns", str(sorted(ran)))
    step(status == "approved", "the task is approved", status)
    on_main = subprocess.run(["git", "show", "main:hello.txt"], cwd=root, capture_output=True,
                             text=True).stdout
    step("hello" in on_main, "its work is on main", repr(on_main[:80]))
    step(state == "finished", "the build finished", state)
    return build_id


def drive():
    seen = {"agent_posts": [], "build_bodies": [], "dialog_seen": False}
    proc = start_hub()
    try:
        pid, root = open_project()
        print(f"project {pid} at {root}", flush=True)
        with Judge("d1120-first-build", hub=HUB, key=KEY) as judge:
            page = use_setup_offer(judge, pid, seen)
            if not problems:
                if submit_and_approve(pid) and press_build(judge, page, pid, seen):
                    build_id = run_build(pid, root)
                    for mode in ("dark", "light"):
                        shot = judge.page(project=pid, mode=mode,
                                          query=f"tab=spec&view=build&focus={build_id}")
                        watch(shot, pid, seen)
                        shot.wait_for_timeout(4000)
                        judge.shot(shot, f"finished_build_1440_{mode}")
                        shot.context.close()
            step(not seen["agent_posts"], "profile creation was never used",
                 str(seen["agent_posts"]))
            step(not seen["dialog_seen"], "the profile-creation dialog never opened")
            if judge.errors:
                print(f"note: {len(judge.errors)} console/page error(s) seen; listed below",
                      flush=True)
        return True, ""
    except SetupError as exc:
        print(f"SETUP {exc}", flush=True)
        return False, f"not reached: {exc}"
    finally:
        if ARGS.keep:
            print(f"Hub left up on {HUB} (key {KEY}); stop pid {proc.pid}")
        else:
            stop_hub(proc)


def main():
    global ARGS
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="leave the scratch Hub running")
    ARGS = parser.parse_args()
    reached, why = drive()
    detail = why or ("; ".join(problems) if problems else "; ".join(steps))
    failed = reached and bool(problems)
    print()
    print(f"check {KEY_CHECK}: reached={'yes' if reached else 'no'} "
          f"failed_at_assertion={'yes' if failed else 'no'} -- {detail}")
    return 0 if reached and not problems else 1


ARGS = argparse.Namespace(keep=False)

if __name__ == "__main__":
    sys.exit(main())
