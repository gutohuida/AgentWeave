## 0. Rounds. No task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent comparison of the proposal against the code at the then-current
  `HEAD`. Re-derive design.md's call-site table (grep `run_secrets.` in `hub/hub`), the mapper's
  emission order at every boundary (`CopilotEventMapper.on_session_update`, `flush`, `finish`,
  `fail_turn`), and every claim tagged INFERRED. In particular: whether a Claude or Codex run can
  register an ambient `COPILOT_PROVIDER_API_KEY` (`agent_trigger.py:1472`, `:1616`, each
  `guard_env`); whether anything other than `record_agent_output` broadcasts model text; and
  whether slice 5 group A's edits (uncommitted during R1) changed any flush path. Re-run D1's
  prototype table yourself. Decide whether the `session.error` log line
  (`copilot_acp.py:1922-1934`) is filed as its own finding. Record the result in the round log.
  **Done 2026-10-04 at `4c054be`:** design survives; 10 corrections in the round log (line numbers;
  raw-event cards now flush, a new boundary; Copilot's notification path swallows a raise, so
  "fails closed" not "fails the run"; Claude/Codex runs can register a key; `scrub_stream` must sit
  beside `sequence += 1`; short-value false positives measured; log line folded in as D6).
- [x] 0.2 R3: a second independent comparison, not a re-read of R2. Also ask what each changed
  call site does when `scrub_stream` raises. Re-derive the `copilot_acp.py` numbers once
  `_after_open_blocks` is committed (R2 read it as an uncommitted diff). `openspec validate
  a-secret-split-across-two-events-is-still-scrubbed --strict` passes.
  **Done 2026-10-04 at `13f7421`:** design survives with one substantive fix: whitespace at an event
  boundary (Copilot's unstripped thinking) defeated D1 entirely, now skipped; task 1.5 as written
  could not fail on the wrong placement, now locks at `commit`; 1.2 must end `completed`; D6 guarded
  so a raise cannot drop the error card; bound re-measured (worst exactly `m - 1`); line numbers
  re-derived; validate passes. Ten corrections in the round log.
- [x] 0.3 The pre-approval Opus adversarial review of the change and its decisions (D1-D5, open
  questions 1-4). Record its findings and what was done about each in the round log.
  **Done 2026-10-04 at `9e9bb83`** (no `hub/hub` change since `13f7421`): five findings, each
  re-measured (`scratchpad/f488rev/subm.py`, `order.py`, `adv.py`). 1.2 now runs every boundary
  at a split below *m* and asserts exact rows; `register` strips (D7, new 1.1 row); a value
  containing whitespace is a stated non-goal; 1.8's mutation replaced (the reviewer's
  `asyncio.sleep(0)` cannot be caught, measured; the scrub moved into the write closure can);
  over-redaction, tail lifetime and MCP-written content recorded. Open questions 1-3 unchanged.
- [x] 0.4 The operator approves the change in `spec-queue/APPROVALS.md`, and answers open
  questions 1-3 (hold or not, and *m*, including the short-value floor; joining across tool
  cards; folding in the log line).
  **APPROVED 2026-10-04** (`spec-queue/APPROVALS.md`, operator: "APPROVED, fold the log in"):
  no hold, `m = min(8, len // 2)` with no floor; join across tool and other cards; D6 folded in.
  Recorded as DECIDED in design.md's open questions.

## 1. Tests first. Each must fail on today's code unless marked as a control

- [x] 1.1 `hub/tests/test_run_secrets_stream.py` (new), unit cases on
  `run_secrets.scrub_stream(run_id, event)` with `plainproxykey123` registered, one parametrised
  row per row of design D1's prototype table (thought→message, message→tool_call→message,
  message→thought split at 5, message→finish dangling, three-way, the `explai` false positive,
  and R3's two whitespace rows: thinking `I will use plainproxy\n\n` then text `key123 now.`, and
  text `Key: plainpr` then thinking `\n oxykey123 hmm`, with the whitespace kept as written in the
  output), plus: a value registered next to a longer value that contains it is replaced whole, once;
  `payload["text"] == content` after every rewrite; a `tool_use`/`tool_result`/`error` event is
  returned unchanged and does not move the tail; `forget` drops the tail, so a value split across
  a forget and a new registration is not joined. (Review) Registration strips (design D7):
  with `plainproxykey123\n` registered, `use plainproxykey123 now` is scrubbed by `scrub` and by
  `scrub_stream` alike (today it is stored unchanged, measured), the raw value is still replaced
  where it occurs as written, and a whitespace-only value registers nothing. **Fails today:**
  `run_secrets` has no `scrub_stream` (AttributeError); the strip row fails on `scrub` alone.
  **Done.** `hub/tests/test_run_secrets_stream.py`: 16 tests (8 D1 rows, other kinds, nested
  value, forget, late call, nothing-registered control, reversed order, strip, whitespace-only).
  Fail-before: 16/16 (AttributeError on `scrub_stream`; the strip and whitespace-only rows on
  `scrub`/`registered` themselves).
- [x] 1.2 In `hub/tests/test_copilot_byok_env.py`, beside
  `test_a_provider_key_is_scrubbed_from_everything_its_run_records`:
  `test_a_provider_key_split_across_events_is_scrubbed`, parametrised over thought→message,
  message→tool_call→message, message→thought, message→finish (dangling), and the raw-event card
  boundaries: text→`session.error`→echo chunk→text, thought→root `session.compaction_complete`→text,
  text→`subagent.completed`→text (design, boundary table), and (R3) thought chunks ending in
  `plainproxy\n\n` → a message beginning `key123`, which the mapper records with the thought's
  whitespace intact (`_flush_thought` does not strip). The raw events are fed through
  `mapper.on_raw_event` in wire order between the `session/update` chunks. The fake
  `copilot_acp.run_turn` builds a **real** `CopilotEventMapper`, feeds it ACP `session/update`
  params shaped as the wire sends them (`{"sessionUpdate": "agent_thought_chunk", "content":
  {"type": "text", "text": …}}`, a `tool_call` with a `toolCallId`), passes every event each call
  returns to `on_event` **in the order returned**, and ends with `mapper.finish()`. The fixture's
  order is therefore the mapper's, not hand-written (CLAUDE.md, F190). The fake returns a
  **completed** `TurnOutcome` (R3: a failed one sends the input back to the queue and makes a run per
  retry, as `test_a_provider_key_is_scrubbed_from_everything_its_run_records` notes at `:969`).
  Assert: no stored `AgentOutput` row and no `agent_output` broadcast contains the key, and the
  `text`/`thinking` rows' contents, ordered by `sequence`, each stripped and concatenated with
  nothing between them, do not contain it either (R3: "two consecutive rows" missed the
  tool-card case, where the two text rows are not consecutive); and **every stored row's `kind`
  and `content`, in `sequence` order, equals the expected list exactly** (review: "carries
  `<redacted>`" passes with a broken join, because at a split of *m* or more the dangling-start
  rule alone redacts the first half and the concatenation `I will use <redacted>key123 now.` no
  longer spells the key). The tool, error and status rows are unchanged and between the text rows.
  **Every boundary case runs twice** (review): at the split above (10|6, 8|8) and at a split
  **below *m***, `plainpr` + `oxykey123` (7|9), where the dangling-start rule does not fire and only
  the carried tail can redact anything. Expected rows at 7|9 (measured through the committed mapper,
  `scratchpad/f488rev/subm.py`): thought→message `I will use plainpr` / `<redacted> now.`;
  message→tool→message `Key: plainpr` / tool_use / tool_result / `<redacted> done`; error card
  `a plainpr` / `boom` / `<redacted> b` (the echo is dropped); compaction `use plainpr` / status /
  `<redacted> now`; subagent `k plainpr` / `explore finished` / `<redacted> z`; whitespace
  `I will use plainpr\n\n` / `<redacted> now.`; plus a three-way case at 3|4|9 (`x pla` / `inpr` /
  `<redacted> y`). message→thought is already 5|11 and message→finish is one event (no join; it
  tests the dangling rule only). **Fails today:** the rows are `I will use plainproxy` and
  `key123 now.`. Each half passes the per-event scrub, and their concatenation contains the key.
  **Done.** `test_a_provider_key_split_across_events_is_scrubbed`, 15 cases (each boundary at
  10|6 or 8|8 and at 7|9, plus message→thought 5|11, message→finish, three-way 3|4|9), each
  thought/message streamed as two wire chunks. Exact rows asserted, including the run's closing
  `Run completed (exit 0).` status row. Fail-before: 15/15 (e.g. `I will use plainproxy` /
  `key123 now.`; message→finish fails on the dangling row).
- [x] 1.3 Order guard, in the same file: the thought→message case asserts that the thinking row's
  `sequence` is lower than the text row's. A second assertion feeds the mapper's output to the
  scrub **reversed** and shows the expected rows differ. A test whose fixture order the mapper
  cannot produce would not notice that. **Fails today** with 1.2, for the same reason.
  **Done.** `test_the_split_rows_follow_the_order_the_mapper_emits` (sequence order + exact rows;
  fail-before 1/1) and `test_reversing_the_emitted_order_changes_the_rows` in the unit file.
- [x] 1.4 The `exec` stream executor (`_execute_run`): a Claude run whose stream holds a `thinking`
  block ending in `plainproxy` and then a `text` block beginning with `key123`, as two `assistant`
  lines of one block each, which is how the stream-json fixtures in `test_agent_trigger.py`
  (`_F359_LINES`, `:3127`) shape them, with the run's value registered. Patch `agent_trigger.run_secrets.register` so the run
  registers `plainproxykey123`. (R2: a Claude run registers one in production when the Hub's
  environment or the agent's `env_vars` carry `COPILOT_PROVIDER_API_KEY`; a second case may set
  that in `env_vars` instead of patching.) Reuse the fake-process harness an existing `_execute_run` stream test uses. Assert the
  same as 1.2. **Fails today:** the two rows hold the two halves.
  **Done.** `test_agent_trigger.py::test_a_registered_value_split_across_claude_blocks_is_scrubbed`,
  10|6 and 7|9, `run_secrets.register` patched to the key, through `_f359_trigger`/`_fake_pty`.
  Asserts the `text`/`thinking` rows exactly (the `exec` run's other status rows are not listed)
  and that no row or payload carries the key. Fail-before: 2/2.
- [x] 1.5 Placement guard: in the 1.2 harness (thought→message case), make the first attempt of the
  text row's write raise `OperationalError("database is locked")` **after the real
  `record_agent_output` has run up to its commit**: wrap `agent_trigger.record_agent_output` so
  that, for that sequence's first attempt only, it calls the real function with a session whose
  `commit` raises the lock. R3: raising at session creation, or raising from the wrapper before
  calling the real function (as the F359 tests at `test_agent_trigger.py:3170-3215` do), never
  runs the in-function code on the failed attempt, so this test would pass with the stream scrub
  wrongly inside `record_agent_output`. Assert the stored rows equal the no-retry case. **Control:**
  passes once group 2 is built as designed. Record that it FAILS with the stream scrub moved
  inside `record_agent_output`: the tail takes the text twice, and R3's prototype shows the retried
  row is then stored as `key123 now.`, unredacted.
  **Done.** `test_a_retried_locked_write_stores_the_same_split_rows` (10|6 and 7|9): the text row's
  first attempt runs the real `record_agent_output` on a session proxy whose `commit` raises
  `database is locked`. Failed before group 2 too (2/2, nothing joined); passes with it.
  Mutation: stream scrub moved into `record_agent_output` (both executor calls removed) → 1.5
  FAILS 2/2 while every 1.2 and 1.4 case still passes, so only this test guards the placement.
- [x] 1.6 Controls, passing before and after: `test_a_provider_key_is_scrubbed_from_everything_its_run_records`
  and `test_the_registry_scrubs_only_its_own_runs_values` unchanged; a run with nothing registered
  records text and thinking byte-identical to what the mapper emitted, and `run_secrets` holds no
  state for it; `hub/tests/test_operator_is_told_the_truth.py` and
  `hub/tests/test_write_paths_on_run_events.py` (F278's) pass unchanged. Run them before group 2
  and record the count.
  **Done.** Controls (`test_a_provider_key_is_scrubbed_from_everything_its_run_records` x2,
  `test_the_registry_scrubs_only_its_own_runs_values`, `test_operator_is_told_the_truth.py`,
  `test_write_paths_on_run_events.py`) with the four source files swapped back to HEAD:
  58 passed (the new nothing-registered unit control fails there only on the missing API);
  with the fix: 59 passed.
- [x] 1.7 The log line (design D6, if open question 3 is "fold in"): with a key registered, feed
  `run_turn`'s armed raw-event path a `session.error` whose `message` quotes the key, and assert
  with `caplog` that no record of the `copilot_acp` logger contains it and the `Copilot
  session.error` line is still written. A second case puts the key across the 2000-character cut
  and asserts no prefix of `m` or more characters survives. A third case (R3) makes the log
  call's scrub raise and asserts the line is logged without its payload and the `session.error`
  card still reaches `on_event` (design D6, *If that scrub raised*). **Fails today:** the payload is
  logged whole.
  **Done.** In `test_copilot_acp_run_turn.py`, through the real `run_turn` (`_drive`, `env` with
  `AW_RUN_ID`): the key quoted in the message; the key across the 2000-character cut (asserts no
  8-character prefix); and a raising scrub (line logged with `payload=<unavailable>`, the error
  event still emitted, outcome `failed`). Fail-before: 3/3.
- [x] 1.8 Order under interleaving: two `_on_event` calls for one run (`I will use plainpr` then
  `oxykey123 now.`, the 7|9 split, so only the tail can redact), started as two tasks from the fake
  `run_turn`, whose writes complete in the reverse order: wrap `agent_trigger._record_observation`
  (module-global, called by name from `_on_event`) so that, for the first of the two events' `what`
  (`output <n>`), it awaits an `asyncio.Event` before delegating to the real function; the test sets
  the event only after the second `_on_event` has returned. The first call is then blocked **before its write closure is
  invoked**. The stored rows, read by `sequence`, equal the sequential case exactly. **Fails today**
  (nothing joins). **Mutation (review, corrected):** after group 2, move the `scrub_stream` call
  into the write closure (`lambda db, …: record_agent_output(…, content=scrub_stream(…).content, …)`);
  record that 1.8 then FAILS, because the second event is scrubbed against an empty tail and the
  first against a tail ending in `oxykey123 now.`. The reviewer's suggested mutation, an
  `await asyncio.sleep(0)` before the scrub, cannot be caught by any test and is not used: asyncio
  resumes ready tasks in FIFO order, so both calls still scrub in `sequence` order (measured,
  `scratchpad/f488rev/order.py`: sync and `sleep(0)` keep order, the closure placement reverses it).
  The hazard is an `await` that waits on something else (a session, a lock), which is what the
  closure placement puts there.
  **Done.** `test_interleaved_writes_are_scrubbed_in_sequence_order`: the fake `run_turn` starts both
  `on_event` calls as tasks; the first's `_record_observation` is held on an `asyncio.Event`
  until the second returns. Fail-before: 1/1. Mutation (scrub moved into `_on_event`'s write
  closure) → FAILS.

## 2. The fix

- [x] 2.1 `hub/hub/run_secrets.py`: a per-run tail beside `_by_run`, and
  `scrub_stream(run_id, event)` implementing design D1 (join, mark occurrences longest first, mark
  the dangling start of at least `m(v) = max(1, min(8, len(v) // 2))` characters, collapse each
  marked run in the new content to one `<redacted>`, keep the unredacted tail). It returns a new
  `RunEvent` with `content` and `payload["text"]` rewritten for `text`/`thinking`, and returns any
  other event unchanged. A run with nothing registered returns the event unchanged and creates no
  state. Whitespace at an event boundary is skipped (D1 steps 1, 2 and 4) and kept as written in
  the output. `forget` drops the tail. `register` keeps each value stripped, and the raw value too
  when it differs, dropping any that strip to empty (design D7). Update the module docstring's
  "Every writer…" paragraph to explain the stream case and cite F488.
  **Done.** `scrub_stream`, `_tail_by_run`, `dangling_minimum`, `forget` drops the tail, `register` strips.
- [x] 2.2 `hub/hub/api/v1/agent_trigger.py`: call `run_secrets.scrub_stream(run_id, event)` once
  per event, before building the `_record_observation` write, at `_execute_run`'s event loop and
  at `_execute_rpc_run`'s `_on_event`, **in the same synchronous step as `sequence += 1`** (no
  `await` between them; design, *Order and concurrency*). Use the scrubbed event for the write,
  bound to the write's lambda as a default argument at both sites (the `exec` loop already binds
  `event=event`; `_on_event`'s lambda reads `event` from its closure today), so every retry of
  that write uses the one scrubbed event and never scrubs again. `outside_writes.note`
  keeps the original event: it reads `write_paths`, which this does not change. No broad `except`
  around the call (design, *What each caller returns when this raises*).
  **Done.** Both sites call `scrub_stream` right after `sequence += 1`; the result is bound as the
  write lambda's `event=` default; `outside_writes.note` keeps the original event; no `except`.
- [x] 2.3 `hub/hub/output_recording.py`: amend `record_agent_output`'s docstring. Its per-event
  scrub is the floor, and joining across events happens at the executors, because a retry re-invokes
  this function.
  **Done.**
- [x] 2.4 `hub/hub/copilot_acp.py` (if open question 3 is "fold in"): in `_on_armed_raw_event`, pass
  `data` through `run_secrets.scrub(env.get("AW_RUN_ID") if env else None, data)` before
  `json.dumps` and before the `[:2000]` cut (design D6). If that raises, log the line without its
  payload and go on to the ledger and the mapper; never log the unscrubbed payload. Nothing else in
  the line changes.
  **Done.** `json.dumps(run_secrets.scrub(AW_RUN_ID, data))[:2000]` inside a `try`; a raise logs
  `payload=<unavailable>` and the ledger and mapper still run.
- [x] 2.5 Run the files from group 1 with `claude` stripped from PATH, then the code-quality block.
  **Done.** The group-1 files with `claude` stripped from PATH: 54 passed. `ruff check src/ hub/
  tests/` clean; `black --check` (with and without `--target-version py311`) clean on the touched
  files.
  **Mutation checks (test guide 2), each on a scratch copy, restored and hash-checked:** drop the
  tail → 23 fail (every multi-event row of 1.2 at both splits; message→finish passes, as stated);
  drop the dangling rule → 13 fail (message→finish, three-way, 1.2's 10|6/8|8 rows; every 7|9 row
  passes); `m = 1` → 6 fail incl. the `explai` row; drop the boundary-whitespace skip → 4 fail
  (1.1's two whitespace rows, 1.2's two blank-line rows); scrub inside `record_agent_output` →
  1.5 fails (2); exec site missing → 1.4 fails (2); RPC site missing → 1.2 fails (15); scrub in
  the RPC write closure → 1.8 fails; `register` unstripped → the strip row fails; log line
  unscrubbed → 1.7 fails (3); log-scrub raise propagates → 1.7's third case fails.

## 3. Verify

- [x] 3.1 Full Hub suite: `py -3.11 -m pytest hub/tests/ -q` (`-n 8` for speed; any failure seen
  only under `-n` is re-run serially before it counts), with `claude` stripped from PATH. Tick
  only with the count on this line, as `N passed, M skipped, 0 failed at <sha>`.
  **6688 passed, 93 skipped, 0 failed at the implementation commit (worktree on `7caf6a8`)**,
  `-n 8`, `claude` stripped from PATH, 21m31s.
- [ ] 3.2 Full CLI suite: `py -3.11 -m pytest tests/ -q`. Tick only with the count on this line.
  Run 2026-10-04: 562 passed, 4 skipped, 2 failed, neither caused by this change:
  `test_every_ticked_full_suite_task_in_flight_carries_its_count` flags task 2.7 of
  `a-copilot-agent-uses-hooks-and-its-own-agents`, and `test_mirrored_skill_trees_match_the_source
  [Codex (user-level)]` reports this machine's user-level skill mirror stale (`e2e-loop/e2e.py`).
  Left unticked until those are cleared.
- [x] 3.3 Lint exactly as CI runs it (`.github/workflows/ci.yml`): `ruff check src/ hub/ tests/`;
  `ruff check scripts/ --select E9,F63,F7,F82,F401,F841`; `black --check src/ hub/hub/ hub/tests/
  tests/`, both with and without `--target-version py311` (DEAD-ENDS 2026-10-03); `mypy src/`;
  `cd hub/ui && npm run lint`. Use `py -3.11 -m ruff` and `py -3.11 -m black` on this machine.
  **Done** for the Python half: `ruff check src/ hub/ tests/` clean; `ruff check scripts/ --select
  ...` clean; `black --check --target-version py311 hub/hub/ hub/tests/` 635 unchanged, plain
  `black --check` on the 8 touched files clean; `mypy src/` clean. `npm run lint` not run: no UI
  file touched.
- [ ] 3.4 Drive, on a throwaway Hub port started from `hub/` with its own trial database (never
  `:8000`; not the `:8010` instance if anything is in flight there), as slice 5 task 3.5 drove:
  a Copilot provider runner against a local fake Anthropic provider that streams a thinking block
  ending in the first ten characters of the run's key and a text block starting with the rest,
  then a text block, a tool call and a text block split the same way, and (R3) once more with the
  thinking block ending in a blank line after the ten characters. Count the key's
  occurrences in `agent_output` rows, `event_log`, the run's SSE frames, the timeline route's
  response and the Hub log. All must be 0. Paste the stored rows into design.md's round log.
- [ ] 3.5 Close F488 in `scripts/drive/FINDINGS.md` with the commit and test names and the stated
  residual (a dangling start shorter than *m* is shown). Regenerate the backlog.
