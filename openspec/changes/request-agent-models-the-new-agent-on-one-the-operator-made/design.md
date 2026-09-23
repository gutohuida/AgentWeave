# Design — `request_agent` models the new agent on one the operator made

**Built on the recommended answer to S9's F378 question** ("where do `request_agent` templates come
from?"): *an existing open agent of the project*. **If the operator answers otherwise** — delete the
tool, or build a dedicated template registry — this change is replaced; the tests in group 1 that
assert "every call 400s today" still stand as the regression for whichever is chosen.

## Context — re-verified on HEAD `404c7d5`

- `request_agent` route: `hub/hub/api/v1/agents.py:2140-2258`. Template lookup `:2169-2176`; budget
  `:2177-2195` counting `set(templates) | {row.name …}`; new row `:2199-2208` with `config` copied
  and no `runner_id`; `schedule_agent` called after commit at `:2255-2257`.
- Agent route wrapper: `hub/hub/api/v1/agent_actions.py:829-840` (identity from the run credential).
- MCP tool: `hub/hub/mcp_server.py:622-627`.
- `project_sessions`: 0 rows on both Hubs (read `mode=ro`, 2026-09-24).
- `git log -S "is not pre-approved for this project"` — unchanged since the route was written in the
  watchdog era; nothing has touched the template source since the session table lost its writer.

## D1 — Options

1. **Template = an existing open agent** (recommended). No new table, no new UI: the operator's act
   of creating `Developer` with a runner and charter *is* the approval of "more like Developer". It
   serves the observed use exactly (the Architect wanted a second developer), and the new agent is
   runnable on its first turn because it inherits a bound runner.
2. **A template registry** (a table plus a settings surface). Honest, but it is a new operator
   surface for a capability used once, and it duplicates what an agent row already holds.
3. **Delete `request_agent`.** Cheapest, and it satisfies `agent-tool-surface` trivially. It removes
   the one path by which a single-agent project grows from inside (`_tool_surface_lines` docstring,
   `agents.py:1513-1514`) and discards real demand seen on 2026-09-17.

## D2 — What is copied, and what is not

| Field | Copied? | Why |
|---|---|---|
| `runner_id` | yes | without it the agent cannot run; the operator chose this runner for this kind of agent |
| `charter_id` | yes | the charter is how the operator told this kind of agent how to behave |
| `config` | yes (minus `principal`, as today) | carries runner options the runner row does not |
| `can_accept_evidence`, `can_read_checkpoints`, `can_recall` | **no** | these are authority the operator grants one agent at a time (`agent-configuration`, *"The operator can grant an agent the authority to accept evidence"*); an agent must not be able to mint a second holder of it |
| `description`, `default_permission_mode`, waiting and checkpoint overrides | no | per-agent settings the operator writes on the agent itself; defaults apply |

`default_permission_mode` is the one R2 should argue: copying it would let a `full access` template
produce more `full access` agents without the operator touching them; not copying means the new
agent runs under the project default. Recommended: not copied (least authority).

## D3 — Refusals

| Condition | Answer |
|---|---|
| no agent named `template` | 400 `No agent named '<t>' in this project to model a new agent on. Name one of: a, b, c.` (open agents, sorted, at most 10, then `…`) |
| template archived | 409 `'<t>' is archived; model the new agent on an open agent.` |
| template has no runner bound | 409 `'<t>' has no runner bound, so an agent modelled on it could not run.` |
| name taken | 409 (unchanged) |
| budget exhausted | 409 (unchanged; counts agent rows only) |

The name rule is unchanged: `worktrees.validate_agent_name` (`:2150-2154`) applies `AGENT_NAME_RE`
and the reserved names; this change does not touch the three restatements.

## D4 — What the route returns when what it calls raises

- Before the commit (validation, template, budget): the raise is one of the answers above; nothing is
  written.
- `persist_event` / `sse_manager.broadcast` / `schedule_agent` after the commit: today any raise
  becomes a 500 after the agent and its queue entry already exist, so the caller retries and gets
  *"already exists"* for an agent it was told was not created. The route will catch an exception from
  `schedule_agent` only, log it, and still answer `201` with `status: "queued"` — the entry is durable
  and the next scheduling pass delivers it (the same reasoning the trigger route applies to queued
  input). `persist_event`/`broadcast` are left as they are; they do not raise in practice and the
  pattern is the same in every route.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
