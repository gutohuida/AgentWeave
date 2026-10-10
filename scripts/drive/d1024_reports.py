"""Acceptance drive for the knowledge vault roadmap's `agent-reports` slice, 2026-10-10.

The slice's `drive` criterion (spec/changes/a-working-agent-tells-the-manager-an-entry-is-wrong/).
It starts its own Hub on :8124 with a fresh database (never :8000 or :8010), serving the bundle
built into hub/hub/static/ui. It opens a scratch git repository as the project, with a Haiku runner
on the vault-reports job and a Haiku agent, uploads a source stating the refund limit without
approval is 300 euros, and writes two fact files beside it citing that line: one claiming 3,000
euros, one claiming 300. It checks, in order:

  1. vault-reports is listed with trigger report_filed, and is enabled with the Haiku runner;
  2. the source and both facts are in the map;
  3. a turn told the 3,000 fact is wrong calls vault_report on it;
  4. within three minutes that report is corrected: a new fact citing the source says 300, the
     3,000 fact is superseded by it in the map, and its card says so;
  5. a second turn, told a colleague claims the 300 fact should say 500, calls vault_report on it;
  6. that report is answered or referred, and the 300 fact is not superseded;
  7. two vault_report_filed events name the agent, and the activity log has two vault-reports
     firings with trigger report_filed, at least one written;
  8. in Chromium, the Vault tab shows both reports with their answers.

It fails on today's Hub at check 1 (no vault-reports job). It stops at the first failure, so a red
run spends no model call. The job is disabled again before the Hub stops. Run from anywhere:

    py -3.11 scripts/drive/d1024_reports.py
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
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

REPO = pathlib.Path(__file__).resolve().parents[2]
PORT = 8124
HUB = f"http://127.0.0.1:{PORT}"
KEY = "aw_live_" + secrets.token_hex(16)
STAMP = time.strftime("%H%M%S")
TMP = REPO / "testbed" / "drive1024-reports" / STAMP
DB = TMP / "hub.db"
SHOT = TMP / "shot"
HAIKU = "claude-haiku-4-5-20251001"
JOB = "vault-reports"
AGENT = "helper"
WAIT = 3 * 60
SOURCE = (
    "Refund policy meeting with Acme Retail, 2026-10-01.\n"
    "Present: Dana (Acme), Luis (us).\n"
    "Dana: we reviewed refunds with finance last week.\n"
    "Dana: the refund limit without manager approval is 300 euros.\n"
    "Luis: understood, we will keep it in the build.\n"
)
LINE = "Dana: the refund limit without manager approval is 300 euros."
LINE_NO = 4
WRONG = "The refund limit without manager approval for Acme is 3,000 euros."
RIGHT = "The refund limit without manager approval for Acme is 300 euros."
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
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            sys.exit(f"port {PORT} is in use; stop whatever holds it first")
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


state = {}


def main():
    proc = start_hub()
    try:
        drive()
    except Stop:
        pass
    finally:
        if state.get("base"):  # never leave a job enabled
            api("PATCH", f"{state['base']}/manager/jobs/{JOB}", {"enabled": False})
        stop_hub(proc)
    bad = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(bad)} passed, {len(bad)} failed  (artefacts: {TMP})")
    sys.exit(1 if bad else 0)


def records(folder, prefix):
    if not folder.is_dir():
        return []
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob(f"{prefix}-*.json"))]


def write_fact(root, source_id, claim):
    """A tracked fact record beside the source, as distillation writes one (vault.add_fact)."""
    fact_id = "fct-" + secrets.token_hex(6)
    meta = {
        "id": fact_id,
        "kind": "fact",
        "claim": claim,
        "citations": [{"source": source_id, "quote": LINE, "line_start": LINE_NO, "line_end": LINE_NO}],
        "sources": [source_id],
        "visibility": "tracked",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
        "holder": None,
        "made_by": {"job": "d1024", "model": None},
    }
    folder = root / "knowledge" / "facts"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{fact_id}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return fact_id


def turn(base, message, label):
    """One agent turn; answers whether it called vault_report, and its outputs."""
    code, run = api("POST", f"{base}/agent/trigger", {"agent": AGENT, "message": message})
    check(f"{label}a the turn starts", code in (200, 202), f"{code} {run}")
    run_id = run["run_id"]
    ended = poll(lambda: ro("select status from runs where id=?", (run_id,))[0][0]
                 not in ("running", "queued", "starting"), 6 * 60)
    check(f"{label}b the turn ends", ended, run_id)
    outputs = ro("select kind, content, payload from agent_outputs where run_id=? "
                 "order by sequence, timestamp", (run_id,))
    (TMP / f"outputs{label}.json").write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
    called = any("vault_report" in f"{content}{payload}" for kind, content, payload in outputs
                 if kind in ("tool_use", "tool_call"))
    return called, outputs


def report_on(root, entry):
    return next((r for r in records(root / "knowledge" / "reports", "rpt") if r.get("entry") == entry), None)


def drive():
    root = TMP / "proj"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("A scratch project for the reports drive.\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")

    code, project = api("POST", "/projects/open", {"path": str(root), "name": "reportdrive"})
    assert code in (200, 201), (code, project)
    pid = project["id"]
    base = f"/projects/{pid}"
    code, haiku = api("POST", f"{base}/runners", {"name": "Haiku", "cli": "claude", "model": HAIKU})
    assert code in (200, 201), (code, haiku)
    code, out = api("POST", f"{base}/agents", {"name": AGENT, "runner_id": haiku["id"]})
    assert code in (200, 201), (code, out)

    # 1: the job exists and is enabled.
    _, jobs = api("GET", f"{base}/manager/jobs")
    listed_jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
    spec = next((j for j in listed_jobs or [] if isinstance(j, dict) and j.get("key") == JOB), None)
    code, job = api("PATCH", f"{base}/manager/jobs/{JOB}", {"enabled": True, "runner_id": haiku["id"]})
    state["base"] = base if code == 200 else None
    check("1 vault-reports is listed with trigger report_filed and enabled with the Haiku runner",
          spec is not None and spec.get("trigger") == "report_filed" and code == 200,
          f"listed={spec} patch={code} {str(job)[:300]}")

    # 2: a source and two facts written beside it.
    code, source = api("POST", f"{base}/vault/sources",
                       {"name": "Acme refund policy", "type": "transcript", "content": SOURCE})
    sid = source.get("id") if isinstance(source, dict) else None
    check("2a the source is uploaded", code == 201 and sid, f"{code} {str(source)[:300]}")
    wrong = write_fact(root, sid, WRONG)
    right = write_fact(root, sid, RIGHT)
    _, vault_map = api("GET", f"{base}/vault/map")
    listed = {e.get("id"): e for e in (vault_map or {}).get("entries", [])} if isinstance(vault_map, dict) else {}
    check("2b both facts are in the map", wrong in listed and right in listed, f"ids={list(listed)}")

    # 3: the agent reports the 3,000 fact.
    called, _ = turn(base, (
        f"The knowledge vault fact {wrong} is wrong: its own source says the refund limit is 300 "
        f"euros, not 3,000. Report it to the manager with vault_report, naming {wrong} and saying "
        "what is wrong. Do nothing else."), "3")
    check("3c the run called vault_report", called and report_on(root, wrong) is not None,
          f"called={called} report={report_on(root, wrong)}")

    # 4: corrected.
    poll(lambda: (report_on(root, wrong) or {}).get("status") == "corrected", WAIT, every=3)
    first = report_on(root, wrong) or {}
    (TMP / "report_wrong.json").write_text(json.dumps(first, indent=2), encoding="utf-8")
    new_id = first.get("replaced_by")
    new_fact = next((f for f in records(root / "knowledge" / "facts", "fct") if f.get("id") == new_id), {})
    _, vault_map = api("GET", f"{base}/vault/map")
    listed = {e.get("id"): e for e in (vault_map or {}).get("entries", [])}
    _, card = api("GET", f"{base}/vault/entries/{wrong}")
    content = (card or {}).get("content") or "" if isinstance(card, dict) else ""
    check("4 the 3,000 report is corrected: a new 300 fact citing the source supersedes it",
          first.get("status") == "corrected" and new_id and "300" in new_fact.get("claim", "")
          and "3,000" not in new_fact.get("claim", "") and sid in (new_fact.get("sources") or [])
          and listed.get(wrong, {}).get("superseded_by") == new_id
          and "superseded" in content.lower() and new_id in content,
          f"report={first} new={new_fact} listed={listed.get(wrong)} card={content[:300]!r}")

    # 5: the agent reports the 300 fact on a colleague's say-so.
    called, _ = turn(base, (
        f"A colleague claims the knowledge vault fact {right} is wrong and that the limit should be "
        f"500 euros. Report that to the manager with vault_report, naming {right} and passing on "
        "the colleague's claim. Do nothing else."), "5")
    check("5c the run called vault_report", called and report_on(root, right) is not None,
          f"called={called} report={report_on(root, right)}")

    # 6: answered or referred, never a correction to 500.
    poll(lambda: (report_on(root, right) or {}).get("status") in ("answered", "referred"), WAIT, every=3)
    second = report_on(root, right) or {}
    (TMP / "report_right.json").write_text(json.dumps(second, indent=2), encoding="utf-8")
    _, vault_map = api("GET", f"{base}/vault/map")
    listed = {e.get("id"): e for e in (vault_map or {}).get("entries", [])}
    check("6 the 300 report is answered or referred, and the 300 fact is not superseded",
          second.get("status") in ("answered", "referred") and second.get("answer")
          and not listed.get(right, {}).get("superseded_by"),
          f"report={second} listed={listed.get(right)}")

    # 7: the events and the firings.
    filed = ro("select agent, data from event_logs where project_id=? and event_type=?",
               (pid, "vault_report_filed"))
    _, activity = api("GET", f"{base}/manager/activity?job={JOB}")
    firings = activity.get("firings", []) if isinstance(activity, dict) else []
    ours = [f for f in firings if f.get("trigger") == "report_filed"]
    check("7 two vault_report_filed events name the agent; two report_filed firings, one written",
          len(filed) == 2 and all(agent == AGENT for agent, _d in filed)
          and len(ours) == 2 and any(f.get("outcome") == "written" for f in ours),
          f"filed={filed} firings={[(f.get('trigger'), f.get('outcome'), f.get('detail')) for f in firings]}")

    # 8: the Vault tab.
    from playwright.sync_api import sync_playwright

    seed = ("sessionStorage.setItem('agentweave-session', JSON.stringify({apiKey: %r, hubUrl: %r}));"
            "localStorage.setItem('agentweave-selected-project', %r);" % (KEY, HUB, pid))
    ids = [first["id"], second["id"]]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1100})
        page.add_init_script(seed)
        page.goto(f"{HUB}/?project={pid}&tab=vault", wait_until="domcontentloaded")
        shown = poll(lambda: all(page.locator(f"[data-testid=vault-report-{i}]").count() == 1 for i in ids), 20)
        texts = [page.locator(f"[data-testid=vault-report-{i}]").inner_text() if shown else "" for i in ids]
        page.screenshot(path=str(SHOT) + "_reports.png", full_page=True)
        browser.close()
    check("8 the Vault tab shows both reports with their answers",
          shown and all(r.get("answer", "")[:40] in t for r, t in zip((first, second), texts)),
          f"shown={shown} texts={[t[:200] for t in texts]}")


if __name__ == "__main__":
    main()
