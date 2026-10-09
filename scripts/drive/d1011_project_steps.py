"""Acceptance drive for `a-project-orders-its-own-spec-steps` (project-steps slice), 2026-10-09.

The slice's `drive` and `page-edits` criteria (spec/changes/a-project-orders-its-own-spec-steps/,
spdoc-3759e366caf1). Starts its own Hub on :8099 with a fresh database (never :8000 or :8010),
serving the bundle built into hub/hub/static/ui, opens a project with one Haiku agent and a new
change document, and checks, in order:

  1. GET /project/journey answers 200 with the built-in steps and no diagnostics (no file yet);
  2. PUT /project/journey with a custom step `threat-model` (sizes: large) after requirements and a
     sentinel appended to intake answers 200; spec/journey.json in the project holds those steps;
  3. the document is sized large and moved to intake: its preview holds the sentinel; moved to
     requirements: its preview holds neither the sentinel nor threat-model's marker;
  4. a real turn at requirements, told to continue here, advances; the document lands on
     threat-model, and the advance's instructions hold `[step: threat-model]` and the pasted Markdown;
  5. the threat-model preview names the step and not the sentinel; GET /project/documents lists the
     document's journey with threat-model between requirements and acceptance;
  6. in Chromium the phase bar shows threat-model between requirements and acceptance, and the
     project page's Spec steps section lists it;
  7. on the project page the operator pastes Markdown as a step after requirements and saves
     (`page-edits`); GET /project/journey returns it at that position.

The contract it fixes for the build: the journey document is `{"steps": [...]}`; a built-in entry is
`{"key": <built-in>, "append": <text, optional>}` and a custom one is `{"key", "title", "instructions",
"sizes": [...], "append"}`; the file lists the seven built-in keys in `STEP_ORDER`; GET answers
`{"steps": [...], "diagnostics": [...]}`; the project page (Environment > Settings) has
`[data-testid=spec-steps]` with one `[data-testid=spec-steps-row-<key>]` per step in order, and the
add form is `spec-steps-add-after` (select of keys), `spec-steps-new-title`, `spec-steps-new-markdown`,
`spec-steps-add`, then `spec-steps-save`.

Fails on today's Hub at check 1 (no /project/journey route). Stops at the first failure, so a red
run spends no agent turn. Run from anywhere:

    py -3.11 scripts/drive/d1011_project_steps.py
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
PORT = 8099
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1011-project-steps" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
DOC = "spec/changes/ping-route/spec.json"
AGENT = "scribe"
BUILTINS = ("intake", "requirements", "requirements-and-acceptance", "acceptance", "approach",
            "tasks", "delivery")
LARGE = ["intake", "requirements", "threat-model", "acceptance", "approach", "tasks", "delivery"]
SENTINEL = "SENTINEL-ORCHID-7731"
THREAT_MD = (
    "List what could go wrong if someone abused the new route. Write the result as a section "
    "named Threats in the change document, one line per threat, then ask to advance."
)
THREAT = {"key": "threat-model", "title": "Threat model", "instructions": THREAT_MD,
          "sizes": ["large"]}
PASTED_MD = "Check the route against our accessibility checklist and write the findings under A11y."
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


def answer_for(question):
    """The operator's side: continue here and advance, else the first option."""
    text = (question.get("question") or "").lower()
    labels = [o.get("label", "") for o in question.get("options") or []]
    for wanted in ("here", "advance", "next", "continue", "yes"):
        hit = next((label for label in labels if wanted in label.lower()), None)
        if hit:
            return hit, [hit]
    if labels:
        return labels[0], [labels[0]]
    if "advance" in text or "continue" in text or "next" in text:
        return "Yes, advance and continue here.", []
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
            print(f"  asked: {question['question'][:160]!r} -> {answer!r}", flush=True)
            api("PATCH", f"{base}/questions/{question['id']}", {"answer": answer, "labels": labels})
        (state,) = ro("select status from runs where id=?", (run_id,))[0]
        if state not in ("running", "queued", "starting"):
            print(f"  run {run_id} {state}", flush=True)
            return asked
        time.sleep(3)
    check("the turn ends within its budget", False, run_id)
    return asked


def journey_body():
    steps = []
    for key in BUILTINS:
        entry = {"key": key}
        if key == "intake":
            entry["append"] = f"Also confirm this marker with the operator: {SENTINEL}."
        steps.append(entry)
        if key == "requirements":
            steps.append(dict(THREAT))
    return {"steps": steps}


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

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "stepsdrive"})
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

    # 1: no file, the built-in steps, nothing to report.
    code, got = api("GET", f"{base}/project/journey")
    keys = [s.get("key") for s in got.get("steps", [])] if isinstance(got, dict) else []
    check("1 GET /project/journey answers the built-in steps with no diagnostics",
          code == 200 and keys == list(BUILTINS) and got.get("diagnostics") == [],
          f"{code} keys={keys} body={str(got)[:200]}")

    # 2: the operator saves a journey; the file in the project is the saved steps.
    body = journey_body()
    code, saved = api("PUT", f"{base}/project/journey", body)
    file = root / "spec" / "journey.json"
    on_disk = json.loads(file.read_text(encoding="utf-8")).get("steps") if file.exists() else None
    check("2 PUT /project/journey saves; spec/journey.json holds the PUT body's steps",
          code == 200 and on_disk == body["steps"], f"{code} {str(saved)[:200]} file={bool(on_disk)}")

    # 3: an appended instruction reaches only its own step.
    for step, size in (("intake", "large"), ("requirements", None)):
        change = {"step": step}
        if size:
            change["size"] = size
        code, out = api("POST", f"{base}/project/documents/journey?path={urllib.parse.quote(DOC)}",
                        change)
        check(f"3 the operator moves the document to {step}", code == 200, f"{code} {str(out)[:200]}")
        text = preview(base)
        (TMP / f"preview_{step}.md").write_text(text, encoding="utf-8")
        if step == "intake":
            check("3a the intake preview holds the appended sentinel", SENTINEL in text)
        else:
            check("3b the requirements preview holds neither the sentinel nor threat-model's marker",
                  SENTINEL not in text and "[step: threat-model]" not in text)

    # 4: a real turn at requirements advances onto the custom step.
    run_turn(base, "Carry on with this document. When requirements are written, advance to the "
                   "next step in this conversation.")
    row = document(base)
    check("4 the turn's advance landed on the custom step", row.get("step") == "threat-model",
          f"step={row.get('step')!r}")

    # 5: the custom step's briefing, and the documents view's journey.
    text = preview(base)
    (TMP / "preview_threat_model.md").write_text(text, encoding="utf-8")
    check("5a the threat-model preview names the step, holds its Markdown, and not the sentinel",
          "[step: threat-model]" in text and THREAT_MD[:40] in text and SENTINEL not in text)
    check("5b the documents view lists the journey with threat-model after requirements",
          document(base).get("journey") == LARGE, f"journey={document(base).get('journey')}")

    # 6-7: the operator sees the steps, and pastes one.
    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=spec&doc={urllib.parse.quote(DOC)}",
                  wait_until="domcontentloaded")
        poll(lambda: page.locator("[data-testid=spec-journey]").count() == 1, 15)
        bar = [s.get_attribute("data-testid").removeprefix("spec-journey-step-")
               for s in page.locator("[data-testid^=spec-journey-step-]").all()]
        page.screenshot(path=str(SHOT) + "_bar.png", full_page=True)
        page.goto(f"{HUB}/?project={pid}&tab=environment&section=settings",
                  wait_until="domcontentloaded")
        section = page.locator("[data-testid=spec-steps]")
        poll(lambda: section.count() == 1, 15)
        rows = [r.get_attribute("data-testid").removeprefix("spec-steps-row-")
                for r in page.locator("[data-testid^=spec-steps-row-]").all()]
        page.screenshot(path=str(SHOT) + "_page.png", full_page=True)
        check("6 the phase bar and the project page show threat-model between requirements and "
              "acceptance",
              bar == LARGE and [k for k in rows if k in LARGE] == LARGE,
              f"bar={bar} page={rows}")

        page.select_option("[data-testid=spec-steps-add-after]", "requirements")
        page.fill("[data-testid=spec-steps-new-title]", "Accessibility check")
        page.fill("[data-testid=spec-steps-new-markdown]", PASTED_MD)
        page.click("[data-testid=spec-steps-add]")
        page.click("[data-testid=spec-steps-save]")
        _ = poll(lambda: any(
            PASTED_MD in (s.get("instructions") or "")
            for s in (api("GET", f"{base}/project/journey")[1] or {}).get("steps", [])), 15)
        page.screenshot(path=str(SHOT) + "_pasted.png", full_page=True)
        browser.close()
    _, got = api("GET", f"{base}/project/journey")
    order = [s.get("key") for s in got.get("steps", [])]
    pasted = next((s for s in got.get("steps", []) if PASTED_MD in (s.get("instructions") or "")), {})
    at = order.index(pasted["key"]) if pasted else -1
    check("7 the pasted Markdown is a step right after requirements",
          at > 0 and order[at - 1] == "requirements", f"order={order}")


if __name__ == "__main__":
    main()
