## ADDED Requirements

### Requirement: A runner offered for choosing names its model

Wherever the operator chooses a runner from a list, each choice SHALL name the runner's model as the operator reads it, alongside the runner's name and provider.

Runners of one provider may share a name and differ only in their model, and the model is what the
choice decides. A choice that leaves the model out offers the operator identical options that have
different effects.

The model SHALL be named by the catalog's label where the catalog declares it, as the provider's
default where the runner records no model, and by the recorded identifier, marked as unrecognised,
where the catalog does not declare it.

#### Scenario: Two runners with one name are told apart

- **WHEN** a project holds two runners of one provider with the same name and different models
- **AND** the operator opens any list offering a runner to choose
- **THEN** the two choices read differently
- **AND** each names its own model

#### Scenario: A runner with no model names the provider's default

- **WHEN** a runner records no model
- **THEN** its choice names the provider's default as its model

#### Scenario: An unrecognised model is named as such

- **WHEN** a runner records a model the catalog does not declare
- **THEN** its choice names that model and marks it as unrecognised
