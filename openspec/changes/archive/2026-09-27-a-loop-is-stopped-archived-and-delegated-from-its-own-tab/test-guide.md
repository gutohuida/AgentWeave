# Test guide — a loop is stopped, archived and delegated from its own tab

## Agent-verifiable

1. **An operator stop is in the loop's history.** Tasks 1.1 and 1.2 fail before the fix and pass
   after. They look the event up by `event_type`, because `GET /loops/{id}` returns events
   newest-first.
2. **A stop for an ended loop is refused and changes nothing.** Tasks 1.3, 1.3a and 1.3c fail
   before and pass after: 409 with `code: "loop_already_ended"`, and the ending, reason and time
   are unchanged. Control 1.3b (archiving an ended loop's job still succeeds) passes before and
   after. The two rewritten tests from 2.1b pass.
2a. **The hooks send what the Hub reads and re-read on failure.** Task 1.14 fails before and
   passes after.
3. **A stop that cannot be recorded does not happen.** Task 1.4: the request fails, and the loop
   is still running with its job still enabled. Task 1.13 is the same check for control and
   archival.
3a. **An operator stop is a stop.** Task 1.11: the reason `loop queue is empty` still records
   `stopped`.
3b. **Archiving a running loop's job is in the loop's history.** Task 1.12.
4. **The tab offers exactly the actions the Hub would accept.** Tasks 1.5-1.10 fail before, since
   no controls exist, and pass after. The state table is design D4.
5. **The ratchet moved the right way.** `n10_route_reachability.py` reports 33 clientless routes,
   and neither `/loops/{loop_id}/archive` nor `/control` is among them. `test_surface_ceilings.py`
   passes at ceiling 33 without warnings.
6. **Nothing else moved.** Full `hub/tests/` and `npx vitest run` counts are recorded, and the only
   test changes are those listed in tasks 1, 2.1b and 2.5.

## Human-only (trial Hub `:8010`, never `:8000`)

1. Create a loop with no stop condition. Open its tab from the conversation side panel's Loops
   index. Check that *"runs until stopped by the operator"* now sits beside a Stop control, and
   that the controller line reads naturally.
2. Delegate, then take back. Check that the controller line updated without a reload. Then read
   `GET /api/v1/projects/{id}/loops/{loop_id}` on `:8010` (curl, or the request in DevTools'
   Network tab) and check that `events` holds both `loop_control_changed` rows. The tab itself
   renders no event list (design, *Residuals*), so the history cannot be checked on screen.
3. Stop the loop while a firing is running. Confirm the running firing finishes and no new firing
   starts. Confirm the badge reads *Stopped early: <reason>*.
4. Archive it. It leaves the index. Switch *Show archived* on, and it is back, marked *Archived*.
5. With a second browser tab open on the same loop, stop it from the first tab. The second tab
   updates without a reload, through the `loop_stopped` SSE event.
5a. Refused stop. On a fresh running loop, open the Stop confirmation in one tab, stop the loop
   from a second tab, then confirm in the first. The first tab shows *"this loop already ended
   (<the second tab's reason>) at …; its record is left as it was"*, then shows the real ending,
   and Stop disappears. `GET /loops/{loop_id}` still shows the second tab's reason and one
   `loop_stopped`. If SSE refreshed the first tab before you could confirm, send the same `PATCH`
   by curl instead. It answers 409 with that sentence, never 500. Also clear the reason field before
   a stop: the badge reads *Stopped early: Stopped by the operator*.
6. Archive a **running** loop's job from the Jobs page. It is still accepted, and the loop tab shows
   it stopped with *"archived with its job"* (design D1, unchanged behaviour). An open loop tab
   updates without a reload. `GET /loops/{loop_id}`'s `events` now lists the stop and the archival
   (design D3a). Check this through the API, as in step 2.
