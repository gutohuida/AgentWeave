"""Record whole conversations' traces from a Hub database, read-only, for the conversation-trace mock.

    py -3.11 mock/record_conversation_trace.py C:/Users/huida/.agentweave/hub/data/agentweave.db conv-... [conv-...]

Writes mock/fixtures/conversation_traces.json: for each conversation, its title, agent and the
conversation it continued (when it was carried over), each run's row (the shape `traces_runs.json`
uses) and each run's whole trace in the `TraceDetail` shape the drawer reads. Spec
`spec/changes/a-trace-of-a-whole-conversation`. The database is opened with `mode=ro`.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"
WAITS = ("aw.ask_user", "aw.permission_wait")
CUT = 400


def iso(value: str | None) -> str | None:
    return value.replace(" ", "T") + "+00:00" if value else None


def cut(value):
    if isinstance(value, str):
        return value if len(value) <= CUT else value[:CUT] + "…"
    if isinstance(value, dict):
        return {k: cut(v) for k, v in value.items()}
    if isinstance(value, list):
        return [cut(v) for v in value]
    return value


def span(s: sqlite3.Row) -> dict:
    return {
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


def conversation(con: sqlite3.Connection, conv_id: str) -> dict:
    c = con.execute("select * from conversations where id=?", (conv_id,)).fetchone()
    # The conversation this one continued: the one before it in the same lineage.
    before = con.execute(
        "select id, title from conversations where lineage_id=? and created_at < ? order by created_at desc limit 1",
        (c["lineage_id"], c["created_at"]),
    ).fetchone()
    runs, details = [], {}
    for r in con.execute(
        "select * from trace_spans where parent_span_id is null and operation='invoke_agent' and run_id in "
        "(select id from runs where conversation_id=?) order by start_time",
        (conv_id,),
    ):
        spans = [span(s) for s in con.execute("select * from trace_spans where run_id=? order by start_time", (r["run_id"],))]
        root = next(s for s in spans if s["parent_span_id"] is None)
        children = [s for s in spans if s is not root]
        a = root["attributes"]
        measured = a.get("aw.usage.status") == "measured" and a.get("aw.usage.api_equivalent_usd_micros") is not None
        wait = 0.0
        for s in children:
            if s["operation"] in WAITS and s["end_time"]:
                from datetime import datetime

                wait += (datetime.fromisoformat(s["end_time"]) - datetime.fromisoformat(s["start_time"])).total_seconds()
        runs.append(
            {
                "trace_id": root["trace_id"],
                "run_id": r["run_id"],
                "agent": a.get("gen_ai.agent.name"),
                "model": a.get("gen_ai.response.model") or a.get("gen_ai.request.model"),
                "initiator": a.get("aw.run.initiator"),
                "run_status": a.get("aw.run.status"),
                "status": root["status"],
                "status_message": root["status_message"],
                "start_time": root["start_time"],
                "end_time": root["end_time"],
                "ended": root["ended"],
                "cost_usd_micros": a.get("aw.usage.api_equivalent_usd_micros") if measured else None,
                "input_tokens": a.get("gen_ai.usage.input_tokens"),
                "output_tokens": a.get("gen_ai.usage.output_tokens"),
                "model_calls": sum(1 for s in children if s["operation"] == "chat"),
                "tool_calls": sum(1 for s in children if s["operation"] == "execute_tool"),
                "tool_errors": sum(1 for s in children if s["operation"] == "execute_tool" and s["status"] == "error"),
                "wait_seconds": round(wait, 1),
                "span_count": len(spans),
            }
        )
        details[r["run_id"]] = {
            "trace_id": root["trace_id"],
            "kind": "run",
            "run_id": r["run_id"],
            "root": root,
            "spans": children,
            "total": len(spans),
            "offset": 0,
            "limit": 500,
        }
    return {
        "conversation": {
            "id": c["id"],
            "agent": c["agent"],
            "title": c["title"],
            "origin": c["origin"],
            "continued_from": {"id": before["id"], "title": before["title"]} if before else None,
        },
        "runs": runs,
        "details": details,
    }


def main(db: str, conv_ids: list[str]) -> None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    out = {cid: conversation(con, cid) for cid in conv_ids}
    OUT.mkdir(exist_ok=True)
    (OUT / "conversation_traces.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for cid, c in out.items():
        print(cid, len(c["runs"]), "runs", sum(r["span_count"] for r in c["runs"]), "spans")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
