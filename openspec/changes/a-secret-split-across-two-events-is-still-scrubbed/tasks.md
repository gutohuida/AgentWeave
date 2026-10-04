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
- [ ] 0.2 R3: a second independent comparison, not a re-read of R2. Also ask what each changed
  call site does when `scrub_stream` raises. Re-derive the `copilot_acp.py` numbers once
  `_after_open_blocks` is committed (R2 read it as an uncommitted diff). `openspec validate
  a-secret-split-across-two-events-is-still-scrubbed --strict` passes.
- [ ] 0.3 The pre-approval Opus adversarial review of the change and its decisions (D1-D5, open
  questions 1-4). Record its findings and what was done about each in the round log.
- [ ] 0.4 The operator approves the change in `spec-queue/APPROVALS.md`, and answers open
  questions 1-3 (hold or not, and *m*, including the short-value floor; joining across tool
  cards; folding in the log line).

## 1. Tests first. Each must fail on today's code unless marked as a control

- [ ] 1.1 `hub/tests/test_run_secrets_stream.py` (new), unit cases on
  `run_secrets.scrub_stream(run_id, event)` with `plainproxykey123` registered, one parametrised
  row per row of design D1's prototype table (thought→message, message→tool_call→message,
  message→thought split at 5, message→finish dangling, three-way, the `explai` false positive),
  plus: a value registered next to a longer value that contains it is replaced whole, once;
  `payload["text"] == content` after every rewrite; a `tool_use`/`tool_result`/`error` event is
  returned unchanged and does not move the tail; `forget` drops the tail, so a value split across
  a forget and a new registration is not joined. **Fails today:** `run_secrets` has no
  `scrub_stream` (AttributeError).
- [ ] 1.2 In `hub/tests/test_copilot_byok_env.py`, beside
  `test_a_provider_key_is_scrubbed_from_everything_its_run_records`:
  `test_a_provider_key_split_across_events_is_scrubbed`, parametrised over thought→message,
  message→tool_call→message, message→thought, message→finish (dangling), and the raw-event card
  boundaries: text→`session.error`→echo chunk→text, thought→root `session.compaction_complete`→text,
  and text→`subagent.completed`→text (design, boundary table). The raw events are fed through
  `mapper.on_raw_event` in wire order between the `session/update` chunks. The fake
  `copilot_acp.run_turn` builds a **real** `CopilotEventMapper`, feeds it ACP `session/update`
  params shaped as the wire sends them (`{"sessionUpdate": "agent_thought_chunk", "content":
  {"type": "text", "text": …}}`, a `tool_call` with a `toolCallId`), passes every event each call
  returns to `on_event` **in the order returned**, and ends with `mapper.finish()`. The fixture's
  order is therefore the mapper's, not hand-written (CLAUDE.md, F190). Assert: no stored
  `AgentOutput` row, no `agent_output` broadcast, and no concatenation of two consecutive rows'
  content (ordered by `sequence`) contains the key; the rows carry `<redacted>` where design D1
  says; the tool row is unchanged and between the two text rows. **Fails today:** the rows are
  `I will use plainproxy` and `key123 now.`. Each half passes the per-event scrub, and their
  concatenation contains the key.
- [ ] 1.3 Order guard, in the same file: the thought→message case asserts that the thinking row's
  `sequence` is lower than the text row's. A second assertion feeds the mapper's output to the
  scrub **reversed** and shows the expected rows differ. A test whose fixture order the mapper
  cannot produce would not notice that. **Fails today** with 1.2, for the same reason.
- [ ] 1.4 The `exec` stream executor (`_execute_run`): a Claude run whose stream holds one assistant
  message with a `thinking` block ending in `plainproxy` and a `text` block beginning with
  `key123`, with the run's value registered. Patch `agent_trigger.run_secrets.register` so the run
  registers `plainproxykey123`. (R2: a Claude run registers one in production when the Hub's
  environment or the agent's `env_vars` carry `COPILOT_PROVIDER_API_KEY`; a second case may set
  that in `env_vars` instead of patching.) Reuse the fake-process harness an existing `_execute_run` stream test uses. Assert the
  same as 1.2. **Fails today:** the two rows hold the two halves.
- [ ] 1.5 Placement guard: in the 1.2 harness, make the first attempt of the second text row's
  write raise `OperationalError("database is locked")` (patch `async_session_factory` for one
  call, as the F359 tests do), and assert the stored rows equal the no-retry case. **Control:**
  passes once group 2 is built as designed. Record that it FAILS with the stream scrub moved
  inside `record_agent_output` (the tail takes the text twice, and the same text is matched
  against itself).
- [ ] 1.6 Controls, passing before and after: `test_a_provider_key_is_scrubbed_from_everything_its_run_records`
  and `test_the_registry_scrubs_only_its_own_runs_values` unchanged; a run with nothing registered
  records text and thinking byte-identical to what the mapper emitted, and `run_secrets` holds no
  state for it; `hub/tests/test_operator_is_told_the_truth.py` and
  `hub/tests/test_write_paths_on_run_events.py` (F278's) pass unchanged. Run them before group 2
  and record the count.
- [ ] 1.7 The log line (design D6, if open question 3 is "fold in"): with a key registered, feed
  `run_turn`'s armed raw-event path a `session.error` whose `message` quotes the key, and assert
  with `caplog` that no record of the `copilot_acp` logger contains it and the `Copilot
  session.error` line is still written. A second case puts the key across the 2000-character cut
  and asserts no prefix of `m` or more characters survives. **Fails today:** the payload is logged
  whole.
- [ ] 1.8 Order under interleaving: two `_on_event` calls for one run whose writes are made to
  complete in the reverse order (the first write's `_record_observation` blocked on an event until
  the second has returned). The stored rows, read by `sequence`, carry `<redacted>` exactly as in
  the sequential case. **Fails today** (nothing joins). After group 2, record that it also FAILS
  with the `scrub_stream` call moved after the first `await` in `_on_event`.

## 2. The fix

- [ ] 2.1 `hub/hub/run_secrets.py`: a per-run tail beside `_by_run`, and
  `scrub_stream(run_id, event)` implementing design D1 (join, mark occurrences longest first, mark
  the dangling start of at least `m(v) = max(1, min(8, len(v) // 2))` characters, collapse each
  marked run in the new content to one `<redacted>`, keep the unredacted tail). It returns a new
  `RunEvent` with `content` and `payload["text"]` rewritten for `text`/`thinking`, and returns any
  other event unchanged. A run with nothing registered returns the event unchanged and creates no
  state. `forget` drops the tail. Update the module docstring's "Every writer…" paragraph to
  explain the stream case and cite F488.
- [ ] 2.2 `hub/hub/api/v1/agent_trigger.py`: call `run_secrets.scrub_stream(run_id, event)` once
  per event, before building the `_record_observation` write, at `_execute_run`'s event loop and
  at `_execute_rpc_run`'s `_on_event`, **in the same synchronous step as `sequence += 1`** (no
  `await` between them; design, *Order and concurrency*). Use the scrubbed event for the write. `outside_writes.note`
  keeps the original event: it reads `write_paths`, which this does not change. No broad `except`
  around the call (design, *What each caller returns when this raises*).
- [ ] 2.3 `hub/hub/output_recording.py`: amend `record_agent_output`'s docstring. Its per-event
  scrub is the floor, and joining across events happens at the executors, because a retry re-invokes
  this function.
- [ ] 2.4 `hub/hub/copilot_acp.py` (if open question 3 is "fold in"): in `_on_armed_raw_event`, pass
  `data` through `run_secrets.scrub(env.get("AW_RUN_ID") if env else None, data)` before
  `json.dumps` and before the `[:2000]` cut (design D6). Nothing else in the line changes.
- [ ] 2.5 Run the files from group 1 with `claude` stripped from PATH, then the code-quality block.

## 3. Verify

- [ ] 3.1 Full Hub suite: `py -3.11 -m pytest hub/tests/ -q` (`-n 8` for speed; any failure seen
  only under `-n` is re-run serially before it counts), with `claude` stripped from PATH. Tick
  only with the count on this line, as `N passed, M skipped, 0 failed at <sha>`.
- [ ] 3.2 Full CLI suite: `py -3.11 -m pytest tests/ -q`. Tick only with the count on this line.
- [ ] 3.3 Lint exactly as CI runs it (`.github/workflows/ci.yml`): `ruff check src/ hub/ tests/`;
  `ruff check scripts/ --select E9,F63,F7,F82,F401,F841`; `black --check src/ hub/hub/ hub/tests/
  tests/`, both with and without `--target-version py311` (DEAD-ENDS 2026-10-03); `mypy src/`;
  `cd hub/ui && npm run lint`. Use `py -3.11 -m ruff` and `py -3.11 -m black` on this machine.
- [ ] 3.4 Drive, on a throwaway Hub port started from `hub/` with its own trial database (never
  `:8000`; not the `:8010` instance if anything is in flight there), as slice 5 task 3.5 drove:
  a Copilot provider runner against a local fake Anthropic provider that streams a thinking block
  ending in the first ten characters of the run's key and a text block starting with the rest,
  then a text block, a tool call and a text block split the same way. Count the key's
  occurrences in `agent_output` rows, `event_log`, the run's SSE frames, the timeline route's
  response and the Hub log. All must be 0. Paste the stored rows into design.md's round log.
- [ ] 3.5 Close F488 in `scripts/drive/FINDINGS.md` with the commit and test names and the stated
  residual (a dangling start shorter than *m* is shown). Regenerate the backlog.
