"""Record the build view's fixtures from a Hub database, read-only.

    py -3.11 mock/record_builds.py C:/Users/huida/.agentweave/hub/data/agentweave.db proj-d85a82bf4216

Writes two files into mock/fixtures/:

- builds.json         a handful of real builds in the `BuildRead` shape the build view's read route is
                      proposed to return (src/components/builds/buildViewModel.ts): each task in the
                      order its document declares them, then the tasks added later; per task its
                      runs (role, model, cost or unpriced, the moves it made) and its send-backs
                      (who, reason class, reason), its requirements' evidence and whether it needs
                      the operator; and the runs of the build that worked no single task.
- builds_traces.json  whole run traces (`TraceDetail`) for the runs of a few tasks, so the trace
                      drawer opens on something real. Long strings are cut to 400 characters.

The run set follows `work_tally` (hub/hub/work_tally.py): a run belongs to a task when it names the
task, or when it ran in the conversation of a stall on that task (the mender); a run in a stall on
the build's loop, or in its lead's conversation, belongs to the build but to no single task. A run's
role is `work_tally.run_role` restated: the mender's, a lead's, a delivered review's, else review
when the task was awaiting a verdict from someone else, else build.

The database is opened with `mode=ro`; nothing is written to it.
"""

from __future__ import annotations

import bisect
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).parent / "fixtures"
CUT = 400

# The builds to record and why: one of each case the view must draw.
BUILDS = {
    "build-e36c054f9e59": "running, a stall the mender fixed, unpriced runs, a task added later",
    "build-04e780a89c1c": "finished, sent back by its reviewer and by the landing checks, then rebuilt",
    "build-76f63278bad5": "finished clean: no send-back",
    "build-aba36d302a01": "finished long: 55 runs, mender turns, unpriced runs, a task added later",
    "build-3ec8eec2d018": "a task the mender gave up on (stalled)",
    "build-72ca7e65a6cf": "the densest: 138 runs and 64 send-backs over 7 tasks",
}
TRACE_TASKS_PER_BUILD = 1
TRACE_SPANS = 80
AWAITING_VERDICT = ("completed", "under_review")
SEND_BACKS = ("revision_needed", "rejected")


def iso(value: str | None) -> str | None:
    return value.replace(" ", "T") + "+00:00" if value else None


def when(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc) if value else None


def cut(value):
    if isinstance(value, str):
        return value if len(value) <= CUT else value[:CUT] + "…"
    if isinstance(value, list):
        return [cut(v) for v in value[:20]]
    if isinstance(value, dict):
        return {k: cut(v) for k, v in value.items()}
    return value


def declared_keys(checkout: Path, path: str | None) -> list[str]:
    """The task keys in the order the build's document declares them, read from the checkout."""
    if not path:
        return []
    candidates = [checkout / path]
    name = Path(path).parent.name
    candidates += sorted((checkout / "spec").glob(f"**/{name}/spec.json"))
    for file in candidates:
        if file.is_file():
            payload = json.loads(file.read_text(encoding="utf-8"))
            return [t["key"] for t in payload.get("tasks") or [] if t.get("key")]
    return []


def record(con: sqlite3.Connection, project: str, build_id: str, checkout: Path) -> dict:
    b = con.execute("select * from builds where id=? and project_id=?", (build_id, project)).fetchone()
    doc = con.execute("select id, title, path from spec_documents where id=?", (b["document_id"],)).fetchone()
    tasks = con.execute("select * from tasks where build_id=? order by created_at", (build_id,)).fetchall()
    task_ids = [t["id"] for t in tasks]
    marks = ",".join("?" * len(task_ids)) or "''"

    menders = {
        r["name"]
        for r in con.execute("select name, config from agents where project_id=?", (project,))
        if json.loads(r["config"] or "{}").get("hub_role") == "mender"
    }
    history: dict[str, list] = {tid: [] for tid in task_ids}
    for r in con.execute(f"select * from task_transitions where task_id in ({marks}) order by sequence", task_ids):
        history[r["task_id"]].append(r)
    review_runs = {
        r[0]
        for r in con.execute(
            f"select delivered_in_run_id from inbound_queue_entries where review_task_id in ({marks}) and delivered_in_run_id is not null",
            task_ids,
        )
    }
    stalls = con.execute(
        f"select * from stalls where conversation_id is not null and (task_id in ({marks}) or (task_id is null and loop_id=?)) order by first_seen_at",
        [*task_ids, b["loop_id"] or ""],
    ).fetchall()

    def status_at(tid: str, at: datetime) -> str | None:
        rows = history.get(tid) or []
        times = [when(r["created_at"]) for r in rows]
        i = bisect.bisect_right(times, at)
        return rows[i - 1]["to_status"] if i else (rows[0]["from_status"] if rows else None)

    def completer_before(tid: str, at: datetime) -> str | None:
        found = None
        for r in history.get(tid) or []:
            if when(r["created_at"]) > at:
                break
            if r["to_status"] == "completed":
                found = r["actor_agent"]
        return found

    def role_of(run, tid: str | None) -> str:
        if run["agent"] in menders:
            return "mender"
        if b["lead_conversation_id"] and run["conversation_id"] == b["lead_conversation_id"]:
            return "lead"
        if run["id"] in review_runs:
            return "review"
        if tid:
            started = when(run["started_at"])
            if status_at(tid, started) in AWAITING_VERDICT and run["agent"] != completer_before(tid, started):
                return "review"
        return "build"

    def run_row(run, tid: str | None) -> dict:
        usage = con.execute("select * from turn_usage where run_id=?", (run["id"],)).fetchone()
        if run["status"] == "running":
            state = "running"
        elif usage is None:
            state = "unreported"
        elif usage["api_equivalent_usd_micros"] is None:
            state = "unpriced"
        else:
            state = "measured"
        moves = [
            {"from": r["from_status"], "to": r["to_status"]}
            for r in con.execute("select from_status, to_status from task_transitions where run_id=? order by sequence", (run["id"],))
        ]
        mend = None
        if run["agent"] in menders and run["conversation_id"]:
            mine = [s for s in stalls if s["conversation_id"] == run["conversation_id"] and when(s["first_seen_at"]) <= when(run["started_at"])]
            stall = mine[-1] if mine else None
            if stall is not None:
                mend = {"cause": stall["cause"], "outcome": stall["outcome"], "detail": cut(stall["outcome_detail"])}
        return {
            "id": run["id"],
            "role": role_of(run, tid),
            "agent": run["agent"],
            "model": usage["model"] if usage else None,
            "conversation_id": run["conversation_id"],
            "started_at": iso(run["started_at"]),
            "ended_at": iso(run["ended_at"]),
            "status": run["status"],
            "cost_state": state,
            "cost_usd_micros": usage["api_equivalent_usd_micros"] if usage and state == "measured" else None,
            "tokens": (
                {
                    "input": usage["input_tokens"],
                    "output": usage["output_tokens"],
                    "cache_read": usage["cache_read_tokens"],
                    "cache_write": usage["cache_write_tokens"],
                }
                if usage and usage["status"] == "measured"
                else None
            ),
            "moves": moves,
            "mend": mend,
        }

    # Each run once: a run naming a task, then a run in a stall's conversation (task or build-wide).
    seen: set[str] = set()
    runs_of: dict[str | None, list[dict]] = {tid: [] for tid in task_ids}
    runs_of[None] = []
    for r in con.execute(f"select * from runs where task_id in ({marks}) order by started_at", task_ids):
        seen.add(r["id"])
        runs_of[r["task_id"]].append(run_row(r, r["task_id"]))
    stall_task = {}
    for s in stalls:
        stall_task.setdefault(s["conversation_id"], s["task_id"])
    convs = list(stall_task) + ([b["lead_conversation_id"]] if b["lead_conversation_id"] else [])
    if convs:
        cmarks = ",".join("?" * len(convs))
        for r in con.execute(f"select * from runs where conversation_id in ({cmarks}) order by started_at", convs):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            tid = stall_task.get(r["conversation_id"])
            runs_of[tid if tid in runs_of else None].append(run_row(r, tid))
    for rows in runs_of.values():
        rows.sort(key=lambda row: row["started_at"])

    evidence: dict[tuple[str, str], str] = {}
    for r in con.execute(
        f"select e.task_id, q.identifier, e.review_state from requirement_evidence e join spec_requirements q on q.id=e.requirement_id "
        f"where e.task_id in ({marks}) and e.artifact_removed_at is null order by e.produced_at",
        task_ids,
    ):
        evidence[(r["task_id"], r["identifier"])] = r["review_state"]
    served: dict[str, list[str]] = {tid: [] for tid in task_ids}
    for r in con.execute(
        f"select l.task_id, q.identifier from task_requirement_links l join spec_requirements q on q.id=l.requirement_id where l.task_id in ({marks})",
        task_ids,
    ):
        served[r["task_id"]].append(r["identifier"])
    for tid, ident in evidence:
        if ident not in served[tid]:
            served[tid].append(ident)

    def fr_order(ident: str) -> tuple:
        head, _, n = ident.partition("-")
        return (head, int(n) if n.isdigit() else 0, ident)

    questions = {
        r["blocked_task_id"]: r["question"]
        for r in con.execute(
            f"select blocked_task_id, question from questions where blocked_task_id in ({marks}) and answered=0 and coalesce(declined,0)=0",
            task_ids,
        )
    }

    def needs(t) -> dict | None:
        if t["status"] in ("approved", "rejected"):
            return None
        if t["id"] in questions:
            return {"kind": "question", "text": cut(questions[t["id"]])}
        mine = [s for s in stalls if s["task_id"] == t["id"]]
        open_ = [s for s in mine if s["ended_at"] is None]
        if open_:
            return {"kind": "stalled", "text": cut(open_[-1]["reason"])}
        if mine and mine[-1]["outcome"] == "gave_up":
            return {"kind": "gave-up", "text": cut(mine[-1]["outcome_detail"] or mine[-1]["reason"])}
        return None

    keys = declared_keys(checkout, doc["path"])
    rank = {k: i for i, k in enumerate(keys)}
    declared = [t for t in tasks if t["spec_task_key"] in rank]
    declared.sort(key=lambda t: rank[t["spec_task_key"]])
    later = [t for t in tasks if t["spec_task_key"] not in rank]

    out_tasks = []
    for t in [*declared, *later]:
        hist = history[t["id"]]
        out_tasks.append(
            {
                "id": t["id"],
                "ref": t["readable_id"],
                "title": t["title"],
                "status": t["status"],
                "declared": t["spec_task_key"] in rank,
                "builder": t["builder"] or t["assignee"],
                "checker": t["checker"],
                "last_change_at": iso(hist[-1]["created_at"] if hist else t["updated"]),
                "needs_operator": needs(t),
                "requirements": [
                    {"identifier": i, "evidence": evidence.get((t["id"], i), "missing")} for i in sorted(served[t["id"]], key=fr_order)
                ],
                "runs": runs_of[t["id"]],
                "send_backs": [
                    {
                        "sequence": r["sequence"],
                        "at": iso(r["created_at"]),
                        "to": r["to_status"],
                        "by": (
                            {"kind": "agent", "agent": r["actor_agent"]}
                            if r["actor_kind"] == "run" and r["actor_agent"]
                            else {"kind": "checks"} if r["origin"] == "checks" else {"kind": "operator"}
                        ),
                        "run_id": r["run_id"],
                        "reason_class": r["reason_class"],
                        "reason": r["reason"] or "",
                        "note": r["note"] or "",
                    }
                    for r in hist
                    if r["to_status"] in SEND_BACKS
                ],
            }
        )

    return {
        "build": {
            "id": b["id"],
            "document_id": doc["id"],
            "document_title": doc["title"],
            "document_path": doc["path"],
            "state": b["state"],
            "level": b["level"],
            "created_at": iso(b["created_at"]),
            "stopped_at": iso(b["stopped_at"]),
            "stop_reason": b["stop_reason"],
        },
        "tasks": out_tasks,
        "build_runs": runs_of[None],
        "as_of": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def traces_for(con: sqlite3.Connection, run_ids: list[str]) -> dict:
    details = {}
    for run_id in run_ids:
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
            for s in con.execute("select * from trace_spans where run_id=? order by start_time limit ?", (run_id, TRACE_SPANS))
        ]
        root = next((s for s in spans if s["parent_span_id"] is None), None)
        if not root:
            continue
        total = con.execute("select count(*) from trace_spans where run_id=?", (run_id,)).fetchone()[0]
        details[run_id] = {
            "trace_id": root["trace_id"],
            "kind": "run",
            "run_id": run_id,
            "root": root,
            "spans": [s for s in spans if s is not root],
            "total": total,
            "offset": 0,
            "limit": 500,
        }
    return details


def main(db: str, project: str) -> None:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    checkout = Path(con.execute("select working_directory from projects where id=?", (project,)).fetchone()[0])
    builds = [record(con, project, build_id, checkout) for build_id in BUILDS]
    # Whole traces for the tasks a review opens first: those with the most send-backs.
    trace_runs: list[str] = []
    for read in builds:
        busiest = sorted(read["tasks"], key=lambda t: -len(t["send_backs"]))[:TRACE_TASKS_PER_BUILD]
        trace_runs += [r["id"] for t in busiest for r in t["runs"]]
    traces = traces_for(con, trace_runs)
    OUT.mkdir(exist_ok=True)
    (OUT / "builds.json").write_text(json.dumps(builds, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "builds_traces.json").write_text(json.dumps(traces, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for read in builds:
        runs = sum(len(t["runs"]) for t in read["tasks"]) + len(read["build_runs"])
        print(f"{read['build']['id']}: {len(read['tasks'])} tasks, {runs} runs ({len(read['build_runs'])} build-wide) - {BUILDS[read['build']['id']]}")
    print(f"{len(traces)} whole traces")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
