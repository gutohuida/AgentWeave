"""Acceptance drive for `the-build-plan-lives-in-the-spec-and-every-task-goes-to-its-people`, 2026-10-29.

The change's `ac-drive` criterion (spdoc-a7d41f10be14), written before the build (task
write-drive). It drives the trial Hub on :8010, reusing one that already answers there and
otherwise starting one from this checkout's `hub/` on the trial profile's database (never :8000).
It opens a scratch git repository as a new project with four Haiku-bound agents -- Builder (the
build-wide builders list), Outsider (t1's builder, outside that list), Checker (t1's checker) and
Architect (the agent that calls create_flow) -- and an approved one-task document. The operator
builds it as a flow at Reviewed, landing on main, with builders [Builder], through the route the
Build dialog calls. Its t2 is Builder's, checked by Outsider, so t1's builder is also named as a
checker elsewhere (F767). Then, in order:

  1. the spec document's file, and an agent's read_spec_document, carry the build labelled as the
     operator's (driver flow, level reviewed, Outsider and Checker for t1), and its delivery is
     unchanged (FR-4);
  2. fired while Outsider is busy (a seeded running run), the flow gives t1 to nobody; fired again
     once Outsider is free, it hands t1's work to Outsider and to nobody else (FR-8: staffing);
  3. while the build runs, an agent's create_flow on the document is refused with 409 naming the
     build and its driver, and t1's loop does not change (FR-7);
  4. Outsider completes t1;
  5. the next firing hands t1's check to Checker and to nobody else, never to Outsider (FR-9).

t1 names its checker as `reviewer`, the name today's payload accepts and that FR-2
(`old-names-still-build`) keeps building as the task's checker, so the document saves on master
and the drive fails at staffing rather than at validation.

The delivery's cron fires once a year, so the flow fires only when the drive fires it. Steps 1-3
spend no agent turn; a failure there is recorded and the drive continues, so one run on master
shows each failure. Steps 4-5 spend Haiku turns (t2's run alongside) and run only once t1 went
to Outsider. What master does is recorded at the end of this file. At the end it stops the build, archives any flow a step-3
acceptance created, and stops the Hub if it started one.

    py -3.11 scripts/drive/d1029_build_plan_in_spec.py

AW_DRIVE_DB names the database of an already-running :8010 when it is not the trial profile's.
"""

import datetime
import hashlib
import json
import os
import pathlib
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8010
HUB = f"http://127.0.0.1:{PORT}"
PROFILE = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial"
DB = pathlib.Path(os.environ.get("AW_DRIVE_DB") or PROFILE / "agentweave.db")
KEY = (PROFILE / "bootstrap-key.txt").read_text(encoding="utf-8").strip()
STAMP = time.strftime("%H%M%S")
# Outside the checkout: the Hub refuses to register a project nested in a task checkout.
TMP = pathlib.Path(tempfile.gettempdir()) / "drive1029-build-plan-in-spec" / STAMP
HAIKU = "claude-haiku-4-5-20251001"
DOC = "spec/changes/hello-file/spec.json"
BUILDER, OUTSIDER, CHECKER, ARCHITECT = "Builder", "Outsider", "Checker", "Architect"
AGENTS = (BUILDER, OUTSIDER, CHECKER, ARCHITECT)
FIRINGS = 4
TURN_WAIT = 10 * 60
DELIVERY = {
    "mode": "flow",
    "driver": "flow",
    "agent": BUILDER,
    "builders": [BUILDER],
    "level": "reviewed",
    "landing": "main",
    "stop_when_queue_empties": True,
    # Once a year: the drive fires the flow itself, so no firing races a step.
    "cron": "0 0 1 1 *",
    "reasons": {"mode": "One task.", "agent": "Builder is the default builder."},
}
BUILD = {"driver": "flow", "level": "reviewed", "builders": [BUILDER], "landing": "main"}
results = []


class Stop(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=False):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


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


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a row not yet written or a file mid-write
            pass
        time.sleep(every)
    return False


def start_hub():
    """The trial Hub: the one already on :8010, else one started from this checkout's hub/."""
    if api("GET", "/projects")[0] == 200:
        print(f"using the Hub already on :{PORT} (database assumed {DB})")
        return None
    TMP.mkdir(parents=True, exist_ok=True)
    # The drive may itself run inside an agent turn on the operator's Hub: its HUB_URL, run
    # credential and tool-server bin would be inherited by the trial agents' runs, which would
    # then send their tool calls to :8000. Hand the trial Hub none of them.
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
        sys.exit(f"the trial Hub did not come up; see {TMP / 'hub.log'}")
    print(f"started the trial Hub on :{PORT} from {REPO / 'hub'} on {DB}")
    return proc


def stop_hub(proc):
    if proc is not None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def hold(pid, agent):
    """A running run of `agent`, as the Hub tests seed one: the agent reads as busy, and the run's
    credential is returned. Every such run's id starts `run-d1029-`."""
    token = "aw_run_" + secrets.token_urlsafe(24)
    run_id = "run-d1029-" + secrets.token_hex(4)
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute(
            "insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
            "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
            (run_id, pid, agent, _now(), hashlib.sha256(token.encode("utf-8")).hexdigest()),
        )
        con.commit()
    finally:
        con.close()
    return run_id, token


def release(run_id):
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute("update runs set status='completed', ended_at=? where id=?", (_now(), run_id))
        con.commit()
    finally:
        con.close()


def as_agent(pid, agent, method, path, body=None):
    """One agent-plane call as `agent`, with a credential that lives for the call's span. The
    credential exists only in a spawned turn otherwise."""
    run_id, token = hold(pid, agent)
    try:
        return api(method, "/agent-actions" + path, body, key=token)
    finally:
        release(run_id)


def payload():
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Hello file",
        "summary": "The repository says hello.",
        "problem": "The repository has no hello.txt.",
        "scope": {"in_scope": ["hello.txt"], "non_goals": ["Anything else"]},
        "requirements": [
            {"key": word, "modal": "MUST",
             "statement": f"The repository MUST hold {word}.txt reading {word}."}
            for word in ("hello", "bye")
        ],
        "acceptance_criteria": [{
            "key": f"says-{word}", "requirement": word, "given": "the repository checked out",
            "when": f"{word}.txt is read", "then": f"it reads {word}",
            "how_to_check": f"cat {word}.txt", "checked_by": "agent"} for word in ("hello", "bye")],
        "tasks": [{
            "key": "t1", "title": "Add hello.txt",
            "description": ("Create the file hello.txt at the repository root holding the single "
                            "line `hello`. Change nothing else."),
            "requirements": ["hello"], "files": ["hello.txt"],
            # t1's builder is outside the build-wide builders list; its checker is named as
            # `reviewer`, which FR-2 keeps building as the task's checker.
            "builder": OUTSIDER, "reviewer": CHECKER,
        }, {
            "key": "t2", "title": "Add bye.txt",
            "description": ("Create the file bye.txt at the repository root holding the single "
                            "line `bye`. Change nothing else."),
            "requirements": ["bye"], "files": ["bye.txt"],
            # t1's builder checks t2: today's flow withholds fresh work from an agent the
            # document names to judge work (F767), which FR-8 says must not keep t1 from them.
            "builder": BUILDER, "reviewer": OUTSIDER,
        }],
        "delivery": DELIVERY,
    }


def find_build(value, outside="delivery"):
    """The first object outside `delivery` that reads as the operator's flow build at Reviewed."""
    if isinstance(value, dict):
        text = json.dumps(value).lower()
        if (value.get("driver") == "flow" and value.get("level") == "reviewed"
                and "operator" in text and OUTSIDER.lower() in text and CHECKER.lower() in text):
            return value
        for key, item in value.items():
            if key != outside:
                found = find_build(item, outside)
                if found is not None:
                    return found
    elif isinstance(value, list):
        for item in value:
            found = find_build(item, outside)
            if found is not None:
                return found
    return None


def runs_busy(pid):
    return ro("select id, agent from runs where project_id=? and status in "
              "('running', 'queued', 'starting') and id not like 'run-d1029-%'", (pid,))


def wait_idle(pid, secs=TURN_WAIT):
    time.sleep(3)
    return poll(lambda: not runs_busy(pid), secs, every=3)


def handouts(task_id, review):
    column = "review_task_id" if review else "task_id"
    extra = "" if review else " and review_task_id is null"
    return [a for (a,) in ro(f"select agent from inbound_queue_entries where {column}=?{extra} "
                             "order by sequence", (task_id,))]


def fire(base, job_id):
    code, out = api("POST", f"{base}/jobs/{job_id}/run")
    print(f"  fired {job_id}: {code} {str(out)[:200]}", flush=True)


def drive(state):
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the build-plan drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"buildplan-{STAMP}"})
    check("setup: the project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    print(f"project {pid} at {root}")
    api("PATCH", base, {"main_branch": "main"})
    code, out = api("PUT", f"{base}/settings", {"allow_agent_jobs": True})
    check("setup: agents may create jobs", code == 200, f"{code} {str(out)[:200]}", fatal=True)
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
    for name in AGENTS:
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    quoted = urllib.parse.quote(DOC)
    code, out = api("POST", f"{base}/project/documents",
                    {"title": "Hello file", "kind": "change-spec", "path": DOC})
    check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    check("setup: the document saves", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    version = read.get("content_version") if isinstance(read, dict) else None
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True, "content_version": version})
    check("setup: the document is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    delivery_before = json.loads((root / DOC).read_text(encoding="utf-8")).get("delivery")

    # The operator builds it, through the route the Build dialog calls.
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}", BUILD)
    check("setup: the operator builds it as a flow at Reviewed", code == 200,
          f"{code} {str(out)[:800]}", fatal=True)
    (TMP / "build_response.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (doc_id,) = ro("select id from spec_documents where project_id=? and path=?", (pid, DOC))[0]
    keyed = {key: (tid, loop) for tid, loop, key in ro(
        "select id, loop_id, spec_task_key from tasks where spec_document_id=?", (doc_id,))}
    (task_id, loop_id), (t2_id, _) = keyed["t1"], keyed["t2"]
    build_id = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    job_id = ro("select job_id from loops where id=?", (loop_id,))[0][0] if loop_id else None
    state.update(base=base, build_id=build_id, pid=pid)
    check("setup: the build runs a flow carrying t1", bool(build_id and job_id),
          f"build={build_id} t1={task_id} loop={loop_id} job={job_id}", fatal=True)
    print(f"build {build_id}, t1 {task_id}, loop {loop_id}, job {job_id}")

    # 1: the document carries the operator's choices; agents read them; delivery unchanged.
    on_file = json.loads((root / DOC).read_text(encoding="utf-8"))
    (TMP / "spec_after_build.json").write_text(json.dumps(on_file, indent=2), encoding="utf-8")
    found = find_build(on_file)
    check("1a the spec document's file carries the build, labelled the operator's",
          found is not None, json.dumps(found)[:400] if found else
          f"no object outside delivery reads flow/reviewed/operator/{OUTSIDER}/{CHECKER}; "
          f"top-level keys {sorted(on_file)}")
    check("1b its delivery is unchanged", on_file.get("delivery") == delivery_before,
          f"before={delivery_before} after={on_file.get('delivery')}")
    code, agent_read = as_agent(pid, ARCHITECT, "GET",
                                f"/spec/documents?path={quoted}&include=full")
    found = find_build(agent_read) if code == 200 else None
    written = pathlib.Path((agent_read or {}).get("written_to_absolute") or "")         if isinstance(agent_read, dict) else pathlib.Path()
    if found is None and written.is_file():
        # A read too large for one result lands in the agent's workspace as text.
        text = written.read_text(encoding="utf-8").lower()
        found = text if all(w in text for w in ("operator", "reviewed", OUTSIDER.lower(),
                                                 CHECKER.lower())) else None
    check("1c an agent's read_spec_document returns the build as the operator's, apart from "
          "delivery", found is not None, f"{code} {str(agent_read)[:400]}")
    _, page = api("GET", f"{base}/project/spec?path={quoted}")
    page_build = find_build({k: v for k, v in (page or {}).items() if k != "delivery"}
                            if isinstance(page, dict) else page)
    check("1d the spec page's read shows the build as the operator's, with t1's people",
          page_build is not None, str((page or {}).get("builds") if isinstance(page, dict)
                                      else page)[:400])

    # 2: the flow gives t1 to its builder -- outside the builders list, and t2's checker -- and to
    #    nobody else; while that builder is busy, t1 waits for them.
    busy, _ = hold(pid, OUTSIDER)
    try:
        fire(base, job_id)
        poll(lambda: handouts(t2_id, review=False) or handouts(task_id, review=False), 20)
        time.sleep(3)
        while_busy = handouts(task_id, review=False)
        check(f"2a while {OUTSIDER} is busy, the firing gives t1 to nobody", not while_busy,
              f"t1 handed to {while_busy}; t2 handed to {handouts(t2_id, review=False)}")
    finally:
        release(busy)
    for _ in range(FIRINGS):
        if handouts(task_id, review=False):
            break
        wait_idle(pid)
        fire(base, job_id)
        poll(lambda: handouts(task_id, review=False), 20)
    worked_by = handouts(task_id, review=False)
    staffed = check(f"2b once {OUTSIDER} is free, the flow hands t1's work to {OUTSIDER} and "
                    "nobody else",
                    worked_by and set(worked_by) == {OUTSIDER},
                    f"handed to {worked_by or 'nobody'} after up to {FIRINGS} firings; t1 is "
                    f"{ro('select status, assignee, blocked_reason from tasks where id=?', (task_id,))}")

    # 3: a second driver is refused while the build runs.
    (build_state,) = ro("select state from builds where id=?", (build_id,))[0]
    check("3a the build is still running when create_flow is called", build_state == "running",
          build_state)
    jobs_before = ro("select count(*) from ai_jobs where project_id=?", (pid,))[0][0]
    code, out = as_agent(pid, ARCHITECT, "POST", "/jobs", {
        "name": f"second-driver-{STAMP}", "agent": ARCHITECT, "message": "Work the document.",
        "cron": "*/5 * * * *", "purpose": "", "stop_at": None, "stop_when_queue_empties": True,
        "work_needs_evidence": None, "spec_document_id": doc_id, "initial_tasks": None,
    })
    if code in (200, 201) and isinstance(out, dict) and out.get("id"):
        state["stray_job"] = out["id"]
    text = json.dumps(out) if not isinstance(out, str) else out
    check("3b an agent's create_flow on the document is refused with 409, naming the build and "
          "its driver", code == 409 and build_id in text and "flow" in text,
          f"{code} {text[:500]}")
    jobs_after = ro("select count(*) from ai_jobs where project_id=?", (pid,))[0][0]
    (loop_now,) = ro("select loop_id from tasks where id=?", (task_id,))[0]
    check("3c no job is created and t1's loop is unchanged",
          jobs_after == jobs_before and loop_now == loop_id,
          f"jobs {jobs_before}->{jobs_after}; t1 loop {loop_id}->{loop_now}")

    if not staffed:
        print("  t1 never reached its builder: steps 4-5 need it, and are skipped")
        return
    # 4: Outsider works and completes t1.
    for _ in range(3):
        wait_idle(pid)
        (status,) = ro("select status from tasks where id=?", (task_id,))[0]
        if status in ("completed", "under_review", "approved"):
            break
        fire(base, job_id)
    worked = sorted(set(handouts(task_id, review=False)))
    (status,) = ro("select status from tasks where id=?", (task_id,))[0]
    check(f"4 {OUTSIDER} completes t1, and only {OUTSIDER} was given its work",
          status in ("completed", "under_review", "approved") and worked == [OUTSIDER],
          f"t1 is {status}; its work went to {worked}", fatal=True)

    # 5: the check goes to t1's checker, and never to its builder.
    for _ in range(FIRINGS):
        if handouts(task_id, review=True):
            break
        fire(base, job_id)
        poll(lambda: handouts(task_id, review=True), 20)
    checked_by = handouts(task_id, review=True)
    check(f"5a the flow hands t1's check to {CHECKER} and nobody else",
          checked_by and set(checked_by) == {CHECKER}, f"handed to {checked_by or 'nobody'}")
    wait_idle(pid)
    (status, assignee) = ro("select status, assignee from tasks where id=?", (task_id,))[0]
    check(f"5b {CHECKER}'s check ends with a verdict on t1", status in ("approved", "revision_needed",
                                                                       "rejected"),
          f"t1 is {status} ({assignee})", fatal=False)


def tidy(state):
    base = state.get("base")
    if not base:
        return
    if state.get("stray_job"):
        code, _ = api("POST", f"{base}/jobs/{state['stray_job']}/archive")
        print(f"archived the flow create_flow made: {code}")
    if state.get("build_id"):
        code, _ = api("POST", f"{base}/project/builds/{state['build_id']}/stop")
        print(f"stopped build {state['build_id']}: {code}")


def main():
    proc = start_hub()
    state = {}
    TMP.mkdir(parents=True, exist_ok=True)
    try:
        drive(state)
    except Stop:
        pass
    finally:
        try:
            tidy(state)
        finally:
            stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on master 86e9c76, 2026-10-29 (artefacts drive1029-build-plan-in-spec/164048): 20 passed,
# 4 failed. Fails at 1a, 1c and 1d: neither the document's file, nor an agent's read, nor the spec
# page's read carries the build as the operator's with t1's people (FR-4, FR-5). Fails at 3b:
# create_flow on a flow build is already refused with 409, but the refusal names the loop
# ("document ... is already claimed by loop ...") and not the build or its driver (FR-7); 3c passes.
# Steps 2, 4 and 5 pass on master: build start assigns t1 to Outsider (builds.cover_tasks), and the
# flow then waits for Outsider while they are busy, works t1 with them although they are outside
# builders and named to check t2, and sends t1's check to its own reviewer. So FR-8's and FR-9's
# staffing is not broken on master on this path, contrary to what the document expected.
