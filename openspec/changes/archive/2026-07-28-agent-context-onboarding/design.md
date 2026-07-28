## Context

AgentWeave currently generates several context files with overlapping responsibilities:

- Root auto-read files: `CLAUDE.md`, `GEMINI.md`, and `AGENTS.md`.
- Source project context: `.agentweave/ai_context.md`.
- Project-wide instructions: `.agentweave/project_instructions.md` or Hub `ProjectInstructions`.
- Role assignment and role guides: `.agentweave/roles.json` and `.agentweave/roles/*.md`.
- Live session state: `.agentweave/shared/context.md`.
- Per-agent generated context: `.agentweave/context/<agent>.md`.

The per-agent generated context is already the richest artifact, but the system does not consistently treat it as canonical. Hub `get_context(role)` only returns role-oriented content, root files still instruct agents to manually traverse multiple files, and external agents that connect through Hub/MCP need a clean onboarding path before they are declared in `agentweave.yml`.

The design keeps `agentweave.yml` as the declared-team source of truth while allowing Hub-registered external agents to receive provisional context and collaborate when explicitly assigned.

## Goals / Non-Goals

**Goals:**

- Make `.agentweave/context/<agent>.md` the canonical runtime context for declared agents.
- Generate a project operating profile from `agentweave.yml` plus normalized session/roles state.
- Keep role guides focused on stable responsibilities and boundaries rather than duplicating full project data.
- Add `get_agent_context(agent)` as the onboarding/runtime context API for declared, registered, and external agents.
- Preserve `get_context(role)` for role guide lookup and compatibility.
- Make context generation skip or clearly flag placeholder `ai_context.md` content.
- Add diagnostics that explain exactly what context each agent receives.

**Non-Goals:**

- Replacing `agentweave.yml` as the source of truth for the declared team.
- Automatically adding external agents to `agentweave.yml`.
- Forcing all runners to support identical context injection if the underlying CLI does not expose that capability.
- Adding new non-stdlib runtime dependencies to the CLI.
- Redesigning task assignment, scheduling, or role taxonomy beyond context/onboarding needs.

## Decisions

### Decision 1: Introduce a shared context builder

Create a reusable context-building layer that can produce:

- project operating profile markdown
- per-agent runtime context markdown
- external/provisional onboarding context markdown
- context freshness metadata

The builder should be used by CLI `sync-context`, watchdog fallback generation, pilot registration, and Hub context endpoints where possible.

Alternative considered: keep context generation inside `cli.py` and duplicate similar formatting in Hub. That preserves the current shape but makes drift more likely and leaves external-agent onboarding inconsistent.

### Decision 2: Project operating profile is generated, not hand-authored

The project operating profile should be synthesized from already validated sources:

- `agentweave.yml` when available
- `.agentweave/session.json` as runtime fallback
- `.agentweave/roles.json` for normalized role assignments
- quality settings copied into session state

The profile should include project name, mode, principal, team directory, runner/model hints, quality gates, and a compact scheduled jobs summary. It should not include secrets or environment variable values.

Alternative considered: ask users to maintain this profile manually in `ai_context.md`. That is simpler but repeats the current failure mode: stale or placeholder project context.

### Decision 3: Role guides stay stable and project data is layered around them

Role files should define scope, responsibilities, boundaries, quality behavior, handoff rules, and escalation paths. Project-specific facts should be injected by the generated context around the role guide, not copied into every role file.

Alternative considered: regenerate role files with full project context embedded. That makes each role file self-contained, but it bloats committed files and creates stale duplicated facts.

### Decision 4: `get_agent_context(agent)` is the external-agent onboarding API

Add an MCP/Hub tool that returns context by agent name rather than role. It should support three states:

- declared agent: return generated runtime context for that agent
- registered but undeclared agent: return provisional onboarding context using registration metadata and any requested roles
- unknown agent: return minimal onboarding instructions explaining how to register before taking work

The response should include structured metadata such as `known`, `declared`, `registered`, `provisional`, `roles`, `missing`, and `context`.

Alternative considered: extend `get_context(role)` to handle onboarding. That would overload a role lookup API and would not work well for multi-role agents or external agents without a settled role.

### Decision 5: Root files become lightweight bootstraps

`CLAUDE.md`, `GEMINI.md`, and `AGENTS.md` should identify the AgentWeave project and point agents to the generated per-agent context. They should keep only essential fallback rules for tools that auto-read root files before injected context is available.

Alternative considered: keep full collaboration protocol in root files. That helps manual sessions but duplicates content that should live in generated per-agent context.

### Decision 6: Live session context remains prompt-level for watchdog triggers

`.agentweave/shared/context.md` changes frequently. Hub/watchdog triggers should continue prepending it to each prompt as current-session focus. Generated per-agent context may instruct manual agents to read it, but should avoid embedding stale live content unless explicitly refreshed.

Alternative considered: embed shared context into every generated context file. That makes manual starts easier but increases staleness and requires frequent regeneration.

## Risks / Trade-offs

- Context becomes too large → Keep project profile compact, filter placeholders, and prefer summaries over raw YAML dumps.
- External agents act before authorization → Provisional context must explicitly forbid file edits and task claims until registration/assignment is complete.
- Hub and CLI context drift → Use a shared builder or mirrored tests that assert equivalent sections.
- Existing users rely on rich root files → Keep enough bootstrap guidance in root files and document the new canonical context path.
- `get_agent_context` leaks sensitive data → Never include secret values; only include environment variable names and public runner metadata.
- Placeholder detection hides user-authored content accidentally → Use conservative detection for known `[Replace with...]` template markers and surface diagnostics rather than deleting files.

## Migration Plan

1. Add the shared builder and tests while preserving current generated file locations.
2. Update `sync-context`, `activate`, watchdog context fallback, and pilot registration to use the builder.
3. Add Hub/API/MCP `get_agent_context(agent)` without removing `get_context(role)`.
4. Update root templates to lightweight bootstraps.
5. Update docs and diagnostics so users can see the new context flow.
6. Keep existing files compatible; users can run `agentweave sync-context --force` to regenerate into the new format.

Rollback is straightforward because the change does not require a destructive migration: keep existing files and restore old templates/context builder behavior if needed.
