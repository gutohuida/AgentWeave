"""D-1, 2026-09-18 day window -- scoped re-drive of F376/F378 on the trial Hub (:8010).

DIRECTION.md's ## 2026-09-18 section asks for a reproduction that feeds the
a-refused-capability-reaches-the-operator spec loop's R1: a real agent calls create_flow where the
403 fires, and confirms the refusal writes no `permission_requests` row (measured zero for
LoopEngine_2's project on :8000). Does not re-derive F376's diagnosis -- only checks it still
reproduces, on a fresh project, with a real Haiku turn.

    AW_HUB=http://127.0.0.1:8010 py -3.11 scripts/drive/d1_0918_refused_capability.py

Refuses :8000 outright. Creates its own fixture project and deletes it in a `finally`.
"""

import json
import os
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, show  # noqa: E402

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8010")
if HUB.endswith(":8000"):
    print("REFUSING TO RUN: 8000 is the operator's real usage.")
    sys.exit(1)

HAIKU = "claude-haiku-4-5-20251001"
TAG = time.strftime("%H%M%S")
root = pathlib.Path(os.path.expanduser("~")) / "Documents" / f"drive-0918-d1-{TAG}"

PASS, FAIL = [], []


def check(ok, label):
    (PASS if ok else FAIL).append(label)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")


root.mkdir(parents=True, exist_ok=True)
(root / "README.md").write_text(f"d1 0918 refused-capability fixture {TAG}\n", encoding="utf-8")
for cmd in (
    ["git", "init", "-b", "main"],
    ["git", "config", "user.email", "d1-0918@example.invalid"],
    ["git", "config", "user.name", "d1-0918"],
    ["git", "add", "README.md"],
    ["git", "commit", "-m", "d1 0918 fixture"],
):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)

code, proj = api("POST", "/projects/open", {"path": str(root), "name": f"d1-0918-{TAG}"})
show("POST /projects/open", code, proj, limit=300)
if code not in (200, 201):
    sys.exit(1)
PID = proj["id"]
A = f"/projects/{PID}"

try:
    code, runner = api(
        "POST", f"{A}/runners", {"name": f"haiku-{TAG}", "cli": "claude", "model": HAIKU}
    )
    show("POST /runners", code, runner, limit=200)
    assert code == 201, (code, runner)

    code, agent = api(
        "POST", f"{A}/agents", {"name": f"architect{TAG}", "runner_id": runner["id"]}
    )
    show("POST /agents", code, agent, limit=200)
    assert code == 201, (code, agent)
    AGENT = agent["name"]

    message = (
        "Call the create_flow tool exactly once, with these exact arguments: "
        f"name=\"d1-0918-flow\", agent=\"{AGENT}\", message=\"go\", "
        "spec_document_id=\"spdoc-doesnotexist\", stop_when_queue_empties=true. "
        "Do not call any other tool first. After the call, reply with exactly the tool's "
        "error text and nothing else."
    )
    code, trig = api(
        "POST", f"{A}/agent/trigger", {"agent": AGENT, "session_mode": "new", "message": message}
    )
    show("POST /agent/trigger", code, trig, limit=300)
    check(code == 200 and trig.get("conversation_id"), "the turn was triggered")
    CONV = trig.get("conversation_id")

    t0 = time.time()
    row = None
    while time.time() - t0 < 120:
        code, roster = api("GET", f"{A}/agents")
        rows = roster if isinstance(roster, list) else (roster or {}).get("agents", [])
        row = next((r for r in rows if r.get("name") == AGENT), None)
        if row and row.get("status") not in ("running", "working"):
            break
        time.sleep(3)
    check(row is not None and row.get("status") not in ("running", "working"), f"the turn finished: {row}")

    code, chat = api("GET", f"{A}/agent/{AGENT}/chat/{CONV}")
    show("GET chat", code, chat, limit=3000)
    text_blob = json.dumps(chat)
    check(
        "Scheduled work from agents requires operator approval or an enabled allowance"
        in text_blob,
        "F376's exact refusal sentence appears in the transcript",
    )
    check(
        "403" in text_blob or "create_flow" in text_blob,
        "the transcript names the refused tool / status",
    )

    import sqlite3

    db_path = os.path.expanduser(
        r"~/.agentweave/hub/profiles/trial/agentweave.db"
    )
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    (count_all,) = con.execute(
        "select count(*) from permission_requests where agent = ?", (AGENT,)
    ).fetchone()
    con.close()
    check(count_all == 0, f"permission_requests holds 0 rows for {AGENT} (found {count_all})")

finally:
    code, body = api("DELETE", f"{A}")
    print(f"\nfixture project deleted: {code}")
    import shutil

    shutil.rmtree(root, ignore_errors=True)

print(f"\n{len(PASS)} passed / {len(FAIL)} failed")
for f in FAIL:
    print(f"  FAILED: {f}")
sys.exit(1 if FAIL else 0)
