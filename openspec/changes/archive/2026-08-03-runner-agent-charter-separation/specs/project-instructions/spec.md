## MODIFIED Requirements

### Requirement: Hub prepends instructions to charter content
The Hub SHALL prepend project instructions before charter content in every direct
`GET /api/v1/agents/context` response and before charter guidance in full agent context.

#### Scenario: Instructions exist — prepended to charter
- **WHEN** project instructions are non-empty and an agent requests direct or full charter context
- **THEN** project instructions appear before the charter content

#### Scenario: No instructions — charter returned unchanged
- **WHEN** project instructions are empty or no instruction row exists
- **THEN** direct charter lookup returns the charter content unchanged
