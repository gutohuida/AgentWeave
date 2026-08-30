# Autonomous run — the flow lands its work

**Branch:** `autonomous/2026-08-31-the-flow-lands-its-work`, cut from `master` at `3a274a2`
**Stop:** 2026-08-31T08:00:00+01:00 · **Runner:** claude (Opus 5) · **Posture:**
`unattended-full-access`

Newest entry at the **bottom**.

---

## Iteration 0 — 2026-08-30 22:45–23:05 (+01:00) — preparation, operator awake

### The operator's instruction, verbatim

> do an autonomos run untill 8AM. Drive everything untill you solve all the issues with the flow
> and things are wortking. Fix what you already know it's broken then test the flow fix again and
> go on untill done

Preceded, in the same session, by: *"Okay let's run a explore on who to fix once and for all the
flow. Let's explore the code base what we know that is wrong... potential fixes once and for all.
I want to get this done on the flow."*

So the target is not a list of findings closed. It is **a flow that lands its work, proven by
driving it.**

### What was done while the operator was awake

**A deep exploration of the flow machinery**, four parallel readers plus direct verification, now
committed as `openspec/explorations/2026-08-30-why-a-flow-cannot-land-its-work.md` (`3a274a2`).
This is the single most valuable thing in this run's inputs: it names seven breaks with
`file:line`, establishes which shipped requirements they breach, and records the traps. **Read it
first, every iteration.** Nothing in it needs re-deriving.

Its headline: *the flow's definition of "done" is the task lifecycle's definition of "decided", and
those are not the same thing.* `hub/hub/scheduler.py` contains **zero** references to integration,
so the module that decides a flow is finished has never heard of the module that decides whether
work landed.

**Two operator decisions were taken** rather than left for the run to guess:

- **D-A — approval is REFUSED while evidence sits unaccepted.** Chosen over seeding a granted agent
  per project, over a flow granting its own resolved reviewer, and over leaving the machinery alone
  while surfacing "approved but unmerged" (that last was rejected because it leaves
  `task-lifecycle-governance:638` breached). The consequence is deliberate: a default project's
  first flow will **stall loudly** instead of finishing silently wrong.
- **D-B — a loop declares at creation whether its work needs evidence.** This was not one of the
  four options offered; the operator wrote it themselves. It makes loops a real working mode rather
  than a structural dead end.

### The stall hunt

| Category | Found | Removed |
|---|---|---|
| Operator decisions | 2 blocking (evidence acceptance; what a loop is) | Both asked and answered before arming |
| Missing artifacts | The whole analysis existed only in a chat session | Written to `openspec/explorations/` and committed |
| Environment | 8010 and 8011 both healthy; `claude` on PATH; py 3.11.9 | Verified, not assumed. **8011 serves whatever code it was started from — the run must restart it from the branch before trusting a drive.** |
| Unstated constraints | — | 20 limits carried verbatim into `STATE.json` |
| Vague queue | — | 19 items, each written for a stranger with no memory of this session |

Seven further decisions the run may hit were **pre-authorised** with a default and a stated cost
(`decisions_for_user` D1–D7), the sharpest being D5: an evidence-free loop task must merge its
**task** branch, never an agent branch — merging an agent branch is finding F58 exactly, and F58 is
severity A.

### Queue shape, and why this order

Four changes, each a full spec loop (R1/R2/R3/IMPL, never collapsed), with drives interleaved:

```
A  a-flow-briefing-names-its-contract        F140, F143   ← cheapest, stops the waste loop
B  a-review-a-flow-cannot-staff-is-named     F142         ← enforcement of agent-flows:134
C  approval-refuses-unaccepted-evidence      F122         ← operator decision D-A
DRIVE-1  prove a flow lands work end to end               ← THE POINT OF THE RUN
D  a-loop-declares-whether-it-needs-evidence F124         ← operator decision D-B
DRIVE-2  both loop modes, and re-drive the flow
SUITE    full uncontended suite, push, do not merge
```

A, B and C together are what make a **flow** work; D is about **loops**, a separate mode. Hence
the drive between them: the flow is proven before the loop work starts, so stopping anywhere leaves
complete changes rather than half-written proposals.

An **05:30 rule** parks spec work at a clean boundary and hands the remaining time to whichever
drive is next — so the run ends having proven something.

### State at arming

- `master` = `3a274a2`, tree clean, nothing in flight.
- CI green on `c6cdf9e` (all nine jobs, run `33310555286`); the only commits since are docs.
- The full hub suite was **not** re-run at arming — ~14 minutes, and green at `894d5b2` with no
  product code moved since. It runs in the `SUITE` item, uncontended, before the branch is offered.
- One change already in flight and **not** this run's job:
  `openspec/changes/a-write-outside-the-workspace-is-recorded` (F115), proposed, unimplemented.

### Next

Iteration 1: read the exploration, cut the branch, begin `A-R1`.

---

## Iteration 1 — 2026-08-30 23:24 → 2026-08-31 00:2x (+01:00) — change A, all four items

**Queue items closed:** `A-R1`, `A-R2`, `A-R3`, `A-IMPL`.
**Commits:** `7da91a3` (R1), `e828add` (R2), `fae6939` (R3), `1b4c730` (IMPL).

Branch was already cut at `ddbcc3a` and clean; `git log` matched `STATE.json`. Nothing to
reconcile.

### What the three rounds actually found

The discipline earned its cost again, and this time each round found something the one before it
could not have.

**Round 1** wrote the proposal from the exploration without re-exploring, as briefed. Two ADDED
requirements in `agent-flows`, because the corpus is genuinely silent: **no requirement anywhere
defines what causes `in_progress → completed`.**

**Round 2 killed one of round 1's claims outright.** Round 1 said a claimed task arrives at
`assigned` or `in_progress`, so the briefing should name both hops from the first and one from the
second. There are **three** arrival states: `CLAIMABLE_STATUSES` is `_statuses_in(BAND_AGENT_ACTIONABLE)`
= `{pending, assigned, in_progress, revision_needed}`, and `enter_selected_task` moves only
`pending → assigned`. A task returned for revision is briefed **at `revision_needed`**, from which
`TRANSITIONS` offers `in_progress` and nothing else. A briefing written to round 1's rule would have
named `completed` as the next call from `revision_needed` — *describing a call the machine refuses,
which is the exact defect the change exists to remove, reintroduced by the fix.*

Round 2 also found three constraints round 1 did not know about: the briefing is **not** the whole
delivered text (`job.message` follows it on both paths, and in F143's own transcript that message
said *"Work the task you have been given"* — to a reviewer); `test_flow_width.py` asserts the words
`"review"` and `"flow"` are absent from a *whole* document-less loop briefing, so every added word
had to clear both; and round 1's evidence wording would have become **false** the moment change C
ships.

And it found the harness wanting the wrong thing: `t_row12_review_leg.py` asserts *"the briefing
names the commit under review"*. It must not. The commit is resolved one step later, at spawn, by
`commit_for_task_review`, and `ReviewContext.work_moved` already exists for the case where the two
disagree. **That check was corrected rather than satisfied.**

**Round 3 found the consequence nobody had asked about: what *else* depends on the transition that
never happens.** `consider_handover` declines at its second gate when `_task_this_run_completed`
finds no `completed` transition attributed to the run. So in F140's drive, both agents called
`submit_checkpoint_notes`, both tasks stayed `in_progress`, and **no handover checkpoint was ever
generated** — the notes are unconsumed to this day. `agent-flows:379` (*"A flow generates the
author's handover briefing"*) and `agent-flows:412` (*"A reviewer is briefed by the author"*) are
both shipped, both tested, and **both unreachable in a real flow.**

The sharpest form of it: the briefing's own sentence *"Record what a reviewer will need … somebody
else reads it"* **was false**. Nobody read it. The briefing asked for a record and never asked for
the thing that delivers it. That is one defect, not two, and it made the change's case far better
than rounds 1 or 2 had.

Round 3 also strengthened the central argument. The strongest objection to fixing prose is that the
defect is structural — there is no `finish_turn`, so progress hangs on an agent choosing to call a
general-purpose tool. Round 1 answered *"it already does, unavoidably"*, which says the alternative
is unavailable rather than that this one is right. The better answer is that **the product already
decided this exact question in writing**, about `ask_user`: *"An agent that needs an answer calls
`ask_user`; a turn that ends without calling it has ended."* Two halves. **This change is the
first.** The second — a turn that ends without the call being *visible* rather than silently
re-briefed — is `loop-firing-accountability`'s, and the proposal now says so in those terms rather
than filing it as a nice-to-have.

And it found round 2's **own** new requirement over-reaching: telling a reviewer that the loop's
message *"does not describe this turn"* is wrong exactly where its author thought hardest, since a
standing message may itself be written to address a review. Narrowed to identifying what the text
is, with instructing the agent to disregard it now forbidden.

Rejected alternatives are recorded so they are not re-proposed: a `finish_turn` tool (a second
writer of a fact `apply_transition` owns — and it does not solve the problem, since an agent never
told to call `update_task` would not be told to call `finish_turn` either); the Hub concluding
completion from a clean turn end (**foreclosed**, not merely undesirable: it must author a
`TaskTransition` with an actor, and `task-lifecycle-governance:359` forbids a third actor kind); and
a separate `_compose_review_briefing` function (three shared sections duplicated to avoid one
conditional).

### The reproduction, run against unmodified code before anything was written

```
--- F143: review briefing vs implementation briefing ---
identical: True
--- F140: what the briefing names ---
  submit_checkpoint_notes    present=True
  update_task                present=False
  record_evidence            present=False
  the word 'completed'       present=False
```

Both defects, exactly as filed. The permanent tests are that reproduction with its assertions turned
around.

### What shipped

`_compose_loop_briefing` takes a keyword-only `is_review` with **no default** — a default is what
would let a future call site reintroduce F143 — plus three helpers. What an agent is now handed:

```
**Finishing means moving the task.** It is `assigned` now; call
`update_task("task-9c1f2a", status="in_progress")` when you start and
`update_task("task-9c1f2a", status="completed")` when the work is done. Nothing else moves
it, and a turn that ends with the task unmoved leaves the next firing to claim the same task
and ask somebody to do the same work again. Record what whoever checks this work will need
before you move it (see `submit_checkpoint_notes`) -- those notes are delivered only when the
task reaches `completed`.

**This task serves `FR-1`.** Record what demonstrates it with `record_evidence("FR-1", summary)`.
What you record enters `awaiting`: somebody else decides on it, and the work cannot land until
they do.
```

and a reviewer, instead of *"Finish the task below and stop"* over the implementation description:

```
**This turn is a review.** Somebody else finished the task below; you are checking their work,
not doing it. …

**End the review with a verdict, using `update_task`.** The task is `under_review`: set it to
`approved` if the work is right, or `revision_needed` if it is not. …

## Under review: Add power(a, b) to calc.py

What the author was asked to build. This is the standard you check their work against, not an
instruction to you.

…

Below this line is the loop's standing message, delivered on every firing. It was not written
for this turn in particular.
```

Both were read end to end as delivered — briefing plus `job.message` — not merely asserted against.

### Verification

- `hub/tests/test_briefing_names_its_contract.py` — 18 new tests, all green.
- `pytest hub/tests/ -k "flow or loop or brief or scheduler or handover or divergence or job"` —
  **451 passed, 14 skipped, 0 failed** (5m57s).
- `ruff check src/ hub/ tests/` clean; `black --check --target-version py311` clean over all 525
  files.
- Six existing call sites now state `is_review=False` explicitly. They failed loudly first, which is
  the no-default decision working.

**What is not proven.** Whether a real agent acts on the text. String assertions cannot settle that
— `DRIVE-1` is the question, and `t_row12_flows.py` now carries a mechanical pass condition for it
(every task the flow worked has left the active band) rather than a transcript to read.

### Next

`B-R1`: propose `a-review-a-flow-cannot-staff-is-named` (break 4, F142).
