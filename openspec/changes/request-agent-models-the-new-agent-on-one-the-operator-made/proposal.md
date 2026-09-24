# Proposal — `request_agent` models the new agent on one the operator made

**Round 1, 2026-09-24** (bundle B3, spec track S9). Finding **F378 (B)**, re-verified on HEAD
`404c7d5`. **Nothing here is implemented yet.**

## Why

`request_agent` is on the agent tool surface (`hub/hub/mcp_server.py:622-627`, described in
`_operations()` at `hub/hub/api/v1/agents.py:1336-1344`) and can never succeed. The route reads its
templates from the watchdog-era session table:

```python
session_data = await _get_session_data(project_id, session) or {}      # agents.py:2169
templates = session_data.get("agents", {}) or {}
template_config = templates.get(body.template)
if not isinstance(template_config, dict):
    raise HTTPException(400, f"Agent template '{body.template}' is not pre-approved for this project")
```

`project_sessions` has one writer, `POST /session/sync`, whose only client is the CLI's
`push_session`, itself marked DEAD (`src/agentweave/transport/base.py:72-80`). Measured read-only on
2026-09-24: **0 rows on the operator's `:8000` database and 0 on the trial Hub's.** So every call
answers 400 — as it did live on 2026-09-17, when the operator asked the Architect for developers and
created `Developer_2` by hand instead (FINDINGS F378).

The route's only passing test seeds a `ProjectSession` row by hand
(`hub/tests/test_agent_actions_governed.py:43-55`) — state no product surface produces, which is why
the suite never saw the defect.

Even where a template was found, the new agent was created with **no runner bound**
(`agents.py:2199-2208` copies `config`, never `runner_id`), so its first queued turn would wait on
*"No runner is bound"* — the capability would still not have worked.

## What Changes

- **A template is an existing, open agent of the project, named exactly.** The new agent copies that
  agent's `runner_id`, `charter_id` and `config` (less `principal` and `yolo`); it does **not** copy the
  per-agent grants (`can_accept_evidence`, `can_read_checkpoints`, `can_recall` start closed), its
  permission posture (`default_permission_mode`, nor its legacy mirror `config["yolo"]`, which the
  spawn reads — R2), its description, or its checkpoint and waiting overrides. The operator approved the template by creating it; the agent
  budget (`Project.agent_budget`) remains the ceiling, exactly as `agent-tool-surface` requires.
- **The refusal names what would work**: an unknown template answers 400 listing the project's open
  agents (bounded), an archived one says it is archived.
- **`project_sessions` is no longer read by this route**, and `existing_names` counts only agent
  rows (the `set(templates)` term at `:2181` goes).
- The tool's description and the `_operations()` row say what `template` means.
- The route no longer answers 500 for a turn it did queue: a raise from `schedule_agent` after the
  commit is logged and the answer stays `201 queued` (design D4). The entry then waits until the agent
  is next scheduled; no sweep picks it up sooner.

## Capabilities

### Modified Capabilities

- `agent-tool-surface` — adds a requirement stating what an agent request is modelled on.

## Impact

- Backend only: `agents.py` (`request_agent`, `_operations`), `mcp_server.py` docstring. No migration,
  no UI.
- `test_agent_actions_governed.py:40-77` is rewritten to use agent rows instead of a hand-seeded
  `ProjectSession`.
- Independent of `agents-no-longer-register-themselves`; if that lands first the literal
  `contact_mode="watchdog-spawn"` at `:2203` is already gone.
