# Design — a task that is waiting, and a binding that outlives one turn

## Context

Both halves come from the operator reading the run→task binding on 2026-08-10, and both are
consequences of the same thing: the binding was built one run at a time, and a run is shorter than
the work.

Nothing here is implemented. The point of writing it down before building is `TRANSITIONS`
(`hub/hub/task_transitions.py:101-136`): B3's evidence checks and B4's completion gates will be
written against that map, so a status added now is cheap and the same status added later is not.

## Goals / Non-Goals

**Goals.** A task can say it is waiting on a person, and say so because the runtime observed it
rather than because an agent remembered to claim it. A piece of work spanning several turns is
checked at the turn where it actually stops.

**Non-Goals.** As stated in `proposal.md`.

## Decisions

### D1 — `blocked` is a ninth status, not a flag beside the status

A boolean `is_blocked` would leave `in_progress` on the board next to a run that is not running, and
every surface reading `status` would still be wrong. The board is the thing that has to be true.

The cost is real and is the reason this is a proposal: `STATUSES` is derived from `TRANSITIONS`, and
`hub/tests/test_task_transitions.py` pins it to two independent declarations in
`src/agentweave/constants.py` and `hub/hub/schemas/tasks.py`. A ninth status touches all three by
design — that pinning exists precisely so a status cannot be added in one place and forgotten in the
others.

### D2 — Proposed edges

| From | To | Who |
|---|---|---|
| `in_progress` | `blocked` | run, operator |
| `blocked` | `in_progress` | run, operator |
| `blocked` | `assigned` | operator |
| `blocked` | `rejected` | operator |

**`blocked → completed` is deliberately absent.** Work that was waiting and is now done passes back
through `in_progress`, so the history says the block ended before the work did. Allowing the shortcut
would let a task be completed while still recorded as waiting on a person who never answered —
which is exactly the class of untrue record B1 exists to prevent.

**`blocked` is reachable only from `in_progress`.** A task nobody has started is not blocked, it is
pending. This keeps the meaning "work began and then hit something".

**Reassignment and rejection stay open to the operator**, because "this agent is stuck, give it to
someone else" and "this is not worth unblocking" are both real.

### D3 — The runtime blocks; the answer unblocks

An agent does not request `blocked`. A run that ends with an unanswered **blocking** question open
has its bound task moved to `blocked`, `origin='runtime'`, attributed to that run — the same
mechanism as the automatic `in_progress` on binding.

Answering that question moves the task back to `in_progress`.

Derived rather than requested for the reason every other part of this mechanism is: a status an
agent asserts is a status an agent can assert falsely, and `blocked` is the one an agent under a
completion gate would most like to reach. Under D3 it cannot claim to be waiting on the operator
unless it actually asked the operator something the operator has not answered.

*Rejected: an MCP `block_task(reason)` tool.* Reads as the obvious design and inverts the incentive
this whole line of work exists to fix.

*Rejected: exempting a run with an open question from the divergence check instead* (the narrower
fix offered to the operator on 2026-08-10 and not taken). An exemption is invisible: the board still
says `in_progress`, and the operator still has to work out why nothing is happening. A status is the
answer to the question the exemption merely suppresses.

### D4 — A blocking question names the task it blocked

Answering has to know what to release, and the answer must not depend on re-deriving it from the
run — a run may have been bound to a task the question was not about.

**Settled: a nullable column on `Question`, not a join table.** A question blocks at most one task,
and `ask_user` gives no way to name several — a join table would model a cardinality nothing can
produce, and every reader would then have to handle a set where there is only ever one row.

The reason it is a column and not re-derived from `run.task_id` stands: a run may be bound to a task
the question was not about, and releasing the wrong task is worse than releasing nothing.

Per R5, the block's reason is filled from the question text, so this column is also what lets the
card say what it is waiting for.

### D5 — A blocked task is not divergent

It falls out of D3 rather than needing its own rule: the run *did* move its task, to `blocked`, so
`run_advanced_its_task` is satisfied — **provided the block is recorded as an actor transition and
not a runtime one.**

That is the one wrinkle worth stating, because it cuts against D3. Two ways out:

1. record the block with `origin='runtime'` and add "or the task is blocked" to the divergence
   check; or
2. treat the block as the run's own final act — `origin='actor'` — on the grounds that the agent
   did do something, namely ask.

**(1) is chosen.** `origin` should keep meaning "who caused this", and the runtime caused it. A
divergence check that has to know about `blocked` is honest; an origin that lies to make a check
simpler is not.

Note what this means concretely: the exclusion is on the task's *status at the run boundary*, not on
the transition that got it there. A task already blocked when the run ends is equally not divergent,
which is what makes a multi-turn blocked task safe under R4's conversation binding.

### D6 — The binding lives on the conversation; the run still records its own

`conversations.task_id` is the durable binding. At spawn, a run inherits it when the delivered
entries name no task of their own; an entry that *does* name one wins and rebinds the conversation.

`Run.task_id` stays. Transitions and divergences are attributed to a run, and an integrity record
that had to join through a conversation to say which task it was about would be weaker for it.

### D7 — Releasing a binding is explicit

The operator releases it, and a terminal transition of the bound task (`approved`, `rejected`)
releases it automatically.

Never inferred from what the operator seems to be talking about. A wrong guess silently stops
checking a run, and a mechanism that quietly stops enforcing is worse than one that never started.

### D8 — Two entry points to work, deliberately

The operator, on whether starting from a card competes with the composer (2026-08-10): *"I think
this changes with the phase of the project. So if a user is exploring things or wants to go over the
details, starting via composer is the obvious choice, but if it's a project that's underway,
starting the task makes more sense because everything is in order already. Both are valid at
different cycles."*

Recorded as a decision, not an observation: neither entry point is redundant, and neither should be
removed or made the "real" one. What D6 changes is that the composer path stops being the *unchecked*
one — a conversation already bound to a task stays bound through it.

## Risks / Trade-offs

- **A ninth status invalidates assumptions the UI makes about eight** → the board grows a column or
  a treatment; `test_task_transitions.py`'s pinning catches the declarations, not the layout.
- **Every composer turn in a bound conversation becomes a checked run** → this is the intent, and
  it is also what makes the previous change's Open Question 1 real for the first time. The two ship
  together or the noise question gets answered against the wrong mechanism.
- **A conversation bound to a finished task keeps checking runs** → D7's automatic release on a
  terminal transition, plus an explicit release.
- **`blocked` becomes a parking space** — a task blocked on a question nobody will ever answer sits
  there forever → out of scope here, but the divergence record already knows how to say "this has
  been sitting"; a staleness surface belongs with it, not with this.
- **An agent learns to ask a pointless question to reach `blocked`** → possible, and it costs it a
  real question row the operator can see. Worth watching rather than pre-empting.

## Migration Plan

`0059` — `conversations.task_id`. `0060` — the question→task link. Both guarded, both nullable, no
backfill: a conversation that predates this was not bound, and inventing one would start checking
runs nobody asked to be checked. Head assertions bumped in `hub/tests/test_migrations.py` **and**
`hub/tests/test_project_persistence.py`.

## Resolved questions

All five were settled with the operator on 2026-08-10, before any code was written, for the reason
stated in Context: `TRANSITIONS` is cheap to shape now and expensive to reshape once B3 and B4 are
written against it.

### R1 — A non-blocking question does not block the task

`ask_user(blocking=False)` is the agent leaving a note and carrying on. Only an unanswered question
with `blocking=True` moves the task. Blocking on a note would make the status mean "an agent
mentioned something", which is not a thing anyone is waiting on.

### R2 — A timed-out question leaves the task waiting, and that is all

The timeout is agent-side — `AW_QUESTION_TIMEOUT` is read in the MCP server process, and the Hub's
`Question` row has no timed-out state; it simply stays unanswered. So a task blocked on a question
nobody answers stays blocked indefinitely.

**Left as is, deliberately.** The task *is* still waiting, so `blocked` remains truthful, and the
alternative that looks tidiest is the dangerous one: auto-unblocking to `in_progress` on timeout
returns the task to the divergence check while the agent is still waiting on the same unanswered
question — reintroducing exactly the retry-into-a-wall bug this change exists to remove.

A "this has been sitting" staleness surface is the right answer and is **out of scope here**. It
belongs with the divergence records, which already know how long something has been open, and it
should cover both parked cases rather than only this one.

### R3 — `blocked` renders as a treatment on `in_progress`, not a ninth column

The status is real either way — this is a board-layout decision only, and `STATUSES` is unaffected.

A blocked card stays in the `in_progress` column with a distinct treatment and a badge naming what
it is waiting for. The operator has already called the board crowded, and a ninth column widens it
for a state that is not a separate stage of work: blocked *is* in-progress work, stopped. Keeping it
in the column also means the card does not move when it blocks and move back when it unblocks, which
would read as progress where there is none.

### R4 — The binding lives on the conversation

`conversations.task_id`, as D6 proposed. A thread is about a piece of work, and two conversations
with the same agent about different tasks stay correctly separate.

*Rejected: binding to the agent.* It permits an agent only ever one task, and opening a second
thread with that agent would silently rebind the first — a wrong binding that stops checking a run,
which D7 exists to prevent.

*Rejected: conversation binding with an agent-level fallback.* The fallback is a binding nobody set,
applied by inference. That is the same silent guess D7 refuses, arriving through a different door.

The case that motivated the question — one task worked across two conversations — is handled by
binding both. That is honest about what is happening, where a single agent-level binding would
quietly attribute one thread's work to the other.

### R5 — A block names what it is waiting for

A free-text reason on the block. Required when the operator sets it by hand; auto-filled from the
question text when the runtime sets it. Cheap, and it is the whole difference between "blocked" and
"blocked on the API key" — which is what R3's badge has to display for the treatment to be worth
more than a tint.
