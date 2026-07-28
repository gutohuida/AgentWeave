## 1. Skill Template Changes

- [x] 1.1 Rewrite `src/agentweave/templates/skills/aw-spec-explore.md` so it focuses on idea, problem, requirement, workflow, risk, and codebase exploration.
- [x] 1.2 Remove mandatory AgentWeave session, role, team, and quality-loading steps from `aw-spec-explore`.
- [x] 1.3 Add `src/agentweave/templates/skills/aw-spec-technical-explore.md` with guidance for architecture, stack, framework, deployment, testing, sequencing, and AgentWeave agent/role planning.
- [x] 1.4 Ensure `aw-spec-technical-explore` handles both existing-project and greenfield-project paths.
- [x] 1.5 Update `src/agentweave/templates/skills/aw-spec-propose.md` to read optional prior discovery artifacts and synthesize from them when present.
- [x] 1.6 Lightly update `src/agentweave/templates/skills/aw-spec-apply.md` only where needed to align wording with the new discovery and proposal flow.

## 2. Discovery Artifact Conventions

- [x] 2.1 Decide and document the discovery artifact location used by the skills.
- [x] 2.2 Add optional capture guidance for idea exploration notes.
- [x] 2.3 Add optional capture guidance for technical exploration notes.
- [x] 2.4 Ensure `aw-spec-propose` can proceed when discovery artifacts are absent.
- [x] 2.5 Ensure `aw-spec-propose` surfaces conflicts between discovery artifacts and current codebase findings.

## 3. Documentation Updates

- [x] 3.1 Update `docs/guides/aw-spec-workflow.md` from the four-stage flow to the expanded idea exploration, technical exploration, propose, apply, archive flow.
- [x] 3.2 Update examples in `docs/guides/aw-spec-workflow.md` to show `/aw-spec-technical-explore` between `/aw-spec-explore` and `/aw-spec-propose`.
- [x] 3.3 Update `docs/guides/context-files.md` skill references to include `/aw-spec-technical-explore`.
- [x] 3.4 Update any README or docs index references if they list AW-Spec stages or skills.

## 4. Generation and Packaging Verification

- [x] 4.1 Verify the new skill template is returned by the existing skill template listing.
- [x] 4.2 Verify `agentweave init` or the relevant skill generation path creates the new skill for Claude skills.
- [x] 4.3 Verify the Codex skill generation path creates the new skill.
- [x] 4.4 Add or update focused tests for skill template listing/generation if suitable tests already exist.

## 5. Final Validation

- [x] 5.1 Run relevant Python tests for CLI/template generation.
- [x] 5.2 Run docs or markdown checks if available.
- [x] 5.3 Run `openspec status --change improve-aw-spec-discovery-flow` and confirm the change is apply-ready.
- [x] 5.4 Review generated artifacts for consistency with the requirement spec.
