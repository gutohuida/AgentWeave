"""DRIVE 2026-09-22 -- F376: a refused capability reaches the operator.

`a-refused-capability-reaches-the-operator` tasks 5.1 and 5.2, re-running D-1's shape
(`d1_0918_refused_capability.py`) against the fix. A fresh project, `allow_agent_jobs` off by
default, one agent bound to Haiku, and one real turn told to call `create_flow`. Then:

5.1  the refusal opened exactly one question of record on the operator's Questions destination,
     the agent's transcript carries the new sentence naming it, and `permission_requests` is empty.
     While it is open: the question is non-blocking (so it renders under Unanswered, not the red
     Blocking banner), and the refused run's conversation does not read as waiting.
5.2  the operator enables the setting by hand and answers the question. This RECORDS what the
     woken agent does. It asserts no retry: the agent wakes holding the question and the answer
     and nothing about the call it made (task 5.2, R4).

    AW_HUB=http://127.0.0.1:<port> AW_KEY=<key> AW_DB=<path to the drive profile's db> \
      py -3.11 -u scripts/drive/d_0922_f376_refused_capability.py

Refuses :8000 and :8010. Creates its own project and deletes it in a `finally`; leaves no job
enabled.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import aw  # noqa: E402
from aw import api  # noqa: E402

HUB = aw.HUB
if HUB.rstrip("/").endswith((":8000", ":8010")):
    raise SystemExit(f"REFUSING: {HUB} is the operator's real Hub or the trial Hub.")
DB = os.environ.get("AW_DB", "")
if not DB or not os.path.exists(DB):
    raise SystemExit("AW_DB must name the drive Hub's own database file.")

HAIKU = "claude-haiku-4-5-20251001"
AGENT = "architect"
RUN = time.strftime("%H%M%S")
FORBIDDEN = ("proj-5e960453", "proj-18e5d4e0", "proj-d85a82bf4216")
ROOT = tempfile.mkdtemp(prefix="aw-f376-")
P = ""
VERDICTS = []


def check(label, ok, detail=""):
    VERDICTS.append((label, bool(ok)))
    print(f"  [{'OK ' if ok else 'BAD'}] {label}" + (f" -- {detail}" if detail else ""))
    return bool(ok)


def git(*args):
    subprocess.run(["git", "-C", ROOT, *args], check=True, capture_output=True)


def ro_count(sql, *params):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    try:
        return con.execute(sql, params).fetchone()[0]
    finally:
        con.close()


def status_of(agent):
    code, body = api("GET", f"/projects/{P}/agents")
    rows = body if isinstance(body, list) else []
    return next((row.get("status") for row in rows if row.get("name") == agent), None)


def settle(label, seconds=240):
    end = time.time() + seconds
    seen_busy = False
    while time.time() < end:
        state = status_of(AGENT)
        seen_busy = seen_busy or state in ("running", "working")
        if seen_busy and state not in ("running", "working"):
            print(f"      [{label}] settled: {state}")
            return True
        time.sleep(3)
    print(f"      [{label}] did not settle ({status_of(AGENT)})")
    return False


def questions(answered=False):
    code, body = api("GET", f"/projects/{P}/questions?answered={'true' if answered else 'false'}")
    return body if isinstance(body, list) else []


def chat(conversation_id):
    code, body = api("GET", f"/projects/{P}/agent/{AGENT}/chat/{conversation_id}")
    return json.dumps(body, ensure_ascii=False)


def conversations():
    code, body = api("GET", f"/projects/{P}/agent/{AGENT}/conversations")
    return body if isinstance(body, list) else []


def spec_document():
    payload = {
        "schema_version": 1,
        "kind": "change-spec",
        "title": "notes.txt exists",
        "summary": "One file, so a flow has something to decompose.",
        "problem": "notes.txt does not exist.",
        "scope": {"in_scope": ["notes.txt"], "non_goals": ["anything else"]},
        "requirements": [
            {
                "key": "file",
                "statement": "The project SHALL contain notes.txt holding the line ok.",
                "modal": "SHALL",
                "rationale": "A drive needs one piece of work.",
            }
        ],
        "acceptance_criteria": [
            {
                "key": "file-exists",
                "requirement": "file",
                "given": "the project after the change",
                "when": "notes.txt is read",
                "then": "it holds the single line ok",
            }
        ],
        "tasks": [
            {
                "key": "write-file",
                "title": "Create notes.txt",
                "description": "Create notes.txt containing exactly the line `ok`.",
                "requirements": ["file"],
            }
        ],
    }
    base = f"/projects/{P}/project"
    code, doc = api("POST", f"{base}/documents", {"title": payload["title"]})
    if code >= 300:
        raise SystemExit(f"create document failed: {code} {doc}")
    q = urllib.parse.quote(doc["path"], safe="")
    api("PUT", f"{base}/documents/{q}/content", {"document": payload})
    api("POST", f"{base}/documents/close-exploration?path={q}", {"reason": "drive f376"})
    api("POST", f"{base}/documents/propose?path={q}", {"reason": "drive f376"})
    api("POST", f"{base}/documents/phase?path={q}&to=approved", {"reason": "drive f376"})
    return doc["id"]


def main():
    global P
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("f376 drive fixture\n")
    git("init", "-q", "-b", "main")
    git("config", "user.email", "drive@example.invalid")
    git("config", "user.name", "Drive")
    git("add", "README.md")
    git("commit", "-q", "-m", "base")

    code, created = api("POST", "/projects/open", {"path": ROOT, "name": f"f376-drive-{RUN}"})
    if code not in (200, 201):
        raise SystemExit(f"could not open the project: {code} {created}")
    P = created["id"]
    aw.P = P
    if P in FORBIDDEN:
        raise SystemExit(f"REFUSING: the Hub handed back {P}")
    print(f"  project {P} at {ROOT}")

    code, runner = api(
        "POST", f"/projects/{P}/runners", {"name": "haiku", "cli": "claude", "model": HAIKU}
    )
    assert code == 201, (code, runner)
    code, agent = api("POST", f"/projects/{P}/agents", {"name": AGENT, "runner_id": runner["id"]})
    assert code == 201, (code, agent)

    code, settings = api("GET", f"/projects/{P}/queue/settings")
    check("a new project starts with allow_agent_jobs off", settings.get("allow_agent_jobs") is False, str(settings))
    doc_id = spec_document()

    print("=" * 78)
    print("5.1 -- one real turn calls create_flow and is refused")
    print("=" * 78)
    message = (
        "Call the create_flow tool exactly once, with these exact arguments: "
        f'name="f376-flow", agent="{AGENT}", message="go", '
        f'spec_document_id="{doc_id}", stop_when_queue_empties=true. '
        "Do not call any other tool first. After the call, reply with exactly the tool's "
        "error text and nothing else, then end your turn."
    )
    code, trig = api(
        "POST", f"/projects/{P}/agent/trigger", {"agent": AGENT, "session_mode": "new", "message": message}
    )
    check("the turn was triggered", code == 200, str(trig)[:200])
    conv = trig.get("conversation_id")

    # While the refused run may still be live: nothing may call it waiting.
    time.sleep(2)
    settle("refused turn")

    open_qs = questions()
    records = [q for q in open_qs if q.get("header") == "Scheduled work"]
    check("exactly one question of record is open", len(records) == 1, json.dumps(open_qs, ensure_ascii=False)[:400])
    record = records[0] if records else {}
    qid = record.get("id", "<none>")
    check("it is attributed to the refused agent", record.get("from_agent") == AGENT)
    check("it is non-blocking, so it renders under Unanswered, not the Blocking banner", record.get("blocking") is False)
    print(f"      asker_waiting={record.get('asker_waiting')} (D14: presumed true for a question with no run)")
    print(f"      question text: {record.get('question')}")
    check("its options are the first record's", [o.get("label") for o in record.get("options", [])] == ["Enabled it — go ahead", "Leave it off"])

    transcript = chat(conv)
    check(
        "the transcript carries the new refusal sentence",
        "Agents cannot create or change scheduled work in this project" in transcript,
    )
    check("the transcript names the question", qid in transcript)
    check(
        "the old false sentence is gone",
        "requires operator approval or an enabled allowance" not in transcript,
    )
    check(
        "permission_requests is empty for the project",
        ro_count("select count(*) from permission_requests where project_id = ?", P) == 0,
    )
    check(
        "the record carries no run and no conversation",
        ro_count(
            "select count(*) from questions where id = ? and created_by_run_id is null and conversation_id is null",
            qid,
        )
        == 1,
    )
    rail = {c.get("id"): c.get("attention") for c in conversations()}
    check("the refused conversation does not read as waiting", rail.get(conv) != "waiting", str(rail))
    code, jobs = api("GET", f"/projects/{P}/jobs")
    check("no job exists yet", isinstance(jobs, list) and len(jobs) == 0, str(jobs)[:200])

    print("=" * 78)
    print("5.2 -- the operator enables the setting and answers; record what the agent does")
    print("=" * 78)
    code, settings = api("GET", f"/projects/{P}/queue/settings")
    settings["allow_agent_jobs"] = True
    code, saved = api("PATCH", f"/projects/{P}/queue/settings", settings)
    check("the operator enabled allow_agent_jobs", code == 200 and saved.get("allow_agent_jobs") is True, str(saved)[:200])
    code, answered = api(
        "PATCH",
        f"/projects/{P}/questions/{qid}",
        {"answer": "Enabled it — go ahead", "labels": ["Enabled it — go ahead"]},
    )
    check("the answer was accepted", code == 200, str(answered)[:200])
    woke = settle("woken turn", seconds=300)
    check("the refused agent was woken for the answer", woke)

    after = conversations()
    print(f"      conversations after: {[(c.get('id'), c.get('attention')) for c in after]}")
    for c in after:
        text = chat(c["id"])
        print(f"      --- conversation {c['id']} (last 1500 chars) ---")
        print("      " + text[-1500:])
    code, jobs = api("GET", f"/projects/{P}/jobs")
    jobs = jobs if isinstance(jobs, list) else []
    print(f"      jobs after the wake: {[(j.get('id'), j.get('name'), j.get('enabled')) for j in jobs]}")
    print(f"      RECORDED (not asserted): the woken agent {'created' if jobs else 'did not create'} the flow.")
    return jobs


if __name__ == "__main__":
    created_jobs = []
    try:
        created_jobs = main() or []
    finally:
        if P:
            code, jobs = api("GET", f"/projects/{P}/jobs")
            for job in jobs if isinstance(jobs, list) else []:
                if job.get("enabled"):
                    api("PATCH", f"/projects/{P}/jobs/{job['id']}", {"enabled": False})
            for attempt in range(20):
                code, _ = api("DELETE", f"/projects/{P}")
                if code in (200, 204, 404):
                    break
                time.sleep(6)
            print(f"\nfixture project deleted: {code}")
        shutil.rmtree(ROOT, ignore_errors=True)
    bad = [label for label, ok in VERDICTS if not ok]
    print(f"\n{len(VERDICTS) - len(bad)} ok / {len(bad)} bad")
    for label in bad:
        print(f"  BAD: {label}")
    sys.exit(1 if bad else 0)
