## 0. Before building

- [x] 0.1 R2 and 0.2 R3: independent re-derivations against `mcp_server._ask_operator`/`_decide`, `agent_actions.open_permission_request`, `permissions.list_permission_requests`, `agent_trigger._await_operator_permission`, `codex_appserver.decide_approval` and `PermissionRequestCard.tsx`; recorded in `spec-queue/tracks/B4.md`
- [x] 0.3 The operator answers D4's second half (recommended: yes, advisory) and approves; told that the approver edit reaches `:8000`'s next run and the migration their next restart

- [x] 0.4 Verification round at IMPL, 2026-09-30 on `e540752`: R2/R3 are in design.md and `spec-queue/tracks/B4.md`; approved in APPROVALS 2026-09-27, where the operator was told the `mcp_server.py` half reaches `:8000`'s tool server. New: Copilot's operator path and its existing `workspace_verdict`; migration `0114`; B11 landed (design D5). Task 1.5b and 2.4a added.

## 1. Tests first — each must fail on today's code

- [x] 1.1 `hub/tests/test_permission_approver.py`: with `AW_PERMISSION_POSTURE=operator` and `_hub_request` stubbed, `approve_tool_call("Write", {"file_path": <outside>})` opens a request whose body carries `workspace_verdict == {"allow": False, "reason": <the _decide refusal>}`, and one inside carries `allow: True` with reason `"inside your workspace"`; `approve_tool_call("Bash", {"command": "ls sub"})` carries `allow: True` with a reason ending `a shell command is read, not sandboxed` (design D3, operator review). FAILS today (no field)
  Done 2026-09-30: failed before 2.3 (no field), passes after.
- [x] 1.2 Same file: `_decide("Bash", {"command": "cp x $DEST"})` is allowed with the qualified reason; `_decide("Bash", {"command": "ls sub"})` keeps `"inside your workspace"`. FAILS today (first case)
  Done 2026-09-30: failed before (plain reason), passes after.
- [x] 1.3 Same file: the stub raises `HubAPIError(422, …)` on a body carrying `workspace_verdict` and accepts the old body → the request is opened once, without the field, and the operator is asked; the stub raises `HubAPIError(500, …)` → no retry, denied "could not be asked". FAILS today (first case: today's body never carries the field, so assert the first attempt did — the test fails because the stub never sees a verdict)
  Done 2026-09-30: the stub records every attempt, so the 422 case asserts the first body carried the verdict (failed before) and the retry did not; the 500 case sends once and denies.
- [x] 1.3b Same file (R2): with `_decide` monkeypatched to raise, `approve_tool_call` under `AW_PERMISSION_POSTURE=operator` still opens the request (without `workspace_verdict`) and waits on the operator. FAILS against a build that computes the verdict outside a `try`
  Done 2026-09-30: a control today; mutation: without the verdict's own `try`, it fails.
- [x] 1.4 Route test (the file covering `/agent-actions/permission-requests`): opening with a verdict stores it and `GET /permission-requests` returns it; opening without one returns `null`; a verdict whose reason exceeds 1000 characters is a 422. FAILS today (extra field → 422)
  Done 2026-09-30 in `test_permission_request_lifecycle.py`: stored and returned, `null` without one (failed before: the field was a 422); an over-long reason is a 422.
- [x] 1.5 Codex: `_await_operator_permission(..., workspace=<ws>)` with a subject whose `cwd` is outside stores `allow: False`, and one inside stores `allow: True`; both reasons contain `checked by working directory only`, and neither contains `read, not sandboxed` (operator review). FAILS today. And (R2) for a set of subjects inside, outside and with neither `cwd` nor `grantRoot`, `workspace_verdict(subject, ws)["allow"]` equals `decide_approval(method, params, posture="workspace", workspace=ws) == {"decision": "accept"}`
  Done 2026-09-30 in the new `test_ask_me_card_verdicts.py`: `codex_appserver.workspace_verdict` agrees with `decide_approval(posture='workspace')` over six command and file-change subjects (inside, outside, none), each reason saying `checked by working directory only`; and through `POST /agent/trigger` with a fake `codex_run_turn` calling the real `request_approval`, the rows store allow true inside and false outside. Failed before (no helper, no column).
- [x] 1.5b (design D5) Copilot: `_await_operator_permission(..., workspace_verdict=<v>)` stores `v` on the row and `None` stores null; `copilot_acp.workspace_verdict` on an allowed `execute` request carries a reason ending `a shell command is read, not sandboxed`, and the Copilot turn's `request_approval` receives the verdict it computed. FAILS today (no parameter; no qualification)
  Done 2026-09-30: the Copilot trigger path stores the verdict its turn computed (failed before: null); `copilot_acp.workspace_verdict` qualifies an `execute` allow (failed before).
- [x] 1.6 `hub/ui/src/__tests__/permissionRequestCard.test.tsx`: two pending requests in the order `GET /permission-requests` returns (newest first, `permissions.py:73`) — the newer outside (`allow: false`), the older inside — render the warning line on the first and the muted line on the second, **each including its own `reason` text** (operator review: the allow reason is shown); a third with `workspace_verdict: null` renders neither. Some assertion fails if the fixture order is reversed (it keys each line to its request id and asserts the DOM order). FAILS today
  Done 2026-09-30: route order (newest first), each line inside its own request, DOM order asserted, reasons shown for allow and refuse, nothing for null; plus a shell allow that never says "stays inside". Failed before.
- [x] 1.7 Migration tests: head bumped in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`; an upgrade from before `permission_requests` existed still runs
  Done 2026-09-30: heads bumped to 0114; `test_migration_0114_adds_a_nullable_workspace_verdict` (downgrade and upgrade) and the missing-table guard test.

## 2. The fix

- [x] 2.1 Migration `0114` (design D5) and `PermissionRequest.workspace_verdict`
  Done 2026-09-30 (`0114_permission_request_workspace_verdict.py`).
- [x] 2.2 `PermissionRequestCreate.workspace_verdict` (optional), the route stores it, `PermissionRequestResponse` returns it
  Done 2026-09-30 (`WorkspaceVerdict`, `reason` max 1000).
- [x] 2.3 `_ask_operator` computes and sends the verdict, with the one 422 retry (design D2); `_decide`'s qualified allow reason (design D4). No return annotation is added to `approve_tool_call` (`.claude/rules/mcp-server.md`)
  Done 2026-09-30; `approve_tool_call` untouched (no return annotation).
- [x] 2.4 `codex_appserver.workspace_verdict`, used by `decide_approval`'s workspace branch and by `_await_operator_permission(workspace=…)`
  Done 2026-09-30; `decide_approval`'s workspace branch calls it.
- [x] 2.4a (design D5) `_await_operator_permission(workspace_verdict=…)`; the Codex and Copilot callers pass theirs; `copilot_acp.workspace_verdict` qualifies an `execute` allow
  Done 2026-09-30.
- [x] 2.5 UI: `api/permissions.ts` type, the card line; `npm test`, `npm run lint`, `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together
  Done 2026-09-30: vitest 171 files, 1769 passed; eslint, tsc clean; bundle refreshed.
- [x] 2.6 Full `hub/tests/` (claude off PATH), ruff, black; record counts
  Done 2026-09-30: `py -3.11 -m pytest hub/tests/ -q -n 8` with `claude` off PATH: 5482 passed, 87 skipped, 0 failed, 4:53. ruff, black clean.

## 3. Drive

- [x] 3.1 On the trial Hub `:8010`, an agent under "Ask me" (Haiku): ask it to write one file inside its worktree and one in the project root. **Both cards** appear; the second shows the warning line naming the path, the first the muted line. Record the `workspace_verdict` values from `GET /permission-requests`
  Done 2026-09-30 on a throwaway Hub (`:8035`, profile `drive0930e`, project `proj-ff31c558b0bd`), not `:8010`: one real Haiku turn under "Ask me". Two cards: `…\.agentweave\worktreessker\inside.txt` with `{"allow": true, "reason": "inside your workspace"}`, and `…\proj-160200\outside.txt` with `{"allow": false, "reason": "'…\outside.txt' is outside your workspace"}`. Allowed the first, denied the second; `outside.txt` was not written. The rendered card is covered by the component test; no browser was opened.

## 4. Close

- [ ] 4.1 F230 and F284 → `fixed <sha>`; backlog regenerated; `openspec validate an-ask-me-card-says-what-workspace-only-would-decide --strict`; archive
