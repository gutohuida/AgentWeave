## 0. Rounds and decision

- [x] 0.1 R2: re-derive the proposal independently. Grep every spawn of a model CLI in `hub/hub` (`subprocess`, `resolve_executable`, `run_worker`, `build_title_command`, `build_worker_command`) and confirm that the checkpoint, the probe and the titler are the only out-of-band spenders. Grep every reader of `project_budget_state` and `accounting_snapshot`. Re-derive the Claude and Codex normalisation from `runner_parsing.py` rather than from design D1. Re-measure `worker_invocations` on `:8000` `mode=ro` only. Record the result in `design.md`'s round log
- [x] 0.2 R3: a second independent re-derivation. `openspec validate worker-spend-counts-against-the-budget --strict` passes
- [ ] 0.3 The operator answers D7's worker question (counted and gated / own line only / counted never refused), recorded in `spec-queue/DECISIONS.md`

## 1. Tests first

- [ ] 1.1 Design tests 1, 2 (normalisation). Both fail today
- [ ] 1.2 Design tests 3, 4, 5, 14 (totals, order, budget, PATCH agreement). 3 and 5 fail today
- [ ] 1.3 Design tests 6, 7, 8, 9, 10, 10b, 10c, 10d, 10e (the triggers' pre-check, the gate and its initiators). 6, 10, 10b and 10d fail today
- [ ] 1.4 Design tests 11, 12 (titler). 11 fails today, and 12 passes as a control before and after
- [ ] 1.5 Design test 13 (migration)
- [ ] 1.6 Design test 15 (UI)

## 2. The fix

- [ ] 2.1 `db/models.py`: `WORKER_OUTCOMES` gains `budget_exhausted`, and `WorkerInvocation.total_tokens` is added. Migration `0106` (design D1), with the head assertions bumped
- [ ] 2.2 `worker.py`: `WorkerUsage.total_tokens` via `_accounting_from_dimensions`; `_record` becomes `record_invocation`; add the required `initiator` and the gate (design D3)
- [ ] 2.3 `checkpoint_generation.py`: derive `initiator` from `trigger` and pass it to `run_worker` and `probe_checkpoint`
- [ ] 2.3a `checkpoint_trigger.consider` (both `not policy.automatic` tests, `:192` and `:263`, via a lazy memoised budget read) and `checkpoint_handover.consider_handover`: the budget read before `generate_checkpoint` (design D3a), fail-closed
- [ ] 2.4 `conversation_titles.py`: JSON mode, the envelope parse, the gate and the invocation row (design D4)
- [ ] 2.5 `usage_accounting.py`: `used_tokens`, the `workers` lines, and project totals including workers. `api/v1/accounting.py`'s PATCH reads the same total
- [ ] 2.6 UI: worker lines in `AccountingPanel.tsx`, and types in `accounting.ts`. Refresh the bundle and commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.7 Run `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH, then the lint block

## 3. Drive (Claude only, bound to Haiku)

- [ ] 3.1 On the trial Hub `:8010`: set `conversation_title_mode: generate` and a checkpoint runner on Haiku. Run one turn, then press Checkpoint. Record `GET /accounting`'s `workers` (`conversation_title`, `checkpoint`, `checkpoint_probe`) and check that `project.total_tokens` equals the turn sum plus the worker sum, read `mode=ro` from the trial database
- [ ] 3.2 Set `token_budget` below usage. Run one more operator turn: a title is **not** generated, and a `budget_exhausted` `conversation_title` row exists. Press Checkpoint: it runs and is counted
- [ ] 3.3 Record, verbatim, what the Budgets section shows in 3.1 and 3.2
