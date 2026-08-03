## MODIFIED Requirements

### Requirement: Hub prepends instructions to role guide content
The Hub SHALL prepend project instructions before the role guide content in every `GET /api/v1/agents/context` response.

#### Scenario: Instructions exist — prepended to role guide
- **WHEN** project has non-empty instructions and agent calls `get_context`
- **THEN** response content is `[instructions]\n\n---\n\n[role guide]`

#### Scenario: No instructions — role guide returned unchanged
- **WHEN** project has no instructions (empty or no DB row)
- **THEN** response content is the role guide only, unchanged

## REMOVED Requirements

### Requirement: Local transport reads instructions file

**Reason**: Local transport is deleted by single-runtime (`openspec/changes/single-runtime`). The
Hub DB is now the only place project instructions are stored or read from; there is no local
transport to have a competing source.

**Migration**: None. Existing `.agentweave/project_instructions.md` content, if any, is not
migrated automatically — an operator who wants it in the Hub pastes it into the Hub UI's
Instructions screen.

### Requirement: Project instructions file created on init

**Reason**: `agentweave init` is removed by single-runtime; there is no longer a placeholder-file
creation step in the CLI. Instructions live exclusively in the Hub DB (`ProjectInstructions` table),
authored through the Hub UI.

**Migration**: None. A project registered under the app-lifecycle capability's bare-invocation
entry point starts with empty instructions, editable immediately in the Hub UI.
