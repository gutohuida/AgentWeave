# Proposal — an unstaffed review names its holders

## RESOLVED 2026-09-19 — the re-derivation this banner demanded is done; see `## R5` below

**This change is no longer stopped.** The banner below is kept as provenance because it is the
record of *why* a round was owed. The round ran on 2026-09-19 (`design.md`, `## Round 5`) and the
change is ready for implementation — with `D1`'s corrected record shape, and with D2's character
budget re-measured first (task 2.4).

**It still needs an operator token in `spec-queue/APPROVALS.md` before any night may build it.**

## ~~STOPPED, 2026-09-15~~ — the split shipped; this half needed re-deriving (discharged, R5)

**Both questions this file raised are decided** (`spec-queue/DECISIONS.md`, `### 2026-09-15,
later` and the `F352-free` row).

- **The split is done.** The F353 half — D4, D5, `own_review_remedy`, the `error_summary` model
  fit, and their tests — now lives in `openspec/changes/a-refusal-names-a-remedy-that-works/`,
  ready for its one verification round. `tasks.md`, `design.md` and `specs/` here have had that
  content removed; read the sibling directory for it, not here.
- **`F352-free` is decided: option (f), reachability — not (d), and not the (e) this file's
  remaining half (D1, D2's naming/clause/prefix/budget logic, D3, D6) was written against.**
  Option (f) already shipped, independently of this change: `4b59ee0`
  (`openspec/changes/archive/2026-09-15-a-task-nothing-will-move-holds-nobody`),
  `hub/hub/scheduler.py:1138`. An independent adversarial (Opus) review, asked to validate (d)
  once (f) was found to have shipped, rejected (d) in (f)'s favour — its full reasoning is in
  `spec-queue/DECISIONS.md`'s `F352-free` row.

**What is left here is real, undone work, not a resolved blocker: rung-3's naming needs
re-deriving against (f), from scratch, through its own R1.** (f) redefines *holding* itself
(a task holds its agent only if a live loop still walks it or a queued turn names it), which is
upstream of everything D1–D3 below say about clauses, exclusions and the prefix sentence. That
re-derivation has not been done in this pass — it is the next round to run on this directory, not
a mechanical find-and-replace of "(e)" with "(f)".

The rest of this file (below) is the REV-era text, kept for provenance. Read it as history: the
OPERATOR QUESTION section's options (a)-(e) no longer include the option that shipped, and the
"Why it stopped" reasoning below is superseded by the decisions above.

## R5, 2026-09-19 — the re-derivation is DONE. This change is unblocked, and smaller than it reads

Run interactively at the operator's instruction. Full findings: `design.md`, **`## Round 5`** —
read `R5-0` before touching `D1`.

**The decision to name the holdings survives a fourth pass. Four things under it do not.**

1. **`D1`, implemented as written, would silently revert `4b59ee0`** — it specifies the pool as
   *"holds no live task"* and claims no agent's membership changes, and both were true at R1 and
   are false now. `D1` is amended in place. This is the one to read first.
2. **The `Why` below is a wedge (f) already fixed.** `test_the_loopengine_shape_staffs_its_review`
   asserts `decision.unstaffed == ()` in exactly the shape the `Why` narrates. Rung 3 is still
   reachable — whenever every non-excluded agent is running, held, or holding *in-loop* work — and
   when it is reached the sentence still names nobody, which is F352 entire. But the justification
   is now that narrower circumstance, **not** the LoopEngine night.
3. **Three of the five findings the `Why` names are already closed.** F365 shipped
   (`scheduler.py:2120-2153`), F367 and the `error_summary` fit shipped
   (`models.py:1336-1348`), and F353/F334's remedy half archived 2026-09-16 with the sibling.
   **Only F352's visibility half is left here.** `tasks.md` §3 is already struck; this file was
   never swept with it, so treat *Why* items 2–4 and the `error_summary` bullet under *What
   changes* as history.
4. **The remedy changes.** Rejecting a held task still frees, but under (f) the strong remedy is
   **archiving the loop that holds them** — which frees every agent holding only its tasks at once,
   which (e) could not do, and which the operator has a real control for. It must name the *other*
   loop, so clause 3 now carries each holding's loop id. **Pausing frees nobody**
   (`scheduler.py:1084-1085`) and the sentence is forbidden from suggesting it — that would be a
   fresh F353 committed by the change whose subject is F353.

**Status: ready for implementation**, with `D1`'s corrected record shape, and with D2's character
budget **re-measured first** — R5 changed the strings and did not recompute the table, and the
500-character bound is now enforced at the model.

**The `OPERATOR QUESTION` section below is CLOSED.** It recommends option (d); the operator
rejected (d) and took (f). It is kept only as provenance. Do not read it as an open choice, and do
not re-open (a)–(e) — the decision is `spec-queue/DECISIONS.md`, the `F352-free` row.

## STOPPED AT REV, 2026-09-14 — specced, unbuilt, waiting on the operator (superseded, kept for provenance)

The adversarial review (REV, an Opus subagent, 2026-09-14 ~12:15) read this change and the
decisions it rests on, and **stopped it**. Nothing here is built, and no task in `tasks.md` is
ticked. Its full findings are in `design.md`, *Round 4 — REV*.

- **Why it stopped.** DIRECTION.md 2026-09-14 attaches *"the change stops after REV, unbuilt"* to R1
  finding a choice that is the operator's and writing it here as an OPERATOR QUESTION. R1 did both.
  R1's reading, that scoping the question out of the change avoids the stop, would let any R1
  cancel the clause, so the clause could never fire. REV rejected that reading, and the window does
  not substitute its own judgement for a DIRECTION clause (`day-window.md`, *A day that builds*).
- **Why the reading was also wrong on its merits.** The rung-3 half is not independent of the
  answer. Its freeing clause, *"rejecting a held task … frees its agent"*, is option (e)'s remedy.
  Under the recommended (d), an agent is unavailable for a review only while it is running or
  already reviewing, so a sentence naming every `pending` and `in_progress` holding would name
  things that are not reasons. The (d) change would then have to MODIFY this change's new
  requirement. The old line *"built for the sentence that option will need"* was false for (d).
- **What REV recommends to the operator: a split.** The F353 half (D4 and D5: the refusals'
  remedies, F334's wording, F365's once-per-task record, and the `error_summary` fit F367 needs)
  does not depend on the definition of free. F353 was re-observed on LoopEngine, so the 2026-09-14
  build row covers it in its own right. REV's split moves that half into its own change directory.
  That directory needs one verification round, not three, and can then be built. The rung-3
  naming (D1, D2, D3, D6) waits for the answer to the OPERATOR QUESTION below. The window did
  **not** split the change on its own authority, and the question is in `decisions_for_user`.
- **REV also found defects in the change itself.** They are fixed in these files now, so they are
  fixed whichever way the operator decides:
  - D5's operator remedy produced the wedge it was meant to explain. It now names the review
    dispatch instead.
  - The agent sentence's claim about its tools was false for `create_task`.
  - The guard sentence overflowed 500 characters, and the fit would have cut its remedy.
  - The rung-3 prefix, *"nobody is free"*, was false when the author is free.
  - `own_review_remedy` was undefined for the statuses a divergence can still reach.

## R6, 2026-09-19 — the adversarial review of R5, applied. DO NOT build the pre-R6 text

An independent Opus review, aimed at R5 because R5 was written by the same model in the same
session. Verdict **DO NOT APPROVE**; its four load-bearing findings were re-verified against the
code and all four held. Full log: `design.md`, **`## Round 6`**.

**R5 re-derived D1 against one of the two changes that had landed on `_agents_that_are_free`, and
missed the twin.** `agents_held` is ORed into the running set in the same expression R5-0 quotes
(`scheduler.py:1114-1122`), and appeared nowhere in this change — so D1 would have reverted
`a-spent-allowance-holds-the-queue` as well as `4b59ee0`. D1 now carries `held`.

The rest, in order of what it changes:

1. **The sentence gains a fifth clause, and it was a shipped `SHALL` all along.** A held agent must
   be named as held; the four-clause list would have reported it as *running a turn*, which is
   false. Three shipped tests break as a result — one an **exact string equality** on the whole
   rung-3 sentence — and none was in any round's list of call sites.
2. **The archive remedy R5 invented is removed.** It frees nobody held through reachability's
   queued arm, it is inapplicable in the in-loop case R5-1 leaves as the dominant one, and the loop
   id it prints is not the identifier the working control takes. Clause 3 loses the loop id with
   it. **R5 was asked for a subtractive re-derivation and the one thing it originated had to come
   out.**
3. **The flagship test could not have been built.** 2.6 stages `loop_id` NULL holdings, which under
   (f) never reach rung 3 at all.
4. **A build-order hazard**: task 2.3 before 2.14 turns an operator's mid-run status move into an
   `AssertionError` in the scheduler. 2.14 now runs first.
5. **Twenty-two drifted citations**, including six of twelve call-site line numbers.

**This is the "materially smaller change" the review argued for.** What is left: clause 1 + 2 +
3-filtered-by-reachability + the hold clause + running, the existing status remedy, and the reject
clause.

**Measured after the fact, same day** (`design.md`, *Round 6, measured*): the budget R5 and R6 both
deferred is now done from the real strings. R6's removals bought ~150 characters — the flagship
shape is **410/440** against a 500 bound, where the review measured R5's at 559/589 — so the fit no
longer fires on the main case. It still fires at **seven agents** on an `under_review` task, and
29-character task ids land exactly on 500, so the fit and R3's "name at least one agent" floor both
stay.

Measuring it also found **R6-8**: `own_review_remedy` ends in a period and every round from R1
appended the reject clause with a leading `;`, so the sentence read `…yourself.; rejecting…`. Five
rounds specified the two halves separately and none concatenated them.

**Verified by running, not derived:** `hub/tests/test_a_held_agent_is_busy.py` and
`hub/tests/test_a_task_nothing_will_move_holds_nobody.py` — **55 passed**, 36s, on `7d805df`. Those
are the two files R6-1 and R5-0 say this change must not break; they are green today, so the
regression guard in task 1.3 and 6.0 has a real baseline.

Still **not** done: `test-guide.md` is not re-derived (task 6.5), and no test of the new behaviour
exists yet because none of it is built.

## Why

On the operator's own Hub (LoopEngine, `:8000`, read mode=ro on 2026-09-13 and 2026-09-14), a flow
stood still for most of a night with two finished tasks nobody reviewed. Every firing recorded the
same `review_unstaffed` sentence (`hub/hub/scheduler.py:1161-1168`):

> *could not staff this step: no agent is free to take it. Every agent on the roster is either
> running a turn, already holding active work, or is the one that completed this task and so may
> not review it.*

It names no agent and no task. No turn was running. Every agent was held by a task in a live status,
almost all of it outside the flow (F352's table). The reviewing agent was asked to diagnose it and
blamed the wrong thing. It then told the operator to reassign, which the app does not offer (F353).
The operator unblocked it by hand at 22:33 UTC with two `land` calls and one rejection.

Four defects share that surface, and this change repairs all four. R2 found a fifth on the column
the sentence is written to, F367, which is under *What changes*.

1. **F352, the visibility half.** The rung-3 sentence names nobody. F352 itself says what any
   repair must do, *"whatever else changes, the unstaffed sentence has to name the holdings — agent
   → task — because it is the whole of what the operator is shown"*. The sentence is also the
   loop board's stall line, rendered one line and truncated (`LoopsIndexTab.tsx:237-244`), so
   what it says first is most of what anyone reads.
2. **F365 (new, measured), the sentence is recorded 357 times, not once.** `agent-loops`
   *"A surfaced step is recorded once, not once per tick"* requires one record per task while the
   reason is unchanged. `_review_unstaffed_already_stands` (`scheduler.py:1913-1941`) reads the
   **loop's** newest `review_unstaffed` and then compares its `task_id`. When two or more tasks
   are unstaffed, their events alternate, the newest is always the other task's, and every firing
   records again. Measured on LoopEngine (`%TEMP%\f352\q1.py`, mode=ro), **347 of 357** events
   repeat their own task's previous reason word for word. Between 22:35 and 22:55 UTC only one
   task was unstaffed, and it recorded once, as designed. So the rule works only while one task is
   stuck. The existing test (`test_an_unchanged_wedge_is_recorded_once_not_once_per_tick`) stages
   exactly one.
3. **F353, the remedy names controls that do not exist.** Three refusals tell the reader to *"clear
   the assignee"* and to *"assign"* or *"dispatch a different reviewer"*:
   - `_guard_reviewer_is_not_the_author`, both branches (`task_transition_service.py:447-464`);
   - `review_dispatch_refusal` (`agent_trigger.py:498-504`).

   The drawer renders Assignee read-only (`TaskDetailDrawer.tsx:380-395`). The agents' MCP
   `update_task` has no assignee field (`mcp_server.py:307`). No UI control dispatches a review
   (F336). The action that does work, **Land it** (`tasks.py:1473`, F163), sits in the same drawer
   and none of the three names it. On LoopEngine the agents met the guard's refusal eight times: the
   Architect six, `tester` twice. In every form the observations quote, the holder named is `dev`,
   so each refused agent was a would-be reviewer, not the author. None of them could act on the
   remedy it was given (`spec-queue/observations/2026-09-14-LoopEngine.md`, Architect item 4 and
   `tester` item 3).
4. **F334, the dispatch-time refusal states an assignment nobody can see.** The flow and the
   dispatch stage the reviewer into `assignee` before the transition (`scheduler.py:816`), and the
   rollback after a refusal discards it. So *"it is assigned to 'authr8f'"* describes a state that
   was never committed. The task is `("completed", None)` before and after. F334 is folded in
   because it edits the same sentence (DIRECTION.md 2026-09-14, *"When two fixes would edit the
   same lines, they become one change"*).

## What changes

> **R6: read this section against `## Impact`, which R6 rewrote.** The bullets below still describe
> the `error_summary` fit, `_review_unstaffed_already_stands`, the guard sentences and the dispatch
> refusal as work to do. **All of that shipped with the sibling change on 2026-09-16.** R5 recorded
> that and did not sweep this section; R6 rewrote `Impact` rather than this prose, because the
> bullets are also the record of what the change argued for. Treat everything here except the first
> two bullets (rung 3's clauses, and the fit) as history, and take the file list from `Impact`.


- **Rung 3 names every roster agent and why it cannot take the review**, in name order:
  - excluded, with the exclusion the caller applied (the author; every agent that worked on an
    operator-completed task; a reviewer that gave no verdict);
  - holding, with each held task's id and status, three per agent and then a count;
  - running a turn, for an agent that holds nothing;
  - no runner bound, for a live roster agent the pool leaves out.

  The per-agent list comes first. After it comes a remedy that exists for the task's status: for a
  `completed` task, **Land it** as the operator's own review; for `under_review`, the three exits.
  The last clause is rejecting a held task that is no longer wanted, which frees its agent. The
  facts come from the **same queries** `_agents_that_are_free` reads, restructured so the pool and
  the sentence are one computation.

  The remedy never promises an approval. `land` runs the approval gate first, and at this rung the
  gate usually refuses while evidence awaits judgment (R2). It does not refuse for a flow declared
  not to need evidence, or where accepted evidence would already merge (R3). One status-aware
  helper writes the remedy's status sentence, for this sentence and for the dispatch refusal below.
  Only rung 3 adds the clause about freeing an agent.
- **The sentence fits in 500 characters, and every `error_summary` write is fitted to its
  column.** `GET /jobs/{id}/history` validates `error_summary` at `max_length=500`
  (`schemas/jobs.py:88`). A longer reason would be stored without complaint by SQLite, and would
  then turn that route into a 500. R2 confirmed that with the real schema at 501 characters.
  - Agents that do not fit collapse into a count, and the remedy is always kept. An agent whose
    held tasks carry long, caller-chosen ids is named with fewer of them before it is counted, so
    at least one agent is always named (R3).
  - The fit is applied **at the model**, so none of the eight writes can miss it.
  - **F367 (new, R2, computed):** `_wedged_review_reason` already passes 500 today, with a long
    title and a long agent name.
- **`resolve_reviewer` takes the exclusion with its reasons.** The divergence restaff
  (`run_divergence.py:430-446`) excludes the silent reviewer and the author together under one
  `excluded_because`, *"is the one that completed this task"*. That is harmless while the sentence
  names nobody. Once the sentence names each agent, it would say a reviewer that gave no verdict
  completed the work, which `agent-flows` already forbids for the author case. The silent
  reviewer's clause overrides *"has worked on this task"*, because the wider author set always
  contains it (R2).
- **A surfaced step is recorded once per task.** `_review_unstaffed_already_stands` compares against
  the newest `review_unstaffed` **for this task** in this loop, not the loop's newest.
- **The author guard's two sentences and the dispatch refusal name remedies that exist**:
  - to the operator, **Land it**, or dispatching another agent's review turn
    (`POST /agent/trigger` with `review_task_id`). **REV:** R1 and R2 named the one PATCH that sets
    the assignee and the status together. That PATCH queues no turn, so in a flow it produced
    F154's wedge (`scheduler.py:1370-1393`), LoopEngine's 63 repeated stalls.
  - to an agent, that none of the task tools it is offered reassigns a task, and who can move the
    work on. R1 wrote *"no agent can"*, and F366's HTTP route makes that false (R2). R2's *"none of
    your tools changes who holds a task"* was false too: `create_task` takes an assignee, and a
    bound `send_message` claims an unassigned task (REV).
  - the dispatch refusal's remedy follows the task's status, because that refusal can meet an
    `under_review` task, which `land` refuses (R2).

  They are worded so they are true whether the assignee was committed before the request or staged
  by it (F334). The rule the guard enforces does not change.
- **The board's stall line shows the whole reason on hover** (`title` on the truncated `<p>`). This
  is UI, so the day's bundle rule applies. If it cannot be driven in a browser today, the group is
  left unbuilt and its row says so.

## OPERATOR QUESTION — CLOSED 2026-09-15: the answer is (f), which is not in the list below

**Decided:** `spec-queue/DECISIONS.md`, the `F352-free` row — **reject (d), take (f)**, reachability,
which had already shipped as `4b59ee0` and was never one of the five options put to the operator.
The table and the recommendation below are **provenance only**. The change is re-derived against (f)
in `design.md`'s `## Round 5`.

Two things in the table below are now wrong on their own terms, recorded so nobody rebuilds an
argument from them: it has no `(f)` column, and under (f) `dev` and `dev_2` are **free** on that
snapshot — so the pool was not empty, the review would have been staffed, and the incident the
table illustrates would not have occurred. `Architect` and `tester` stay held, correctly, because
their tasks are in-loop.

**R6 deleted the options table and the "Recommended: (d)" paragraph that stood here.** R5
recorded that they had to go — *"leaving a recommendation for a rejected option in the file is
how a later round re-litigates a closed decision"* — and then left them in place, under a
banner, where the next reader would still find a recommendation for the option the operator
rejected. The decision and its full reasoning are `spec-queue/DECISIONS.md`, the `F352-free`
row; the re-derivations are `design.md`'s `## Round 5` and `## Round 6`.

Two facts from the deleted table are worth keeping, because they are measurements rather than
argument: on the 2026-09-13 LoopEngine snapshot, under (f) **`dev` and `dev_2` are free** (their
holdings carried no `loop_id` and had no queued turn), so the pool was not empty and the review
would have been staffed; `Architect` and `tester` stay held, correctly, because their tasks were
in-loop.

## Capabilities

### Modified Capabilities

- `agent-flows` — adds *"A review nobody is free to take names who holds what"*.
- `agent-loops` — *"A surfaced step is recorded once, not once per tick"* gains a scenario for two
  steps surfaced by one loop. It also adds *"A firing's recorded reason never makes the loop's
  history unreadable"* (R2, F367).
- `task-lifecycle-governance` — *"A task entering review must not still name its author as its
  holder"*: the refusal's remedy is one the refused actor can take, and it is true whether the
  assignee was staged by the request. The operator's author-refused dispatch names a remedy for
  the task's status (R2).

## Impact

**R6 rewrote this section.** Everything below is what is left after the 2026-09-15 split and the
R5/R6 re-derivations. The previous version listed five files that the sibling change already
shipped; an implementer following it literally would have re-implemented working code.

- **Python:**
  - `hub/hub/scheduler.py`: `_agents_that_are_free` restructured over a per-agent availability
    read (`AgentAvailability` / `Holding`, carrying **`held`** and **`reachable`**);
    `resolve_reviewer` rung 3's five clauses and its remedy.
  - `hub/hub/run_divergence.py`: the exclusion carries reasons (D3), and the status screen task
    2.14 adds.
- **UI:** `hub/ui/src/components/spec/LoopsIndexTab.tsx`, one `title` attribute. The bundle is
  committed only under the day's rule: it must be driven in a browser, and nothing it calls may be
  newer than the `:8000` process. It calls nothing new.
- **Tests this change must UPDATE, not just add** (R6): `hub/tests/test_a_held_agent_is_busy.py`
  — three assertions, one of them an exact string equality on the whole rung-3 sentence, plus
  three `exclude=` call sites that a `Mapping` signature breaks.
- **Already shipped by `a-refusal-names-a-remedy-that-works`; this change touches none of it:**
  `own_review_remedy`, `_review_unstaffed_already_stands`' per-task scope, `_wedged_review_reason`'s
  fit, `_stall_run_to_increment`'s comparison, `JOB_RUN_ERROR_SUMMARY_CHARS` / `fit_error_summary`
  / `@validates` in `models.py`, the guard's two sentences in `task_transition_service.py`, and the
  dispatch refusal in `agent_trigger.py`.
- **Not touched:** `hub/hub/mcp_server.py` (F354; nothing here needs it), **the definition of
  free** — this change reads it, and R5-0/R6-1 are both about not accidentally rewriting it — the
  transition map, and every guard's decision.
- **No migration.** No API shape change: `reason` is already a string on the event and on
  `stall_reason`.
- **Findings:** would retire **F352's visibility half** if built, with a dated note saying the
  definition half was settled separately by `F352-free` (option (f), `4b59ee0`). F353, F334, F365
  and F367 are **already** marked fixed by the sibling directory — this change retires none of
  them. **Leaves F366 open**: this change stops relying on the route's hole, and closing it is that
  finding's own loop.
