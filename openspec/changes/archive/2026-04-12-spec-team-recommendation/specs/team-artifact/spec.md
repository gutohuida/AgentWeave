## ADDED Requirements

### Requirement: team.md is a registered spec-driven artifact
The `spec-driven` schema SHALL include `team.md` as a 5th artifact, ordered after `proposal`, with no hard dependency on `design`, `specs`, or `tasks`.

#### Scenario: Status shows team artifact
- **WHEN** a user runs `openspec status --change <name>` on a spec-driven change
- **THEN** the output SHALL include a `team` artifact entry with status `done` (if `team.md` exists) or `ready` (if `proposal.md` is done but `team.md` is missing)

#### Scenario: team.md dependency is proposal only
- **WHEN** a change has `proposal.md` but no `design.md` or `specs/`
- **THEN** the `team` artifact status SHALL be `ready` (not `blocked`)

---

### Requirement: team.md has a defined four-section structure
A valid `team.md` SHALL contain four sections in order:
1. `## Recommended Team` — a table with columns: Role, Label, Why Needed
2. `## Role Reasoning` — a paragraph per role grounding the choice in specific spec decisions
3. `## Gap Analysis` — comparison of recommended roles vs. current session agents/roles
4. `## Setup Commands` — ready-to-run `agentweave` commands to add missing agents

#### Scenario: Recommended Team section is present
- **WHEN** `team.md` is generated
- **THEN** it SHALL contain a markdown table under `## Recommended Team` with at least one row

#### Scenario: Role Reasoning is spec-grounded
- **WHEN** `team.md` is generated
- **THEN** each role in the Recommended Team table SHALL have a corresponding paragraph under `## Role Reasoning` that references at least one decision from the proposal or spec

#### Scenario: Gap Analysis reflects current session
- **WHEN** current session agent roles are known at generation time
- **THEN** `## Gap Analysis` SHALL mark each recommended role as present (✓) or missing (✗) based on the current session

#### Scenario: Gap Analysis falls back gracefully
- **WHEN** current session agent roles are NOT available at generation time
- **THEN** `## Gap Analysis` SHALL display the full recommended team without a diff and note that session state was unavailable

#### Scenario: Setup Commands are runnable
- **WHEN** gap analysis identifies missing roles
- **THEN** `## Setup Commands` SHALL contain one `agentweave agent add` or `agentweave roles add` command per missing role

---

### Requirement: team.md carries a generation timestamp note
The `team.md` file SHALL include a note at the top indicating it reflects the spec at the time of generation and may need to be regenerated if the spec changes significantly.

#### Scenario: Staleness note is present
- **WHEN** `team.md` is generated
- **THEN** the file SHALL begin with a `> Note:` blockquote stating the generation date and that the file reflects the spec at that point in time
