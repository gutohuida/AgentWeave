# What is still unanswered, and what the database says about it

**Date:** 2026-08-26 · **Written because:** the operator asked what still needs answering, after
`every-run-knows-its-task` was proposed and handoff 0091's queue was cleared down.
**Status:** exploration. No code written. Every figure below is measured against
`~/.agentweave/hub/profiles/beta/agentweave.db`, read-only, 2026-08-26.

## The headline: the carried list was partly stale, and one item on it was never a defect

Handoff 0090 carried a standing warning — *"F50, F53(b), F58, F60, F61, F65 carry 'the operator's
chosen fix' but were rubber-stamped while burned out. Re-check before building."* That warning was
right to exist and re-checking it was worth doing, because **the list is not six open items.** It is
one closed, two half-closed, and three genuinely open, and the difference matters before anyone
spends a session on it.

| | State, verified in code and rows |
|---|---|
| **F50** | **Closed.** The chosen fix (render the failure) is implemented, mutation-checked, and live-verified against the original failed checkpoint. Nothing to re-decide. |
| **F53(b)** | **Half.** Option (a) shipped with migration `0090` and a partial unique index. Option (b) — task `loop_id` orphaning — is untouched and still needs a decision. |
| **F58** | **Open.** Blast radius made visible (`rode_along_commits`, migration `0089`); the merge semantics itself is unchosen between three candidates. |
| **F60** | **Open.** Nothing implemented. The guard is easy; the board-surfacing half is a design decision. |
| **F61** | **Open.** The chosen fix is **not implemented.** `name_conversation` still titles from the job name alone. |
| **F65** | **Half, and not as chosen.** A generic three-attempt withdrawal exists (F56's fix, `DELIVERY_ATTEMPT_LIMIT = 3`); the chosen fix was *terminal on the first refusal*. |

## A new finding: two spellings of one severity, and the louder one is the invisible one

Found while measuring the severity distribution for `every-run-knows-its-task`'s D6, which is how it
surfaced at all — nothing was looking for it.

```
severity   count
info       2996
warn        108
warning       3     <-- turn_produced_nothing, all three
```

`hub/hub/run_divergence.py:613` emits `severity="warning"`. Every other call site in the codebase
emits `"warn"`. `persist_event` (`hub/hub/utils.py:25`) does not normalise — severity is a free-form
string written verbatim.

Three consumers key on `"warn"` and none of them knows `"warning"`:

- `EventRow.tsx:44` `SEVERITY_BORDER` — no match, so `borderClr` is `undefined` and the row renders
  with **no amber border**.
- `EventRow.tsx:37` `SEVERITY_CHIP` — no match, so `chip` is `undefined` and the row renders with
  **no severity chip**.
- `ActivityLog.tsx:31` `SEVERITY_FILTERS = ['all','error','warn','info','debug']` — `"warning"` is in
  none of them, and `:165` filters on strict equality. The event is reachable **only** with the
  filter on `all`. Selecting `warn` hides it; selecting `info` hides it too.

The API has the same hole: `GET /events?severity=warn` filters on `EventLog.severity == severity`
(`hub/hub/api/v1/events.py:42`), so an operator or script asking for warnings never receives one.

So `turn_produced_nothing` — an agent's turn that ended having written nothing and asked nothing,
which is precisely an event that wants attention — is the one event in the product that renders as
though it were routine and vanishes under the filter meant to find it. Three rows exist today.

This is the house failure mode exactly: it passes anything that asserts "the event was persisted with
a severity", and it cannot fire in the UI. **Recommended: normalise in `persist_event` rather than
only fixing the one call site**, so a fourth spelling cannot be introduced the same way — and give
the normalisation a test that enumerates the accepted set. Fixing only line 613 leaves the class open.

## The roster-of-three question, answered by measurement

Carried unanswered since handoff 0089: *should a roster of three be unable to staff one review?*

Rung 2 of the ladder (`scheduler._agents_that_are_free`) defines free as **not running** *and*
**holding no active task**, where active is `LIVE_STATUSES`:

```
assigned · in_progress · pending · revision_needed · under_review
```

Two consequences follow, and neither is written down anywhere as a decision:

**1. A reviewer is consumed entirely by the review.** Staffing a review makes the reviewer the task's
assignee and the task's status `under_review` — which is a LIVE status. So an agent reviewing one
task cannot be picked to review a second, and cannot be picked for work either. This is the same
mechanism that made mutation check 2.14 fail 2.6 instead of 2.5 last session; it was observed there
as a surprise and never generalised.

**2. Merely being the assignee of a `pending` task disqualifies an agent.** `pending` is in
LIVE_STATUSES. An agent named on a task that has not started, and may not start for hours, is not
free to review anything.

Measured across every project on the trial Hub:

| project | roster | holding a LIVE task | free for rung 2 |
|---|---|---|---|
| `ledger-stress` | 3 | 3 | **0** |
| `toolkit-sandbox` | 3 | 2 | 1 |
| `snakeGame` | 3 | 0 | 3 |
| `AgentWeave` | 4 | 0 | 4 |
| `drive-2026-08-26` | 4 | 0 | 4 |

`ledger-stress` is the only project that has ever run sustained flow work, and it has **zero** agents
rung 2 can pick. Its steady state is unstaffable. `review_unstaffed` has fired **10 times**, every one
carrying the identical reason — *"no agent is free to take it. Every agent on the roster is either
running a turn, already holding active work, or is the one that completed this task."*

The three projects showing plenty of free agents are the ones that have done no flow work. **Review
capacity collapses exactly as throughput rises**, which is the opposite of what you want, and the
busiest project is the one where it collapses completely.

The counter-argument is real and is in D4's own text: not-running alone was rejected because *"an
agent can hold three assigned tasks and be idle between turns, which is the pile-up the operator named
as the thing to avoid."* That reasoning is about **being given work**. A review is a bounded turn
against somebody else's commit, not an accumulation of ownership — treating the two identically is the
thing to question, not the pile-up rule itself.

Three shapes worth considering, none of them free:

1. **A review does not count as holding.** Exclude `under_review` from what makes an agent unfree
   *for the purpose of taking a review*. Cheapest, and directly addresses consequence 1 — but an
   agent could then hold several concurrent reviews.
2. **A separate review capacity.** Rung 2 asks "is this agent free *to review*", a different question
   from "is this agent free to be given work", with its own rule. Cleanest conceptually, most work.
3. **Leave it, and let the operator add agents.** Defensible: the flow surfaces truthfully and the
   remedy it names is correct. It just means a three-agent roster cannot sustain review.

## `dev`'s 37 firings were not a stall, and the exploration was wrong about them

The other-half-of-the-binding exploration listed as its question 4: *"`dev`'s 36 firings on an empty
queue in `toolkit-sandbox` — a loop fired 36 times with nothing to claim. `_loop_stall_reason` is
supposed to be what an operator sees for that. Worth checking whether they saw it."*

Checked. **There was no stall and nothing to see.** The measurement conflated two different jobs.

```
proj-2826f39e event counts
  run_triggered 37 · run_started 37 · run_completed 37 · job_fired 36
  queue_entry_queued 37 · queue_entry_delivered 37
tasks with loop_id set: 0
```

Thirty-seven runs **started, were delivered input, and completed.** The 36–37 `dev` runs belong to
`Hourly test check` — a plain scheduled job whose message is *"Run `python -m pytest -q` and report
the summary line. Do not change any files."* It is not a loop, it claims no task, and it moves no
task, correctly. `toolkit-sandbox` has thirteen tasks and **none carries a `loop_id`**, so no firing
in that project could ever claim or bind anything.

This does not weaken the binding change — it strengthens its central number. Those 36 runs are the
clearest possible demonstration that the unscoped "45 of 55 job-origin work runs moved nothing" is the
wrong denominator: 36 of them are a pytest reporter doing exactly what it was asked, and would never
bind under the new rule either. The scoped 9-of-19 stands, and question 4 can be struck rather than
carried.

## F47, measured for the first time: over half of what the record blames on the operator was the flow

F47 has been parked since 2026-08-25 as a truthfulness defect with no enforcement hole, and its
write-up says only *"an operator asking 'what did I do to this task' is told they did something they
did not."* Nobody had measured how much.

```
actor_kind='operator' transitions        55
  pending -> assigned                    17   <- the flow claiming work
  completed -> under_review              12   <- the flow staffing a review (F45's addition)
  everything else                        26
```

**29 of 55 — 53% — of every transition the database attributes to a person was made by the flow.**
`origin` does not rescue it: that column splits `actor` (97) from `runtime` (10, the `bind_run_to_task`
auto-transitions), and every one of the 55 is `actor`.

`every-run-knows-its-task` makes this worse in a specific way worth stating now rather than
discovering later: binding work runs adds a **runtime** `assigned → in_progress` per flow work turn,
which is correctly attributed. So the runtime slice grows and the honest fraction improves — but the
17 and the 12 keep accruing and stay wrong, and they are the two that carry meaning for an operator
reading a task's history.

Still not a hole in enforcement — `_guard_author_is_not_reviewer` binds `_REVIEW_OUTCOMES`, and neither
`assigned` nor `under_review` is one. The pin in `test_flow_chain_end_to_end.py` still names both rows.

## What still needs a decision, ranked by what it blocks

**1. F58 — the merge semantics.** The highest-severity open item, flagged as such since Q6. Approving
one task's evidence merges the agent's entire branch history. Blast radius is now *visible*
(`rode_along_commits`), which makes it survivable, not fixed. Three candidates, none evaluated:
(a) `cherry-pick <last-integrated>..<target>`, (b) a squashed single-commit diff against merge-base,
(c) per-task worktrees. This one is a change of its own and wants its own exploration before a
proposal.

**2. The roster-of-three ladder.** Blocks nothing today because the flow surfaces truthfully, but it
means the product's main loop cannot review on a three-agent roster, which is the roster most people
will have.

**3. F53(b) — task `loop_id` orphaning.** A dead loop's tasks keep a `loop_id` pointing at it. The
decision the write-up names: tasks the dead loop's agent had already started or completed should
almost certainly *keep* `loop_id` as history rather than be silently reset — which means the fix is
not symmetric and someone has to say where the line is.

**4. F60 — a task that shipped on an unanswered question.** The guard half is small (`questions.py`'s
PATCH handler refusing an answer whose asking run has ended). The durable-surfacing half is the
decision: a task-level flag, a distinct completion state, or visible only in the questions list
forever.

**5. F61 — flow conversation titles.** The chosen fix was never written. The condition has worsened
with exactly the usage the feature is for: `Ledger flow` is now **13** conversations sharing one title
(11 when the finding was written), and `Hourly test check` is **36**. Also worth reconfirming, per
handoff 0089's own question 2, that exposing `review_task_id` on `QueueEntryResponse` is still
deliberately *out* of scope — it remains on no schema.

**6. F65 — the no-evidence briefing.** Bounded rather than fixed. The generic three-attempt path
withdraws it eventually; the chosen fix was terminal on the first refusal. Until then the entry is
re-delivered and re-refused up to three times and blocks archiving its agent throughout.

**7. F47 — the flow's routing recorded as the operator's.** Now measured at 53%. Still deferred for the
stated reason: a third actor kind touches `Actor` validation, `is_operator`, every `actor_kind`
consumer and the history surfaces. Worth its own change, not a bolt-on.

**8. The trivial one.** Handoff 0091 asked whether fixing `TaskIntegrationNote.tsx`'s raw hex
(`var(--amber, #b45309)`, which was failing `hubVisualLanguage.test.ts` and blocking task 7.3) was
acceptable, given it was outside that change's scope. It is done and trivially revertable; it needs a
yes or a revert, not a design.

## One question the new change carries

`every-run-knows-its-task` design open question 1: a work entry deferred by D3's batch narrowing keeps
its queue position. A flow that reviews often could in principle keep pushing it back. The assumption
is that it cannot starve because the review and the work are usually for different agents and the
deferred entry is first in line on the next turn — but that is an assumption, and the task list pins
it with a test (1.3) rather than proving it.

---

# Decisions, 2026-08-26

The operator answered all eight. Two answers changed the shape of the item they answered, and both
changes came from the operator's own knowledge rather than from the measurements above.

## 1. F58 — **(c), per-task worktrees.** Not merely the cleanest; the only correct one

Asked directly whether (c) is right and whether the objection is rework. **The objection was not
rework**, and the standing preference settles that anyway. The objection was specific: a task that
legitimately builds on another task's not-yet-landed work would find a worktree forked from the main
branch missing it.

**That objection is dissolved by the product's own rule, checked rather than assumed.**
`task-dependencies` requires *"A dependency is met at approval, not at completion"*, and
`task_transition_service.py:375` runs `integrate_task` on exactly `to_status == "approved"`. So a
prerequisite is merged to the main branch **before** its dependent may start. A per-task worktree
forked from the main branch therefore contains every dependency it is entitled to see, by
construction.

With that gone, (a) and (b) are not weaker options — they are wrong ones:

- **(a) `cherry-pick <last-integrated>..<target>`** cannot separate two tasks whose commits
  interleave on one branch. F58's own text concedes this.
- **(b) a squashed single-commit diff** breaks a task whose work spans several commits: the evidence
  names the tip, so only the tip's diff lands, shipping partial work that has never been run. Read
  the other way — the *tree* at the target — it re-includes the other task's files and fixes nothing.

Only (c) makes the branch correspond to the task, so that "merge what the evidence names" and "merge
this task's work" finally denote the same thing, multi-commit tasks included.

**What is genuinely left is engineering, not unknowns:** the worktree lifecycle and disk cost of one
checkout per task rather than per agent (precedent exists — *"A review checkout is bounded and
reused"*); what happens to an agent mid-task on a per-agent worktree when this lands; and the fact
that two task branches forked before either landed will meet as an ordinary merge, possibly with a
conflict. That last one is a feature: it surfaces a real collision the current design hides by
sweeping both into one branch.

**Next step:** its own exploration before a proposal. It is the only item on this list that can
damage a repository.

## 2. The reviewer ladder — **option 2, a separate review capacity**

Rung 2 asks one question, *"is this agent free"*, and uses it to answer two different ones. It will
ask *"is this agent free to be given work"* and *"is this agent free to review"* separately, with
their own rules. D4's pile-up argument is about the first; a review is a bounded turn against
somebody else's commit, not an accumulation of ownership.

Not chosen: excluding `under_review` from what makes an agent unfree (option 1). It fixes the
measured case but leaves one question still doing two jobs — the defect
`one-answer-to-what-is-happening` exists to end.

## 3. F53(b) — **keep the history; gate on liveness instead**

The operator's answer: *"the important here is to keep the history to retrace it later."*

So `loop_id` is **never nulled**, on any task, in any state. The column is history and it stays. What
changes is the *gate*: `_adopt_document_tasks` is restricted to `loop_id IS NULL`, and that
restriction becomes "owned by a **live** loop" — exactly the `archived_at.is_(None)` shape already
shipped for `_check_spec_document_conflict` in option (a).

This is better than the line the exploration proposed drawing (release `pending`, keep the rest).
That would have destroyed history on precisely the tasks whose history is cheapest to lose and
hardest to notice missing, and it needed a judgement call about where the line sits. Gating on
liveness needs none: every task keeps its full provenance, and a dead loop stops blocking anything.
One rule, symmetric with the half already shipped.

## 4. F60 — **ship the guard, park the surfacing**

`questions.py`'s PATCH handler refuses an answer whose asking run has ended, so the record can no
longer claim the operator chose something the shipped code contradicts. The durable board-surfacing
half — *"this completed task shipped on an unanswered question"* — waits for F14's own fix rather
than being bolted on separately.

## 5. F61 — **the chosen fix is withdrawn.** It was built on a concept the product does not own

The operator's objection, and it is correct: *"the problem of using role is that agentweave doesn't
enforce a role. This is a recurring problem. Role means different things in different places."*

Verified. **`role` survives in this codebase only in two prose comments** (`runner_commands.py:136`,
`worktrees.py:360`) — no field, no enum, no API, no UI. CLAUDE.md is explicit that *"the former CLI
multi-role subsystem, fixed enum, role files, and role-derived API/UI fields no longer exist and must
not be recreated"*, and last session's `agent_role` → `agent_capacity` rename was this same problem
being paid off again. Titling a conversation *"by agent and role"* would have reintroduced the exact
vocabulary the product spent effort removing, one week after removing it. This is what handoff 0090's
"re-check before building" warning was for, and it earned its keep here.

**And there is a better fix already built.** The operator noted an AI naming option exists but is
unreachable. Confirmed, in full:

- `conversation_titles.generate_conversation_title` is complete and wired — called at run completion
  from `agent_trigger.py:1670` and `:2193`, gated on `project.conversation_title_mode == "generate"`,
  bounded by a concurrency gate, and it overwrites a non-operator title (`:213` bails only on
  `title_set_by_operator`). So it **would** replace `Ledger flow` on a flow conversation.
- The field exists on the model (`db/models.py:96`), on the API schema (`api/v1/projects.py:87`), and
  in the TypeScript type (`ui/src/api/projects.ts:88`).
- `ProjectSettingsPanel.tsx` renders **no control for it** — zero occurrences.
- `ui/src/__tests__/projectSettingsPanel.test.tsx` fixtures it as `'generate'`, so the suite
  exercises a value no operator can set.

A finished feature, reachable only by writing to the database by hand, with a green test over the
setting nobody can reach. The same shape as F68 and for the same reason: everything asserted that the
value round-trips, nothing asserted that a human could produce it.

**Revised fix: make the existing feature reachable** — expose `conversation_title_mode` in project
settings — rather than invent a title template on an unowned concept. If a derived fallback is still
wanted for projects that leave titling off, build it from facts the product *does* own: the agent
name, and whether the entry carries `review_task_id`. Never from "role".

Handoff 0089's sub-question is answered by the same reasoning: `review_task_id` stays off
`QueueEntryResponse`. Nothing needs it once titles are real.

## 6. F65 — **terminal on the first refusal**, as chosen. The three-attempt bound is survivable, not right.

## 7. F47 — **its own change.** A third actor kind, not a bolt-on.

## 8. `TaskIntegrationNote.tsx` — **keep the fix.**

## Not asked, still standing

**F68** (`severity="warning"` vs `"warn"`) has no competing options. Normalise in `persist_event`
against an enumerated set so the class closes rather than the instance, and land it before
`every-run-knows-its-task` begins deriving severities.

## A pattern worth naming, since it is now three findings deep

F61's real defect, F68, and `conversation_title_mode` are the same failure: **a value the code
handles correctly and no human can produce or see.** The AI titler works and cannot be switched on.
`turn_produced_nothing` is emitted and cannot be seen. Both have green tests, because the tests
assert the value round-trips through the layer under test and never that it reaches a person.

The cheap counter-check, worth adding to the drive method: for any setting, ask *which control sets
it*; for any event, ask *which filter shows it*. Both questions are answerable by grep in under a
minute, and both would have caught these before a live drive did.
