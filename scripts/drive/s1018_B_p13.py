"""Sweep B: F621 under F672 -- a review held on another (unbound) piece of evidence; the operator's
acceptance asks the reviewer again. Four Haiku turns."""
from s1018_B_lib import *  # noqa

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

c, d = req("POST", f"{SPEC}/documents", {"title": "Held review on another piece"}, show=False)
H = d["path"]
p = base_payload("change-spec", "Held review on another piece", n=1)
p["requirements"] = [{"key": "r1", "statement": "The README MUST mention item 9.", "modal": "MUST"}]
p["acceptance_criteria"] = [{"key": "c1", "requirement": "r1", "given": "README", "when": "read", "then": "item 9"}]
p["tasks"] = [{"key": "t1", "title": "Mention item 9", "description": "Add 'item 9' to README.md.", "requirements": ["r1"]}]
p["delivery"] = {"mode": "none"}
req("PUT", f"{SPEC}/documents/{H}/content", {"document": p}, show=False)
req("POST", f"{SPEC}/documents/{H}/rigor", {"rigor": "gate", "reason": "held review"}, show=False)
req("POST", f"{SPEC}/documents/close-exploration?path={H}", show=False)
req("POST", f"{SPEC}/documents/propose?path={H}", show=False)
c, a = req("POST", f"{SPEC}/documents/phase?path={H}&to=approved", {"reason": "drive", "approve_anyway": True}, cut=300)
[T] = a["tasks_created"]
print("DOC", H, "TASK", T)

# 1: an unbound builder turn records evidence for FR-1 with no task
run = e2e.cmd_turn(P, "builder", f"Call the AgentWeave tool record_evidence with identifier FR-1, document {H}, kind "
                   f"manual_observation, summary 'README will mention item 9', and no task_id. Quote the answer's id and "
                   f"review_state. Do not ask me anything; then stop.", fresh=True, perm="workspace")
e2e.wait_for(run, 6)
print("UNBOUND EV", rows("select e.id, e.task_id, e.run_id, e.review_state from requirement_evidence e join spec_requirements r on r.id=e.requirement_id join spec_documents d on d.id=r.document_id where d.path=?", H))

# 2: the builder works the task without recording evidence
e2e.call("PATCH", f"/projects/{P}/tasks/{T}", {"assignee": "builder"})
run = e2e.cmd_turn(P, "builder", f"Work task {T}: append a line 'item 9' to README.md, commit it with git (message: item 9). "
                   f"Do NOT record evidence. Then move task {T} to completed with update_task. Reply DONE.",
                   task=T, fresh=True, perm="workspace")
e2e.wait_for(run, 8)
print("TASK after build", rows("select status, assignee from tasks where id=?", T))

# 3: tester reviews and approves -> held?
before = len(runs_of("tester"))
req("POST", f"/projects/{P}/agent/trigger", {"agent": "tester", "review_task_id": T, "message":
    f"Review task {T}: if README.md on the task's branch mentions item 9, approve it (update_task status approved, with "
    f"notes). If the approval is refused, end your turn and quote the refusal word for word; do not ask anyone."})
wait_until(lambda: len(runs_of("tester")) > before and settled("tester"), 600)
rid = runs_of("tester")[-1]["id"]
e2e.dump_turn(rid)
print("TASK after review", rows("select status, assignee from tasks where id=?", T))
print("DIVERGENCES", rows("select agent, policy_applied, outcome from run_divergences where task_id=?", T))

# 4: operator accepts the unbound piece -> reviewer asked again?
ev = rows("select e.id from requirement_evidence e join spec_requirements r on r.id=e.requirement_id join spec_documents d on d.id=r.document_id where d.path=? and e.review_state='awaiting'", H)
if ev:
    n = len(runs_of("tester"))
    req("POST", f"{SPEC}/spec/evidence/{ev[0]['id']}/decision", {"decision": "accepted", "reason": "README has item 9 on the task branch"}, cut=600)
    asked = wait_until(lambda: len(runs_of("tester")) > n, 120)
    print("TESTER ASKED AGAIN:", asked)
    wait_until(lambda: settled("tester"), 600)
    if asked:
        e2e.dump_turn(runs_of("tester")[-1]["id"])
    print("TASK final", rows("select status, assignee from tasks where id=?", T))
    print("DIVERGENCES final", rows("select agent, policy_applied, outcome from run_divergences where task_id=? order by sequence", T))
    print("INTEGRATION", rows("select outcome, commit_sha from task_integrations where task_id=?", T))
save()
