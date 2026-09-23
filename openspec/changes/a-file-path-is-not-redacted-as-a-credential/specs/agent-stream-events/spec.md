## MODIFIED Requirements

### Requirement: Structured payload safety
The Hub SHALL recursively redact known secret patterns before transport and SHALL NOT persist
complete raw provider events, opaque reasoning blobs, or encrypted reasoning fields.

Redaction SHALL be bounded so that it does not consume identifiers that are not secrets. In
particular it SHALL NOT redact the Hub's own vocabulary — the MCP tool names it publishes and the
document slugs it mints from titles agents choose. A rule that matches any sufficiently long
identifier removes precisely the identifier that tells the operator *which* document an agent read,
and it does so to catch credentials the recognized-prefix rules have already caught.

Nor SHALL redaction consume a file path. A run of the high-entropy rule that is made of at least
three `/`-separated segments, each an ordinary lowercase, capitalised or camel-case word, is a path
and SHALL survive, except that any single segment of credential length SHALL still be redacted. A
path with `/` separators is the commonest thing a tool input names on a Linux host. The one most
reliably lost is the agent's own checkout, which is what an operator reading a transcript is most
often trying to establish.

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

#### Scenario: A deep POSIX file path
- **WHEN** a payload contains `/Users/operator/code/agentweave/hub/main.py` or a path under `.agentweave/worktrees/`
- **THEN** the path SHALL survive redaction intact

#### Scenario: A credential used as a path segment
- **WHEN** a payload contains a URL or path one of whose segments is a 32-character or longer hex or base64 value
- **THEN** that segment SHALL be redacted
- **AND** the segments around it SHALL survive

#### Scenario: A base64 credential that contains a slash
- **WHEN** a payload contains a base64 value with `/` in it whose segments are not all ordinary words, such as `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`
- **THEN** the whole value SHALL be redacted

#### Scenario: Tool output exceeds its bound
- **WHEN** a tool result is larger than 8 KiB
- **THEN** the stored result excerpt SHALL be bounded, the summary SHALL remain readable, and `truncated` SHALL be true

#### Scenario: Provider emits opaque reasoning
- **WHEN** a provider event contains encrypted or otherwise opaque reasoning data
- **THEN** that field SHALL NOT be copied into content or payload
