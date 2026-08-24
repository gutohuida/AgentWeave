## Context

A loop is a mature sequential executor — 27 requirements, three bugs found only by driving it live.
The operator's standing decision (`2026-08-20-the-loop-under-dependencies.md` §1) is *"improve the
loop, do not rebuild it"*, and this design is written to satisfy that literally: the audit in
`2026-08-21-the-loop-becomes-a-flow.md` §3 found **20 of 25 requirements untouched**.

*(Recounted 2026-08-24. The audit said 25, and `agent-loops` now has **27** — `task-dependencies`
added §690 and §723 after this was written. This change's delta modifies **3**, so 24 of 27 are
untouched and the "extension, not a rebuild" evidence is stronger than the sentence above claims,
not weaker. The two new ones are both in groups 3 and 5's path and were read before this recount.)*

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
(`hub/hub/task_transition_service.py:108`, read by the guard at `:153`), which author/reviewer
separation reads for
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
   1b. a declaration that does NOT resolve  — surface it; never substitute
   2. no declaration: any agent not running and holding no active task
   3. surface: "could not staff this step"
```

**Amended 2026-08-24, after `a-reviewer-can-see-the-work` shipped.** This ladder was written on
2026-08-21 and had rung 1 falling through to rung 2 on an unresolvable declaration. Three days later
`review_turn.resolve_declared_reviewer` shipped doing the opposite, deliberately, with the reason in
its docstring: *"an operator reading 'reviewed by critic' when `critic` does not exist and `auditor`
reviewed it has been told something false about who checked the work."* Two answers to one question,
and the shipped one is live and carries the argument.

So rung 1b is now explicit, and it is the right distinction rather than a concession: **silence and
a failed declaration are different facts.** Nobody named a reviewer → the flow is free to choose, and
rung 2 still runs the whole thing with nothing configured, which is the operator's objection
answered. Somebody named a reviewer and the name did not resolve → substituting misrepresents who
checked the work, and the operator is the one who can fix the name.

**Resolution is against agent names, and this is settled rather than open.** `resolve_declared_reviewer`
matches the declared string against roster `Agent.name` for this project, and treats an archived
agent as unresolved for the same reason `trigger_agent_directly` refuses one. The flow reuses that
function; it does not write a second resolution. This closes what the Open Questions below listed as
*"against charters, agent names, or both"* — `task-dependencies` D11 left it to the flow, and the
reviewer change answered it first.

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

**The largest mechanical consequence:** `_claim_loop_task` returns one task. *(Corrected
2026-08-24: this said "three callers assume it". There was **one** — `_do_fire_job`. The board never
called it; it kept its own copy of the startability rule with a comment saying it "mirrors" the
firing's. Group 1 turned that copy into a real shared call, `scheduler.candidate_is_startable`, so
the count is now genuinely two and they cannot drift.)* The set-valued form must land before
anything else in this change is useful.

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

### D9 — A firing that staffs a review delivers a review turn, not an ordinary one

**Added 2026-08-24.** This design was written on 2026-08-21, three days before
`a-reviewer-can-see-the-work` shipped, and it therefore describes firing a reviewer as an ordinary
firing. It is not one, and the difference is the whole of finding F10.

An ordinary firing puts the agent in its own working checkout. Unreviewed work exists only on the
author's branch, so a reviewer given an ordinary turn cannot see the thing it was fired to review —
which is circular in exactly the way `review_turn.py`'s own docstring records: *"the only way to see
it was to integrate it — which is what the review was meant to decide."*

The mechanism already exists and this change reuses it rather than inventing a second one. A turn
becomes a review turn when it carries a `review_task_id` — either passed to the trigger or read off
the queue entry (`InboundQueueEntry.review_task_id`, migration `0086`) — at which point
`prepare_review_turn` resolves the commit the task's most recent evidence cites, builds a detached
checkout of it, and states in the turn context that this is a review, of which task, at which
commit.

**So the concrete gap is one argument.** `scheduler._do_fire_job` builds its entry with
`new_entry(...)` and passes no `review_task_id` (`hub/hub/scheduler.py:1187`). A flow staffing a
review must pass it.

*Rejected:* **firing an ordinary turn and letting the agent find the branch itself.** That is what
produced F10 — the reviewer asked the author what changed. It also puts the author's branch inside
the reviewer's own checkout, which is the isolation boundary `worktrees.py` exists to hold.

*Rejected:* **downgrading to an ordinary turn when the review turn cannot be prepared.** A reviewer
silently placed somewhere it cannot see the work reports on what it can see, and the operator reads
that as a review. `ReviewTurnRefused` already carries a stated reason; surface it.

**Consequence for D4.** Rung 2 selects "any free agent", and a review turn is per-agent isolation —
so the agent rung 2 picks determines which checkout is built. Nothing here requires the same agent
across retries, but a released or re-fired review builds a fresh checkout, which is the bounded and
reused behaviour the reviewer change's own third requirement already specifies.

### D10 — Review outranks new work, because the ordering already said so

**Added 2026-08-24, implementing group 3.** `_loop_queue_order` sorts non-`pending` rows first, by
`updated` descending, then pending rows oldest-first. A `completed` task is non-pending, so the
moment group 3 makes one claimable it sorts **ahead of** untouched pending work — a flow reviews
finished work before starting more.

That was inherited rather than chosen, and it is being written down rather than changed, because it
is the behaviour a queue should have: work that is finished and waiting on a second pair of eyes is
closer to done than work not yet begun, and letting it wait while the flow opens new fronts is how a
queue accumulates a tail of unreviewed work. It also falls out of the same rule that already makes
an in-progress task outrank a pending one, so there is one ordering rule rather than an exception
for review.

The author is unaffected: it walks past its own finished task and takes the pending one, because
claimability is answered per agent before ordering is consulted.

*Rejected:* **a separate ordering for reviewable candidates.** Two orderings is what
`_loop_queue_order`'s own comment records going wrong — the board and the firing each had one, both
shared a flaw, and two consistent wrong answers read as a match.

### D11 — A non-author agent may take a task to `approved`

**Decided by the operator 2026-08-24**, answering a question carried unanswered since handoff 0078
and load-bearing for everything in groups 3, 4 and 4b.

An agent may sign work off. The only guard is author/reviewer separation — the agent that recorded
the move to `completed` may not approve, reject or request revision of it — and that guard is
already implemented, already tested, and already the thing group 3's claimability defers to.

Two consequences worth stating, since a later reader will ask:

- **The flow's review is a real review, not a staging step.** A reviewer's turn can end at
  `approved`, so a queue can drain without the operator in it. That is what makes an unattended flow
  possible at all; without it every loop stops at a wall of finished work.
- **The operator is not removed from the loop, only from the critical path.** `ask_user` and the
  permission posture still stop a run, and B4's evidence gates still govern *what* an approval
  requires. This decides who may press the button, not what has to be true before it is pressed.

### D12 — Ordinary work resolves an agent too, and an assignee outranks the default

**Decided by the operator 2026-08-24, implementing group 5.** D2 made the job's agent the *default*
and D4 built a ladder for reviewers, which left the question D5 needs answered and does not ask: a
firing that starts three ordinary tasks has to say who works the second and third. `decide_firing`
paired every non-review candidate with `default_agent`, so widening the walk literally would have
produced three selections that D6 then collapsed to one — a flow with three independent tasks and
three idle agents starting one, which is D5's own *Rejected* case reached by accident.

So ordinary work resolves an agent, in two steps:

1. **A candidate that already has an assignee resumes with that assignee.** This closes the open
   question below rather than deferring it again, and it is the finding that made the rest visible:
   `claimed_task.assignee = selection.agent` is unconditional, so under width a task running under
   agent B is re-selected next tick as ordinary work, reassigned to the job's agent and briefed to
   them while B is still working it. An `in_progress` or `assigned` task is *already staffed*; the
   firing is resuming it, not staffing it.
2. **Otherwise the job's agent takes the first such task and each further one takes the next free
   agent**, drawn from `_agents_that_are_free` — the same not-running, holds-no-active-task,
   not-archived, runner-bound set D4 rung 2 already uses. One notion of "free" in the module, in
   queue-stable order, so a wide firing pairs the same tasks with the same agents on a rerun.

   **The job's own agent is tested against "running a turn", not against that free set**, and the
   asymmetry is deliberate. `_agents_that_are_free` is a *recruitment* pool: it additionally demands
   a roster row with a bound runner and no active work, which is the right bar for an agent the flow
   is choosing on the operator's behalf and the wrong one for the agent the operator already chose
   when they created the job. Applying it to the default made a loop whose agent happens to hold any
   active task — or whose project has no roster rows at all — resolve nobody and read as stalled.
   That is not hypothetical: the dependency board derives its current item from this same walk, so
   the first implementation of this decision broke the board's agreement with the firing, which is
   `task-dependencies` human-only check 13.1 and has a shipped test.

*Rejected:* **running D4's full ladder over ordinary work.** Its rung 1 is
`resolve_declared_reviewer`, which is review-specific; an ordinary-work sibling would be a second
resolver with no requirement asking for one. *Rejected:* **leaving ordinary work at width one.** It
fails task 5.1 as written and is the shape D5 rejects.

**The busy guard has to move for any of this to be reachable.** `_do_fire_job` calls
`_loop_agent_busy_reason(..., job.agent)` and returns before `decide_firing` runs, on the stated
grounds that "a loop's agent runs one turn at a time" — true of a loop, false of a flow, where
`job.agent` is only the default. Left there, the moment a flow staffs its own job's agent, every
tick for the length of that turn refuses to staff any *other* free agent on any *other* independent
task, and width is reachable only inside a tick that finds the job's agent idle. Busy-ness becomes a
fact about *a candidate agent* — it excludes that agent from resolution — rather than a reason to
abandon the firing. A firing that resolves nobody for anything still refuses, which is the old
behaviour of a single-agent loop, unchanged.

### D13 — A wide firing records one `JobRun` per selection

**Decided by the operator 2026-08-24.** `JobRun` correlates back to the `Run` it started **only**
through `conversation_id` — `finalize_job_run_for_conversation` says so, and `models.py` records
that there is no foreign key. A firing that starts three agents creates three conversations, so one
row per firing would have nothing left to correlate with, and would need a new rule for when a run
covering three agents stops being "in progress".

One row per selection keeps that correlation exactly as it is: the finalize path is untouched, and
each agent's outcome — completed, failed, the error summary — is separately visible instead of
being merged into a single verdict for the tick.

Two costs, accepted rather than mitigated:

- **`_prune_job_history`'s 100-row window fills N times faster** for a flow of width N, so a wide
  flow keeps proportionally less history. Left alone: the window is per job, and a flow doing three
  times the work per tick producing three times the rows is the window measuring the same thing.
- **`JobCard`'s history shows N rows for one tick.** Correct rather than noisy — they are N turns.

*Rejected:* **one `JobRun` spanning several conversations**, which breaks the only correlation there
is. *Rejected:* **parent and child rows**, which is a migration and a UI change on top of this
group's scheduler work, for a presentation improvement group 9 is the place to consider.

## Risks / Trade-offs

**[Set-valued claim breaks the board, the firing and §548 at once]** → Land the set-valued form
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

**[A flow's review turn multiplies checkouts]** → Every staffed review builds a detached checkout,
and D5 permits several at once, so a wide flow can build several in one firing. The reviewer
change's "A review checkout is bounded and reused" requirement is what bounds this, and it was
written for one reviewer at a time — confirm it still holds when a flow staffs three
(`scripts/drive/FINDINGS.md` F22 is also open here: shared-dependency symlinks fail on Windows
without Developer Mode, so a review checkout of a project with `node_modules` or `.venv` is
unproven).

## Migration Plan

No data migration. `Checkpoint.agent` already exists and already records the writer; what changes is
which lineage a firing reads, and it already reads by loop.

Every existing loop becomes a loop, not a flow — none declares a document unless someone declared
one. The behaviour of a flow with one agent is today's behaviour, so the regression suite is the
existing loop suite, unmodified.

## Open Questions

- ~~**May an agent take a task from `under_review` to `approved`?**~~ **Answered 2026-08-24: yes,
  provided it is not the agent that completed it.** See D11.
- **What does the board show for a flow staffing several tasks?** The dependency board renders the
  graph; whether concurrent work is shown per card, per layer, or as a flow header is undecided.
- ~~**How is a declared reviewer resolved — against charters, agent names, or both?**~~
  **Answered 2026-08-24: agent names.** Not decided here — `a-reviewer-can-see-the-work` shipped
  `review_turn.resolve_declared_reviewer` first, matching the declared string against roster
  `Agent.name` and treating an archived agent as unresolved. See D4.
- ~~**Does a flow ever fire the same agent for a task it is already working?**~~ **Answered
  2026-08-24: yes — an already-assigned task resumes with its own assignee, never with the job's
  default agent.** See D12, step 1.
- **Cross-firing selection races** — see the risk above.
