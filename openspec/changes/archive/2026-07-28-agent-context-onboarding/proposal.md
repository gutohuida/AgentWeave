## Why

AgentWeave already has the ingredients for useful agent context, but they are scattered across `agentweave.yml`, role files, `ai_context.md`, project instructions, shared session context, and Hub role lookup. Agents can start work with incomplete or stale information, and external agents that connect through Hub/MCP have no single onboarding path unless they are already declared in `agentweave.yml`.

This change makes generated per-agent context the canonical model-facing artifact and adds a Hub-facing onboarding flow for registered or external agents.

## What Changes

- Generate a concise project operating profile from `agentweave.yml` and session state.
- Include project metadata, mode, principal, team topology, runner/model hints, quality gates, and scheduled job summaries in generated agent context.
- Treat `.agentweave/context/<agent>.md` as the canonical runtime context for each agent.
- Keep root `CLAUDE.md`, `GEMINI.md`, and `AGENTS.md` as lightweight bootstraps that point agents to their generated context and collaboration protocol.
- Filter or warn on placeholder `ai_context.md` content instead of injecting stale template text.
- Add a Hub/MCP `get_agent_context(agent)` capability for external and self-registered agents.
- Preserve `get_context(role)` as a role-guide lookup while using the richer agent context path for onboarding and runtime orientation.
- Add diagnostics that show which context files each agent receives and whether generated context is stale or incomplete.

## Capabilities

### New Capabilities
- `agent-context-onboarding`: Generated model context, project operating profiles, and Hub/MCP onboarding for declared, registered, and external agents.

### Modified Capabilities

None.

## Impact

- CLI context generation: `sync-context`, `activate`, role assignment flows, pilot registration, and diagnostics.
- Hub API and MCP tools: agent context retrieval and external-agent onboarding behavior.
- Templates and docs: root agent files, role guides, context-file documentation, and MCP tool reference.
- Runtime launch paths: Claude, Codex, Codex MCP, OpenCode, Kimi pilot, and watchdog-triggered prompts should consistently receive the generated context where supported.
