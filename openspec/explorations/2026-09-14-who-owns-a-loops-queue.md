# Who owns a loop's queue

**2026-09-14 evening, interactive session with the operator.** Not a proposal and not a change
directory: an exploration, written while deciding F352-free (the OPERATOR QUESTION left open by
`openspec/changes/an-unstaffed-review-names-its-holders`). Every figure below was measured against
the operator's `:8000` database read `mode=ro`, or read out of this checkout's source. The
repository is public, so LoopEngine is cited and never quoted.

It exists because F352-free asks *"which holdings make an agent unavailable to a flow"* and the
five options in that proposal all argue about **which statuses count**. The measurement says the
statuses are not the variable that matters.

## What we saw

LoopEngine was frozen for twelve hours. Not slow — stopped. The last agent turn of any kind ended
at 07:02, and from then until at least 19:13 the loop's `*/5` job fired on schedule and recorded
`review_unstaffed` **498 times in a row**, claiming no agent was free.

All four agents were idle. Between them they held ten tasks, and **not one of the ten had a live
run, a queued inbound entry, or an open question against it**:

| agent | holds | inside the loop? |
|---|---|---|
| Architect | 1 × `under_review` | yes — moved there by the operator at 21:00 the previous night |
| dev | 3 × `in_progress`, 1 × `pending` | **no — all four outside** |
| dev_2 | 4 × `pending` | **no — all four outside** |
| tester | 1 × `pending` | yes |

Nobody was busy. Nobody was waiting for anything. Every one of them was disqualified.

### The eight tasks that did it

Every one of the eight out-of-loop holdings was **created by the Architect and assigned to somebody
else** — four to `dev`, four to `dev_2`. Five of the eight were created by a run whose *own* task was
inside the loop, so they are literally the case the operator described: new work discovered during a
development cycle.

The Architect was doing its job. It found follow-up work while executing the loop, and filed it. It
could not put that work in the loop — it is not the loop's job agent, and `Loop.control` was never
delegated — so it did the only other thing `create_task` offers: it created a free-floating task and
named an assignee.

**Each one permanently disabled that assignee.** The Architect disabled both of the project's
implementers, eight decisions at a time, by correctly reporting work it had found.

## The mechanism, in three facts from the source

1. **A loop only ever walks its own tasks.** `_loop_candidates` filters `Task.loop_id == loop.id`
   (`hub/hub/scheduler.py:717`). A task with `loop_id` NULL is invisible to every firing, forever.
   Nothing automatic will ever start it, move it, or close it.
2. **Any assigned task in a live status disqualifies its assignee.** `_agents_that_are_free`
   (`scheduler.py:1022`) subtracts every agent named as `assignee` on a task whose status is in
   `LIVE_STATUSES` — `pending`, `assigned`, `in_progress`, `revision_needed`, `under_review`
   (`task_transitions.py:338`). It does not ask whether anything will ever move that task.
3. **One predicate answers three different questions.** The same function is read by the firing
   guard (`:306`, "is anyone free at all"), by the reviewer ladder's rung 2 (`:1187`, "who reviews
   this"), and by the flow walk (`:1368`, "who takes new work"). A holding that disqualifies an
   agent for one disqualifies it for all three.

Composed, those three facts make a **ratchet**:

```
   agent executing a loop finds follow-up work
              │
              ▼
   cannot add it to the loop (not the owner)
              │
              ▼
   create_task with no loop_id, assigned to a worker
              │
              ▼
   nothing will ever walk it  (fact 1)
              │
              ▼
   its assignee is disqualified for everything  (facts 2 and 3)
              │
              ▼
   and can never be re-qualified, because the only thing
   that would clear the holding is working the task
```

It only turns one way. Every follow-up filed costs the project one agent, permanently. The more
diligent the roster, the faster the project seizes. LoopEngine ran well for a day and then locked
solid, and this is why — the quota wall (F355) was a symptom layered on top of a board that was
already unstaffable.

## The four properties, and which one a free-floating task actually gets

A task carries four independent properties. Today they are welded to different sources, and only
one of them survives the `create_task` route — the harmful one.

| property | where it comes from | `create_task` | materialised from the document |
|---|---|---|---|
| traceability — which requirement it serves | `requirement_ids` | yes | yes |
| queue membership — anything will work it | `loop_id` | owner only | yes |
| graph position — what it waits on | document `depends_on` | **never** | yes |
| **disqualifies its assignee** | `assignee` + live status | **yes** | yes |

"Never" in the third row is literal, not "not yet". `materialise()` is **the only writer of
dependency edges in the system** (`hub/hub/spec_tasks.py:293-299`, `task-dependencies` design D5) and
it runs only from an approved document. `create_task` has no `depends_on` parameter and no route to
one. A task created outside the document is unordered by construction and can never be ordered.

## The operator's model, and how much of it is already built

The operator's framing, stated in session:

> The loop cannot be edited by a worker, only by the one who owns it — the one who created the loop
> or flow. The assignee is the *executer*; the creator is the *owner*. A task that appears during a
> loop goes to the owner for approval first. If it is really needed the owner puts it in the loop,
> and amends the spec — flagged as an amend — so a new task enters the loop's structure.

Measured against the code, five of the seven pieces exist:

| piece | state |
|---|---|
| a loop has an owner distinct from its executer | **the field exists, the design discarded it** — see below |
| detect a task born inside a loop | **derivable today**: `Task.created_by_run_id` → `Run.task_id` → `Task.loop_id`. Used to label the five above |
| route it to the owner for approval | **missing** |
| the owner admits it to the loop | **shipped**: `_authorize_loop_task_creation` (`hub/hub/api/v1/tasks.py:601`), and `create_task(loop_id=…)` already documents the rule |
| amend the spec, flagged as an amend | **shipped but gated**: `SpecEditProposal`, `change_kind` ∈ `add`/`modify`/`remove`, agent proposes and the operator accepts — but only at `contract`/`gate` rigor. LoopEngine's document is `sketch`, where a submission writes through silently |
| the amendment lands as loop tasks | **shipped**: `materialise()` is idempotent and stamps the owning loop's `loop_id` on everything it creates, edges included |
| ask without stopping the agent | **modelled, not offered**: `Question.blocking` defaults to `False`, `Question.blocked_task_id` parks one task rather than the agent, and `unanswered_blocking_question` (`run_task_binding.py:638`) is what decides a task is parked. The agent-facing `ask_user` always blocks the turn |

### Owner and executer — the field exists and the shipped design picked the other one

`Loop.created_by_run_id` records the creating run, and through it the creating agent. For
LoopEngine's loop that resolves to the **Architect**. `AIJob.agent` — the loop's executer — is
**dev**. `Loop.control` is `None`, so control was never delegated and sits with the operator.

`_authorize_loop_task_creation`'s docstring states the choice plainly: *"D8 collapses 'creator' into
`Loop`'s own `AIJob.agent` — there is no separate creator field, deliberately."* So the authority a
delegation would hand over goes to the **executer**, while the agent that actually composed the
decomposition has none.

That is not a missing feature so much as a reversal to make deliberately, with D8 named. The data to
un-collapse it has been recorded on every loop since the table existed.

## The amend trigger, and why it is decidable rather than a judgement

The operator's rule — *amend only when it is needed, otherwise just create the task with its
requirement ids* — needs a definition of "needed" that an agent can apply without taste. The
property table supplies one:

> **Does the new task need a dependency edge?**
>
> - **No** → the owner admits it straight to the loop. No document change. It is worked, and it now
>   *legitimately* holds its assignee, because something will in fact start it.
> - **Yes** → it must be ordered against existing work, and ordering exists only in the document.
>   So it needs an amendment, because the document is the only place an edge can be written.

This is mechanical, not a matter of degree: `create_task` cannot express an edge, so *needing an
edge* is exactly the condition under which the lighter route is unavailable. Most discovered work —
"this spawn should not string-join a shell command" — needs no edge and should never touch the
document.

Worth separating in R1: amending **requirements** (new scope, a new FR) and amending the
**decomposition** (a new task entry against requirements that already exist) are different weights
of change, and the operator's rule reads as being about the first. `SpecEditProposal` is
requirement-and-metadata shaped today.

## Approval as a question that does not stop the work

The operator's third condition — a question that needs answering must surface distinctly in the Hub,
and the agent must keep working everything it *can* work meanwhile — is the same mechanism as the
admission queue, not a second one:

- the proposed task is the `blocked_task_id`;
- the question is `blocking = False`, so the asking turn is not suspended;
- the agent continues on its other queue;
- the Hub renders an admission decision distinctly from an ordinary question.

The model already carries both fields. What is missing is an agent-facing way to raise one, since
`ask_user` blocks unconditionally. LoopEngine's evidence that this matters: 8 overnight questions
went unanswered and 3 batches were answered after their wait had already expired — an approval queue
only the operator can drain will accumulate silently, which is tolerable for *admission* (that is the
guardrail working) and is not tolerable if it also stops the agent.

## What this means for F352-free — the decision this was written for

The five options in `an-unstaffed-review-names-its-holders` all vary *which statuses hold*. None of
them distinguishes a task something will work from a task nothing will ever touch. Under every one
of them, a single assigned out-of-loop task still disqualifies its assignee forever; (a) comes
closest and was dismissed on the grounds that *"agents file their follow-ups with no `loop_id`"* —
which is not a weakness of (a) but a description of the defect.

D4's original argument for the strict rule is sound **inside a loop**: *"an agent can hold three
assigned tasks and be idle between turns, which is the pile-up the operator named."* Those three
tasks are a real queue the agent will genuinely reach. Outside a loop the same three tasks are a
phantom queue nothing will ever serve, and the pile-up objection does not transfer, because nothing
can pile up on a list no firing reads.

So the sharper predicate is not a status set but a reachability test:

> **Is anything ever going to move this task on its own?**
> In a loop → yes. It is a real queue. It holds its agent, exactly as D4 intended.
> Outside a loop, nothing queued, no live run → no. It is a bookmark, and a bookmark must not cost
> the project an agent.

**And the two decisions are coupled.** If admission control ships, out-of-loop assigned tasks largely
stop being created, and the strict rule stops hurting — it can stay as D4 wrote it. If admission
control never ships, the availability rule has to be loosened to compensate for a defect upstream of
it. That coupling is the argument for deciding the admission design's *direction* before answering
F352-free, which is what this exploration is for.

## Open, and left to R1

- **Does the owner concept reverse D8, or sit beside it?** A third column (`Loop.owner_agent`)
  versus deriving the owner from `created_by_run_id` at read time. The second writes no migration
  and cannot drift from the fact it is derived from; the first survives a run being pruned.
- **An operator-created loop has no creating run.** `created_by_run_id` is NULL and the owner is the
  operator, which is the common case and must be the default rather than an edge case.
- **What admits a task: a new row, or a task status?** A `proposed` status would reach
  `STATUS_BANDS`, every derived set, and the transition table. A separate admission row mirrors
  `SpecEditProposal` and touches none of them. The second looks much cheaper and is the shipped
  precedent for exactly this shape.
- **Do the ten existing holdings get cleared, and by whom?** This exploration explains them; it does
  not retire them. An answer that only prevents new ones leaves LoopEngine frozen.
- **Does admission apply to an unassigned task?** A free-floating task with no assignee costs
  nobody anything today, because `_agents_that_are_free` reads `Task.assignee IS NOT NULL`. The
  cheapest partial mitigation available — refusing to *assign* an out-of-loop task — is worth
  pricing against the full design before the full design is built.
- **Whether the Architect's eight suspended messages are the other half of this.** Exactly 8 of the
  20 hop-suspended entries were sent by the Architect, and it created exactly 8 orphan tasks
  (F361: a suspended message tells its sender it was sent). Suggestive, unproven, and cheap to check
  from the entries' content.

## Rough cost — a code read, not an estimate anyone has tested

- `hub/hub/scheduler.py` — the reachability predicate, and which of the three callers read it.
- `hub/hub/api/v1/tasks.py` — `_authorize_loop_task_creation` gains the owner; the create route
  gains the admission branch.
- `hub/hub/db/models.py` + one migration — the admission row, if R1 takes that route.
- `hub/hub/mcp_server.py` — an agent-facing non-blocking question, and `create_task`'s refusal
  telling the agent to propose rather than orphan. **This file is the constraint**: every agent turn
  on `:8000` spawns it fresh from the working tree (F354), so it is not edited on a build day.
- `hub/ui` — the admission surface, under the bundle-compatibility rule.

Nothing here is small. The reachability predicate alone (`scheduler.py` only, no migration, no
`mcp_server.py`, no UI) is severable, is what unfreezes a board, and is the half worth building
first.
