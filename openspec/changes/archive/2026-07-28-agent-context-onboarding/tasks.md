## 1. Shared Context Builder

- [x] 1.1 Add a shared context builder module that renders project operating profiles, declared-agent context, provisional external-agent context, and freshness metadata.
- [x] 1.2 Add unit tests for project profile rendering from `agentweave.yml`, session fallback data, roles config, quality settings, and jobs.
- [x] 1.3 Add placeholder detection for untouched `ai_context.md` template content and test both omit and warning behavior.
- [x] 1.4 Ensure rendered context never includes secret values and only lists environment variable names.

## 2. CLI Context Generation

- [x] 2.1 Refactor `agentweave sync-context` to use the shared builder for `.agentweave/context/<agent>.md`.
- [x] 2.2 Update `agentweave activate` context refresh behavior to preserve the same generated sections after agent, role, quality, or job changes.
- [x] 2.3 Update watchdog fallback context generation to use the shared builder.
- [x] 2.4 Update pilot session registration paths to regenerate context through the shared builder.
- [x] 2.5 Update root `CLAUDE.md`, `GEMINI.md`, and `AGENTS.md` templates into lightweight bootstrap files.

## 3. Runtime Injection Coverage

- [x] 3.1 Verify Claude, claude_proxy, native, Codex, Codex MCP, OpenCode, and Kimi pilot launch paths inject or reference `.agentweave/context/<agent>.md`.
- [x] 3.2 Add or update tests for runner command construction with generated context files.
- [x] 3.3 Preserve watchdog prompt prepending of `.agentweave/shared/context.md` as live session focus.

## 4. Hub and MCP Agent Onboarding

- [x] 4.1 Add Hub API support for retrieving context by agent name for declared, registered undeclared, and unknown agents.
- [x] 4.2 Add CLI MCP `get_agent_context(agent)` tool that calls the Hub endpoint and returns structured status plus markdown context.
- [x] 4.3 Add Hub MCP `get_agent_context(agent)` tool with the same response shape.
- [x] 4.4 Preserve `get_context(role)` behavior and add guidance or metadata pointing callers to `get_agent_context(agent)` for full context.
- [x] 4.5 Add tests for declared-agent runtime context, registered undeclared provisional context, unknown-agent registration guidance, and invalid agent names.

## 5. Diagnostics and Freshness

- [x] 5.1 Add context diagnostics that list source files, generated files, root bootstrap files, and runner-specific injection mechanisms.
- [x] 5.2 Detect missing, stale, or incomplete `.agentweave/context/<agent>.md` files and suggest `agentweave sync-context` or `agentweave sync-context --force`.
- [x] 5.3 Warn when `.agentweave/ai_context.md` still contains known placeholder content.
- [x] 5.4 Add tests for stale context detection and placeholder diagnostics.

## 6. Documentation

- [x] 6.1 Update the context files guide to define `.agentweave/context/<agent>.md` as canonical runtime context.
- [x] 6.2 Update the `agentweave.yml` reference to explain which fields appear in the generated project operating profile.
- [x] 6.3 Update MCP tools documentation with `get_agent_context(agent)` and the intended external-agent onboarding flow.
- [x] 6.4 Update role management documentation to clarify that role files are stable contracts and project data is layered around them.

## 7. Verification

- [x] 7.1 Run CLI unit tests covering context generation, roles, config, diagnostics, watchdog command construction, and MCP tools.
- [x] 7.2 Run Hub backend tests covering the new context endpoint and MCP tool behavior.
- [x] 7.3 Run `openspec validate agent-context-onboarding --strict` or the repository's equivalent OpenSpec validation command.
