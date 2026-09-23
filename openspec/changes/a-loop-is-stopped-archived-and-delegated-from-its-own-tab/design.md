# Design — a loop is stopped, archived and delegated from its own tab

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
operator may replace it. `end_loop` records `ending_state="completed"` when the reason equals
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
stays. Task 1.11 pins it.

## D3 — the operator stop writes its own `loop_stopped` event, in the same transaction

In `update_job`, capture `ended_now = loop.ending_state is None` before calling `end_loop`. When
`ended_now` is true, persist the event with `commit=False`, before the `session.commit()` at
`jobs.py:1145`:

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

- `PATCH /jobs/{id}` with `stop_reason`: `end_loop` only assigns, so it cannot raise.
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

**The broadcast goes after the commit, never before.** Note for whoever lands second, this change or
B9's `an-event-is-announced-only-once-its-write-is-committed`. That change adds `defer_broadcast`
and an `ast` guard, `test_no_staged_event_is_broadcast_before_commit`. The guard fails any
function that calls `persist_event(..., commit=False)` **and** calls `sse_manager.broadcast`
anywhere in its body, even after the commit. After this change that would flag `update_job`
(its existing `job_updated` and `loop_edit_staged` broadcasts included), `archive_job`,
`archive_loop` and `set_loop_control`.
- If B9 lands first, this change stages each new announcement with `defer_broadcast` and converts
  those four functions' other broadcasts too.
- If this change lands first, B9's IMPL converts them.
Either way the wire order is unchanged: the route's own broadcast still follows the commit. R3
should confirm B9's guard text has not narrowed in the meantime.

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
  nobody.
- **Stop confirmation** is inline and two-step, the way `JobCard.tsx:499-515` confirms Archive, not a
  modal. The confirmation carries the reason field and one sentence. When `firing_active` is true:
  *"The firing running now finishes; no firing starts after it."* When it is false: *"No firing starts
  after this."*
- **Failures** go in a `role="alert"` line built with `readableApiError(error, fallback)`
  (`hub/ui/src/api/client.ts:74`), the shared helper that extracts the Hub's `detail` sentence,
  including from a structured `{message, code}` detail. Each action has its own fallback, e.g.
  *"Could not stop this loop."* Do not add a third local `errorDetail` copy
  (`JobsPage.tsx:18` and `AgentCreateDialog.tsx:10` already have one each).
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

- The `_require_operator` detail says *"only the operator can archive a loop"* for the control
  route too (`loops.py:56`). It cannot be reached today (see its own docstring), so it is left alone.
- The Jobs page `LoopBlock` still reads a stopped loop from `stop_reason` text (`JobCard.tsx:286`)
  rather than from `ending_state`. Not this change's finding.
