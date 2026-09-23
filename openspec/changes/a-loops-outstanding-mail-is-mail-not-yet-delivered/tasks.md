# Tasks — a loop's outstanding mail is mail not yet delivered

## 0. Rounds

- [ ] 0.1 R2: re-derive, without reading design D1 first, every reader and writer of `Message.read`
  (`grep -rn "Message.read\|\.read = \|read == False" hub/hub src/`). Check whether every
  message-creation site creates exactly one entry (`grep -rn "Message(" hub/hub`). Check whether
  option (b) removes each consequence F259 names. Decide D2's open points: whether a duplicate entry
  should fail a test, and whether the `message_id` index is needed.
- [ ] 0.2 R3: the same, fresh.

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
- [ ] 1.5 `hub/tests/test_status.py` `test_pending_counts_mail_not_yet_delivered` (new): two
  operator messages (`POST /messages`, no `from`) to a registered agent with no runner, so both stay
  `queued`. `pending == 2`. Mark one entry `delivered` in the DB, and `pending == 1` while
  `total == 2`. **Fails today**: `pending` stays 2.

## 2. Implementation

- [ ] 2.1 `hub/hub/scheduler.py` `_pending_loop_request`: the D2 query. Update its docstring's
  *"mail sitting unread in an inbox nobody has to check"* (`:440-441`) to *"mail not yet delivered"*.
- [ ] 2.2 `hub/hub/api/v1/status.py`: the D2 count.

## 3. Verification

- [ ] 3.1 `py -3.11 -m pytest hub/tests/test_scheduler.py -k "pending or exhausted" hub/tests/test_status.py -q`
  with `claude` stripped from PATH. As a batch, see F264's foot: the exhaustion tests need an
  earlier test to create the schema. Then run the full `hub/tests/`.
- [ ] 3.2 The CLAUDE.md lint block.

## 4. Close

- [ ] 4.1 Foot F259 in `scripts/drive/FINDINGS.md`: no product decision reads the flag. The flag
  stays as API bookkeeping, per D1.
- [ ] 4.2 Sync the delta into `openspec/specs/agent-loops/spec.md` (run the R-2 collision script)
  and archive.
