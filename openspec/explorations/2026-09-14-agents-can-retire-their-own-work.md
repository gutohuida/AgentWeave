# Agents can retire their own work

**2026-09-14, day window, I-1 brief 2 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 2, `### Architect` item 4, `#### tester` item 1 and `#### dev_2` item 1.

## What we saw

**Evidence.** Five of `tester`'s 34 rejections were not judgements of the work. Each reason says the
content is fine, and that the rejection only stops a superseded or duplicate row being counted
twice.
- Two of them were `dev_2`'s rows for a fix `dev` had already landed (`ev-90bc84ab8ddb`,
  `ev-13c55e550139`).
- The author could not withdraw them itself. Evidence has three states, `awaiting`, `accepted` and
  `rejected` (`hub/hub/db/models.py:2364`), and no action retracts a row.
- The duplicate refusal offers *"If the wording is wrong, say so on that piece"*
  (`hub/hub/requirement_evidence.py:147-153`). The only way to say so is for someone else to reject
  it.

**Tasks.** A task that is superseded, or that duplicates another, cannot be closed by any agent.
- An agent run may move a `completed` task only to `under_review`. Rejecting outside a review is the
  operator's alone (`hub/hub/task_transitions.py:134-142`), and no status means "superseded".
- The Architect tried three times to close `task-5420e60359c1`. The operator rejected it by hand at
  22:33.
- `task-8ae8e1ace072`, which the Architect tried to reject as superseded at 23:06, is still
  `completed` and assigned to `dev`. `dev_2`'s `task-3fe4f652e5c2` duplicated it: `dev_2` found that
  `dev`'s claimed fix had never merged and did it again.
- The Architect ended five autonomous turns asking the operator, in prose, to close or reassign
  tasks. Nothing surfaced those requests.

## What would change

**Evidence.** The agent that recorded a row could withdraw it while it is still `awaiting`, giving a
reason. The row stays on record, marked withdrawn. It leaves the reviewer's queue and the
requirement's count, and it no longer blocks a re-record at the same commit. Accepted and rejected
rows stay beyond anyone's reach, as now.

**Tasks.** An agent could say that a task is superseded by another one, naming it. Whether that
*closes* the task or only *asks the operator to close it* is the decision below. Either way, the
claim becomes a record the operator sees, not a sentence at the end of a turn.

## Why it matters

Reviewers spend judgement on bookkeeping. On LoopEngine that was 5 rejections by `tester`, an Opus
agent that cost $76.05 over the review. It also skews what the evidence
says: a `rejected` row that means "duplicate" reads, to anyone who comes later, like work that
failed review. For tasks, the ledger keeps claiming work is waiting for review when the team knows
it is dead. That makes it look unfinished to `list_tasks`, to the flow's staffing (F352 counts such
a task's assignee as busy), and to the operator.

## Rough cost — a code-read estimate

- **Evidence:**
  - a fourth state in `EVIDENCE_REVIEW_STATES`. Its CHECK constraint (`models.py`,
    `ck_requirement_evidence_review_state`) means **a migration**, a table rebuild on SQLite;
  - a `withdraw` path in `hub/hub/requirement_evidence.py`, next to `decide` (`:677-737`);
  - the counts, gates and the duplicate check (`:241` already skips `rejected`) all learn the new
    state;
  - a route in `hub/hub/api/v1/agent_actions.py`;
  - an MCP tool or parameter in `hub/hub/mcp_server.py`, **which F354 keeps out of today**.
- **Tasks:** either a new edge in `task_transitions.py` that governance must admit, or a
  supersede-request record plus an operator control. The second is a new table, a migration and UI.
- **Capabilities:**
  - `openspec/specs/requirement-traceability` (evidence states, *"Evidence names what produced it
    and what it was produced against"*);
  - `task-lifecycle-governance` (*"Some transitions are the operator's alone"*);
  - `agent-capability-plane` (*"An agent can record, read and decide requirement evidence"*).
- **UI:** a withdrawn row has to render somewhere. A supersede request needs an operator control.

## Risks and open questions

- **Withdrawal can hide a failure.** An author who senses a rejection coming could withdraw first.
  Keeping the row, its reason, and who withdrew it and when answers most of that. Whether a
  withdrawn row still shows on the task's review is a design question for R1.
- **Closing tasks is deliberately the operator's.** `task-lifecycle-governance` makes rejection
  outside review operator-only, and the operator should say whether "superseded by task X" is an
  agent's call or a request to them. That is the one real decision here.
- **It overlaps F353.** "Clear the assignee" has no control that can do it, and the f352 change
  (queued today) rewrites that sentence. A supersede action is a second way out of the same trap,
  and R1 should read f352's diff first.
- **The duplicate refusal's other half is F358's.** Its *"commit it first"* remedy contradicts the
  briefing, and that is fixed there, not here.

## The decision, in one line

Approve a spec loop for *an author can withdraw its own awaiting evidence*, with a migration, and
decide separately whether an agent may close a superseded task or only ask the operator to. The
loop runs on a build day that allows `mcp_server.py` edits (after F354).
