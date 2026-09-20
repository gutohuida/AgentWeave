# The approval transport is not the tool surface

**Date:** 2026-09-20 · **Status:** exploration, nothing built · **Branch at writing:**
`autonomous/2026-09-17-daily` @ `d7f2694`

**Read the health warning first.** An earlier draft of this argument was **substantially wrong**,
and the way it was wrong is recorded as **F393**: it rested on `hub/hub/launchability.py`'s
nine-entry `RUNNER_CLI`, which is not the live runner registry. The operator caught it
(*"beware that I think you might be reading legacy code"*). What follows is what survived the
correction. **Nothing here is a live defect today**, and that is stated deliberately, because the
first version claimed otherwise.

## Why this is filed at all

The operator intends to implement GitHub Copilot support ("ghcp") and asked that any solution in
this area be thought about against *"the agnostic agentic structure"*, since Codex exists too. This
note exists so that whoever picks that up does not re-derive the analysis — and does not repeat the
mistake at the top of it.

## What is true today (measured 2026-09-20, not inherited)

- **Two runner kinds are creatable**: `RUNNER_CLIS = ("claude", "codex")`
  (`hub/hub/db/models.py:300`), enforced at `hub/hub/schemas/runners.py:22-23`, offered as
  `CLI_OPTIONS` in `hub/ui/src/components/runners/RunnersPage.tsx:19`.
- **Both are in `MCP_INJECTABLE_RUNNERS`** (`launchability.py:210`). So every runner an operator
  can create gets the Hub's MCP server injected and keeps the `workspace` posture and its approver.
- **Therefore the approver-less path is not reached by any ordinary configuration.** It is reached
  by a harness that refuses the injected server, or by `hub_client: "cli"`, which no UI sets
  (`grep -rn "hub_client" hub/ui/src/` → nothing).

**There is no runner-shaped defect open here.** The one real deployment that hits the approver-less
state is a machine whose policy blocks MCP servers — the operator reports their work PC is one, and
notes they do not run AgentWeave there today.

## The observation worth keeping

`resolve_access_path(runner, hub_client) -> "mcp" | "cli"` is one boolean answering three
independent questions:

1. can the Hub deliver its **tool surface** to this agent?
2. can the Hub **approve** this agent's tool calls?
3. how does the agent **reach the capability plane**?

Its own docstring concedes the coupling — the value *"also decides the run's permission posture"*.
For `claude` and `codex` the three co-vary, so the conflation costs nothing and the abstraction has
never been wrong in production. It becomes a question when a runner arrives for which they do not
co-vary.

**The layers underneath are already runner-agnostic**, which is the good news and the reason this is
a small change if it is ever needed:

| layer | state |
|---|---|
| policy | `_decide` (`mcp_server.py:1438`) and `decide_approval` (`codex_appserver.py:244`), both *"pure and total"*; `_decide`'s docstring says it mirrors the Codex contract |
| recording | `POST /permission-decisions` (`agent_actions.py:932`), used by `mcp_server.py:1500` and `codex_appserver.py:1090`, feeding checkpoints |
| plane | HTTP `/api/v1/agent-actions`, which the MCP tools are documented as *"a thin adapter over"* |

Only **transport** is unnamed as a layer — it is an if/else on one string with two values.

## The fact that makes a third transport cheap, if it is ever wanted

Recorded because it is not written down anywhere in this repo, and it removes the premise of a
question that has been parked since 2026-09-13.

On the installed `claude` 2.1.269:

- `--settings <file-or-json>` accepts **a settings JSON file or a JSON string** — the same inline
  shape `build_command` already uses for `--mcp-config`.
- Hook events include **`PermissionRequest`**, documented as *"Route or auto-decide approvals"*, and
  `PreToolUse`, which can return
  `{"hookSpecificOutput":{"permissionDecision":"allow"|"deny"|"ask"}}`.
- Hook types include `command` and `http` (POST JSON).

So on a Claude harness that refuses MCP, the Hub could carry approvals over a **hook** and keep
`_decide` and `/permission-decisions` unchanged — keeping its own policy and its own audit trail,
and keeping `Bash`, which the `acceptEdits` fallback can never give back.

**This is Claude-specific and therefore not itself the agnostic answer.** Its significance is that
it makes *approval transport* a real axis with more than one value, which retires the parked
`(i)/(ii)/(iii)` question in `DECISIONS.md` (`### 2026-09-13 afternoon`) rather than answering it:
that question only exists because "MCP or nothing" was assumed.

**Unverified, and must be before anything is built on it:** whether `PermissionRequest` fires under
headless `-p`; whether a hook can *grant* rather than only block (the repo's one adjacent
measurement, DEAD-ENDS 2026-09-15, is a `PreToolUse` hook *blocking* under `bypassPermissions`);
and whether a policy that blocks MCP servers also constrains hooks or managed settings.

## What this does not propose

No change directory, no tasks, no requirement delta. The honest trigger for picking this up is
**GitHub Copilot support landing** — at which point the first design question is not "is Copilot
MCP-injectable" but "what are its values on the three axes above". Note that
`src/agentweave/constants.py:210-221` already carries a `copilot` entry with an `mcp_add_cmd`
(`copilot mcp add …`), i.e. out-of-band registration rather than inline config — a shape the current
boolean cannot express. **That entry is legacy and wired to nothing** (F393); it is named here as a
hint about Copilot's shape, not as evidence of existing support.

## Related

- **F393** — the three disagreeing runner registries, and how this note's first draft was wrong.
- **F302** — decided 2026-09-09, unbuilt: the turn-start notice stops asserting a tool surface it
  cannot know. Independent of everything above, and true on any runner.
- **F325** — Codex app-server never receives the canonical context: the same "per-runner axis
  handled by a scattered branch" shape, on the context-delivery axis.
- `DECISIONS.md` `### 2026-09-13 afternoon` — the parked `(i)/(ii)/(iii)` question.
