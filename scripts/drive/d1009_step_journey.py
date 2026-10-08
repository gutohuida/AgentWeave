"""Acceptance drive for `a-spec-is-written-one-step-at-a-time` (step-journey, slice 1), 2026-10-08.

The slice's `drive` criterion. Starts its own Hub on :8098 with a fresh database (never :8000 or
:8010), serving the bundle built into hub/hub/static/ui, opens a project with one Haiku agent and a
new change document, and checks, in order:

  1. the document starts at step intake with no size;
  2. GET /agents/agent-context?spec_document= holds intake's duty marker and the journey line, and no
     other step's duty (acceptance's in particular);
  3. a real turn asked for a /ping route asks one question per ask_user; the drive answers "small"
     to sizing and "continue in a fresh conversation" to the step question;
  4. after that turn the document records size small and step requirements-and-acceptance;
  5. the preview now holds that step's duty and not intake's;
  6. a turn in a new conversation writes requirements, each MUST with a criterion;
  7. in Chromium, the phase bar shows the small journey with requirements-and-acceptance current.

The contract it fixes for the build: each step's duty carries the marker `[step: <name>]`; the
briefing carries one line beginning `- Journey` naming the steps in order; the document view
(GET /project/documents) carries `step` and `size`; the bar renders
`[data-testid=spec-journey]` with one `[data-testid=spec-journey-step-<name>]` per step, the current
one `aria-current="step"`.

Fails on the tree before the build at check 1 (no step). Stops at the first failure, so a red run
spends no agent turn. Run from anywhere:

    py -3.11 scripts/drive/d1009_step_journey.py
"""

import json
import os
import pathlib
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
from playwright.sync_api import sync_playwright  # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8098
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1009-journey" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
DOC = "spec/changes/ping-route/spec.html"
AGENT = "scribe"
STEPS = ("intake", "requirements", "acceptance", "approach", "tasks", "delivery",
         "requirements-and-acceptance")
SMALL = ["intake", "requirements-and-acceptance", "tasks", "delivery"]
LARGE = ["intake", "requirements", "acceptance", "approach", "tasks", "delivery"]
results = []


class Stop(Exception):
    """A failed check the rest of the drive depends on."""


def check(name, ok, detail="", fatal=True):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)
    if not ok and fatal:
        raise Stop(name)
    return bool(ok)


def api(method, path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        HUB + "/api/v1" + path, data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:2000]
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


def poll(fn, secs=15.0):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render; try again
            pass
        time.sleep(0.25)
    return False


def start_hub():
    TMP.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
    env["AW_BOOTSTRAP_API_KEY"] = KEY
    log = open(TMP / "hub.log", "w", encoding="utf-8")  # noqa: SIM115 -- the child's stdout
    proc = subprocess.Popen(
        ["py", "-3.11", "-m", "uvicorn", "hub.main:app", "--port", str(PORT), "--host", "127.0.0.1"],
        cwd=str(REPO / "hub"), env=env, stdout=log, stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    if not poll(lambda: api("GET", "/projects")[0] == 200, 90):
        proc.kill()
        sys.exit(f"hub did not come up; see {TMP / 'hub.log'}")
    return proc


def stop_hub(proc):
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def main():
    proc = start_hub()
    try:
        drive()
    except Stop:
        pass
    finally:
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


def document(base):
    _, listed = api("GET", f"{base}/project/documents")
    return next((d for d in listed.get("documents", []) if d.get("path") == DOC), {})


def preview(base):
    query = urllib.parse.urlencode({"agent": AGENT, "spec_document": DOC})
    code, body = api("GET", f"{base}/agents/agent-context?{query}")
    return body.get("context", "") if code == 200 and isinstance(body, dict) else f"{code} {body}"


def markers(text):
    return [step for step in STEPS if f"[step: {step}]" in text]


def journey_line(text, steps):
    """The step line: one line beginning `- Journey` naming every step of the journey, in order."""
    for line in text.splitlines():
        if line.startswith("- Journey"):
            at = [line.find(step) for step in steps]
            return -1 not in at and at == sorted(at)
    return False


def answer_for(question):
    """The operator's side of the interview: small, then a fresh conversation, else minimal."""
    text = (question.get("question") or "").lower()
    labels = [o.get("label", "") for o in question.get("options") or []]
    for wanted in ("fresh", "small"):
        hit = next((label for label in labels if wanted in label.lower()), None)
        if hit:
            return hit, [hit]
    if "fresh" in text or "continue" in text:
        return "Continue in a fresh conversation.", []
    if "size" in text or "small" in text or "large" in text:
        return "small", []
    if labels:
        return labels[0], [labels[0]]
    return "Keep it minimal: GET /ping answers 200 with the body 'pong'. Nothing else.", []


def run_turn(base, message, minutes=12):
    """Trigger one turn on the document in a new conversation; answer its questions until it ends."""
    code, run = api("POST", f"{base}/agent/trigger",
                    {"agent": AGENT, "message": message, "spec_document": DOC})
    check("the turn starts", code in (200, 202), f"{code} {run}")
    run_id = run["run_id"]
    asked = []
    end = time.time() + minutes * 60
    while time.time() < end:
        _, pending = api("GET", f"{base}/questions?answered=false")
        for question in pending if isinstance(pending, list) else []:
            if question["id"] in {q["id"] for q in asked}:
                continue
            asked.append(question)
            answer, labels = answer_for(question)
            print(f"  asked (batch {question.get('batch_size')}): {question['question'][:160]!r}"
                  f" -> {answer!r}", flush=True)
            api("PATCH", f"{base}/questions/{question['id']}", {"answer": answer, "labels": labels})
        (state,) = ro("select status from runs where id=?", (run_id,))[0]
        if state not in ("running", "queued", "starting"):
            print(f"  run {run_id} {state}", flush=True)
            return asked
        time.sleep(3)
    check("the turn ends within its budget", False, run_id)
    return asked


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A tiny HTTP service with no routes yet.\n", encoding="utf-8")
    (root / "app.py").write_text(
        "from http.server import BaseHTTPRequestHandler\n\n\nclass Handler(BaseHTTPRequestHandler):\n"
        "    pass\n", encoding="utf-8")
    git(root, "add", "README.md", "app.py")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "journeydrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, runner = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, runner)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": runner["id"]})
    assert code in (200, 201), (code, out)
    code, out = api("POST", f"{base}/project/documents",
                    {"title": "A ping route", "kind": "change-spec", "path": DOC})
    assert code == 201, (code, out)

    # 1-2: the document's place, and what a turn on it is told -- before any turn.
    row = document(base)
    check("1 a new change document starts at intake with no size",
          row.get("path") == DOC and row.get("step") == "intake" and "size" in row and row["size"] is None,
          f"found={row.get('path') == DOC} phase={row.get('phase')!r} step={row.get('step')!r} "
          f"size={row.get('size')!r}")
    text = preview(base)
    (TMP / "preview_intake.md").write_text(text, encoding="utf-8")
    check("2 the intake briefing holds intake's duty only, and the journey line",
          markers(text) == ["intake"] and journey_line(text, LARGE),
          f"markers={markers(text)}")

    # 3-4: a real turn interviews, sizes, and asks to advance.
    asked = run_turn(base, "Add a /ping route to this project.")
    check("3a the turn asked through ask_user", len(asked) >= 2, f"{len(asked)} questions")
    check("3b one question per ask_user call", all(q.get("batch_size", 1) == 1 for q in asked),
          str([q.get("batch_size") for q in asked]))
    row = document(base)
    check("4 the document records size small and step requirements-and-acceptance",
          row.get("size") == "small" and row.get("step") == "requirements-and-acceptance",
          f"step={row.get('step')!r} size={row.get('size')!r}")

    # 5-6: any new conversation resumes at the recorded step.
    text = preview(base)
    (TMP / "preview_reqs.md").write_text(text, encoding="utf-8")
    check("5 the briefing is now requirements-and-acceptance's, not intake's",
          markers(text) == ["requirements-and-acceptance"], f"markers={markers(text)}")
    run_turn(base, "Carry on with this document.")
    sys.path.insert(0, str(REPO / "hub"))
    from hub.spec_payload import extract_payload  # noqa: PLC0415

    stored = extract_payload((root / DOC).read_text(encoding="utf-8"))
    musts = [r["key"] for r in stored.get("requirements") or [] if r.get("modal") == "MUST"]
    covered = {c.get("requirement") for c in stored.get("acceptance_criteria") or []}
    check("6 the fresh conversation wrote requirements, each MUST with a criterion",
          musts and set(musts) <= covered, f"musts={musts} covered={sorted(covered)}")

    # 7: the operator sees the journey.
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=spec&doc={urllib.parse.quote(DOC)}",
                  wait_until="domcontentloaded")
        journey = page.locator("[data-testid=spec-journey]")
        poll(lambda: journey.count() == 1, 15)
        steps = [s.get_attribute("data-testid").removeprefix("spec-journey-step-")
                 for s in page.locator("[data-testid^=spec-journey-step-]").all()]
        current = page.locator("[data-testid^=spec-journey-step-][aria-current=step]")
        page.screenshot(path=str(SHOT) + "_bar.png", full_page=True)
        check("7 the phase bar shows the small journey with requirements-and-acceptance current",
              steps == SMALL and current.count() == 1
              and current.get_attribute("data-testid") == "spec-journey-step-requirements-and-acceptance",
              f"steps={steps}")
        browser.close()


if __name__ == "__main__":
    main()
