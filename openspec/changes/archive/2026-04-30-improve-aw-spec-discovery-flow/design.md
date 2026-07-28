## Context

AgentWeave ships AW-Spec skills from `src/agentweave/templates/skills/`. During `agentweave init`, the CLI generates both `.claude/skills/<skill>/SKILL.md` and `.agents/skills/<skill>/SKILL.md` from every template returned by `list_skill_templates()`. Package data already includes `templates/skills/*`, so a new markdown template fits the existing architecture without a new registry or dependency.

The current `aw-spec-explore` template starts by loading AgentWeave session, role, and quality context. That is useful for implementation planning, but it makes the earliest exploration stage too focused on team execution. The proposed workflow should separate product/problem discovery from technical delivery discovery:

```
Explore What        Explore How             Formalize              Build
────────────        ───────────             ─────────              ─────
aw-spec-explore  -> aw-spec-technical    -> aw-spec-propose    -> aw-spec-apply
                    -explore                                     -> aw-spec-archive
```

## Goals / Non-Goals

**Goals:**

- Make `aw-spec-explore` primarily about understanding the idea, problem, users, workflows, requirements, risks, and relevant codebase context.
- Add `aw-spec-technical-explore` for implementation strategy, existing architecture discovery, stack/framework decisions, deployment planning, test strategy, and AgentWeave agent/role planning.
- Preserve the existing template-based skill generation model.
- Allow exploration artifacts to inform `aw-spec-propose` without requiring every user to create them.
- Update documentation so the AW-Spec workflow is clearly described as "explore what, explore how, propose, apply, archive."

**Non-Goals:**

- Replace OpenSpec or change the OpenSpec CLI schema.
- Add a new runtime dependency or new persistence layer.
- Force every change through both exploration stages.
- Implement automated parsing or validation of discovery artifacts in this change.
- Redesign `aw-spec-apply` beyond wording needed to align with the new discovery flow.

## Decisions

### Decision: Keep idea exploration framework-light

`aw-spec-explore` should no longer require reading `.agentweave/session.json`, `.agentweave/roles.json`, or `agentweave.yml` before discussion. It should still inspect the codebase when relevant, but the center of gravity becomes the user idea and the existing product behavior.

Alternative considered: keep all AgentWeave context in the first step. This preserves current multi-agent awareness, but it pulls role assignment and quality gates into discovery before the problem is clear.

### Decision: Add a separate technical exploration skill

Create `src/agentweave/templates/skills/aw-spec-technical-explore.md`. This skill should run naturally after `aw-spec-explore` and before `aw-spec-propose`, but users can invoke it directly for technical planning.

The skill should explicitly branch based on project state:

- Existing project: discover and obey current architecture, technologies, deployment model, tests, style, and constraints. Skip already-decided technology choices unless they need integration details.
- New project or greenfield area: compare stack, framework, persistence, deployment, CI, testing, and operational choices.

Alternative considered: expand `aw-spec-explore` with technical sections. That would keep fewer skills, but it would recreate the same overloaded discovery phase.

### Decision: Let technical exploration own AgentWeave execution planning

AgentWeave-specific questions such as available agents, role fit, handoffs, review flow, quality settings, and development cycle should move to `aw-spec-technical-explore`. This is the point where "how will we build it?" naturally includes "who should build each part?"

Alternative considered: keep team recommendations in `aw-spec-propose` only. That is too late to discuss sequencing, test ownership, and agent gaps before the proposal is written.

### Decision: Use optional discovery artifacts

The skills may offer to capture exploration notes under a predictable discovery location, for example:

```
spec/discovery/<slug>/idea.md
spec/discovery/<slug>/technical.md
```

`aw-spec-propose` should look for and read these artifacts when present. If they do not exist, it should proceed from the user's request as it does today.

Alternative considered: require discovery artifacts before proposal. That would make the workflow too rigid and reduce the current quick-propose path.

### Decision: Update propose into a synthesizer

`aw-spec-propose` should treat prior `idea.md` and `technical.md` files as source material. When technical exploration exists, propose should not invent major architecture, stack, deployment, testing, or agent-ownership decisions without noting or resolving conflicts.

Alternative considered: leave propose unchanged. That would make the new technical exploration useful conversationally, but the formal proposal could still drift away from the discoveries.

## Risks / Trade-offs

- More stages can feel heavier -> Keep both exploration stages optional and make each skill useful when invoked directly.
- Discovery artifacts could become stale -> Include dates and tell users to regenerate or revisit them when scope changes.
- Propose may over-trust stale notes -> Instruct propose to compare notes against the current codebase and flag conflicts.
- A new skill might not appear in generated projects -> Add focused tests or checks around skill template listing/generation.
- AgentWeave-specific planning could still leak into early exploration -> Rewrite `aw-spec-explore` guardrails to keep team planning out unless the user explicitly asks.

## Migration Plan

1. Rewrite `aw-spec-explore` to remove mandatory AgentWeave context loading and focus on idea/codebase exploration.
2. Add `aw-spec-technical-explore` as a new skill template.
3. Update `aw-spec-propose` to read optional discovery artifacts and synthesize from them.
4. Lightly update `aw-spec-apply` wording only if needed for consistency with the new proposal/team artifacts.
5. Update documentation and context-file references to list the new stage.
6. Add or update tests that verify skill templates are listed/generated and documentation references the new skill.

Rollback is straightforward: remove the new template and restore the previous skill text. Existing spec changes are unaffected because this change modifies templates and docs, not persisted change formats.

## Open Questions

- Should the discovery artifact directory be `spec/discovery/` to match current AW-Spec docs, or `openspec/discovery/` to align with the repo's current OpenSpec workspace?
- Should `aw-spec-propose` create discovery artifacts retroactively when the user skips exploration, or only consume artifacts that already exist?
- Should `aw-spec-technical-explore` include a fixed output checklist, or remain stance-oriented like `aw-spec-explore` with optional capture?
