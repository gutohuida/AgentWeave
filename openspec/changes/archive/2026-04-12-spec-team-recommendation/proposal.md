# Spec-Driven Team Recommendation

## Summary

When exploring a project idea with AgentWeave's spec mode, the current flow is implicitly constrained by whatever agents are already in the session. This limits thinking to "what can my current team build?" rather than "what's the best way to build this?"

This change decouples the spec from the current team. After exploring and producing a spec, AgentWeave generates a `team.md` artifact: the ideal team composition for the project, the reasoning behind each role choice, and a gap analysis vs. the current session with ready-to-run setup commands.

## Problem

- `opsx:explore` and `opsx:propose` are mentally anchored to the current session's agents and roles
- Users who start exploring with only one or two agents (e.g., just `architect`) never get a recommendation about what team would actually serve the project well
- There's no artifact that captures *why* a particular team composition was chosen — that reasoning is lost after the session

## Solution

Add `team.md` as a new OpenSpec artifact in the `spec-driven` schema. It is generated at proposal time (or can be generated standalone after explore).

`team.md` contains:
1. **Recommended roles** — which roles the project needs, derived from the spec
2. **Reasoning** — why each role is needed, grounded in the specific spec decisions
3. **Gap analysis** — which roles you currently have vs. which are missing
4. **Setup commands** — `agentweave agent add` commands to fill the gaps

The explore and propose skills are updated to always produce (or offer to produce) `team.md` after a spec crystallizes. The flow is unconstrained — it reasons from the spec outward to the ideal team, not from the current team inward to a constrained spec.

## Non-Goals

- Injecting team reasoning into per-agent context files at session start (not needed — role drift is not a current pain point)
- Changing how roles are defined or assigned (that system stays as-is)
- Auto-spawning or configuring agents (team.md produces commands, not actions)

## Impact

- `openspec/config.yaml` (or schema definition): add `team` as an artifact in `spec-driven` schema
- `opsx:explore` skill: surface team recommendation naturally at end of explore
- `opsx:propose` skill: generate `team.md` alongside `proposal.md`
- New `team.md` template with sections: Recommended Team, Role Reasoning, Gap Analysis, Setup Commands

## Scope

Small. Two skill updates + one new artifact template + schema registration. No CLI or Hub changes required.
