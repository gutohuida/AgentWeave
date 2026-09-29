"""Task 3.2 drive for request-agent-models-the-new-agent-on-one-the-operator-made (F378).

Creates a Haiku agent bound to a runner and a charter, with the evidence grant switched on, and asks
it to call `request_agent` with itself as the template. Then checks, from the operator side and the
trial database (read-only), that the new agent exists with the template's runner and charter, holds
no grant and no posture, ran one turn, and that the template's transcript shows the 201.

Run: AW_HUB=http://127.0.0.1:8010 AW_KEY=... AW_PROJECT=... AW_DB=<sqlite path> \
     AW_RUNNER=<haiku runner id> AW_CHARTER=<charter id> \
     py -3.11 scripts/drive/d0929_f378_request_agent_template.py
"""

import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

from aw import api, require_hub, require_key  # noqa: E402

require_hub()
require_key()
PROJ = os.environ["AW_PROJECT"]
RUNNER = os.environ["AW_RUNNER"]
CHARTER = os.environ["AW_CHARTER"]
TAG = os.environ.get("DRIVE_TAG", time.strftime("%H%M%S"))
A = f"/projects/{PROJ}"
TEMPLATE = f"r7model{TAG}"
CHILD = f"r7child{TAG}"
PONG = f"PONG-R7-{TAG}"

FAILURES = []


def check(label, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {str(detail)[:300]}" if detail else ""))
    if not ok:
        FAILURES.append((label, detail))


def db():
    return sqlite3.connect(f"file:{os.environ['AW_DB']}?mode=ro", uri=True)


def agent_row(name):
    c, rows = api("GET", f"{A}/agents")
    rows = rows if isinstance(rows, list) else rows.get("agents", [])
    return next((r for r in rows if r.get("name") == name), None)


def wait_runs(agent, n, timeout=300):
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = (
            db()
            .execute(
                "select id,status from runs where project_id=? and agent=? order by started_at",
                (PROJ, agent),
            )
            .fetchall()
        )
        done = [r for r in rows if r[1] not in ("running", "queued", "pending", "starting")]
        if len(done) >= n:
            return rows
        time.sleep(5)
    return rows


c, b = api("POST", f"{A}/agents", {"name": TEMPLATE, "runner_id": RUNNER})
check("template agent created", c == 201, b)
c, b = api("PATCH", f"{A}/agents/{TEMPLATE}", {"charter_id": CHARTER, "can_accept_evidence": True})
check("template given a charter and the evidence grant", c == 200, b)

message = (
    f"Call the AgentWeave tool request_agent exactly once with name='{CHILD}', "
    f"template='{TEMPLATE}', task='Reply with the single word {PONG} and stop.'. "
    "Then reply with the tool's result verbatim (its full JSON) and stop. Do nothing else."
)
c, t = api("POST", f"{A}/agent/trigger", {"agent": TEMPLATE, "session_mode": "new", "message": message})
check("template triggered", c in (200, 201, 202), t)

rows = wait_runs(TEMPLATE, 1)
check("template's run finished", rows and rows[0][1] == "completed", rows)
template_run = rows[0][0] if rows else None

outputs = (
    db()
    .execute(
        "select kind,content,payload from agent_outputs where run_id=? order by sequence",
        (template_run,),
    )
    .fetchall()
)
print("\n--- template transcript, verbatim ---")
for kind, content, payload in outputs:
    print(f"  {kind}: {str(content)[:400]}  {str(payload)[:600]}")
results = [
    json.loads(p)
    for k, _, p in outputs
    if k == "tool_result" and p and '"status\\":\\"queued\\"' in p
]
check("template called mcp__agentweave__request_agent", any(
    k == "tool_use" and "mcp__agentweave__request_agent" in str(p) for k, _, p in outputs
))
check("the tool answered the 201 body, status queued", bool(results))
check("no 'not pre-approved' refusal", all("not pre-approved" not in str(p) for _, _, p in outputs))

child = agent_row(CHILD)
check("child appears on the roster", child is not None)
if child:
    row = (
        db()
        .execute(
            "select runner_id,charter_id,created_by_run_id,can_accept_evidence,can_read_checkpoints,"
            "can_recall,default_permission_mode,config from agents where project_id=? and name=?",
            (PROJ, CHILD),
        )
        .fetchone()
    )
    print("child row:", row)
    runner_id, charter_id, by_run, ev, ck, rc, posture, config = row
    config = json.loads(config or "{}")
    check("child's runner is the template's", runner_id == RUNNER, runner_id)
    check("child's charter is the template's", charter_id == CHARTER, charter_id)
    check("child was created by the template's run", by_run == template_run, by_run)
    check("no grant inherited", not ev and not ck and not rc, (ev, ck, rc))
    check("no posture inherited", posture is None, posture)
    check("no yolo/hub_client in config", not config.get("yolo") and "hub_client" not in config, config)

    crows = wait_runs(CHILD, 1)
    check("child ran one turn to completion", crows and crows[0][1] == "completed", crows)
    if crows:
        cout = "\n".join(
            str(r[0])
            for r in db().execute(
                "select content from agent_outputs where run_id=? order by sequence", (crows[0][0],)
            )
        )
        check("child's turn answered its task", PONG in cout, cout[-300:])

print("\n--- summary ---")
if FAILURES:
    for label, detail in FAILURES:
        print(f"FAIL: {label} ({str(detail)[:200]})")
    sys.exit(1)
print("All checks passed.")
