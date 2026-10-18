"""Sweep B phase 4: builder records evidence with command/output (F673), tester verdict decides it (F672).

  py -3.11 s1018_B_p4.py approve|sendback
"""
from s1018_B_lib import *  # noqa

CH = "spec/changes/scarlet-minotaur/spec.json"
T1, T2 = "task-67fd63386c95", "task-26c07baafa80"


def runs_of(agent):
    return rows("select id, status from runs where project_id=? and agent=? order by started_at", P, agent)


def settled(agent):
    return all(r["status"] not in ("running", "queued", "starting") for r in runs_of(agent))


def wait_until(pred, seconds):
    end = time.time() + seconds
    while time.time() < end:
        if pred():
            return True
        time.sleep(5)
    return pred()


def build(task_id, instruction):
    e2e.call("PATCH", f"/projects/{P}/tasks/{task_id}", {"assignee": "builder"})
    run = e2e.cmd_turn(P, "builder", instruction, task=task_id, fresh=True, perm="workspace")
    print("BUILDER RUN", run)
    if run:
        e2e.wait_for(run, 10)
    return run


def review(task_id, message):
    before = len(runs_of("tester"))
    c, body = req("POST", f"/projects/{P}/agent/trigger",
                  {"agent": "tester", "review_task_id": task_id, "message": message})
    wait_until(lambda: len(runs_of("tester")) > before and settled("tester"), 600)
    rs = runs_of("tester")
    return rs[-1]["id"] if rs else None


def show_task(task_id):
    print("TASK", rows("select status, assignee from tasks where id=?", task_id))
    print("EVIDENCE", json.dumps(rows("select id, requirement_id, digest, kind, review_state, command, substr(output,1,300) as output, covers, summary, locator from requirement_evidence where task_id=?", task_id), ensure_ascii=False, indent=1))
    print("REVIEWS", rows("select r.decision, r.actor_kind, r.actor, r.reason from evidence_reviews r join requirement_evidence e on e.id=r.evidence_id where e.task_id=?", task_id))
    print("TRANSITIONS", rows("select from_status, to_status, actor_kind, actor_agent, origin, override_reason from task_transitions where task_id=? order by created_at", task_id))


leg = sys.argv[1]
if leg in ("approve", "review1"):
    run = None if leg == "review1" else build(T1, f"Work task {T1} (requirement FR-1 of {CH}): in intervals/core.py, Interval.overlaps must "
                    f"return True for closed intervals that share an endpoint (use <= instead of <). Add a unit test "
                    f"test_touching_overlap to tests/test_core.py. Run: py -3.11 -m unittest discover -s tests . Commit "
                    f"with git (message 'touching intervals overlap'). Then call the AgentWeave tool record_evidence "
                    f"with identifier FR-1, task_id {T1}, kind test_result, summary of what you ran, command set to the "
                    f"exact test command, output set to what it printed, covers full. Then move task {T1} to completed "
                    f"with update_task. Do not ask me anything. Reply DONE.")
    show_task(T1)
    if rows("select status from tasks where id=?", T1)[0]["status"] == "completed":
        rid = review(T1, f"Review task {T1}: on the task's branch, read intervals/core.py and run "
                         f"py -3.11 -m unittest discover -s tests . First call list_evidence for FR-1 and look at the "
                         f"command and output the builder recorded. If overlaps treats touching intervals as "
                         f"overlapping and tests pass, approve it (update_task status approved, with notes saying what "
                         f"you checked). Otherwise send it back (revision_needed) with notes. If a call is refused, end "
                         f"your turn and report the refusal word for word; do not ask anyone.")
        print("TESTER RUN", rid)
        show_task(T1)
else:
    run = build(T2, f"Work task {T2}: this is a test of review. Do NOT edit any source file. Make an empty commit "
                    f"(git commit --allow-empty -m 'claim merge'). Call record_evidence once with identifier FR-2, "
                    f"task_id {T2}, kind test_result, summary 'merge combines touching intervals', command "
                    f"'py -3.11 -m unittest discover -s tests', output 'OK', covers full. Then move task {T2} to "
                    f"completed. Do not ask me anything. Reply DONE.")
    show_task(T2)
    if rows("select status from tasks where id=?", T2)[0]["status"] == "completed":
        rid = review(T2, f"Review task {T2}: requirement FR-2 says merge MUST combine intervals that touch at a "
                         f"single point. On the task's branch, check whether its commit changed anything and whether a "
                         f"test proves merge([Interval(1,2), Interval(2,3)]) == [Interval(1,3)]. The task's own diff "
                         f"must show the work. If it does not, send it back (update_task status revision_needed) with "
                         f"notes saying what is missing. If a call is refused, end your turn and report the refusal word "
                         f"for word; do not ask anyone.")
        print("TESTER RUN", rid)
        show_task(T2)
save()
