## ADDED Requirements

### Requirement: The operator shapes the corpus from the app

The operator's interface SHALL show whether the project's document index is usable and what its home is, SHALL let the operator rebuild the index, and SHALL let the operator set or clear a document's parent from that document's view.

The index is the only record of the corpus's home, hierarchy and ordering that travels with the
project, and placement is an operator-only judgement. A judgement that can only be expressed through a
direct HTTP call is not one the operator can make.

Where a rebuild cannot record an index because no home is recorded and the choice is ambiguous, the
interface SHALL ask the operator which document is home and SHALL rebuild with that answer. It SHALL
NOT choose a home on the operator's behalf. A rebuild SHALL be announced to every open view of the
project.

Where a placement is refused, the interface SHALL show the reason the Hub gave, and where the refusal
is that there is no usable index, SHALL offer the rebuild in place.

#### Scenario: A corpus with no index says so and offers a rebuild

- **WHEN** the operator opens the document browser for a project with no usable index
- **THEN** the browser says the index is not usable
- **AND** offers to rebuild it

#### Scenario: The home is asked for, not guessed

- **WHEN** the operator rebuilds the index of a corpus with several documents and no recorded home
- **THEN** the interface asks which document is home
- **AND** no index is written until the operator answers
- **AND** the rebuild that follows records the document the operator chose

#### Scenario: A document is placed from its own view

- **WHEN** the operator chooses a parent for the open document
- **THEN** the index records that parent
- **AND** the document's rendered navigation names it

#### Scenario: A refused placement shows why

- **WHEN** the operator chooses a parent that would create a cycle
- **THEN** the interface shows the Hub's reason
- **AND** the index is unchanged
