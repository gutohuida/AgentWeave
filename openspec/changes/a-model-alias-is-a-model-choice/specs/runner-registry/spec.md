## ADDED Requirements

### Requirement: Runner management offers each declared alias as a choice of its own

Wherever the operator chooses a model for a provider, the interface SHALL offer each alias the catalog declares for that provider as a choice distinct from the identifiers, and SHALL label it as following the provider's latest model, naming the model the catalog currently records it as standing for.

Choosing an alias and choosing the identifier it currently stands for have the same effect today and
different effects after the provider moves the alias. The label SHALL make that difference readable.

#### Scenario: Aliases are offered beside identifiers

- **WHEN** the operator creates a runner or an agent and selects a provider that declares aliases
- **THEN** each declared alias is offered as its own choice
- **AND** its label says it follows the latest model and names the model it currently stands for

#### Scenario: A runner recording an alias opens with it selected

- **WHEN** the operator opens a runner that records an alias for editing
- **THEN** the alias is the selected choice
- **AND** the runner is not presented as having an unrecognised model
