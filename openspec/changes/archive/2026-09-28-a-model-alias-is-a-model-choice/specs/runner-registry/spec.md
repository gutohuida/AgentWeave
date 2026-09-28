## MODIFIED Requirements

### Requirement: A runner's model is drawn from the catalog

A runner's model SHALL be a model the catalog declares for that runner's provider, or an alias the catalog declares for that provider, or unset, and runner management SHALL offer that choice as a selection over the declared models and aliases rather than as free-typed text.

The Hub SHALL refuse a request that sets a runner's model to one its provider does not
declare, as a model or as an alias. A declared alias is recorded as written, not as the model it
currently stands for.

An unset model is a valid, spawnable state meaning the provider's own default, and runner management
SHALL offer it as a named choice alongside the declared models. Where a runner's model is asked to be
cleared, the Hub SHALL clear it, and SHALL NOT answer a request that left the model unchanged as
though it had changed it. A request that carries no model at all leaves the runner's model as it was;
these are different requests and the Hub SHALL distinguish them.

Where a runner already records a model the catalog does not declare, that model SHALL remain among
the offered choices, selected, and marked as unrecognised, so that opening the runner for editing
cannot silently re-point it at a different model. Runner management SHALL also mark such a runner
where runners are listed, so that which runners need attention is legible without opening each one.
A declared alias is not such a model.

A model the catalog does not declare is refused where it is newly *set*, and only there. Where a
request carries the model a runner already records, the Hub SHALL accept it, because that request
changes nothing about the runner's model and refusing it would make an existing runner uneditable
in every other respect as well.

#### Scenario: Runner management offers declared models

- **WHEN** the operator creates or edits a runner and selects its provider
- **THEN** the models offered are those the catalog declares for that provider, and its declared
  aliases
- **AND** no free-typed model field is presented

#### Scenario: A declared alias is accepted and recorded as written

- **WHEN** a runner is created or edited with an alias its provider declares
- **THEN** the request is accepted
- **AND** the runner records the alias, not the model it currently stands for
- **AND** the runner is not marked as unrecognised

#### Scenario: The provider's default is a choice, and clearing is honoured

- **WHEN** the operator sets a runner that has a model back to the provider's default
- **THEN** the runner records no model
- **AND** the answer carries the model as it now stands rather than the one the runner had
- **AND** runs it backs launch on the provider's own default model

#### Scenario: A request carrying no model at all leaves the model alone

- **WHEN** a request updates a runner and carries no model field
- **THEN** the runner's model is unchanged
- **AND** the request is answered differently from one that asked for the provider's default

#### Scenario: An undeclared model is refused

- **WHEN** a runner is submitted with a model its provider does not declare, as a model or as an
  alias
- **AND** the runner does not already record that model
- **THEN** the request is refused with a stated reason

#### Scenario: Existing runners keep working

- **WHEN** a runner already records a model the catalog does not declare
- **THEN** that runner remains readable and its agents remain listable
- **AND** the operator is told the model is unrecognised when editing it
- **AND** that runner is marked as unrecognised where runners are listed
- **AND** that model is still offered and still selected, so saving the runner unchanged keeps it

#### Scenario: A legacy runner can still be saved

- **WHEN** the operator opens a runner whose model the catalog does not declare, changes its name,
  and saves it with that model still selected
- **THEN** the save is accepted and the runner keeps its unrecognised model
- **AND** moving that runner to a *different* model the catalog does not declare is still refused

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
