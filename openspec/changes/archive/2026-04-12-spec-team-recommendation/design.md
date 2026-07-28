## Context

AgentWeave's spec workflow (`opsx:explore` → `opsx:propose`) currently produces a proposal, design, specs, and tasks — all scoped to "what to build." But there's no artifact capturing "who should build it." Users exploring a project with a minimal team (e.g., just an architect) get no signal about what team composition the project actually calls for.

The goal is to add `team.md` as a first-class OpenSpec artifact in the `spec-driven` schema, and update the explore/propose skills to surface team recommendations derived from the spec — not from the current session's agents.

Current state:
- `spec-driven` schema has 4 artifacts: `proposal`, `design`, `specs`, `tasks`
- `opsx:explore` converges toward a proposal but never recommends a team
- `opsx:propose` generates all 4 artifacts but not team composition
- `roles.json` defines 13 role types with labels and responsibilities
- The `agentweave roles` CLI can add/set roles on session agents

## Goals / Non-Goals

**Goals:**
- Add `team.md` as a 5th artifact in the `spec-driven` schema
- Define a consistent `team.md` structure: recommended roles, reasoning, gap analysis, setup commands
- Update `opsx:explore` to offer team recommendation at natural closure points
- Update `opsx:propose` to generate `team.md` alongside the other artifacts
- Keep team recommendation spec-driven (derived from what the spec decided, not from current agents)

**Non-Goals:**
- Injecting team reasoning into per-agent context files at session start
- Auto-spawning or configuring agents
- Changing how roles are defined in `roles.json`
- Adding a new CLI command (all changes are in skills and schema)

## Decisions

### D1: `team.md` as a schema artifact vs. an optional output

**Decision:** Register `team.md` as a proper schema artifact in `spec-driven`.

**Alternatives considered:**
- Conversational output only (team suggestion in chat, no file) — loses the recommendation after the session, not referenceable
- Optional file (generate if asked) — inconsistent; users won't know to ask

**Rationale:** Treating it as a schema artifact means it shows up in `openspec status`, can be checked for completeness, and persists alongside the spec. The overhead is one lightweight file.

---

### D2: Where `team.md` sits in artifact ordering

**Decision:** `team.md` comes after `proposal` but has no hard dependency on `design`, `specs`, or `tasks`. It can be generated once the proposal is done.

**Rationale:** Team composition derives from the project's goals and scope (proposal), not from implementation details (design/specs). Generating it early keeps it useful during planning.

---

### D3: team.md structure

**Decision:** Four sections:

```
## Recommended Team
Table: role | label | why needed for this project

## Role Reasoning
Per-role paragraph grounding the choice in specific spec decisions

## Gap Analysis
Current session agents/roles vs. recommended — what's missing

## Setup Commands
Ready-to-run `agentweave` commands to fill the gaps
```

**Alternatives considered:**
- Just a role list (no reasoning) — too generic, doesn't help agents or users understand context
- Full per-agent context injection — overkill given drift isn't a pain point

**Rationale:** The reasoning section is what makes this valuable over a generic team template. It answers "why this role for *this* project" — not "what does this role do in general."

---

### D4: Skill update approach

**Decision:** Update `opsx:explore` and `opsx:propose` skill prompts in their source files to include team recommendation instructions.

For `opsx:explore`: add a closing section — when the conversation reaches a natural conclusion point (proposal-ready), offer to generate `team.md`.

For `opsx:propose`: include `team.md` generation as part of the artifact generation sequence (after proposal, before or alongside design).

**Rationale:** Skills are the right layer for behavioral changes; the schema artifact handles persistence.

## Risks / Trade-offs

- **Risk**: Gap analysis requires reading the current session state (which agents are configured) — this may not always be available inside the skill context.
  → **Mitigation**: Fall back to showing the full recommended team without a gap diff if session state is unavailable. Gap analysis is a nice-to-have, not core.

- **Risk**: Team recommendation could become stale if the spec evolves significantly.
  → **Mitigation**: `team.md` is regenerable at any time via `opsx:propose`. Note in the file that it reflects the spec at generation time.

## Open Questions

- Should `team.md` be regenerated automatically when specs change, or only on explicit invocation? (Current answer: explicit only — no auto-regeneration.)
