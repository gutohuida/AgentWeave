"""Record the traces view's fixtures from a Hub database, read-only.

    py -3.11 mock/record_traces.py C:/Users/huida/.agentweave/hub/data/agentweave.db proj-d85a82bf4216

Writes three files into mock/fixtures/:

- traces_runs.json     every run trace: its root's agent, model, task, conversation, outcome, cost,
                       tokens, and the counts the view totals (model calls, tool calls, waits). This
                       is the shape the traces view's route is proposed to return
                       (spec/changes/a-traces-view-with-filters-grouping-and-stats); today's list
                       route carries no cost or tokens, so it is computed here from the spans.
- traces_hub.json      the Hub's own traces (worker calls, requests, events, background work): the
                       newest 200 roots of each kind, plus each kind's total.
- traces_details.json  a handful of whole run traces in the `TraceDetail` shape the trace drawer
                       reads, long strings cut to 400 characters so the file stays small.

The database is opened with `mode=ro`; nothing is written to it.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"
KINDS = {"chat": "worker", "aw.request": "request", "aw.event": "event", "aw.work": "work"}
WAITS = ("aw.ask_user", "aw.permission_wait")
CUT = 400


def iso(value: str | None) -> str | None:
    return value.replace(" ", "T") + "+00:00" if value else None


def cut(value):
    if isinstance(value, str):
        return value if len(value) <= CUT else value[:CUT] + "…"
    if isinstance(value, list):
        return [cut(v) for v in value[:20]]
    if isinstance(value, dict):
        return {k: cut(v) for k, v in value.items()}
    return value


def seconds(start: str, end: str | None) -> float | None:
    if not end:
        return None
    from datetime import datetime

    return (datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()


def main(db: str, project: str) -> None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    tasks = {r["id"]: (r["readable_id"], r["title"]) for r in con.execute("select id, readable_id, title from tasks where project_id=?", (project,))}
    convs = {r["id"]: r["title"] for r in con.execute("select id, title from conversations where project_id=?", (project,))}

    counts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in con.execute(
        "select run_id, operation, start_time, end_time, status from trace_spans "
        "where project_id=? and run_id is not null and parent_span_id is not null",
        (project,),
    ):
        c = counts[r["run_id"]]
        c["spans"] += 1
        if r["operation"] == "chat":
            c["model_calls"] += 1
        elif r["operation"] == "execute_tool":
            c["tool_calls"] += 1
            if r["status"] == "error":
                c["tool_errors"] += 1
        elif r["operation"] in WAITS:
            c["wait_seconds"] += seconds(r["start_time"], r["end_time"]) or 0

    runs = []
    for r in con.execute(
        "select * from trace_spans where project_id=? and parent_span_id is null and operation='invoke_agent' order by start_time desc",
        (project,),
    ):
        a = json.loads(r["attributes"])
        c = counts[r["run_id"]]
        task_id = a.get("aw.task.id")
        conv_id = a.get("gen_ai.conversation.id")
        measured = a.get("aw.usage.status") == "measured" and a.get("aw.usage.api_equivalent_usd_micros") is not None
        runs.append(
            {
                "trace_id": r["trace_id"],
                "run_id": r["run_id"],
                "agent": a.get("gen_ai.agent.name"),
                "model": a.get("gen_ai.response.model") or a.get("gen_ai.request.model"),
                "task_id": task_id,
                "task_ref": tasks.get(task_id, (None, None))[0] if task_id else None,
                "task_title": tasks.get(task_id, (None, None))[1] if task_id else None,
                "conversation_id": conv_id,
                "conversation_title": convs.get(conv_id),
                "initiator": a.get("aw.run.initiator"),
                "run_status": a.get("aw.run.status"),
                "status": r["status"],
                "status_message": cut(r["status_message"]),
                "start_time": iso(r["start_time"]),
                "end_time": iso(r["end_time"]),
                "ended": bool(r["ended"]),
                "cost_usd_micros": a.get("aw.usage.api_equivalent_usd_micros") if measured else None,
                "usage_status": a.get("aw.usage.status"),
                "input_tokens": a.get("gen_ai.usage.input_tokens"),
                "output_tokens": a.get("gen_ai.usage.output_tokens"),
                "cache_read_tokens": a.get("aw.usage.cache_read_tokens"),
                "cache_write_tokens": a.get("aw.usage.cache_write_tokens"),
                "model_calls": int(c["model_calls"]),
                "tool_calls": int(c["tool_calls"]),
                "tool_errors": int(c["tool_errors"]),
                "wait_seconds": round(c["wait_seconds"], 1),
                "span_count": int(c["spans"]) + 1,
            }
        )

    hub: dict[str, dict] = {}
    for op, kind in KINDS.items():
        total = con.execute(
            "select count(*) from trace_spans where project_id=? and parent_span_id is null and run_id is null and operation=?",
            (project, op),
        ).fetchone()[0]
        rows = [
            {
                "trace_id": r["trace_id"],
                "name": r["name"],
                "kind": kind,
                "agent": json.loads(r["attributes"]).get("aw.agent") or json.loads(r["attributes"]).get("gen_ai.agent.name"),
                "status": r["status"],
                "status_message": cut(r["status_message"]),
                "start_time": iso(r["start_time"]),
                "end_time": iso(r["end_time"]),
            }
            for r in con.execute(
                "select * from trace_spans where project_id=? and parent_span_id is null and run_id is null and operation=? order by start_time desc limit 200",
                (project, op),
            )
        ]
        hub[kind] = {"total": total, "traces": rows}

    # Whole traces for the drawer: the newest five runs, and every run counted as an error.
    chosen = [r["run_id"] for r in runs[:5]] + [r["run_id"] for r in runs if r["run_status"] in ("failed", "stopped") or r["status"] == "error"]
    details = {}
    for run_id in dict.fromkeys(chosen):
        spans = [
            {
                "span_id": s["span_id"],
                "trace_id": s["trace_id"],
                "parent_span_id": s["parent_span_id"],
                "name": s["name"],
                "operation": s["operation"],
                "status": s["status"],
                "status_message": cut(s["status_message"]),
                "start_time": iso(s["start_time"]),
                "end_time": iso(s["end_time"]),
                "ended": bool(s["ended"]),
                "attributes": cut(json.loads(s["attributes"])),
                "events": cut(json.loads(s["events"])),
            }
            for s in con.execute("select * from trace_spans where run_id=? order by start_time limit 300", (run_id,))
        ]
        root = next((s for s in spans if s["parent_span_id"] is None), None)
        if not root:
            continue
        details[run_id] = {
            "trace_id": root["trace_id"],
            "kind": "run",
            "run_id": run_id,
            "root": root,
            "spans": [s for s in spans if s is not root],
            "total": len(spans),
            "offset": 0,
            "limit": 500,
        }

    OUT.mkdir(exist_ok=True)
    (OUT / "traces_runs.json").write_text(json.dumps(runs, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "traces_hub.json").write_text(json.dumps(hub, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "traces_details.json").write_text(json.dumps(details, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(runs)} runs, {sum(h['total'] for h in hub.values())} Hub traces, {len(details)} whole traces")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
