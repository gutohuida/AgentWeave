# Session Modes

AgentWeave supports three collaboration modes that determine how agents interact and make decisions.

## Mode Overview

| Mode | Description | Best For |
|------|-------------|----------|
| **hierarchical** | Principal agent assigns work, delegates execute | Clear ownership, structured workflows |
| **peer** | Agents can assign tasks to each other | Flat teams, mutual collaboration |
| **review** | Review-focused workflow | Code reviews, audits, quality gates |

## Hierarchical Mode (Default)

In hierarchical mode, one agent is designated as the **principal**. The principal:

- Does architecture and planning
- Assigns work to other agents
- Makes final decisions
- Reviews completed work

Other agents are **delegates** who:

- Execute assigned tasks
- Report back to the principal
- Can discuss but don't assign work to others

### Setup

```bash
agentweave init --project "My App" --mode hierarchical --principal claude
```

## Peer Mode

In peer mode, all agents are equals:

- Any agent can create and assign tasks
- Any agent can review another's work
- No single decision-maker

Use this for small teams where everyone contributes equally.

### Setup

```bash
agentweave init --project "My App" --mode peer
```

## Review Mode

Review mode is specialized for review workflows:

- Tasks flow through explicit review stages
- Emphasizes quality gates
- Clear separation between author and reviewer

Use this when code quality and formal reviews are critical.

### Setup

```bash
agentweave init --project "My App" --mode review
```

## Session Roles

Within a session, agents have specific roles:

| Role | Description |
|------|-------------|
| `principal` | Architecture, planning, final decisions |
| `delegate` | Executes assigned tasks |
| `reviewer` | Reviews work but doesn't execute |
| `collaborator` | General participant |

Developer roles are assigned in `.agentweave/roles.json`. Current files may use `agent_assignments` for a single default role per agent or `agent_roles` for multiple roles; the CLI normalizes both forms when you manage roles with `agentweave roles`. Each assigned role has a corresponding guide in `.agentweave/roles/*.md`.

### Multi-Role Assignment

Agents can have multiple roles simultaneously. For example, an agent might be both `tech_lead` and `backend_dev`, or `frontend_dev` and `qa_engineer`. This provides flexibility for small teams and cross-functional work.

See [Context Files](context-files.md) for details on managing roles via CLI.

## Changing Modes

To change the mode after initialization, edit `agentweave.yml`:

```yaml
project:
  mode: peer
```

Then apply the configuration:

```bash
agentweave activate
```

For older sessions without `agentweave.yml`, edit `.agentweave/session.json`:

```json
{
  "mode": "peer",
  ...
}
```

Then update the collaboration protocol:

```bash
agentweave sync-context
```

## See Also

- [Task Lifecycle](../reference/task-lifecycle.md) — how tasks flow through statuses
- [Configuration](../getting-started/configuration.md) — general configuration options
