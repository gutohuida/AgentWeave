"""Drive a-review-no-reviewer-can-approve-goes-to-the-operator (F374) through real Haiku turns.

Reuses t_d0915_reachability's setup: one lane, alpha authors a task with evidence naming a commit
(left awaiting), then beta and gamma are created idle. Fire the flow: beta is staffed as reviewer,
meets the evidence gate, ends without a verdict. Before the change gamma was then spent on the same
refusal; after it the task must stay with beta, gamma get no entry, and the run_diverged row must
name the gate's sentence. Needs AW_HUB, AW_KEY.
"""
import os, sys, time
os.environ["AW_PHASE"] = "author"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import t_d0915_reachability as d  # noqa: E402
from aw import api  # noqa: E402

d.LANES = ("hold",)
try:
    d.phase_author()
    lane = d.S["lanes"]["hold"]
    d.make_agent(d.B, d.S["runner"]); d.make_agent(d.C, d.S["runner"])
    code, detail = d.fire(lane["job"], "review")
    d.wait_for(lambda: d.statuses().get(d.B) == "running", 90, "beta start")
    d.settle("review", rounds=90, tids=(lane["task"],))
    time.sleep(8)
    d.settle("tail", rounds=30, tids=(lane["task"],))
    row = d.task(lane["task"])
    d.note("task after review", f"{row['status']} / {row.get('assignee')}")
    code, ev = api("GET", f"/projects/{d.P()}/logs?event_type=run_diverged&limit=50")
    for e in ev if isinstance(ev, list) else []:
        print("  run_diverged:", d.blob(e.get("data"), 900))
    print("  gamma queue:", d.blob(d.queue(d.C), 300))
    code, evs = api("GET", f"/projects/{d.P()}/project/spec/evidence")
    print("  evidence:", d.blob([(e['id'], e.get('status')) for e in evs.get('evidence', [])], 300))
    d.S["ev"] = [e["id"] for e in evs.get("evidence", [])]
    d.save()
    code, jb = api("GET", f"/projects/{d.P()}/jobs/{lane['job']}")
    print("  job card:", d.blob(jb, 1500))
finally:
    if d.S.get("P"):
        d.teardown()
print("STATE", d.STATE)
