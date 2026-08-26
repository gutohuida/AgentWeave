# 2026-08-26 — One answer to "what is happening right now"

Exploration behind the change that will fix F49, F63 and F64 at their root rather than one at a
time. Opened after archiving `loop-becomes-a-flow`, when the operator asked what actually needed
exploring. Every number in this document was measured against the live trial database
(`~/.agentweave/hub/profiles/beta/agentweave.db`, read-only) or read out of the code on
`autonomous/2026-08-26-drive-everything-and-fix-it`, not carried over from a prior write-up — two
of the claims that *were* carried over turned out to be wrong, and both are corrected below.

## Why this exploration exists

Five findings looked like one defect: the Hub says something it does not know, or knows something
it does not say.

| | |
|---|---|
| **F49** | `agent_role` could never say `working` — a set of tuples asked with a bare string |
| **F52** | the `workspace` posture never sees a git command; every commit refused, silently |
| **F61** | eleven flow conversations, all titled `Ledger flow` |
| **F63** | the board says an agent is mid-turn on work nothing is running |
| **F64** | one unstaffable queue, two surfaces, two different causes, opposite remedies |

The starting hypothesis was that these were one problem with one fix, and that the fix was
event-sourcing the state core — the shape the OpenHands SDK paper (arXiv 2511.03690) argues for,
where an append-only `EventLog` is the single source of truth and state is replayed rather than
mutated.

**That hypothesis is wrong, and rejecting it is the first result.** These are three defects at three
layers, and event-sourcing addresses one of them.

```
            THE TURN                     WHERE TRUTH IS LOST
  ┌───────────────────────────┐
  │  operator / scheduler     │
  │  decides to fire          │──── L2: one word, two meanings ────▶ F63, F64
  │                           │         `in_flight` means "cannot
  ├───────────────────────────┤          staff" AND "is running"
  │  Hub binds run → task     │──── L1: the edge is never written ─▶ F49, F63
  │                           │         review runs bind to nothing;
  │                           │         board guesses from `agent`
  ├───────────────────────────┤
  │  runner executes          │──── L3: decisions made outside ────▶ F52
  │  (claude / codex CLI)     │         the Hub, recorded nowhere
  ├───────────────────────────┤
  │  surfaces render          │──── (L1+L2 surface here) ──────────▶ F61
  └───────────────────────────┘
```

L1 is a missing column read. L2 is a vocabulary collision. L3 is outside the process boundary
entirely — no event log helps, because the event is never generated. Rebuilding the state core
would be the largest available change aimed at the smallest of the three.

The principle that came out of it instead is narrower and cheaper:

> **Every surface derives; no surface restates.** A question like *"is this agent mid-turn on this
> task"* gets exactly one implementation, and an API renderer is never where it lives.

That is a discipline plus one refactor, not an architecture.

---

## L1 — every review turn in this product runs unbound

### What was measured

```
runs total                                    202
runs with task_id NULL                        154   (76%)

runs that moved a task at all                  32
  …of those, unbound                            9
     6 × in_progress → completed
     5 × assigned    → in_progress
     2 × under_review → approved        ◀── a run approved work while recording no link to it

inbound_queue_entries
                     task_id set   review_task_id set
  work deliveries         34               0
  review dispatch          0               9         ◀── perfectly disjoint, zero overlap
  everything else          0               0             (150 rows)

review entries delivered into an unbound run:   5 of 7
```

Every review turn this product has ever run was unbound. Not most — all nine.

### Why

`review_task_id` is **not a binding field. It is a checkout instruction.** From `scheduler.py:2611`:

```python
# Design D9, same as the primary path: only a selection the ladder made *as a review*
# gets a checkout of the author's work.
review_task_id=task.id if is_review else None,
```

It exists because of **finding F10** — a reviewer fired into its own worktree cannot see the
author's unmerged work. It carries a task id because that is how you find the commit, not because it
means "this run is about this task."

Meanwhile `run_task_binding.binding_from_entries` reads only `entry.task_id`. Both resolutions live
in the *same function*, roughly seventy lines apart, reading different columns:

```
trigger_agent()  in  hub/hub/api/v1/agent_trigger.py
│
├── line 468   review_task_id = await _review_task_from_entries(...)   ──▶ reads entry.review_task_id
│               "which task's commit do I check out?"                       → sets the WORKSPACE
│
│   … 70 lines …
│
└── line 538   binding    = await resolve_bound_task(...)              ──▶ reads entry.task_id
    line 744   await bind_run_to_task(session, run, bound_task)              → sets run.task_id
                "which task is this run about?"                              (never reached for a review)
```

### This was not a decision

No comment, no design note, and no spec requirement says a review run should be unbound. The
`run-task-binding` spec's own list of legitimate unbound runs — *"exploration, conversation,
questions, and scheduled work"* — does not include reviews, and reviews are none of those things.

The chronology confirms it: `binding_from_entries` arrived in `0b71b47` (*"A run that drops its work
is now caught at the boundary"*); `review_task_id` arrived much later in `ce923ce`, migration
`0086`. The binding predates reviews by many migrations, and the review work added a column for its
own purpose without going back to teach the older one.

**It is an omission of the ordinary kind: two features each needed "the task", and each grew its own
field.**

### What binding a review run costs

Three things are genuinely inert, verified rather than assumed:

| | |
|---|---|
| task status | `allowed_targets('under_review', run)` = `['approved', 'rejected', 'revision_needed']` — no `in_progress`, so `bind_run_to_task` binds and moves nothing |
| assignee | the scheduler already set it when it staffed the review |
| conversation | no unique constraint on `conversations.task_id`; author's and reviewer's threads may both bind |

One thing is **not** inert, and it is the actual content of the change. `run_advanced_its_task`
opens with:

```python
if not run.task_id:
    return True          # "no task to have neglected"
```

Being unbound is how review runs currently escape the run-boundary check entirely. Bind them and
they are checked:

```
review run ends
      │
      ├── verdict recorded?  (all 14 observed verdicts are origin='actor') ──▶ True, no divergence
      │
      └── no verdict ──▶ RunDivergence recorded
```

Plus a knock-on: F38's `note_turn_that_produced_nothing` currently fires for review runs *because*
they are unbound, and would stop, taking the divergence branch instead.

### Two defects found while checking the escalation path

Both would have shipped invisibly, and both are this repository's dominant failure mode — a fix that
passes its tests and cannot fire.

**(a) A divergence response gets no review checkout.** `run_divergence._queue_response` builds its
entry as `new_entry(..., task_id=task_id)` with no `review_task_id`. So a retried or escalated
reviewer is fired into its own worktree, where the work under review does not exist. **That is
finding F10, reproduced by the exact mechanism meant to rescue a failed review.**

**(b) Escalating to the wrong agent is a guaranteed 403.** An agent cannot approve work it completed
(`task_transition_service.py`, `_agent_that_completed`). A task whose `escalation_agent` is its own
author would have its escalated review refused on arrival.

Neither has ever fired, because `escalation_agent` is **NULL on all 40 tasks** and `_decide`
surfaces rather than escalating when nobody is named. The machinery has simply never been pointed at
a review.

---

## L2 — one word, three meanings

`FiringDecision.in_flight` means *"this firing cannot staff anybody onto this."* The scheduler
appends to it unconditionally whenever an `under_review` task has an assignee — deliberately, so a
verdict-less review stays visible on the board (F23, F45). `api/v1/jobs.py` rendered the same
collection as *"this agent is mid-turn on it."*

There are four `in_flight`s in the codebase carrying three distinct meanings:

```
scheduler.FiringDecision.in_flight   "this firing cannot staff anybody onto this"
api/v1/jobs.py rendered it as        "this agent is mid-turn on it"              ← F63
checkpoint_handover._in_flight       "dedup: don't re-enter for this run_id"
checkpoint_trigger._in_flight        "dedup: don't re-enter for this conv_id"
```

The `agent_role` derivation is ~90 lines inside an API renderer, merging three sources, carrying
five findings' worth of archaeology in its comments — F23, F26, F45, F49, F63 — each one a minimal
repair to the previous one's blind spot. It is doing work that is not a renderer's to do.

**A correction to an earlier claim in this thread.** It was asserted that eight modules re-derive
`Run.status == "running"` and should collapse into one. That overstates it: `agent_auth` asks *"is
there a live run to mint credentials for"*, which is a security question with legitimately different
scoping from a board question. **Which of those call sites are genuinely the same question has not
been audited, and that audit is a task in the change rather than a settled input to it.**

### Options considered

| | |
|---|---|
| **A · a derivation module** | One pure function, both callers use it. No schema change, no migration, and it makes the derivation **testable in Python** — F49's literal root cause was a derivation with zero Python tests while its renderer had five vitest cases. Still read-time; a third surface can bypass it. |
| **B · split at the source** | Separate "cannot staff" from anything implying "running". Kills the collision where it is born. Rejected during F63's hotfix as *"cleanest at source, but touches every consumer for a defect living in one renderer"* — a reasonable objection to a hotfix and not to a deliberate change. |
| **C · materialize it** | A column or table written at transitions. Readers stop computing, so they cannot compute wrong — but two sources of truth that can drift. This is the event-sourcing-adjacent option. |
| **D · runs own "working"** | After L1, runs reliably answer *is someone mid-turn on this task*. Stop asking `in_flight` that question; the scheduler keeps `in_flight` for what it means and it is never rendered. |

**C is dropped.** It is the only option that introduces a genuinely new failure mode, and it is the
one the paper nudges toward. Not clean, just fashionable.

### Decision — B in its strong form, fused with A

Splitting a field is a rename, not a new concept: `jobs.py` could still misread `cannot_staff`
tomorrow. The version that earns the claim is stronger:

> **The scheduler stops handing out raw collections for other modules to interpret.** There is one
> owned answer to "what is the state of this task in its loop right now", and consumers cannot reach
> the ingredients that compose it.

That prevents recurrence not by naming things better but by making the misuse unreachable. The
current bug is only possible because `decision.in_flight` is a public, semantically loaded tuple
that any renderer may pick up and interpret however it likes. Five findings did exactly that.

```
                 B (strong form) fused with A
  ┌───────────────────────────────────────────────┐
  │  work state — the only public answer          │
  │                                               │
  │   for a (task, agent):                        │
  │     working  ← runs table   (correct after L1)│
  │     held     ← claimed/under_review, no run,  │
  │                scheduler cannot staff         │
  │     next     ← the firing's selection         │
  │     assigned ← the task's own assignee        │
  └───────────────────────────────────────────────┘
        ▲                              ▲
        │ consumes                     │ consumes
  ┌─────┴──────┐                ┌──────┴───────┐
  │ scheduler  │                │ jobs.py API  │
  │ internals  │                │  (renders    │
  │  private   │                │   only)      │
  └────────────┘                └──────────────┘
```

The insight underneath: *two inputs* is not the problem — **one input being asked a question it does
not answer** is. Each role gets its own source. B without A gives clean interfaces nobody tests; A
without B gives a tested module a future surface can bypass. Neither half alone gets there.

**The one caveat, and it is about method rather than scope.** This repository's dominant failure
mode is fixes that pass their tests and cannot fire; F49 was a five-line derivation bug that lived
in production from the day it shipped. A refactor touching the scheduler's public interface plus
every consumer is a larger surface for that same failure than any point fix was. So: the new
module's tests must be Python and must exercise the derivation rather than the renderer; each role
branch must be mutation-checked by name, as F63 and F64 were; and it must be live-verified against
the trial Hub, which is the only thing in this repository's history that has ever caught one of
these.

---

## L3 — dropped from scope, with the measurement that dropped it

Two parties can refuse an agent's command:

```
  ┌─────────┐   asks    ┌──────────┐   asks   ┌──────────────┐
  │  agent  │──────────▶│  runner  │─────────▶│     Hub      │
  │         │           │ (CLI)    │          │ approve_tool │
  └─────────┘           └──────────┘          │    _call     │
                             │                └──────────────┘
                             │                       │
                    refuses on its own          refuses properly
                    ▼                                ▼
              NOTHING RECORDED                 permission_denied  (45 rows live)
```

The Hub narrates its own decisions well — 34 distinct event types, 45 `permission_denied` rows. F52's
zero rows were not a broken mechanism; they were the Hub being bypassed. Claude's CLI refused before
`approve_tool_call` was ever invoked; Codex refused on its own sandbox check.

**A proposal was made and then killed by measurement.** The idea was to avoid parsing vendor prose
(which breaks when wording changes) and instead count failures, since `is_error` is already recorded
structurally on every `tool_result`. Three results:

```
tool_result rows in the DB:                            1402   (is_error already structured)
per-run failure rate, 59 runs with ≥8 tool calls:      median 0.25, max 0.76

F52's own two runs:   run-2f63d76eeae2  →  0.26        ◀── the median
                      run-9e793f8b5c35  →  0.36        ◀── 8th worst

tool_result rows whose text names an approval refusal:    0
agent_outputs rows containing refusal prose:             17, across 8 distinct runs
```

The rate signal **would not have caught F52** — those runs sit mid-pack, and eight healthier-looking
runs rank worse. More decisively, **zero refusals appear as tool results at all.** They exist only
as prose in `text`/`thinking` rows — the agent *talking about* being blocked — which is consistent
with the CLI refusing before the tool is ever invoked.

**The Hub has no structured trace of these refusals whatsoever. Its only witness is the agent's
narration.** Cause detection is therefore not currently implementable, and that is a measured
conclusion rather than a judgement call.

What survives is the consequence half, and it routes back through L1: a run that ends having claimed
completion while producing no commit and no evidence is exactly what the boundary check is for. F52's
two runs both moved their tasks to `completed` with zero evidence rows and the board called it done.
That is catchable without ever knowing why the CLI refused.

The paper's two-layer `SecurityAnalyzer` / `ConfirmationPolicy` split was considered and rejected for
now: it is a better answer on an endpoint that is not being called. It becomes reachable only if
AgentWeave owns the agent loop, which is a separate strategic question deliberately deferred.

---

## What a verdict-less review means, and what answers it

A review turn's output is a task transition: `under_review → approved | rejected | revision_needed`.
If the run ends and none of those happened, the review produced nothing — and today the Hub cannot
tell, because the run is not bound. Both recent fixes are the Hub *inferring from absence*: F45
withdrew a briefing that was being re-staffed forever; F63 invented the `held` role for a card that
read `working` with no run alive. After L1 the Hub can state the fact instead.

**Decided: it records a `RunDivergence` row.**

### Reviews are not governed by `divergence_policy`

A run's exit status already discriminates two cases, and they are **already handled by different
machinery**:

```
run bound to a task ends
        │
        ├── final_status == "failed"  →  return_run_entries(): its queue entries go BACK to queued
        │        │                        …and the boundary check is SKIPPED
        │        └──▶ a new run picks up the same entry and binds to the same task
        │
        └── final_status == "completed", task didn't move  →  evaluate_run_end()
                 └──▶ RunDivergence recorded, divergence_policy applied
```

Confirmed by the data — `run_divergences` holds 23 rows and **every one has
`run_exit_status = 'completed'`**; none from the 16 `failed` runs. A crashed run already retries, via
re-queueing, and that predates `divergence_policy` entirely.

So `retry` means something much narrower than it first appears: *the run finished normally, the agent
had its full turn, and it moved nothing.* For a work run that is defensible. For a review it is close
to indefensible — the reviewer completed its turn, saw the evidence and the briefing, and declined to
record a verdict; re-running the same reviewer on the same inputs is the least likely intervention to
change the outcome. The observed causes are deterministic rather than flaky (F65's refused briefing,
F52's wall, the F38 family of turns that simply end), and the genuinely transient case is already
covered by the re-queue path.

Taking the three policy values one at a time against reviews:

- **`retry`** — no. Duplicates the re-queue path and fires only where it helps least.
- **`escalate`** — the concept is right, the mechanism is wrong. Using `task.escalation_agent` would
  be a second resolution path, which `agent-flows` forbids in so many words: *"by the same
  resolution the rest of the product already uses for a declared reviewer, **never a second one**."*
- **`surface`** — fine, but that is just "record it and show it", which the `RunDivergence` row
  already does.

**None of the three does useful work for reviews that is not better done elsewhere.**
`divergence_policy` keeps exactly one meaning — what to do when a *work* run drops its task — and
review failures are answered by the reviewer-resolution rule already specified and shipped:

```
review run completes with no verdict
        │
        ├── reviewer was DECLARED (spec-time)
        │      └──▶ SURFACE. Never substitute.
        │           Firing someone else would tell the operator the named reviewer
        │           checked the work when it did not — the requirement's own reasoning.
        │
        └── reviewer was picked by AVAILABILITY
               └──▶ resolve again, excluding the one that just failed.
```

Three things fall out for free: **no entry price** (nobody has to populate `escalation_agent`, which
is NULL on all 40 tasks and would have stayed that way — consistent with the operator's standing
principle that AgentWeave must not demand setup before use); **the 403 in (b) cannot fire**, because
the resolver already excludes ineligible agents; and **spec-time declaration is what gets honoured**,
which is the behaviour the operator asked for.

### When a review legitimately should not move the task

> **A review that could see the work owes a verdict. A review that could not see the work owes the
> operator an explanation.**

| what happened | should it have moved the task? |
|---|---|
| reviewer judged, forgot to record it | **yes** — agent-side defect |
| no evidence, task *can* carry evidence | **yes** → `revision_needed` |
| no evidence, task *cannot* carry evidence | no — the demand is unsatisfiable; surface |
| checkout failed (F10 family) | no — Hub-side; blaming the author misattributes a Hub failure |
| permission wall (F52) | no — runner-side |
| reviewer called `ask_user` | no — **already handled**: the task goes `blocked`, and `evaluate_run_end` explicitly excludes it from divergence |
| run crashed | n/a — entries re-queued, boundary check skipped |

Most "could not see the work" cases prevent the run from starting at all: `prepare_review_turn`
refusing means a 409 and no run, so those never reach the divergence path. The main exception is F52,
where the run starts and hits the wall mid-turn. **A verdict-less review that actually reaches the
run boundary is therefore almost always agent-side** — the reviewer had the work in front of it and
said nothing — which is precisely what a `RunDivergence` should record.

---

## Decisions

1. **One change covering L1 and L2.** Operator's reasoning: *"If they share the same theme they're
   bound to collide. So they need to be tackled and tested together."* They are also mechanically
   entangled — L1 removes the need for L2's ugliest artifact, and L1 creates a new fact L2 must
   render.
2. **Event-sourcing rejected as the framing.** It addresses L2 only.
3. **L2's shape: B strong form fused with A.** C dropped.
4. **A verdict-less review records a `RunDivergence` row.**
5. **Reviews are not governed by `divergence_policy`.** The response is the reviewer-resolution rule.
6. **`retry` is not extended to reviews.** Evidenced, not hedged — see the exit-status split above.
7. **Backfill forward-only.** The 154 unbound runs are test data.
8. **L3 dropped from scope**, cause detection measured as not currently implementable; the
   consequence half is absorbed into L1's boundary machinery.
9. **F61 leaves this change.** See below.
10. **Standing preference recorded:** the cleanest solution wins; "requires more work" is never the
    objection. Stated by the operator: *"I don't like to keep applying fixes because they bite us in
    the ass later down the road."* Noted alongside it: cleanest is not the same as largest, and where
    the small option is the clean one it should be said plainly.

## Deferred, with reasons

**A policy rule table.** The operator's observation is correct — `divergence_policy` is an enum
column pretending to be a rule set, and rules have applicability: some apply to workers, some to
reviewers. A table with declared applicability is the honest model and is where this ends up.

Not built now, and the reason is evidence rather than effort: there is currently **one** consumer
distinction, and we have just decided reviewers use none of the rules. Building a rule table to
express *"these apply to workers, and reviewers use none of them"* models a distinction with one
populated side. `escalation_agent` is the cautionary tale sitting right there — a column added for a
policy nobody set, NULL on all 40 tasks, superseded before it ever fired.

The spec must therefore say reviews are **not governed by** `divergence_policy`, not that reviews
*have* a policy value, so the table can arrive later without unpicking anything.

**F65's fix changes, and it is not part of this change.** A reviewer that finds nothing to check has
learned something real: `revision_needed` says *you completed this and gave me nothing to check*, and
it is a legal edge. But it is only right where evidence is possible:

```
tasks:                          40
with a requirement link:        21     ← evidence is possible
without:                        19     ← evidence is STRUCTURALLY impossible
```

`record_evidence` takes `identifier: "FR-1"` and evidence rows are keyed by `requirement_id`; a plain
loop task carries no `FR-` id, which F52 hit directly. So the rule needs its qualifier — *no evidence
→ `revision_needed` where the task can carry evidence, surface where it cannot* — or it ships an
infinite bounce. F65's refusal also happens at **trigger** time, before any run exists, so it is a
different code path from the divergence work entirely.

**A database reachability audit.** Found incidentally in one afternoon: `conversation_title_mode`
(works, defaulted off, no UI control exists); `escalation_agent` (NULL on all 40, superseded);
`run.task_id` (NULL on 76% of runs, and on every review turn); `inbound_queue_entries.task_id` vs
`review_task_id` (two columns, one question, disjoint); `EventLog` (a table with two write sites in
the whole codebase). Suggested scope for a deliberate pass over all 45 tables: for every column, who
writes it, who reads it, and is it reachable from the UI — the answer *"nobody"* being the finding.

**F61 and configuration visibility.** F61 is not a state-truthfulness defect. AI-generated
conversation titles already exist (`conversation_title_mode: 'truncate' | 'generate'`, migration
`0037`), the module is complete and careful, and the setting is `truncate` with a NULL runner on all
five projects. `grep -rn "conversation_title_mode" hub/ui/src/` returns the type definition and a
test: **no control renders it.** So F61's eleven identical titles are a shipped feature that cannot
be switched on from the UI, not a titling-scheme defect — and the recorded fix ("title a flow
conversation by its agent and role") would build a second mechanism beside a working one.

Two constraints for whoever writes that change. **"Role" is unusable as a new name** — it already
means three things: `agent_role` on the board (a staffing state), a charter (a behaviour contract),
and work-versus-review (a turn kind). Adding a fourth would repeat the exact mistake this change
exists to end. And **nothing may require a charter to exist**: 6 of 17 agents have none, by design,
so that AgentWeave does not demand setup before use.

`OverviewPage.tsx` today has Attention, Navigate, Tasks and Activity, and **no configuration summary
at all** — which is how a working feature sat dark for 49 migrations. The operator's framing is that
the overview should state what is set and settings is where it changes.

## What the change should contain

1. Bind review runs — `binding_from_entries` learns `review_task_id`.
2. Spec what a verdict-less review means: a `RunDivergence` row, answered by the reviewer-resolution
   rule rather than by `divergence_policy`.
3. Divergence response entries carry the review checkout **(defect (a) above)**.
4. An escalation target must be able to legally review **(defect (b) above)**.
5. Reconcile re-delivery-on-crash with F45's withdrawal-on-silence — both act on the same entry, and
   the design must state which applies when, or F45 returns.
6. Audit which `Run.status == "running"` call sites are genuinely the same question. Not all are.
7. Rebuild the `agent_role` derivation as an owned module with private scheduler internals, with
   Python tests over the derivation and mutation checks per role branch.
8. Drop the agent-fallback in `jobs.py` that L1 makes unnecessary.

## Sources

- `scripts/drive/FINDINGS.md` — F49, F52, F61, F63, F64, F65
- `openspec/specs/agent-flows/spec.md` — *A flow resolves a reviewer by declaration, then by
  availability*, the requirement that settles the escalation question
- `openspec/specs/run-task-binding/spec.md` — the list of legitimate unbound runs
- `hub/hub/run_task_binding.py`, `hub/hub/run_divergence.py`, `hub/hub/api/v1/agent_trigger.py`,
  `hub/hub/api/v1/jobs.py`, `hub/hub/scheduler.py`
- arXiv 2511.03690, *The OpenHands Software Agent SDK* — read as a source of ideas, not a design to
  adopt. Its event-sourced `ConversationState`, its condenser, and its two-layer security split were
  each considered explicitly and each declined here for stated reasons.
