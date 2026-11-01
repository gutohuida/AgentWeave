"""Acceptance drive for `a-finished-spec-gets-a-build-retrospective` (spdoc-89b0b4568f7f), 2026-11-01.

The document's `acceptance-drive` criterion, written before the build (task FSGBR-1). It starts its
own Hub on :8020 from this checkout's `hub/`, on a new database under
~/.agentweave/hub/profiles/drive8020/<stamp>/, and stops it at the end. If :8020 already answers it
refuses, because that Hub may be running another checkout's code (F1121). It never uses :8010 or
:8000. It does not import d1029_build_plan_in_spec, whose module level fixes :8010 and reads the
trial key.

The project is a new git repository under the main checkout's testbed/. Not this task's testbed/:
the Hub refuses to register a project inside `.agentweave/tasks` (project_workspace.py).

Haiku agents Builder and Checker build a two-task document as a flow at Reviewed, t2 after t1:

  1. the job is turned on with the Haiku runner;
  2. Builder really works t1, and the operator sends it back once, class defect;
  3. Builder really works it again, and the operator approves it: no retrospective may fire yet;
  4. Builder really works t2, and the operator approves it, the document's last task;
  5. within RETRO_WAIT, exactly one firing and one retrospective appear for the document, its
     send-backs name t1, its transcripts name the run the send-back ended, the project's vault gains
     one tracked source naming the document, and the spec page shows it.

The operator has to be the one approving, so Checker holds a seeded running run throughout, which
keeps the flow from giving it the check. That is the drive's only seeded row; the builder's runs,
the transitions, the approval and the firing are all real.

Written before the job, so three names here are the contract the build keeps or changes here, in one
place: JOB, `retrospectives()` (its route and shape), and the report's `send_backs[].task_id` and
`transcripts_read[].run_id`.

    py -3.11 scripts/drive/d1029_build_retrospective.py
"""

import datetime
import hashlib
import json
import os
import pathlib
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8020
HUB = f"http://127.0.0.1:{PORT}"
STAMP = time.strftime("%Y%m%d-%H%M%S")
PROFILE = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "drive8020" / STAMP
DB = PROFILE / "agentweave.db"
KEY = "aw_live_" + secrets.token_hex(16)
HAIKU = "claude-haiku-5-5"
JOB = "build-retrospective"
DOC = "spec/changes/hello-file/spec.json"
TITLE = "Hello file"
BUILDER, CHECKER = "Builder", "Checker"
TURN_WAIT = 10 * 60
RETRO_WAIT = 5 * 60
SETTLE = 20
SEND_BACK = "hello.txt needs a second line reading `world`. Add it and change nothing else."
DONE = ("completed", "under_review")
results = []


class Stop(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=False):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def api(method, path, body=None, timeout=240):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
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
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        return 0, str(exc)


def ro(sql, args=()):
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def rw(sql, args=()):
    con = sqlite3.connect(DB.as_posix(), timeout=30)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def poll(fn, secs, every=2.0):
    end = time.time() + secs
    while time.time() < end:
        if fn():
            return True
        time.sleep(every)
    return bool(fn())


def port_answers():
    with socket.socket() as sock:
        sock.settimeout(2)
        return sock.connect_ex(("127.0.0.1", PORT)) == 0


def testbed():
    """The main checkout's testbed/: this file may be running from a task checkout."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()
    return pathlib.Path(common).parent / "testbed" / "drive1029-retro" / STAMP


def start_hub(log_path):
    PROFILE.mkdir(parents=True)
    # The drive may run inside an agent turn on another Hub: its HUB_URL, credential and tool-server
    # bin would reach this Hub's agents, whose tool calls would then go to that other Hub.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/")
    )
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 120):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{PORT} from {REPO / 'hub'} on {DB}", flush=True)
    return proc


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")


def hold(pid, agent):
    """A running run of *agent*, so the flow hands it nothing. Its id starts `run-d1029r-`."""
    run_id = "run-d1029r-" + secrets.token_hex(4)
    token = "aw_run_" + secrets.token_urlsafe(24)
    rw("insert into runs (id, project_id, agent, status, started_at, initiator, turn_depth, "
       "capability_token_hash) values (?, ?, ?, 'running', ?, 'operator', 0, ?)",
       (run_id, pid, agent, _now(), hashlib.sha256(token.encode("utf-8")).hexdigest()))
    return run_id


def release(run_id):
    rw("update runs set status='completed', ended_at=? where id=?", (_now(), run_id))


def payload():
    def task(key, word, depends_on):
        return {
            "key": key, "title": f"Add {word}.txt",
            "description": (f"Create the file {word}.txt at the repository root holding the single "
                            f"line `{word}`. Change nothing else. Record evidence for the "
                            "requirement with record_evidence, then complete the task."),
            "requirements": [word], "files": [f"{word}.txt"], "depends_on": depends_on,
        }

    return {
        "schema_version": 1, "kind": "change-spec", "title": TITLE,
        "summary": "The repository says hello.", "problem": "The repository has no hello.txt.",
        "scope": {"in_scope": ["hello.txt", "bye.txt"], "non_goals": ["Anything else"]},
        "requirements": [
            {"key": word, "modal": "MUST", "statement": f"The repository MUST hold {word}.txt."}
            for word in ("hello", "bye")
        ],
        "acceptance_criteria": [{
            "key": f"says-{word}", "requirement": word, "given": "the repository checked out",
            "when": f"{word}.txt is read", "then": f"it reads {word}",
            "how_to_check": f"cat {word}.txt", "checked_by": "agent"} for word in ("hello", "bye")],
        "tasks": [task("t1", "hello", []), task("t2", "bye", ["t1"])],
        "delivery": {
            "mode": "flow", "agent": BUILDER, "stop_when_queue_empties": True,
            # Once a year: the drive fires the flow itself, so no firing races a step.
            "cron": "0 0 1 1 *",
            "reasons": {"mode": "The drive.", "agent": "The default builder."},
        },
    }


def status(task_id):
    return ro("select status from tasks where id=?", (task_id,))[0][0]


def live_runs(pid):
    return ro("select id, agent from runs where project_id=? and status in "
              "('running', 'queued', 'starting') and id not like 'run-d1029r-%'", (pid,))


def bound_runs(task_id, agent):
    return [r for (r,) in ro("select id from runs where task_id=? and agent=? order by started_at",
                             (task_id, agent))]


def work(base, pid, job_id, task_id, label):
    """Fire the flow until a real turn finishes *task_id*, re-firing only while nothing runs."""
    end = time.time() + TURN_WAIT
    fired = 0
    while time.time() < end and status(task_id) not in DONE:
        if not live_runs(pid):
            code, out = api("POST", f"{base}/jobs/{job_id}/run")
            fired += 1
            print(f"  fired {job_id} for {label}: {code} {str(out)[:160]}", flush=True)
        time.sleep(20)
    check(f"{label}: a real turn finishes the task", status(task_id) in DONE,
          f"{status(task_id)} after {fired} firing(s); runs {bound_runs(task_id, BUILDER)}", fatal=True)
    poll(lambda: not live_runs(pid), 180)


def approve(base, task_id, label):
    code, rows = api("GET", f"{base}/project/spec/evidence?review_state=awaiting")
    check(f"{label}: the awaiting evidence reads", code == 200, "" if code == 200 else str(rows)[:300],
          fatal=True)
    rows = rows.get("evidence", []) if isinstance(rows, dict) else rows
    for row in rows:
        decided, out = api("POST", f"{base}/project/spec/evidence/{row['id']}/decision",
                           {"decision": "accepted", "reason": "the drive's operator"})
        print(f"  evidence {row['id']} accepted: {decided} {'' if decided == 200 else str(out)[:200]}",
              flush=True)
    # The operator's approval: `land` releases the builder's hold and walks completed -> under_review
    # -> approved, each step a real transition.
    code, out = api("POST", f"{base}/tasks/{task_id}/land")
    check(f"{label}: the operator approves it", code == 200 and status(task_id) == "approved",
          f"{code} {status(task_id)} {'' if code == 200 else str(out)[:400]}", fatal=True)


def firings(base):
    code, out = api("GET", f"{base}/manager/activity?job={JOB}")
    return out.get("firings", []) if code == 200 and isinstance(out, dict) else []


def retrospectives(base):
    """The document's retrospectives, newest first, as its spec page reads them. CONTRACT."""
    quoted = urllib.parse.quote(DOC)
    code, out = api("GET", f"{base}/project/documents/retrospectives?path={quoted}")
    return code, (out.get("retrospectives", []) if code == 200 and isinstance(out, dict) else out)


def sources(base):
    code, out = api("GET", f"{base}/vault/map")
    check("the vault map answers", code == 200, "" if code == 200 else f"{code} {str(out)[:300]}",
          fatal=True)
    return {e["id"]: e for e in out["entries"] if e.get("kind") == "source"}


def spec_page_shows(base, pid, sent_back):
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    (readable,) = ro("select readable_id from tasks where id=?", (sent_back,))[0]
    quoted = urllib.parse.quote(DOC, safe="")
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 1000})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=spec&document={quoted}", wait_until="domcontentloaded")
        page.locator(".aw-sp-phase").first.wait_for(timeout=30000)
        page.wait_for_timeout(2500)
        text = page.locator("body").inner_text()
        page.screenshot(path=str(PROFILE / "spec_page.png"), full_page=True)
        browser.close()
    check("the spec page shows the retrospective, naming the sent-back task",
          "retrospective" in text.lower() and (sent_back in text or (readable or sent_back) in text),
          f"looked for {sent_back}/{readable}; screenshot {PROFILE / 'spec_page.png'}")


def drive(state):
    root = testbed() / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A throwaway project for the retrospective drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"retro-{STAMP}"})
    check("setup: the throwaway project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    state.update(base=base)
    print(f"project {pid} at {root}", flush=True)
    api("PATCH", base, {"main_branch": "main"})
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    check("setup: a Haiku runner", code in (200, 201), f"{code} {haiku}", fatal=True)
    for name in (BUILDER, CHECKER):
        code, out = api("POST", f"{base}/agents", {"name": name, "runner_id": haiku["id"]})
        check(f"setup: agent {name}", code in (200, 201), f"{code} {out}", fatal=True)

    # Not fatal: on a Hub without the job this fails, and the drive goes on to show nothing fires.
    code, out = api("PATCH", f"{base}/manager/jobs/{JOB}",
                    {"enabled": True, "runner_id": haiku["id"], "model": HAIKU})
    check("the build retrospective job turns on with the Haiku runner", code == 200,
          f"{code} {str(out)[:300]}")

    quoted = urllib.parse.quote(DOC)
    code, out = api("POST", f"{base}/project/documents",
                    {"title": TITLE, "kind": "change-spec", "path": DOC})
    check("setup: the document is created", code == 201, f"{code} {out}", fatal=True)
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload()})
    check("setup: the document saves", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    _, read = api("GET", f"{base}/project/spec?path={quoted}")
    code, out = api("POST", f"{base}/project/documents/phase?path={quoted}&to=approved",
                    {"reason": "drive", "approve_anyway": True,
                     "content_version": read.get("content_version")})
    check("setup: the document is approved", code == 200, f"{code} {str(out)[:600]}", fatal=True)

    state["hold"] = hold(pid, CHECKER)
    code, out = api("POST", f"{base}/project/documents/build?path={quoted}",
                    {"driver": "flow", "level": "reviewed", "builder": BUILDER, "checker": CHECKER,
                     "landing": "main"})
    check("setup: built as a flow at Reviewed", code == 200, f"{code} {str(out)[:800]}", fatal=True)
    state["build_id"] = ((out.get("build_outcome") or {}).get("build") or {}).get("id")
    (doc_id,) = ro("select id from spec_documents where project_id=? and path=?", (pid, DOC))[0]
    tasks = {k: (t, l) for t, l, k in ro(
        "select id, loop_id, spec_task_key from tasks where spec_document_id=?", (doc_id,))}
    t1, t2 = tasks["t1"][0], tasks["t2"][0]
    job_id = ro("select job_id from loops where id=?", (tasks["t1"][1],))[0][0]
    print(f"build {state['build_id']}, t1 {t1}, t2 {t2}, job {job_id}", flush=True)

    # The first task, sent back once.
    work(base, pid, job_id, t1, "t1, first turn")
    runs = bound_runs(t1, BUILDER)
    check("setup: t1 has a real run of Builder's to be sent back", bool(runs), str(runs), fatal=True)
    sent_back_run = runs[-1]
    code, out = api("PATCH", f"{base}/tasks/{t1}",
                    {"status": "revision_needed", "notes": SEND_BACK, "reason_class": "defect"})
    check("the operator sends t1 back once", code == 200, f"{code} {str(out)[:400]}", fatal=True)
    work(base, pid, job_id, t1, "t1, after the send-back")
    approve(base, t1, "t1")
    time.sleep(SETTLE)
    check("no retrospective fires while t2 is open", not firings(base), str(firings(base))[:300])

    # The last task.
    work(base, pid, job_id, t2, "t2")
    check("Checker was given no check, so the operator is the approver",
          not ro("select id from inbound_queue_entries where review_task_id in (?, ?) and agent=? "
                 "and delivered_at is not null",
                 (t1, t2, CHECKER)), "", fatal=True)
    before = sources(base)
    approve(base, t2, "t2, the document's last task")

    # What the job does. Everything above this line works on a Hub without the job.
    fired = poll(lambda: firings(base), RETRO_WAIT, every=5)
    check(f"a retrospective fires for real within {RETRO_WAIT}s of the last approval", fired,
          f"no manager_job_fired event for {JOB} in {base}/manager/activity", fatal=True)
    poll(lambda: retrospectives(base)[0] == 200 and retrospectives(base)[1], RETRO_WAIT, every=5)
    time.sleep(SETTLE)
    check("exactly one firing recorded", len(firings(base)) == 1, str(firings(base))[:600])
    code, listed = retrospectives(base)
    (PROFILE / "retrospectives.json").write_text(json.dumps(listed, indent=2), encoding="utf-8")
    check("exactly one retrospective of the document", code == 200 and len(listed) == 1,
          f"{code} {str(listed)[:600]}", fatal=True)
    report = listed[0].get("report") or {}
    backs = report.get("send_backs") or []
    check("its send-backs name the real sent-back task", any(b.get("task_id") == t1 for b in backs),
          f"wanted {t1}; {str(backs)[:600]}")
    read_runs = report.get("transcripts_read") or []
    check("its transcripts include the sent-back run",
          any(r.get("run_id") == sent_back_run for r in read_runs),
          f"wanted {sent_back_run}; {str(read_runs)[:600]}")

    after = sources(base)
    new = [after[i] for i in after if i not in before]
    check("the vault gains exactly one source", len(new) == 1, str(new)[:600], fatal=True)
    entry = new[0]
    check("it is tracked and dated", entry.get("visibility") == "tracked" and bool(entry.get("dated")),
          str({k: entry.get(k) for k in ("visibility", "dated")}))
    code, whole = api("GET", f"{base}/vault/entries/{entry['id']}")
    named = entry.get("name", "") + " " + (json.dumps(whole) if code == 200 else "")
    check("it names the document", DOC in named or TITLE in named, str(entry.get("name")))
    spec_page_shows(base, pid, t1)


def tidy(state, proc):
    if state.get("hold"):
        release(state["hold"])
    if state.get("build_id"):
        code, _ = api("POST", f"{state['base']}/project/builds/{state['build_id']}/stop")
        print(f"stopped build {state['build_id']}: {code}", flush=True)
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print(f"stopped the Hub on :{PORT}", flush=True)


def main():
    if port_answers():
        sys.exit(f"REFUSED: :{PORT} already answers, and it may be running another checkout's code "
                 "(F1121). Stop it first; this drive does not reuse a Hub.")
    proc = start_hub(pathlib.Path(os.environ.get("TEMP", ".")) / f"drive1029-retro-{STAMP}-hub.log")
    state = {}
    try:
        drive(state)
    except Stop:
        pass
    finally:
        tidy(state, proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {PROFILE})")
    for name in bad:
        print("  FAILED:", name)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on 6cee437 (before the job exists), 2026-11-01, on :8020 (artefacts
# drive8020/20261101-195501): 20 passed, 2 failed. All setup and the real flow held: Builder worked t1,
# the operator sent it back, Builder worked it again, both tasks landed. The two failures are the
# missing job: PATCH /manager/jobs/build-retrospective answers 404, and no manager_job_fired event
# appeared within 300s of the last approval. The checks after that one have not run yet.
