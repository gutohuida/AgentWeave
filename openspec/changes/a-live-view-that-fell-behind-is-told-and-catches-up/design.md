# Design — a live view that fell behind is told, and catches up

No operator decision is required. D1 records the one real choice with its alternatives, and the
recommendation this change is built on. Built on HEAD `ce086b6`.

## Operator review, 2026-09-24

After the Opus adversarial review; citations re-checked at HEAD `c1c0fa4`. Operator decisions
B9-Q1 (no runtime allowlist; generated type) and B9-Q2 (the F251 bundle waits for `:8000`'s
restart) are confirmed; neither gates this change (see the skew section).

- **Test 1.6's "once" depended on how many hooks were mounted (Opus review).** Every mounted
  `useSSE()` registers its own reconnect listener that calls `queryClient.invalidateQueries()` with
  no arguments (`hub/ui/src/hooks/useSSE.ts:410-414`), so one gap produces one no-argument call
  **per mounted hook**. Test 1.6 (and 1.7) now render exactly one `useSSE()` and say so; the
  assertion is exact only under that condition.
- **Task 2.3b matched to F251's revised D3.** F251 now derives `DISPATCHED_STREAM_FRAMES` (every
  `STREAM_FRAMES` entry except `connected`) and generates from it, so adding `stream_gap` is one
  line in `STREAM_FRAMES` plus a regeneration.
- **Follow-up, not in scope:** moving the invalidate-everything reconnect listener out of the hook
  into one module-level listener would make the catch-up once per event regardless of how many
  hooks are mounted (D4).

## D1 — tell the client with a gap frame (recommended), not a disconnect or a replay

| Option | What it does | What it costs |
|---|---|---|
| **A. Gap frame (chosen)** | Count drops per subscriber; the stream sends `event: stream_gap`, `data: {"dropped": n, "severity": "warn"}` once it is sending again; the client runs its reconnect catch-up. | One new frame kind on the wire and one client branch. The connection survives. |
| B. Close the slow subscriber | On overflow, end that stream; the client reconnects after 3 s (`useSSE.ts:227`) and its existing reconnect hook refetches. | No new frame kind, but a throttled tab reconnects in a loop under load, the 255 queued events are thrown away too, and nothing on screen says anything was lost (the feed does not reload history on reconnect — `ActivityLog.tsx:106-131` fetches only on project change). |
| C. Event IDs and `Last-Event-ID` replay | Number every frame and keep a ring buffer to replay. | A buffer per instance, a replay protocol, and the same overflow question one level down. Out of proportion to a client that can simply refetch. |
| D. Block, or grow the queue | — | Blocking stalls every broadcaster behind the slowest tab; a bigger queue moves the cliff. |

A is what F253 itself proposes (*"One counter on the subscriber and a `stream_gap` frame on the
next successful put"*) with one change: the frame is written by the **stream**, not by the next
`put`. If it were queued by the next broadcast, a burst followed by silence would never deliver it,
and the gap frame would itself compete for a full queue.

## D2 — where the gap is written

`subscribe()` and `subscribe_operator()` return a `SubscriberQueue(asyncio.Queue)` carrying
`dropped: int = 0`, so every existing caller that does `q.get_nowait()` keeps working
(`hub/tests/test_sse.py`, `hub/tests/test_operator_events.py`). The per-subscriber `except
asyncio.QueueFull` becomes `q.dropped += 1`.

A new `async def stream_frames(queue, is_disconnected)` in `hub/hub/sse.py` owns the loop both routes
repeat today (`events.py:95-107`, `:144-153`): yield `make_connected_event()`, then loop: stop when
disconnected, `await queue.get()`, yield it, and **then**, if `queue.dropped`, take the count, reset
it, and yield `make_gap_event(count)`. The routes keep their own `try/finally` unsubscribe.

Why after the yielded message: drops only happen while the queue is full, so by the time the
consumer returns from sending any message after a drop, the count is non-zero and the gap goes out
next. The gap may therefore arrive **before** some events that were queued ahead of the loss. That
is harmless: the client's response to a gap is to refetch everything, which already reflects those
events, and their own invalidations then refetch again. Delivery is what matters, and it is
guaranteed: a full queue means there are 256 messages still to send, so the check runs.

## D3 — a gap is not a project's event

The operator queue is fed by every project (`sse.py:96-103`), so one count mixes projects. The gap
frame carries **no** `project_id`. This does not weaken the rule that every project event carries a
server-stamped `project_id` (`local-project-workspace`, *"One live operator stream identifies every
project event"*): a gap is stream metadata, like `connected`. Its response on the client is
correspondingly instance-wide: `queryClient.invalidateQueries()` with no key, which already covers
every project-prefixed key.

## D4 — what the app does with it

In `useSSE.ts`'s read loop, `stream_gap` is handled **before** the allowlist test at `:337` (so it
works whether or not `every-event-the-hub-sends-reaches-the-app` has landed): parse, `dispatchEvent`
it to the buffer and listeners, then call the reconnect listeners (`fireReconnect`, `:141`). That
reaches both existing catch-ups — the invalidate-everything at `:410-414` and the agent-output
reconciliation poll at `api/agents.ts:560`. `onSseReconnect`'s docstring (`:131-133`) is widened to
*"fires whenever the client may have missed events: after a reconnect, or when the Hub reports a
gap"*; the name stays, since both callers mean exactly that.

**Once per hook, not once per event (Opus review).** The invalidate-everything listener is
registered inside `useSSE()`'s own `useEffect` (`:410-414`), so every mounted instance adds one and
a single `fireReconnect()` invalidates everything once per mounted hook. The app mounts one
(`App.tsx`), so production behaviour is one catch-up; the tests pin it with exactly one hook
mounted. Hoisting that listener to module level (registered once, beside `onSseReconnect` at
`:134`) would make the count independent of mounts; it is a follow-up, not part of this change.

`ActivityLog.tsx:136-146` (the check is at `:139`) drops any live event whose `project_id` is not the selected project's. A
gap passes that filter unconditionally. `summaryForEvent` (`lib/eventSummary.ts`) gains
`stream_gap`: *"The live connection fell behind and {n} events were not delivered. Views were
refreshed; this feed may be missing lines until Activity is reopened."* The feed is not refetched:
live and history rows carry different timestamps (client-stamped at `useSSE.ts:185` versus
server-stamped), so its de-duplication at `ActivityLog.tsx:117-119` would double rows. Saying so is
honest; refetching is not in scope.

## What each route returns when what it calls raises

`stream_frames` raises nothing new: `make_gap_event` builds a `JSONServerSentEvent` from
`{"dropped": int, "severity": "warn"}`, which always serialises. A client that disconnects mid-gap
leaves through the route's existing `finally`.

## A bundle ahead of its Hub, and a Hub ahead of its bundle (R3)

A committed bundle reaches the operator's `:8000` on its next page reload; Hub code reaches it only
when the operator restarts it. Both skews are safe for this change:

- **New bundle, old Hub process:** the old Hub never writes `stream_gap`, so the new branch never
  runs and the app behaves exactly as today (drops are still silent until the restart). No
  regression.
- **New Hub, old bundle still open in a tab:** the old allowlist (`useSSE.ts:337`) drops
  `stream_gap`, which is today's behaviour. The next reload picks up the new bundle.

So this change needs no restart gate.

## Open questions

None for the operator. Noticed, not in scope (R2 confirmed): `components/overview/OverviewPage.tsx:101` lists the last ten buffered
events of **every** project, unfiltered by the selected project — the one live consumer that does not
apply the `ActivityLog` filter. Worth a finding; it grows more visible once F251 admits 18 more kinds.
