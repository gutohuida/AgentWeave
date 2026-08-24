# Tasks

Run the suite with **`py -3.11 -m pytest hub/tests/ -q`**. Bare `python` resolves to a venv that has
pytest but produces three false failures in `test_pty_runner.py` on a green tree.

## 1. The delivery filter

- [x] 1.1 In `turn_scheduler.schedule_agent`, filter the selected batch to entries whose
      `hop_depth` is within the project's budget. Today the selection filters only by conversation
      and the delivery cap.
- [x] 1.2 Set the turn's depth from the admitting entry rather than `min(hop_depth)` (design D2).
- [x] 1.3 Tests: a batch mixing an in-budget and an over-budget entry delivers only the first; the
      resulting run's `turn_depth` is the admitting entry's; an outbound message from that turn is
      deeper than the entry that admitted it.
- [x] 1.4 Regression test reproducing F5 exactly: budget 1, chain to depth 2, operator message into
      the same conversation, assert the depth-2 entry stays `queued` and the run's depth is 0.

## 2. Continue and discard

- [x] 2.1 Add the release endpoint: re-base a budget-held entry to depth 0 and requeue it for
      delivery. Refuse an entry that is not actually budget-held, with a stated reason.
- [x] 2.2 Persist and broadcast an event recording the operator's decision to release (design D3).
- [x] 2.3 Confirm `redrain_queued_agents` still releases held entries when the budget is raised, and
      add the test that pins it — the behaviour exists and is unasserted.
- [x] 2.4 Tests: release delivers on the next turn; release is recorded; discard withdraws; raising
      the budget releases without an explicit action.

## 3. Surfacing

- [x] 3.1 Render Continue and Discard on an entry the UI already marks `hop_budget_exceeded`. The
      state is already computed and already displayed — this adds the actions, not the indicator.
- [x] 3.2 State why the entry is held, in words naming the remedy rather than the rule.
- [x] 3.3 UI tests for both actions and the held state.

## 4. Verification an agent can do

- [ ] 4.1 `py -3.11 -m pytest hub/tests/ -q` — green, no new skips.
- [ ] 4.2 `cd hub/ui && npm run lint && npx tsc --noEmit`, then `npm run build` and
      `python scripts/refresh_ui_bundle.py`, and commit the bundle and the stamp together — once.
      `/health` reads `src_fingerprint` alone (`hub/hub/main.py:161-167`), which committing does
      not change, so there is nothing to re-stamp afterwards.
- [ ] 4.3 `uvx ruff@0.15.22 check src/ hub/ tests/` and `uvx black@26.5.1 --check`.
- [ ] 4.4 `npx openspec validate --changes --strict`.
- [ ] 4.5 Re-run `scripts/drive/t_hop.py` against the trial Hub and confirm the depth-2 entry is not
      delivered when an operator message arrives.

## 5. Verification only a person can do

- [ ] 5.1 Judge whether the held-entry explanation tells you what to do, not merely what happened.
- [ ] 5.2 Release a held chain by hand and confirm the conversation reads coherently afterwards —
      that the released message arrives somewhere it still makes sense.

## 6. User test guide

- [ ] 6.1 Write the operator-facing walkthrough: what a held entry looks like, the three ways
      forward, and what changes about the chain after a release.
