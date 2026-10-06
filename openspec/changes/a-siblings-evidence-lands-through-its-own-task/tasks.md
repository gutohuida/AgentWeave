## 1. Acceptance first

- [x] 1.1 `hub/tests/test_sibling_evidence_waits_for_its_task.py`: two parts, both failing on master (accepting a sibling's evidence lands it; the sibling's approval then has nothing to merge)

## 2. Build

- [x] 2.1 `task_integration._targets`: exclude evidence whose `task_id` names another task that is not `approved`
- [x] 2.2 `tasks_awaiting_this_commit`: re-integrate only the tasks the accepted evidence is a target of
- [x] 2.3 Guard: the existing integration/gate suites stay green (`test_task_integration*.py`, `test_approval_refuses_unaccepted_evidence.py`, `test_project_checks_gate.py`)

## 3. Close

- [ ] 3.1 Full Hub suite; ruff, black
- [ ] 3.2 F520 `**Status:**` line; sync the delta into `openspec/specs/task-lifecycle-governance/spec.md`; archive
