# The other half of the binding: a flow's own work runs do not know what they are working on

**Date:** 2026-08-26 · **Found while:** implementing group 4 of `one-answer-to-what-is-happening`
**Status:** exploration. No code written. Nothing here is proposed yet.

## How this surfaced

Group 1 of `one-answer-to-what-is-happening` closed a hole for reviews: a review turn's queue entry
carried `review_task_id`, `binding_from_entries` read only `task_id`, so **every review run in the
product's history was unbound** and `run_advanced_its_task` waved each one through on *"no task to
have neglected"*.

Task 4.7 then asks to remove the board's agent-fallback, on the reasoning that D1 made
`Run.task_id` trustworthy. Before removing it I checked whether it was still load-bearing. It is —
because reviews were only half the hole.

**A flow's ordinary work firing sets no `task_id` on its queue entry either.** The two staging
paths (`scheduler.py:2284` and `scheduler.py:2600`) pass `review_task_id` and nothing else. So a
firing claims a task, writes its assignee, moves it to `assigned`, fires an agent — and the run it
starts carries no record of which task it is for.

## Measured, not read

All figures from `~/.agentweave/hub/profiles/beta/agentweave.db`, read-only, 2026-08-26.

| | |
|---|---|
| Job-origin queue entries | **61** |
| …carrying `task_id` | **0** |
| …carrying `review_task_id` | 6 |
| Runs delivered a job entry | 59 |
| …bound | **5** — inherited from an earlier operator turn in the same thread, not from the firing |
| Runtime `→ in_progress` transitions in the entire database | **10** |

That last row is the sharpest. `bind_run_to_task` moving a task to `in_progress` is *the* mechanism
by which "an agent is working on this" becomes true without asking the agent. Ten occurrences,
total, across 202 runs.

Binding today happens almost entirely through the two paths that name a task explicitly:
delegation (`send_message` with `task_id` — 22 of 77 agent-origin entries) and an operator starting
work from a card (12 of 53 operator-origin entries). **The flow, which is the product's main loop,
binds essentially never.**

## Why this is more than a rendering defect

`run_advanced_its_task` returns `True` for any unbound run. So the run boundary check — the whole
enforcement that a turn either moves its work or is recorded as not having — **has never applied to
a flow's own work turns.** The 14 divergence rows that sit on loop tasks came from delegated and
operator-triggered runs, not from firings.

The board compensates with the agent-fallback, and that fallback's own comment states the price:
it *"can still over-report `working` when an agent is mid-turn on a different task."* Which is to
say the renderer is patching, at display time, an edge the data model never wrote. That is L1 of
this change's own three-layer diagnosis, on the larger half.

## It is a gap, not a decision

Two things to check before calling something an oversight, and both check out.

**The shipped spec already requires it.** `openspec/specs/run-task-binding/spec.md:53`:

> The system SHALL set a run's binding itself, **from the cause that started the run.** No
> agent-facing operation — over HTTP or MCP — SHALL create, change, or remove a run's binding.

A flow firing is a cause that started a run, and it knows the task: it just claimed it. The
requirement does not carve flows out.

**Nobody wrote down a reason to leave work runs unbound.** The comment sitting beside the missing
line is about the *checkout*, not the binding — *"Set only for a selection the ladder made as a
review, so ordinary work acquires no checkout."* That is correct and should stay; it says nothing
about `task_id`.

Meanwhile `loop-becomes-a-flow`'s design (archived, line 450) records rewriting a checkpoint fixture
to have **`run.task_id` NULL**, because that is what the product produces for a flow. The NULL was
observed and worked around, in the same change whose docstring warned *"the fixture builds what the
product does not build"*. So the gap has been seen. It has not been decided.

## What binding a work run would switch on

This is the part that deserves thought rather than a one-line patch, and it is why this is an
exploration rather than a commit.

**1. The task starts itself.** `assigned → in_progress` becomes a runtime transition the firing
causes. Today a flow's task sits at `assigned` while an agent works it, and `assignee_status` is
derived from a column the agent has to write. This is the fix working as designed — but it changes
what the board shows and when, and it is the first time it would fire at flow scale.

**2. Every flow work turn enters the divergence boundary.** This is the real question. A turn that
ends without moving its task records a `RunDivergence` and a `run_diverged` event at `warn`.

The first cut of this number was alarming and **wrong**, and the correction is the point:

| Population | Runs | No actor transition |
|---|---|---|
| All job-origin work runs | 55 | 45 (82%) |
| …excluding `toolkit-sandbox` | **19** | **9** (47%) |

`dev` accounts for 36 runs, all silent, all in `toolkit-sandbox` — **a project with zero loop
tasks.** Those firings claimed nothing, so they would never bind and would never diverge. Counting
them made the flow look like it drops four turns in five. Scoped to projects that actually have
loop tasks, it is 9 of 19, spread across `builder` (7) and `relay` (2) on `ledger-stress`.

Nine is a very different number from forty-five, and reading it right matters:

- Roughly 19 firings across 18 loop tasks is ~1 firing per task, so these are not obviously
  intermediate turns of long work — but `ledger-stress` is a stress fixture and its shape should
  not be generalised from.
- The divergence design already anticipates multi-turn work: `resolve_divergences_for_task` closes
  every open row the moment an actor transition lands, precisely so the default policy does not
  *"read as an accusation against an agent that is simply not finished yet."*
- So the rows are open-then-closed conditions, not verdicts. **But the `warn` event is emitted at
  the moment of opening and is never retracted.** An operator watching the activity log would see a
  warning per intermediate turn, and the closing is silent.

That asymmetry — a loud open and a quiet close — is the thing to design for. It is the same shape as
the noise argument that kept `deferred` from becoming an event in `loop-notices-and-reacts` D6:
*"emitting for that would bury `review_unstaffed` — the one that genuinely needs the operator —
under the healthy case."*

**3. `retry` and `escalate` become live for flow work.** All 40 tasks carry `surface` today, so
nothing would spawn on day one. But the policy would be reachable from the flow for the first time,
and a task set to `retry` would start re-running its agent on every silent intermediate turn. Group
2 of the current change reached exactly this conclusion for reviews and carved them out entirely.
Work is not reviews and the same carve-out is not obviously right — but the question is now open for
work too, and it was not before.

**4. The flow's conversation becomes bound.** `resolve_bound_task` returns `named=True` for a
delegated task, so `rebind_conversation` would point the thread at the task. Flows run
`session_mode: new`, so each firing gets a fresh conversation and this stays contained — but it is a
change, and `release_conversations_bound_to` then fires on terminal statuses.

## What I would want an answer to before proposing anything

1. **Is the `warn` on a divergence right once it fires per intermediate turn?** Options include
   severity by whether the row is still open, emitting only on the *second* consecutive silent turn
   for the same task, or leaving the event and fixing the close to be as visible as the open.
2. **Should work get the same policy carve-out reviews just got?** `retry` on a turn that is simply
   not finished yet re-runs an agent that was doing fine. That is the F45 spend-loop shape.
3. **Does the task auto-starting at `in_progress` change what the flow board should show?** It
   removes the reason the agent-fallback exists, which is the whole point — but 4.7 should land
   with it, not before it.
4. **`dev`'s 36 firings on an empty queue in `toolkit-sandbox`** — separate finding, not this one.
   A loop fired 36 times with nothing to claim. `_loop_stall_reason` is supposed to be what an
   operator sees for that. Worth checking whether they saw it.

## What this does *not* block

Only task 4.7 of `one-answer-to-what-is-happening` depends on this. Groups 1, 2, 3 and 5 are
complete and pushed. Group 4's owned `task_attribution` module, its encapsulation test and the
`agent_role` → `agent_capacity` rename are all independent and proceed.

Until this is settled, the agent-fallback **stays**, and it stays with a comment pointing here —
because a fallback whose reason is written down is a different object from one that is merely
still there.
