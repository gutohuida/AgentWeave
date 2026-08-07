# How long an agent waits for you, and where you say so

**Approved:** 2026-08-07, operator (*"#3: Make it configurable. Should we have a config screen for
agents for things like this and future things?"*)

## Why

Three timeouts govern how long an agent will wait for the operator, and all three are module
constants: `OPERATOR_DECISION_TIMEOUT` (120s), `QUESTION_ANSWER_TIMEOUT` (240s) and
`CODEX_OPERATOR_DECISION_TIMEOUT` (120s). They were set to what was measured, which was right for
establishing that the mechanism works and wrong as a permanent answer: how long a wait is reasonable
depends on the agent and the operator, not on what a spike happened to tolerate.

An operator watching one agent closely wants it to give up quickly and get on with something. An
operator who steps away from a long-running agent wants it to still be waiting when they return.
Neither is served by a number compiled into the Hub.

### The second half of the question: where do agent settings live?

The operator asked, and it needed answering before anything could be built. The answer is that they
already have a home nobody has been treating as one.

`AgentInfoTab` is not an info panel — it already edits the agent's runner and charter bindings. And
the conversation's overflow menu already opens it *without unmounting the conversation*, which is
exactly the mid-chat path a gear would have been for.

Adding a gear would create a third place settings live and blur a distinction the product currently
makes clearly:

| Surface | Scope | Lifetime |
|---|---|---|
| Composer pills (Model, Effort, Permissions) | this conversation | ephemeral, chosen as you send |
| The agent's own tab | this agent | durable, chosen once |

A timeout is durable and per-agent. It belongs in the tab.

## What changes

- Each agent carries its own `permission_timeout_seconds` and `question_timeout_seconds`. Unset
  means the measured default, so nothing changes for an agent nobody has configured.
- The values reach the approval tool and the question tool through the run's environment, the way
  the workspace boundary and the permission posture already do.
- `AgentInfoTab` becomes the agent's **Settings** tab, rebuilt on the `SettingsSection` /
  `SettingsRow` components the project settings panel already uses, with the two waits as its first
  settings section.

## Impact

- **`Agent`** gains two nullable columns (migration 0034); `PATCH /agents/{name}` accepts them.
- **`hub/hub/mcp_server.py`** reads both from the environment, falling back to today's constants.
- **`hub/hub/api/v1/agent_trigger.py`** puts them in the spawn environment and uses the permission
  value for the Codex app-server wait.
- **`AgentInfoTab.tsx`** — renamed tab, new section.

## Explicitly not in this change

- **A gear, a modal, or a separate settings screen.** See above: the tab is the answer.
- **Project-level defaults.** An agent with nothing set uses the built-in default. A per-project
  default layer is a third place to look for one number, and no one has asked for it.
- **Making other constants configurable.** The poll intervals and the hop budget stay as they are;
  this change is about the waits the operator actually experiences.
