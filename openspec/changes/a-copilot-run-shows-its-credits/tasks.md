**Depends on:** `each-runner-cli-is-one-adapter` (slice 1: `RunnerAdapter`, `get_adapter`, the
RPC executor `_execute_rpc_run`; it does **not** define `compaction_percent`, which task 3.1 adds),
`a-copilot-agent-runs-over-acp` (slice 2: `copilot_acp.run_turn`, its raw-event subscription
constant, `parse_copilot_envelope`, the `copilot` literal and migration) and
`a-run-reaches-the-hub-without-mcp` (slice 3). Build after all three are archived and after the
2026-09-27 night queue. Test commands use `py -3.11`, never bare `python`. Run pytest from the repo
root.

## 0. Rounds

- [x] 0.1 R2: re-derive the design independently against the code **as it stands after slices 1–3
  and tonight's queue**. In particular: (a) slice 1's `usage_from` contract and whether it defines
  `compaction_percent` (Q1, D9); (b) slice 2's executor, whether it runs one process per run, whether
  it knows `session/new` vs `session/load`, whether its `initialize` subscribes to the four event
  types, and whether its run end applies the refusal branch of `_execute_run` (Q2, D8); (c) every
  file:line in design.md, especially `usage_accounting.py:61-96` after
  `an-estimate-that-misses-turns-says-so` lands, and `checkpoint_trigger.py:168-310`; (d) what
  `GET /agents` loads per agent (D11). Also: what does each route return when the function it calls
  raises? Record the result in design.md's round log
  - **Done 2026-09-28** against master `ef55e6f`. Slices 1–3 are unbuilt and 5 of the 28 night changes
    have landed, so (a) and (b) were answered from those slices' designs. 12 corrections, among them
    a credit double count (D4), a refused turn whose input would not have been returned (D8), the
    ledger's home (D2), where the token ceiling goes (D10), and a drive step that could not raise its
    banner (7.6). Q1, Q2 and Q8 are answered, and gaps G1–G6 are in the round log
- [x] 0.2 R3: a second, fresh re-derivation of D3 (the lower-bound argument), D4 (the baseline
  lookup) and D10 (the formulas and the token-mode ceiling), from the code and the acp4 numbers, not
  from R2's notes. `openspec validate a-copilot-run-shows-its-credits --strict` passes
  - **Done 2026-09-28** against master `fc33ff9`. The acp4 sums were recomputed and hold (33108 / 64 /
    21888 / 33172, and 275856000 nano-AIU from each call's `tokenDetails`). The corrections: D4 is
    now the larger of two lower bounds, correct whether the checkpoint continues after a load or not.
    D2's settle was keyed on a checkpoint total, which starved the fallback and the D8 reset fill. The
    D8 JSON-RPC-error route could not fire, because slice 2 raises. The token-mode notes point was
    missing. Plus a "Required of slices 1 and 2" section; details in the round log
- [x] 0.3 Opus adversarial review of the change and its decisions (the operator's standing step
  before an APPROVED row). It re-derives in particular: whether any path adds a Copilot credit to a
  token total or to the budget; whether a Claude or Codex project's API responses and screens are
  byte-identical when no Copilot row exists; whether D8 can hold a queue on anything but the
  structured quota code
  - **Done 2026-09-28.** Opus review ghcp-s4-2026-09-28: APPROVE WITH FIXES → 11 applied, 2 answered
    (`spec-queue/tracks/reviews/ghcp-s4-2026-09-28.md`). Applied: findings 1–9, 11 and 12, with the
    byte-identity answer (API responses gain empty credit fields; the four moving asserts are named in
    6.1). Answered: 10 (the "no reported cost" string is kept) and 13 (stated under D8; the review's
    60 s floor hold does not start for a first-call refusal). Q7 is re-opened as an operator
    question. Mapping in design.md's round log, *Review fixes, 2026-09-28*

## 1. Tests first — each fails on today's code

- [x] 1.1 New `hub/tests/test_copilot_usage.py`, fixture `acp4_events()` built from the acp4
  transcript in the order Copilot emitted it (three `assistant.usage`, then `session.usage_checkpoint`,
  then the prompt result `{inputTokens 33108, outputTokens 64, totalTokens 33172, thoughtTokens 0,
  cachedReadTokens 21888, cachedWriteTokens 0}`). With `session_was_new=True`, `finish()` gives input
  33108, output 64, total 33172, cache_read 21888, reasoning 0, model `mai-code-1.1-flash`,
  `ai_nano_aiu` 275856000, `premium_requests` 1.0, both session totals equal to those, and
  `source == "copilot_calls"` (the calls and the result tie at 33172; a tie goes to the calls, D3).
  Fails today
  (no module). `py -3.11 -m pytest hub/tests/test_copilot_usage.py -q`
  - **Done 2026-10-02.** `hub/hub/copilot_usage.py` (new): `CopilotUsageLedger` with
    `observe_event`/`observe_prompt_result`/`finish` covering D3's per-call sum, the key-name
    mapping (D3 *Key names*) and the tie-goes-to-calls rule; `AccountingSample`
    (`runner_events.py`) gained the five new fields and carries them in `merged` (task 2.3's
    dataclass half only — `db/models.py`, the migration and `record_turn_usage`'s write stay open,
    tasks 2.1/2.2). `observe_prompt_error` and D7/D8's quota reading are not built yet (tests 1.9+).
    `py -3.11 -m pytest hub/tests/test_copilot_usage.py -q`: 1 passed. Re-ran
    `hub/tests/test_accounting_model.py`, `test_agent_trigger.py`, `test_provider_allowance.py`,
    `test_runner_parsing.py` (the four files that touch `AccountingSample`/`merged`): 169 passed,
    nothing moved by the new fields (they default to `None` and sit after the existing ones).
    `ruff check` clean; `black --check --target-version py311` clean after one reformat.
- [x] 1.2 Same file: the sum is not doubled. Total is 33172, not 66344, whichever of the calls or
  the prompt result the ledger saw first
  - **Done 2026-10-02.** `test_sum_is_not_doubled_whichever_side_arrives_first`: runs the acp4
    fixture through two ledgers, one fed events-then-result, one fed result-then-events (`finish`
    only reads accumulated state, so the two call orders are the only degrees of freedom `observe_event`/
    `observe_prompt_result` expose). Both give `total_tokens == 33172`, neither 66344.
    `py -3.11 -m pytest hub/tests/test_copilot_usage.py -q`: 2 passed. Also re-ran
    `test_accounting_model.py`, `test_agent_trigger.py`, `test_provider_allowance.py`,
    `test_runner_parsing.py`: 171 passed. `ruff check` and `black --check --target-version py311`
    clean on all three touched files.
- [x] 1.3 Same file: dropped events (`session_was_new=True`). Only calls 1 and 3 observed (their sum
  is 22080 + 26 = 22106), plus the full prompt result, gives total 33172 and
  `source == "copilot_prompt_result"`, `cache_read_tokens == 21888` (the prompt result's
  `cachedReadTokens`, mapped by the ledger, design D3 *Key names*), and logs one warning naming both
  figures. All three calls and no prompt result gives 33172 and `source == "copilot_calls"`
  - **Done 2026-10-02.** `test_dropped_calls_fall_back_to_the_prompt_result`: feeds calls 1 and 3
    only (skips call 2), then the full prompt result; asserts total 33172, `source ==
    "copilot_prompt_result"`, `cache_read_tokens == 21888`, and a captured WARNING-level log record
    containing both `"22106"` and `"33172"`. `test_all_calls_with_no_prompt_result_uses_the_calls`:
    all three calls, no prompt result, gives 33172 and `source == "copilot_calls"`. Both passed
    against today's code unchanged — `CopilotUsageLedger.finish` (`hub/hub/copilot_usage.py:141-166`)
    already implements this fallback and warning from task 1.1's build, so this task found no gap,
    only confirmed one. `py -3.11 -m pytest hub/tests/test_copilot_usage.py -v`: 4 passed. Re-ran the
    same four `AccountingSample`-touching files plus this one together: 173 passed (same unrelated
    `RuntimeError: Event loop is closed` aiosqlite-teardown resource warning noted by 1.1/1.2, not a
    test failure). `ruff check` and `black --check --target-version py311` clean on the touched file.
    `openspec validate a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.4 Same file: one ledger (one process) that observes two prompt results, 33172 and then a
  cumulative 40000, uses 40000, not their sum 73172 (design D3: the process-cumulative figure is the
  run's). Assert with the results in the order they were emitted, so a ledger that kept the earlier
  one fails

  Done 2026-10-02: `test_second_prompt_result_replaces_the_first_not_summed` added to
  `hub/tests/test_copilot_usage.py`. Feeds the acp4 calls, then `observe_prompt_result` with the
  acp4 result (33172) followed by a second result of 40000; asserts `total_tokens == 40000`,
  `!= 73172`, `source == "copilot_prompt_result"`. Passed against today's code unchanged —
  `observe_prompt_result` (`hub/hub/copilot_usage.py:115-117`) already overwrites `_prompt_result`
  on every call rather than keeping the first, so "last result wins" (D3) was already correct; this
  task found no gap, only added the test the spec calls for. `py -3.11 -m pytest
  hub/tests/test_copilot_usage.py -v`: 5 passed. Regression (same four `AccountingSample`-touching
  files plus this one): 174 passed (same unrelated aiosqlite-teardown `RuntimeError: Event loop is
  closed` resource warning noted by iterations 20-22, not a test failure). `ruff check` and
  `black --check --target-version py311` clean on both touched files. `openspec validate
  a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.5 Same file: a subagent call (`parentToolCallId` set, `initiator: "sub-agent"`) is counted
  once; a repeated notification with the same `providerCallId` is counted once

  **Done 2026-10-02.** `test_subagent_call_counted_once_and_duplicate_notification_deduped` added
  to `hub/tests/test_copilot_usage.py`. Feeds one top-level call plus one subagent call
  (`parentToolCallId` set, `initiator: "sub-agent"`), then the subagent call's event a second time
  (same `providerCallId`); asserts `total_tokens == 11009 + 510` (both calls counted once each,
  not the duplicate counted twice) and `ai_nano_aiu == 222280000 + 5000000` (the per-call nano-AIU
  sum, since no checkpoint was observed in this test). Sabotage check: with the `providerCallId`
  dedup in `_observe_call` (`hub/hub/copilot_usage.py:94-98`) disabled, the test fails on the
  `total_tokens` assert, confirming it actually exercises the dedup rather than passing
  vacuously — reverted after the check (`git status --short` showed only the test file touched).
  `py -3.11 -m pytest hub/tests/test_copilot_usage.py -v`: 6 passed. Regression (same four
  `AccountingSample`-touching files plus this one): 175 passed (same unrelated aiosqlite-teardown
  `RuntimeError: Event loop is closed` resource warning noted by iterations 20-23, not a test
  failure). `ruff check` clean; `black --check --target-version py311` clean after one reformat.
  `openspec validate a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.6 Same file: a `session.compaction_complete` with `compactionTokensUsed` adds its tokens and
  nano-AIU when no call has `providerCallId == requestId`, and adds nothing when one does

  Done 2026-10-02. `hub/hub/copilot_usage.py` gained a `_Compaction` record, `_observe_compaction`
  (dispatched from `observe_event` on `session.compaction_complete`) and `_effective_calls`
  (`_calls` plus each stored compaction whose `requestId`/`serviceRequestId` matches no observed
  call's `providerCallId`/`apiCallId`). The match is resolved lazily in `_effective_calls`, read by
  both `_calls_sample` and `finish`, rather than at observe-time, because whether a matching call
  exists can only be known once every event has arrived — an earlier observe-time version (using
  the shared `_seen_call_ids` set directly inside `_observe_compaction`) gave the wrong answer when
  the compaction event arrived *before* its matching call: it registered the compaction's own
  tokens first, then discarded the real call as a "duplicate" of its own `requestId`, counting the
  compaction's approximate figure instead of the call's actual one. Caught by adding a
  reversed-order assertion to the same test and is why the fix exists.

  Two tests added to `hub/tests/test_copilot_usage.py`:
  `test_compaction_adds_its_tokens_and_nano_aiu_when_no_call_shares_its_request_id` (one call plus
  an unrelated compaction: total and nano-AIU are both sums) and
  `test_compaction_adds_nothing_when_a_call_shares_its_request_id` (one call and a compaction whose
  `requestId` equals that call's `providerCallId`: total and nano-AIU are the call's alone, checked
  in both arrival orders — call-then-compaction and compaction-then-call). `py -3.11 -m pytest
  hub/tests/test_copilot_usage.py -v`: 8 passed. Sabotage check: temporarily forced the dedup
  branch in `_effective_calls` to never match (`if False:`) — the "adds nothing" test failed
  (13059 tokens instead of 11009), confirming it is not vacuous; reverted and re-ran clean. Re-ran
  the same four `AccountingSample`-touching files plus this one together: 177 passed (same
  unrelated aiosqlite-teardown `RuntimeError: Event loop is closed` resource warning noted by
  iterations 20-24, not a test failure). `ruff check` clean; `black --check --target-version py311`
  needed one reformat of both touched files (applied, re-checked clean). `openspec validate
  a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.7 Same file: two `session.usage_checkpoint` events (first 100000000/0, later 275856000/1) in
  emitted order: the later wins. Reversing their order fails this test

  Done 2026-10-02. Confirm-only, like 1.3/1.4: `observe_event`'s `session.usage_checkpoint` branch
  (`hub/hub/copilot_usage.py:95-99`) already unconditionally replaces `self._checkpoint` on every
  call, so "later wins" held before this task touched it. Added
  `test_second_usage_checkpoint_replaces_the_first` to `hub/tests/test_copilot_usage.py`: feeds two
  checkpoints (100000000/0, then 275856000/1) and asserts `session_nano_aiu_total == 275856000` and
  `session_premium_requests_total == 1.0`; then feeds the same two reversed and asserts
  `session_nano_aiu_total == 100000000` and `session_premium_requests_total == 0.0`. Sabotage check:
  temporarily guarded the assignment with `if self._checkpoint is None:` (first-wins) — the
  in-order assertion failed (100000000 != 275856000), confirming the test is not vacuous; reverted
  by re-editing the three lines back (not `git checkout --`), `git status --short` afterward showed
  only the test file touched. `py -3.11 -m pytest hub/tests/test_copilot_usage.py -v`: 9 passed.
  Re-ran the same four `AccountingSample`-touching files plus this one together: 178 passed (same
  unrelated aiosqlite-teardown `RuntimeError: Event loop is closed` resource warning noted by
  iterations 20-25, not a test failure). `ruff check` and `black --check --target-version py311`
  clean on the touched file. `openspec validate a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.8 Same file, credits (D4, R3's larger-of rule). Each case runs through
  `settle_copilot_credits` with a seeded `turn_usage`/`runs` baseline. "One call of N" means one
  `assistant.usage` whose `copilotUsage.totalNanoAiu` is N. Each case's per-call sum is chosen so that
  a rule taking only the difference, or only the calls, fails it:
  - (a) loaded, baseline 275856000/1, checkpoint 400000000/2, one call of 124144000 gives 124144000
    and premium 1.0, and stores 400000000/2;
  - (b) loaded with no baseline, the acp4 calls (275856000), checkpoint 400000000/2 gives 275856000
    and `premium_requests is None`, and stores 400000000/2;
  - (c) counter reset: baseline 275856000/1, checkpoint 124144000/1, one call of 124144000 gives
    124144000 (not None, R2's rule), `premium_requests is None`, and stores 124144000/1;
  - (d) counter restarted per process: baseline 100000000/1, checkpoint 124144000/1, one call of
    124144000 gives 124144000, not the difference 24144000, and `premium_requests is None`;
  - (e) the fallback stores what it charged: a new-session run with the acp4 calls and no
    checkpoint records 275856000 and `session_nano_aiu_total == 275856000`,
    `session_premium_requests_total is None`. The following loaded run, checkpoint 400000000/2 and
    one call of 124144000, is charged 124144000 with `premium_requests is None`. This fails if the
    fallback stores nothing;
  - (f) a run whose sample has `credit_session_new` set but no checkpoint and no calls is settled
    (a no-op on credits) rather than skipped. A sample without `credit_session_new` is returned
    unchanged. No events at all gives `total_tokens is None`;
  - (g) (review finding 12) the acp4 calls plus one call whose `totalNanoAiu` is -5000000 give
    275856000: the negative value is ignored;
  - (h) (review finding 3) a clock that steps backwards: four runs of one session (the first new,
    the rest loaded), spending 275856000, 124144000, 100000000 and 50000000 through their checkpoints
    (each with its own calls), recorded in that order with `observed_at` 10, 20, 10 and 15 seconds
    past a fixed instant. Run 4 is charged 50000000 and the four sum to 550000000. Ordered by
    `observed_at`, run 4 would be charged 150000000 against run 2's total, so this fails on the R3 rule

  **Done 2026-10-02.** `settle_copilot_credits` and `copilot_session_baseline` did not exist (task
  4.3 was unbuilt), and `turn_usage` had none of design D5's four credit columns (task 2.1/2.2
  unbuilt), so this task's own gap included the production code, not only the test. Built the
  minimal slice 1.8 needs, leaving the rest of 2.1/2.2/4.3's scope (the `worker_invocations`
  columns, D7/D8's quota half) open for 1.9/5.x:
  - `db/models.py`: `TurnUsage` gained `ai_nano_aiu` (BigInteger), `premium_requests` (Float),
    `session_nano_aiu_total` (BigInteger), `session_premium_requests_total` (Float), all nullable.
    Migration `0116_turn_usage_copilot_credits.py` (guarded for a missing table, as `0033`/`0034`
    do); `HEAD_REVISION` in `test_migrations.py` and the head assertion in
    `test_project_persistence.py` bumped to `0116`.
  - `usage_accounting.record_turn_usage` now writes the four fields from the sample whether or
    not the turn is `measured` (task 2.3's remaining half).
  - `usage_accounting.copilot_session_baseline(db, project_id, agent, session_id)`: the last
    `turn_usage` row with a non-null `session_nano_aiu_total`, for that project/agent, joined to
    `runs` on `session_id`, `ORDER BY turn_usage.rowid DESC` (not `observed_at` — review finding 3).
    Returns None on no row or on any exception, logged.
  - `usage_accounting.settle_copilot_credits(db, sample, *, project_id, agent, session_id)`: D4's
    larger-of rule. Returns `sample` unchanged when `credit_session_new is None`; otherwise never
    raises, logging and returning `sample` on any other exception.
  - `copilot_usage.CopilotUsageLedger.finish`'s provisional `ai_nano_aiu` was wrong for this task:
    it used the checkpoint total whenever one existed, discarding the per-call sum `settle` needs to
    compare against. In the acp4 fixture the two happen to be equal (both 275856000), so every
    task-1.1-1.7 test passed either way and the bug went unnoticed until 1.8 needed the per-call
    figure independently of the checkpoint. Fixed: `finish`'s provisional `ai_nano_aiu` is now always
    the per-call sum (D11's "provisional per-call credits"); `session_nano_aiu_total` still carries
    the checkpoint separately. Re-ran 1.1-1.7 after the fix: unaffected (9/9 still passed).

  Eight tests added to `hub/tests/test_copilot_usage.py`, one per case (a)-(h), each seeding real
  `Project`/`Run`/`turn_usage` rows through a test database session (`app` fixture) rather than
  only exercising the ledger. (h) seeds four runs of one session with `observed_at` 10s/20s/10s/15s
  past a fixed instant and asserts run 4 is charged 50000000 (the sum of all four is 550000000).

  **Sabotage checks** (both reverted after, `git diff` clean before the next step): (1) baseline
  query changed from `ORDER BY turn_usage.rowid DESC` to `ORDER BY turn_usage.observed_at DESC` —
  case (h) failed (`150000000 != 50000000`), confirming it actually exercises the rowid-vs-clock
  distinction the task describes. (2) the larger-of condition changed from
  `diff >= (per_call or 0)` to always prefer `diff` — cases (c) and (d) both failed (`24144000 !=
  124144000`), confirming the "larger of" comparison is live, not vacuous.

  `py -3.11 -m pytest hub/tests/test_copilot_usage.py -v`: 17 passed. Regression: `test_copilot_usage.py`
  plus `test_accounting_model.py`, `test_agent_trigger.py`, `test_provider_allowance.py`,
  `test_runner_parsing.py`, `test_accounting_api.py` together: 196 passed.
  `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q`: 124
  passed, 1 skipped (pre-existing skip, unrelated). `ruff check` clean on all touched files;
  `black --check --target-version py311` needed one reformat of the test file (applied, re-checked
  clean). `openspec validate a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.9 Same file, quota (D7, D8): acp4's snapshots give reading `{"status": "allowed", "quota":
  "chat", "rateLimitType": "monthly", "resetsAt": 1790812800, "remainingPercentage": 96.5,
  "provider": "copilot"}`. (1790812800 is 2026-10-01T00:00:00Z; assert it with
  `datetime(2026,10,1,tzinfo=timezone.utc).timestamp()`.) Adding `session.error {errorType: "quota",
  errorCode: "quota_exceeded"}` gives `status "rejected"`, and `provider_allowance.allowance_refusal`
  of it is not None. `errorType "rate_limit"`, `errorCode "session_quota_exceeded"`,
  `"billing_not_configured"`, and `errorType "query"` with message `"quota exceeded"` each leave
  `status "allowed"`. A refused run with no snapshot and a `prior_reading` whose `resetsAt` is ahead
  takes **only its `resetsAt`**: the reading is `{"status": "rejected", "resetsAt": <prior>,
  "rateLimitType": "monthly", "provider": "copilot"}`, with no `quota` or `remainingPercentage`
  copied (the seeded prior has `quota "chat"`, `remainingPercentage 12.0` and `status "allowed"`, so
  a whole-reading copy fails). `settle_copilot_credits` supplies the prior from a seeded `turn_usage`
  row (design D8). With one whose reset is past, `resetsAt` is absent. **Review finding 2:**
  `quota_reading(None, refused=False, prior_reading=<a rejected reading whose resetsAt is ahead>)`
  returns None (no reading written), and a settled non-refused sample with no snapshot carries
  `allowance is None`, so a later `rate_limit` failure cannot renew a hold. **Review finding
  1(b):** agent `b`'s first-call refusal, with agent `a`'s Copilot reading in the same project ahead
  and none of `b`'s own, is filled with `a`'s `resetsAt`, and `allowance_refusal` of it is not None;
  a reading from another project is not used. A replayed `session.usage_checkpoint` observed before
  the ledger is armed is ignored
  - **Done 2026-10-02.** Built the quota half of D7/D8 that task 1.1 left open: `copilot_usage.py`
    gained `_qualifying_snapshot` (excludes `completions` by name, any `isUnlimitedEntitlement`,
    and any entitlement `<= 0`), `_resets_at_from` (`resetDate` as epoch seconds) and the pure,
    stdlib-only `quota_reading(snapshots, *, refused, prior_reading)`. The ledger now tracks the
    newest call's `quotaSnapshots` and a `_refused` flag set only by `session.error
    {errorType: "quota", errorCode: "quota_exceeded"}` (never message text), and `finish()` calls
    `quota_reading(self._quota_snapshots, refused=self._refused, prior_reading=None)` into the
    sample's `allowance` — `prior_reading=None` always, since the ledger has no database (D2).
    `usage_accounting.py` gained `copilot_prior_quota_reading(db, project_id, *, now)`: the
    project's newest `turn_usage.allowance` (any agent, `runner == "copilot"`, `ORDER BY
    turn_usage.rowid DESC` as D4) whose `resetsAt` is still ahead of `now`. `settle_copilot_credits`
    calls it, and fills `resetsAt` alone into the sample's allowance, only when that allowance is
    already `{"status": "rejected", ...}` with no `resetsAt` of its own — never for an `allowed`
    reading (review finding 2), never overwriting a `resetsAt` the run's own snapshot already
    named (the late-reset case).
  - 17 tests added to `hub/tests/test_copilot_usage.py`: the acp4 allowed reading (exact dict,
    `resetsAt` asserted against `datetime(2026,10,1,tzinfo=timezone.utc).timestamp()`); the
    quota-exceeded refusal read by `allowance_refusal`; three other `errorType`/`errorCode` pairs
    (`rate_limit`/`session_quota_exceeded`, `rate_limit`/`billing_not_configured`,
    `query`/message `"quota exceeded"`) each staying `allowed`; four direct `quota_reading()` unit
    cases (no snapshot and not refused, review finding 2's prior-ignored case, the
    only-`resetsAt`-copied case, and refused with neither snapshot nor prior); and four
    `settle_copilot_credits` integration cases through a real database session — review finding
    1(b) (agent `b` filled from agent `a`'s reading in the same project), project isolation (a
    reading in another project is not borrowed), a past prior reset leaving `resetsAt` absent, and
    review finding 2's second half (a settled non-refused sample with no snapshot carries
    `allowance is None`).
  - **Sabotage checks**, both reverted after (`git diff` clean before moving on): (1) `_observe_error`
    changed to `if False: self._refused = True` — the quota-exceeded and 1(b) tests both failed
    (`allowance` stayed `None`/unrefused), confirming they exercise the recognition. (2)
    `copilot_prior_quota_reading`'s `if resets_at > current.timestamp()` changed to `if True` — the
    past-reset test failed (`resetsAt` present when it should be absent), confirming the "ahead of
    now" filter is live.
  - "A replayed `session.usage_checkpoint` observed before the ledger is armed is ignored" is
    `copilot_acp.run_turn`'s own dispatch-arming invariant (design.md:66-68, 1691, 1751), not a
    `CopilotUsageLedger` behaviour — the ledger only ever sees events `run_turn` has already armed
    and dispatched to it (design.md:114). Deferred to task 4.4, where the armed dispatch point and
    its wiring to the ledger are built; not tested here because there is nothing in this file to
    sabotage.
  - `py -3.11 -m pytest hub/tests/test_copilot_usage.py -v`: 30 passed. Regression:
    `test_copilot_usage.py` plus `test_accounting_model.py`, `test_agent_trigger.py`,
    `test_provider_allowance.py`, `test_runner_parsing.py`, `test_accounting_api.py` together: 209
    passed (same unrelated aiosqlite-teardown `RuntimeError: Event loop is closed` resource warning
    noted by iterations 20-27, not a test failure). `py -3.11 -m pytest hub/tests/test_migrations.py
    hub/tests/test_project_persistence.py -q`: 124 passed, 1 skipped (pre-existing, unrelated).
    `ruff check` clean on all touched files; `black --check --target-version py311` needed one
    reformat of the test file (applied, re-checked clean). `openspec validate
    a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.10 Extend `hub/tests/test_accounting_api.py`: seed a Claude turn (1000 tokens, no credits)
  for agent `a-claude` and two Copilot turns (500 and 300 tokens; 200000000 and 75856000 nano-AIU;
  premium 1.0 and 0.5) for agent `b-copilot`. `GET /accounting` gives `project.total_tokens == 1800`,
  `project.ai_nano_aiu == 275856000`, `project.premium_requests == 1.5`, `budget.used_tokens == 1800`.
  `agents[0]` is `a-claude` with `ai_nano_aiu is None`, `agents[1]` is `b-copilot` with 275856000 (by
  position, in the route's name order). `recent_turns` in `observed_at` descending order carry their
  own `ai_nano_aiu`, asserted by position. With `token_budget = 1801` and the same rows,
  `usage_accounting.project_budget_state(db, project_id)["exhausted"] is False` and its `used_tokens
  == 1800` (review finding 11: the scheduling hot path, `turn_scheduler.py:363`). Fails today
- [x] 1.11 Same file: a project with only Claude rows returns `ai_nano_aiu: null` and
  `premium_requests: null` everywhere. `preferred_display` for a Claude allowance row is unchanged
  except for the new `runner: "claude"` key. For a newer Copilot allowance row it carries
  `runner: "copilot"`. `GET /accounting/conversations/{id}` sums a conversation's credits
- [x] 1.12 Extend `hub/tests/test_checkpoint_policy.py`: `resolve_policy(None, None)` and
  `compaction_percent=95` give threshold 80, notes 70, final 92 (pins Claude). `compaction_percent=80`
  gives 65 / 55 / 77. A project percent threshold 80 with `compaction_percent=80` gives 77 and
  `threshold_source == "runner_ceiling"`, and a notes value of 78 becomes 67. A Claude percent
  threshold 95 with `compaction_percent=95` gives 92 (`runner_ceiling`; Q7 decided (b): the percent
  ceiling applies to Claude too), and a Claude notes value of 94 with it becomes 82. Token mode
  (Q7 decided (b), 2026-09-28: the token ceilings apply only below C=95): `should_checkpoint` with
  tokens below the threshold is True at percent 77 under C=80 and False at percent 76. Under C=95 it
  is False at percent 92 and at percent 99 (a Claude token threshold above 92% of the window is
  **not** fired early; this assert fails if the ceiling is applied uniformly). `crosses` itself is
  unchanged, since its signature has no policy.
  `needs_final_warning` at 77 is True under C=80 and False under C=95. Token-mode notes (R3): with
  C=80, a token threshold of 150000 and notes 140000, `should_request_notes` at 30000 tokens is False
  at percent 66 and True at percent 67, and False at percent 77 (the threshold ceiling). With no
  notes value it is False at 67. The same threshold and notes under C=95 give False at percent 82 and
  at 91 (no Claude token-notes ceiling). Fails today
- [x] 1.13 Extend `hub/tests/test_checkpoint_cutover.py` (beside the offered-mode tests): an `offered`
  project, a `copilot` runner bound to agent `cop` and a `claude` runner bound to agent `cla`, both
  with no threshold of their own. A reading of 66% for `cop`'s conversation sets
  `checkpoint_warning == "due"` and broadcasts one `checkpoint_due` with `threshold_value == 65`. The
  same reading for `cla` changes nothing. Then a dismissed `cop` conversation at 78% gets
  `"final"`. Fails today
- [x] 1.14 Extend `hub/tests/test_migrations.py`: upgrade to head adds the four `turn_usage` and two
  `worker_invocations` columns, nullable; downgrade removes them; a pre-existing `turn_usage` row
  survives with NULLs. Fails today
- [x] 1.15 The run end, in two files.
  - (a) `hub/tests/test_copilot_acp_run_turn.py` (slice 2's scripted fake session): a session whose raw
    events include the quota refusal and whose `session/prompt` returns `stopReason: "end_turn"` yields
    `TurnOutcome.status == "failed"` and one `on_accounting` call carrying the rejected reading. This
    is design D8's case. A fixture that ends `failed` by construction could not catch it. R3 adds
    two more. First, a session whose `session/prompt` answers with a JSON-RPC error whose `data`
    carries `errorType "quota"` and `errorCode "quota_exceeded"`. Second, one whose process exits
    after the quota `session.error` and before the prompt returns. In both, `run_turn` **returns**
    the failed outcome and calls `on_accounting` once, carrying the rejected reading. The same
    JSON-RPC error with `errorType "rate_limit"` also returns slice 2's `failed` outcome (its D12 R3),
    with no rejected reading, so no hold (contract reconciliation, 2026-09-28: R3 said it still raises).
  - (b) `hub/tests/test_a_refused_turn_holds_the_queue.py` gains an RPC case. It patches the Copilot
    transport's module-level `run_turn` (slice 1 D9's seam) to deliver that sample and a failed
    outcome. The run persists one `queue_agent_held` event. Its entries are returned, and the refusal
    is not counted as a delivery attempt. The job run is not finalised, and `provider_hold` names the
    reset. A run with `errorType "rate_limit"` persists no `queue_agent_held`, and a Codex RPC run's
    end is unchanged.

  Both fail today. **(a) done, iter 34, 2026-10-02**: slices 1 and 2 are no longer unbuilt --
  `each-runner-cli-is-one-adapter` and `a-copilot-agent-runs-over-acp` are both archived
  (`openspec/changes/archive/2026-10-01-each-runner-cli-is-one-adapter`,
  `2026-09-30-a-copilot-agent-runs-over-acp`) and `RunnerAdapter`/`get_adapter`/`_execute_rpc_run`/
  `CopilotAdapter`/`copilot_acp.run_turn` all exist -- the stale "(Rebase at IMPL: slices 1 and 2
  unbuilt at R2)" note below was checked fresh and no longer holds. What is still unbuilt, and is
  (a)'s own reason every new test fails, is slice 4's wiring: `run_turn`'s own docstring still says
  `on_accounting` is not called by this slice, and `CopilotUsageLedger.observe_prompt_error` does
  not exist, though `CopilotUsageLedger` itself and its quota recognition are already built and
  tested in isolation (1.1-1.9). Four tests added to `TestRunEndQuotaRefusalCallsOnAccountingWith
  RejectedReading` in `test_copilot_acp_run_turn.py`: the armed-session.error case, the JSON-RPC
  quota-error case, the process-exit-after-quota-error case (all three fail today exactly on their
  `on_accounting` assertion, confirmed by running each alone), and a `rate_limit` negative control
  (passes today, since no case calls `on_accounting` yet -- kept as a regression guard against a
  future wiring that fires on every JSON-RPC error rather than quota ones specifically). Full-file
  regression: `py -3.11 -m pytest hub/tests/test_copilot_acp_run_turn.py -q`: 50 passed, 3 failed
  (the new quota cases only, no other breakage). `ruff check` clean; `black --check
  --target-version py311` needed one reformat, applied.

  **(b) done, iter 35, 2026-10-02.** Four tests added to `hub/tests/test_a_refused_turn_holds_the_
  queue.py`: `test_a_refused_copilot_turn_holds_the_queue_uncounted` (patches `hub.copilot_acp.
  run_turn` to feed a rejected `AccountingSample` through `on_accounting`; asserts one entry
  returned `queued` with `delivery_attempts == 0`/`allowance_refusals == 1`, a `provider_hold`
  naming the reset and its `limit_type`, and exactly one `queue_agent_held` event), `test_a_refused_
  copilot_firing_stays_in_progress_until_delivered` (same quota turn fired through `JobScheduler.
  _fire_job_internal`; asserts the `JobRun` stays `in_progress`), `test_a_copilot_rate_limit_
  refusal_persists_no_held_event` (no sample delivered, mirroring 1.15(a)'s own `rate_limit`
  control; asserts the entry is counted as an ordinary failure and no `queue_agent_held` row
  exists), and `test_a_refused_codex_rpc_run_is_unchanged` (same shape over `hub.codex_appserver.
  run_turn`, bound `--app-server`; asserts Codex keeps today's counted-failure handling). Verified
  each of the first two fails for the stated reason, not a fixture error: `delivery_attempts == 1`
  (counted, not 0) and `firing.status == "failed"` (finalised, not `in_progress`) -- both because
  `_execute_rpc_run` (`hub/hub/api/v1/agent_trigger.py:3900-3984`) calls `return_run_entries(db,
  run_id)` with no `refusal` and `finalize_job_run_for_conversation` unconditionally, unlike
  `_execute_run`'s D2/D5 block (`:2963-3026`) that `_execute_rpc_run` never gained. The negative
  controls (rate-limit, Codex) pass today, unchanged, confirming they describe behaviour the fix
  must not disturb. `py -3.11 -m pytest hub/tests/test_a_refused_turn_holds_the_queue.py -v`: 14
  passed (all pre-existing, no regression) + 2 passed (the two new controls) + 2 failed (the two
  new quota cases, as predicted) = 16/18. `ruff check` clean; `black --check --target-version
  py311` clean, no reformat needed. `openspec validate a-copilot-run-shows-its-credits --strict`:
  valid.
- [x] 1.16 UI, extend `hub/ui/src/__tests__/accountingPresentation.test.tsx`: `formatAiCredits(275856000)`
  is `0.28 AI credits`, `formatAiCredits(4000000)` is `<0.01 AI credits`, and `formatAiCredits(null)` is
  `null`. `accountingDisplayLabel` with a Copilot allowance `{status: 'allowed', rateLimitType:
  'monthly', resetsAt, remainingPercentage: 96.5}` and `runner: 'copilot'` starts `Copilot monthly
  allowance available`. The existing Claude label strings are unchanged

  **Done 2026-10-02 (iter 36).** `formatAiCredits` does not exist yet (lands at 6.2), and
  `accountingDisplayLabel`/`AccountingDisplay` take no `runner` field yet (lands at 6.2/6.3), so the
  three `formatAiCredits` cases and the Copilot-naming case are read through a namespace cast
  (`readFormatAiCredits()` in the test file) rather than a direct named import — a missing named
  export fails module load for the *whole* test file under Vite's ESM resolution, not just one
  assertion, which would have taken the file's 15 pre-existing passing tests down with it. The
  fourth test added, pinning today's unprefixed Claude label (`'Rate-limit allowance available'`
  ...) as a control, passes today and is the byte-identical case design.md's "Surfaces" section
  promises to preserve.

  `npx vitest run src/__tests__/accountingPresentation.test.tsx` (from `hub/ui/`): 19 tests, 4
  failed (the three `formatAiCredits` cases at `expected undefined to be ...`/`toBeNull()`, and the
  Copilot-naming case at `'Rate-limit allowance available · resets Oct 1, 1:00 AM'` not matching
  `/^Copilot monthly allowance available/` — each failing for the stated reason, not a crash), 15
  passed (all pre-existing, no regression, plus the new Claude-control case). `npx tsc --noEmit`:
  clean. `npm run lint`: clean. Full suite, `npm test`: 176 files, 1 failed (this one) / 175 passed,
  1810 tests, 4 failed / 1806 passed — no collateral breakage elsewhere. `openspec validate
  a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.17 UI, extend `agentTimelineModel.test.ts`: `usageByRunId` returns `{tokens, nanoAiu}` per run
  and omits unavailable turns as `tokensByRunId` did. Extend `agentTimeline.test.tsx`: a turn with
  credits reads `… tokens · 0.28 AI credits`, and a turn without them reads exactly as today

  **Done 2026-10-02 (iter 37).** `usageByRunId` does not exist yet (lands at 6.3), and
  `TurnUsage.ai_nano_aiu` does not exist yet (lands at 6.2), so `agentTimelineModel.test.ts` reads
  `usageByRunId` through the same namespace-cast pattern 1.16 used for `formatAiCredits`
  (`readUsageByRunId()`), and builds its fixtures through a local `turnUsageWithCredits()` helper
  that casts past today's `TurnUsage` type for the extra field. Three new tests: a measured turn
  maps to `{tokens, nanoAiu}`; a turn with no credit figure carries `nanoAiu: null`; an unavailable
  turn alongside a measured one is omitted from the result — asserted on the *whole* returned object
  (not a single missing key), so `usageByRunId` not existing — `undefined?.(...)` is `undefined` —
  fails this test too, rather than vacuously satisfying "the unavailable run's key is absent" (the
  trap the file's comment on `readUsageByRunId` names).

  `agentTimeline.test.tsx` gained one test, next to the existing token-count test: a `recentTurns`
  row with `ai_nano_aiu: 275_856_000` (cast past today's `TurnUsage` type) expects
  `'1,234 tokens · 0.28 AI credits'` on `turn-worked-for`. The existing "omits the token stat
  entirely" test already pins a turn with no credits reading exactly as today, so task 1.17's
  "turn without them reads exactly as today" half needed no new test — it is still green and
  unmodified.

  `npx vitest run src/__tests__/agentTimelineModel.test.ts`: 22 tests, 3 failed (the three new
  `usageByRunId` cases, each `expected undefined to deeply equal {...}` — the gap, not a crash), 19
  passed (all pre-existing, no regression). `npx vitest run src/__tests__/agentTimeline.test.tsx`:
  47 tests, 1 failed (the new credits case, `Worked for 10s · 1,234 tokens` not matching the
  expected credits suffix), 46 passed (all pre-existing, no regression). `npx tsc --noEmit`: clean.
  `npm run lint`: clean. Full suite, `npm test`: 176 files, 3 failed (the two files above plus
  1.16's still-open `accountingPresentation.test.tsx`) / 173 passed; 1814 tests, 8 failed (4 from
  1.16, 4 new from 1.17) / 1806 passed — unchanged pass count, confirming no collateral breakage.
  `openspec validate a-copilot-run-shows-its-credits --strict`: valid.
- [x] 1.18 UI: an `AccountingPanel` test renders the credits line only when `project.ai_nano_aiu` is
  not null. Extend `overviewBudgetSummary.test.tsx` to match. Extend `agentCheckpointSettings.test.tsx`:
  an agent with `checkpoint_compaction_percent: 80` shows the "compacts at about 80%" line, and one
  with 95 or null and no configured threshold does not. **Review finding 5:** an agent with
  `checkpoint_compaction_percent: 95` and a percent override of 96 shows "lowered to 92%", and one
  with 92 does not. Extend `projectSettingsPanel.test.tsx`: a project threshold of 80 with an agent
  at `checkpoint_compaction_percent: 80` shows the "Lowered to 77%" line naming that agent; with
  only agents at 95 it shows nothing. **Q7 decided (b), 2026-09-28:** an agent with
  `checkpoint_compaction_percent: 95` and a percent override of 95 shows "lowered to 92%"; an agent
  with a token override of 150000 shows the "fires at 150000 tokens or at 77% of its window" line
  at `checkpoint_compaction_percent: 80` and **no** token line at 95 (Claude's token threshold is
  not lowered)

  **1.18(a) done 2026-10-02 (iter 38): the AccountingPanel/overviewBudgetSummary half.** Split like
  1.15(a)/(b) — this is the credits-display half (D6); the checkpoint-threshold-lowering half (D10,
  review finding 5, Q7) is 1.18(b), not yet started. `project.ai_nano_aiu`/`premium_requests` don't
  exist on `UsageSummary`/`AgentUsageSummary` yet (land at task 6.1), so both files build fixtures
  through an inline `as unknown as AccountingSnapshot[...]` cast rather than widening those types
  here, matching 1.16/1.17's namespace-cast pattern. `accountingPresentation.test.tsx` gained three
  tests under a new "AI credits on the Budgets panel" describe: a project with `ai_nano_aiu`/
  `premium_requests` set shows `'0.28 AI credits · 1.5 premium requests (Copilot) — not counted
  against the budget'` (D6's headline-caption row, byte-matched against its table text); a project
  with neither set shows no "AI credits" text anywhere (control); an agent chip with `ai_nano_aiu`
  set reads `'claude: 1,234 tokens · 0.28 AI credits'` while a sibling chip with no credits figure
  is unchanged (`'codex: Unavailable · 1 unavailable'`). `overviewBudgetSummary.test.tsx`'s mock was
  made mutable (a module-level `let project`, reset in `beforeEach`, mirroring
  `accountingPresentation.test.tsx`'s `let snapshot` — it was a fixed inline object before, with no
  way for a second scenario to vary it) and gained two tests: a project with `ai_nano_aiu` set shows
  `'0.28 AI credits'` somewhere on the summary; one without shows no "AI credits" text (control).
  All four assertions read `container.textContent` rather than a specific DOM split, since neither
  component's eventual markup for the new line is designed yet.

  **Verified each new failure is for the stated reason, not a crash.** `npx vitest run
  src/__tests__/accountingPresentation.test.tsx src/__tests__/overviewBudgetSummary.test.tsx`: the
  headline test fails with `expected '...' to contain '0.28 AI credits · 1.5 premium requests...'`
  (the gap); the chip test fails on `getByText('claude: 1,234 tokens · 0.28 AI credits')` finding no
  such node (the chip shows only `'claude: 1,234 tokens'` today, confirmed in the printed DOM); the
  overview-row test fails with `expected '...' to contain '0.28 AI credits'`. Both control tests
  (nothing to report) pass today, unchanged. `npx tsc --noEmit`: clean (the cast approach holds
  before task 6.1 adds the real fields). `npm run lint`: clean. Full suite, `npm test`: 176 files, 4
  failed (the two files above, plus 1.16's still-open `accountingPresentation.test.tsx` cases and
  1.17's still-open `agentTimelineModel.test.ts`/`agentTimeline.test.tsx` — same files, no new ones)
  / 172 passed; 1819 tests, 11 failed (8 pre-existing from 1.16/1.17, 3 new from 1.18(a)) / 1808
  passed — exactly 5 more total tests than iteration 37's 1814, all five accounted for (3 new
  failures + 2 new passing controls), confirming no collateral breakage. `openspec validate
  a-copilot-run-shows-its-credits --strict`: valid.

  Next (1.18(b)): `agentCheckpointSettings.test.tsx` (the "compacts at about 80%" line,
  `checkpoint_compaction_percent` on `AgentSummary` — not yet a field, lands at task 3.4 — review
  finding 5's "lowered to 92%" wording, and Q7 (b)'s token-override line) and
  `projectSettingsPanel.test.tsx` (the project-level "Lowered to 77%" line naming the agent). Read
  design D10 (`openspec/changes/a-copilot-run-shows-its-credits/design.md:567-685`) in full before
  starting — the percent/token ceiling rules and the exact wording for each surface are there, not
  restated in tasks.md.

  **1.18(b) done 2026-10-02 (iter 39): the checkpoint-ceiling-notice half.** None of D10's UI lines
  are built yet (only the policy fields and callers land across tasks 3.x–5.x), so every new
  assertion here is expected to fail today through `queryByText` — a missing node, not a crash.
  `checkpoint_compaction_percent` is not on `AgentSummary` yet (task 3.4): `agentCheckpointSettings
  .test.tsx`'s `agent()` fixture helper widened to `Partial<AgentSummary & {
  checkpoint_compaction_percent?: number | null }>`, cast `as unknown as AgentSummary` at the
  return, the same cast-past-today's-type approach 1.16/1.17/1.18(a) used. Seven new tests under
  "checkpoint ceiling notices": a Copilot-bound agent (`checkpoint_compaction_percent: 80`, no
  override) shows `/compacts at about 80%/` and `/fires by 77% at the latest/`; agents at 95 or
  null show neither (two control tests, pass today); review finding 5's 96%-override-at-C=95 case
  shows `/lowered to 92%/` and `/Claude compacts at about 95%/`; a 92% override at the final
  warning itself does not (control); Q7 (b)'s 95%-override case also shows `/lowered to 92%/`
  (95 > 92, so it is past the ceiling too); a 150000-token override on a Copilot-bound agent shows
  `/fires at 150000 tokens or at 77% of its window/`; the same override on a Claude-bound
  (`compaction_percent: 95`) agent shows no such line (control — Claude's token threshold is not
  lowered, Q7 (b)).

  `projectSettingsPanel.test.tsx` gained a `useAgents` mock (`@/api/agents`) — the panel does not
  call it yet; D10's "Project settings" bullet is what will make it — reset to `[]` in the file's
  main `beforeEach` so the thirteen pre-existing tests are unaffected, and a new describe block with
  the project's `checkpoint_threshold_mode`/`checkpoint_threshold_value` set to `'percent'`/`80` in
  its own `beforeEach`: a bound agent at `checkpoint_compaction_percent: 80` makes the panel show
  both `/Lowered to 77%/` and the agent's own name (`/cop-1/`); a bound agent at the C=95 default
  shows no "Lowered to" text at all (control).

  **Verified each new failure is for the stated reason, not a crash.** `npx vitest run
  src/__tests__/agentCheckpointSettings.test.tsx`: 20 tests, 4 failed (the four non-control cases
  above, each `received value must be an HTMLElement... Received has value: null` from
  `queryByText(...).toBeInTheDocument()` — a clean "not found", not a thrown `getByText` error or a
  render crash), 16 passed (all pre-existing plus the three new controls). `npx vitest run
  src/__tests__/projectSettingsPanel.test.tsx`: 18 tests, 1 failed (the naming case, same `null`
  shape), 17 passed (all pre-existing plus the new control). `npx tsc --noEmit`: clean. `npm run
  lint`: clean. Full suite, `npm test`: 176 files, 6 failed (the two files touched here, plus
  1.16/1.17/1.18(a)'s four still-open files, unchanged) / 170 passed; 1829 tests (10 more than
  iteration 38's 1819, all ten accounted for: 5 new failures + 5 new passing controls), 16 failed
  (11 pre-existing + 5 new) / 1813 passed — exactly the prior pass count plus the five new
  controls, confirming no collateral breakage. `openspec validate a-copilot-run-shows-its-credits
  --strict`: valid.

  A fresh, complete `hub/tests/` background run is still owed (iteration 35's died with its
  session, never finished) — 1.18(b) was UI-only (no Python touched), so this did not block it, but
  the next Python-touching task should kick one off early and actually read its tail before relying
  on it.
- [x] 1.19 Extend `hub/tests/test_provider_allowance.py` (Q6 decided 2026-09-28, design D8): a
  reading `{"status": "rejected", "resetsAt": 1790812800, "rateLimitType": "monthly", "provider":
  "copilot"}` gives `hold_for_reading(...).provider == "copilot"`, and `hold_sentence("cop", hold)`
  contains `"2026-10-01"`, `"00:00 UTC"`, `"another runner"`, `"then send it a message"` and
  `"rebinding alone does not end the hold"`, and names loops and jobs. `hold_busy_reason` and
  `hold_coalesce_reason` for it contain `"2026-10-01"`, and the coalesce form is at most 500
  characters at a 32-character agent name. The existing Claude reading (no `provider` key) gives
  `provider is None`, and the three existing length asserts (285, 86, 161) are unchanged, so no
  Claude sentence moves. Extend `test_a_refused_turn_holds_the_queue.py`'s RPC case (1.15(b)): the
  held Copilot agent's `waiting_reason` from `schedule_agent` is that Copilot sentence. Fails today

  **Done 2026-10-02 (iter 40).** `1790812800` decodes to exactly `2026-10-01T00:00:00+00:00`
  (checked: `datetime.fromtimestamp`), matching D8's own example, so `_copilot_hold()`'s
  `hold_until` is built from it directly. `provider_allowance.py` has neither field yet
  (task 5.5, not this one), so all four new assertions fail cleanly: `hold_for_reading(...).provider`
  raises `AttributeError: 'ProviderHold' object has no attribute 'provider'`, and
  `ProviderHold(..., provider="copilot")` raises `TypeError: unexpected keyword argument 'provider'`
  at construction — not masked passes, and not a different crash than the one task 5.5 closes.
  `hold_for_reading` had to be added to the file's `from hub.provider_allowance import (...)` block
  (it wasn't previously imported there). **Care taken not to regress the three pinned lengths:**
  the new `_copilot_hold()` is its own helper with a hard-coded `provider="copilot"`, not a
  `provider=` parameter threaded onto the existing `_hold()` — a first pass did exactly that and
  broke all 3 of the existing sentence tests (`_hold()` calling `ProviderHold(..., provider=None)`,
  which the dataclass does not accept, `TypeError` on every call) before being caught and reverted;
  `_hold()` is back to its original signature, confirmed unchanged by the full file re-run below.
  `_rejected_copilot_sample` (`test_a_refused_turn_holds_the_queue.py`) gained `"provider": "copilot"`
  in its allowance dict (D7's real wire shape always carries it) — inert today since nothing reads
  the key yet, confirmed by diffing this file's failure set before/after (`git stash`): the same two
  tests fail at the same two assertions, for the same reason, with or without the key. The RPC case's
  new assertion (`real_schedule_agent` called again after the hold is established, asserting
  `result.waiting_reason == provider_allowance.hold_sentence(agent, hold)`) sits after the function's
  existing assertions, so it does not change *where* that already-red test fails today; it will bite
  once task 5.3 (the RPC run-end branch) and 5.5 (the Copilot sentence) both land.
  `py -3.11 -m pytest hub/tests/test_provider_allowance.py hub/tests/test_a_refused_turn_holds_the_queue.py hub/tests/test_inbound_queue.py -q`
  run per-file: `test_provider_allowance.py` 25 passed / 4 new failed (exactly the four new
  assertions above); `test_a_refused_turn_holds_the_queue.py` 14 passed / 2 failed, the same two as
  the `git stash` baseline, at the same assertion lines; `test_inbound_queue.py` 29 passed,
  untouched — 68 passed / 6 failed overall, all six accounted for, no regression.
  `ruff check` clean on both edited files. `black --check --target-version py311` needed one
  reformat of `test_provider_allowance.py` (applied, re-checked clean).
  `openspec validate a-copilot-run-shows-its-credits --strict`: valid.

## 2. Schema and sample

- [ ] 2.1 `db/models.py`: add the four `TurnUsage` columns and two `WorkerInvocation` columns (design
  D5). Leave `ck_turn_usage_availability` unchanged
- [ ] 2.2 The migration (next free number at build time): table guards as `0033`/`0034`,
  `batch_alter_table`, no backfill. Bump `HEAD_REVISION` (`hub/tests/test_migrations.py`) and the head
  assertion in `hub/tests/test_project_persistence.py`. `py -3.11 -m pytest hub/tests/test_migrations.py hub/tests/test_project_persistence.py -q`
- [ ] 2.3 `runner_events.AccountingSample`: add `ai_nano_aiu`, `premium_requests`,
  `session_nano_aiu_total`, `session_premium_requests_total` (Optional, default None) and the
  unpersisted `credit_session_new: Optional[bool]`, and carry all five in `merged` (R3: a merge that
  dropped the flag would turn the settle into a no-op). `usage_accounting.record_turn_usage` writes them whether or not the sample is measured

## 3. The compaction point and the thresholds

- [ ] 3.1 `RunnerAdapter.compaction_percent` (`ClassVar[Optional[int]]`, no base default) with
  Claude 95 and Codex 95, and 80 on slice 2's `CopilotAdapter` (design D9). Slice 1 reserves the
  member for this slice (its D16). Extend slice 1's conformance test so every `ADAPTERS` entry
  declares it. `grep -rn "compaction_percent" hub/hub/runner_adapters` shows all three. (Rebase at
  IMPL: `each-runner-cli-is-one-adapter` unbuilt at R2)
- [ ] 3.2 `checkpoint_policy.py`: D10's formulas, the two new `CheckpointPolicy` fields, the percent
  clamp (every runner), the notes clamp, the token-mode ceiling in `should_checkpoint` and in the
  threshold half of `should_request_notes` (not in `crosses`) and the token-mode notes ceiling, both
  guarded by `policy.compaction_percent < 95` (Q7 decided (b), 2026-09-28), and `needs_final_warning`
  reading the policy. Keep the three module constants at their C=95 values. Task 1.12 passes
- [ ] 3.3 `checkpoint_trigger.consider`: resolve the agent's runner (`Agent.runner_id` → `Runner` →
  adapter) and pass `compaction_percent`; the decline message names `policy.final_warning_percent`;
  both `checkpoint_due` payloads carry `threshold_source`. Task 1.13 passes.
  `py -3.11 -m pytest hub/tests/test_checkpoint_policy.py hub/tests/test_checkpoint_cutover.py -q`
- [ ] 3.4 `AgentSummary.checkpoint_compaction_percent` in `schemas/agents.py`, filled in
  `list_agents`'s `AgentSummary(...)` (`api/v1/agents.py:581-630`) from `bound_runner` (`:548`, taken
  from `runners_by_id`, `:405-407`) through `get_adapter`, null when there is none, with no new
  query

## 4. The ledger

- [ ] 4.1 Add `assistant.usage`, `session.usage_checkpoint` and `session.compaction_complete` to
  slice 2's subscription constant. Its design already lists `session.error`, leaves the first two to
  this slice, and includes none of the three. A test asserts that the `initialize` request carries all
  four. (Rebase at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2)
- [ ] 4.2 `hub/hub/copilot_usage.py`: `CopilotUsageLedger` (`observe_event`, `observe_prompt_result`,
  `observe_prompt_error`, `finish`) per design D2–D4, with the Copilot key mapping of D3 and
  negative credit figures ignored (D4), and `quota_reading(snapshots, *, refused, prior_reading)` per
  D7–D8: `prior_reading` is read only when `refused`, and only for `resetsAt`.
  `finish(*, session_was_new)` is pure and never raises (D11). Tasks 1.1–1.7 and the ledger half of
  1.9 pass. `py -3.11 -m pytest hub/tests/test_copilot_usage.py -q`
- [ ] 4.3 `usage_accounting.copilot_session_baseline(db, project_id, agent, session_id)`: the last
  written `turn_usage` row (`ORDER BY turn_usage.rowid DESC`, not `observed_at`; design D4, review
  finding 3) joined to `runs` on `Run.session_id == session_id`, for that project and agent, with
  `session_nano_aiu_total` not null. It returns None on any exception, logged. Also
  `usage_accounting.settle_copilot_credits(db, sample, *, project_id, agent, session_id)` (design D2,
  D4, D8): the larger of the baseline difference and the per-call sum, premium requests only when the
  difference was used, the fallback's stored total, and, for a `rejected` reading only, the
  `resetsAt` of the project's last written Copilot reading (any agent) whose reset is ahead (D8). It acts on
  every sample whose `credit_session_new` is not None, checkpoint or not, returns any other sample
  unchanged, and never raises.
  Tasks 1.8 and the settle half of 1.9 pass
- [ ] 4.4 `copilot_acp.run_turn` (design D2; R2's answer to Q1 is that there is no adapter
  `usage_from`):
  - one ledger per call, armed when the `session/prompt` request is written;
  - every subscribed raw event and the prompt result go to the ledger;
  - `cb.on_accounting(ledger.finish(session_was_new=…))` is called exactly once on every return path
    after a session exists;
  - it returns `TurnOutcome(status="failed", …)` when the ledger recorded the quota refusal (D8);
  - once the prompt is written, an exception while waiting for it (a JSON-RPC error, whose `data`
    goes to `observe_prompt_error`, or the process ending) ends in slice 2's returned `failed`
    outcome (its D12 R3), carrying the refusal when the ledger has recognised it (contract reconciliation, 2026-09-28: R3 said
    re-raised otherwise). This reads slice 2's `CopilotACPError.data` (design, *Required of slices 1
    and 2*, item 9).

  Task 1.15(a) passes. (Rebase at IMPL: `a-copilot-agent-runs-over-acp` unbuilt at R2)

## 5. The run end

- [ ] 5.1 `_execute_rpc_run` (slice 1's generic RPC executor): at run end, in the finalising session
  and before `record_turn_usage`, pass the merged sample through `settle_copilot_credits`, which acts
  on any sample whose `credit_session_new` is set (R3: not only one with a session credit total). Then record it with `runner=adapter.name`. The
  executor has no `"copilot"` literal. (Rebase at IMPL: slice 1 unbuilt at R2)
- [ ] 5.2 Log every `session.error` payload at warning level with its `errorType`, `errorCode` and
  `statusCode` (design D8, capture)
- [ ] 5.3 Apply `_execute_run`'s refusal branch (`api/v1/agent_trigger.py:2667-2743`) to
  `_execute_rpc_run`. Its Codex ancestor has none of it (`:3345-3362`), and slice 1's design does not
  unify the run end (R2). The branch is:
  - `hold_for_reading`, and `allowance_refusal` gated on `final_status == "failed"`, no binding
    conflict and a reset still ahead;
  - `finalize_job_run_for_conversation` skipped under a refusal;
  - `return_run_entries(..., refusal=)`;
  - after the commit, `arm_allowance_wake` and the `queue_agent_held` event.

  Task 1.15(b) passes. (Rebase at IMPL: slice 1 unbuilt at R2)
- [ ] 5.4 `WorkerUsage` gains `ai_nano_aiu` and `premium_requests`, and `run_worker` writes them into
  `WorkerInvocation(...)` (`worker.py:393-412`). Slice 2's `parse_copilot_envelope` reads
  `session.shutdown {totalNanoAiu, totalPremiumRequests}` into them **if** slice 2's task 1.2 capture
  of the `-p --output-format json` stream contains that event. The parser test uses that capture, not
  a hand-written line. If the capture has no `session.shutdown`, record that here and leave the
  columns NULL. (Rebase at IMPL: slices 1 and 2 unbuilt at R2)
- [ ] 5.5 `provider_allowance.py` (Q6 decided 2026-09-28, design D8): `AllowanceRefusal` and
  `ProviderHold` gain `provider: Optional[str] = None`, read from the reading's `provider` key and
  carried by `hold_for_reading`. For `provider == "copilot"`, `hold_sentence` names the reset date and
  the way out (bind the agent to another runner, then message it; rebinding alone does not end the
  hold; its loops and jobs stay blocked until then), and `hold_busy_reason` and
  `hold_coalesce_reason` add the date. A hold with no provider renders exactly as today. Task 1.19
  passes. `py -3.11 -m pytest hub/tests/test_provider_allowance.py hub/tests/test_a_refused_turn_holds_the_queue.py hub/tests/test_inbound_queue.py -q`

## 6. API and UI

- [ ] 6.1 `usage_accounting`: `ai_nano_aiu` and `premium_requests` in `_aggregate_columns`,
  `_summary_from_row`, `recent_turns` and `conversation_usage`; `runner` on the allowance display.
  Every new key is appended after the existing ones. **Extend, do not loosen,** the four exact-dict
  assertions in `hub/tests/test_accounting_api.py` that the new keys move (review finding 9; design
  D6): `:89` (`data["project"] ==`) and `:98` (`data["agents"] ==`) gain `"ai_nano_aiu": None,
  "premium_requests": None`; `:136` (`preferred_display ==`, an allowance) gains `"runner": "claude"`;
  `:368` (the conversation `response.json() ==`) gains the two null keys. They stay exact `==`, and
  are the byte-identity test of test-guide item 3. Tasks 1.10–1.11 pass. `py -3.11 -m pytest hub/tests/test_accounting_api.py hub/tests/test_accounting_budget.py hub/tests/test_provider_allowance.py -q`
- [ ] 6.2 `api/accounting.ts` types; `accountingDisplay.ts`: `NANO_AIU_PER_AI_CREDIT`,
  `formatAiCredits`, `monthly` period, provider name in the allowance label
- [ ] 6.3 `AccountingPanel.tsx`, `OverviewBudgetSummary.tsx`, `AgentOutputPanel.tsx` (conversation
  header), `agentTimelineModel.ts` (`usageByRunId`), `AgentTimeline.tsx`, `AgentSettingsControls.tsx`
  and `ProjectSettingsPanel.tsx` (the lowering lines, one `runnerCeilingNote` helper beside
  `describeThreshold`) per design D6 and D10. Tasks 1.16–1.18 pass.
  `cd hub/ui && npm run lint && npx vitest run`
- [ ] 6.4 Only if `worker-spend-counts-against-the-budget` has already landed: each `workers` line
  gains `ai_nano_aiu` and `premium_requests` sums, with a test in its test file. Otherwise record here
  that it has not landed, so that change adds them when it lands (design D12)
- [ ] 6.5 `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py`. Commit
  `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 6.6 The CI set: `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`,
  `mypy src/`, `py -3.11 -m pytest hub/tests/ -q`, `py -3.11 -m pytest tests/ -q`

## 7. Drive

On the trial Hub `:8010`, started from `hub/` per `CLAUDE.md`:
`cd hub && DATABASE_URL="sqlite+aiosqlite:///C:/Users/huida/.agentweave/hub/profiles/trial/agentweave.db" py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1`.
Read its startup line to confirm the database. **Never touch `:8000`.** The account is **Copilot
Free**: Auto model only, a small monthly allowance. Keep prompts to one short sentence and the whole
drive to at most **four** model-calling turns. Record each figure verbatim in design.md's round log.

- [ ] 7.1 Bind a Copilot agent (slice 2's runner, model Auto) in the trial project. Send "Reply with
  the word OK." Read its `turn_usage` row (`mode=ro` SQLite read of the trial database). `total_tokens`
  equals the sum of the run's `assistant.usage` events in the run's log, and `ai_nano_aiu` and
  `session_nano_aiu_total` are set. `GET /accounting`: `budget.used_tokens` rose by exactly the
  tokens, and `project.ai_nano_aiu` equals the row's
- [ ] 7.2 In the app: the Budgets section shows the credits line and the agent chip, the Overview
  shows credits, the conversation header shows `… tokens · X AI credits`, and the turn's "Worked for"
  line shows the credits. A Claude agent's turn in the same project shows no credits
- [ ] 7.3 A second turn in the **same conversation** (a resumed session): its `ai_nano_aiu` equals its
  `session_nano_aiu_total` minus 7.1's. That answers whether the checkpoint total continues across
  `session/load` (design table, INFERRED until now). **This gates D4 (review finding 4; R3 had said
  it did not).** If it continued, D4 stands. If it restarted from zero, D4's larger-of rule charges
  the per-call sum only while no call event is lost; with one lost it charges `K' − S` and
  under-charges by up to the previous total. So in that case stop and revise D4 before archive: a
  run on a loaded session charges `max(K', P)` and takes premium requests from its own checkpoint
  alone, tests 1.8(a) and (e) and the `usage-accounting` credits paragraph are rewritten, and the
  run's `ai_nano_aiu` is checked against its own checkpoint. Record which it was. Also record this
  resumed turn's prompt-result `usage` beside its per-call sum (Q10). If the result includes 7.1's tokens,
  stop and make the per-call sum authoritative on a loaded session (design D3)
- [ ] 7.4 Record the run's `quotaSnapshots` keys and which one's `usedRequests` rose. Record whether
  the ACP prompt result and the per-call sum agreed (the ledger's warning log line, if any)
- [ ] 7.5 Optional, only if 7.1–7.3 used little allowance: `/compact` in the same conversation (one
  compaction model call). Record whether an `assistant.usage` accompanied `session.compaction_complete`
  (same `providerCallId` as its `requestId`) and that the run's credits were counted once
- [ ] 7.6 Thresholds with no model call: with the project's checkpoint mode `offered`, post a synthetic
  66% reading for the Copilot agent's conversation through `POST /agents/{name}/context-usage`
  (`api/v1/agents.py:2980`), carrying that conversation's provider `session_id`, `status: "measured"`,
  `source`, `observed_at`, `context_tokens`, `limit_tokens` **and `percent: 66`**. The route does not
  derive `percent` when `limit_tokens` is present (`output_recording.py:139-140`), and without it no
  banner can appear (the route resolves the conversation from the session,
  `output_recording.py:173-189`, and hands the reading to `consider_from_reading`, `:233-238`). The conversation shows the checkpoint-due banner. The same
  reading for the Claude agent shows nothing. The Copilot agent's settings show the "compacts at
  about 80%" line
- [ ] 7.7 The hold, by fixture: quota exhaustion cannot be reached on Free. Replay 1.15's event
  sequence through the executor on `:8010` if slice 2 offers a replay seam, and read `GET /queue`
  status: it names the hold and the reset. If there is no seam, record that the hold is verified by
  task 1.15 only, and leave test-guide Human-only item 3 open

## 8. Archive

- [ ] 8.1 Sync the three delta specs into `openspec/specs/` (`openspec-sync-specs`), archive the
  change, and record slice 4 as done in the exploration's slice list
- [ ] 8.2 File a finding (or append to an open one) asking for the first real Copilot quota refusal's
  `session.error` payload, captured by task 5.2's log, so that D8's recognition is confirmed or
  corrected. Copy the Q6 decision (2026-09-28: keep the month-long hold; its notice states the reset
  date and the rebind-then-message way out) and the Q7 decision (2026-09-28: option (b)) into
  DECISIONS
