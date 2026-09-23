## 0. Rounds — no task below may start until R2 and R3 are recorded in `spec-queue/tracks/B9.md`

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B9.md`): re-derive D1-D4 from `hub/hub/sse.py`, `hub/hub/api/v1/events.py`, `hub/ui/src/hooks/useSSE.ts`, `hub/ui/src/components/activity/ActivityLog.tsx` and `hub/ui/src/api/agents.ts:540-570` without reading R1's argument first
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate a-live-view-that-fell-behind-is-told-and-catches-up --strict` passes
- [ ] 0.3 Operator approval in `spec-queue/APPROVALS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (D2, F253) `hub/tests/test_a_stream_that_fell_behind_is_told.py`: `SSEManager.subscribe_operator()`; publish 256 events to fill it, then 10 more across **two** projects. Assert `queue.qsize() == 256` and `queue.dropped == 10`. Same for a project stream's `subscribe(p)`. FAILS today (`dropped` does not exist)
- [ ] 1.2 (D2) Drive `stream_frames` over that queue with `is_disconnected` answering `False` until the frames are read. The first frame is `connected`; the second is the first queued event; the third is `event: stream_gap` whose data is `{"dropped": 10, "severity": "warn"}` with **no** `project_id`; then the remaining 255 queued events; no second gap. FAILS today (`stream_frames` does not exist; on today's routes no gap frame is ever written)
- [ ] 1.3 (D2) A burst followed by silence: fill, overflow by one, and publish nothing more. Reading the queue to empty still yields exactly one gap. This is the case a "gap on the next put" design would miss. FAILS today
- [ ] 1.4 (D2) Control: a subscriber that never overflows gets no gap frame. PASSES today and after
- [ ] 1.5 Control: `hub/tests/test_sse.py` and `hub/tests/test_operator_events.py` pass before and after (record counts). `test_reconnecting_gets_a_clean_queue_with_no_stale_events` must still hold: a fresh subscription starts at `dropped == 0`
- [ ] 1.6 (D4) `hub/ui/src/__tests__/useSSE.test.tsx`: a response whose chunks are, **in the order `stream_frames` emits them**, `event: connected`, one `task_updated` stamped with `project_id: "proj-a"`, then `event: stream_gap` / `data: {"dropped":10,"severity":"warn"}`. Assert: a listener sees `stream_gap` after `task_updated`; `queryClient.invalidateQueries` is called with **no** arguments once after the gap; an `onSseReconnect` callback fires once. FAILS today (the allowlist at `useSSE.ts:337` drops `stream_gap`)
- [ ] 1.7 (D4) The same stream with the gap placed **before** `task_updated` (the order D2 also permits): the catch-up still fires once and `task_updated` is still dispatched. FAILS today
- [ ] 1.8 (D4) `ActivityLog` with project `proj-a` selected: a live `stream_gap` with no `project_id` renders one line containing `10 events were not delivered`; a live `task_updated` for `proj-b` renders nothing (the existing filter is kept). FAILS today on the first assertion
- [ ] 1.9 Control: the existing `useSSE-lifecycle.test.tsx` reconnect tests pass before and after (the reconnect hook still fires on a real reconnect, and not on the first connect)

## 2. The fix

- [ ] 2.1 `hub/hub/sse.py`: `SubscriberQueue`, returned by both subscribe methods; `QueueFull` increments `dropped` in both loops (in `publish` if `an-event-is-announced-only-once-its-write-is-committed` has landed); `make_gap_event(n)`; `stream_frames(queue, is_disconnected)`
- [ ] 2.2 `hub/hub/api/v1/events.py`: both routes yield from `stream_frames`, keeping their `try/finally` unsubscribe and `EventSourceResponse(..., ping=15)`
- [ ] 2.3 `hub/ui/src/hooks/useSSE.ts`: handle `stream_gap` before the allowlist test; dispatch it, then `fireReconnect()`; widen `onSseReconnect`'s docstring
- [ ] 2.4 `hub/ui/src/components/activity/ActivityLog.tsx`: let `stream_gap` past the project filter. `hub/ui/src/lib/eventSummary.ts`: the `stream_gap` sentence (design D4)
- [ ] 2.5 Run group 1; `py -3.11 -m pytest hub/tests -q` and `cd hub/ui && npm test && npm run lint && npm run build`; record the counts. `ruff check hub/`, `black --check --target-version py311 hub/hub hub/tests`
- [ ] 2.6 `python scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Drive and close out

- [ ] 3.1 On a trial Hub from source (never `:8000`): re-run `t_sweep_row16_logs_events_sse.py` leg 6 (a stalled operator-stream subscriber, 3,000 events). Record the `stream_gap` frame(s) and that `dropped` plus the events received equals 3,000
- [ ] 3.2 Human-only check from `test-guide.md`
- [ ] 3.3 Mark F253 fixed in `scripts/drive/FINDINGS.md`; reconcile the requirement into `openspec/specs/local-project-workspace/spec.md` on archive
