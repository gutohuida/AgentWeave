## ADDED Requirements

### Requirement: Decision document template
The system SHALL provide a `code_decision.md` template in `src/agentweave/templates/` with the following structure:
- Header fields: `task_id`, `requirement` (original prompt/task description), `agent`, `model`, `session`, `date`, `files_modified`, `ai_generated` (list of fully AI-generated files)
- Body sections: `## What Was Done`, `## Why This Approach`, `## Alternatives Considered`, `## Risks / Known Limitations`

#### Scenario: Template is accessible via get_template
- **WHEN** `get_template("code_decision")` is called
- **THEN** the system SHALL return the decision doc template string without error

### Requirement: Decision doc path resolution
The system SHALL resolve the decision doc storage path based on `quality.docs_path`:
- If `docs_path` is not set: store at `.agentweave/code-docs/<task-id>.md` (gitignored)
- If `docs_path` is set: store at `<docs_path>/<task-id>.md` (committable, outside `.agentweave`)

#### Scenario: Doc stored inside .agentweave when docs_path omitted
- **WHEN** `quality.docs_path` is not configured
- **THEN** the resolved path SHALL be `.agentweave/code-docs/<task-id>.md`

#### Scenario: Doc stored at custom path when docs_path is set
- **WHEN** `quality.docs_path` is set to `"code-docs"`
- **THEN** the resolved path SHALL be `code-docs/<task-id>.md`

### Requirement: Decision doc required before task completion at threshold
The system (via agent role directives) SHALL require implementing agents to produce a decision doc before marking a task complete, when `docs_threshold` indicates it is required.

#### Scenario: Doc required for non_trivial threshold
- **WHEN** `docs_threshold: non_trivial` and the implementing agent judges the task as non-trivial
- **THEN** the agent SHALL produce a decision doc at the resolved path before updating task status to `completed`

#### Scenario: Doc never required when threshold is never
- **WHEN** `docs_threshold: never`
- **THEN** the agent SHALL NOT be required to produce a decision doc for any task

### Requirement: Attribution tag in decision doc header
When `attribution_tag: true`, the decision doc header SHALL include an `ai_generated` field listing files that were fully AI-generated (not merely AI-assisted).

#### Scenario: Attribution field populated when tag is enabled
- **WHEN** `attribution_tag: true` and a decision doc is produced
- **THEN** the `ai_generated` header field SHALL list any files written entirely by the AI agent

### Requirement: Decision docs archived with their change
When a spec change is archived, any decision docs associated with tasks in that change SHALL move with the change directory to the archive location.

#### Scenario: Decision docs present in archived change
- **WHEN** a spec change is archived via `aw-spec-archive`
- **THEN** all decision docs for that change's tasks SHALL be present in the archive directory
