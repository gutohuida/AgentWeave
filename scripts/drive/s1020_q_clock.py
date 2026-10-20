"""Questions sweep, 2026-10-20: the turn clock counts work, not waiting (F782/F783), with work
AND waiting in one Copilot turn, together past the old 600 s cut.

Agent `cop` (Copilot, claude-haiku-4.5, question_timeout_seconds 300) runs a 420 s command, then
calls ask_user. The operator answers `answer_at` seconds after the send (default 640), so the
run has spent ~430 s working and ~200 s waiting. Expected: one run, completed, the answer the
tool result, one question; the deadline did not cut at 600 s.

    py -3.11 scripts/drive/s1020_q_clock.py [answer_at]
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("\\", 1)[0].rsplit("/", 1)[0])
from s1020_q_lib import P, e2e, q, req  # noqa: E402

answer_at = float(sys.argv[1]) if len(sys.argv) > 1 else 640.0
# `--watch <run-id>`: re-attach to a run already started (the launcher's shell died).
watch = sys.argv[sys.argv.index("--watch") + 1] if "--watch" in sys.argv else None
if watch:
    import datetime as _dt

    started = q("select started_at from runs where id=?", watch)[0]["started_at"]
    t0 = _dt.datetime.fromisoformat(started.replace("Z", "")).replace(
        tzinfo=_dt.timezone.utc).timestamp()
else:
    t0 = None
if not watch:
    e2e.cmd_agent(P, "cop", "-", "copilot", "claude-haiku-4.5")
    print("wait:", req("PATCH", f"/projects/{P}/agents/cop", {"question_timeout_seconds": 300})[0])
    t0 = time.time()
    rid = e2e.cmd_turn(
    P, "cop",
    "Step 1: in the shell, run exactly `py -3.11 -c \"import time; time.sleep(420); print('slept')\"` "
    "synchronously and wait for it to finish (it takes 7 minutes; do not background it). "
    "Step 2: after it prints slept, call the AgentWeave tool ask_user with the question "
    "'Which name should the new helper have?' and the options 'double' and 'twice', and wait. "
    "Step 3: add that function (returning 2*x) to src/calc.py and reply in one line.",
    fresh=True, perm="workspace")
seen, answered = set(), None
while time.time() - t0 < 25 * 60:
    rows = {
        "runs": q("select id, status, error, started_at, ended_at from runs where agent='cop' "
                  "order by started_at"),
        "questions": q("select id, answered, created_at, answered_at, wait_expires_at, "
                       "wait_ended_at, created_by_run_id from questions where from_agent='cop'"),
        "entries": q("select id, state, delivery_attempts, abandoned_reason from "
                     "inbound_queue_entries where agent='cop'"),
    }
    for k, v in rows.items():
        for r in v:
            key = (k,) + tuple(str(x) for x in r.values())
            if key not in seen:
                seen.add(key)
                print(f"t+{time.time()-t0:6.0f}s {k} {r}", flush=True)
    open_qs = [r for r in rows["questions"] if not r["answered"]]
    if answered is None and open_qs and time.time() - t0 >= answer_at:
        answered = time.time() - t0
        st = req("PATCH", f"/projects/{P}/questions/{open_qs[0]['id']}",
                 {"answer": "double", "labels": ["double"]})[0]
        print(f"t+{answered:6.0f}s ANSWERED {open_qs[0]['id']} -> {st}", flush=True)
    runs = rows["runs"]
    if time.time() - t0 > 60 and runs and all(
            r["status"] not in ("running", "queued", "starting") for r in runs):
        break
    time.sleep(10)
print(f"done t+{time.time()-t0:.0f}s answered_at={answered}")
for r in q("select id from runs where agent='cop' order by started_at"):
    e2e.dump_turn(r["id"])
