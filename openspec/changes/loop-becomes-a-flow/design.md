## Context

A loop is a mature sequential executor — 25 requirements, three bugs found only by driving it live.
The operator's standing decision (`2026-08-20-the-loop-under-dependencies.md` §1) is *"improve the
loop, do not rebuild it"*, and this design is written to satisfy that literally: the audit in
`2026-08-21-the-loop-becomes-a-flow.md` §3 found **20 of 25 requirements untouched**.

What forces the change is arithmetic, not ambition. An agent cannot approve its own work; a
dependency is met at `approved`; a loop has one agent. **A single-agent loop cannot advance past its
first layer.**

## Goals / Non-Goals

**Goals:**

- A decomposition runs from nothing to fulfilled without an operator relaying between agents.
- Every selection stays deterministic — which task, and now which agent.
- A flow with one agent is indistinguishable from today's loop.

**Non-Goals:** as stated in the proposal — no rename of `Loop`, no separate flow screen, no
concurrency setting, no `list_agents`, no event-driven firing, and no change to what any status means
or which transitions are legal.

## Decisions

### D1 — A flow is a configuration, not a record

Three tiers, one row: a job is an `AIJob`; a loop adds a `Loop`; a flow is a `Loop` that declares a
document. `Loop.spec_document_id` is already `nullable=True, unique=True`, and `agent-loops` §150
already permits it.

*Rejected:* **a `Flow` table.** Three tables and three route families for one row with two optional
columns, and every rule written this month would fork into three copies. The distinction is real; the
storage is not.

**Consequence accepted:** *flow* and *loop* are both live words for one table called `Loop`. They
nest — a flow is a loop that declares a document — so this is tolerable. Revisit only if they start
disagreeing rather than nesting.

### D2 — `AIJob.agent` becomes the default, never the mandate

The column stays `NOT NULL` and keeps meaning *the agent this job fires when nothing says otherwise*.
A firing supplies the agent per selection; where a flow has nothing to say, it supplies the job's own.

This is what makes the regression bar expressible in one sentence: **a flow with one agent and no
declared reviewers must behave identically to a loop today**, and every existing loop test asserts
exactly that without modification.

*Rejected:* **making it nullable.** Agent identity reaches the run credential, the briefing, the
conversation and the queue entry. A null would have to be handled at each, for no gain over a default.

### D3 — `completed` becomes claimable by a non-author, and that is the whole review mechanism

Not by widening `CLAIMABLE_LOOP_TASK_STATUSES`, which is actor-blind. Claimability becomes a question
about *(task, agent)* rather than about status alone.

The determination already exists: `_agent_that_completed`
(`hub/hub/task_transition_service.py:92-116`), which author/reviewer separation reads for
`under_review -> approved`. **Using the same function is not tidiness, it is the correctness
property** — a task the flow offers an agent must never be one that agent is then refused for
approving.

*Rejected:* **a review as its own task row.** A review task's own completion needs reviewing —
infinite regress — and `Task` has no `kind` column to exempt it with.
*Rejected:* **a handoff message the finishing agent sends.** That was the previous design
(`2026-08-20-who-guarantees-the-review-handoff.md`) and it required detection, re-briefing, a
reminder bound and an exhaustion path, all to compensate for an act that can be omitted. Nothing here
can be omitted, because nothing is asked of the finishing agent.

**This is why `loop-notices-and-reacts` lost its R1–R3.**

### D4 — Reviewer resolution is a ladder, and the bottom rung needs no configuration

```
   1. the task's declared reviewer          (task-dependencies D11) — if it resolves
   2. any agent not running and holding no active task
   3. surface: "could not staff this step"
```

Rung 2 is the important one, and it exists because of the operator's objection to the previous
direction: *"I don't want to end up in a old problem where having a squad to develop is a price that
you need to pay before even starting development."* With nothing configured — no charters, no scope
lines, no declarations — rung 2 still runs the whole flow.

"Free" is *not running* **and** *holding no active task*. Both facts already exist:
`schedule_agent`'s running query (`hub/hub/turn_scheduler.py:37-43`) and `Task.assignee` against the
active statuses. *Rejected:* not-running alone — an agent can hold three assigned tasks and be idle
between turns, which is the pile-up the operator named. *Rejected:* least-loaded — never blocks, and
so hides that the project needs another agent.

**Rung 3 never disables the job.** Same reasoning that chose *skip* over *stop* on 2026-08-20: the
operator resolving it must be enough, and `remove_job` is not reversible by resolving anything.

**A single-agent project needs no special case.** Its only agent is the author, rung 1 and 2 both
yield nothing, and rung 3 surfaces — the correct outcome, reached by the general rule.

### D5 — Width comes from the graph, never from a setting

A firing starts every task whose dependencies are met and for which an agent resolved, bounded by
available agents. No cap, no configuration.

**This does not reverse the max-concurrent-runs withdrawal** (2026-08-20). That was a *project-level
cap*, withdrawn because it ignored `token_budget` and made review structurally unreachable at 1.
Width here is not a policy the operator sets; it is the shape of the decomposition they approved. The
operator still starts parallelism — at spec time, by declaring independent work.

**The largest mechanical consequence:** `_claim_loop_task` returns one task and three callers assume
it. The set-valued form must land before anything else in this change is useful.

*Rejected:* **serial, one task per firing.** It solves every correctness problem and makes the graph
decorative — a DAG walked in a valid order that never uses its width.

### D6 — One agent, one task, per firing

An agent selected for two tasks in one firing would be started twice concurrently, which
`schedule_agent` refuses anyway (*"agent is already running"*) — silently dropping one selection.
Deciding it at selection time makes the drop visible instead.

### D7 — The checkpoint lineage is the flow's

`agent-loops` §231 already says a firing is briefed with the checkpoint of *"any prior firing of that
same loop, regardless of which conversation produced it"*, and `latest_checkpoint_for_loop` already
retrieves that way. Only the `Checkpoint` model's comment disagrees — *"Linear, single-agent chain."*

So this resolves a **latent disagreement between a requirement that already says "the loop's" and a
comment that says "one agent's"**, which nothing had to settle because no loop ever had two agents.

*Rejected:* **per-agent chains within a flow** — a reviewer would start blind to what the implementer
was thinking, which is most of what a handover carries.

**Consequence:** a checkpoint becomes readable by an agent that did not write it, so the instruction
an agent is given when writing one must say who will read it. Otherwise agents write notes to
themselves and a reviewer inherits shorthand.

### D8 — The briefing states the tier and what follows from it

An agent inside a flow did not choose to be there and has no reason to ask. It must be told, in the
one place it reliably reads, that finishing means stopping — routing is the flow's job.

*Rejected:* **a tool to ask.** Costs nothing per turn and an agent that does not know to ask never
asks — exactly how the self-messaging capability stayed invisible
(`2026-08-20-an-agent-messaging-its-other-conversation.md`).

## Risks / Trade-offs

**[Set-valued claim breaks the board, the firing and §525 at once]** → Land the set-valued form
first, with the board reading the same function, before any multi-agent behaviour. A flow that
returns a set of one must pass every existing test unchanged.

**[Concurrent agents spend concurrently]** → Real, and deliberately unmitigated by a cap per D5.
`token_budget` and `stop_at` still bound a flow, and the operator can disable the job.

**[Reviewer resolution races]** → Two firings, or a firing and an operator, could select the same
"free" agent. `schedule_agent` already serialises per agent behind a lock and refuses a second start,
so the failure mode is a dropped selection rather than a double start. D6 makes it visible within one
firing; across firings it needs the same treatment.

**[A flow fires an agent that cannot be launched]** → `AIJob.agent` is validated at creation; an agent
selected at firing time is not. Runner-bound is part of eligibility, not an error path.

**[Two words for one table]** → Accepted in D1. The mitigation is that they nest.

## Migration Plan

No data migration. `Checkpoint.agent` already exists and already records the writer; what changes is
which lineage a firing reads, and it already reads by loop.

Every existing loop becomes a loop, not a flow — none declares a document unless someone declared
one. The behaviour of a flow with one agent is today's behaviour, so the regression suite is the
existing loop suite, unmodified.

## Open Questions

- **What does the board show for a flow staffing several tasks?** The dependency board renders the
  graph; whether concurrent work is shown per card, per layer, or as a flow header is undecided.
- **How is a declared reviewer resolved — against charters, agent names, or both?**
  `task-dependencies` D11 deliberately left this here, and it is the last thing rung 1 needs.
- **Does a flow ever fire the same agent for a task it is already working?** Resumption of an
  `in_progress` task should keep its agent; nothing says so yet.
- **Cross-firing selection races** — see the risk above.
