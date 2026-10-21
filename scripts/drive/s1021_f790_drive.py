"""F790 acceptance drive (scratch Hub :8152, profile f790): a real Haiku turn under `manual`
runs a command carrying a token only the high-entropy catch-all knows; the operator approves the
card; the run's `aw.permission_wait` span must redact it as its `execute_tool` span does, in the
route and in the day's OTLP export. The permission row keeps the raw input (the card needs it).

    AW_E2E_STATE=~/.agentweave/e2e-f790.json AW_P=<project> py -3.11 scripts/drive/s1021_f790_drive.py
"""

import json
import os
import pathlib
import sys
import time
from datetime import datetime, timedelta, timezone

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-f790.json")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

TOKEN = "Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4"
P = os.environ["AW_P"]
LIVE = ("running", "queued", "starting", "pending")


def ro(sql, args=()):
    c = e2e.ro()
    try:
        return [dict(r) for r in c.execute(sql, args)]
    finally:
        c.close()


status, res = e2e.request(
    "POST",
    f"/projects/{P}/agent/trigger",
    {
        "agent": "tracer",
        "message": "Run exactly this one shell command and nothing else, then reply with its output: "
        f"py -3.11 -c \"print('build', '{TOKEN}')\"",
        "overrides": {"permission_mode": "manual"},
    },
)
print("trigger", status, res)
run = res["run_id"]
deadline = time.time() + 300
while time.time() < deadline:
    rows = ro("select status from runs where id=?", (run,))
    if rows and rows[0]["status"] not in LIVE:
        break
    _, pending = e2e.request("GET", f"/projects/{P}/permission-requests")
    for item in pending if isinstance(pending, list) else []:
        if item.get("run_id") == run and item.get("status") == "pending":
            print("card", item["tool_name"], TOKEN in json.dumps(item.get("tool_input")))
            print("decide", e2e.request("POST", f"/projects/{P}/permission-requests/{item['id']}/decide", {"allow": True})[0])
    time.sleep(3)
print("run", ro("select status, error from runs where id=?", (run,)))
time.sleep(2)
_, trace = e2e.request("GET", f"/projects/{P}/traces/by-run/{run}?limit=2000")
for span in trace["spans"]:
    if span["operation"] in ("execute_tool", "aw.permission_wait"):
        args = span["attributes"].get("gen_ai.tool.call.arguments") or ""
        print(span["operation"], span["attributes"].get("gen_ai.tool.call.id"), "| token in args:", TOKEN in args, "|", args[:160])
print("token anywhere in trace:", TOKEN in json.dumps(trace))
today = datetime.now(timezone.utc).date()
_, exported = e2e.request(
    "GET", f"/projects/{P}/traces/export?since={today.isoformat()}&until={(today + timedelta(days=1)).isoformat()}"
)
# The prompt and model text carry the token as the conversation's own text rows do (FR-3 is
# "the redaction recorded output passes"), so only the two tool-call spans are checked.
for resource in exported["resourceSpans"]:
    for scope in resource["scopeSpans"]:
        for span in scope["spans"]:
            if span["name"].startswith(("aw.permission_wait", "execute_tool")):
                attrs = {a["key"]: a["value"] for a in span["attributes"]}
                print("export", span["name"], "| token in args:", TOKEN in json.dumps(attrs.get("gen_ai.tool.call.arguments")))
rows = ro("select tool_name, tool_input, status from permission_requests where run_id=?", (run,))
print("permission rows keep raw input:", [(r["tool_name"], r["status"], TOKEN in (r["tool_input"] or "")) for r in rows])
