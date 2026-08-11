# Design — the run→task binding and what a divergent run costs

## Context

B1 shipped a machine that refuses a *wrong* transition. It cannot see a *missing* one, because a run
holds no reference to the work it is doing. `Run` (`hub/hub/db/models.py:749`) has one creation site
(`hub/hub/api/v1/agent_trigger.py:474`) and no task column; `InboundQueueEntry` (`models.py:440`)
carries `spec_document` but not `task_id`; `send_message`'s optional `task_id`
(`hub/hub/mcp_server.py:173`) lands on a `Message` row and stops there.

The four enforcement tiers are set out in
`openspec/explorations/2026-08-10-enforcing-the-development-cycle.md`. This change implements tiers 1
and 2 — derive the transition rather than ask for it, and observe the run boundary — both of which
sit at boundaries AgentWeave owns for every runner. Tier 3 is B4; tier 4 already exists as turn-start
injection.

Decisions 1–3, 7–9 below were taken with the operator on 2026-08-10 and are recorded here with their
alternatives so they are not re-litigated.

## Goals / Non-Goals

**Goals.** A run knows its task. Starting work on a task moves it, without asking the agent. A run
that ends without moving its task is detected outside the agent, recorded durably, and answered
according to a policy the operator sets per task — including routing the work to a stronger agent.

**Non-Goals.** As stated in `proposal.md`: no many-to-many binding, no agent self-binding, no
job-sourced binding, no blocking of subsequent runs, no evidence model, no backfill, and no
retry/escalate chain longer than one hop.

## Decisions

### D1 — One nullable `task_id` on `runs`, not a join table

A run is started *for* one thing. Modelled as a column, "did the run's task move?" has exactly one
answer, which is what the tier-2 check consumes.

*Rejected: many-to-many.* Realistic — a session does fix three related board items — but it makes
the run-boundary question ambiguous (all of them? any?), and an ambiguous check cannot drive a
policy that spends tokens. Work on unbound tasks is not lost: B1 records those moves with agent
attribution regardless. What is lost is only the claim that the run was *for* them.

*Rejected: primary + secondaries.* The most faithful, and it buys nothing this change needs. Deferred
without prejudice — the column can gain a companion table later without changing its meaning.

### D2 — The runtime binds. There is no agent-facing binding tool

Binding is set by the Hub at spawn, from the cause of the run. No MCP tool and no HTTP route lets a
run declare or change its own binding.

The reason is structural, not distrust: **an enforcement mechanism the subject can decline is not
enforcement.** An agent able to bind itself is an agent able to never bind, and an unbound run never
diverges — so self-binding would reintroduce, one level down, exactly the forgetting this change
exists to remove.

*Rejected: an `adopt_task` tool.* It covers the real case of an agent picking up work nobody bound
it to. That case is better answered by giving the *operator* a one-click bound start (D3) than by
making the check optional.

### D3 — Two binding sources, both explicit causes

| Source | Where the task comes from |
|---|---|
| **Delegation** | `send_message(..., task_id=…)` — the id is validated against the project's tasks, carried on the resulting `InboundQueueEntry`, and read by the trigger path when the turn starts |
| **Operator** | Starting a run from a board card; the trigger request carries the task id |

`request_agent(name, template, task)` takes `task` as free text and keeps doing so — it is a
description of work for an agent that may not exist yet, not a reference to a row. It gains no
binding power in this change.

Scheduled jobs bind nothing (`JobRun`, `hub/hub/scheduler.py:304`, has no task concept). A
job-triggered run is unbound, and unbound is legitimate — see D14.

Where several queue entries are delivered into one turn and more than one names a task, the
**earliest queued entry that names a task** wins, matching the order the turn prompt is assembled in
(`inbound_queue.format_turn_prompt`). Deterministic beats clever; the alternative is a run whose
binding depends on delivery timing.

### D4 — The auto-transition goes *through* `apply_transition`, never around it

Binding a task from which `in_progress` is reachable by a run applies that transition using
`apply_transition(..., actor=run_actor(run_id, agent))` — B1's own entry point, with B1's own
legality check.

This matters more than it looks. `task_transition_service.apply_transition` is documented as the seam
B3's evidence checks and B4's completion gates plug into. A runtime path that set `task.status`
directly would be a bypass of every gate not yet written.

Consequences that follow rather than being decided separately:

- A task already `in_progress` produces no transition (B1's same-status no-op, D7 of that change).
- A task in `completed`, `under_review`, `approved` or `rejected` has no run edge to `in_progress`,
  so **binding still happens and no transition does**. Binding is a statement about the run; it is
  not a claim about the task's status.
- `revision_needed → in_progress` is a legal run edge, so re-delegating revision work advances it
  for free.

### D5 — Transitions record an `origin`, not a third actor kind

`task_transitions` gains `origin` ∈ {`actor`, `runtime`}. The runtime's auto-transition is written
with `origin='runtime'` and the *run's* actor identity; everything else is `origin='actor'`.

Without this the change eats itself: the divergence check asks "did this run move its task?", and the
runtime's own auto-transition — made by that run, on that task — answers yes for every run.

*Rejected: a third `ACTOR_KINDS` value.* `Actor` is what author/reviewer separation and the whole
edge map are keyed on (`hub/hub/task_transitions.py:88-136`). Adding `runtime` there would require
every edge to declare whether the runtime may take it, and would make the runtime capable of moves no
one is accountable for. The runtime does not act *instead of* the run; it acts *as* the run, at a
moment the run did not choose. `origin` says exactly that, and author/reviewer separation continues
to read agent identity unchanged.

*Rejected: inferring it from timing* ("the first transition within N ms of run start"). Unfalsifiable
and quietly wrong under load.

### D6 — What makes a run divergent

At run end, a run is **divergent** when all hold:

1. `run.task_id` is not NULL;
2. no `task_transitions` row exists with this `run_id`, this `task_id`, and `origin='actor'`.

Exit status is not a condition — a crashed, failed, or interrupted run is still a run that ended
holding a task nobody moved. The recorded divergence names the exit status so a crash reads
differently from a forgetful completion.

`run_reconciliation.reconcile_interrupted_runs` marks orphaned runs `interrupted` on Hub start; that
path performs the same check, so a divergence is not lost to a crash.

**A divergence is an open condition, not a verdict.** It is resolved automatically when a later
`origin='actor'` transition lands on the task, whoever makes it. A run that ends mid-way through
multi-turn work opens a divergence that closes as soon as the work reaches the ledger. This is the
weakest part of the design and is recorded as an open question below.

### D7 — The response is a per-task policy, defaulting to `surface`

`tasks.divergence_policy` ∈ {`surface`, `retry`, `escalate`}, default `surface`; `tasks.escalation_agent`
is a nullable agent name.

- **`surface`** — record and show. Nothing runs, nothing is spent.
- **`retry`** — re-trigger the *same* agent once, with a prompt naming the task, its current status,
  and the reachable transitions.
- **`escalate`** — reassign the task to `escalation_agent` and trigger that agent, with the same
  prompt plus the diverging run's identity.

`surface` is the default, and therefore what every task already on the board gets. That is the point:
this change cannot begin spending tokens across an existing project the moment it ships. Retry and
escalate are opt-in, per task, by the operator.

*Rejected: one project-wide setting.* One flip would change behaviour for every task at once, and the
operator's stated use — a cheap model doing the work and an expensive one resolving what it could
not — is a per-task property, not a project one.

### D8 — Retry is bounded by construction, not by a counter

A run spawned in response to a divergence carries `runs.divergence_source_run_id`. Retry fires only
when the diverging run has that column NULL. So:

```
run A (bound, diverges) → retry → run B (divergence_source_run_id = A)
run B diverges          → no retry. Falls through: escalate if escalation_agent is set, else surface
```

No max-attempts field, nothing to misconfigure, and no loop is expressible.

The bound is per *chain*, not per task lifetime: if run B does move the task, the chain is clean, and
a later independent run C that diverges may retry again. That is the intended behaviour — the bound
exists to stop a stuck agent burning tokens, not to ration a task's whole life.

*Rejected: retry until the task moves.* The clearest available way to spend a large amount of money
on an agent stuck on something it cannot do.

### D9 — Escalation reassigns the task

`escalate` sets `task.assignee = escalation_agent` before triggering. The operator's stated intent is
routing work from a weaker model to a stronger one; leaving the assignee pointing at the agent that
just failed would make the board disagree with reality, and the next reader would re-delegate to the
wrong agent.

The prior assignee is recoverable from the divergence record, so nothing is lost.

### D10 — Divergences are a table, not only an event

`run_divergences`: `id`, `project_id`, `run_id`, `task_id`, `task_status_at_end`, `run_exit_status`,
`policy_applied`, `outcome` ∈ {`surfaced`, `retried`, `escalated`}, `response_run_id`,
`previous_assignee`, `created_at`, `resolved_at`.

An SSE event vanishes; the operator needs to see divergences that happened while they were away, and
"how often does this agent forget?" is a question worth being able to ask. B3 will want the same rows.

Ordered by an autoincrement `sequence` primary key, following `InboundQueueEntry` and
`TaskTransition` — B1 learned this the expensive way, when rows staged in one flush shared a
`created_at` and the tiebreak was a random id.

### D11 — Unbound runs are legitimate and produce no divergence

Exploration, questions, conversation and job-triggered work are real work with no task. An unbound
run is never checked and never divergent.

This is a known hole only under D2's converse: because the agent cannot bind itself, it also cannot
*un*bind itself, so it cannot escape a binding the runtime made. The hole would exist only if agents
could choose, and they cannot.

### D12 — No backfill

Existing `runs` keep `task_id` NULL, existing `tasks` take the `surface` default, and existing
`task_transitions` take `origin='actor'` — the value that is true for every row written before the
runtime could write one. Nothing is invented.

### D13 — The hook rule lands in `agent-capability-plane`

*No capability may exist only in a hook.* A hook may make an independently-enforced rule fire sooner
(at the offending tool call rather than at run end) or more pleasantly (inside the agent's transcript
rather than as a later rejection); remove the hook and the identical rule still fires at the boundary.

The repo already took this decision once, in another domain: `hub/hub/runner_commands.py:19-21` states
Claude's permission posture explicitly "rather than from whatever `~/.claude/settings.json` says on
the machine the Hub runs on." Hooks live in that same file. Writing the rule down here is what stops
a convenient shortcut from reversing it — and every mechanism in this change deliberately sits at a
boundary, so the change is entitled to state the rule.

### D14 — The board card is where binding becomes visible

The operator sets policy and escalation agent on the card, sees a divergence indicator there, and
starts a bound run from there. Policy that can only be set through an API is policy nobody sets.

## Risks / Trade-offs

- **The auto-transition changes the board without anyone asking** → bounded twice: binding only ever
  comes from an explicit cause (D3), and the move goes through B1's map (D4), so a run that may not
  make the move does not make it.
- **A long task spanning several turns opens a divergence on each intermediate run** → under the
  default `surface` this is a transient open row that closes on the next real transition (D6); under
  `retry` it produces one extra nudge, which is arguably what `retry` is for. It is still the
  weakest joint in the design — see Open Questions 1.
- **`retry`/`escalate` spend tokens on a schedule the operator is not watching** → default is
  `surface`, both are opt-in per task, and D8 makes a loop unexpressible.
- **Escalation reassigns work under the operator** → recorded, reversible, and visible on the card.
- **A validated `task_id` on delegation is a new refusal path** — an agent that names a task from
  another project, or a deleted one, now fails a call that used to succeed → the refusal names the
  problem and the message still sends unbound rather than being lost.
- **Two more nullable columns on the hot `runs` table** → both nullable, neither indexed unless the
  divergence query needs it; `runs` is already 18 columns and this is not the change that makes it
  expensive.

## Migration Plan

Four migrations, each guarded for a missing table in the manner of `0052`/`0053`, because an upgrade
starting from an early revision reaches them with only that revision's tables:

1. `0054` — `runs.task_id`, `runs.divergence_source_run_id`
2. `0055` — `inbound_queue_entries.task_id`
3. `0056` — `tasks.divergence_policy` (server default `'surface'`), `tasks.escalation_agent`;
   `task_transitions.origin` (server default `'actor'`)
4. `0057` — `run_divergences`

Head assertions bump in **both** `hub/tests/test_migrations.py` and
`hub/tests/test_project_persistence.py`.

Rollback is a downgrade per revision. Because nothing is backfilled and every default is the
pre-change behaviour, a partially-applied upgrade degrades to "no binding, no divergence" rather
than to a wrong state.

## Open Questions

1. **Is a divergence per intermediate run too noisy?** D6 resolves it by making divergence an *open
   condition* that closes on the next real transition, which is correct for `surface` and defensible
   for `retry`. It has not been seen against real usage. If it proves noisy the fix is a quiet
   period before the policy fires, not a change to the definition. **Revisit after first live use.**
2. **Should a divergence block archiving or completing the *conversation*?** Out of scope here; it is
   tier 3, and tier 3 is B4.
3. **Does the binding make B1's deferred question answerable** — whether `in_progress → completed`
   should be restricted to the assignee? It does: with a binding, "the assignee" stops being
   guesswork. Left open deliberately; changing an edge's actor rules belongs with B4's gates, not
   with the plumbing that makes it possible.
4. **Should `completed → under_review` be automatic too?** B1 left this status holding nothing
   (its D15, operator: *"too early to say"*). This change makes an automatic move technically
   trivial. Still declined: automating a step that means nothing yet makes it a formality with a
   mechanism, which is harder to remove than a formality.
