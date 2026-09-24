## 0. Rounds and decision — nothing below starts until these are done

- [x] 0.1 R2: independent re-derivation against `hub/hub/api/v1/agents.py` (register, create, request, PATCH, detail, list), `hub/hub/launchability.py:470-520`, `hub/hub/scheduler.py:229-252,3078`, `hub/hub/db/models.py:193-222`, and every `agents/register` caller under `hub/tests/`, `scripts/`, `.claude/skills/`, `docs/`. Rebuild design D3's table from `grep` before reading it
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate agents-no-longer-register-themselves --strict` passes
- [ ] 0.3 The operator confirms D3 (delete) and design Open Question 2; recorded in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 Add the `add_agent` fixture to `hub/tests/conftest.py` (design D4): inserts an `Agent` row via `async_session_factory`; returns the name. Control: a test using it plus `bind_runner` triggers an agent with `claude` stripped from PATH and reaches the runner-CLI refusal, not a 404
- [ ] 1.2 New `hub/tests/test_agents_no_longer_register_themselves.py`: `POST /api/v1/projects/proj-test/agents/register` answers 404 or 405. FAILS today (200)
- [ ] 1.3 Same file: an agent made by `add_agent` with no runner bound — `GET /agents/launchability` reports it with `runner == "unbound"` and a reason that does not contain the agent's name as a CLI; `POST /agent/trigger` answers queued with a `waiting_reason` that does not contain `Runner CLI '<name>'`. **Two stages (R2).** Run first against a row with `self_registered=True`, before group 2: it FAILS today — F136's reproduction; record the output. After the migration the column no longer exists, so the committed test uses a plain row and is a **control** (it passes today for `self_registered=False`). What stops the exemption returning is then 1.6 (the column is gone, so the guard has nothing to read) plus a source assertion in this file that `launchability.py` does not contain `self_registered`
- [ ] 1.4 Same file: `POST /projects/{p}/agents` (probe patched runnable, as `test_operator_agent_creation.py` does) returns a body with no `contact_mode` and no `self_registered` key. FAILS today
- [ ] 1.5 Same file: `PATCH /agents/{name}` with `{"contact_mode": "poll"}` answers 400 naming the valid fields, and the list does not contain `contact_mode`. FAILS today (200)
- [ ] 1.6 `hub/tests/test_migrations.py`: upgrade to head leaves `agents` without the four columns; downgrade one step restores them nullable. FAILS today
- [ ] 1.7 Edit `hub/tests/test_operator_agent_creation.py:56-57` to drop the two keys from the whole-body equality. Record that it FAILS after the edit and before group 2

## 2. The fix

- [ ] 2.1 Delete `register_agent` (`agents.py:2261-2324`), `_CONTACT_MODES` and its DEAD block (`:76-84`); remove `contact_mode`/`self_registered` from `OperatorAgentResponse`, the create route (`:735-736`), `request_agent` (`:2203-2204`), `_PATCH_AGENT_FIELDS` and the PATCH handler (`contact_mode`, `mcp_endpoint`, `spawn_cmd`), and the detail dict (`:2699-2700`)
- [ ] 2.2 Remove `self_registered` and `liveness` from `AgentSummary` (`hub/hub/schemas/agents.py`) and the computation at `agents.py:567-577`
- [ ] 2.3 `launchability.py:507` → `elif "runner" not in meta:`; rewrite the comment block `:491-514` to say no agent is exempt by origin (and drop the claim about `collaboration_ready`), and the `get_agent_config` docstring's two self-registration sentences (`:455`, `:466-467`). Also the `_render_hub_agent_context` docstring naming `POST /agents/register` as a caller (`agents.py:1659`)
- [ ] 2.4 Delete `_job_agent_skip_reason` and its call block at `scheduler.py:3078-3097` (design D3)
- [ ] 2.5 Model: drop the four columns and their DEAD comment from `Agent` (`db/models.py:206-220`). Migration per `.claude/rules/db-migrations.md` (batch mode, missing-table guard, head bumps in `test_migrations.py` and `test_project_persistence.py`)
- [ ] 2.6 Remove `register_agent` from `NO_CONTRACT_BY_DESIGN` in `hub/tests/test_request_strictness.py:49`
- [ ] 2.7 Replace every `agents/register` call in the 19 other `hub/tests/` files with `add_agent` (plus `GET /agents/agent-context` where the test read the returned context). Delete `hub/tests/test_agents_self_registered.py`; move any assertion in it that tests something other than registration (e.g. PATCH of `description`, charter binding) into the file for that route first
- [ ] 2.8 CLI: delete `get_agent_registration` (`src/agentweave/transport/http.py:586`, `transport/base.py:98`) and `CONTACT_MODES` (`src/agentweave/constants.py:315-321`). Run `pytest tests/` and `mypy src/`
- [ ] 2.9 UI: drop `self_registered`, `contact_mode`, `liveness` from `hub/ui/src/api/agents.ts`; remove the `EXT` badge in `AgentCard.tsx:65-72` and any test fixture keys. `npm run lint`, vitest, `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.10 Harnesses and docs: update or retire the 9 `scripts/drive/` callers (`n10_route_reachability`, `t_continue_burns_attempts`, `t_queue_attrition`, `t_sweep_conversations`, `t_sweep_integration`, `t_sweep_queue`, `t_sweep_row15_worktrees`, `t_ui_refusal`, `_d2_write_status`) and `.claude/skills/e2e-loop/e2e.py`; delete the route's row in `docs/reference/hub-api.md`

## 3. Verify

- [ ] 3.1 Group 1 passes; full `hub/tests/` with `claude` stripped from PATH (DEAD-ENDS), then the full CLAUDE.md lint block
- [ ] 3.2 Drive on a trial Hub (`:8010` or a scratch profile, never `:8000`): create an agent through the UI's route, `PATCH` its `runner_id` to null (F136's step 2), trigger it, and read the three surfaces F111 named (launchability, queue status, composer line). Record the sentences verbatim
- [ ] 3.3 Reconcile `openspec/specs/` (sync the three deltas) and archive
