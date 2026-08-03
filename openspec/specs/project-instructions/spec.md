# project-instructions Specification

## Purpose
Per-project instruction content stored in Hub DB and served prepended to every agent's role guide; editable via Hub UI. `openspec/changes/single-runtime` removed the local-file mirror and its `agentweave init` placeholder — the Hub DB is now the only source.

## Requirements
### Requirement: Hub stores project instructions per project
The Hub DB SHALL store project-wide instruction content in a `ProjectInstructions` table scoped by `project_id`.

#### Scenario: Empty instructions on new project
- **WHEN** a project has no instructions saved
- **THEN** `GET /api/v1/project/instructions` returns `{ "content": "" }`

#### Scenario: Save instructions via Hub API
- **WHEN** a PUT request is made to `/api/v1/project/instructions` with `{ "content": "..." }`
- **THEN** the content is persisted and subsequent GET returns the same content

---

### Requirement: Hub prepends instructions to role guide content
The Hub SHALL prepend project instructions before the role guide content in every `GET /api/v1/agents/context` response.

#### Scenario: Instructions exist — prepended to role guide
- **WHEN** project has non-empty instructions and agent calls `get_context`
- **THEN** response content is `[instructions]\n\n---\n\n[role guide]`

#### Scenario: No instructions — role guide returned unchanged
- **WHEN** project has no instructions (empty or no DB row)
- **THEN** response content is the role guide only, unchanged

---

### Requirement: Hub UI provides instructions editor
The Hub UI SHALL provide an "Instructions" screen with a markdown textarea, a Save button, and a session disclaimer.

#### Scenario: User saves instructions
- **WHEN** user edits the textarea and clicks Save
- **THEN** content is persisted via PUT and UI confirms success

#### Scenario: Disclaimer shown
- **WHEN** Instructions screen is displayed
- **THEN** a notice reads "Changes take effect when agents start a new session"

#### Scenario: Existing instructions loaded on open
- **WHEN** user navigates to the Instructions screen
- **THEN** the textarea is pre-filled with the current saved content
