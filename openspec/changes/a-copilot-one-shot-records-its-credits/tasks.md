## 0. Rounds and decision

- [x] 0.1 R1: explore and propose (2026-10-03 night, iter 21). Record it in `design.md`'s round log
- [ ] 0.2 R2: re-derive the proposal independently against the code. Re-read the capture line by line rather than from design's list. Grep every caller of `parse_copilot_envelope` and `parse_envelope`, and every reader of `WorkerInvocation.ai_nano_aiu`/`premium_requests`. Confirm `COPILOT_ONE_SHOT_FLAGS` cannot resume a session, and that `_interpret` carries usage on each exit D4 names. Record the result in the round log
- [ ] 0.3 R3: a second independent re-derivation. `openspec validate a-copilot-one-shot-records-its-credits --strict` passes
- [ ] 0.4 Adversarial Opus review over the change and its decisions, then an OPEN approval row in `spec-queue/DECISIONS.md`
- [ ] 0.5 The operator approves the change (and answers Open question 1 for the sibling), recorded in `spec-queue/DECISIONS.md`

## 1. Tests first

- [ ] 1.1 Design tests 1, 3, 4 and 5 in `hub/tests/test_worker.py`, against the real capture (`fixtures/copilot_acp/oneshot_ok.jsonl`), edited line by line where a test needs another stream. Test 1 replaces `test_the_captured_copilot_one_shot_has_no_session_shutdown`. 1, 3 and 4 fail today, and 5 passes today as a guard
- [ ] 1.2 Design test 2 (through `run_worker` to the `worker_invocations` row, unpatched parser). It fails today
- [ ] 1.3 Design test 6 (non-finite, the parser and the ledger). The ledger half fails today
- [ ] 1.4 Restate `test_the_captured_copilot_envelope_yields_its_answer`'s assertion message (design, "Tests that can fail", last paragraph)

## 2. The fix

- [ ] 2.1 `copilot_usage.py`: `checkpoint_totals(data)`, with `_nonneg_number` plus a `math.isfinite` check, used by `CopilotUsageLedger.observe_event` (design D2, the `inf` bullet)
- [ ] 2.2 `runner_adapters/copilot.py`: `parse_copilot_envelope` keeps the last checkpoint and returns `WorkerUsage(ai_nano_aiu=..., premium_requests=...)` on all three exits, and its docstring says so (design D1, D4)
- [ ] 2.3 `py -3.11 -m pytest hub/tests/test_worker.py hub/tests/test_copilot_usage*.py hub/tests/test_runner_adapters_imports.py hub/tests/test_title_generation.py hub/tests/test_copilot_byok_env.py -q`, then the full `hub/tests/` with `claude` stripped from PATH, then the lint block (ruff, black `--target-version py311`, mypy)

## 3. Drive (Copilot Free plan, Auto: at most 2 calls)

- [ ] 3.1 On the trial Hub `:8010`, give a Copilot runner's agent a checkpoint (the operator's Checkpoint button, one real one-shot plus its probe). Read the new `worker_invocations` rows `mode=ro` from the trial database: `ai_nano_aiu` and `premium_requests` are non-NULL for both the `checkpoint` and the `checkpoint_probe` rows, and `cli = 'copilot'`. Record the figures, and record that `GET /accounting` shows none of them (design D5, expected)
- [ ] 3.2 Compare the figures with the Copilot CLI's own report of the same calls, if one can be read without an interactive session. If none can (as task 7.1 of `a-copilot-agent-uses-hooks-and-its-own-agents` found for `/usage`), record "not compared: no independent reading"
