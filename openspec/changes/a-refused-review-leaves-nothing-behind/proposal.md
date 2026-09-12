> **ANSWERED 2026-09-12 ~19:20: option (a).** See `spec-queue/DECISIONS.md` row `F327-scope`. The
> change ships as scoped, and F327 stays open. The question is kept below as the record.
>
> ## OPERATOR QUESTION (R2): does *"whichever path"* reach a review a flow staffed before it dispatched it?
>
> **Answer it in `DECISIONS.md` before approving this change.** Tasks §6.3 blocks on it.
>
> **What R2 measured** (F327, `design.md` D7). Suppose a flow staffs a review and its dispatch is
> then refused (a pruned commit, or an obstructed checkout). The task is left `under_review`, held
> by the refused reviewer, with no run. That is F319's end state. The operator is told once, at
> the refusal: the job run fails with the refusal's words. After that the flow reports the task
> **in flight** until the queued input is given up. That takes two more passes for that reviewer,
> and on a quiet project nothing makes them. Only then does it name *"a review nobody is doing"*.
> Throughout, sending a different reviewer is refused with *"… or let the review in flight
> finish"*.
>
> **Why this change cannot reach it.** The rollback discards what the dispatch staged. The flow
> staged its review earlier, in a commit of its own. The two main specs also disagree on exactly
> this point:
> - `agent-flows` requires the firing to stage *"in the same commit that queues the review turn"*.
> - `task-lifecycle-governance` says, for every path, that staffing *"SHALL NOT be performed when
>   the request to review is recorded … so that a request that is never delivered leaves no task
>   held by a reviewer that never ran"*.
>
> **The options:**
> - **(a) Ship tonight as scoped. R2 recommends this.** This change fixes the dispatch's own
>   staging on the route and the scheduler (F319 as measured), and F320. F327 stays open and is the
>   next spec loop. R1's claim that the flow's state already meets the verdict is withdrawn. The
>   delta now says nothing about flows, so it contradicts neither main spec.
> - **(b) Widen this change.** The flow stops staging before the dispatch. The dispatch stages the
>   review instead, as it already does for a review entry, and the pool exclusion reads the pending
>   entry (`tasks_with_a_turn_pending_or_running`) instead of the status. That modifies
>   `agent-flows` and the firing code, and no round has examined it. It cannot be built tonight
>   without breaking the round discipline.
> - **(c) Compensate on the flow path.** A refused dispatch of a flow-staffed review returns the task
>   to `completed`. That needs an `under_review -> completed` edge the lifecycle does not declare,
>   and it leaves two transition rows, which the verdict's *"no … transition row survives"* forbids.
> - **(d) Declare the flow's state acceptable (R1's reading).** Then the main requirement's
>   *"every path"* and *"never delivered"* clauses must be MODIFIED to exempt flows, and the
>   in-flight window and the *"let the review in flight finish"* refusal stay.
>
> **Why (a).** It is the only option that ships tonight without skipping rounds. It records the
> verdict's intent as an open finding, F327, instead of defining it away.
>
> **R3's evidence on the question (added by R3, `design.md` D13).**
> - **(a)'s claim was false as R2 left it, and R3 made it true.** The delta's scenario *"A refused
>   review does not stop another reviewer being sent"* covered every refused dispatch, flows
>   included. On R2's prototype of the fix, a flow-staffed review refused by B1 or B2 still answers
>   a different reviewer `409` *"already under review by 'critic'"* (measured). So the delta
>   contradicted its own product. That scenario now covers a dispatch that found the task awaiting
>   review. The requirement says it governs what the dispatch itself records, and does not decide
>   the flow's earlier record.
> - **The fix leaves no new stuck state on the flow path (measured).** Every row of F327's table
>   is the same on the prototype as on the unmodified tree.
> - **(b) is not smaller than R2 says (read, inferred).** Besides the two firing sites in
>   `scheduler.py` and the pool query, a divergence restaff has a different shape: its task is
>   already `under_review`, so not staging early does not apply, and moving its assignee write into
>   the dispatch meets D9's holder check. (b) needs its own spec loop.
> - **R3 recommends (a).**

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

### What R2 found, and what it changed

R2 started again from the code and from the verdict, measured on `75b11ac`. The scratch is in
`testbed/scratch/r2f319/`, and `design.md` D12 records the re-derivation. **R2 found two defects in
R1's argument, and in both the facts were right.**

- **R1 declared a flow's staged review compliant, and wrote that into the delta.** The added
  requirement's last paragraph said a refused dispatch leaves a flow's staging *"as that commit
  left them"*, and that the flow names the review. R2 drove the flow path (F327). The staging does
  survive, which R1 said. But the flow calls the task *in flight* until the input is given up, and
  a different reviewer is refused *"let the review in flight finish"*. And the main requirement
  that the delta sits beside says staffing holds *"for every path"*, and that *"a request that is
  never delivered leaves no task held by a reviewer that never ran"*. So the delta added a
  paragraph that contradicts a main requirement left standing. **R2 removed the paragraph, filed
  F327, and raised the operator question above.**
- **R1's reason for stopping the loop is F114, and the loop reaches F114 anyway.** R1 went on only
  after giving up, so that one pass could not spend an input's three attempts. But input rides in
  another input's turn. **Measured** against R1's own prototype, with a delivery cap of 2: a plain
  message at 0 attempts rode in `[H1, M]`, then in `[M, H6]`, then went alone as `[M]`. It was
  counted three times and withdrawn, all in one pass. The added requirement's first line said the
  rule held *"so that no input's allowance is spent on the way"*, which is not true. **R2 added one
  rule.** A pass counts an input at most once, however many of its attempts carry it, which is
  what a pass that does not go on already does. The input is still attempted each time. Measured
  with that rule, M ends at 1 attempt in every shape (D4, tasks 3.1a and 1.6(f), mutation 4.10, and
  one new scenario).

**What R2 changed in the plan.**
- An xfail marks a whole test and never one assertion, so each leg that mixed a pin with an xfail
  is now two tests.
- 1.8 scans with `ast`, because a text search misses an aliased import or a `partial`.
- 1.8a pins that a refused review does not close an open divergence.
- 4.4 is narrowed to one re-read.
- 6.3 now blocks approval on the operator question.

**What R2 attacked, and what held.** Each item says whether it was run or read.
- **Nothing escapes the rollback except one broadcast.**
  - Read: no commit inside the dispatch before a refusal.
  - Read: no `TriggerAgentError` after the `Run` commit at `agent_trigger.py:1235`.
  - Read: an unexpected exception already discards the staging, because the session closes without
    a commit.
  - The one exception is `run_divergence_resolved`. Its reach is read: a divergence opens on a run
    that ends without moving its task, whatever the task's status. It surfaces as a live activity
    line (`eventSummary.ts:142`) saying a divergence was resolved when it is still open. That is an
    accepted residual (D8), which task 1.8a pins and task 8.5 files.
- **D5, run.** The route, queued behind a head it gives up on, answers `queued` today and `running`
  with the loop. A job firing's run is `failed` today with the head's reason, and `in_progress` with
  the loop.
- **Leg F's premise, run.** `/continue` counts an attempt for a request-level refusal: 1, 2, then
  withdrawn at 3.
- **The loop ends, read.** A transient refusal stops the pass. Every repetition follows a withdrawal,
  so the loop cannot busy-loop.
- **The re-drain alternative, inferred.** It deadlocks, because `asyncio.Lock` is not reentrant.
- **The one caller, read.** `trigger_agent_directly` has one caller.
- **D9, read.** The delta stays ADDED, and with the flow paragraph removed it contradicts no main
  scenario.

### What R3 found, and what it changed

R3 started again from the code and the verdict, on `895aad9`. The scratch is in
`testbed/scratch/r3f319/`, and `design.md` D13 records the re-derivation. R3 reached R1's and R2's
mechanism independently: the rollback first, then going on only after giving up, with one count
per pass. **It found six defects in the text around that mechanism, and one gap in it.**

- **The D9 scenario reached flows (measured).** On R2's prototype, a flow-staffed review refused by
  B1 or B2 still refuses a different reviewer as *"already under review"*. The scenario promised
  the opposite for every refused dispatch. It is now scoped to a dispatch that found the task
  awaiting review, and the requirement says the flow's earlier record is not decided here (F327).
  This is what makes option (a)'s claim true.
- **R2's once-per-pass rule added a stop case the stop list did not name (measured).** A pass that
  gives up on H1 and is then refused on the rider M alone stops, and N, in another conversation,
  waits. That is not F320, because M was not given up on. But the first scenario promised N's
  delivery. It now requires that nothing rode with the given-up input and that the next turn is not
  refused. The stop list names the case, and task 1.6(g) pins it.
- **Mutation 4.4 named five failures, and three happen (measured).** The other two need the
  captured conversation id to be dropped as well, which is now 4.4c.
- **The `selected` re-read was not load-bearing (measured), and a race sat beside it (F328,
  D).** An entry the operator withdraws while its turn is being dispatched is counted and
  announced as given up by the Hub, on both trees. Task 2.1 now re-reads only rows still `queued`,
  and task 1.8b pins it. **This is R3's one addition to the mechanism.** Attack it hardest.
- **Mutation 4.5's reason could not happen once 3.1a exists.** It is reworded: the guard is what
  fails.
- **The request-answer sentence promised more than D5 builds (read).** It now says the answer comes
  from the attempt that ended the pass.
- **1.8a's fixture now has a recipe built through the product (measured).** R2's reach was right:
  the prototype keeps the divergence open, and the broadcast still escapes.

**What R3 attacked and found standing:** D1's rollback and its placement; D8's residual, measured
against *"the operator is told"*; the rollback's expired-attribute hazards; the flow path, which is
not made worse (measured); D5's route behaviour; the drive plan; and file isolation. Tasks number
52, up from 50 (1.8b and 8.5a). The scenario counts are unchanged, at 8 and 7.

## What the pre-approval review found, and what it changed

An adversarial Opus review ran after R3, as the operator requires before any approval. Its
verdict was **approve with repairs, all doc-only.**

**Measured on R3's prototype, and standing:**
- All five F319 legs leave the task as it was, through both the route and the scheduler.
- Nothing inside the dispatch commits before a refusal: zero commits by any session, across all
  five legs.
- A second refusal in the same pass does not undo the first give-up.
- Leg A closes, and the §3.4 guard still refuses with its own sentence.
- The 57-file path suite gave 1 failed, 747 passed. The one failure is D6's.

**The false claim.** The `state == "queued"` re-read **narrows F328, and does not retire it.** A
review dispatch holds the database write lock while it records the reviewer. The operator's
withdrawal waits on that lock and commits after the re-read, so the filter never sees it (test O2,
measured identical on both trees). R3's leg WD and task 1.8b use a mock trigger that takes no lock,
which is why they pass. The filter stays, because it is harmless and catches the earlier window.
F328 stays open, with its durable fix named in D3. Task 8.5a is rewritten accordingly.

**Smaller repairs:**
- The stop list in the `agent-conversation-workspace` delta and in D4 now names the case the filter
  creates: every input the attempt carried was withdrawn during the dispatch.
- D5 records a residual. A later attempt of the loop can start input that another request has just
  queued, and that request is answered `queued` while its input runs.
- Task 7.4's must-be-unchanged diff now covers `task_transition_service.py`, `scheduler.py` and
  `run_divergence.py`.
- Task 5.5 matches the model with `LIKE 'claude-haiku-4-5%'`.
- The operator-question banner is marked answered.

## What Changes

- **`turn_scheduler.schedule_agent`, refusal branch.** On `TriggerAgentError`, first
  `await db.rollback()`. Then re-read the selected entries by the ids captured before the call,
  taking only those still `queued` (R3; this narrows F328 and does not retire it, see the
  pre-approval review above), and re-read the agent's queued entries. Use the conversation id captured before the call. Then record
  `waiting_reason`, count and abandon, and emit exactly as today. A rollback expires every loaded row.
  Without the re-read, five tests of the workspace-counting branch fail with `MissingGreenlet`
  (measured, D3).
- **`schedule_agent` goes on after giving up.** The body becomes one attempt. `schedule_agent`
  repeats it under the same lock and session **only while the previous attempt gave up on at least
  one entry**. Anything else ends the pass as today: a turn started, a transient or agent-wide
  refusal, an attempt counted without being given up on, or an early return. Each repetition follows
  at least one entry leaving the queue, and an entry that arrives meanwhile has no attempts, so it
  cannot be given up on in its first attempt. That bounds the loop (D4).
- **One pass counts an input at most once (R2).** Input that rode in the turn that was given up
  on can be carried again by the next attempt. It is attempted again, and its count is not raised
  again in that pass. Without this, one pass can give up on input no pass had refused before (D4,
  measured).
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
- **The flow's own staging, pending the operator question above.** `_do_fire_job`
  (`scheduler.py:2794`, committed at `:2891`), `_fire_additional_selection` (`:3156`) and a
  divergence restaff (`run_divergence.py:458`) record their reviewer **before** the dispatch, in a
  commit of their own, as `agent-flows` requires. The rollback cannot reach that commit. R2
  measured what it leaves: F327, the same end state as F319, reported late. Under option (a) it is
  **not** fixed here, and this proposal does **not** claim that it meets the verdict (D7).
- **Timers.** No tick is introduced. F320 is closed inside the pass that gives up.
- **The review checkout left by a refusal raised after provisioning.** Measured: leg T leaves
  `.agentweave/reviews/<reviewer>` registered. Filed as **F326 (D)**, and out of this verdict (D8).
- **The `run_divergence_resolved` broadcast a refused staging already sent (R2).** The rollback
  keeps the divergence open, which is the truth. The live activity line that announced it resolved
  cannot be recalled. This is accepted, pinned by task 1.8a, and filed at close-out by §8.5 (D8).
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
  it"* (7 scenarios, one of them R2's *"Going on never counts one input twice in a pass"*).

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
- **Findings:** closes F319 and F320 when built and driven. It **narrows** F328 (D, R3) with task
  2.1's filter and does not close it. F326 (D, R1), F327 (B, R2; out of scope by the operator's
  answer, option (a)) and F328 stay open.
