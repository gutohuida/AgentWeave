# Proposal — a loop is stopped, archived and delegated from its own tab

**Round 1, 2026-09-24** (bundle B10, decision D6, surface "loop controls"). Finding: **F225 (C)**,
re-verified on HEAD `404c7d5` (worktree `ce086b6`). **Nothing here is implemented yet.**

## Why

A loop has three operator actions, and the app has a control for none of them:

| Action | Route | Client today |
|---|---|---|
| Stop a running loop | `PATCH /jobs/{job_id}` with `stop_reason` (`hub/hub/api/v1/jobs.py:1068-1076`, through `end_loop`) | none. `stop_reason` is read by `JobCard.tsx:286-299` and `LoopTab.tsx:140`, never written |
| Archive an ended loop | `POST /loops/{id}/archive` (`hub/hub/api/v1/loops.py:152-187`) | none |
| Delegate or take back queue control | `POST /loops/{id}/control` (`loops.py:190-231`) | none |

Measured on the worktree: `scripts/drive/n10_route_reachability.py`'s `clientless_routes` still lists
`POST …/loops/{loop_id}/archive` and `POST …/loops/{loop_id}/control` among its **35**, and
`hub/ui/src/api/loops.ts` still exports only `useLoops` and `useLoop`, both `useQuery`.

Three places on screen promise what cannot be done:

- `LoopTab.tsx:242` describes a loop with no stop condition as *"runs until stopped by the
  operator"*. No control stops it.
- `LoopsIndexTab.tsx:141-152` offers *Show archived*. Only archiving a loop's job can archive a loop.
- `LoopSummary.control` is on every loop route (`hub/hub/schemas/jobs.py`, `control`) and rendered
  nowhere, while the loop's timeline can show a `loop_control_changed` event.

The gap also shapes a decision. On 2026-09-23 the operator decided that `archive_job` does not refuse
a running loop: archiving the job ends the loop (F224). A refusal was withdrawn *because no screen can
stop a loop* (`ROUNDS.md` "Read this first" item 3; `jobs.py:1238-1242`). The docstring says to
revisit that if a stop control ships. This change ships one, so it has to answer that question.

A second defect sits in the same path. An operator stop through `PATCH /jobs/{id}` writes no
`loop_stopped` event. A firing's stop does (`scheduler.py:3176-3187`). So the loop's own history
(`GET /loops/{id}` `events`) has no entry for the one stop the operator makes. `agent-loops`' *"A
loop's history is answerable for that loop alone"* requires *"its stop with the reason"*. No
`loop_stopped` broadcast goes out either. `useSSE.ts:522-536` handles `job_updated` by invalidating
only `jobs` queries, so an open loop tab stays stale.

## What changes

1. **The loop tab gets the three actions** (`hub/ui/src/components/spec/LoopTab.tsx`):
   - **Stop**, while the loop has not ended. It asks for confirmation and takes an optional reason.
     It says the firing now running, if any, is not interrupted. It sends
     `PATCH /jobs/{job_id} {stop_reason}`.
   - **Archive**, once the loop has ended and is not archived. It sends `POST /loops/{id}/archive`.
   - **Who decides additions to this queue**: the operator or the loop's agent, with one button to
     delegate or take back. It sends `POST /loops/{id}/control`. Hidden once the loop has ended: an
     ended loop's queue is closed to every caller (`tasks.py:648-677`), so its controller decides
     nothing.
   - Each failure shows the Hub's refusal text, in the way `JobsPage.tsx:47-52` already does.
2. **Three mutation hooks** in `hub/ui/src/api/loops.ts`: `useStopLoop`, `useArchiveLoop` and
   `useSetLoopControl`. Each invalidates `['project', pid, 'loops']` and `['project', pid, 'jobs']`
   on settle (success or failure), so a refusal re-reads the truth instead of keeping a stale view.
3. **An operator stop is recorded like a firing's stop.** `update_job` writes a `loop_stopped` event
   against the loop (reason, `loop_id`, `job_id`, actor) and broadcasts it, **only when this call
   ended the loop**. Editing the reason of a loop that has already ended adds no second stop. The event
   is written in the same transaction as the ending. An operator stop always records
   `ending_state="stopped"`, whatever its reason's text: `end_loop` takes `completed` from its
   caller instead of comparing the reason to `loop queue is empty` (design D2, added by R2).
4. **`archive_job` keeps retiring a running loop, and its docstring says why.** The 2026-09-23
   decision was provisional on "no stop control". It is re-answered here: still no refusal. See
   design D1. **When it ends the loop, it now records that as a `loop_stopped` against the loop,
   and it always records `loop_archived` against the loop.** Today it writes only `job_archived`,
   with no `loop_id`, so the loop's own history misses both (design D3a, added by R2).
5. **`archive_loop` and `set_loop_control` write their events in the change's own transaction**,
   not after it. Today a failed event write returns 500 for a change that landed and has no
   history row (design D3b, added by R2).
6. **The route-reachability ceiling drops from 35 to 33** (`hub/tests/test_surface_ceilings.py`),
   because both loop routes now have a client.

## What does not change

- No route is added, removed or renamed. The Stop control uses the operator stop that exists
  (`update_job`'s B2.5 path).
- `archive_loop` still refuses a loop that has not ended (`agent-loops` *"A loop that is still
  running cannot be archived"*). The tab shows Archive only once the loop has ended.
- `JobCard`'s loop block (`JobCard.tsx:249-330`, `LoopBlock`) gets no controls. The Jobs page already has
  Pause/Resume/Archive for the job. Putting a second Stop there would give two surfaces the same act.

## Impact

- `hub/ui/src/api/loops.ts`, `hub/ui/src/components/spec/LoopTab.tsx`, their tests, and the bundle
  (`hub/hub/static/ui`, with `make ui`).
- `hub/hub/api/v1/jobs.py` (`update_job`'s stop branch; `archive_job`'s loop events and docstring),
  `hub/hub/loop_ending.py` (`end_loop(..., completed=)`), `hub/hub/scheduler.py` (its one
  `end_loop` call), `hub/hub/api/v1/loops.py` (`archive_loop` and `set_loop_control` event order).
- Interacts with B9's `an-event-is-announced-only-once-its-write-is-committed`: whichever lands
  second converts these functions' broadcasts to its `defer_broadcast` (design D3).
- `hub/tests/test_surface_ceilings.py` (ceiling constant).
- Spec: `agent-loops`, two ADDED requirements.
