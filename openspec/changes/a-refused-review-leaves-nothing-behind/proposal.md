> **File isolation from `a-url-is-not-a-path` (approved for the same night).** This change does
> **not** touch `hub/hub/mcp_server.py`, `hub/tests/test_permission_approver.py` or
> `docs/reference/permission-postures.md`. Its code is `hub/hub/turn_scheduler.py` and one comment in
> `hub/hub/api/v1/agent_trigger.py`, which that change states it does not touch. The only file both
> changes edit is `scripts/drive/FINDINGS.md`, each in its own findings' sections, at close-out.

## Why

**F319 (A).** A review that is refused when its queued turn is delivered leaves the task staffed
for a review that never happened. The board shows an ordinary `Under Review · Idle` card, and the
next reviewer the operator sends is refused because the task is "already under review".

**F320 (B).** The scheduling pass that gives up on a refused queue head then returns. The input
queued behind that head is never delivered, until some unrelated event schedules that agent
again. There is no timer to do it (`agent_trigger.py:2433`: *"There is no tick"*).

The operator decided both on 2026-09-12 (`spec-queue/DECISIONS.md`, *"F319 + F320, decided
2026-09-12 afternoon"*):
- A refused review dispatch leaves the task exactly as it was before the dispatch, and the operator
  is told. No assignee, status change or transition row survives a refusal, whichever refusal and
  whichever path.
- A scheduling pass that abandons a refused queue head moves on to the next entry.
- One change, not two.

The decision left the mechanism to R1. This proposal chooses it from measurement.

### The mechanism, in one paragraph

`trigger_agent_directly` stages a review in its caller's session. `enter_selected_task`
(`scheduler.py:768`) writes the reviewer into `assignee`, then applies `completed -> under_review`
(`agent_trigger.py:836`). Everything that can refuse after that point raises `TriggerAgentError`
into the dispatch's one caller, `turn_scheduler.schedule_agent`. That caller writes the refusal onto
the queued entries as `waiting_reason`, then calls `await db.commit()` on **the same session**
(`turn_scheduler.py:347-349`). That commit makes the staged assignee, status and transition row
durable. The comment above the staging (`agent_trigger.py:788-793`) says a refusal *"abandons
it"*. That comment is design D10 of `2026-08-28-a-review-started-by-hand-can-finish`, whose
premise is true of the dispatch and false of its caller. **Every step of that argument is right
except the last one: the transaction is abandoned only if the caller discards it, and the caller
commits it.**

**The fix is for the caller to roll back before it records anything** (`design.md` D1). Then it
re-reads the entries by id, writes the refusal's words, counts the attempt and commits, as it does
today. F97 wanted the refusal's words kept where the operator reads them, and they are, because they
are written *after* the rollback. The staged review is not. `schedule_agent` then goes on to the
next entry whenever the attempt it just made gave up on its head (D4).

### What R1 measured

Measured on the unmodified tree at `87dfbf4` (hub code identical to `6468aed`), with scratch tests
under `testbed/scratch/r1f319/`. Each was copied into `hub/tests`, run once and deleted.

| leg | refusal | today, after one `schedule_agent` | with the prototype |
|---|---|---|---|
| B0 | project is not a git repository (`review_turn.py:201`) | `('under_review', reviewer)`, +1 transition, no run | `('completed', None)`, no transition |
| B1 | commit absent (`worktrees.py:546`) | same | same as before the dispatch |
| B2 | review checkout path obstructed (`worktrees.py:599-604`) | same | same as before the dispatch |
| A | entry guard, §3.4 fallback (`task_transition_service.py:454`) | `('completed', author)`, no transition | `('completed', None)` |
| **T** | **transient** HUB_URL unknown (`agent_trigger.py:1146`), raised after staging | `('under_review', reviewer)`, entry queued at 0 attempts | `('completed', None)`, entry queued at 0 attempts |

- **Leg T is new, and it is the same mechanism.** A deferral that is meant to clear on its own
  still commits the staged review. That happens at the startup re-drain, before the Hub has served a
  request (the comment at `agent_trigger.py:1152-1157`).
- **What a rollback discards (instrumented flushes).** Nothing on a non-review turn refused at the
  last raise site. On a review turn: exactly `Task` (dirty) and `TaskTransition` (new). No commit
  happens inside the dispatch before any refusal. The scheduler's own session holds nothing
  pending when it makes the call.
- **Over three passes with the prototype**, B1 and A each leave the task as it was on every pass.
  The entry is withdrawn at the third attempt, with the refusal as its `waiting_reason`, and
  `queue_entry_abandoned` is emitted. So the operator is still told, through the same two surfaces
  as today.
- **F320.** Today, after one `schedule_agent` whose head reaches the limit, the trigger was called
  **once**. The head is `withdrawn`, and the entry behind it is still `queued` at 0 attempts. With
  the prototype the trigger is called twice, and the entry behind is delivered.
- **The prototype against the 57 test files that touch this path** (748 tests): one failure. It
  is `test_a_blocked_task_checkout_still_counts_with_nothing_waiting`, whose second entry's
  `("queued", 0)` encodes F320 itself (`design.md` D6).
- **Savepoints are unusable here as they stand.** On this engine a successful `begin_nested()`
  whose savepoint opened the transaction **commits** on release. Another session saw the write, and
  the outer rollback did not undo it (D2).

## What Changes

- **`turn_scheduler.schedule_agent`, refusal branch.** On `TriggerAgentError`, first
  `await db.rollback()`. Then re-read the selected entries by the ids captured before the call, and
  re-read the agent's queued entries. Use the conversation id captured before the call. Then record
  `waiting_reason`, count and abandon, and emit exactly as today. A rollback expires every loaded row.
  Without the re-read, five tests of the workspace-counting branch fail with `MissingGreenlet`
  (measured, D3).
- **`schedule_agent` goes on after giving up.** The body becomes one attempt. `schedule_agent`
  repeats it under the same lock and session **only while the previous attempt gave up on at least
  one entry**. Anything else ends the pass as today: a turn started, a transient or agent-wide
  refusal, an attempt counted without being given up on, or an early return. Each repetition follows
  at least one entry leaving the queue, and an entry that arrives meanwhile has no attempts, so it
  cannot be given up on in its first attempt. That bounds the loop (D4).
- **What the pass reports** is the last attempt's result, except where that attempt found the queue
  empty. Then it reports the attempt that emptied it (D5).
- **Comments that are false today are corrected**: `agent_trigger.py:788-793` (a refusal abandons
  the staging only because the one caller rolls back) and `turn_scheduler.py:493-497` (*"the next
  tick tries again"*).
- **A source-scan test** pins that `trigger_agent_directly` has one production caller. The
  rollback lives in that caller, and a second caller that commits after a refusal would bring F319
  back.

## Non-goals

- **Weakening the entry guard.** Leg A exists because of `4929ea0`'s §3.4 fallback, which
  `DIRECTION.md` 2026-09-13 says must stand. Nothing in `task_transition_service.py` changes. Leg A
  is closed because the guard's refusal now discards the assignee that
  `enter_selected_task` wrote so the guard could judge it.
- **The flow's own staging.** `_do_fire_job` (`scheduler.py:2794`, committed at `:2891`),
  `_fire_additional_selection` (`:3156`) and a divergence restaff (`run_divergence.py:458`) record
  their reviewer **before** the dispatch, in a commit of their own, as their design requires (F45).
  A refused dispatch leaves those tasks exactly as that commit left them. That is *"as it was before
  the dispatch"*. Undoing them would need a reverse transition the lifecycle does not declare. And
  `agent-flows` already names a review nobody is doing (D7). **R2 should attack this reading of
  "whichever path".**
- **Timers.** No tick is introduced. F320 is closed inside the pass that gives up.
- **The review checkout left by a refusal raised after provisioning.** Measured: leg T leaves
  `.agentweave/reviews/<reviewer>` registered. Filed as **F326 (D)**, and out of this verdict (D8).
- **Who a successful review entry is attributed to.** `enter_selected_task` records
  `completed -> under_review` as `operator()`, whoever dispatched. After this change that row exists
  only when the review starts. Its attribution is unchanged.

## Capabilities

### Modified Capabilities

- `task-lifecycle-governance`: ADDED *"A refused review dispatch leaves the task as it was before
  the dispatch"* (8 scenarios). The main requirement *"Dispatching a review staffs the task,
  whichever path dispatched it"* already says a refused review leaves the task *"exactly as the
  refusal found it"*. It is **not** MODIFIED, because a MODIFIED block must re-assert its scenario
  *"A refused review leaves no checkout behind … for any reason"*, which R1 measured false for
  refusals raised after provisioning (F326). D9 explains the choice.
- `agent-conversation-workspace`: ADDED *"Giving up on queued input goes on to the input behind
  it"* (6 scenarios).

## Impact

- **Code:** `hub/hub/turn_scheduler.py` (`schedule_agent` split into a loop and one attempt, plus
  the rollback and re-read). `hub/hub/api/v1/agent_trigger.py`: comment only.
- **Tests:** a new `hub/tests/test_a_refused_review_leaves_nothing_behind.py`.
  `hub/tests/test_a_blocked_workspace_counts_where_input_could_run.py:227` has one expectation
  changed, deliberately (D6). The docstrings of two tests in
  `hub/tests/test_the_evidence_names_the_author.py` (`:474-480`, `:517-520`) stop saying the product
  path is unverified.
- **Harness:** `scripts/drive/t_d1_0912_f319_reach.py` gains a fixed-tree mode, and an F320 leg that
  uses only operator routes.
- **No** migration, no API or schema change, no UI change.
- **Findings:** closes F319 and F320 when built and driven. Files F326 (D), which stays open.
