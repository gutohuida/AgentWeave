## 0. Acceptance drive first (R3)

- [x] 0.1 Write `scripts/drive/d1006_checks_gate.py`: design.md's five steps, against a fresh Hub, with real Haiku agents. Run it on master and record that step 1 fails (no check run recorded). Ran on master `:8037`: `setup` fails, HTTP 422 `extra_forbidden` on `checks`.

## 1. Model and migration

- [x] 1.1 Tests first: migration `0119` upgrades from `0118` and from an early revision, and the head assertions in `test_migrations.py` and `test_project_persistence.py` are bumped.
- [x] 1.2 `Project.checks` (JSON, nullable: null means none), `TaskCheckRun`, and `TaskTransition.override_reason` in `models.py`, plus migration `0119` per `.claude/rules/db-migrations.md`.

## 2. Configuring checks

- [x] 2.1 Tests first: the operator saves and reads checks; duplicate names, empty commands and timeouts out of range are refused naming the field; every agent route that touches project settings refuses to change checks.
- [x] 2.2 `ProjectSettings` gains `checks`, validated (`api/v1/projects.py`).

## 3. Building and running a check run

- [ ] 3.1 Tests first (real git repo fixtures): the would-merge commit equals main plus every target (D1); a conflicting target records `error`; a failing command records `failed` with its exit code and output tail; a timeout ends the process tree; the root checkout is unchanged; no Hub credential reaches the environment; output is scrubbed.
- [ ] 3.2 `hub/hub/project_checks.py`: the D1 commit, the D2 scratch worktree, the D4 queue (two at a time, per-task join), D8's environment, and result rows (D3).
- [ ] 3.3 Tests first: moving to `completed` enqueues a run and returns before it ends; a project without checks enqueues nothing; startup marks `running` rows `interrupted`.
- [ ] 3.4 Wire the enqueue into `apply_transition` on `completed`, and the startup reconcile into `main.py`.

## 4. The gate

- [ ] 4.1 Tests first: each of the four task-lifecycle-governance scenarios, plus stale-by-main and stale-by-targets, plus a test that `approval_held_for_operator` and the integration preview start no run. The order of results matches what the route returns.
- [ ] 4.2 The `checks` category in `GateRefusal` (D6); `evaluate(start_checks=...)` (D5); the approval transition and the land route pass `True`.
- [ ] 4.3 Tests first: operator override with and without a reason, an agent override refused, a `running` result not overridable, the reason shown by `task_history`.
- [ ] 4.4 `override_checks_reason` on the operator's update route, honoured per D7, stored on the transition.

## 5. Briefing

- [ ] 5.1 Tests first: both review channels state passed / failed / running / none, and say nothing without checks.
- [ ] 5.2 The sentence in `review_turn` (one helper, as `verdict_evidence_sentence`), used by both channels.

## 6. UI

- [ ] 6.1 Tests first (vitest): the settings Checks editor saves and reloads; the drawer row shows each state and the failing tail; Re-run calls the route.
- [ ] 6.2 The settings editor, the drawer row, and `POST /tasks/{id}/checks/run` (an operator-only re-run); refresh the bundle (`scripts/refresh_ui_bundle.py`) and commit `hub/ui/src` and `hub/hub/static/ui` together.

## 7. What must not move

- [ ] 7.1 Full suites: `pytest hub/tests/ -q`, `pytest tests/ -q`, `cd hub/ui && npm test`, and CI's lint set, with counts on this line.
- [ ] 7.2 Run the acceptance drive (0.1) to completion, all five steps passing. Record it in `scripts/drive/FINDINGS.md` and as a `spec-queue/METRICS.md` row.
- [ ] 7.3 Reconcile `openspec/specs/` (sync) and archive.
