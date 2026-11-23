"""Acceptance drive for `the-spec-process-uses-what-the-hub-already-knows` (spdoc-f28755f7a656),
task SPUWH-1, 2026-11-23. Written before the build, failing on today's code at the cutover's binding.

Criterion drive-premortem-woven (FR-5, with FR-2, FR-3, FR-4, FR-6 and FR-7 on the way):

  1. write     A Haiku author, in a conversation bound to a large change document placed at its
               acceptance step, saves the document's requirements and criteria with
               submit_spec_document and moves it on. The side panel's Document tab shows it.
  2. fire      The pre-mortem job, on with automatic firing on the Haiku runner, fires exactly once
               for the document on leaving acceptance (trigger criteria_written, outcome written).
  3. cutover   The operator takes a checkpoint of the author's conversation and cuts it over. The
               successor is bound to the same document (GET /conversations/{id}/spec-documents),
               and a turn there is briefed with '### Pre-mortem findings' listing every finding.
               The operator's Check says ready false with a pre-mortem gap naming N unanswered,
               and the successor's side panel Document tab ends with the Pre-mortem, '0 of N
               answered'; the Builds tab holds no pre-mortem. <- today's build fails here, first at
               the binding.
  4. answer-1  The author, in the successor, answers finding 1 with a note and saves: the
               pre-mortems read carries finding 1's answer (note, by Author, at), the rest null;
               the save's ready_to_approve is false with the gap; the Check's gap says N-1
               unanswered; the briefing lists findings 2..N and not 1; the panel says '1 of N
               answered' and shows the note.
  5. answer-*  The author answers the rest at once with one note and saves: every finding answered,
               no gap in the save or the Check, no pre-mortem block in the briefing, the panel
               says 'N of N answered' and shows each note.
  6. again     The operator moves the document back to acceptance and forward again: no second
               pre-mortem fires (none listed, none running), and the panel still says N of N.

How the author answers is not fixed here: the turn is told to use the AgentWeave tool that answers
pre-mortem findings, as its briefing says (FR-3 "say how to answer them"). What is fixed, the
contract for the builders (hub/ui/src/api/manager.ts, the approved mock):
  - GET /manager/jobs/pre-mortem/pre-mortems?path= answers {"pre_mortems": [...]}, newest first,
    each finding carrying `answer`: {"note", "by", "at"} or null;
  - the gap is a warning (or refusal) of the Check and of the save whose `code` or `message` names
    the pre-mortem and whose message says '<n> unanswered';
  - the side panel's Document tab ends with a level-2 heading named 'Pre-mortem ...', its count
    '<a> of <n> answered', each answer's note and 'Answered by <author>'.

The Hub. Always a fresh one from this checkout's hub/, on its own database under
~/.agentweave/hub/profiles/drive<PORT>/<stamp>/, stopped at the end; a port that already answers is
refused (F1121), and so are :8000 (the operator's) and :8010 (the trial Hub). The project is a
throwaway git repository under ~/.agentweave/hub/premortem-drive/<stamp>/, with two profiles:
Author, whose pool holds Haiku (default) and Sonnet, and Reviewer on Haiku. Real agent turns run on
Haiku only; the checkpoint and the pre-mortem run on the Haiku runner too.

At the end it prints one `check <key>: reached=<yes|no> failed_at_assertion=<yes|no> -- <detail>`
line per criterion, the drive_baseline evidence shape, and exits 1 on any failure. About five
Haiku turns, a checkpoint and one or two pre-mortems; 15-30 minutes.

    py -3.11 scripts/drive/premortem_woven.py                  # :8037
    py -3.11 scripts/drive/premortem_woven.py --port 8041
    py -3.11 scripts/drive/premortem_woven.py --stop-after cutover   # the baseline: stop at step 3
"""

import argparse
import json
import os
import pathlib
import re
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
REFUSED_PORTS = (8000, 8010)
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
JOB = "pre-mortem"
HEADING = "### Pre-mortem findings"
AUTHOR, REVIEWER = "Author", "Reviewer"
# The path must not hold the word the gap matcher looks for.
DOC = "spec/changes/status-routes-drive/spec.json"
TITLE = "Status routes for the hello service"
KEY_CRITERION = "drive-premortem-woven"
NOTE_ONE = "PMDRIVE-NOTE-ONE: narrowed the requirement this finding names"
NOTE_REST = "PMDRIVE-NOTE-REST: accepted as a known limit of a three-route service"
PM_WAIT = 6 * 60
AGAIN_WAIT = 3 * 60
TURN_WAIT = 12 * 60
STEPS = ("write", "fire", "cutover", "answer-one", "answer-rest", "again")
TERMINAL = ("completed", "failed", "cancelled", "canceled", "error", "timed_out", "stopped")

HUB = ""
KEY = ""
ARTEFACTS = pathlib.Path()
results = []
criteria = {}  # key -> {"reached": bool, "failed_at_assertion": bool, "detail": str}


class StopError(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=False):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise StopError(name)
    return bool(ok)


def criterion(ok, detail):
    """The criterion's own assertion. The first failing one is the one reported."""
    row = criteria.setdefault(KEY_CRITERION, {"reached": True, "failed_at_assertion": False, "detail": ""})
    if not ok and not row["failed_at_assertion"]:
        row["failed_at_assertion"] = True
        row["detail"] = detail
    elif ok and not row["failed_at_assertion"]:
        row["detail"] = detail
    return check(f"{KEY_CRITERION}: {detail}", ok)


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


def save_artefact(name, value):
    text = value if isinstance(value, str) else json.dumps(value, indent=2, default=str)
    (ARTEFACTS / name).write_text(text, encoding="utf-8")


def git(root, *args):
    subprocess.run(["git", "-c", "user.email=d@example.invalid", "-c", "user.name=d", *args],
                   cwd=root, check=True, capture_output=True)


def port_answers(port):
    with socket.socket() as sock:
        sock.settimeout(2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


# -- the Hub --------------------------------------------------------------------------------------

def start_hub(port):
    global HUB, KEY, ARTEFACTS
    if port in REFUSED_PORTS:
        sys.exit(f"REFUSED: {port} is the operator's Hub or the trial Hub; this drive starts its own.")
    if port_answers(port):
        sys.exit(f"REFUSED: :{port} already answers, and it may be running another checkout's code "
                 "(F1121). StopError it first, or pick another --port.")
    HUB, KEY = f"http://127.0.0.1:{port}", "aw_live_" + secrets.token_hex(16)
    ARTEFACTS = pathlib.Path.home() / ".agentweave" / "hub" / "profiles" / f"drive{port}" / STAMP
    ARTEFACTS.mkdir(parents=True)
    db = ARTEFACTS / "agentweave.db"
    # The drive may run inside an agent turn on another Hub: that Hub's URL, credential and
    # tool-server bin must not reach this Hub's agents.
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
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                          capture_output=True, text=True).stdout.strip()
    print(f"started a Hub on :{port} from {REPO / 'hub'} at {head}, database {db}", flush=True)
    return proc


def stop_hub(proc, port):
    out = subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, text=True)
    if poll(lambda: not port_answers(port), 20, every=1):
        print("stopped the drive's Hub", flush=True)
    else:
        print(f"WARNING: :{port} still answers after taskkill of {proc.pid} "
              f"({(out.stdout + out.stderr).strip()[:300]}); stop it by hand", flush=True)


# -- the project ----------------------------------------------------------------------------------

def setup():
    root = pathlib.Path.home() / ".agentweave" / "hub" / "premortem-drive" / STAMP / "proj"
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
    code, project = api("POST", "/projects/open", {"path": str(root), "name": f"premortem-{STAMP}"})
    check("setup: the throwaway project opens", code in (200, 201), f"{code} {project}", fatal=True)
    pid = project["id"]
    base = f"/projects/{pid}"
    runners = {}
    for name, model in (("Haiku", HAIKU), ("Sonnet", SONNET)):
        code, runner = api("POST", f"{base}/runners", {"name": name, "cli": "claude", "model": model})
        check(f"setup: a {name} runner", code in (200, 201), f"{code} {runner}", fatal=True)
        runners[name] = runner["id"]
    for agent in (AUTHOR, REVIEWER):
        code, out = api("POST", f"{base}/agents", {"name": agent, "runner_id": runners["Haiku"]})
        check(f"setup: profile {agent} on the Haiku runner", code in (200, 201), f"{code} {out}", fatal=True)
    code, out = api("PATCH", f"{base}/agents/{AUTHOR}", {"pool": [
        {"runner_id": runners["Haiku"], "default": True}, {"runner_id": runners["Sonnet"]}]})
    check(f"setup: {AUTHOR}'s pool holds Haiku (default) and Sonnet", code == 200, f"{code} {str(out)[:300]}",
          fatal=True)
    _, agents = api("GET", f"{base}/agents")
    rows = agents if isinstance(agents, list) else (agents or {}).get("agents", [])
    pool = next((a.get("pool") for a in rows if isinstance(a, dict) and a.get("name") == AUTHOR), None)
    check(f"setup: {AUTHOR}'s pool reads back with two entries", isinstance(pool, list) and len(pool) == 2,
          str(pool)[:300])
    code, out = api("PUT", f"/projects/{pid}/settings", {
        "allow_agent_jobs": False, "main_branch": "main", "checkpoint_runner_id": runners["Haiku"], "checkpoint_model": HAIKU})
    check("setup: the checkpoint runner is the Haiku runner", code == 200, f"{code} {str(out)[:300]}",
          fatal=True)
    code, out = api("PATCH", f"{base}/manager/jobs/{JOB}",
                    {"enabled": True, "runner_id": runners["Haiku"], "model": HAIKU, "mode": "automatic"})
    check("setup: the pre-mortem job is on, automatic, on the Haiku runner",
          code == 200 and isinstance(out, dict) and out.get("enabled") is True and out.get("mode") == "automatic",
          f"{code} {str(out)[:300]}", fatal=True)
    code, out = api("POST", f"{base}/project/documents", {"title": TITLE, "kind": "change-spec", "path": DOC})
    check(f"setup: {DOC} is created", code == 201, f"{code} {str(out)[:300]}", fatal=True)
    code, out = api("POST", f"{base}/project/documents/journey?path={q(DOC)}",
                    {"size": "large", "step": "acceptance", "reason": "the pre-mortem drive's setup"})
    check("setup: the document is large, at acceptance", code == 200 and out.get("step") == "acceptance",
          f"{code} {str(out)[:300]}", fatal=True)
    print(f"project {pid} at {root}", flush=True)
    return {"pid": pid, "base": base, "root": root, "runners": runners, "doc_id": document(base).get("id")}


def payload():
    routes = {"ping": "pong", "version": "1.0.0", "health": "ok"}
    return {
        "schema_version": 1, "kind": "change-spec", "title": TITLE,
        "summary": "The hello service answers three status routes an uptime checker polls.",
        "problem": "Nothing tells an operator whether the hello service is up or which version runs.",
        "scope": {"in_scope": [f"GET /{r}" for r in routes], "non_goals": ["Authentication", "Metrics"]},
        "requirements": [
            {"key": r, "modal": "MUST",
             "statement": f"GET /{r} MUST answer 200 with the plain-text body `{body}`."}
            for r, body in routes.items()
        ],
        "acceptance_criteria": [
            {"key": f"answers-{r}", "requirement": r, "given": "the service running",
             "when": f"GET /{r} is requested", "then": f"it answers 200 with the body {body}",
             "how_to_check": f"curl -s localhost:8080/{r}", "checked_by": "agent"}
            for r, body in routes.items()
        ],
    }


def document(base):
    """The document as the app lists it, by path (the author is told not to rename it)."""
    _, listed = api("GET", f"{base}/project/documents")
    docs = listed.get("documents", []) if isinstance(listed, dict) else []
    return next((d for d in docs if d.get("path") == DOC), {})


# -- turns ----------------------------------------------------------------------------------------

def chat(base, conv):
    code, out = api("GET", f"{base}/agent/{AUTHOR}/chat/{conv}")
    return out if code == 200 and isinstance(out, dict) else {}


def wait_turn(base, conv, run_id=None, before=()):
    """Waits for the author's run in *conv* to end, answering any ask_user without deciding."""
    end = time.time() + TURN_WAIT
    answered = set()
    while time.time() < end:
        runs = chat(base, conv).get("runs") or {}
        if run_id is None:
            fresh = [r for r in runs if r not in before]
            run_id = fresh[0] if fresh else None
        _, pending = api("GET", f"{base}/questions?answered=false")
        for question in pending if isinstance(pending, list) else []:
            if question.get("agent") not in (None, AUTHOR) or question["id"] in answered:
                continue
            answered.add(question["id"])
            print(f"  ask_user: {question.get('question', '')[:160]!r}", flush=True)
            api("PATCH", f"{base}/questions/{question['id']}",
                {"answer": "No preference: decide it yourself and carry on.", "labels": []})
        if run_id and str(runs.get(run_id, {}).get("status", "")).lower() in TERMINAL:
            break
        time.sleep(5)
    status = (chat(base, conv).get("runs") or {}).get(run_id, {}).get("status") if run_id else None
    check(f"turn {run_id} in {conv} ends within its budget", str(status).lower() in TERMINAL,
          f"status {status}", fatal=True)
    entries = [e for e in chat(base, conv).get("entries") or [] if e.get("run_id") == run_id]
    return run_id, entries


def turn(base, message, conv=None, spec_document=None):
    """One turn of the author. A continued conversation is addressed by id alone, never with
    spec_document: binding it here would hide whether the cutover kept the document."""
    body = {"agent": AUTHOR, "message": message, **({"conversation_id": conv} if conv else {}),
            **({"spec_document": spec_document} if spec_document else {})}
    code, out = api("POST", f"{base}/agent/trigger", body)
    check("the author's turn starts", code in (200, 202), f"{code} {str(out)[:300]}", fatal=True)
    conv = out["conversation_id"]
    before = set(chat(base, conv).get("runs") or {})
    run_id, entries = wait_turn(base, conv, out.get("run_id"), before)
    return conv, run_id, entries


def save_verdict(entries):
    """The last submit_spec_document answer in the turn's transcript: (ready_to_approve, text)."""
    found = None
    for e in entries:
        text = str(e.get("content") or "") + " " + json.dumps(e.get("payload") or {}, default=str)
        match = re.search(r'\\?"ready_to_approve\\?"\s*:\s*(true|false)', text)
        if match:
            found = (match.group(1) == "true", text)
    return found


# -- the pre-mortem, the gap, the briefing --------------------------------------------------------

def pre_mortems(base):
    code, out = api("GET", f"{base}/manager/jobs/{JOB}/pre-mortems?path={q(DOC)}")
    if code == 200 and isinstance(out, dict) and isinstance(out.get("pre_mortems"), list):
        return out["pre_mortems"]
    return []


def running_pre_mortems(base, doc_id):
    _, out = api("GET", f"{base}/manager/runs/running")
    rows = out if isinstance(out, list) else (out or {}).get("runs", []) if isinstance(out, dict) else []
    return [r for r in rows if isinstance(r, dict) and r.get("job") == JOB
            and (DOC in json.dumps(r, default=str) or (doc_id and doc_id in json.dumps(r, default=str)))]


def pm_gap(findings):
    """The gap that names the pre-mortem and how many of its findings are unanswered."""
    for f in findings or []:
        text = f"{f.get('code', '')} {f.get('message', '')}".replace(DOC, "").lower()
        if re.search(r"pre[-_ ]?mortem", text) and "unanswered" in text:
            return f
    return None


def check_document(base):
    code, out = api("POST", f"{base}/project/documents/check?path={q(DOC)}")
    if code != 200 or not isinstance(out, dict):
        return None, None, f"{code} {str(out)[:300]}"
    gap = pm_gap((out.get("blocking") or []) + (out.get("warnings") or []))
    return out.get("ready"), gap, out


def briefing(base, spec_document):
    query = {"agent": AUTHOR, **({"spec_document": spec_document} if spec_document else {})}
    code, body = api("GET", f"{base}/agents/agent-context?{urllib.parse.urlencode(query)}")
    return body.get("context", "") if code == 200 and isinstance(body, dict) else f"{code} {body}"


def attached(base, conv):
    code, out = api("GET", f"{base}/conversations/{conv}/spec-documents")
    return ((out or {}).get("attached") or {}).get("path") if code == 200 and isinstance(out, dict) else None


def snippet(story):
    return " ".join((story or "").split())[:50]


def assert_briefing(label, text, findings):
    """The block lists exactly the unanswered findings, each by its story."""
    save_artefact(f"briefing_{label}.md", text)
    flat = " ".join(text.split())
    open_ = [f for f in findings if not f.get("answer")]
    done = [f for f in findings if f.get("answer")]
    if not open_:
        criterion(HEADING not in text, f"{label}: every finding answered, the briefing carries no "
                                       f"'{HEADING}' block")
        return
    criterion(HEADING in text, f"{label}: the continued conversation's briefing holds '{HEADING}'")
    missing = [i for i, f in enumerate(findings, 1) if not f.get("answer") and snippet(f.get("story")) not in flat]
    criterion(not missing, f"{label}: it lists each unanswered finding's story (missing {missing or 'none'})")
    if done:
        listed = [i for i, f in enumerate(findings, 1) if f.get("answer") and snippet(f.get("story")) in flat]
        criterion(not listed, f"{label}: it does not list an answered finding again (listed {listed or 'none'})")


# -- the side panel, in Chromium ------------------------------------------------------------------

_playwright = None


def chromium():
    """One Playwright for the whole drive: a second sync_playwright() in one process fails on this
    machine ('Connection closed while reading from the driver', 2026-11-23)."""
    global _playwright
    if _playwright is None:
        from playwright.sync_api import sync_playwright

        _playwright = sync_playwright().start()
    return _playwright.chromium

def panel(state, conv, label):
    """Opens *conv* in the app, its side panel's Document tab, reads the document's end and the
    Builds tab. Elements by accessible name; the counts are read, the caller asserts."""
    seen = {"document": False, "title": False, "heading": None, "last_section": None,
            "notes": {}, "answered_by": 0, "in_builds": None, "error": None}
    browser = chromium().launch()
    try:
        page = browser.new_context(viewport={"width": 1600, "height": 1000}).new_page()
        page.goto(f"{HUB}/?project={state['pid']}&agent={AUTHOR}&conversation={conv}")
        page.wait_for_selector("[data-testid=conversation-header]", timeout=30000)
        page.wait_for_timeout(2500)
        pane = page.get_by_test_id("document-pane")
        if not pane.count():
            # No document of its own opened it: the panel's shortcut (the toggle's title names it)
            # shows the panel anyway, to see what it holds.
            page.keyboard.press("Control+Alt+B")
            page.wait_for_timeout(1500)
        document_tab = pane.get_by_role("radio", name=re.compile(r"^Document"))
        seen["document"] = pane.count() > 0 and document_tab.count() > 0
        if seen["document"]:
            document_tab.first.click()
            page.wait_for_timeout(1500)
            seen["title"] = pane.get_by_text(TITLE).count() > 0
            heading = pane.get_by_role("heading", name=re.compile(r"^Pre-mortem"))
            if heading.count():
                heading.first.scroll_into_view_if_needed()
                seen["heading"] = " ".join(heading.first.inner_text().split())
            seen["last_section"] = pane.evaluate(
                "el => { const s = [...el.querySelectorAll('.aw-sp-content section')]"
                ".filter(x => x.offsetParent !== null); const h = s.length ? s[s.length - 1]"
                ".querySelector('h2') : null; return h ? h.textContent.trim() : null }")
            for note in (NOTE_ONE, NOTE_REST):
                seen["notes"][note] = pane.get_by_text(note).count()
            seen["answered_by"] = pane.get_by_text(re.compile(rf"Answered by {AUTHOR}")).count()
            page.screenshot(path=str(ARTEFACTS / f"panel_{label}_document.png"), full_page=True)
            builds_tab = pane.get_by_role("radio", name=re.compile(r"^Builds"))
            if builds_tab.count():
                builds_tab.first.click()
                page.wait_for_timeout(1200)
                seen["in_builds"] = pane.get_by_role("heading", name=re.compile(r"^Pre-mortem")).count()
        else:
            page.screenshot(path=str(ARTEFACTS / f"panel_{label}_none.png"), full_page=True)
    except Exception as exc:  # noqa: BLE001 -- a browser failure is reported as the check's detail
        seen["error"] = f"{type(exc).__name__}: {exc}"[:300]
    finally:
        browser.close()
    save_artefact(f"panel_{label}.json", seen)
    return seen


def assert_panel(state, conv, label, findings):
    seen = panel(state, conv, label)
    total = len(findings)
    answered = sum(1 for f in findings if f.get("answer"))
    criterion(seen["document"] and seen["title"],
              f"{label}: the conversation's side panel opens the document on its Document tab "
              f"(tab={seen['document']}, title={seen['title']}{', ' + seen['error'] if seen['error'] else ''})")
    count = f"{answered} of {total} answered"
    criterion(bool(seen["heading"]) and count in seen["heading"],
              f"{label}: the Document tab holds the Pre-mortem heading saying '{count}' ({seen['heading']!r})")
    criterion(bool(seen["last_section"]) and seen["last_section"].startswith("Pre-mortem"),
              f"{label}: the Pre-mortem is the Document tab's last section ({seen['last_section']!r})")
    criterion(seen["in_builds"] == 0, f"{label}: the Builds tab shows no pre-mortem ({seen['in_builds']})")
    if answered:
        want_rest = sum(1 for f in findings if f.get("answer") and NOTE_REST in (f["answer"].get("note") or ""))
        criterion(seen["notes"].get(NOTE_ONE, 0) >= 1 and seen["notes"].get(NOTE_REST, 0) >= want_rest
                  and seen["answered_by"] >= answered,
                  f"{label}: each answer's note and 'Answered by {AUTHOR}' show "
                  f"(notes {seen['notes']}, answered-by {seen['answered_by']}, want {answered})")


# -- steps ----------------------------------------------------------------------------------------

def step_write(state):
    base = state["base"]
    message = (
        "Write this change document's requirements and acceptance criteria now. Call "
        f"submit_spec_document for path {DOC} with exactly this content (title {TITLE!r}, kind "
        "change-spec), and do not rename the document:\n\n"
        f"```json\n{json.dumps(payload(), indent=2)}\n```\n\n"
        "Then call advance_spec_step once for the same path, to leave the acceptance step. Do not "
        "ask me anything; reply with one line saying what the save answered.")
    conv, run_id, entries = turn(base, message, spec_document=DOC)
    state["conv"] = conv
    save_artefact("turn_write.json", entries)
    doc = document(base)
    try:
        saved = json.loads((state["root"] / DOC).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    check("write: the author's save landed (three requirements and their criteria on disk)",
          len(saved.get("requirements") or []) >= 3 and len(saved.get("acceptance_criteria") or []) >= 3,
          f"{len(saved.get('requirements') or [])} requirements, step {doc.get('step')}")
    if doc.get("step") == "acceptance":
        # The author did not move it: the operator does, so the drive still leaves acceptance once.
        code, out = api("POST", f"{base}/project/documents/journey?path={q(DOC)}",
                        {"step": "approach", "reason": "the drive: the author did not advance"})
        check("write: the author did not advance; the operator moves acceptance -> approach",
              code == 200, f"{code} {str(out)[:200]}")
    check("write: the document has left acceptance", document(base).get("step") not in (None, "acceptance"),
          str(document(base).get("step")))
    seen = panel(state, conv, "write")
    check("write: the author's side panel opens the document on its Document tab",
          seen["document"] and seen["title"], json.dumps(seen)[:300])


def step_fire(state):
    base = state["base"]
    poll(lambda: any(p.get("outcome") for p in pre_mortems(base))
         and not running_pre_mortems(base, state["doc_id"]), PM_WAIT, every=5)
    time.sleep(20)
    rows = pre_mortems(base)
    save_artefact("pre_mortems_fire.json", rows)
    criterion(len(rows) == 1 and rows[0].get("outcome") == "written",
              f"fire: exactly one pre-mortem on leaving acceptance, written "
              f"({[(r.get('outcome'), r.get('trigger'), r.get('detail')) for r in rows]})")
    if rows:
        criterion(rows[0].get("trigger") == "criteria_written",
                  f"fire: its trigger is criteria_written ({rows[0].get('trigger')!r})")
    findings = (rows[0].get("findings") if rows else None) or []
    check("fire: it wrote at least two findings, so one can be answered and then the rest",
          len(findings) >= 2, f"{len(findings)} findings", fatal=not findings)
    state["findings"] = findings


def step_cutover(state):
    base = state["base"]
    code, cp = api("POST", f"{base}/conversations/{state['conv']}/checkpoint", timeout=600)
    check("cutover: a checkpoint of the author's conversation is written",
          code == 201 and isinstance(cp, dict) and cp.get("status") == "ready",
          f"{code} {str(cp)[:300]}", fatal=True)
    code, out = api("POST", f"{base}/checkpoints/{cp['id']}/cutover")
    check("cutover: the conversation is cut over", code == 200 and isinstance(out, dict),
          f"{code} {str(out)[:300]}", fatal=True)
    successor = out["successor_conversation_id"]
    state["successor"] = successor
    bound = attached(base, successor)
    criterion(bound == DOC, f"cutover: the successor {successor} is bound to the document "
                            f"(attached {bound!r}, want {DOC!r})")
    code, out = api("POST", f"{base}/conversations/{successor}/continue")
    check("cutover: the successor's first turn starts from its checkpoint",
          code == 200 and isinstance(out, dict), f"{code} {str(out)[:300]}")
    wait_turn(base, successor)
    rows = pre_mortems(base)
    findings = (rows[0].get("findings") or []) if rows else state["findings"]
    assert_briefing("cutover", briefing(base, attached(base, successor)), findings)
    ready, gap, out = check_document(base)
    save_artefact("check_cutover.json", out)
    state["gap_seen"] = gap is not None
    total = len(findings)
    criterion(ready is False and gap is not None and f"{total} unanswered" in (gap or {}).get("message", ""),
              f"cutover: the Check says ready false with the pre-mortem gap, {total} unanswered "
              f"(ready={ready}, gap={gap})")
    assert_panel(state, successor, "cutover", findings)


def step_answer_one(state):
    base, successor = state["base"], state["successor"]
    _, _, entries = turn(base, (
        "Answer pre-mortem finding 1 of this document, on its newest pre-mortem, with exactly this "
        f"note: {NOTE_ONE!r}. Use the AgentWeave tool that answers pre-mortem findings, as your "
        "briefing says. Answer only finding 1. Then save the document once, unchanged, with "
        "submit_spec_document, and reply with what the save answered for ready_to_approve and its "
        "warnings."), conv=successor)
    save_artefact("turn_answer_one.json", entries)
    rows = pre_mortems(base)
    findings = (rows[0].get("findings") if rows else None) or []
    save_artefact("pre_mortems_answer_one.json", rows)
    first = (findings[0].get("answer") if findings else None) or {}
    criterion(NOTE_ONE in (first.get("note") or "") and first.get("by") == AUTHOR and bool(first.get("at")),
              f"answer-one: finding 1 carries the note, {AUTHOR} and a time ({first or None})")
    others = [i for i, f in enumerate(findings[1:], 2) if f.get("answer")]
    criterion(not others, f"answer-one: no other finding is answered ({others or 'none'})")
    verdict = save_verdict(entries)
    criterion(verdict is not None and verdict[0] is False and bool(re.search(r"pre[-_ ]?mortem", verdict[1].replace(DOC, ""), re.I)),
              f"answer-one: the author's save says ready_to_approve false with the pre-mortem gap "
              f"({'no save in the transcript' if verdict is None else verdict[0]})")
    open_ = sum(1 for f in findings if not f.get("answer"))
    ready, gap, out = check_document(base)
    save_artefact("check_answer_one.json", out)
    state["gap_seen"] = state.get("gap_seen") or gap is not None
    criterion(ready is False and gap is not None and f"{open_} unanswered" in (gap or {}).get("message", ""),
              f"answer-one: the Check's gap says {open_} unanswered (ready={ready}, gap={gap})")
    assert_briefing("answer-one", briefing(base, attached(base, successor)), findings)
    assert_panel(state, successor, "answer-one", findings)


def step_answer_rest(state):
    base, successor = state["base"], state["successor"]
    _, _, entries = turn(base, (
        "Answer all the remaining unanswered findings of this document's newest pre-mortem at once, "
        f"with exactly this one note: {NOTE_REST!r}. Use the AgentWeave tool that answers pre-mortem "
        "findings. Then save the document once, unchanged, with submit_spec_document, and reply with "
        "what the save answered for ready_to_approve and its warnings."), conv=successor)
    save_artefact("turn_answer_rest.json", entries)
    rows = pre_mortems(base)
    findings = (rows[0].get("findings") if rows else None) or []
    save_artefact("pre_mortems_answer_rest.json", rows)
    rest = [i for i, f in enumerate(findings[1:], 2)
            if NOTE_REST not in ((f.get("answer") or {}).get("note") or "") or (f.get("answer") or {}).get("by") != AUTHOR]
    criterion(bool(findings) and not rest, f"answer-rest: findings 2..{len(findings)} carry the shared note "
                                           f"by {AUTHOR} (not: {rest or 'none'})")
    verdict = save_verdict(entries)
    criterion(verdict is not None and not re.search(r"pre[-_ ]?mortem[^\"]{0,80}unanswered",
                                                    verdict[1].replace(DOC, ""), re.I),
              f"answer-rest: the author's save carries no pre-mortem gap "
              f"({'no save in the transcript' if verdict is None else 'ready_to_approve=' + str(verdict[0])})")
    ready, gap, out = check_document(base)
    save_artefact("check_answer_rest.json", out)
    # Gone, not absent: a Check that never reported the gap would pass this vacuously.
    criterion(gap is None and state.get("gap_seen"),
              f"answer-rest: the Check's pre-mortem gap, reported before, is gone "
              f"(gap={gap}, seen before={bool(state.get('gap_seen'))}, ready={ready})")
    assert_briefing("answer-rest", briefing(base, attached(base, successor)), findings)
    assert_panel(state, successor, "answer-rest", findings)
    state["findings"] = findings


def step_again(state):
    base = state["base"]
    for step in ("acceptance", "approach"):
        code, out = api("POST", f"{base}/project/documents/journey?path={q(DOC)}",
                        {"step": step, "reason": "the drive: back to acceptance and forward again"})
        check(f"again: the operator moves the document to {step}",
              code == 200 and isinstance(out, dict) and out.get("step") == step, f"{code} {str(out)[:200]}")
    fired = poll(lambda: len(pre_mortems(base)) > 1 or bool(running_pre_mortems(base, state["doc_id"])),
                 AGAIN_WAIT, every=5)
    rows = pre_mortems(base)
    save_artefact("pre_mortems_again.json", rows)
    criterion(not fired and len(rows) == 1,
              f"again: going back and forward fires no second pre-mortem ({len(rows)} listed, "
              f"running {len(running_pre_mortems(base, state['doc_id']))})")
    assert_panel(state, state["successor"], "again", (rows[0].get("findings") if rows else None) or [])


# -- main -----------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8037)
    parser.add_argument("--stop-after", choices=STEPS, default=STEPS[-1],
                        help="stop after this step (the baseline on today's code stops after cutover)")
    args = parser.parse_args()
    proc = start_hub(args.port)
    try:
        state = setup()
        for name, fn in zip(STEPS, (step_write, step_fire, step_cutover, step_answer_one,
                                    step_answer_rest, step_again), strict=True):
            print(f"\n== {name} ==", flush=True)
            fn(state)
            if name == args.stop_after:
                break
    except StopError as stop:
        criteria.setdefault(KEY_CRITERION, {"reached": False, "failed_at_assertion": False,
                                            "detail": f"stopped before the criterion: {stop}"})
        if criteria[KEY_CRITERION]["reached"] and not criteria[KEY_CRITERION]["failed_at_assertion"]:
            criteria[KEY_CRITERION]["detail"] += f"; then stopped: {stop}"
    finally:
        if _playwright is not None:
            _playwright.stop()
        stop_hub(proc, args.port)
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

# Observed on ebe51f1 (before the build), 2026-11-23, --port 8037 --stop-after cutover (artefacts
# drive8037/20261123-232803): 23 passed, 8 failed. The pre-mortem fires once on leaving acceptance
# (criteria_written, five findings); the criterion fails first at the cutover's binding: the
# successor's spec-documents read answers attached null, so its briefing has no pre-mortem block, the
# Check names no pre-mortem gap and the successor's side panel opens no document. A full run the same
# evening (drive8037/20261123-232129) got to the end: the author, unbound, said it had no answer
# tool and no document path, and going back to acceptance and forward started a second pre-mortem.
