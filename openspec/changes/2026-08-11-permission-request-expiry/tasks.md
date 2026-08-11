# Tasks — A permission request never outlives the run that raised it

## 1. Reproduce before fixing

- [x] 1.1 Write a failing test at the **HTTP route level** — the seam nothing currently covers. Open a
      request through `POST /agent-actions/permission-requests`, let the wait lapse without a
      decision, then assert the row is *not* pending and that `POST .../decide` is refused. It must
      fail on today's code for the stated reason, not for a setup error.

      `hub/tests/test_permission_request_lifecycle.py`, **3 tests, all failing as intended**. Written
      in two halves deliberately: the reported-timeout half fails `405 Method Not Allowed` (the
      expire route is absent), which alone would only prove an endpoint is missing, so
      `test_a_request_does_not_survive_the_run_that_raised_it` reaches the same defect *without*
      touching the new route and fails `assert 'pending' != 'pending'` — the defect verbatim.

      **The diagnosis was confirmed against the routes, not carried from the exploration.** A
      throwaway probe (written, run, deleted) opened a request, ended the run, and found the row
      `STILL_LISTED: True` and `POST .../decide` returning **`200 allowed`** — the false record of an
      authorisation that never took effect, exactly as D3 describes.
- [x] 1.2 Confirm the second symptom in the same test or beside it: a stale pending row keeps its
      conversation marked as waiting (`conversations.py:268-269`). Fixing 2 and 3 must clear it.

      `test_an_expired_request_stops_pinning_its_conversation_as_waiting` asserts `attention ==
      "waiting"` while pending (passes today — the symptom is real), then that it stops after expiry
      **and** after the run leaves `running`, so it cannot pass on the run's status alone.

## 2. The Hub closes what the run stops waiting on

- [x] 2.1 Add `POST /agent-actions/permission-requests/{id}/expire` in `agent_actions.py`, beside the
      existing agent-facing routes and authenticated the same way — run-bound identity, never an
      agent name from a body or header.

      `expire_permission_request`, immediately after `poll_permission_request`. Identity comes from
      `Depends(get_agent_actor)` alone; the body is empty by design, so there is nothing in it to
      trust.
- [x] 2.2 Scope it per design D6: only `pending` → `expired`, only for a request belonging to the
      calling run, idempotent on an already-terminal row (success, no change, no error). Carries no
      reason — `_report_decision` reports the decision; this reports only that nobody is listening.

      Scoped on `run_id == actor.run_id` — *narrower than the poll route beside it*, which scopes on
      `agent`. One run must not be able to close another's decision even under the same agent name.
- [x] 2.3 Write `decided_at`/`decided_by` in a way that keeps a timeout distinguishable from an
      answer, which `db/models.py:1157-1159` says `decided_at` is for. State which you chose.

      **Chosen: expiry leaves both NULL.** The model's sentence is only true if a timeout does not
      set `decided_at` — so the invariant is now `decided_at is not None` ⟺ a human answered. `status`
      carries the terminal fact; `decided_at` carries who and when. Asserted in 4.1.

## 3. The run reports, and the run's end sweeps

- [x] 3.1 `mcp_server._ask_operator` — call the expiry endpoint on the timeout path before returning
      its denial. **Best-effort exactly like `_report_decision`**: every failure swallowed, no
      exception escaping, and no change to the decision or its timing. The denial must be returned
      even if the Hub is unreachable.

      `_report_wait_ended`, written next to `_report_decision` and on the same terms.

      **One thing changed beyond the task, deliberately.** The poll loop treated `"expired"` as
      `"the operator refused this action"`. Before this change nothing could expire a Claude row, so
      that branch was unreachable; the sweep makes it reachable, and it would have told the agent a
      person refused it when no person was involved. Now expired reads *"this request is no longer
      open, so it was not approved"*. Same decision, no invented refuser.
- [x] 3.2 Add one helper that expires a run's pending requests, and call it from **both** run-end
      sites (`agent_trigger.py:1270` and `:1656`), in the transaction that already sets `run.status`
      and `run.ended_at`. One helper, two call sites — per D5, writing it twice is how the two paths
      drift.

      `hub/hub/permission_requests.py` — `expire_pending_for_run(db, run_id)`, one `UPDATE ... WHERE
      status = 'pending'`, caller commits so it joins the existing transaction.
- [x] 3.3 **Check the assumption**: search for every place a run reaches a terminal status. If there
      is a third, call the helper there too and record that the set was verified rather than assumed.

      **The assumption was wrong, and this is the task that caught it. There are five sites, not
      two.** Beyond `:1270` and `:1656`:

      | site | what it is | why it matters |
      |---|---|---|
      | `agent_trigger.py:1086` | PTY spawn failure (`FileNotFoundError`) | nothing spawned, so nothing asked — swept anyway |
      | `agent_trigger.py:1600` | Codex spawn failure | as above |
      | `run_reconciliation.py:43` | **Hub restart orphan sweep** | **the worst case there is** |

      The reconciliation site is the one that most needed this: a Hub bounced while a card is on
      screen leaves a row whose run no longer exists in *any* process, so before this the card
      outlived not just its run but the Hub that served it — permanently, across every subsequent
      restart. It also uses a **sixth terminal status, `"interrupted"`**, which a grep for
      completed/failed/stopped does not find. `scheduler.py:401` was examined and **excluded**: it is
      a `JobRun`, not a `Run`.
- [x] 3.4 Confirm the Codex path is unaffected — it already expires its own row at
      `agent_trigger.py:1451`, and the sweep must be a harmless no-op after it, not a double write.

      Unaffected. `:1451` guards on `status == "pending"` and so does the helper, so whichever runs
      second matches no rows. Asserted in 6.3.

## 4. Refuse a decision nobody is waiting for

- [x] 4.1 `permissions.py` — the 409 guard already exists and already says the right thing. Confirm it
      now fires for `expired`, and that the row's status, `decided_at`, and `decided_by` are left
      untouched when it does.

      Confirmed, no code change. The guard was always correct; nothing ever reached it. Asserted in
      `test_a_run_that_stops_waiting_leaves_no_answerable_request`: 409, `"moved on"` in the detail,
      and `status == "expired"` with both `decided_at` and `decided_by` still NULL.
- [x] 4.2 Surface the 409 in the UI as "the run has moved on" rather than a generic failure. An
      operator who hits the race must learn what happened, per D3.

      The Hub's sentence is rendered verbatim via the existing `readableApiError`, keyed to the
      request the operator actually clicked so a failure on one card cannot appear under another.
      Styled as the codebase's other refusals are — `role="alert"`, `var(--red)` — rather than a
      new treatment.

## 5. The operator sees that the agent gave up

- [x] 5.1 Keep an expired request visible instead of filtering it out. `list_permission_requests`
      defaults to `pending_only=True` — decide whether expired rows arrive via that endpoint or
      alongside, and say which in the task notes.

      **Chosen: the same endpoint, behind a new `include_expired` flag** which the UI sets. The
      default is untouched, so nothing else that lists requests changes meaning.

      *Rejected: dropping the filter and sorting it out client-side.* The query is capped at 100
      rows ordered newest-first, so in a busy project the answered history would push the requests
      that still matter off the end — a correctness bug dressed as a simplification.
- [x] 5.2 `PermissionRequestCard.tsx` — an expired request reads as expired and offers no allow/deny.
      Reuse the "no longer waiting" treatment from `2026-08-11-declining-a-question` rather than
      inventing a second visual language for the same idea (D4).

      The same words, position and token as `AgentQuestionCard`: a `--text-3` marker reading **"no
      longer waiting"** beside the eyebrow, with the explanation in its `title`. Allow/Deny are not
      rendered at all rather than disabled — a greyed button invites a click that cannot work.
      Beneath it, the one thing the operator can act on: raise this agent's permission timeout.
- [x] 5.3 Expired and operator-answered must be visibly different, not one grey state for both.

      They cannot collapse: an answered request is not rendered at all, and never was. Asserted
      from both ends — `allowed`/`denied` render nothing (frontend), and the list route omits an
      answered request while keeping the expired one (backend).
- [x] 5.4 Use the `Icon` component; introduce no second icon system and no raw hex.

      No icon was needed — the marker is text, as it is on the question card it copies. No hex:
      `var(--text-3)` and `var(--red)`.

## 6. Close the test gap

- [x] 6.1 Make 1.1 pass.
- [x] 6.2 Cover the full lifecycle over **real HTTP routes**, not a stubbed `_hub_request`: open →
      expire-on-timeout → decide is refused; open → run ends → row expired; open → operator allows →
      run sees `allowed`.

      All three, plus the poll the run actually reads to turn an answer into "allow".
- [x] 6.3 Test the race directly: decide and expire arriving together leave exactly one terminal
      status, whichever lands first.

      Both orders. `test_an_answer_already_given_is_not_overwritten_by_the_sweep` asserts the sweep
      matches **0 rows** after an answer — an unconditional write would erase a decision the run had
      already acted on. `test_expiring_twice_is_not_an_error` covers the reverse and is also 3.4's
      evidence that arriving second is a no-op rather than a double write.
- [x] 6.4 Test that an unreachable Hub on the expiry call still returns the run's denial, unchanged
      and undelayed — the rule the whole reporting path is built on.

      Asserts the message is unchanged **and** that the call does not add a retry or backoff to a
      turn already being held open.
- [x] 6.5 `test_permission_approver.py` — the timeout test currently asserts only the local denial
      against a stubbed Hub. Extend it to assert the write-back is attempted.

      Done, and one test added beyond the task: an expired request must not be reported to the agent
      as *"the operator refused this action"* (see 3.1).
- [x] 6.6 Frontend tests for the expired card: marked, not answerable, distinct from answered.

      6 new tests in `permissionRequestCard.test.tsx` (10 → 16), including the 409 race and that a
      failure on one card is not shown under another.
- [x] 6.7 A test that a conversation stops reading as "waiting" once its request expires.

      `test_an_expired_request_stops_pinning_its_conversation_as_waiting`, over the conversations
      route rather than by calling `conversation_attention` directly.

## 7. Verification — agent-verifiable

- [x] 7.1 `pytest hub/tests/ -q` green; record the count against the 1500 baseline.

      **1510 passed, 10 skipped** — 1500 plus the 10 added here. No pre-existing test changed
      behaviour.
- [x] 7.2 `pytest tests/ -q` green (372 baseline).

      **372 passed, 3 skipped** — exactly the baseline; no CLI code was touched.
- [x] 7.3 `npx vitest run` green (759 baseline across 80 files); `npx tsc --noEmit` clean.

      **765 passed across 80 files** — 759 plus the 6 added. `tsc --noEmit` clean.
- [x] 7.4 `ruff check hub/ src/` and `black` clean.

      `ruff`: all checks passed. `black --check` on all 8 files touched here: unchanged.
      **Not fixed, and stated rather than quietly swept:** `black` also flags four files this change
      never touches — `test_accounting_budget.py`, `test_task_transitions.py`,
      `test_project_workspace_unavailable.py`, `test_agent_trigger.py`. Pre-existing drift;
      reformatting them here would bury this change's diff in unrelated noise.
- [x] 7.5 `npx openspec validate --changes --strict` and `--specs --strict` pass.

      **10 changes passed, 29 specs passed.**
- [x] 7.6 `npm run build`, refresh `hub/hub/static/ui`, confirm with `diff -rq`.

      Built, copied, `diff -rq` reports identical.
- [x] 7.7 Re-run the standalone probe from the exploration
      (`testbed/scratch/run_probe.sh`) at 0s and 65s and confirm both still allow — the fix must not
      regress the path that already worked.

      | delay | approver called | allow returned | tool executed | elapsed |
      |---|---|---|---|---|
      | 0s | yes | yes | **yes** — `hello.txt` written | 11s |
      | 65s | yes | yes | **yes** — `hello.txt` written | 78s |

      Matches the pre-change run (10s / 72s). No regression.
- [x] 7.8 Behavioural probe against a **copy** of the real database: open a request, expire it both
      ways (timeout report, and run-end sweep), confirm the decide route refuses afterwards. Delete
      the copy; write nothing to the live board.

      `testbed/scratch/expiry_db_probe.py` (gitignored, like the other probes). Against a copy of
      `hub/data/agentweave.db` — project `proj-cddb0827` "Testbed", carried through every migration
      rather than built by `create_all` as the suite's schema is. **14/14 checks passed**, both
      closing routes: the schema accepts the new row, stores `"expired"`, leaves `decided_at` and
      `decided_by` NULL, refuses the late approval with the 409, drops it from the default list, and
      keeps it in the widened one.

      **This is what confirms D-"no migration needed" rather than assuming it.**

      Live board verified untouched afterwards: `permission_requests` still `[('allowed', 2)]`, zero
      probe rows, zero probe credentials. The copy did not delete on the first attempt — the async
      engine still held the file — so it was removed explicitly and its absence confirmed.
- [x] 7.9 Restart the Hub by exact PID and confirm `/openapi.json` publishes the new route.

      PID 21272 stopped, restarted via WMI as PID **19508** on `:8010`. `/openapi.json` now lists
      **six** permission routes, the sixth being
      `POST /api/v1/agent-actions/permission-requests/{request_id}/expire`. The pre-restart process
      listed five, which is the before/after rather than a bare assertion.

## 8. Verification — human-only (the operator runs these)

- [ ] 8.1 Does an expired card tell you what happened, or just look broken?
- [ ] 8.2 Having missed one, do you know what to change so you do not miss the next?
- [ ] 8.3 Is an expired card distinguishable from one you answered, at a glance?
- [ ] 8.4 Do expired cards accumulate into clutter over a real session?

## 9. User test guide

**Setup.** Testbed, a Claude agent, the composer's Permissions pill on **"Ask me"**. For step 1, set
the agent's permission timeout low (about 30s) so you are not waiting two minutes.

1. **The card stops pretending.** Ask the agent to run a shell command. When the card appears, **do
   not answer it.** Wait out the timeout.
   *Expect:* the card turns to expired on its own, and the agent continues, having been refused.
   *Failure looks like:* the card sits there as though still live — the original bug.

2. **A late answer is not silently swallowed.** With the card expired, try to Allow it.
   *Expect:* you are told the run has moved on. Nothing is recorded as approved.
   *Failure looks like:* it accepts, says nothing, and the tool still does not run.

3. **Approving in time still works.** Ask for another shell command and answer **Allow** promptly.
   *Expect:* the tool runs. This is the path that already worked and must keep working.
   *Failure looks like:* any regression here — the fix touched the timeout path, not this one.

4. **A stopped run does not leave a card behind.** Trigger a permission card, then **Stop** the run
   while it waits.
   *Expect:* the card closes as expired rather than outliving the run.
   *Failure looks like:* a card for a run that is no longer running.

5. **The conversation stops saying it is waiting.** After steps 1 and 4, look at the conversation.
   *Expect:* it no longer reads as waiting on you.
   *Failure looks like:* a permanent "waiting" marker with nothing behind it — the second symptom.
