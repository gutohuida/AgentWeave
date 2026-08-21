## Why

A loop pokes one agent on a schedule. It cannot get a decomposition from nothing to fulfilled,
because the work needs more than one agent and the loop only ever fires one.

Concretely, and reachable the moment `task-dependencies` ships: an agent cannot approve its own work
(`hub/hub/task_transition_service.py:119`), a dependency is met only at `approved`, and a loop has
exactly one agent. **A single-agent loop cannot advance past its first layer** — not slowly, at all.
Today that surfaces as a stall; with dependencies it becomes the normal case.

Everything needed to fix it is either present or being built:

- the graph and the gate — `task-dependencies`, in flight
- one flow per decomposition — `Loop.spec_document_id` is already `unique=True`, *"so two loops
  cannot silently race to claim the same decomposition"*
- memory across firings — `agent-loops` §231 already briefs a firing with the checkpoint from *"any
  prior firing of that same loop, regardless of which conversation produced it"*
- a single decision point for what a firing does — `loop-notices-and-reacts`, which leaves room for
  exactly the answer this change adds

**What is missing is that a firing cannot fire anyone but the job's one agent.**

Explored and decided with the operator in
`openspec/explorations/2026-08-21-the-loop-becomes-a-flow.md` and
`2026-08-21-a-review-is-a-task-not-a-message.md`.

## What Changes

**A flow is a loop that declares a document.** Three tiers, one row, no new tables:

| | |
|---|---|
| `AIJob`, no `Loop` | a **job** — one agent, no queue |
| `AIJob` + `Loop`, no document | a **loop** — one agent working a sequence |
| `AIJob` + `Loop` + document | a **flow** — a decomposition, its graph, and whoever it takes |

- **A firing selects a task and an agent**, both deterministically. Today it selects a task and reads
  the agent off `AIJob.agent`.
- **`AIJob.agent` becomes the default rather than the mandate.** A flow with one agent and no
  declared reviewers behaves exactly as a loop does today — that is both the migration story and the
  regression bar.
- **`completed` becomes claimable by an agent that did not complete it**, which is how a review
  becomes work the flow can staff rather than a message someone must remember to send. The
  determination already exists (`_agent_that_completed`).
- **A flow may start every task whose dependencies are met**, up to the width its graph offers.
- **Reviewer resolution:** the task's declared reviewer (`task-dependencies` D11) if it resolves,
  else any agent that is neither running nor holding an active task, else the flow surfaces that it
  could not staff the step.
- **`create_flow`** joins `create_job` and `create_loop` — the third instance of a pattern already
  used twice: separate verbs writing one table.
- **The briefing states which tier this firing belongs to and what follows for the agent** — in a
  flow, finish and stop, because routing is the flow's job.
- **The checkpoint chain belongs to the flow**: one lineage, many authors, each checkpoint recording
  who wrote it.

**Non-Goals — stated, not left to omission:**

- **Renaming `Loop`.** The storage word stays. `task-dependencies` is being implemented against it,
  and *flow* and *loop* nest rather than conflict.
- **A separate flow screen.** The flow's view is `task-dependencies`' dependency board, additively.
  The board must keep working with no flow at all.
- **A project-wide concurrency cap.** Withdrawn by the operator on 2026-08-20 and still withdrawn.
  Width here comes from the document's own graph, not from a setting.
- **Charter summaries in the Team section, and `list_agents`.** They improve matching; nothing here
  waits on them.
- **Event-driven firing.** Decided against; the cron stays.
- **Changing what any status means**, or which transitions are legal.

## Capabilities

### New Capabilities

- `agent-flows`: What a flow is, how a firing selects both a task and an agent, when it may start
  more than one, how a reviewer is resolved, and what happens when no agent can be found.

### Modified Capabilities

- `agent-loops`: A firing determines who acts, not only what is worked; "the queue's current item"
  admits more than one; and consecutive firings by different agents are not one event.
- `conversation-checkpoint`: A loop's checkpoint lineage becomes the flow's rather than one agent's,
  and a checkpoint records which agent wrote it.
- `agent-tool-surface`: `create_flow` exists, `create_loop` refuses a document and names it, and a
  firing's briefing states which tier the agent is working inside.

## Impact

**Code**

- `hub/hub/scheduler.py` — the firing decision gains its fourth answer; `_claim_loop_task` returns a
  set rather than one task; `_compose_loop_briefing` states the tier.
- `hub/hub/api/v1/jobs.py` — `_batch_loop_summaries` must reflect several current items.
- `hub/hub/mcp_server.py` — `create_flow`, and `create_loop` refusing a document. Stdlib + fastmcp
  only.
- Reviewer resolution, reading `task-dependencies`' reviewer field and agent availability.

**Database**

- `Checkpoint` — the lineage's meaning changes; `agent` already exists and already records the
  writer.
- `AIJob.agent` stays `NOT NULL`. Nothing is dropped.

**Specification**

- `agent-loops` has 25 requirements. **20 are untouched by this change** — including the controller,
  stop conditions, archiving, history, and the queue's ownership. That count is the evidence this is
  an extension rather than the rebuild the operator ruled out on 2026-08-20.

**Depends on**

- `task-dependencies` — the graph, the gate, and the reviewer field. **Must land first.**
- `loop-notices-and-reacts` — the shared firing decision and the status vocabulary. Not strictly
  required, but building this against the four-set world means rewriting it immediately.

**Risk.** Parallelism is the largest single change: `_claim_loop_task` returning one task is assumed
by the firing, the board, and `agent-loops` §525. A flow that starts several tasks also spends
several agents' tokens at once, which the operator currently eyeballs rather than caps.
