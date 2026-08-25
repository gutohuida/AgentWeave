## MODIFIED Requirements

### Requirement: Structured payload safety
The Hub SHALL recursively redact known secret patterns before transport and SHALL NOT persist
complete raw provider events, opaque reasoning blobs, or encrypted reasoning fields.

Redaction SHALL be bounded so that it does not consume identifiers that are not secrets. In
particular it SHALL NOT redact the Hub's own vocabulary — the MCP tool names it publishes and the
document slugs it mints from titles agents choose. A rule that matches any sufficiently long
identifier removes precisely the identifier that tells the operator *which* document an agent read,
and it does so to catch credentials the recognized-prefix rules have already caught.

The serialized payload SHALL be at most 64 KiB, and a retained tool-result excerpt SHALL be at most
8 KiB. Truncated payloads SHALL preserve readable content and set `truncated=true`.

#### Scenario: Tool input contains a secret
- **WHEN** normalized structured input contains a recognized credential or secret
- **THEN** the secret SHALL be redacted before the event leaves the Hub's direct-execution path

#### Scenario: A long identifier that is not a secret
- **WHEN** a payload contains a published MCP tool name or a Hub-minted document slug of any length
- **THEN** it SHALL survive redaction intact

#### Scenario: A credential with no recognized prefix
- **WHEN** a payload contains a long high-entropy token with no separators
- **THEN** it SHALL be redacted

#### Scenario: Tool output exceeds its bound
- **WHEN** a tool result is larger than 8 KiB
- **THEN** the stored result excerpt SHALL be bounded, the summary SHALL remain readable, and `truncated` SHALL be true

#### Scenario: Provider emits opaque reasoning
- **WHEN** a provider event contains encrypted or otherwise opaque reasoning data
- **THEN** that field SHALL NOT be copied into content or payload
