# Proposal — a live view that fell behind is told, and catches up

**Round 1, 2026-09-24** (bundle B9, spec track S4). Finding: **F253 (B)**. Re-verified on HEAD
`ce086b6` (= `404c7d5` for every `hub/` file). **Nothing here is implemented yet.** Independent of
the other two B9 changes; if it lands after `an-event-is-announced-only-once-its-write-is-committed`,
the drop counter sits in `SSEManager.publish` rather than `broadcast`.

## Why

Every stream subscriber is an `asyncio.Queue(maxsize=256)` (`hub/hub/sse.py:43`, `:63`). When one is
full, `broadcast` drops the event and says nothing (`sse.py:91-94` for project streams, `:100-103`
for the operator stream: `except asyncio.QueueFull: pass`). Driven (row-16 drive, `00b5dd9`): a
stalled operator-stream subscriber received **1,574 of 3,000** events, twice, deterministically.

Nothing tells the client. The wire carries no `id:`, no sequence number and no gap frame, and the
connection stays open, so the one catch-up the app has — `useSSE.ts:410-414`, which invalidates
every query on `onSseReconnect` — never runs. A tab that lost half the stream looks exactly like a
tab watching a quiet project. 3,000 events is one verbose agent turn (`output_recording.py:104`,
`:121` broadcast per streamed chunk) reaching a backgrounded or throttled tab.

Re-verified: both `except asyncio.QueueFull: pass` blocks are unchanged; both stream generators
(`hub/hub/api/v1/events.py:95-107`, `:144-153`) yield `queue.get()` results and nothing else; the
client's only catch-up hook is `onSseReconnect` (`useSSE.ts:134`), consumed at `useSSE.ts:411` and
`hub/ui/src/api/agents.ts:560`.

## What changes

- Each subscriber counts what it drops. The stream that serves it sends one **`stream_gap`** frame
  (`{"dropped": n}`) as soon as it is sending again, then resets the count.
- The two stream routes share one frame generator (today they are two copies of the same loop), so
  the gap is written once.
- The app treats a gap as it treats a reconnect: every query is invalidated, and the agent-output
  reconciliation poll runs. The Activity feed shows one line saying events were not delivered and
  the views were refreshed.
- A gap is **not a project's event**: it carries no `project_id`, because the events lost may belong
  to any project. The feed shows it whatever project is selected.

## What does not change

- The queue depth (256) and the choice to drop rather than block a slow consumer (the comment at
  `sse.py:88-90` is right about that).
- No replay: the Hub still keeps no event IDs; the client refetches state instead (design D1).

## Impact

- `hub/hub/sse.py`, `hub/hub/api/v1/events.py`, `hub/ui/src/hooks/useSSE.ts`,
  `hub/ui/src/components/activity/ActivityLog.tsx`, `hub/ui/src/lib/eventSummary.ts`, tests, and the
  committed UI bundle (`hub/hub/static/ui`, refreshed with `scripts/refresh_ui_bundle.py`).
- Spec: `local-project-workspace` gains *"A stream subscriber that falls behind is told what it lost"*.
