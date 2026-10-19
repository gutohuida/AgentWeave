"""Shared helpers for the 2026-10-19 Copilot stall drive (scratch Hub :8110, profile c1019cop).
Loads the e2e harness with this drive's own state file.

    py -3.11 scripts/drive/c1019_copilot_lib.py GET /projects/<p>/runners

Drive log (2026-10-19, home, licensed work account, Copilot CLI 1.0.91 as the Hub runs it,
claude-haiku-4.5, ~19 session/prompt requests in all):
- s1 baseline: plain turn 6.1 s, task turn 15.6 s (edit + pytest), held. Cold start per turn
  ~4 s before the prompt is sent (spawn 0.6 s, ACP ready +1.4 s, Hub MCP server +1.7-2.2 s),
  the same for new and resumed sessions. One task turn recorded its thinking block twice (D).
- s2 refusal: outside-path read refused, continuation, same path via Get-Content refused, turn
  `completed` with no reply, task left in_progress (divergence surfaced) -> F785.
- s3 long work: 700 s command; 3 attempts x 600 s, withdrawn after 30 min 14 s -> F782, F786.
- s4 card: two unanswered cards (2 x 120 s), turn `completed`, no reply -> F784.
  s4 ask: ask_user (wait 600) killed by the 600 s deadline; duplicate question on retry;
  an answer to the first card reached the agent 9 min 38 s later -> F783.
- s5 silence: `Read-Host` in a script gets empty stdin under Copilot's shell; no stall (held).
- s6 Hub restart mid-run: reconciled to `interrupted`, input returned and re-delivered 2 s after
  startup (counts as a delivery attempt); Stop worked; no strand (held; F-strand not reproduced).
- s7 Stop mid-command: stopped in 1 s, shell tree killed, resumed turn fine (held).
  s7b Stop during a pending card: 11 s (the 10 s cancel grace; Copilot does not answer the
  cancel while its permission request is open); the card is marked `expired` (noted, not filed).
- Judge false positives (reach-5 hold): none were hit in these prompts.
"""

import importlib.util
import json
import os
import pathlib
import sys
import time

os.environ.setdefault("AW_E2E_STATE", "C:/Users/huida/.agentweave/e2e-c1019cop.json")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_E2E = pathlib.Path(__file__).resolve().parents[2] / ".claude" / "skills" / "e2e-loop" / "e2e.py"
_spec = importlib.util.spec_from_file_location("e2e", _E2E)
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)

P = os.environ.get("AW_P", "proj-33d1893b68ba")
MODEL = "claude-haiku-4.5"


def req(method, path, body=None, **kw):
    return e2e.request(method, path, body, **kw)


def show(method, path, body=None, limit=4000):
    status, res = req(method, path, body)
    text = json.dumps(res, indent=1, ensure_ascii=False)
    print(f"{method} {path} -> {status}\n{text[:limit]}")
    return status, res


def q(sql, *args):
    return [dict(r) for r in e2e.ro().execute(sql, args)]


def run_row(rid):
    rows = q("select * from runs where id=?", rid)
    return rows[0] if rows else None


def events_for(rid):
    return q(
        "select timestamp, event_type, substr(data,1,700) d from event_logs where data like ? "
        "order by timestamp",
        f"%{rid}%",
    )


def outputs(rid):
    return q(
        "select timestamp, kind, substr(content,1,600) c from agent_outputs where run_id=? "
        "order by timestamp, sequence, id",
        rid,
    )


def report(rid, outs=True):
    r = run_row(rid)
    keep = ("id", "agent", "status", "error", "started_at", "ended_at", "exit_code",
            "runner_version", "session_id", "task_id", "last_heartbeat_at", "error_kind")
    print("RUN:", {k: r.get(k) for k in keep if k in r} if r else None)
    for e in events_for(rid):
        print("  EV", e["timestamp"], e["event_type"], e["d"][:400])
    if outs:
        for o in outputs(rid):
            print("  OUT", o["timestamp"], o["kind"], (o["c"] or "").replace("\n", " | ")[:400])


def poll(rid, seconds, every=5, quiet=False):
    t0 = time.time()
    last = None
    while time.time() - t0 < seconds:
        r = run_row(rid)
        st = r["status"] if r else None
        if st != last and not quiet:
            print(f"  t+{time.time()-t0:5.0f}s status={st}")
            last = st
        if st and st not in ("running", "queued", "starting", "pending"):
            return st, time.time() - t0
        time.sleep(every)
    return "still-running", time.time() - t0


if __name__ == "__main__":
    body = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    show(sys.argv[1], sys.argv[2], body, limit=10**7)
