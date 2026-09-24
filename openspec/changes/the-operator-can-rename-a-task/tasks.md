## 0. Rounds and decision

- [x] 0.1 R2: independent re-derivation against `schemas/tasks.py`, `tasks.py:update_task_for_actor`, `TaskDetailDrawer.tsx`, `api/tasks.ts:useUpdateTask`
- [x] 0.2 R3: second independent re-derivation; `openspec validate the-operator-can-rename-a-task --strict` passes
- [ ] 0.3 The operator answers F125 (operator may rename / nobody may); recorded in `spec-queue/DECISIONS.md`

## 1. Tests first — `hub/tests/test_the_operator_can_rename_a_task.py`

- [ ] 1.1 Operator PATCH `{"title": "  New name  "}`: 200, title `New name`, no new `task_transitions` row. FAILS today (422)
- [ ] 1.2 `{"title": "   "}`: 422, title unchanged. FAILS today (422 for a different reason — assert on the message)
- [ ] 1.3 Agent-plane PATCH `{"title": "x"}`: 403, title unchanged. FAILS today (422 extra_forbidden)
- [ ] 1.4 UI (`hub/ui/src/__tests__/`): the drawer's title enters edit mode, Enter calls the update with the new title, Escape restores the old one. FAILS today

## 2. The fix

- [ ] 2.1 `TaskUpdate.title` with a trimming validator; write it in `update_task_for_actor`; add to the run-actor refusal (or the list from `an-agent-updates-a-task-with-what-its-tool-carries`)
- [ ] 2.2 Drawer title editor; `npm run lint`, vitest, `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together

## 3. Verify

- [ ] 3.1 Full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 3.2 Browser check on a trial Hub: rename a task from the drawer, see it on the board without a reload
- [ ] 3.3 Sync the delta and archive
