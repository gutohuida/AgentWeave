## 0. Before building

- [ ] 0.1 R2 and 0.2 R3: independent re-derivations against `runner_commands.build_command`, `model_catalog`, `launchability.resolve_access_path`, the agents list route and the three UI files; recorded in `spec-queue/tracks/B4.md`
- [ ] 0.3 The operator answers D4's first half (recommended: `workspace` for Claude) and approves in `APPROVALS.md`

## 1. Tests first — each must fail on today's code

- [ ] 1.1 `hub/tests/test_permission_approver.py`: replace `test_the_catalog_default_still_accepts_edits` with `test_each_catalog_default_is_the_posture_a_run_gets` — for each provider, `control.default == posture_at_rest(provider, "mcp", False)`; FAILS today (Claude's default is `acceptEdits`, the spawn's is `workspace`)
- [ ] 1.2 Same file: `test_the_spawn_at_rest_is_the_posture_it_names` — for Claude with and without `mcp_command`, and with `yolo`, `build_command(... control_args=None)` equals `build_command(... control_args=render_control_args("claude", {"permission_mode": posture}), control_overrides={"permission_mode": posture})` for `posture = posture_at_rest(...)`, ignoring flag order only where the builder already orders them. FAILS today (no function)
- [ ] 1.3 `hub/tests/` agents-list test (extend the file that covers `GET /agents`' `default_permission_mode`): a Claude-bound agent reads `permission_mode_at_rest == "workspace"`, one with `hub_client: "cli"` reads `acceptEdits`, one with `yolo` reads `bypassPermissions`, a Codex-bound one reads `acceptEdits`, an unbound one reads `null`, and a Claude-bound agent in a project whose session data sets only a top-level `hub_client: "cli"` reads `acceptEdits` (R2: the spawn's session-wide fallback, `launchability.py:476-479`; this row fails if the list reads `agent_meta` alone). FAILS today (no field)
- [ ] 1.4 `hub/ui/src/__tests__/composerPermissionDefault.test.tsx`: rewrite *"reads the catalog default when the agent states none"* — with `permission_mode_at_rest: 'workspace'` and no default the pill reads "Workspace only" (FAILS today); with the field absent and the fixture catalog's Claude default updated to `workspace` it reads "Workspace only"; with `default_permission_mode: 'manual'` it reads "Ask me" (passes today; guards precedence). Assert no override is sent on render
- [ ] 1.5 `hub/ui/src/__tests__/agentPermissionDefault.test.tsx`: the blank option reads "Built-in default (Workspace only)" for a Claude agent and "Built-in default (depends on the runner)" unbound; FAILS today (hard-coded "Edit files", `:77`)

## 2. The fix

- [ ] 2.1 `posture_at_rest` in `hub/hub/runner_commands.py`; `build_command` uses it
- [ ] 2.2 `hub/hub/model_catalog.py`: Claude's control default `workspace`; delete `DEFAULT_PERMISSION_MODE`
- [ ] 2.3 `launchability.effective_hub_client(meta, session_data)`, used by `get_agent_config` and the list route; `AgentSummary.permission_mode_at_rest` (`hub/hub/schemas/agents.py`) and the list serializer (`hub/hub/api/v1/agents.py:595-615`)
- [ ] 2.4 UI: `api/agents.ts` type, `AgentOutputPanel.tsx:393-395`, `AgentSettingsControls.tsx:199`; update `__tests__/support/modelCatalogFixture.ts` to the new Claude default
- [ ] 2.5 `py -3.11 -m pytest hub/tests/ -q` (claude off PATH), `cd hub/ui && npm test && npm run lint`, ruff, black; record counts
- [ ] 2.6 `npm run build`, `py -3.11 scripts/refresh_ui_bundle.py`; commit `hub/ui/src` and `hub/hub/static/ui` together; open the app on the trial Hub `:8010` and check a fresh agent's pill reads "Workspace only"

## 3. Close

- [ ] 3.1 F283 → `fixed <sha>`; backlog regenerated; `openspec validate the-permissions-pill-shows-the-posture-the-run-gets --strict`; archive
