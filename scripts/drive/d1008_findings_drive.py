"""Drive for the five spec-flow findings fixed 2026-10-08 (Tier 0): F452, F424, F330, F435, F529.

Against `:8010`, each in a fresh testbed project, operator-side except F452's one Haiku turn:

- F452: an agent reads its document with include="full" and resubmits the requirements exactly as
  read; the file still holds both criteria and no Hub read fields.
- F424: a project whose directory has gone answers an approval with a stated "could not ask git"
  refusal, not a 500.
- F330: in Chromium, an exploring first message to an agent the Hub refuses leaves no document.
- F435: rewording a requirement supersedes its open drift candidate.
- F529: operator evidence naming a commit beside a file locator is footprinted at that commit.

Usage: py -3.11 scripts/drive/d1008_findings_drive.py [f452 f424 f330 f435 f529]
"""

import json
import pathlib
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

HUB = "http://127.0.0.1:8010"
KEY = (pathlib.Path.home() / ".agentweave/hub/profiles/trial/bootstrap-key.txt").read_text().strip()
DB = pathlib.Path.home() / ".agentweave/hub/profiles/trial/agentweave.db"
OUT = pathlib.Path(__file__).resolve().parents[2] / "testbed/drive1008-findings"
HAIKU = "claude-haiku-4-5-20251001"
DOC = "spec/changes/widgets/spec.html"
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" -- {detail}" if detail else ""), flush=True)


def api(method, path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{HUB}/api/v1{path}", data,
        {"Authorization": "Bearer " + KEY, "Content-Type": "application/json"}, method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:2000]
        try:
            return exc.code, json.loads(text)
        except ValueError:
            return exc.code, text


def ro(sql, args=()):
    connection = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    try:
        return connection.execute(sql, args).fetchall()
    finally:
        connection.close()


def git(root, *args):
    return subprocess.run(
        ["git", "-c", "user.email=d@x.invalid", "-c", "user.name=d", *args],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()


def project(tag):
    root = OUT / f"{tag}-{time.strftime('%H%M%S')}"
    root.mkdir(parents=True)
    (root / "README.md").write_text("findings drive\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    _, opened = api("POST", "/projects/open", {"path": str(root), "name": root.name})
    pid = opened["id"]
    api("PATCH", f"/projects/{pid}", {"main_branch": "main"})
    return pid, root


def payload(requirements, criteria, tasks):
    return {
        "schema_version": 1, "kind": "change-spec", "title": "Widgets", "summary": "s",
        "problem": "p", "scope": {"in_scope": ["x"], "non_goals": ["n"]},
        "requirements": requirements, "acceptance_criteria": criteria, "tasks": tasks,
        "delivery": {"mode": "none"},
    }


REQS = [
    {"key": "alpha", "statement": "A widget MUST list.", "modal": "MUST"},
    {"key": "beta", "statement": "A widget MUST record.", "modal": "MUST"},
]
CRITS = [
    {"key": "alpha-c", "requirement": "alpha", "given": "g", "when": "w", "then": "listed"},
    {"key": "beta-c", "requirement": "beta", "given": "g", "when": "w", "then": "recorded"},
]
TASKS = [{"key": "t", "title": "Build", "description": "d", "requirements": ["alpha", "beta"]}]


def stored_payload(root, path=DOC):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "hub"))
    from hub.spec_payload import extract_payload  # noqa: PLC0415

    return extract_payload((root / path).read_text(encoding="utf-8"))


def make_doc(pid, requirements=REQS, criteria=CRITS, tasks=TASKS):
    P = f"/projects/{pid}/project"
    code, res = api("POST", f"{P}/documents", {"title": "Widgets", "kind": "change-spec", "path": DOC})
    assert code == 201, res
    code, res = api("PUT", f"{P}/documents/{DOC}/content", {"document": payload(requirements, criteria, tasks)})
    assert code == 200, res


def f452():
    pid, root = project("f452")
    make_doc(pid)
    _, runner = api("POST", f"/projects/{pid}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    code, res = api("POST", f"/projects/{pid}/agents", {"name": "writer", "runner_id": runner["id"]})
    assert code in (200, 201), res
    message = (
        f"Call read_spec_document with path '{DOC}' and include 'full'. Then call "
        f"submit_spec_document for the same path with the same title, kind, scope, tasks and "
        f"delivery it returned, and pass `requirements` exactly as read_spec_document returned "
        f"them, unchanged, including each requirement's nested acceptance_criteria, identifier, "
        f"state and anchor. Do not pass a top-level acceptance_criteria argument. Report what "
        f"submit_spec_document returned. Do nothing else."
    )
    code, run = api("POST", f"/projects/{pid}/agent/trigger",
                    {"agent": "writer", "message": message, "spec_document": DOC, "session_mode": "new"})
    assert code in (200, 202), run
    run_id = run["run_id"]
    for _ in range(72):
        time.sleep(5)
        (state,) = ro("select status from runs where id=?", (run_id,))[0]
        if state not in ("running", "queued", "starting"):
            break
    print("  run", run_id, state, flush=True)
    calls = ro("select count(*) from agent_outputs where run_id=? and (content like '%submit_spec_document%' or payload like '%submit_spec_document%')", (run_id,))
    stored = stored_payload(root)
    keys = sorted(c["key"] for c in stored.get("acceptance_criteria") or [])
    check("F452: the run called submit_spec_document", calls and calls[0][0] > 0, calls)
    check("F452: both criteria survive the agent's read-then-resubmit", keys == ["alpha-c", "beta-c"], keys)
    leaked = [k for r in stored["requirements"] for k in ("identifier", "state", "anchor", "acceptance_criteria") if k in r]
    check("F452: no Hub read field is stored on a requirement", not leaked, leaked)


def f424():
    pid, root = project("f424")
    code, task = api("POST", f"/projects/{pid}/tasks", {"title": "approve me"})
    assert code in (200, 201), task
    for step in ("in_progress", "completed", "under_review"):
        code, res = api("PATCH", f"/projects/{pid}/tasks/{task['id']}", {"status": step})
        assert code == 200, (step, res)
    gone = root.with_name(root.name + "-moved")
    root.rename(gone)
    try:
        code, res = api("PATCH", f"/projects/{pid}/tasks/{task['id']}", {"status": "approved"})
    finally:
        gone.rename(root)
    text = json.dumps(res)
    check("F424: approval with the project directory gone is not a 500", code != 500, f"{code} {text[:300]}")
    check("F424: the refusal says git could not be asked", code == 409 and "could not ask git" in text,
          f"{code} {text[:300]}")


def f330():
    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    pid, root = project("f330")
    code, res = api("POST", f"/projects/{pid}/agents", {"name": "loner"})
    print("  agent without a runner:", code, str(res)[:200], flush=True)
    code, refused = api("POST", f"/projects/{pid}/agent/trigger", {"agent": "loner", "message": "hi"})
    print("  bare trigger to it:", code, str(refused)[:200], flush=True)
    if code < 400:
        check("F330: a trigger the Hub refuses could be arranged", False, f"{code} {refused}")
        return
    before = {d["path"] for d in api("GET", f"/projects/{pid}/project/documents")[1]["documents"]}
    seed = (
        "sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
        " localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid)
    )
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&agent=loner&conversation=__new__", wait_until="domcontentloaded")
        page.locator('[data-testid="composer-start-exploration"]').click(timeout=30000)
        page.get_by_role("textbox").fill("An idea about widgets")
        page.get_by_role("button", name="Send message").click()
        page.get_by_role("alert").wait_for(timeout=15000)
        alert = page.get_by_role("alert").inner_text()
        time.sleep(2)  # the withdrawal is best effort, after the refusal is shown
        page.screenshot(path=str(OUT / "f330-refused.png"))
        browser.close()
    after = {d["path"] for d in api("GET", f"/projects/{pid}/project/documents")[1]["documents"]}
    new = sorted(after - before)
    check("F330: the refusal is shown", bool(alert.strip()), alert[:200])
    check("F330: no exploring document is left behind", new == [], new)
    left = sorted(p.relative_to(root).as_posix() for p in (root / "spec").rglob("*.html")) if (root / "spec").exists() else []
    check("F330: no document file is left behind", left == [], left)


def f435():
    pid, root = project("f435")
    make_doc(pid)
    (root / "ledger.py").write_text("def split(): pass\n", encoding="utf-8")
    git(root, "add", "ledger.py")
    git(root, "commit", "-q", "-m", "ledger")
    P = f"/projects/{pid}/project"
    code, res = api("POST", f"{P}/spec/evidence",
                    {"identifier": "FR-1", "kind": "test_result", "summary": "ran", "locator": "ledger.py", "document": DOC})
    assert code == 201, res
    (root / "ledger.py").write_text("def split(a, b): return a - b\n", encoding="utf-8")
    git(root, "commit", "-qam", "changed")
    code, raised = api("POST", f"{P}/spec/drift/detect")
    check("F435: a drift candidate is raised", code == 200 and len(raised.get("raised", [])) == 1, raised)
    reworded = [dict(REQS[0], statement="A widget MUST list overdue ones."), REQS[1]]
    code, res = api("PUT", f"{P}/documents/{DOC}/content", {"document": payload(reworded, CRITS, TASKS)})
    assert code == 200, res
    code, listed = api("GET", f"{P}/spec/drift")
    states = [d["state"] for d in listed.get("drift", [])] if isinstance(listed, dict) else listed
    check("F435: rewording supersedes the open candidate", states == ["superseded"], states)


def f529():
    pid, root = project("f529")
    make_doc(pid)
    (root / "cart.py").write_text("import math\n", encoding="utf-8")
    git(root, "add", "cart.py")
    git(root, "commit", "-q", "-m", "the work")
    work = git(root, "rev-parse", "HEAD")
    (root / "notes.md").write_text("later\n", encoding="utf-8")
    git(root, "add", "notes.md")
    git(root, "commit", "-q", "-m", "an unrelated later commit")
    code, res = api("POST", f"/projects/{pid}/project/spec/evidence",
                    {"identifier": "FR-1", "kind": "test_result", "summary": "cart test", "locator": "cart.py",
                     "document": DOC, "commit": work})
    sha = ((res or {}).get("footprint") or {}).get("commit_sha") if isinstance(res, dict) else None
    check("F529: evidence naming a commit beside a file locator is footprinted there",
          code == 201 and sha == work, f"{code} {sha} want {work[:12]} {str(res)[:200] if code != 201 else ''}")


def main():
    # f424 is not drivable without fault injection: a missing project directory makes the gate
    # skip git (merge_situation answers None), so its evidence is the unit test patching `_git`.
    chosen = sys.argv[1:] or ["f452", "f330", "f435", "f529"]
    OUT.mkdir(parents=True, exist_ok=True)
    for name in chosen:
        print(f"== {name}", flush=True)
        try:
            globals()[name]()
        except Exception as exc:  # noqa: BLE001 - one finding's setup failure must not hide the rest
            check(f"{name}: drive ran", False, f"{type(exc).__name__}: {exc}")
    failed = [n for n, ok in results if not ok]
    print(f"{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
