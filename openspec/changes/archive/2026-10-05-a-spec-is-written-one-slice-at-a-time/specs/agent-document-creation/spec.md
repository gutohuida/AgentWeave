## MODIFIED Requirements

### Requirement: An agent may begin only a change specification

The creation operation SHALL produce a document of the change-specification kind or, when the agent asks for it, of the roadmap kind, SHALL default to the change-specification kind, and SHALL NOT offer any other.

Two reasons, and the first is a trap rather than a preference. A capability document is created
directly in the current phase, and a separate standing rule refuses every capability submission from
an agent — so an agent permitted to choose that kind would create a document that succeeds and can
then never be filled in. Creation that looks like success and produces an unusable artefact is worse
than a refusal.

The second reason is that the remaining kinds describe what a project *is* and how its corpus is
arranged, rather than contributing to it. A change specification is the one kind whose whole
lifecycle is designed to be authored by an agent and gated by the operator at each transition. A
roadmap is the same kind of thing at a larger scale: the plan whose slices are change
specifications, with the same operator-gated lifecycle. An agent told to write a large request as a
roadmap plus a slice must be able to create both.

A refusal SHALL name what may be created, not only what may not.

#### Scenario: A capability document cannot be created by an agent

- **WHEN** an agent attempts to create a capability document
- **THEN** it is refused
- **AND** the refusal names the kinds an agent may create, change specification and roadmap

#### Scenario: The corpus is unreachable through creation

- **WHEN** an agent creates a document and submits a capability payload against it
- **THEN** the submission is refused because the document's kind is fixed at creation

#### Scenario: An agent creates a roadmap

- **WHEN** an agent creates a document asking for the roadmap kind
- **THEN** a roadmap is created in the exploring phase

#### Scenario: No kind given is a change specification

- **WHEN** an agent creates a document without naming a kind
- **THEN** a change specification is created
