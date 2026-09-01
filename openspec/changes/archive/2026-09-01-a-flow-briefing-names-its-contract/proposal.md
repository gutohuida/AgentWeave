## Why

A flow's briefing is the one text an agent inside a flow reliably reads, and it is the product's
own chosen channel for saying what an agent could not otherwise know — design D8 put the tier
statement there on exactly that argument: *"an agent that does not know to ask never asks."*

It tells the agent to **finish the task and stop**. It never says what finishing *is*.

**F140 (severity A).** Driven on 2026-08-30 against `proj-1964cdedffe2`: a flow with two
independent tasks, two Haiku agents, both of which did the work, committed it in their own task
checkouts, recorded evidence and submitted checkpoint notes. **Neither task ever left
`in_progress`.** The next firing re-claimed the same two tasks, re-briefed the same two agents, and
burned two more provider turns producing a board byte-identical to the one before it. The second
transcript is the proof it is waste rather than progress:

> *"Ah, evidence has already been recorded for FR-1 on this task. … The prior agent likely already
> recorded evidence for FR-1."*

The briefing names `submit_checkpoint_notes` explicitly, and **both agents called it.** It never
names `update_task`, and **neither agent called it.** That is not a model failure. It is the
product declining to state its own contract at the place the agent reads.

The cost is not one wasted turn. It is the entire second half of the feature. Review is gated on
`REVIEWABLE_LOOP_TASK_STATUSES`, which is `{completed}` and nothing else (`scheduler.py:530-536`),
so a task that never reaches `completed` is never offered to a reviewer, `resolve_reviewer` never
runs, and `stop_when_queue_empties` — whose band is `{approved, rejected}` — can never fire. **A
flow left on its cron re-briefs its agents for finished work on every firing, forever, and reports
itself busy the whole time.**

### The second defect, on the same six characters

**F143 (severity B).** Both call sites compute `is_review`, thread it into the checkpoint selection
on one line, and drop it on the next:

```python
prior_checkpoint = await _briefing_checkpoint(session, loop, task, is_review=is_review)
briefing = await _compose_loop_briefing(session, loop, task, prior_checkpoint)
```

`_compose_loop_briefing` has no `is_review` parameter, so **a reviewer receives the implementation
briefing verbatim** — *"Finish the task below and stop"*, followed by the task's implementation
description and acceptance criteria. Meanwhile the turn-context channel (`api/v1/agents.py:1127`)
says the opposite: *"This is a review turn. You are reviewing someone else's work, not doing your
own."* The agent got both, and its own transcript is the finding:

> *"But this is marked as 'This is a review turn.' … **This is confusing.** … The briefing
> describing the task is just context for what was supposed to be built, not instructions for me to
> follow."*

It resolved it correctly, on Haiku, after spending a visible stretch of the turn on it. Nothing in
the product decided that. The other resolution is a reviewer that re-implements the work it was
meant to check and then approves its own edit — which `review_turn.py`'s own opening paragraph
names as the failure the whole review boundary exists to prevent.

### And the notes nobody reads — found in round 3

Neither of the two rounds above asked what *else* depends on the transition that never happens. It is
more than the review dispatch.

`consider_handover` declines at its second gate (`checkpoint_handover.py:203-206`) when
`_task_this_run_completed` finds no `completed` transition attributed to the run. In F140's drive
**both agents called `submit_checkpoint_notes` and neither task reached `completed`** — so no
handover checkpoint was ever generated, and the notes both agents wrote are unconsumed to this day.

`agent-flows:379` — *"A flow generates the author's handover briefing"* — and `agent-flows:412` —
*"A reviewer is briefed by the author of the work it is reviewing"* — are therefore both shipped,
both tested, and **both unreachable in a real flow.**

The sharpest form of it: the briefing's own existing sentence, *"Record what a reviewer will need
(see `submit_checkpoint_notes`); somebody else reads it"*, **is false today.** Nobody reads it. The
briefing asks for a record and never asks for the thing that delivers it.

### Both are one defect

The briefing is written as **description**, and the two channels that build agent-facing text —
`scheduler.py` for the briefing and `api/v1/agents.py` for the turn context — never see each other.
One says *do the work*; the other says *do not do the work*. One states the completion contract for
a review turn (`agents.py:1154`, the F45 fix); neither states it for an implementation turn, which
is the only turn that has to travel `in_progress → completed` for the flow to move at all.

This change makes the briefing say what finishing is, and makes it stop telling a reviewer to build
the thing it is reviewing.

### The corpus is silent here, so this adds a requirement

`agent-flows:314` requires the briefing to state the tier and *"that an agent in a flow completes
its task and stops"* — satisfied literally today by the words "finish and stop". Nothing requires it
to say what completing means. More broadly: **no requirement anywhere defines what causes
`in_progress → completed`.** `task-lifecycle-governance:1389` says who *may*; `:1010` says it is not
gated on evidence; `:21` says the edge is legal. F140 is the absence of a requirement as much as a
defect in one, so this change **adds** two requirements rather than enforcing existing ones.

`agent-flows:363` — *"A review turn is told how to record its verdict"* — is satisfied today by the
turn context, and is **not** breached by F143. What F143 shows is that nothing forbids the other
channel from saying the opposite at the same moment. That is what the second new requirement fixes.

## What Changes

**One function, one parameter, two branches, and one query.**

1. **`_compose_loop_briefing` takes `is_review`.** Both call sites already have it in hand
   (`scheduler.py:2356-2366` and `:2713`); they pass it one line further.

2. **An implementation firing's briefing names the completion contract.** After the tier statement:
   the task's current status, the call that finishes it —
   `update_task("<task id>", status="completed")` — what that causes, and what a turn that ends
   without it costs. Stated for **every** firing that claims a task, flow or loop: the task
   lifecycle is the same in both, and a document-less loop's queue drains on the same band.

3. **Where the task serves requirements, the briefing names them and names `record_evidence`.**
   The identifiers come from `requirement_links.for_task`, so only requirements that actually exist
   are named — which is what keeps the instruction from producing the `404` a guessed identifier
   gets (`agent_actions.py:1041`). Silent when there are none, so a loop task is never told to
   record evidence it cannot record.

4. **A review firing gets a review briefing.** It keeps the flow paragraph and the "stop" statement
   — both still true — and replaces the implementation instruction. The task's own text is
   re-framed as *the standard the work is checked against* rather than as an instruction, under a
   heading that says so, and both verdicts are named with the transitions that are legal from
   `under_review`.

5. **The three-way harness assertion in `scripts/drive/t_row12_review_leg.py` is inverted.** It
   currently asserts F143's state — implementation wording present, review wording absent — so that
   the day this is fixed the checks swap and say so. This change is that day.

### Round 2 corrections — what a fresh read of the code changed

Round 2 re-derived the proposal against the code rather than against round 1's reasoning. Two of
round 1's claims were **wrong**, and three constraints it did not know about were found. Full record
in `design.md` D7-D12; the short form:

| # | Correction |
|---|---|
| **D7** | Round 1 named two arrival states. There are **three** — `revision_needed` is claimable, and `completed` is not reachable from it in one step. A briefing written to round 1's rule would have described a refused call, which is the defect this change removes. |
| **D8** | The briefing is **not** the whole delivered text: `job.message` follows it on both paths, and in F143's own transcript that message read *"Work the task you have been given"* — to a reviewer. The review branch pre-empts it in one sentence; the operator's text stays untouched. |
| **D9** | The harness check demanding the briefing *"names the commit under review"* is **wrong** and is corrected rather than satisfied. The commit is resolved one step later, at spawn, and `ReviewContext.work_moved` already handles the case where the two disagree. |
| **D11** | `test_flow_width.py:600-604` asserts `"review"` and `"flow"` are absent from a *whole* document-less loop briefing. Every word the loop branch gains has to clear both. Not weakened — it is `agent-flows:314`'s second scenario in executable form. |
| **D12** | Round 1's evidence wording becomes **false** when change C ships. Reworded so it is true under both regimes. |

### Round 3 corrections — an independent re-derivation of the argument

Round 3 re-asked whether the briefing is the right place at all. It is, and the derivation is now
stronger than round 1's: the product already decided this question in writing, about `ask_user`
(design D13). Three further changes:

| # | Correction |
|---|---|
| **D14** | F140 does not only block review dispatch — it silently disables the **whole handover feature**, leaving `agent-flows:379` and `:412` unreachable in a real flow. The requirement gains a clause: a briefing that asks for a record for a later reader must name what delivers it. |
| **D15** | "Let the Hub conclude it" is not merely undesirable — its obvious implementation is **foreclosed by `task-lifecycle-governance:359`**, which forbids a third actor kind. Round 1 rejected it on other grounds; this is an independent second reason, recorded so it is not re-proposed as cheap. |
| **D16** | Round 2's **own** new requirement over-reached. Telling a reviewer that the loop's message "does not describe this turn" is wrong exactly where its author thought hardest — a standing message may be written to address a review. Narrowed to identifying it as the standing message, with instructing the agent to disregard it now forbidden. |

Also re-derived and rejected on their merits, so they are not proposed again: a `finish_turn` tool
(a second writer of a fact `apply_transition` owns, and it does not solve the problem — an agent
never told to call `update_task` would not be told to call `finish_turn` either), and splitting the
review branch into a second function (three shared sections duplicated to avoid one conditional).

Verified and holding: the claim precedes the briefing on the same ORM row, so the status the briefing
reads is the post-claim one; `requirement_links` creates no import cycle, so round 1's fallback query
is dropped; the briefing reaches the agent untruncated; and the tool inventory's exclusion of
`submit_checkpoint_notes` is a **precedent** for naming a tool where it applies, not an obstacle.

**Deliberately not in this change**, each with its reason:

- **The Hub concluding `completed` from a clean turn end.** F140's second repair. It asserts the
  work is finished on the strength of the process exiting, which is precisely the inference the
  operator retired the question-detection backstop for making (`CLAUDE.md`, 2026-08-20) — and a
  turn can end because the agent gave up.
- **Escalating a repeated divergence — and round 3 says plainly that this leaves the change half
  finished.** `run_divergence.py:743-752` already detects that a run did not advance its task, routes
  `POLICY_RETRY → POLICY_FLOW`, and grades it `severity = "info"` — indistinguishable from healthy
  multi-turn work (`:793-800`). The product's own rule for this class of thing, written about the
  retired question backstop, has two halves: *"An agent that needs an answer calls `ask_user`; a turn
  that ends without calling it has ended."* **This change is the first half.** The second — a turn
  that ends without the call being visible rather than silently re-briefed — is
  `loop-firing-accountability`'s subject, in another module, and folding it in would make one change
  out of two. It is named here so the operator reads this as half a statement rather than a whole
  one.
- **Anything about integration or evidence acceptance.** Changes B, C and D.

## Impact

- **Specs:** `agent-flows` — two ADDED requirements. No MODIFIED requirements: `:314` and `:363` are
  both still satisfied, and this change is additive to each.
- **Code:** `hub/hub/scheduler.py` (`_compose_loop_briefing` and its two call sites).
- **Harness:** `scripts/drive/t_row12_review_leg.py`.
- **Tests:** `hub/tests/test_loop_briefing.py` (or wherever the briefing's existing assertions live
  — task 1.1 finds out rather than assuming).
- **No migration, no schema change, no UI change, no API surface change.** The briefing is composed
  per firing and read once; there is nothing stored to migrate.
- **Cost of being wrong:** agent-facing prose, changed in one function, reversible in one commit.
  The risk that matters is the opposite one — this text is the flow's only instruction channel, so
  wording that is *almost* right produces a defect that only a drive finds. `DRIVE-1` is where it
  gets found.
