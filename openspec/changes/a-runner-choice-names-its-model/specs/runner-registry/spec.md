## ADDED Requirements

### Requirement: A runner offered for choosing names its model

Wherever the operator chooses a runner from a list, each choice SHALL name the model that choice will run, as the operator reads it, once, alongside the runner's name and provider.

Runners of one provider may share a name and differ only in their model, and the model is what the
choice decides. A choice that leaves the model out offers the operator identical options that have
different effects.

The model a choice will run is the runner's own model, except where a setting beside the list
overrides the model for that use, in which case it is the overriding model. A runner whose name
already ends with its model's label is not labelled with the model a second time.

The model SHALL be named by the catalog's label where the catalog declares it, as the provider's
default where the runner records no model, and by the recorded identifier, marked as unrecognised,
where the catalog does not declare it.

#### Scenario: Two runners with one name are told apart

- **WHEN** a project holds two runners of one provider with the same name and different models
- **AND** the operator opens any list offering a runner to choose
- **THEN** the two choices read differently
- **AND** each names its own model

#### Scenario: A runner named after its model names it once

- **WHEN** a runner's name already ends with the label of the model it runs, as the Hub names the
  runners it creates
- **THEN** its choice names that model once

#### Scenario: An overriding model is the one named

- **WHEN** the operator chooses the runner that writes checkpoints
- **AND** the project sets a checkpoint model
- **THEN** each choice names the checkpoint model, not the runner's own

#### Scenario: A runner with no model names the provider's default

- **WHEN** a runner records no model
- **THEN** its choice names the provider's default as its model

#### Scenario: An unrecognised model is named as such

- **WHEN** a runner records a model the catalog does not declare
- **THEN** its choice names that model and marks it as unrecognised
