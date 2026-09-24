# Tasks — a loop's outstanding mail is mail not yet delivered

## 0. Rounds

- [ ] 0.1 R2: re-derive, without reading design D1 first, every reader and writer of `Message.read`
  (`grep -rn "Message.read\|\.read = \|read == False" hub/hub src/`). Check whether every
  message-creation site creates exactly one entry (`grep -rn "Message(" hub/hub`). Check whether
  option (b) removes each consequence F259 names. Decide D2's open points: whether a duplicate entry
  should fail a test, and whether the `message_id` index is needed.
  **Done 2026-09-24.** No duplicate test: the `IN` subquery cannot double-count. No index: the
  entry side uses the existing composite index. R2 added the running-turn clause (design D2).
- [ ] 0.2 R3: the same, fresh.
  **Done 2026-09-24.** The readers are confirmed: `scheduler.py:498`, `status.py:45`, and the API
  filter. The one writer, `messages.py:410`, is confirmed too. Of the four `Message(` sites, only
  `messages.py:45` and `agents.py:2213` get an entry. `/compact` and `/new-session`
  (`agents.py:2979`, `:3016`) get none, so after this change they stop inflating `pending`. The
  entry states are `queued`, `delivered` and `withdrawn`. "Abandoned" is `withdrawn` with an
  `abandoned_reason`. `Run.status` defaults to `running`. Nothing changed but 1.5's setup.

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 `hub/tests/test_scheduler.py`: restage
  `test_loop_queue_exhausted_event_names_an_unread_message_to_the_creator` and
  `test_a_loops_pending_message_is_never_another_projects`. Each seeded `Message` gets a `queued`
  `InboundQueueEntry` (`message_id=` the message). Both still pass after the fix. Without the
  restaging, both fail after it, which is how 1.2 is known to have taken effect.
- [ ] 1.2 `test_a_delivered_message_is_not_an_outstanding_request` (new): the same setup as the
  first test, but the entry is `delivered` and the message keeps `read=False`. The
  `loop_queue_exhausted` payload has `pending_request: null`. **Fails today**: the message is reported,
  because `read` is still false.
- [ ] 1.3 `test_a_withdrawn_message_is_not_an_outstanding_request` (new): the entry is `withdrawn`.
  Gives `pending_request: null`. **Fails today.**
- [ ] 1.4 `test_the_newest_undelivered_message_is_the_one_named` (new): two executor→creator
  messages, the newer one `delivered` and the older one `queued`. The payload's `reason` is the
  older one's subject. **Fails today**: the newer one is picked. This also pins the newest-first
  order among the candidates that qualify.
  **Seed explicit timestamps** (operator review, 2026-09-24): both `Message` rows get
  `timestamp=` set by the test, several seconds apart (e.g. `base` and `base + timedelta(seconds=
  10)`), and the "newer" one is the later of the two. The column defaults to `_now()` at insert
  (`hub/hub/db/models.py:537`, `:24-25`), so two rows added in one flush can carry equal or
  microsecond-apart times, and `order_by(Message.timestamp.desc())` (`scheduler.py:500`) would then
  pick either. A test that passes by insertion accident is not evidence of the order. Add a third
  `queued` message older still, so the assertion names the newest *qualifying* one, not merely
  the only one.
- [ ] 1.4a `test_a_message_the_creator_is_still_reading_is_outstanding` (new): the entry is
  `delivered` with `delivered_in_run_id` naming a creator `Run` whose `status == "running"`. The
  payload names that message. It passes today as a control, because `read` is false. **It fails on
  R1's `queued`-only version**, which is how the running-turn clause is known to be in the query. A
  second case sets that run to `completed` and gets `pending_request: null`, which is 1.2's shape
  through a real run row.
- [ ] 1.5 `hub/tests/test_status.py` `test_pending_counts_mail_not_yet_delivered` (new): two
  operator messages (`POST /messages`, no `from`) to a registered agent with no runner, so both stay
  `queued`. Before counting, read both entries from the DB and assert they are `queued`, so the test
  does not depend on whether the route's drain attempt has settled. If they are not, seed the
  `Message` and `InboundQueueEntry` rows directly. `pending == 2`. Mark one entry `delivered` in the
  DB, and `pending == 1` while `total == 2`. **Fails today**: `pending` stays 2.

## 2. Implementation

- [ ] 2.1 `hub/hub/scheduler.py` `_pending_loop_request`: the D2 query. Update its docstring's
  *"mail sitting unread in an inbox nobody has to check"* (`:440-441`) to *"mail not yet delivered"*.
- [ ] 2.2 `hub/hub/api/v1/status.py`: the D2 count.

## 3. Verification

- [ ] 3.1 `py -3.11 -m pytest hub/tests/test_scheduler.py -k "pending or exhausted" hub/tests/test_status.py -q`
  with `claude` stripped from PATH. As a batch, see F264's foot: the exhaustion tests need an
  earlier test to create the schema. Then run the full `hub/tests/`.
- [ ] 3.2 The CLAUDE.md lint block.
- [ ] 3.3 Run `EXPLAIN QUERY PLAN` for both D2 queries against a trial-Hub database, never `:8000`.
  Record that the entry side uses `ix_inbound_queue_project_agent_state_arrival` (or
  `ix_inbound_queue_delivered_run` for the run join), and that `messages` is probed by primary key.
  If either shows a full scan of `inbound_queue_entries` per message, stop and reopen D2's index
  verdict.

## 4. Close

- [ ] 4.1 Foot F259 in `scripts/drive/FINDINGS.md`: no product decision reads the flag. The flag
  stays as API bookkeeping, per D1.
- [ ] 4.2 Sync the delta into `openspec/specs/agent-loops/spec.md` (run the R-2 collision script)
  and archive.
