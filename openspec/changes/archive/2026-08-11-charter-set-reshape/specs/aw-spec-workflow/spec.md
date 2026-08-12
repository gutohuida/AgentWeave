## MODIFIED Requirements

### Requirement: The spec role routes instead of duplicating procedures

The packaged spec charter SHALL contain identity, ownership boundaries, and the judgment that makes
a specification useful — that requirements are measurable assertions, that a spec captures WHAT and
WHY rather than HOW, that work is sliced vertically by capability, and that ambiguity is resolved
with the operator rather than guessed.

The charter SHALL route only to mechanisms the project actually has. It MUST NOT name a skill,
command, or support document that is not installed into the project it is running in. Where the
authoring procedure lives in a mechanism the project does not currently ship, the charter SHALL carry
the judgment directly and stay silent about the procedure, rather than directing the agent to
something absent.

The charter MUST NOT describe the approval gate as its holder's to enforce. Whether work may proceed
from a proposal to an implementation is decided by the task transition service, and the agent is
subject to that decision rather than the administrator of it.

The charter MUST NOT assert discovery, indexing, or manifest behavior that the Hub does not itself
perform.

#### Scenario: The charter names no uninstalled skill

- **WHEN** the packaged spec charter is examined
- **THEN** it names no skill or support document that a fresh project does not contain

#### Scenario: Judgment survives the absence of the procedure

- **WHEN** an agent receives the spec charter in a project with no authoring skills installed
- **THEN** it is still told what makes a requirement testable, what belongs in a spec, and when to
  ask the operator

#### Scenario: The approval gate is not restated as the agent's duty

- **WHEN** the packaged spec charter is examined for approval rules
- **THEN** it does not instruct the agent to withhold implementation pending a status it sets itself

#### Scenario: The charter claims no discovery the Hub does not perform

- **WHEN** the packaged spec charter describes how specification documents become visible
- **THEN** it asserts no automatic discovery or manifest reconciliation on the Hub's part
