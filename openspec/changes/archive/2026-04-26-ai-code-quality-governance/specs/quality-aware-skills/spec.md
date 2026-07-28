## ADDED Requirements

### Requirement: aw-spec-propose generates quality-gated task structure
When `review_required: true` or `docs_threshold` is not `never`, `aw-spec-propose` SHALL structure `tasks.md` with quality gates baked into the task order and role assignments:
- Test spec task (assigned to `qa_engineer`) precedes the implementation task
- Implementation task includes a decision doc subtask if threshold applies
- A review task (assigned to `code_reviewer` agent) follows implementation — structurally preventing echo-chamber at spec time
- If no `code_reviewer` role is assigned in the session, the review task SHALL include a warning: "⚠ No reviewer assigned — add via: `agentweave roles add <agent> code_reviewer`"

#### Scenario: Review task assigned to different agent than implementer
- **WHEN** `aw-spec-propose` generates tasks.md with `review_required: true`
- **THEN** the review task SHALL be assigned to the agent with `code_reviewer` role, not the implementing agent

#### Scenario: Missing code_reviewer surfaces as warning in tasks.md
- **WHEN** `review_required: true` and no agent has `code_reviewer` in `roles.json`
- **THEN** the review task in tasks.md SHALL include the setup command to assign the role

### Requirement: aw-spec-propose includes Security Considerations in design.md
`aw-spec-propose` SHALL include a `## Security Considerations` section in `design.md` between Key Decisions and Dependencies, prompting reasoning about permissions, sensitive data flows, and packages being introduced.

#### Scenario: Security section present in all generated design docs
- **WHEN** `aw-spec-propose` generates `design.md`
- **THEN** the file SHALL contain a `## Security Considerations` section

### Requirement: aw-spec-propose flags missing code_reviewer in team.md
When `review_required: true` and no agent has `code_reviewer` role, `aw-spec-propose` SHALL mark the role as a quality gate blocker in `team.md` — not just a missing role.

#### Scenario: code_reviewer gap marked as blocker
- **WHEN** `review_required: true` and `code_reviewer` is absent from `roles.json`
- **THEN** the gap analysis in `team.md` SHALL label this role as "⚠ Quality gate blocker" with the setup command

### Requirement: aw-spec-apply reads quality config and produces decision docs
`aw-spec-apply` SHALL read `quality:` from `agentweave.yml` before implementing any task and produce a decision doc before marking each non-trivial task complete.

#### Scenario: Decision doc produced before task marked complete
- **WHEN** `docs_threshold: non_trivial` and the current task is non-trivial
- **THEN** `aw-spec-apply` SHALL create the decision doc at the resolved path before updating the task checkbox

#### Scenario: Delegation includes quality expectations
- **WHEN** `aw-spec-apply` delegates tasks to another agent
- **THEN** the delegation message SHALL include active quality settings (`docs_threshold`, `review_required`, `docs_path`)

### Requirement: aw-spec-archive checks approved status before archiving
`aw-spec-archive` SHALL verify that no tasks are in `under_review` or `revision_needed` status before archiving, in addition to checking task checkboxes.

#### Scenario: Archive blocked on pending reviews
- **WHEN** one or more tasks are in `under_review` status at archive time
- **THEN** `aw-spec-archive` SHALL warn the user and require explicit confirmation before proceeding

### Requirement: aw-done routes via quality config instead of manual prompt
`aw-done` SHALL route tasks to review automatically based on `quality.review_required` rather than asking the user each time.

#### Scenario: Task auto-routed to under_review when review_required
- **WHEN** `review_required: true` and `/aw-done <task-id>` is run
- **THEN** the task SHALL be set to `under_review` and routed to the `code_reviewer` agent without a manual prompt

#### Scenario: Decision doc checked before routing
- **WHEN** `review_required: true` and `docs_threshold` applies to the task
- **THEN** `aw-done` SHALL verify the decision doc exists before routing; if missing, warn and offer to produce it first

### Requirement: aw-status includes quality health section
`aw-status` SHALL include a Quality Health block when `quality:` is configured, showing: tasks under review and wait time, missing decision docs, flagged mismatches, and a stale review alert for tasks waiting more than a configurable threshold.

#### Scenario: Quality health visible in status output
- **WHEN** `quality.review_required: true` and `/aw-status` is run
- **THEN** the output SHALL include a Quality Health section with under-review task counts and wait times

### Requirement: aw-collab-start surfaces quality config per role
`aw-collab-start` SHALL include role-specific quality orientation: implementing agents see docs threshold and TDD requirement; reviewers see the zero-trust sequence and docs path; PM sees echo-chamber guard setting and review routing rules.

#### Scenario: Reviewer sees docs path on session start
- **WHEN** an agent with `code_reviewer` role runs `aw-collab-start`
- **THEN** the orientation output SHALL include the configured `docs_path` so the agent knows where to find decision docs
