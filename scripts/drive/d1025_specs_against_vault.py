"""Acceptance drive for the knowledge vault roadmap's `specs-against-the-vault` slice, 2026-10-11.

The slice's `drive` criterion (spec/changes/a-requirement-is-checked-against-what-the-vault-recorded/,
spdoc-e4f531e0b926). It starts its own Hub on the first free port from 8110 with a fresh database
(never :8000 or :8010), serving the bundle built into hub/hub/static/ui. It opens a scratch git
repository as the project, with a Haiku runner on vault-distillation and spec-vault-check, and
checks, in order:

  1. spec-vault-check is listed with trigger document_proposed, and is enabled with the Haiku runner;
  2. a transcript dated 2026-01-10 saying refunds up to 300 euros need no approval is uploaded, and
     its 300-euro fact is distilled;
  3. a change document is saved whose R1 cites that fact (refunds up to 300 euros need no approval)
     and whose R2 cites nothing (refunds up to 3,000 euros need no approval); R1's facts list is
     read back unchanged;
  4. it is proposed; within three minutes spec-vault-check fires once, trigger document_proposed,
     outcome written, keeping a conflict on R2;
  5. a transcript dated 2026-03-01 saying the limit is now 500 euros is uploaded and distilled, and
     an open contradiction cites the 300 fact and a 500 fact;
  6. GET /vault/warnings has a disputed warning on R1 whose message names both transcripts;
  7. approving without approve_anyway answers 409 approval_warnings with a vault_warning gap at
     requirements[0];
  8. with approve_anyway it answers 200, and warnings_overridden holds the vault_warning;
  9. in Chromium, the spec page's Vault warnings panel shows R1's warning naming both transcripts.

It fails on today's Hub at check 1 (no spec-vault-check job). It stops at the first failure, so a
red run spends no model call. Both jobs are disabled again before the Hub stops. Run from anywhere:

    py -3.11 scripts/drive/d1025_specs_against_vault.py
"""

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
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1025-specs-vault" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
JOB = "spec-vault-check"
DISTIL = "vault-distillation"
WAIT = 3 * 60
DOC = "spec/changes/refund-limits/spec.json"
R1, R2 = "small-refunds", "large-refunds"
JANUARY_NAME, MARCH_NAME = "Acme refunds January", "Acme refunds March"
JANUARY = (
    "Refund policy meeting with Acme Retail, 2026-01-10.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "Dana: we went through refunds with finance.\n"
    "Dana: refunds up to 300 euros need no manager approval.\n"
    "Luis: understood, we will build it that way.\n"
)
MARCH = (
    "Follow-up meeting with Acme Retail, 2026-03-01.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "Dana: finance reviewed the refund numbers again.\n"
    "Dana: the limit is now 500 euros; refunds up to 500 euros need no manager approval.\n"
    "Luis: noted, we will raise it.\n"
)
results = []
state = {}


def free_port():
    for port in range(8110, 8140):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    sys.exit("no free port in 8110-8139")


PORT = free_port()
HUB = f"http://127.0.0.1:{PORT}"


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


def poll(fn, secs=15.0, every=0.5):
    end = time.time() + secs
    while time.time() < end:
        try:
            if fn():
                return True
        except Exception:  # noqa: BLE001 -- a locator mid-render or a file mid-write
            pass
        time.sleep(every)
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
    print(f"hub on :{PORT}", flush=True)
    proc = start_hub()
    try:
        drive()
    except Stop:
        pass
    finally:
        if state.get("base"):  # never leave a job enabled
            for job in (JOB, DISTIL):
                api("PATCH", f"{state['base']}/manager/jobs/{job}", {"enabled": False})
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


def records(folder, prefix):
    if not folder.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob(f"{prefix}-*.json"))]


def facts_of(root, source_id):
    return [f for f in records(root / "knowledge" / "facts", "fct")
            if source_id in (f.get("sources") or [])]


def refund(facts, number):
    return [f for f in facts if number in f.get("claim", "")]


def upload(base, name, dated, content):
    code, out = api("POST", f"{base}/vault/sources",
                    {"name": name, "type": "transcript", "content": content, "dated": dated})
    return code, (out.get("id") if isinstance(out, dict) else None), out


def payload(fact_id):
    return {
        "title": "Refund limits",
        "summary": "Refunds below a limit go through without a manager's approval.",
        "problem": "Every refund waits for a manager today, however small.",
        "scope": {"in_scope": ["The approval rule for refunds"], "non_goals": ["Partial refunds"]},
        "requirements": [
            {"key": R1, "statement": "Refunds up to 300 euros MUST need no manager approval.",
             "modal": "MUST", "rationale": "Agreed with Acme in January.", "party": None,
             "facts": [fact_id]},
            {"key": R2, "statement": "Refunds up to 3,000 euros MUST need no manager approval.",
             "modal": "MUST", "rationale": None, "party": None},
        ],
        "acceptance_criteria": [],
        "tasks": [{
            "key": "rule", "title": "Apply the rule", "description": "Skip approval below the limit.",
            "requirements": [R1, R2], "depends_on": [], "files": ["refunds.py"],
            "from": None, "reviewer": None,
        }],
        "algorithms": [],
        "design": "One comparison against the limit.",
        "evidence": {"checked": ["refunds.py always asks a manager"], "limits": []},
        "lifecycle": "",
        "open_questions": [],
        "delivery": {"mode": "none", "agent": None, "reviewer": None,
                     "stop_when_queue_empties": False, "stop_at": None, "cron": "*/5 * * * *"},
    }


def detail_of(out):
    if isinstance(out, dict):
        return out.get("detail", out)
    try:
        return json.loads(out).get("detail", {})
    except (ValueError, AttributeError):
        return {}


def view(base):
    _, listed = api("GET", f"{base}/project/documents")
    return next((x for x in (listed or {}).get("documents", []) if x.get("path") == DOC), {})


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the specs-against-the-vault drive.\n",
                                    encoding="utf-8")
    (root / "refunds.py").write_text("# every refund asks a manager\n", encoding="utf-8")
    git(root, "add", "README.md", "refunds.py")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "specvault"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)

    # 1: the job exists and is enabled. Nothing is spawned before this passes.
    _, jobs = api("GET", f"{base}/manager/jobs")
    listed_jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
    spec = next((j for j in listed_jobs or [] if isinstance(j, dict) and j.get("key") == JOB), None)
    code, job = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": haiku["id"]})
    state["base"] = base
    check("1 spec-vault-check is listed with trigger document_proposed and enabled with the Haiku runner",
          spec is not None and spec.get("trigger") == "document_proposed" and code == 200,
          f"listed={spec} patch={code} {str(job)[:300]}")
    code, job = api("PATCH", f"{base}/manager/jobs/{DISTIL}", {"enabled": True, "runner_id": haiku["id"]})
    assert code == 200, (code, job)

    # 2: the January transcript and its fact.
    code, jan, out = upload(base, JANUARY_NAME, "2026-01-10", JANUARY)
    check("2a the January transcript is uploaded", code == 201 and jan, f"{code} {str(out)[:300]}")
    got = poll(lambda: refund(facts_of(root, jan), "300"), WAIT, every=3)
    check("2b its 300-euro fact is distilled", got,
          f"facts={[f.get('claim') for f in facts_of(root, jan)]}")
    fact300 = refund(facts_of(root, jan), "300")[0]["id"]

    # 3: the change document, R1 citing the fact, R2 citing nothing.
    quoted = urllib.parse.quote(DOC)
    code, out = api("POST", f"{base}/project/documents",
                    {"title": "Refund limits", "kind": "change-spec", "path": DOC})
    assert code == 201, (code, out)
    code, out = api("PUT", f"{base}/project/documents/{DOC}/content", {"document": payload(fact300)})
    saved = json.loads((root / DOC).read_text(encoding="utf-8")) if (root / DOC).is_file() else {}
    kept = next((r for r in saved.get("requirements", []) if r.get("key") == R1), {}).get("facts")
    check("3 the document is saved and R1's facts list is read back unchanged",
          code == 200 and kept == [fact300], f"{code} {str(out)[:300]} facts={kept}")
    code, out = api("POST", f"{base}/project/documents/journey?path={quoted}",
                    {"size": "small", "step": "intake", "reason": "drive setup"})
    assert code == 200, (code, out)
    code, out = api("POST", f"{base}/project/documents/close-exploration?path={quoted}")
    assert code == 200, (code, out)

    # 4: proposal fires the check once, keeping a conflict on R2.
    code, out = api("POST", f"{base}/project/documents/propose?path={quoted}")
    assert code == 200 and isinstance(out, dict) and out.get("proposed") is True, (code, out)

    def firings():
        _, activity = api("GET", f"{base}/manager/activity?job={JOB}")
        return activity.get("firings", []) if isinstance(activity, dict) else []

    poll(lambda: any(f.get("outcome") in ("written", "empty", "failed") for f in firings()), WAIT, every=3)
    fired = firings()
    events = ro("select data from event_logs where project_id=? and event_type=?",
                (pid, "manager_job_fired"))
    ours = [json.loads(data) for (data,) in events if json.loads(data or "{}").get("job") == JOB]
    (TMP / "firings.json").write_text(json.dumps({"activity": fired, "events": ours}, indent=2),
                                      encoding="utf-8")
    check("4 spec-vault-check fires once on document_proposed, written, with a conflict on R2",
          len(fired) == 1 and fired[0].get("trigger") == "document_proposed"
          and fired[0].get("outcome") == "written" and len(ours) == 1 and R2 in json.dumps(ours[0])
          and R1 not in json.dumps(ours[0].get("conflicts", ours[0])),
          f"activity={[(f.get('trigger'), f.get('outcome'), f.get('detail')) for f in fired]} events={ours}")

    # 5: the March transcript contradicts the January fact.
    code, mar, out = upload(base, MARCH_NAME, "2026-03-01", MARCH)
    check("5a the March transcript is uploaded", code == 201 and mar, f"{code} {str(out)[:300]}")
    folder = root / "knowledge" / "contradictions"

    def the_pair():
        new500 = {f["id"] for f in refund(facts_of(root, mar), "500")}
        for record in records(folder, "ctr"):
            pair = set(record.get("facts") or [])
            if record.get("status") == "open" and fact300 in pair and pair & new500:
                return record
        return None

    poll(lambda: the_pair() is not None, WAIT, every=3)
    every = records(folder, "ctr")
    (TMP / "contradictions.json").write_text(json.dumps(every, indent=2), encoding="utf-8")
    check("5b an open contradiction cites the 300 fact and a 500 fact", the_pair() is not None,
          f"contradictions={[(c.get('facts'), c.get('presumed'), c.get('status')) for c in every]}")

    # 6: the derived warning on R1.
    code, out = api("GET", f"{base}/vault/warnings?path={quoted}")
    (TMP / "warnings.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    listed = out.get("warnings", out) if isinstance(out, dict) else out
    on_r1 = [w for w in listed or [] if isinstance(w, dict) and w.get("key") == R1
             and w.get("kind") == "disputed"]
    message = on_r1[0].get("message", "") if on_r1 else ""
    check("6 GET /vault/warnings has a disputed warning on R1 naming both transcripts",
          code == 200 and on_r1 and JANUARY_NAME in message and MARCH_NAME in message,
          f"{code} {str(out)[:600]}")

    # 7: approval lists it.
    phase = f"{base}/project/documents/phase?path={quoted}&to=approved"
    code, out = api("POST", phase, {"reason": "drive"})
    detail = detail_of(out)
    gaps = detail.get("warnings", []) if isinstance(detail, dict) else []
    vault_gaps = [g for g in gaps if isinstance(g, dict) and g.get("code") == "vault_warning"]
    check("7 approve without approve_anyway: 409 approval_warnings, a vault_warning at requirements[0]",
          code == 409 and isinstance(detail, dict) and detail.get("code") == "approval_warnings"
          and any(g.get("where") == "requirements[0]" for g in vault_gaps),
          f"{code} {str(detail)[:600]}")

    # 8: approve anyway approves and records it.
    code, out = api("POST", phase, {"reason": "drive", "approve_anyway": True})
    row = view(base)
    overridden = row.get("approval_warnings_overridden") or []
    check("8 approve_anyway: 200, and warnings_overridden holds the vault_warning",
          code == 200 and row.get("phase") == "approved"
          and any(isinstance(g, dict) and g.get("code") == "vault_warning" for g in overridden),
          f"{code} {str(out)[:300]} phase={row.get('phase')} overridden={overridden}")

    # 9: the spec page.
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        # The app has no document URL parameter: open it from the tree (d1012's recipe).
        page.goto(f"{HUB}/?project={pid}&tab=spec", wait_until="domcontentloaded")
        target = page.locator(f'[data-testid="spec-tree-document-{DOC}"]')
        poll(lambda: page.locator("[data-testid^=spec-tree-directory-]").count() > 0, 20)
        closed = page.locator("[data-testid^=spec-tree-directory-][aria-expanded=false]")
        for _ in range(6):
            if target.count() or not closed.count():
                break
            closed.first.click()
        poll(lambda: target.count() == 1, 10)
        if target.count() == 1:
            target.click()
        row_r1 = page.locator(f"[data-testid=spec-vault-warning-{R1}]")
        shown = poll(lambda: row_r1.count() >= 1, 20)
        if shown:
            row_r1.first.scroll_into_view_if_needed()
        text = row_r1.first.inner_text() if shown else ""
        page.screenshot(path=str(SHOT) + "_warnings.png", full_page=True)
        browser.close()
    check("9 the spec page's Vault warnings panel shows R1's warning naming both transcripts",
          shown and JANUARY_NAME in text and MARCH_NAME in text, f"shown={shown} text={text[:300]!r}")


if __name__ == "__main__":
    main()
