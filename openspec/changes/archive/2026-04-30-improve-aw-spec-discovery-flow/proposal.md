## Why

AW-Spec currently blends idea discovery, technical planning, AgentWeave team planning, and proposal generation too early in the workflow. This makes exploration feel more framework-driven than idea-driven, and forces `aw-spec-propose` to invent product scope and technical strategy at the same time.

This change separates "what are we building?" from "how are we building it?" so proposals can be generated from clearer discovery artifacts and better grounded codebase investigation.

## What Changes

- Refocus `aw-spec-explore` on idea, problem, requirement, workflow, risk, and codebase exploration.
- Remove AgentWeave session/team/quality-loading requirements from `aw-spec-explore`.
- Add a new `aw-spec-technical-explore` skill that runs after idea exploration and before proposal generation.
- Make technical exploration focus on architecture, existing project constraints, technology choices, frameworks, deployment, testing strategy, implementation sequencing, and AgentWeave agent/role usage.
- Update `aw-spec-propose` to consume prior exploration artifacts when present and synthesize them into formal proposal, design, tasks, and team artifacts.
- Keep `aw-spec-apply` focused on implementation from formal tasks, with only minimal alignment updates if the new discovery artifacts affect task ownership or delegation wording.
- Update AW-Spec documentation to describe the new flow: explore what, explore how, propose, apply, archive.
- No breaking changes are intended for existing spec changes.

## Capabilities

### New Capabilities

- `aw-spec-workflow`: User-facing AW-Spec skill workflow for idea exploration, technical exploration, proposal generation, task application, and archival.

### Modified Capabilities

- None.

## Impact

- Skill templates: `src/agentweave/templates/skills/aw-spec-explore.md`, `src/agentweave/templates/skills/aw-spec-propose.md`, `src/agentweave/templates/skills/aw-spec-apply.md`, and a new `src/agentweave/templates/skills/aw-spec-technical-explore.md`.
- Skill installation or template copy logic may need updates if skill template lists are explicit.
- Documentation: `docs/guides/aw-spec-workflow.md`, `docs/guides/context-files.md`, and any command/skill reference that lists AW-Spec skills.
- Tests: template generation, packaged file inclusion, and focused assertions that the new skill is installed or referenced where expected.
- Dependencies: no new runtime dependencies.
