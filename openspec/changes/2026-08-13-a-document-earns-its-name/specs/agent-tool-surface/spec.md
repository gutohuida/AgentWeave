# agent-tool-surface

## ADDED Requirements

### Requirement: The agent can name the document it is exploring

The agent's tool surface SHALL include a tool that renames the open specification document from a
subject in prose, and that tool SHALL appear in the described surface the agent is given.

An agent conducting an exploration learns what the document is about before anyone else does, and
until now had no way to say so: it minted a real title inside the payload while the document's path
went on naming the operator's opening sentence. The tool closes the gap between the moment the
subject becomes known and the moment the document reflects it.

The tool SHALL take the document's current path and a subject, and SHALL NOT take a path to rename
to. It SHALL return the new path, so that an agent renaming and then writing in the same turn
addresses the document it just moved rather than the one it no longer has.

The described tool surface SHALL list this tool, and the surface described SHALL remain equal to the
surface the server serves when spawned as a subprocess — the condition that already fails the build
when it is broken.

#### Scenario: The tool is served

- **WHEN** the specification server is spawned as the Hub spawns it and its tools are listed
- **THEN** the rename tool is among them

#### Scenario: The tool is described

- **WHEN** an agent's canonical context is assembled
- **THEN** the described tool surface names the rename tool and what it takes

#### Scenario: The new path is returned

- **WHEN** an agent renames a document
- **THEN** the result states the document's new path

#### Scenario: The agent cannot choose a location

- **WHEN** the rename tool's schema is inspected
- **THEN** it accepts a subject and not a destination path
