# Tasks — a runner that cannot collaborate says so where it is bound

## 0. Rounds

- [x] 0.1 R2: re-derive, against `hub/hub/api/v1/agents.py` (`get_agents_launchability`),
  `hub/hub/bound_address.py`, `hub/hub/main.py` (`_observe_bound_address`), and
  `hub/ui/src/components/agents/AgentSettingsControls.tsx` (`RunnerPicker`), whether
  `collaboration_ready` still reaches no screen, and whether design D3's condition is exact. Rerun
  `grep -rn "AgentCard\|collaboration_" hub/ui/src --include=*.tsx | grep -v __tests__`.
  **Done 2026-09-30 on `bdc8447`** (not recorded on 09-24). D1–D6 stand after
  `a-copilot-agent-runs-over-acp`. One gap: the reason's remedy says "enable yolo", a word the app
  never shows. New design D7, task 1.6, task 2.3a, and a scenario in the delta. Writing 1.5 found a
  second: the app neither shows nor edits a runner's flags (F469, filed), so the remedy names
  rebinding instead of a flag edit, and test-guide step 2 is rewritten (D7).
- [x] 0.2 R3: the same, fresh.
  **Done 2026-09-24.** The condition, the mount (`AgentSettingsPage.tsx:113`) and the failure line
  stand. Rebinding invalidates the verdict at once: `useBindAgentRunner` invalidates
  `['project', pid, 'agents']`, the launchability key's prefix. Nothing breaks on a Hub that has not
  restarted, because the route has returned `collaboration_*` since before this change. One more
  stale reference was added to 2.2.

## 1. Tests first — each must fail on today's code unless marked as a control

- [x] 1.1 `hub/ui/src/__tests__/runnerPickerCannotCollaborate.test.tsx` (new, modelled on
  `runnerPickerCannotRun.test.tsx`). Verdict `{runnable: true, collaboration_ready: false,
  collaboration_reason: "This Codex agent's runner opted out …"}`: a `role="status"` line contains
  *"cannot collaborate"* and the reason. **Fails today.**
  Done 2026-09-30: failed before 2.1 (no such line), passes after.
- [x] 1.2 Same file: `collaboration_ready: true` gives no such line. `collaboration_ready: null`
  with `runnable: true` gives no such line. Controls that pass before and after.
  Done 2026-09-30: controls, pass before and after.
- [x] 1.3 Same file: `{runnable: false, reason: "No runner is bound…", collaboration_ready: null}`
  shows the cannot-run line and not the collaboration line. A control. It also guards against D3's
  `runnable === true` clause being dropped: if it is dropped, a synthetic
  `{runnable: false, collaboration_ready: false}` row shows both lines, and that case is asserted
  here too.
  Done 2026-09-30: control; mutation check, dropping `runnable === true` from the condition fails the synthetic-pair case.
- [x] 1.4 Same file: `collaboration_reason: null` with `collaboration_ready: false` shows the
  fallback sentence (design D3).
  Done 2026-09-30: failed before, passes after.
- [x] 1.5 `hub/ui/src/__tests__/runnersApi.test.tsx` (new, following `tasksApi.test.tsx`: a real
  `QueryClient`, `renderHook`, `globalThis.fetch` replaced, `useConfigStore.setState` with
  `selectedProjectId: 'proj-1'`). Spy on `client.invalidateQueries`. `useUpdateRunner().mutateAsync(
  {id: 'r1', updates: {name: 'renamed'}})` answered 200: the spy saw `{queryKey: ['project', 'proj-1',
  'agents', 'launchability']}` as well as `['project', 'proj-1', 'runners']`. **Fails today**: only
  the `runners` key is invalidated (design D6). Controls in the same file: `useCreateRunner` and
  `useDeleteRunner` do not invalidate the agents' launchability key (the drive found the Hub refuses
  to delete a bound runner, design D7's drive note).
  Done 2026-09-30: the edit case failed before 2.1a and passes after (re-checked by stashing `runners.ts`); the create and delete controls pass both ways.

- [x] 1.6 `hub/tests/test_launchability.py`, the Codex opt-out case (`:343`): the reason contains
  `--no-app-server` and `Full access`, and not `yolo` (design D7). **Fails today.**
  Done 2026-09-30: failed before 2.3a, passes after.

## 2. Implementation

- [x] 2.1 `RunnerPicker`: the line per design D3.
  Done 2026-09-30.
- [x] 2.1a `hub/ui/src/api/runners.ts`: `useUpdateRunner` (`:92`) `onSuccess` also invalidates
  `['project', projectId, 'agents', 'launchability']` (design D6, narrowed by the drive in D7).
  `runnersUi.test.tsx` mocks these hooks, so it is unaffected.
  Done 2026-09-30, `useUpdateRunner` only (D7's drive note).
- [x] 2.2 Delete `hub/ui/src/components/agents/AgentCard.tsx` and
  `hub/ui/src/__tests__/agentCardCollaboration.test.tsx`. Fix the comment at
  `hub/ui/src/lib/agentStatusConfig.ts:3` and the docstring of
  `hub/tests/test_dashboard_truth.py::test_the_agents_route_reports_the_derived_last_seen` (`:184`,
  *"`AgentCard` and `OverviewPage` read this response"*). AgentCard has no query hook of its own,
  so no `n11` row or ceiling moves.
  Done 2026-09-30. `grep -rn AgentCard hub/ui/src` finds only the new test's comment naming F178's history.
- [x] 2.3 `get_agents_launchability` docstring: name the runner picker as its consumer.
  Done 2026-09-30.
- [x] 2.3a The Codex opt-out reason (`agents.py:263-269`): name the remedies as the app shows them (design D7).
  Done 2026-09-30: "Bind a runner without --no-app-server, or set this agent's permissions to Full access."
- [x] 2.4 `make ui`. Commit `hub/ui/src` and `hub/hub/static/ui` together.
  Done 2026-09-30 (`npm run build`, `scripts/refresh_ui_bundle.py`).

## 3. Verification

- [x] 3.1 `cd hub/ui && npm run lint && npx vitest run`, then `py -3.11 -m pytest
  hub/tests/test_surface_ceilings.py -q`. No ceiling should move: no query call site is added or
  removed.
  Done 2026-09-30: eslint and tsc clean; `npx vitest run` 170 files, 1759 passed (was 169/1753: +2 files, -1 file, +9, -3 tests); `py -3.11 -m pytest hub/tests/test_surface_ceilings.py hub/tests/test_launchability.py hub/tests/test_dashboard_truth.py -q` 84 passed, no ceiling moved; ruff, black clean.
- [ ] 3.2 Human-only check on `:8010`: see `test-guide.md`.

## 4. Close

- [ ] 4.1 Foot F178 in `scripts/drive/FINDINGS.md` (runnable half by F179, 2026-09-23;
  collaboration half by this change).
- [ ] 4.2 Sync the delta into `openspec/specs/runtime-diagnostics/spec.md` and archive.
