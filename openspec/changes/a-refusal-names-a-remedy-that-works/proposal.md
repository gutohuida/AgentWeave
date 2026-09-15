# Proposal — a refusal names a remedy that works

## Provenance

Split from `an-unstaffed-review-names-its-holders` on 2026-09-15, by the operator's decision
(`spec-queue/DECISIONS.md`, `### 2026-09-15, later`), following the adversarial review (REV,
2026-09-14) that stopped the parent change. REV's own words: *"The separable half is D4 and D5,
with `own_review_remedy`, the model fit (2.5, 2.12) and 2.13. F353 was re-observed on LoopEngine,
so the build row covers it in its own right."* This directory carries exactly that half, with its
task numbers and decision text carried over **verbatim** from the parent's `tasks.md` and
`design.md` — nothing here has been reworded in the split, only regrouped and renumbered. The
parent directory keeps the rung-3 naming half (D1, D2's availability/clause logic, D3, D6), which
is not ready to build: it depends on `F352-free`, decided the same day in favour of option (f),
reachability (`4b59ee0`) — not the option this half's sibling was written against. The rung-3 half
needs its own re-derivation round before it can build; this half does not, and takes **one
verification round** instead of the parent's three, per REV.

This change needs no answer to `F352-free` at all: none of its four findings, its two spec deltas,
or its tasks touch who counts as available. It fixes what the Hub *says* once staffing has already
failed, for whatever reason staffing failed.

## Why

An operator refused by the same three sentences, watched live on the operator's own second project
(LoopEngine, `:8000`, read `mode=ro` 2026-09-13/14):

1. **F353, the remedy names controls that do not exist.** Three refusals tell the reader to *"clear
   the assignee"* and to *"assign"* or *"dispatch a different reviewer"*:
   - `_guard_reviewer_is_not_the_author`, both branches (`task_transition_service.py:447-464`);
   - `review_dispatch_refusal` (`agent_trigger.py:498-504`).

   The drawer renders Assignee read-only (`TaskDetailDrawer.tsx:380-395`). The agents' MCP
   `update_task` has no assignee field (`mcp_server.py:307`). No UI control dispatches a review
   (F336). The action that does work, **Land it** (`tasks.py:1473`, F163), sits in the same drawer
   and none of the three names it. On LoopEngine the agents met the guard's refusal eight times:
   the Architect six, `tester` twice. In every form the observations quote, the holder named is
   `dev`, so each refused agent was a would-be reviewer, not the author. None of them could act on
   the remedy it was given (`spec-queue/observations/2026-09-14-LoopEngine.md`, Architect item 4
   and `tester` item 3).
2. **F334, the dispatch-time refusal states an assignment nobody can see.** The flow and the
   dispatch stage the reviewer into `assignee` before the transition (`scheduler.py:816`), and the
   rollback after a refusal discards it. So *"it is assigned to 'authr8f'"* describes a state that
   was never committed. The task is `("completed", None)` before and after. F334 is folded in
   because it edits the same sentences.
3. **F365, a surfaced step is recorded once per fact, not once per task.**
   `_review_unstaffed_already_stands` (`scheduler.py:1913-1941`) reads the **loop's** newest
   `review_unstaffed` and compares its `task_id`. When two or more tasks are unstaffed, their
   events alternate, the newest is always the other task's, and every firing records again.
   Measured on LoopEngine (`%TEMP%\f352\q1.py`, mode=ro), **347 of 357** events repeat their own
   task's previous reason word for word.
4. **F367, an existing reason already exceeds the run history's own length bound.**
   `_wedged_review_reason` (`scheduler.py:1744-1748`) reaches `error_summary` and measures 551
   characters with a 32-character reviewer and a 256-character title — over the 500 that
   `GET /jobs/{id}/history` validates (`schemas/jobs.py:88`). SQLite stores the overlong value
   without complaint; the history route then answers 500 for as long as that row is among the
   rows it returns.

## What changes

- **`own_review_remedy(task)`, one status-aware helper**, public in `scheduler.py`. For a
  `completed` task: Land it, on the task, as the operator's own review — with no promise that it
  approves (the approval gate may still refuse while evidence awaits judgment). For an
  `under_review` task: the three exits (approve, reject, revision_needed), and never Land it,
  which `land` refuses with a 409 there. This is the status half only; nothing here decides who
  is free to be handed a review — that is the sibling directory's problem.
- **Every `JobRun.error_summary` write is fitted to its declared 500-character column, at the
  model.** `JOB_RUN_ERROR_SUMMARY_CHARS`, `fit_error_summary(text)`, and `@validates` on `JobRun`
  catch all eight writes, so no future write site can miss it. `_wedged_review_reason` shortens
  its quoted title first, so the sentence keeps its remedy rather than being cut from the end.
  `_stall_run_to_increment` compares the fitted value, so a shortened reason that recurs is still
  recognised as the same stall.
- **A surfaced step is recorded once per task, not once per loop.**
  `_review_unstaffed_already_stands` compares against the newest `review_unstaffed` **for this
  task** in this loop, not the loop's newest record of any task.
- **The author guard's two sentences and the dispatch refusal name remedies that exist**:
  - to the operator, Land it, or dispatching another agent's review turn (`POST /agent/trigger`
    with `review_task_id`) — never the PATCH that sets assignee and status together, which queues
    no turn and produces F154's wedge;
  - to an agent, that none of the task tools it is offered reassigns a task, and who can move the
    work on — never "no agent can", which F366's HTTP route makes false;
  - the dispatch refusal's remedy follows the task's status, because that refusal can meet an
    `under_review` task, which `land` refuses;
  - the D9 "Reassign the task" sentence, which names a control the operator does not have, becomes
    "let the review in flight finish, or decide it yourself."

  They are worded so they are true whether the assignee was committed before the request or staged
  by it (F334). The rule each guard enforces does not change — only the sentences.

## Capabilities

### Modified Capabilities

- `agent-loops` — *"A surfaced step is recorded once, not once per tick"* gains a scenario for two
  steps surfaced by one loop. Adds *"A firing's recorded reason never makes the loop's history
  unreadable"* (F367).
- `task-lifecycle-governance` — *"A task entering review must not still name its author as its
  holder"*: the refusal's remedy is one the refused actor can take, true whether the assignee was
  staged by the request. The operator's author-refused dispatch names a remedy for the task's
  status.

Not touched: `agent-flows` (the rung-3 naming requirement stays with the sibling directory, which
also owns `agent-flows`'s delta).

## Impact

- **Python:**
  - `hub/hub/scheduler.py`: `own_review_remedy` (new, public); `_wedged_review_reason`'s title
    fit; `_stall_run_to_increment`'s comparison; `_review_unstaffed_already_stands`.
  - `hub/hub/db/models.py`: `JOB_RUN_ERROR_SUMMARY_CHARS`, `fit_error_summary`, and
    `@validates("error_summary")` on `JobRun`. `hub/hub/schemas/jobs.py` reads the constant.
  - `hub/hub/task_transition_service.py`: the guard's two sentences.
  - `hub/hub/api/v1/agent_trigger.py`: the dispatch refusal's sentence, and the D9 "Reassign"
    sentence at both its sites.
- **Not touched:** `hub/hub/mcp_server.py` (F354; nothing here needs it); who is free
  (`_agents_that_are_free`, `resolve_reviewer`'s rung-3 clause construction); the transition map;
  every guard's *decision* (only its wording); the UI (the board's hover line is D6, the sibling
  directory's).
- **No migration.** No API shape change: `error_summary` and every refusal's `detail` are already
  strings.
- **Findings:** retires F353, F334, F365 and F367 once built and archived. Leaves F352 open — its
  visibility half ships with the sibling directory once re-derived; its definition half closed
  2026-09-15 (`F352-free`, decided (f)). Leaves F366 open: this change stops relying on the route's
  hole, closing it is that finding's own loop.
