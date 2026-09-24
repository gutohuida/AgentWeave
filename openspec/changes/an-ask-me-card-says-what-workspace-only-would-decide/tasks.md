## 0. Before building

- [ ] 0.1 R2 and 0.2 R3: independent re-derivations against `mcp_server._ask_operator`/`_decide`, `agent_actions.open_permission_request`, `permissions.list_permission_requests`, `agent_trigger._await_operator_permission`, `codex_appserver.decide_approval` and `PermissionRequestCard.tsx`; recorded in `spec-queue/tracks/B4.md`
- [ ] 0.3 The operator answers D4's second half (recommended: yes, advisory) and approves; told that the approver edit reaches `:8000`'s next run and the migration their next restart

## 1. Tests first — each must fail on today's code

- [ ] 1.1 `hub/tests/test_permission_approver.py`: with `AW_PERMISSION_POSTURE=operator` and `_hub_request` stubbed, `approve_tool_call("Write", {"file_path": <outside>})` opens a request whose body carries `workspace_verdict == {"allow": False, "reason": <the _decide refusal>}`, and one inside carries `allow: True`. FAILS today (no field)
- [ ] 1.2 Same file: `_decide("Bash", {"command": "cp x $DEST"})` is allowed with the qualified reason; `_decide("Bash", {"command": "ls sub"})` keeps `"inside your workspace"`. FAILS today (first case)
- [ ] 1.3 Same file: the stub raises `HubAPIError(422, …)` on a body carrying `workspace_verdict` and accepts the old body → the request is opened once, without the field, and the operator is asked; the stub raises `HubAPIError(500, …)` → no retry, denied "could not be asked". FAILS today (first case: today's body never carries the field, so assert the first attempt did — the test fails because the stub never sees a verdict)
- [ ] 1.3b Same file (R2): with `_decide` monkeypatched to raise, `approve_tool_call` under `AW_PERMISSION_POSTURE=operator` still opens the request (without `workspace_verdict`) and waits on the operator. FAILS against a build that computes the verdict outside a `try`
- [ ] 1.4 Route test (the file covering `/agent-actions/permission-requests`): opening with a verdict stores it and `GET /permission-requests` returns it; opening without one returns `null`; a verdict whose reason exceeds 1000 characters is a 422. FAILS today (extra field → 422)
- [ ] 1.5 Codex: `_await_operator_permission(..., workspace=<ws>)` with a subject whose `cwd` is outside stores `allow: False`. FAILS today. And (R2) for a set of subjects inside, outside and with neither `cwd` nor `grantRoot`, `workspace_verdict(subject, ws)["allow"]` equals `decide_approval(method, params, posture="workspace", workspace=ws) == {"decision": "accept"}`
- [ ] 1.6 `hub/ui/src/__tests__/permissionRequestCard.test.tsx`: two pending requests in the order `GET /permission-requests` returns (newest first, `permissions.py:73`) — the newer outside (`allow: false`), the older inside — render the warning line on the first and the muted line on the second; a third with `workspace_verdict: null` renders neither. Some assertion fails if the fixture order is reversed (it keys each line to its request id and asserts the DOM order). FAILS today
- [ ] 1.7 Migration tests: head bumped in `hub/tests/test_migrations.py` and `hub/tests/test_project_persistence.py`; an upgrade from before `permission_requests` existed still runs

## 2. The fix

- [ ] 2.1 Migration `0106` and `PermissionRequest.workspace_verdict`
- [ ] 2.2 `PermissionRequestCreate.workspace_verdict` (optional), the route stores it, `PermissionRequestResponse` returns it
- [ ] 2.3 `_ask_operator` computes and sends the verdict, with the one 422 retry (design D2); `_decide`'s qualified allow reason (design D4). No return annotation is added to `approve_tool_call` (`.claude/rules/mcp-server.md`)
- [ ] 2.4 `codex_appserver.workspace_verdict`, used by `decide_approval`'s workspace branch and by `_await_operator_permission(workspace=…)`
- [ ] 2.5 UI: `api/permissions.ts` type, the card line; `npm test`, `npm run lint`, `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.6 Full `hub/tests/` (claude off PATH), ruff, black; record counts

## 3. Drive

- [ ] 3.1 On the trial Hub `:8010`, an agent under "Ask me" (Haiku): ask it to write one file inside its worktree and one in the project root. **Both cards** appear; the second shows the warning line naming the path, the first the muted line. Record the `workspace_verdict` values from `GET /permission-requests`

## 4. Close

- [ ] 4.1 F230 and F284 → `fixed <sha>`; backlog regenerated; `openspec validate an-ask-me-card-says-what-workspace-only-would-decide --strict`; archive
