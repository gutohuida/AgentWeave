"""Acceptance drive for `a-run-is-a-trace-you-can-export` (trace-1019) on a scratch Hub.

Real Claude turns on Haiku through the Hub's own routes: one with a tool call and a refusal (a
Write outside the workspace, which Workspace only refuses), one bound to a task, and the
conversation-titles manager job's worker call. Then it reads each run's trace, checks the OTLP
receiver (`otlp_receiver.py`) got the spans, exports the day and clears it.

Usage (after `e2e.py hub-up <profile> <port>` and `e2e.py setup <name>`, with AW_E2E_STATE set
the same way, and `otlp_receiver.py <port> <out.jsonl>` running):
  py -3.11 scripts/drive/d1019_trace_drive.py <project-id> <receiver-port> <receiver.jsonl> [step]
Steps: all (default), turns, check, clear.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

AGENT = "tracer"
SECRET = "aw_live_" + "Dr1v3" * 7


def turns(project: str, port: int) -> None:
    e2e.call(
        "PUT",
        f"/projects/{project}/traces/settings",
        {
            "otlp_endpoint": f"http://127.0.0.1:{port}",
            "otlp_headers": {"Authorization": "Bearer drive-collector"},
            "export_enabled": True,
        },
    )
    e2e.cmd_agent(project, AGENT, "-", "claude", "claude-haiku-5-5")
    e2e.cmd_manager(project, "conversation-titles", "on")
    first = e2e.cmd_turn(
        project,
        AGENT,
        "Do exactly two things, then stop. 1) Use the Bash tool to run: echo trace-drive-ok . "
        "2) Use the Write tool to create the file ../outside-trace-1019.txt (one directory ABOVE "
        "your working directory) containing the word hi. If a step is refused, do not retry it "
        f"and do not ask anything; just say what happened. (Ignore this token: {SECRET})",
        fresh=True,
    )
    print("turn 1:", e2e.wait_for(first, 6))
    task = e2e.call("POST", f"/projects/{project}/tasks", {"title": "Trace a task turn"})
    print("TASK=" + task["id"])
    second = e2e.cmd_turn(
        project,
        AGENT,
        "Use the Bash tool to run: ls . Then reply with one short sentence. Do not change any "
        "task status.",
        task=task["id"],
        fresh=True,
    )
    print("turn 2:", e2e.wait_for(second, 6))
    # The title job fires after a turn; give the worker call a moment.
    time.sleep(40)


def _spans(trace: dict) -> list:
    return trace.get("spans", [])


def check(project: str, receiver: str) -> None:
    listed = e2e.call("GET", f"/projects/{project}/traces?limit=50")["traces"]
    print(f"\n{len(listed)} traces")
    for row in listed:
        print(
            f"  {row['kind']:<6} {row['name']:<40} status={row['status']:<5} "
            f"spans={row['span_count']} run={row['run_id']} worker={row.get('worker_kind')}"
        )
    secret_seen = False
    for row in listed:
        trace = e2e.call("GET", f"/projects/{project}/traces/{row['trace_id']}")
        text = json.dumps(trace)
        secret_seen = secret_seen or SECRET in text
        print(f"\n== {row['name']} ({row['trace_id']})")
        for span in _spans(trace):
            attrs = span["attributes"]
            extra = {
                key: attrs[key]
                for key in (
                    "gen_ai.tool.name",
                    "aw.decision.allowed",
                    "aw.decision.reason",
                    "aw.decision.source",
                    "gen_ai.usage.input_tokens",
                    "gen_ai.usage.output_tokens",
                    "aw.task.id",
                    "aw.worker.kind",
                )
                if key in attrs
            }
            print(
                f"   {span['operation']:<18} {span['name'][:40]:<40} {span['status']:<5} "
                f"parent={span['parent_span_id']} ended={span['ended']} {json.dumps(extra)[:220]}"
            )
            for event in span.get("events", []):
                print(f"      event {event['name']}")
    print("\nsecret present in any trace:", secret_seen)
    pushed = []
    for line in pathlib.Path(receiver).read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        body = record.get("body") or {}
        for resource in body.get("resourceSpans", []):
            for scope in resource["scopeSpans"]:
                pushed.extend(scope["spans"])
        auth = record["authorization_present"]
    pushed_traces = {span["traceId"] for span in pushed}
    print(f"receiver got {len(pushed)} spans in {len(pushed_traces)} traces; auth header: {auth}")
    print(
        "every listed trace pushed:",
        {row["trace_id"] for row in listed if row["ended"]} <= pushed_traces,
    )
    print("secret in pushed spans:", SECRET in json.dumps(pushed))
    settings = e2e.call("GET", f"/projects/{project}/traces/settings")
    print("settings:", json.dumps(settings))


def clear(project: str) -> None:
    today = datetime.date.today()
    window = f"since={today.isoformat()}&until={(today + datetime.timedelta(days=1)).isoformat()}"
    status, exported = e2e.request("GET", f"/projects/{project}/traces/export?{window}")
    spans = [
        span
        for resource in exported["resourceSpans"]
        for scope in resource["scopeSpans"]
        for span in scope["spans"]
    ]
    print(f"export {status}: {len(spans)} spans, {len({s['traceId'] for s in spans})} traces")
    status, result = e2e.request("DELETE", f"/projects/{project}/traces?{window}")
    print(f"clear {status}: {result}")
    status, after = e2e.request("GET", f"/projects/{project}/traces/export?{window}")
    left = [s for r in after["resourceSpans"] for sc in r["scopeSpans"] for s in sc["spans"]]
    print(f"export after clear: {len(left)} spans")
    outputs = e2e.ro().execute(
        "select count(*) from agent_outputs where project_id=?", (project,)
    ).fetchone()[0]
    print("agent_outputs kept:", outputs)


if __name__ == "__main__":
    project_id, receiver_port, receiver_file = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    step = sys.argv[4] if len(sys.argv) > 4 else "all"
    if step in ("all", "turns"):
        turns(project_id, receiver_port)
    if step in ("all", "check"):
        time.sleep(5)
        check(project_id, receiver_file)
    if step in ("all", "clear"):
        clear(project_id)
