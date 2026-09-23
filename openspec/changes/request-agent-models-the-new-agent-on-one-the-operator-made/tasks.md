## 0. Rounds and decision

- [ ] 0.1 R2: independent re-derivation against `agents.py:2140-2258`, `agent_actions.py:829-840`, `mcp_server.py:622-627`, `_operations()` (`agents.py:1336-1344`) and `test_agent_actions_governed.py`. Argue design D2's `default_permission_mode` row
- [ ] 0.2 R3: second independent re-derivation; `openspec validate request-agent-models-the-new-agent-on-one-the-operator-made --strict` passes
- [ ] 0.3 The operator answers the F378 question (template = existing agent / registry / delete); recorded in `spec-queue/DECISIONS.md`

## 1. Tests first — new file `hub/tests/test_request_agent_models_an_existing_agent.py`

Each builds the template with real agent rows (an `Agent` row plus `bind_runner`), never a `ProjectSession`, and calls the route through the agent plane (`/api/v1/agent-actions/agents/request`) with a run credential, as `_actor()` in `test_agent_actions_governed.py` does.

- [ ] 1.1 Template = an open agent with a runner and charter: 201; the new row's `runner_id` and `charter_id` equal the template's; `created_by_run_id` is the requester's run. FAILS today (400 *not pre-approved*)
- [ ] 1.2 The template holds `can_accept_evidence=True`: the new agent's is `False`. FAILS today (400)
- [ ] 1.3 Unknown template: 400, detail contains every open agent's name and not an archived one's. FAILS today (the detail names no agent)
- [ ] 1.4 Archived template: 409 naming archival. FAILS today (400)
- [ ] 1.5 Template with no runner: 409. FAILS today (400)
- [ ] 1.6 Budget: with `agent_budget` equal to the agent count, 409 and no row. Control for the budget sentence; FAILS today only because the template check comes first — assert on the budget sentence
- [ ] 1.7 `schedule_agent` patched to raise: 201, `status == "queued"`, the entry exists. FAILS today (500)
- [ ] 1.8 Rewrite `test_agent_request_uses_bound_requester_template_and_budget` (`test_agent_actions_governed.py:40`) onto agent rows; keep its impostor-header and `run_id`-in-body assertions

## 2. The fix

- [ ] 2.1 In `request_agent`, replace the `_get_session_data` lookup with a query for the template `Agent` row; add the three refusals (design D3); count `existing_names` from agent rows only
- [ ] 2.2 Create the new row with the template's `runner_id`, `charter_id`, `config` (minus `principal`); nothing else copied
- [ ] 2.3 Wrap only `schedule_agent` in `try/except Exception`, log, and return the `201` payload
- [ ] 2.4 Update the MCP docstring (`mcp_server.py:623-624`) and the `_operations()` text to say `template` is the exact name of an open agent in this project whose runner and charter the new agent takes; `test_tool_surface_matches_server.py` must stay green

## 3. Verify

- [ ] 3.1 Group 1 passes; full `hub/tests/` with `claude` stripped from PATH; CLAUDE.md lint block
- [ ] 3.2 Drive on a trial Hub with one Haiku agent: ask it to request a second agent modelled on itself; the second agent appears, runs one turn, and the first agent's transcript shows a 201. Record the call and answer verbatim
- [ ] 3.3 Sync the delta into `openspec/specs/agent-tool-surface/spec.md` and archive
