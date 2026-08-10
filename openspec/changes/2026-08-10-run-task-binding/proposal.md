## Why

**A run does not know what task it is working on.** `Run` (`hub/hub/db/models.py:749-800`) carries
project, agent, session, conversation, pid and heartbeat — and no task. The only link that exists is
`send_message(..., task_id=...)` (`hub/hub/mcp_server.py:168-204`), which is optional, is never
validated against what the receiving run then does, and never reaches the `Run` record.
`request_agent(name, template, task)` (`mcp_server.py:425`) takes `task` as **free text**, not an id.
`InboundQueueEntry` (`models.py:440-470`) has no task column, so even a delegation that names a task
loses it before the turn starts.

The consequence is that the board depends on agents *remembering* to keep it current — not because
agents are careless, but because the runtime holds no link that would let it know instead. B1
(`openspec/changes/archive/2026-08-10-task-transition-machine/`) made it impossible to record a
**wrong** transition. It does nothing about a **missing** one: an agent that does the work and never
touches the ledger passes every check B1 introduced, because it never asks for anything. B1 gives
validity; this change gives liveness
(`openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`).

It is also B3's prerequisite. Evidence is produced *by a run*, about *a task*, and that edge does
not exist, so there is nothing for evidence to attach to.

## What Changes

- **A run carries one primary task.** A nullable `task_id` on `runs`, set by the **runtime** at spawn
  from whatever caused the run — a delegation carrying `task_id`, or the operator starting work from
  a board card. The agent is never asked, so it cannot forget or decline. `InboundQueueEntry` gains a
  `task_id` so a delegation's task survives the queue into the turn.
- **Binding advances the task by itself (tier 1).** When a run binds to a task from which
  `in_progress` is reachable, the Hub applies that transition through the existing
  `apply_transition`, attributed to the binding run. Nothing bypasses B1's machine.
- **Transitions record who caused them.** `task_transitions` gains an `origin` of `actor` or
  `runtime`, so "the agent moved this task" is distinguishable from "AgentWeave moved it on the
  agent's behalf". Without it, the runtime's own auto-transition would satisfy the divergence check
  it exists to feed.
- **A run that ends without moving its task is divergent (tier 2).** Detected at the run boundary —
  which AgentWeave owns for every runner — not inside the agent.
- **The response to divergence is a per-task policy.** `surface` (default), `retry`, or `escalate`,
  with an escalation agent named on the task. `retry` re-runs the same agent **once**, then falls
  through to `escalate` if the task names an agent and to `surface` otherwise. Escalating reassigns
  the task to the escalation agent, which is what makes the weaker-model → stronger-model pattern
  visible on the board before it fires.
- **Every divergence is recorded**, not just broadcast: a `run_divergences` row per occurrence with
  the policy applied, the outcome, and the responding run.
- **The operator gets the controls and the surface** — policy and escalation agent on the task card,
  a divergence indicator, and a way to start a bound run from a board card.
- **The hook rule becomes a requirement.** *No capability may exist only in a hook.* A hook may make
  an independently-enforced rule fire sooner or more pleasantly; remove it and the identical rule
  still fires at the boundary. This is the rule that keeps a future runner without hooks from being
  structurally second-class.

### Non-Goals

- **Many tasks per run.** One primary binding only. A run that touches other tasks still has those
  moves recorded by B1 with agent attribution; they are simply not what the run was *for*. Decided
  with the operator 2026-08-10: many-to-many makes "did the task move?" a question with no single
  answer, which is precisely what the run-boundary check needs.
- **Agent self-binding.** No tool lets an agent declare mid-run which task it is on. It would reopen
  the evasion hole — an agent that never binds never diverges.
- **Scheduled jobs as a binding source.** `JobRun` (`hub/hub/scheduler.py:304`) has no task concept
  and giving it one is its own change. Job-triggered runs stay unbound, and unbound is legitimate.
- **Blocking the agent's next run on an unresolved divergence** (tier 3). That is B4's mechanism
  pointed at liveness, and the operator chose observation plus routing first.
- **Making bookkeeping a precondition of other capabilities** (tier 3) and **evidence** (B3).
- **Retry/escalate depth beyond one hop.** A divergence response run that itself diverges surfaces;
  it does not retry or escalate again.
- **Backfilling `runs.task_id` for existing rows.** They stay NULL, which reads correctly as
  "unbound", and inventing a binding would put a guess into a record whose value is that everything
  in it happened.

## Capabilities

### New Capabilities

- `run-task-binding`: what binds a run to a task, who may set it, what binding does to the task's
  status, what makes a completed run divergent, and how each per-task policy resolves.

### Modified Capabilities

- `task-lifecycle-governance`: transitions gain a recorded origin (`actor` / `runtime`); the runtime
  is added as a legitimate cause of a transition without becoming a third actor kind; tasks carry a
  divergence policy and an escalation agent.
- `agent-capability-plane`: the hook rule; a delegation's `task_id` becomes runtime state rather than
  message decoration; run-bound identity is what the binding is attributed to.

## Impact

**Schema** — `runs.task_id`, `runs.divergence_source_run_id`, `inbound_queue_entries.task_id`,
`tasks.divergence_policy`, `tasks.escalation_agent`, `task_transitions.origin`, and a new
`run_divergences` table. Migrations `0054`+, each guarded for a missing table, with the head
assertions bumped in **both** `hub/tests/test_migrations.py` and
`hub/tests/test_project_persistence.py`.

**Backend** — `hub/hub/db/models.py`; `hub/hub/api/v1/agent_trigger.py` (the single `Run(` creation
site at line 474, and the run-end path); `hub/hub/inbound_queue.py`; `hub/hub/task_transitions.py`
and `hub/hub/task_transition_service.py` (the seam `apply_transition` already documents);
`hub/hub/run_reconciliation.py` (an interrupted run is also a run that ended); `hub/hub/mcp_server.py`
(`send_message`'s `task_id` must reach the queue; `request_agent`'s free-text `task`);
`hub/hub/api/v1/tasks.py`; `hub/hub/schemas/`.

**Frontend** — the task card's policy and escalation controls, a divergence indicator, and starting a
bound run from a board card (`hub/ui/src/components/tasks/`, `hub/ui/src/api/tasks.ts`), plus the
rebuilt `hub/hub/static/ui`.

**Risk** — the auto-transition changes the board without an operator or agent asking for it. It is
bounded by binding only ever coming from an explicit cause, and by going through B1's machine rather
than around it: if the move is not legal for a run, no move happens.
