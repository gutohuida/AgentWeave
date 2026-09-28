## ADDED Requirements

### Requirement: A declared alias is accepted wherever a model is, and kept as written

The Hub SHALL accept an alias the catalog declares for a provider everywhere it accepts that provider's model identifiers, and SHALL record and pass on the alias as written rather than the identifier it currently stands for.

An alias is the provider's own way of naming its latest model of a family. Recording the identifier
it stood for on the day it was chosen would freeze the choice that the alias exists to keep current.
A choice of an identifier and a choice of an alias are different choices, and the Hub SHALL keep
them distinct.

A value that is neither a declared identifier nor a declared alias SHALL still be refused, and the
refusal SHALL name the declared identifiers and aliases that would be accepted.

#### Scenario: An alias is accepted on a runner and kept

- **WHEN** a runner is created or edited with a model that is an alias its provider declares
- **THEN** the request is accepted
- **AND** the runner records the alias, not the identifier it stands for

#### Scenario: An alias reaches the provider as written

- **WHEN** a run is started on a runner that records an alias
- **THEN** the provider is invoked with the alias as its model

#### Scenario: An alias is accepted as a per-run override and by a worker

- **WHEN** a turn's model override, or a worker's model, is an alias its provider declares
- **THEN** it is accepted as the model identifier would be

#### Scenario: An alias is not unrecognised

- **WHEN** a runner records an alias its provider declares
- **THEN** the runner is not marked as having an unrecognised model

#### Scenario: An undeclared value is refused naming aliases too

- **WHEN** a model is submitted that is neither a declared identifier nor a declared alias
- **THEN** the request is refused
- **AND** the refusal names the declared identifiers and aliases
