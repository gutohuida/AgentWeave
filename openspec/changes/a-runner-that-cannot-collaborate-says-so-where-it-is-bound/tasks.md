# Tasks — a runner that cannot collaborate says so where it is bound

## 0. Rounds

- [ ] 0.1 R2: re-derive, against `hub/hub/api/v1/agents.py` (`get_agents_launchability`),
  `hub/hub/bound_address.py`, `hub/hub/main.py` (`_observe_bound_address`), and
  `hub/ui/src/components/agents/AgentSettingsControls.tsx` (`RunnerPicker`), whether
  `collaboration_ready` still reaches no screen, and whether design D3's condition is exact. Rerun
  `grep -rn "AgentCard\|collaboration_" hub/ui/src --include=*.tsx | grep -v __tests__`.
- [ ] 0.2 R3: the same, fresh.
  **Done 2026-09-24.** The condition, the mount (`AgentSettingsPage.tsx:113`) and the failure line
  stand. Rebinding invalidates the verdict at once: `useBindAgentRunner` invalidates
  `['project', pid, 'agents']`, the launchability key's prefix. Nothing breaks on a Hub that has not
  restarted, because the route has returned `collaboration_*` since before this change. One more
  stale reference was added to 2.2.

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 `hub/ui/src/__tests__/runnerPickerCannotCollaborate.test.tsx` (new, modelled on
  `runnerPickerCannotRun.test.tsx`). Verdict `{runnable: true, collaboration_ready: false,
  collaboration_reason: "This Codex agent's runner opted out …"}`: a `role="status"` line contains
  *"cannot collaborate"* and the reason. **Fails today.**
- [ ] 1.2 Same file: `collaboration_ready: true` gives no such line. `collaboration_ready: null`
  with `runnable: true` gives no such line. Controls that pass before and after.
- [ ] 1.3 Same file: `{runnable: false, reason: "No runner is bound…", collaboration_ready: null}`
  shows the cannot-run line and not the collaboration line. A control. It also guards against D3's
  `runnable === true` clause being dropped: if it is dropped, a synthetic
  `{runnable: false, collaboration_ready: false}` row shows both lines, and that case is asserted
  here too.
- [ ] 1.4 Same file: `collaboration_reason: null` with `collaboration_ready: false` shows the
  fallback sentence (design D3).
- [ ] 1.5 `hub/ui/src/__tests__/runnersApi.test.tsx` (new, following `tasksApi.test.tsx`: a real
  `QueryClient`, `renderHook`, `globalThis.fetch` replaced, `useConfigStore.setState` with
  `selectedProjectId: 'proj-1'`). Spy on `client.invalidateQueries`. `useUpdateRunner().mutateAsync(
  {id: 'r1', updates: {flags: []}})` answered 200: the spy saw `{queryKey: ['project', 'proj-1',
  'agents', 'launchability']}` as well as `['project', 'proj-1', 'runners']`. The same for
  `useDeleteRunner().mutateAsync('r1')`. **Fails today** for both: only the `runners` key is
  invalidated (design D6). A control in the same file: `useCreateRunner` does not invalidate the
  agents' launchability key.

## 2. Implementation

- [ ] 2.1 `RunnerPicker`: the line per design D3.
- [ ] 2.1a `hub/ui/src/api/runners.ts`: `useUpdateRunner` (`:92`) and `useDeleteRunner` (`:106`)
  `onSuccess` also invalidate `['project', projectId, 'agents', 'launchability']` (design D6).
  `runnersUi.test.tsx` mocks these hooks, so it is unaffected.
- [ ] 2.2 Delete `hub/ui/src/components/agents/AgentCard.tsx` and
  `hub/ui/src/__tests__/agentCardCollaboration.test.tsx`. Fix the comment at
  `hub/ui/src/lib/agentStatusConfig.ts:3` and the docstring of
  `hub/tests/test_dashboard_truth.py::test_the_agents_route_reports_the_derived_last_seen` (`:184`,
  *"`AgentCard` and `OverviewPage` read this response"*). AgentCard has no query hook of its own,
  so no `n11` row or ceiling moves.
- [ ] 2.3 `get_agents_launchability` docstring: name the runner picker as its consumer.
- [ ] 2.4 `make ui`. Commit `hub/ui/src` and `hub/hub/static/ui` together.

## 3. Verification

- [ ] 3.1 `cd hub/ui && npm run lint && npx vitest run`, then `py -3.11 -m pytest
  hub/tests/test_surface_ceilings.py -q`. No ceiling should move: no query call site is added or
  removed.
- [ ] 3.2 Human-only check on `:8010`: see `test-guide.md`.

## 4. Close

- [ ] 4.1 Foot F178 in `scripts/drive/FINDINGS.md` (runnable half by F179, 2026-09-23;
  collaboration half by this change).
- [ ] 4.2 Sync the delta into `openspec/specs/runtime-diagnostics/spec.md` and archive.
