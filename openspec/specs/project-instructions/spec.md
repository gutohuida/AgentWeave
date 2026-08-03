# project-instructions Specification

## Purpose
Per-project instruction content stored in Hub DB and served before every agent's charter guidance; editable via Hub UI. `openspec/changes/single-runtime` removed the local-file mirror and its `agentweave init` placeholder — the Hub DB is now the only source.

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

### Requirement: Hub prepends instructions to charter content
The Hub SHALL prepend project instructions before charter content in every direct
`GET /api/v1/agents/context` response and before charter guidance in full agent context.

#### Scenario: Instructions exist — prepended to charter
- **WHEN** project instructions are non-empty and an agent requests direct or full charter context
- **THEN** project instructions appear before the charter content

#### Scenario: No instructions — charter returned unchanged
- **WHEN** project instructions are empty or no instruction row exists
- **THEN** direct charter lookup returns the charter content unchanged

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
