## ADDED Requirements

### Requirement: Project instructions file created on init
`agentweave init` SHALL create an empty `.agentweave/project_instructions.md` file as a placeholder when the file does not already exist.

#### Scenario: Init creates placeholder
- **WHEN** user runs `agentweave init` on a new project
- **THEN** `.agentweave/project_instructions.md` is created with an empty or placeholder comment body

#### Scenario: Init does not overwrite existing file
- **WHEN** user runs `agentweave init` and `.agentweave/project_instructions.md` already exists
- **THEN** the existing file is left unchanged

### Requirement: Hub stores project instructions per project
The Hub DB SHALL store project-wide instruction content in a `ProjectInstructions` table scoped by `project_id`.

#### Scenario: Empty instructions on new project
- **WHEN** a project has no instructions saved
- **THEN** `GET /api/v1/project/instructions` returns `{ "content": "" }`

#### Scenario: Save instructions via Hub API
- **WHEN** a PUT request is made to `/api/v1/project/instructions` with `{ "content": "..." }`
- **THEN** the content is persisted and subsequent GET returns the same content

### Requirement: Hub prepends instructions to role guide content
When HTTP transport is active, the Hub SHALL prepend project instructions before the role guide content in every `GET /api/v1/agents/context` response.

#### Scenario: Instructions exist — prepended to role guide
- **WHEN** project has non-empty instructions and agent calls `get_context`
- **THEN** response content is `[instructions]\n\n---\n\n[role guide]`

#### Scenario: No instructions — role guide returned unchanged
- **WHEN** project has no instructions (empty or no DB row)
- **THEN** response content is the role guide only, unchanged

#### Scenario: Hub wins over local file
- **WHEN** HTTP transport is active and both Hub DB and local file have content
- **THEN** Hub DB version is used; local file is not read

### Requirement: Local transport reads instructions file
When local transport is active, `aw-collab-start` SHALL read `.agentweave/project_instructions.md` before the role guide if the file exists and is non-empty.

#### Scenario: Instructions file present — read first
- **WHEN** local transport is active and `.agentweave/project_instructions.md` is non-empty
- **THEN** agent reads instructions content before reading the role guide

#### Scenario: Instructions file absent or empty — no change
- **WHEN** local transport is active and the file does not exist or is empty
- **THEN** agent proceeds with role guide only, no error

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
