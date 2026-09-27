# Design — a loop is stopped, archived and delegated from its own tab

## Operator review, 2026-09-24

The Opus adversarial review found that the change approved rewording an ended loop's ending. It
also found three smaller gaps. The operator decided each one as follows:

- **A stop sent for a loop that has already ended is refused (operator decision).** Today
  `end_loop` overwrites `stop_reason` and `stopped_at` without checking (`hub/hub/loop_ending.py:55-56`).
  Only `ending_state` is guarded (`:57-58`). So a second `PATCH {stop_reason}` rewrote the reason
  and time of a loop that had completed or stopped an hour earlier. The change approved that: its
  ADDED requirement said such a call "SHALL NOT record a second stop", test 1.3 was a control that
  passed the rewording, and `end_loop`'s docstring describes "the operator editing the prose after
  the fact". Now the route answers **409** with *"this loop already ended (<reason>) at <time>; …"*
  and leaves `ending_state`, `stop_reason` and `stopped_at` untouched. `end_loop` itself becomes
  write-once for every caller. The tab re-reads on settle, so it shows the real ending. New design
  D2a. The ADDED requirement's sentence and scenario were rewritten, test 1.3 was rewritten as a
  failing test, and tests 1.3a, 1.3b (archive of an ended loop's job still works) and 1.3c
  (`end_loop` itself) were added. Two existing tests that pin the rewording are
  rewritten (task 2.1b). No main-spec SHALL permits rewording, so no MODIFIED delta is needed (D2a).
- **The hooks get their own test (1.14).** Tests 1.5-1.10 mock `@/api/loops` wholesale, so nothing
  checked each hook's method, URL, body keys, or that invalidation runs on an **error** (`onSettled`,
  not `onSuccess`). That last point is the one the refusal above depends on.
- **A blank reason falls back to the default.** The UI trims the reason. An empty or whitespace-only
  reason sends `Stopped by the operator`. Added to test 1.6 (D4).
- **Noted, not fixed:** `PATCH {stop_reason, enabled: true}` ends the loop and then re-enables its
  job. Delegating to an archived agent is accepted and has no effect. Both are under *Residuals*. The
  second one's toggle is hidden in the tab, because hiding it is small (D4, tasks 1.10a and 2.4a).

**Built on the recommended answer to D6 for F225: build.** If the operator answers *delete* instead,
this change is withdrawn. The replacement would be a smaller one: remove `POST /loops/{id}/archive`
and `POST /loops/{id}/control`, and REMOVE the *"may be delegated"* half of `agent-loops`' *"A loop
has a controller…"* requirement (`openspec/specs/agent-loops/spec.md:339-365`) along with the loop
half of *"A loop and a job are archivable"* (`:483-506`). R1 argues against that below (D0).

**Also built on the recommended answer to the interaction.** `archive_job` keeps retiring a running
loop, with no refusal (D1). If the operator wants the refusal back, add a MODIFIED delta for
*"A loop that is still running cannot be archived"* that removes the scenario *"Archiving a job
retires its loop"* (`:534-540`), and make `archive_job` refuse a job whose loop has
`ending_state IS NULL`. Nothing else here changes.

## D0 — build, not delete

| | Build (recommended) | Delete |
|---|---|---|
| What the operator gets | Stop, Archive and delegation, in the tab that already describes all three | Only the job's Pause/Archive on the Jobs page |
| Spec | Two ADDED requirements. Nothing removed | Removes delegation (D10 of `2026-08-18-a-loop-writes-its-own-queue`) and loop archival from the main spec |
| Backend | One event write in `update_job` | Two routes and their tests go; `Loop.control` becomes a column only an agent path reads (`tasks.py:701`) |
| Screens | `LoopTab.tsx:242`'s *"runs until stopped by the operator"* becomes true | That sentence and *Show archived* (`LoopsIndexTab.tsx:141-152`) must be reworded or removed |
| Ratchet | Clientless routes 35 → 33 | 35 → 33 as well, by deletion |

Deleting takes away a governance capability that the spec wrote on purpose. `agent-loops:344-350`
says the operator *"SHALL be able to delegate control … and to take it back"*. It keeps the code that
reads it (`_authorize_loop_task_creation`, `tasks.py:701-703`). The only thing missing is a button.
Building costs one small UI section and three hooks, and it removes a barrier. Deleting leaves a loop
the operator can only end by archiving its job, which is the case D1 is about. The operator's
direction is "barriers are the enemy" and "cleanest solution wins". Both point to building.

## D1 — once Stop ships, `archive_job` still does not refuse a running loop

The refusal was withdrawn on 2026-09-23 for one reason, and it named the condition for revisiting
it: *"Revisit only if a stop control ships"* (`jobs.py:1238-1242`). This change ships the control, so
the question is asked again. The answer is still no:

1. **The refusal protects nothing that is not already protected.** It existed for D17: *"archiving
   can never conceal work that is still firing"*. Since F224, `archive_job` ends the loop in the same
   transaction (`jobs.py:1279-1285`, `end_loop(..., reason=ARCHIVED_WITH_JOB_REASON)`). The job is
   disabled and unregistered (`_hand_job_to_scheduler`, `:1293`), and it can never be re-enabled
   (F222, `update_job` `:927-928`). Nothing is still firing, and the record says how the loop ended.
2. **The main spec already says no refusal.** `agent-loops:534-540`, *"Archiving a job retires its
   loop"*: *"the operator is not required to stop it first"*. A refusal would have to remove that
   scenario, which was written after the 2026-08-21 measurement of the three-step workaround
   (`:517-519`).
3. **A refusal adds a step and no information.** With Stop shipped, the refusal would turn one
   action into two (Stop, then Archive) and learn nothing the first action did not already record.

So IMPL changes one thing: `archive_job`'s docstring. The sentence *"Revisit only if a stop control
ships"* becomes a note that it was revisited when `LoopTab` gained Stop, and the answer stood, for
reasons 1 and 2.

**How D1 and D0 fit together.** D0 builds a stop control. D1 says that control does not bring the
refusal back. `ROUNDS.md` item 3 made the refusal conditional on a stop control shipping, so both
answers are needed to settle it.

## D2 — the Stop control uses the existing operator stop, not a new route

`update_job` already treats `stop_reason` as *"an operator stop"* and ends the loop with `end_loop`
(`jobs.py:1068-1076`, B2.5/D17). A `POST /loops/{id}/stop` would be a second route to the same
function. `LoopDetail` carries `job_id` (`loops.ts` `LoopDetail.job_id`), so the tab can call the
job route directly. **Rejected:** a new route under `/loops`, which would look tidier but duplicate
an existing write path.

**The UI always sends a non-empty reason.** The default is `Stopped by the operator`, and the
operator may replace it. The UI sends `reason.trim()`. If that is empty (the operator cleared the
field, or typed only spaces), it sends the default instead (operator review, test 1.6). The Hub
would otherwise record an ending whose reason is blank, and the badge and refusals quote that
reason. `end_loop` records `ending_state="completed"` when the reason equals
`QUEUE_DRAINED_REASON` (`loop_ending.py:32`, `:57-58`), so an operator who typed exactly
`loop queue is empty` would record a completion. The UI does not produce that string itself.

**R2 decided: pin it. An operator stop always records `stopped`.** This is not a new rule. The main
spec already requires it: `agent-loops` *"How a loop ended is a distinct value, not only a written
reason"* says completing SHALL be distinguishable from stopping *"without interpreting prose"*, and
its scenario counts *"another stopped by the operator"* as a stop. `end_loop` deriving the value
from the reason's text is exactly that interpretation. Today it is out of reach, because no UI
writes `stop_reason`. This change adds a free-text reason field, so it becomes reachable, and an
agent with the job allowance can already send it (`_require_agent_job_allowance` admits a PATCH
from a run).

How: `end_loop` gains a required keyword `completed: bool` and stops comparing `reason` to
`QUEUE_DRAINED_REASON`. The comparison moves to the one caller that produced that string: the
scheduler passes `completed=(loop_stop_reason == QUEUE_DRAINED_REASON)` (`scheduler.py:3156`).
`update_job` (`jobs.py:1075`) and `archive_job` (`:1284`) pass `completed=False`. A required keyword,
not a default, so a fourth caller must say which it is. There are no direct `end_loop` calls in
`hub/tests/` (grep). The rule *"`ending_state` is written only if nothing recorded one already"*
stays, and D2a widens it to all three facts. Task 1.11 pins it.

## D2a — a stop for a loop that has already ended is refused, and an ending is written once

**Operator decision, 2026-09-24, after the Opus review.** An ending is a governance fact. Once a
loop has one, nothing rewrites how, why or when it ended.

**Today.** `end_loop` writes `loop.stop_reason` and `loop.stopped_at` unconditionally
(`loop_ending.py:55-56`). Only `ending_state` is guarded (`:57-58`), and its docstring defends this
as *"the operator editing the prose after the fact"* (`:48-50`). `update_job` reaches it for any
`stop_reason` (`jobs.py:1068-1076`). Two existing tests pin the rewording:
`test_an_operator_stop_actually_stops.py:123-143` (asserts `stop_reason == "actually, it finished"`
after a second PATCH), and `test_loop_archival.py:428-435` (a second PATCH answered 200).

**Where the check lives: both, for different reasons.**

1. **The route refuses, and it says so.** In `update_job`'s loop block, right after the loop is
   resolved (`jobs.py:998-1000`) and before anything is mutated (the `spec_document_id` claim at
   `:1017-1027` and the staged definition edit at `:1041-1066` come later):
   `if body.stop_reason is not None and loop_already_existed and loop.ending_state is not None:`
   raise **409**. The detail has the same shape as F13's refusal a few lines above
   (`jobs.py:948-964`):
   `{"message": f"this loop already ended ({loop.stop_reason or loop.ending_state}) at {when}; its
   record is left as it was", "code": "loop_already_ended", "loop_id", "ending_state",
   "stop_reason", "stopped_at"}`. `{when}` falls back to `"an unknown time"` as F13's does. The
   whole PATCH is refused, including any other field sent with it. That matches F13, and it avoids
   half-applying a request whose stop was refused.
2. **`end_loop` becomes write-once, silently.** When `loop.ending_state is not None`, it clears
   `job.enabled` (unchanged, and it is already `False` for an ended loop) and returns without
   touching `stop_reason`, `stopped_at` or `ending_state`. It returns a `bool`: `True` if this call
   recorded the ending. This guards the two other callers without changing what they return.
   `end_loop` is the only writer of the three fields in `hub/hub`
   (`grep -rn "\.stop_reason = \|\.stopped_at = \|\.ending_state = " hub/hub` finds only
   `loop_ending.py:55-58`), so the requirement's *"no caller SHALL change how, why or when a loop
   ended"* holds by construction once this guard is in.
   - `archive_job` (`jobs.py:1279-1285`) already calls `end_loop` only when `ending_state is None`.
     **Archiving an ended loop's job still succeeds.** It sets `loop.archived_at` (`:1285`) and
     writes `loop_archived` (D3a). Test 1.3b pins this.
   - The scheduler (`scheduler.py:3149-3156`) calls `end_loop` whenever `_loop_stop_reason` returns
     a reason. `_loop_stop_reason` does not look at `ending_state` (`scheduler.py:378-418`). So a
     manual firing of an ended loop's job could today overwrite the first ending with
     `loop stop time reached …`. With the guard, the firing is still skipped (`run.status =
     "skipped"`, `:3151`), and the first ending stands. The scheduler's own ending of a running loop
     is unchanged. Test 1.3c pins the guard directly.

**What the route returns.** 409 with the structured detail. `readableApiError` returns its
`message` (`hub/ui/src/api/client.ts:88-91`), so the tab's alert line reads *"this loop already
ended (loop queue is empty) at 2026-…; its record is left as it was"*. This is not a 500: the check
raises `HTTPException` before any write, and `get_session` closes the session without committing
(`db/engine.py:166-169`). In the tab, the only way to send it is a race: Stop is shown only while
`ending_state == null` (D4), and another tab or a firing ends the loop first. `onSettled` then
re-reads the loop, so Stop disappears and the badge shows the real ending.

**Consequence for D3.** In `update_job`, every call that reaches `end_loop` is ending a running
loop, so `ended_now` there is always true. The `loop_stopped` row is written whenever the stop
branch runs. Tasks keep the `ended_now` capture only in `archive_job`, or they use `end_loop`'s
return value.

**No MODIFIED delta.** No requirement in `openspec/specs/` permits rewording an ended loop's
reason. `grep -n "reason" openspec/specs/agent-loops/spec.md` shows the stop requirements
(`:107-145`, `:425-444`, `:446-464`, `:548-563`), and each describes recording an ending, never
editing one. The rewording existed only in `end_loop`'s docstring and the two tests above. The
change's own ADDED requirement carries the new rule.

## D3 — the operator stop writes its own `loop_stopped` event, in the same transaction

In `update_job`, the stop branch runs only for a loop that has not ended, because D2a's 409 comes
first. So whenever it calls `end_loop`, persist the event with `commit=False`, before the
`session.commit()` at `jobs.py:1145` (asserting `end_loop`'s `True` return is enough; there is no
case to branch on):

```python
await persist_event(session, project_id, "loop_stopped",
                    {"job_id": job.id, "loop_id": loop.id, "reason": body.stop_reason},
                    agent=agent_identity, loop_id=loop.id, commit=False)
```

Then broadcast `loop_stopped` with the same payload after the commit. The payload keys match the
firing path's (`scheduler.py:3176-3180`), so `useSSE.ts:544-556` already routes it: it reads
`loop_id` and invalidates `['project', pid, 'loops', loopId]`. `agent=agent_identity` is `None` for
the operator, which is how every operator loop event is recorded (`loops.py:185`, `:223-229`).

**Why in the transaction.** Most routes here commit and then call `persist_event`. If that write
raises, the route returns 500 after the loop has already ended. The operator is then told the stop
failed while it succeeded, and the loop has no record of it. Writing the event inside the
transaction removes both halves: if the event cannot be written, nothing is written. This is
`persist_event`'s own `commit=False` contract (`hub/hub/utils.py`, *"for a caller that is itself
called from inside another function's uncommitted transaction"*).

**What each route returns when what it calls raises:**

- `PATCH /jobs/{id}` with `stop_reason` on a loop that has already ended: **409** with D2a's
  structured detail, and nothing written.
- `PATCH /jobs/{id}` with `stop_reason` on a running loop: `end_loop` only assigns, so it cannot raise.
  `persist_event(commit=False)` only calls `session.add`, so in practice the commit is what fails.
  If either raises, the route returns 500 with nothing changed: `get_session` closes the session
  without committing (`db/engine.py:166-169`).
  The hook's `onSettled` invalidation re-reads the loop, which still shows it running, so the view
  matches the truth. If the broadcast raises after the commit, the route returns 500 while the stop
  landed. That is the existing shape of every broadcast in this file. The same invalidation makes
  the tab show the stopped loop, so the view is still correct.
- `POST /loops/{id}/archive` and `/control`: see D3b. After it, a failed event write or commit
  returns 500 with nothing changed, and a failed broadcast returns 500 after the change landed. In
  both cases the `onSettled` invalidation re-reads the truth.
- `POST /jobs/{id}/archive`: see D3a. Same shape as the stop.

**Every event row these four functions write moves into the transaction, and B9's guard decides
how their frames are sent (R3).** B9's `an-event-is-announced-only-once-its-write-is-committed` is
now final (R3 read its design D4 and tasks 1.6, 1.6b and 2.4b at `6c38a61`). Its `ast` guard has
two rules:

1. A function that calls `persist_event(..., commit=False)` must not call `sse_manager.broadcast`
   or `.publish` anywhere in its body, even after its commit. It must use
   `defer_broadcast(session, project_id, kind, payload)`.
2. In a function that calls `defer_broadcast` and awaits a `.commit()` of its own, every
   `defer_broadcast` must come before that function's **last own** `.commit()` in source order. A
   commit hidden in a callee (`persist_event(commit=True)`, `_hand_job_to_scheduler`) does not
   count. A defer left where today's post-commit broadcast sits is never published: the listener
   fires on the commit, and `get_session` then closes the session without another one.

So that either landing order is mechanical, this change moves **every** event row of the four
functions into the transaction, not only the new ones. That includes `update_job`'s
`loop_edit_staged` (today it is `commit=True` after the commit, `jobs.py:1147-1160`) and
`archive_job`'s `job_archived` (today it comes after the commit and after its broadcast,
`:1290-1291`). If one stayed after the commit, a frame deferred to the main commit would go out
before its row existed. A reader refetching the loop on that frame would miss the row, which is the
shape B9 forbids. Each function then has exactly one commit of its own: `update_job` `:1145`,
`archive_job` `:1287`, `archive_loop` `loops.py:182`, `set_loop_control` `:217`. Every row and every
announcement goes above it. The frame order is fixed here, so neither lander has to choose one:

| Function | Rows staged before the commit (`commit=False`) | Frames, in this order |
|---|---|---|
| `update_job` | `loop_edit_staged` (if staged), `loop_stopped` (if `stop_reason` given; D2a refused an ended loop already) | `loop_edit_staged`, `loop_stopped`, `job_updated {id, enabled}` |
| `archive_job` | `job_archived`, `loop_stopped` (if `ended_now`), `loop_archived` (if it has a loop) | `job_archived`, `loop_stopped`, `loop_archived` |
| `archive_loop` | `loop_archived` | `loop_archived` |
| `set_loop_control` | `loop_control_changed` | `loop_control_changed` |

- **If B9 has not landed:** each frame is an `await sse_manager.broadcast(...)` after the function's
  commit, in the table's order, where today's broadcasts sit. B9's rule 1 then flags all four
  functions. B9's task 2.4b converts each one to a `defer_broadcast` above the commit, in the same
  order, and moves the spies. Nothing else in B9 changes.
- **If B9 has landed:** each frame is a `defer_broadcast(session, project_id, kind, payload)`
  **above** the function's own `session.commit()`, in the table's order. Payloads are built from
  values known before the commit: `job.enabled` is final by then, and `set_loop_control`'s
  `new_value` is `loop.control or "operator"` after the assignment. Tests that spy on these frames
  (1.2) spy on `SSEManager.publish`, not `broadcast`. Run B9's
  `test_no_staged_event_is_broadcast_before_commit` and
  `test_no_announcement_is_deferred_after_the_last_commit`.

The wire effect is the same either way: every frame follows the commit of the row it reports. The
one visible difference with B9 is that `job_updated` and `job_archived` go out a few milliseconds
before `_hand_job_to_scheduler` registers or unregisters the job. That function writes nothing to
the database, because the store is in memory (F351). A reader that refetches on the frame reads the
same rows.

## D3a — archiving a running loop's job is an operator stop too, and is recorded as one

R2 found the same gap on the other operator path. `archive_job` ends a running loop through
`end_loop(..., reason=ARCHIVED_WITH_JOB_REASON)` (`jobs.py:1279-1285`). It writes only
`job_archived` with `{"id": job_id}` and no `loop_id` (`:1290-1291`). So the loop's own history
(`GET /loops/{id}` reads `EventLog.loop_id == loop.id`, `loops.py:76-80`) shows neither the stop nor
the archival. `job_archived` is also not one of the cases `useSSE` handles, so an open loop tab stays
stale. The requirement this change ADDs, *"a stop the operator makes"*, would be false on this path
if it were left alone.

So `archive_job`, in the same transaction:
- writes `loop_stopped` `{job_id, loop_id, reason: ARCHIVED_WITH_JOB_REASON}` when it ended the loop
  (`ending_state` was `None`);
- writes `loop_archived` `{"id": loop.id}` with `loop_id=loop.id` whenever the job has a loop. That
  is the same payload `archive_loop` writes.

Both are broadcast after the commit, so `useSSE.ts:544-556` invalidates the loop views. Human-only
step 6 of the test guide then shows it in the loop's history as well as in its badge. Task 1.12.

## D3b — `archive_loop` and `set_loop_control` move their events into the transaction

**R2 decided: yes.** Today each route commits, broadcasts, and then commits the event separately
(`loops.py:180-185`, `:217-229`). A failed event write answers 500 for a change that landed, and it
leaves the change with no history row. That breaks `agent-loops` *"A loop has a controller…"*
(*"Each change of control SHALL be recorded against the loop"*). This change is what makes these two
routes reachable for the first time. The fix is the same two moved lines as D3:
`persist_event(..., commit=False)` before `session.commit()`, then the broadcast. Task 1.13.

## D4 — what the tab shows, and when

Visibility comes from the tab's own row (`useLoop`), using the same `endingBucket` helper as the
badge (`loopCounts.ts`). The badge and the controls cannot disagree:

| Loop state | Stop | Archive | Controller line |
|---|---|---|---|
| not ended (`ending_state == null`), not archived | shown | hidden | shown, with a toggle |
| ended, not archived | hidden | shown | hidden |
| archived | hidden | hidden | hidden |

- **The controller line** reads *"Additions to this queue are decided by you"* with the button
  *"Let {agent} decide"* when `control` is null, and *"… by {agent}"* with the button *"Decide them
  yourself"* when `control == "creator"`. `{agent}` is `loop.agent`, the job's agent. D8 of the loop
  change makes that agent the loop's creator for this purpose (`tasks.py:611-613`). If `loop.agent`
  is empty (`loops.ts` says that can happen), the toggle is hidden, because a delegation would go to
  nobody. **It is also hidden when `loop.agent` is an archived agent** (operator review). The Hub
  accepts that delegation, but it does nothing: `_authorize_loop_task_creation` refuses an archived
  creator before it reads `control` (`tasks.py:694-701`). The tab reads `useAgents('archived')`
  (`hub/ui/src/api/agents.ts:180`, key `['project', pid, 'agents', 'archived']`) and hides the
  toggle when that list names `loop.agent`. It checks the archived list, not "absent from the open
  list", because a name with no `Agent` row at all is still allowed to decide (`tasks.py:688-693`),
  and hiding the toggle for it would be wrong. While the list is loading, the toggle shows, as
  today. The controller line itself still shows.
- **Stop confirmation** is inline and two-step, the way `JobCard.tsx:499-515` confirms Archive, not a
  modal. The confirmation carries the reason field and one sentence. When `firing_active` is true:
  *"The firing running now finishes; no firing starts after it."* When it is false: *"No firing starts
  after this."*
- **Failures** go in a `role="alert"` line built with `readableApiError(error, fallback)`
  (`hub/ui/src/api/client.ts:74`), the shared helper that extracts the Hub's `detail` sentence,
  including from a structured `{message, code}` detail. Each action has its own fallback, e.g.
  *"Could not stop this loop."* Do not add a third local `errorDetail` copy
  (`JobsPage.tsx:18` and `AgentCreateDialog.tsx:10` already have one each).
  **What the operator reads, per failure (R3).** A refusal is JSON, so its sentence is shown:
  *"loop is already archived"*, *"this loop is still running; it must stop or complete before it
  can be archived"* (a race with another tab), *"this loop already ended (<reason>) at <time>; its
  record is left as it was"* (a Stop that lost a race with another tab or a firing, D2a), *"Job not found"* / *"Loop not found"*, or, for a
  reason over 4000 characters, the 422 rendered as *"String should have at most 4000 characters"*
  (the field name is dropped because the message starts with a capital, `client.ts:103`). An unhandled exception's 500 has a plain-text body, so `readableApiError` shows that
  body (*"Internal Server Error"*), not the fallback. The fallback appears only when no response
  arrived (a network error). In every case `onSettled` re-reads the loop, so the controls then
  match what the Hub recorded. That includes the one misleading case, a broadcast that raised
  after the commit, where the line says the call failed while the tab shows the loop stopped.
  `readableRefusal` was considered and rejected: it would turn that same case into *"Could not stop
  this loop."* beside a stopped loop.
- **Why a new stop hook rather than `useUpdateJob`** (`api/jobs.ts:207`, which has no component
  caller today): that hook invalidates only `jobs`, and the tab reads `loops`. A dedicated
  `useStopLoop` keeps the invalidation next to the one reader it serves.

## D5 — the ratchet

`CLIENTLESS_ROUTE_CEILING` goes from 35 to 33 in the same commit as the hooks. Both routes match by
URL literal (`n10` step 2), for example
`` `/api/v1/projects/${projectId}/loops/${loopId}/control` ``. `PATCH /jobs/{job_id}` was already
reached (`usePauseJob`). The ratchet's own warning (`test_surface_ceilings.py:_ratchet`) asks for
the new floor.

## Residuals, stated

- **`PATCH {stop_reason, enabled: true}` ends the loop and then re-enables its job (operator
  review, noted not fixed).** F13's re-enable refusal checks `not job.enabled` before the stop runs
  (`jobs.py:940-943`), so it does not fire for a running loop. `end_loop` then clears `enabled`
  (stop branch, `:1068-1076`), and `if body.enabled is not None: job.enabled = body.enabled`
  (`:1139-1141`) sets it back. The result is an ended loop whose job is enabled and registered. The
  next firing is skipped by `_loop_stop_reason` only if a stop condition holds, so it may fire.
  The tab never sends this pair (`useStopLoop` sends `{stop_reason}` only). An agent with the job
  allowance could. This is a candidate finding, not carried here.
- **Delegating to an archived agent is accepted and has no effect (operator review, noted).**
  `POST /loops/{id}/control {"control": "creator"}` sets the column regardless, and
  `_authorize_loop_task_creation` refuses the archived creator before reading it
  (`tasks.py:699-700`). The tab hides the toggle in that case (D4). The route is left as it is.
- **The scheduler writes `loop_stopped` even when `end_loop` recorded nothing.** A manual firing of
  an ended loop reaches `end_loop` (`scheduler.py:3149-3156`), which is now a no-op for the loop
  (D2a), and then writes a `loop_stopped` event (`:3179-3185`) naming a reason the loop does not
  record. Before this change it at least matched the rewritten record. Candidate finding: gate that
  event on `end_loop`'s return value. It is not carried here, because the firing path has its own
  owner.

- The `_require_operator` detail says *"only the operator can archive a loop"* for the control
  route too (`loops.py:56`). It cannot be reached today (see its own docstring), so it is left alone.
- The Jobs page `LoopBlock` still reads a stopped loop from `stop_reason` text (`JobCard.tsx:286`)
  rather than from `ending_state`. Not this change's finding.
- **`LoopTab` fetches the loop's history and renders none of it (R3).** `LoopDetail.events`
  (`loops.ts`, *"This loop's own audit trail"*) is read by no component (`grep -rn "\.events"
  hub/ui/src`). The events this change writes are therefore checked through `GET /loops/{id}`, not
  on screen (test guide, human-only steps 2 and 6). This is a candidate finding for the ledger, not
  carried here: the spec asks only that the history be retrievable (`agent-loops` *"A loop's
  history is answerable…"*: *"The Hub SHALL let a caller retrieve…"*).
