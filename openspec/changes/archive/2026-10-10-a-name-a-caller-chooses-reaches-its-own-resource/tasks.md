## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently rebuild the collision table from `app.routes` (not from R1's script), including routers mounted outside `project_resources_router`; confirm every door that creates an agent reaches `validate_agent_name`, and every door that creates a task reaches the id validator (initial tasks on a loop, the MCP `create_task`, spec materialisation mints its own ids). Re-run the `mode=ro` checks on `:8000`. Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate a-name-a-caller-chooses-reaches-its-own-resource --strict` passes
- [ ] 0.3 The operator records the F248 decision in `spec-queue/DECISIONS.md` (reserve, or move the routes)

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 Measure the two unmeasured rows first: with an agent named `settings` inserted directly, `GET /queue/settings` answers the settings body, not that agent's entries; with a task id `board` inserted directly, `GET /tasks/board` does not answer that task. (R3) With an agent named `sessions` inserted directly, `GET /agent/sessions/chat` does not answer that agent's chat history. Record both results in the round log (they justify rows 2 and 3)
- [ ] 1.2 New `hub/tests/test_a_chosen_name_is_not_a_route.py`: D2's route walk. Record that it FAILS today, naming `conflicts`, `settings`, `sessions`, `board`, `boards`
- [ ] 1.3 Same file: `POST /agents {"name": "conflicts"}` and `{"name": "Settings"}` are refused, and the detail names the route. Record that both FAIL today (201)
- [ ] 1.4 Same file: `POST /tasks {"id": "board", ...}` (operator door) **and** `POST /agent/tasks {"id": "boards", ...}` (agent door, run-token auth) each answer 422 naming `id`, never 500. Record that both FAIL today (201). The agent-door case fails if only `TaskCreate` gains the check (R2: it would 500 from `agent_actions.py:233`)
- [ ] 1.5 Control: `user` and `operator` are still refused with their existing reasons; an agent named `conflict` (singular) is accepted
- [ ] 1.6 `tests/`: the CLI's `is_valid_agent_name("settings")` and `is_valid_agent_name("sessions")` are False. Record that it FAILS today

## 2. The fix

- [ ] 2.1 `hub/hub/worktrees.py` and `src/agentweave/constants.py`: D1's two names, together
- [ ] 2.2 `hub/hub/schemas/tasks.py`: one shared reserved-id check beside `_TASK_ID_RE`, called from `TaskCreate._validate_id_shape` and from `AgentTaskCreate.validate_id` (`hub/hub/api/v1/agent_actions.py`)
- [ ] 2.3 Group 1, then `py -3.11 -m pytest hub/tests/ -q` and `py -3.11 -m pytest tests/ -q`; record counts inline or do not tick
- [ ] 2.4 `ruff check src/ hub/ tests/`, `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`, `mypy src/`
