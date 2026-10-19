"""Acceptance drive for `everything-the-hub-does-is-in-a-trace` (trace-hub-wide) on a scratch Hub.

Built a slice at a time; each step drives what its slice built through the Hub's real routes, with
the real lifespan writer (nothing here calls `flush_spans`), and reads the result back through the
trace routes.

  requests (slice 1): the operator creates a task, polls the list, reads a task that does not
      exist; the POST and the 404 are request traces with their route templates, the poll is not;
      with `record_reads` on, the poll is. Then a real Haiku turn calls a Hub MCP tool, and the
      request its tool server made is a span in the run's trace, under that tool call.
  events (slice 2): the event a request emits is a span event on its request's span; the events a
      real run's executor emits are on the run's root; an event with neither is an `aw.event`
      trace of its own. Every event row of the window is found in some trace.

Usage (after `e2e.py hub-up <profile> <port>` and `e2e.py setup <name>`):
  py -3.11 scripts/drive/d1020_hub_wide_trace_drive.py <project-id> [step]
Steps: all (default), requests, nested, events.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop"))
import e2e  # noqa: E402

AGENT = "tracer"
#: Longer than the writer's interval (1 s), so what was recorded has been written.
SETTLE = 3


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _requests(project: str, since: str) -> list:
    """The request traces' roots that started at or after *since*, so a rerun on the same project
    reads only its own (a step that turned `record_reads` on left polls behind)."""
    listed = e2e.call("GET", f"/projects/{project}/traces?operation=aw.request&limit=200")
    out = []
    for row in listed["traces"]:
        trace = e2e.call("GET", f"/projects/{project}/traces/{row['trace_id']}")
        if trace["root"]["start_time"] >= since:
            out.append(trace["root"])
    return out


def _show(spans: list) -> None:
    for span in spans:
        a = span["attributes"]
        print(
            f"   {a.get('http.request.method'):<6} {a.get('http.route')} -> "
            f"{a.get('http.response.status_code')} actor={a.get('aw.actor')} "
            f"status={span['status']} ms={_ms(span)}"
        )


def _ms(span: dict) -> int:
    from datetime import datetime

    start = datetime.fromisoformat(span["start_time"])
    end = datetime.fromisoformat(span["end_time"]) if span["end_time"] else start
    return int((end - start).total_seconds() * 1000)


def requests(project: str) -> None:
    since = _now()
    created =e2e.call("POST", f"/projects/{project}/tasks", {"title": "Hub-wide trace drive"})
    for _ in range(5):
        e2e.call("GET", f"/projects/{project}/tasks")
    missing = e2e.cmd_api("GET", f"/projects/{project}/tasks/task-000000000000")
    time.sleep(SETTLE)
    spans = _requests(project, since)
    print(f"\n[1] request traces after POST, 5 polls and a 404: {len(spans)}")
    _show(spans)
    routes = [(s["attributes"]["http.request.method"], s["attributes"]["http.route"]) for s in spans]
    print("  POST /tasks recorded:", ("POST", "/api/v1/projects/{project_id}/tasks") in routes)
    print("  404 recorded:", any(s["attributes"]["http.response.status_code"] == 404 for s in spans))
    print("  poll recorded (must be False):", ("GET", "/api/v1/projects/{project_id}/tasks") in routes)
    settings = e2e.call("GET", f"/projects/{project}/traces/settings")
    print("  settings:", json.dumps({k: settings.get(k) for k in ("record_reads", "dropped_spans", "spans_by_operation")}))
    del created, missing

    e2e.call("PUT", f"/projects/{project}/traces/settings", {"record_reads": True})
    since = _now()
    e2e.call("GET", f"/projects/{project}/tasks")
    time.sleep(SETTLE)
    polls = [
        s for s in _requests(project, since)
        if s["attributes"]["http.request.method"] == "GET"
        and s["attributes"]["http.route"].endswith("/tasks")
    ]
    print(f"\n[2] with record_reads on, polls recorded: {len(polls)} (expect >= 1)")
    e2e.call("PUT", f"/projects/{project}/traces/settings", {"record_reads": False})


def nested(project: str) -> None:
    print("\n[3] a real Haiku turn calling a Hub MCP tool")
    e2e.cmd_agent(project, AGENT, "-", "claude", "claude-haiku-4-5-20251001")
    run = e2e.cmd_turn(
        project,
        AGENT,
        "Call the AgentWeave MCP tool that lists this project's tasks (list_tasks or the closest "
        "one), once. Then reply with the number of tasks in one short sentence. Do not change "
        "anything and do not ask anything.",
        fresh=True,
    )
    print("  turn:", e2e.wait_for(run, 6))
    time.sleep(SETTLE)
    trace = e2e.call("GET", f"/projects/{project}/traces/by-run/{run}?limit=2000")
    spans = trace["spans"]
    by_id = {s["span_id"]: s for s in spans}
    tools = [s for s in spans if s["operation"] == "execute_tool"]
    reqs = [s for s in spans if s["operation"] == "aw.request"]
    print(f"  run trace: {len(spans)} spans, {len(tools)} tool calls, {len(reqs)} requests")
    for s in tools:
        print(f"   tool {s['name']} span={s['span_id']} ended={s['ended']}")
    for s in reqs:
        parent = by_id.get(s["parent_span_id"], {})
        a = s["attributes"]
        print(
            f"   request {a.get('http.request.method')} {a.get('http.route')} -> "
            f"{a.get('http.response.status_code')} actor={a.get('aw.actor')} "
            f"parent={parent.get('operation')} {parent.get('name')}"
        )
    nested = [
        s for s in reqs if by_id.get(s["parent_span_id"], {}).get("operation") == "execute_tool"
    ]
    print("  a request nested under a tool call:", bool(nested))
    own = [s for s in _requests(project, "") if s["attributes"].get("aw.actor") == "run"]
    print("  run requests that are traces of their own (must be 0):", len(own))
    settings = e2e.call("GET", f"/projects/{project}/traces/settings")
    print("  settings:", json.dumps({k: settings.get(k) for k in ("dropped_spans", "spans_by_operation")}))


def _all_spans(project: str, operation: str, since: str) -> list:
    listed = e2e.call("GET", f"/projects/{project}/traces?operation={operation}&limit=200")
    out = []
    for row in listed["traces"]:
        trace = e2e.call("GET", f"/projects/{project}/traces/{row['trace_id']}?limit=2000")
        if trace["root"]["start_time"] >= since:
            out.extend(trace["spans"])
    return out


def events(project: str) -> None:
    since = _now()
    created = e2e.call("POST", f"/projects/{project}/tasks", {"title": "Event drive"})
    time.sleep(SETTLE)
    [post] = [
        s for s in _requests(project, since)
        if s["attributes"]["http.request.method"] == "POST"
        and s["attributes"]["http.route"].endswith("/tasks")
    ]
    names = [e["name"] for e in post["events"]]
    print(f"\n[4] POST /tasks request span events: {names} (expect task_created)")

    print("\n[5] a real Haiku turn: its executor's events")
    e2e.cmd_agent(project, AGENT, "-", "claude", "claude-haiku-4-5-20251001")
    run = e2e.cmd_turn(project, AGENT, "Reply with the single word: done.", fresh=True)
    print("  turn:", e2e.wait_for(run, 6))
    time.sleep(SETTLE)
    trace = e2e.call("GET", f"/projects/{project}/traces/by-run/{run}?limit=2000")
    [root] = [s for s in trace["spans"] if s["parent_span_id"] is None]
    print("  run root events:", [e["name"] for e in root["events"]])
    for s in trace["spans"]:
        if s["operation"] == "aw.request" and s["events"]:
            print(f"  run request {s['name']} events:", [e["name"] for e in s["events"]])

    print("\n[6] every event row of the window is in a trace")
    spans = []
    for operation in ("aw.request", "aw.event", "invoke_agent"):
        spans += _all_spans(project, operation, since)
    traced = {
        e["attributes"].get("aw.event.id") for s in spans for e in s["events"]
    } - {None}
    own = [s for s in spans if s["operation"] == "aw.event"]
    print("  aw.event traces of their own:", sorted({s["name"] for s in own}))
    from datetime import datetime, timezone

    def _at(value) -> datetime:
        at = datetime.fromisoformat(str(value).replace(" ", "T"))
        return at if at.tzinfo else at.replace(tzinfo=timezone.utc)

    rows = [
        (r["id"], r["event_type"])
        for r in e2e.ro().execute(
            "SELECT id, event_type, timestamp FROM event_logs WHERE project_id = ?", (project,)
        )
        if _at(r["timestamp"]) >= _at(since)
    ]
    missing = [r for r in rows if r[0] not in traced]
    print(f"  event rows in the window: {len(rows)}, in a trace: {len(rows) - len(missing)}")
    print("  missing (must be empty):", missing)
    settings = e2e.call("GET", f"/projects/{project}/traces/settings")
    print("  settings:", json.dumps({k: settings.get(k) for k in ("dropped_spans", "spans_by_operation")}))
    del created


def main() -> None:
    project = sys.argv[1]
    step = sys.argv[2] if len(sys.argv) > 2 else "all"
    if step in ("requests", "all"):
        requests(project)
    if step in ("nested", "all"):
        nested(project)
    if step in ("events", "all"):
        events(project)
    if step not in ("requests", "nested", "events", "all"):
        raise SystemExit(f"unknown step {step}")


if __name__ == "__main__":
    main()
