"""Sweep B phase 7: agent-side spec tools.

  A  tester review turn on T2: list_evidence, decide_evidence (no grant), amend_spec_document, send back
  B  builder turn on T2: large read_spec_document, identifiers read, record_evidence, report_cannot_satisfy
"""
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


def _build(task_id, instruction):
    e2e.call("PATCH", f"/projects/{P}/tasks/{task_id}", {"assignee": "builder"})
    run = e2e.cmd_turn(P, "builder", instruction, task=task_id, fresh=True, perm="workspace")
    print("BUILDER RUN", run)
    if run:
        e2e.wait_for(run, 10)
    return run


def _review(task_id, message):
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



CH = "spec/changes/scarlet-minotaur/spec.json"
BIG = "spec/changes/teal-kraken/spec.json"
T2 = "task-26c07baafa80"
leg = sys.argv[1]


def last_run(agent):
    rs = runs_of(agent)
    return rs[-1]["id"] if rs else None


if leg == "A":
    before = len(runs_of("tester"))
    req("POST", f"/projects/{P}/agent/trigger", {"agent": "tester", "review_task_id": T2, "message": (
        f"Review task {T2} of {CH} (requirement FR-2, criterion c2). Do these AgentWeave tool calls in order and "
        f"report each answer word for word in your reply:\n"
        f"1. list_evidence with identifier FR-2 and document {CH}.\n"
        f"2. decide_evidence on the newest FR-2 evidence id with decision accepted and reason 'probe'.\n"
        f"3. amend_spec_document with path {CH}, op add_criterion, requirement r2, criterion c2-touching, "
        f"change {{\"given\": \"intervals [1,2] and [2,3]\", \"when\": \"merge is called\", \"then\": \"the result is [1,3]\", "
        f"\"how_to_check\": \"py -3.11 -m unittest discover -s tests\", \"checked_by\": \"agent\"}}, reason 'no test "
        f"exercises merge on touching intervals; I read tests/test_core.py', how_to_check 'grep merge tests/test_core.py'.\n"
        f"4. update_task {T2} status revision_needed with notes naming criterion c2-touching.\n"
        f"Do not ask anyone; if a call is refused, quote the refusal and continue with the next.")})
    wait_until(lambda: len(runs_of("tester")) > before and settled("tester"), 600)
    rid = last_run("tester")
    print("TESTER RUN", rid)
    e2e.dump_turn(rid)
    show_task(T2)
elif leg == "B":
    e2e.call("PATCH", f"/projects/{P}/tasks/{T2}", {"assignee": "builder"})
    run = e2e.cmd_turn(P, "builder", (
        f"Work task {T2} of {CH}. Do these in order and report each tool answer briefly:\n"
        f"1. read_spec_document path {BIG} include full. Say whether it came back as a file (written_to) and how many "
        f"requirement identifiers it names; open the file and quote the first line of FR-60.\n"
        f"2. read_spec_document path {CH} identifiers FR-2. Quote the criteria it lists.\n"
        f"3. Add a test test_merge_touching to tests/test_core.py asserting merge([Interval(1, 2), Interval(2, 3)]) == "
        f"[Interval(1, 3)]. Run py -3.11 -m unittest discover -s tests and commit with git.\n"
        f"4. record_evidence identifier FR-2, document {CH}, task_id {T2}, kind test_result, command and output from "
        f"step 3, covers partial, summary saying which part.\n"
        f"5. report_cannot_satisfy path {CH}, criterion c2, reason 'criterion c2 says requirement r2 holds when the unit "
        f"tests run, but it names no input; it cannot be checked as written'.\n"
        f"Do not move the task. Do not ask me anything. Reply DONE."), task=T2, fresh=True, perm="workspace")
    if run:
        e2e.wait_for(run, 12)
        e2e.dump_turn(run)
    show_task(T2)
save()
