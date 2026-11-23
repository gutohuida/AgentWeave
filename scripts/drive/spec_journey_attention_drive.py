"""Acceptance drive for `the-spec-journey-spends-the-operator-s-attention-only-on-their-decisions`
(spdoc-e5c551ebc4ca), task SJSOS-1, 2026-11-22. Written before the build, failing on today's code.

Two of the document's criteria are checked here, each end to end through the Hub's routes:

  drive-pre-mortem-live (FR-11), phases 1 and 2:
    1. the Pre-mortem job is switched on with a Haiku runner, button only; the drive presses
       POST /manager/jobs/pre-mortem/run {"path": A} on a document holding requirements and
       criteria; within PM_WAIT exactly one firing for A with outcome `written` is listed by
       GET /manager/jobs/pre-mortem/pre-mortems?path=A, one manager_job_fired event names the job
       and A, and GET /agents/agent-context?spec_document=A holds `### Pre-mortem findings`;
    2. the job is set to automatic, a second large document B is moved from acceptance to approach,
       and exactly one written firing appears for B (trigger criteria_written), with its findings in
       B's briefing; A still has exactly one.
  drive-advances-unasked (FR-7), phase 3:
    3. a Haiku author on a large document C at requirements, holding drafted requirements, takes one
       turn that reviews them and asks what it must, then the operator answers in the same
       conversation without saying to continue; the document's step moves on by a `journey` event
       whose run is one of the author's, and neither reply contains 'Continue here' or 'fresh
       conversation'.

The Hub. By default the trial Hub on :8010 (key from ~/.agentweave/hub/profiles/trial/
bootstrap-key.txt), which must already be running the code under test: this drive cannot tell which
checkout serves it, so it says so and trusts it. `--own-hub PORT` instead starts a Hub from this
checkout's `hub/` on a fresh database under ~/.agentweave/hub/profiles/drive<PORT>/<stamp>/ and
stops it at the end; it refuses a port that already answers (F1121). Never :8000.

The project. Not proj-d85a82bf4216, whose working directory is the repository root: a real Haiku
author there would read and could write the operator's checkout. The drive opens a throwaway git
project under the main checkout's testbed/ (a project inside `.agentweave/tasks` is refused) on
whichever Hub it drives, with its own Haiku runner and its author agent.

The contract it fixes for the build (the document's design, Contract), in one place:
JOB, `run_pre_mortem` (POST body `{"path"}`, 202), `pre_mortems` (GET ?path=, `{"pre_mortems": [...]}`
newest first, each with `outcome`, `trigger`, `findings: [{story, requirement, cites}]`), the
firing's `subject.path`/`subject.document`, and HEADING in the briefing.

At the end it prints one `check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`
line per criterion, the drive_baseline evidence shape.

    py -3.11 scripts/drive/spec_journey_attention_drive.py                 # the trial Hub on :8010
    py -3.11 scripts/drive/spec_journey_attention_drive.py --own-hub 8021  # a fresh Hub from here
    py -3.11 scripts/drive/spec_journey_attention_drive.py --phases 1,2    # skip the author's turns
"""

import argparse
import json
import os
import pathlib
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
STAMP = time.strftime("%Y%m%d-%H%M%S")
TRIAL_PORT = 8010
TRIAL_KEY = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / "trial" / "bootstrap-key.txt"
HAIKU = "claude-haiku-5-5"
JOB = "pre-mortem"
HEADING = "### Pre-mortem findings"
AUTHOR = "Author"
DOC_A = "spec/changes/attention-drive-greeting/spec.json"
DOC_B = "spec/changes/attention-drive-farewell/spec.json"
DOC_C = "spec/changes/attention-drive-ping/spec.json"
PM_WAIT = 6 * 60
TURN_WAIT = 12 * 60
SETTLE = 30
ASKS_TO_CONTINUE = ("continue here", "fresh conversation")
TERMINAL = ("completed", "failed", "cancelled", "canceled", "error", "timed_out", "stopped")

HUB = ""
KEY = ""
ARTEFACTS = pathlib.Path()
results = []
criteria = {}  # key -> {"reached": bool, "failed_at_assertion": bool, "detail": str}


class Stop(Exception):
    """A failed check the rest of the phase depends on."""


def check(name, ok, detail="", fatal=False, quiet=False):
    if ok and quiet:
        return True
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def criterion(key, ok, detail):
    """The criterion's own assertion: reached, and failing (or passing) at it. The first failing
    assertion is the one reported; later ones only add to a passing criterion's detail."""
    row = criteria.setdefault(key, {"reached": True, "failed_at_assertion": False, "detail": ""})
    if not ok and not row["failed_at_assertion"]:
        row["failed_at_assertion"] = True
        row["detail"] = detail
    elif ok and not row["failed_at_assertion"]:
        row["detail"] = detail
    return check(f"{key}: {detail}", ok)


def not_reached(key, detail):
    criteria[key] = {"reached": False, "failed_at_assertion": False, "detail": detail}


def api(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
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


def q(path):
    return urllib.parse.quote(path, safe="")


def poll(fn, secs, every=3.0):
    end = time.time() + secs
    while time.time() < end:
        if fn():
            return True
        time.sleep(every)
    return bool(fn())


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def port_answers(port):
    with socket.socket() as sock:
        sock.settimeout(2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main_checkout():
    """The main checkout: this file may be running from a task checkout."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=REPO, check=True, capture_output=True, text=True).stdout.strip()
    return pathlib.Path(common).parent


# -- the Hub --------------------------------------------------------------------------------------

def start_own_hub(port):
    global HUB, KEY, ARTEFACTS
    if port in (8000, TRIAL_PORT):
        sys.exit(f"REFUSED: --own-hub starts a fresh Hub; {port} is the operator's or the trial one.")
    if port_answers(port):
        sys.exit(f"REFUSED: :{port} already answers, and it may be running another checkout's code "
                 "(F1121). Stop it first; --own-hub does not reuse a Hub.")
    HUB, KEY = f"http://127.0.0.1:{port}", "aw_live_" + secrets.token_hex(16)
    ARTEFACTS = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / f"drive{port}" / STAMP
    ARTEFACTS.mkdir(parents=True)
    db = ARTEFACTS / "agentweave.db"
    # The drive may run inside an agent turn on another Hub: its HUB_URL, credential and tool-server
    # bin would reach this Hub's agents, whose tool calls would then go to that other Hub.
    env = {k: v for k, v in os.environ.items() if k != "HUB_URL" and not k.startswith("AW_")}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if "tool-server" not in p.replace("\\", "/")
    )
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log_path = ARTEFACTS / "hub.log"
    log = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(port), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects", timeout=5)[0] == 200, 120, every=2):
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        sys.exit(f"setup error: the Hub did not come up; see {log_path}")
    print(f"started a Hub on :{port} from {REPO / 'hub'} on {db}", flush=True)
    return proc


def use_trial_hub():
    global HUB, KEY, ARTEFACTS
    HUB = f"http://127.0.0.1:{TRIAL_PORT}"
    if not TRIAL_KEY.exists():
        sys.exit(f"setup error: no trial key at {TRIAL_KEY}")
    KEY = TRIAL_KEY.read_text(encoding="utf-8").strip()
    ARTEFACTS = main_checkout() / "testbed" / "attention-drive" / STAMP / "artefacts"
    ARTEFACTS.mkdir(parents=True)
    code, out = api("GET", "/projects", timeout=10)
    if code != 200:
        sys.exit(f"setup error: the trial Hub on :{TRIAL_PORT} does not answer ({code} {str(out)[:200]}). "
                 "Start it from the branch under test (.claude/reference/hubs.md), or use --own-hub.")
    print(f"driving the trial Hub on :{TRIAL_PORT}; it must already run the code under test", flush=True)


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    print("stopped the drive's Hub", flush=True)


# -- documents ------------------------------------------------------------------------------------

def payload(title, problem, words, with_criteria=True):
    doc = {
        "schema_version": 1, "kind": "change-spec", "title": title,
        "summary": f"The service answers {', '.join(words)}.",
        "problem": problem,
        "scope": {"in_scope": [f"GET /{w}" for w in words], "non_goals": ["Anything else"]},
        "requirements": [
            {"key": w, "modal": "MUST",
             "statement": f"GET /{w} MUST answer 200 with the plain-text body `{w}`."}
            for w in words
        ],
    }
    if with_criteria:
        doc["acceptance_criteria"] = [{
            "key": f"answers-{w}", "requirement": w, "given": "the service running",
            "when": f"GET /{w} is requested", "then": f"it answers 200 with the body {w}",
            "how_to_check": f"curl -s localhost:8080/{w}", "checked_by": "agent"} for w in words]
    return doc


def make_document(base, path, title, content, size, step):
    code, out = api("POST", f"{base}/project/documents",
                    {"title": title, "kind": "change-spec", "path": path})
    check(f"setup: {path} is created", code == 201, f"{code} {str(out)[:300]}", fatal=True)
    code, out = api("PUT", f"{base}/project/documents/{path}/content", {"document": content})
    check(f"setup: {path} saves", code == 200, f"{code} {str(out)[:600]}", fatal=True)
    code, out = api("POST", f"{base}/project/documents/journey?path={q(path)}",
                    {"size": size, "step": step, "reason": "the attention drive's setup"})
    check(f"setup: {path} is {size}, at {step}", code == 200 and out.get("step") == step,
          f"{code} {str(out)[:300]}", fatal=True)
    return out


def document(base, path=None, doc_id=None):
    """The document as the app lists it, by path or, where the author may rename it, by id."""
    _, listed = api("GET", f"{base}/project/documents")
    docs = listed.get("documents", []) if isinstance(listed, dict) else []
    return next((d for d in docs if (d.get("id") == doc_id if doc_id else d.get("path") == path)), {})


def briefing(base, path):
    query = urllib.parse.urlencode({"agent": AUTHOR, "spec_document": path})
    code, body = api("GET", f"{base}/agents/agent-context?{query}")
    return body.get("context", "") if code == 200 and isinstance(body, dict) else f"{code} {body}"


# -- the pre-mortem's contract ---------------------------------------------------------------------

def run_pre_mortem(base, path):
    """The button's route. CONTRACT: body {"path"}, 202."""
    return api("POST", f"{base}/manager/jobs/{JOB}/run", {"path": path})


def pre_mortems(base, path):
    """The document's pre-mortems, newest first. CONTRACT."""
    code, out = api("GET", f"{base}/manager/jobs/{JOB}/pre-mortems?path={q(path)}")
    if code == 200 and isinstance(out, dict) and isinstance(out.get("pre_mortems"), list):
        return code, out["pre_mortems"]
    return code, out


def firings_for(base, path, doc_id):
    code, out = api("GET", f"{base}/manager/activity?job={JOB}")
    rows = out.get("firings", []) if code == 200 and isinstance(out, dict) else []
    return [f for f in rows if f.get("job") == JOB and (
        (f.get("subject") or {}).get("path") == path or (f.get("subject") or {}).get("document") == doc_id)]


def written(rows):
    return [r for r in rows if isinstance(r, dict) and r.get("outcome") == "written"]


def assert_one_firing(key, base, path, doc_id, label, trigger, wait):
    """Exactly one written firing of *path*, listed by the route, and its findings in the briefing."""
    poll(lambda: written(pre_mortems(base, path)[1] if pre_mortems(base, path)[0] == 200 else []),
         wait, every=5)
    time.sleep(SETTLE if wait else 0)
    code, listed = pre_mortems(base, path)
    (ARTEFACTS / f"pre_mortems_{label}.json").write_text(json.dumps(listed, indent=2), encoding="utf-8")
    ok = code == 200 and isinstance(listed, list)
    criterion(key, ok, f"{label}: GET /manager/jobs/{JOB}/pre-mortems answers a list "
                       f"({code} {str(listed)[:240] if not ok else len(listed)})")
    rows = listed if ok else []
    criterion(key, len(rows) == 1 and len(written(rows)) == 1,
              f"{label}: exactly one firing of the document, outcome written "
              f"({[(r.get('outcome'), r.get('detail')) for r in rows]})")
    if rows:
        criterion(key, rows[0].get("trigger") == trigger,
                  f"{label}: its trigger is {trigger} ({rows[0].get('trigger')!r})")
        findings = rows[0].get("findings") or []
        criterion(key, bool(findings) and all(f.get("story") for f in findings),
                  f"{label}: it holds findings, each with a story ({len(findings)})")
    fired = firings_for(base, path, doc_id)
    criterion(key, len(fired) == 1,
              f"{label}: one manager_job_fired event names the job and the document ({len(fired)})")
    text = briefing(base, path)
    (ARTEFACTS / f"briefing_{label}.md").write_text(text, encoding="utf-8")
    story = ((rows[0].get("findings") or [{}])[0].get("story") or "") if rows else ""
    criterion(key, HEADING in text and (not story or story[:60] in text),
              f"{label}: the document's next briefing holds '{HEADING}' and the latest findings "
              f"(heading={'yes' if HEADING in text else 'no'})")


# -- phases ---------------------------------------------------------------------------------------

def setup():
    root = main_checkout() / "testbed" / "attention-drive" / STAMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service with one route, GET /hello.\n", encoding="utf-8")
    (root / "app.py").write_text(
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n\n\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        if self.path == '/hello':\n"
        "            self.send_response(200)\n"
        "            self.end_headers()\n"
        "            self.wfile.write(b'hello')\n"
        "        else:\n"
        "            self.send_response(404)\n"
        "            self.end_headers()\n\n\n"
        "if __name__ == '__main__':\n"
        "    HTTPServer(('', 8080), Handler).serve_forever()\n", encoding="utf-8")
    git(root, "add", "README.md", "app.py")
    git(root, "commit", "-q", "-m", "seed")
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"attention-{STAMP}"})
    check("setup: the throwaway project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    api("PATCH", base, {"main_branch": "main"})
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    check("setup: a Haiku runner", code in (200, 201), f"{code} {runner}", fatal=True)
    code, out = api("POST", f"{base}/agents", {"name": AUTHOR, "runner_id": runner["id"]})
    check(f"setup: agent {AUTHOR} on the Haiku runner", code in (200, 201), f"{code} {out}", fatal=True)
    print(f"project {pid} at {root}", flush=True)
    return {"pid": pid, "base": base, "runner": runner["id"], "root": root}


def phase_1(state):
    key, base = "drive-pre-mortem-live", state["base"]
    code, out = api("GET", f"{base}/manager/jobs")
    listed = next((j for j in (out.get("jobs") or [])
                   if j.get("key") == JOB), None) if code == 200 and isinstance(out, dict) else None
    criterion(key, listed is not None, f"phase 1: GET /manager/jobs lists the {JOB} job "
                                       f"({code}, keys {[j.get('key') for j in (out or {}).get('jobs', [])]})"
              if isinstance(out, dict) else f"phase 1: GET /manager/jobs ({code})")
    code, out = api("PATCH", f"{base}/manager/jobs/{JOB}",
                    {"enabled": True, "runner_id": state["runner"], "model": HAIKU, "mode": "button"})
    state["job_on"] = code == 200 and isinstance(out, dict) and out.get("enabled") is True
    criterion(key, state["job_on"],
              f"phase 1: the job switches on with the Haiku runner, button only ({code} {str(out)[:240]})")

    make_document(base, DOC_A, "A greeting route",
                  payload("A greeting route", "The service greets only at /hello.", ["greet"]),
                  "large", "acceptance")
    state["doc_a"] = document(base, DOC_A).get("id")
    code, out = run_pre_mortem(base, DOC_A)
    pressed = code == 202
    criterion(key, pressed, f"phase 1: POST /manager/jobs/{JOB}/run {{path}} answers 202 "
                            f"({code} {str(out)[:240]})")
    assert_one_firing(key, base, DOC_A, state["doc_a"], "phase 1", "requested",
                      PM_WAIT if pressed else 0)


def phase_2(state):
    key, base = "drive-pre-mortem-live", state["base"]
    code, out = api("PATCH", f"{base}/manager/jobs/{JOB}", {"mode": "automatic"})
    automatic = code == 200 and isinstance(out, dict) and out.get("mode") == "automatic"
    criterion(key, automatic, f"phase 2: the job is set to automatic ({code} {str(out)[:240]})")
    make_document(base, DOC_B, "A farewell route",
                  payload("A farewell route", "The service cannot say goodbye.", ["bye"]),
                  "large", "acceptance")
    state["doc_b"] = document(base, DOC_B).get("id")
    code, out = api("POST", f"{base}/project/documents/journey?path={q(DOC_B)}",
                    {"step": "approach", "reason": "the attention drive: acceptance is written"})
    check("phase 2: the second document moves from acceptance to approach",
          code == 200 and isinstance(out, dict) and out.get("step") == "approach",
          f"{code} {str(out)[:300]}", fatal=True)
    # With no job on, nothing can fire: settle briefly rather than wait the whole firing budget.
    assert_one_firing(key, base, DOC_B, state["doc_b"], "phase 2", "criteria_written",
                      PM_WAIT if state.get("job_on") else SETTLE)
    code, listed = pre_mortems(base, DOC_A)
    if code == 200 and isinstance(listed, list):
        criterion(key, len(listed) == 1, f"phase 2: the first document still has one firing ({len(listed)})")


def chat(base, conv):
    code, out = api("GET", f"{base}/agent/{AUTHOR}/chat/{conv}")
    check("phase 3: the conversation's history reads", code == 200 and isinstance(out, dict),
          "" if code == 200 else f"{code} {str(out)[:300]}", fatal=True, quiet=True)
    return out


def turn(base, message, conv=None):
    """One turn of the author on C; waits for it to end. Returns (conversation id, run id, reply)."""
    body = {"agent": AUTHOR, "message": message, "spec_document": DOC_C,
            **({"conversation_id": conv} if conv else {})}
    code, out = api("POST", f"{base}/agent/trigger", body)
    check("phase 3: the author's turn starts", code in (200, 202), f"{code} {str(out)[:300]}", fatal=True)
    conv = out["conversation_id"]
    before = set(state_runs(base, conv))
    run_id = out.get("run_id")
    end = time.time() + TURN_WAIT
    answered = set()
    while time.time() < end:
        runs = state_runs(base, conv)
        if run_id is None:
            fresh = [r for r in runs if r not in before]
            run_id = fresh[0] if fresh else None
        # An exploring turn asks in its reply; if it calls ask_user anyway, answer without deciding
        # anything about continuing.
        _, pending = api("GET", f"{base}/questions?answered=false")
        for question in pending if isinstance(pending, list) else []:
            if question.get("agent") not in (None, AUTHOR) or question["id"] in answered:
                continue
            answered.add(question["id"])
            print(f"  ask_user: {question.get('question', '')[:160]!r}", flush=True)
            api("PATCH", f"{base}/questions/{question['id']}",
                {"answer": "No preference: decide it yourself.", "labels": []})
        if run_id and str(runs.get(run_id, {}).get("status", "")).lower() in TERMINAL:
            break
        time.sleep(5)
    status = state_runs(base, conv).get(run_id, {}).get("status") if run_id else None
    check("phase 3: the author's turn ends within its budget", str(status).lower() in TERMINAL,
          f"run {run_id} {status}", fatal=True)
    entries = chat(base, conv).get("entries") or []
    reply = "\n".join(e.get("content") or "" for e in entries
                      if e.get("kind") == "agent_output" and e.get("run_id") == run_id
                      and e.get("output_kind") == "text")
    return conv, run_id, reply


def state_runs(base, conv):
    return chat(base, conv).get("runs") or {}


def phase_3(state, db_events):
    key, base = "drive-advances-unasked", state["base"]
    make_document(base, DOC_C, "A ping route",
                  payload("A ping route", "Nothing tells an operator the service is up.", ["ping"],
                          with_criteria=False),
                  "large", "requirements")
    # An author may rename its document (the path follows its subject), so C is followed by id.
    placed = document(base, DOC_C)
    doc_id, before = placed.get("id"), placed.get("step")
    conv, first_run, first = turn(
        base, "The requirements for this document are drafted. Review them against the code and "
              "ask me whatever you need to settle them.")
    (ARTEFACTS / "phase3_reply_1.md").write_text(first, encoding="utf-8")
    print(f"  first reply ({first_run}): {first[:400]!r}", flush=True)
    conv, second_run, second = turn(
        base, "My answers: GET /ping answers 200 with the plain-text body `pong`, needs no "
              "authentication, and answers the same while the service is starting. Nobody else "
              "calls it but our uptime checker, every 30 seconds. It sends text/plain, matches "
              "the exact path only, and it stays a large change. Anything else you would "
              "have asked, decide yourself and write it down as an assumption.", conv)
    (ARTEFACTS / "phase3_reply_2.md").write_text(second, encoding="utf-8")
    print(f"  second reply ({second_run}): {second[:400]!r}", flush=True)

    now = document(base, doc_id=doc_id)
    after = now.get("step")
    criterion(key, after not in (None, before),
              f"phase 3: the document's step moved on from {before} (now {after}, at {now.get('path')})")
    moves = db_events(doc_id, {first_run, second_run})
    criterion(key, bool(moves), f"phase 3: an advance (a step event with no size change) moved it, "
                                f"its run the author's "
                                f"({moves or 'none by runs ' + str([first_run, second_run])})")
    for label, text in (("first", first), ("second", second)):
        hits = [p for p in ASKS_TO_CONTINUE if p in text.lower()]
        criterion(key, not hits, f"phase 3: the {label} reply asks nothing about continuing "
                                 f"(found {hits or 'none'})")


def journey_moves_via(db_path):
    """The document's advances by these runs. No route lists a document's events, so they
    are read from the Hub's database read-only; the step itself is read through the route."""
    import sqlite3

    def moves(doc_id, runs):
        if db_path is None or not db_path.exists():
            return []
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "select run_id, detail from spec_document_events where document_id = ? "
                "and kind = 'journey' order by created_at", (doc_id,)).fetchall()
        finally:
            con.close()
        # An advance records `{"step": ...}` alone (`advance_spec_step`, `set_step`); a size change
        # that re-places the step records `{"size": ..., "step": ...}` and is not an advance.
        found = []
        for run, detail in rows:
            detail = json.loads(detail) if isinstance(detail, str) else (detail or {})
            if run in runs and "step" in detail and "size" not in detail:
                found.append((run, detail["step"]))
        return found
    return moves


# -- main -----------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--own-hub", type=int, default=None,
                        help="start a fresh Hub from this checkout on this port instead of :8010")
    parser.add_argument("--phases", default="1,2,3")
    args = parser.parse_args()
    phases = {p.strip() for p in args.phases.split(",")}
    proc = None
    if args.own_hub:
        proc = start_own_hub(args.own_hub)
        db_path = ARTEFACTS / "agentweave.db"
    else:
        use_trial_hub()
        db_path = TRIAL_KEY.parent / "agentweave.db"
    try:
        state = setup()
        for number, key, fn in (("1", "drive-pre-mortem-live", phase_1),
                                ("2", "drive-pre-mortem-live", phase_2),
                                ("3", "drive-advances-unasked", None)):
            if number not in phases:
                continue
            try:
                if fn is None:
                    phase_3(state, journey_moves_via(db_path))
                else:
                    fn(state)
            except Stop as stop:
                if key not in criteria:
                    not_reached(key, f"phase {number} stopped at setup: {stop}")
    except Stop as stop:
        for key in ("drive-pre-mortem-live", "drive-advances-unasked"):
            criteria.setdefault(key, {"reached": False, "failed_at_assertion": False,
                                      "detail": f"setup stopped: {stop}"})
    finally:
        if proc is not None:
            stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {ARTEFACTS})")
    for name in bad:
        print("  FAILED:", name)
    print()
    for key, row in criteria.items():
        print(f"check {key}: reached={'yes' if row['reached'] else 'no'} "
              f"failed_at_assertion={'yes' if row['failed_at_assertion'] else 'no'} -- {row['detail']}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

# Observed on 4bb4542 (before the build), 2026-11-22, with --own-hub 8021 (artefacts
# drive8021/20261122-233949): 18 passed, 15 failed. drive-pre-mortem-live fails at its first
# assertion, the job not listed (and every pre-mortem route 404). drive-advances-unasked fails at the
# step: the Haiku author drafts, keeps the document at requirements, and ends "Do you want to continue
# this document here, continue it in a fresh conversation, or stop here?". An earlier run, before
# the answer said the size stays, passed the step check falsely through a size change re-placing the
# step; an advance is now an event with `step` and no `size`.
