"""Shared helpers for the 2026-10-23 Logs, events & SSE drive (scratch Hub :8119, profile ev1023).

    AW_E2E_STATE=... py -3.11 scripts/drive/s1023_ev_sse_lib.py GET /health
"""

import importlib.util
import json
import os
import pathlib
import sys
import time

os.environ.setdefault(
    "AW_E2E_STATE", "C:/Users/huida/Documents/projects/AgentWeave/testbed/e2e-state-ev1023.json"
)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = os.environ.get("AW_P", "proj-c01bff86cc78")
B = f"/projects/{P}"
HAIKU = "claude-haiku-4-5-20251001"
SLEEP_CMD = 'py -3.11 -c "import time; [time.sleep(1) for i in range(120)]"'


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=3000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(f"{method} {path} -> {status}\n{text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def trigger(agent, message, perm="workspace", conversation=None, project=None):
    body = {"agent": agent, "message": message, "overrides": {"permission_mode": perm}}
    if conversation:
        body["conversation_id"] = conversation
    status, res = req("POST", f"/projects/{project or P}/agent/trigger", body)
    print("trigger", status, json.dumps(res)[:300])
    return res.get("run_id") if isinstance(res, dict) else None


def wait_status(run_id, statuses, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        rows = q("select status, pid from runs where id=?", run_id)
        if rows and rows[0]["status"] in statuses:
            return rows[0]
        time.sleep(2)
    return q("select status, pid from runs where id=?", run_id)


def wait_tool_call(run_id, timeout=150):
    """Until the run has a tool_use with no tool_result after it (the tool call is in flight)."""
    end = time.time() + timeout
    while time.time() < end:
        kinds = [r["kind"] for r in q("select kind from agent_outputs where run_id=? order by sequence", run_id)]
        if "tool_use" in kinds and "tool_result" not in kinds[kinds.index("tool_use"):]:
            return True
        st = q("select status from runs where id=?", run_id)
        if st and st[0]["status"] not in ("running", "queued", "starting", "pending"):
            return False
        time.sleep(2)
    return False


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=20000)
