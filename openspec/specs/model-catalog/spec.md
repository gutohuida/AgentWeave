# model-catalog Specification

## Purpose
TBD - created by syncing change 2026-08-04-hub-model-control-and-provisioning. Update Purpose after archive.
## Requirements
### Requirement: The Hub declares a model catalog for every supported provider

The Hub SHALL maintain a catalog describing, for each provider it can spawn, the models available to
that provider and the runtime controls that provider accepts.

Each model entry SHALL carry the identifier passed to the provider's command line, a human-readable
label, any shorthand aliases the provider accepts, and the size of that model's context window where
it is known. A model whose context window is not known SHALL declare it as unknown rather than
declaring a substitute value.

A model entry MAY declare more than one selectable context window. Each declared window SHALL carry
the exact identifier that selects it, its own window size, and a label. A model that declares no
alternatives has exactly one window and offers no choice.

The identifier of a selected window SHALL be a model identifier in its own right, so that
requesting a window is expressed as requesting a model and nothing downstream of the choice
acquires a second concept to carry.

Resolving a context window from an identifier SHALL prefer a declared window over any partial match
against a base model's identifier. A selectable window's identifier commonly extends its base
model's, so a resolver that matched the base first would report the window the operator did not
choose.

The catalog SHALL cover exactly the providers the Hub can spawn. A provider the Hub cannot spawn
MUST NOT appear in the catalog.

#### Scenario: Every spawnable provider is described

- **WHEN** the catalog is read
- **THEN** it contains an entry for each provider the Hub can spawn
- **AND** contains no entry for a provider the Hub cannot spawn

#### Scenario: A model without a known window declares it unknown

- **WHEN** a model's context window is not known to the Hub
- **THEN** the catalog declares that window as unknown
- **AND** does not substitute a default value in its place

#### Scenario: A model offering two windows declares both

- **WHEN** a provider offers the same model at two context window sizes
- **THEN** the catalog declares both, each with the identifier that selects it and its own size

#### Scenario: A selected window resolves to its own size

- **WHEN** a context window is resolved for a selectable window's identifier
- **THEN** the size declared for that window is returned
- **AND** not the size declared for the model whose identifier it extends

#### Scenario: A model declaring one window offers no choice

- **WHEN** a model declares no alternative windows
- **THEN** no window choice is offered for it

### Requirement: Runtime controls are declared, not coded

Each provider entry SHALL declare its runtime controls. A control declaration SHALL carry its
identity, a human-readable label, its kind, its permitted values where the kind is enumerated, its
default where one exists, and how the control is applied to that provider's invocation.

The application specification SHALL express whether the control is applied as a command-line flag or
as a provider configuration override, together with the form it takes.

Adding a control to a provider MUST NOT require changes to command construction, to request
validation, or to the operator interface.

#### Scenario: A control declares its own application

- **WHEN** a control is declared for a provider
- **THEN** its declaration states whether it applies as a flag or as a configuration override
- **AND** states the form that application takes

#### Scenario: Adding a control requires only a catalog entry

- **WHEN** a further control is added to a provider's catalog entry
- **THEN** that control is accepted on a turn, validated, applied to the invocation, and offered to
  the operator, with no other change

### Requirement: Control values are per provider

Permitted values for a control SHALL be declared on that provider's control. Two providers offering
a control of the same identity MAY declare different permitted values.

A value permitted for one provider MUST NOT be accepted for another provider that does not permit
it.

#### Scenario: Providers declare different scales for the same control

- **WHEN** two providers each declare an effort control
- **THEN** each declares its own permitted values
- **AND** neither provider's values constrain the other's

#### Scenario: A value valid elsewhere is refused

- **WHEN** a turn requests a control value that its provider does not permit, but another provider
  does
- **THEN** the request is refused with a stated reason

### Requirement: The catalog is served to the operator interface

The Hub SHALL expose the catalog over its API so the operator interface can present models and
controls without embedding provider knowledge of its own.

The interface SHALL render controls from the catalog. It MUST NOT hardcode a provider's models,
control identities, or permitted values.

#### Scenario: The interface presents catalog-driven choices

- **WHEN** the operator is offered model or control choices
- **THEN** those choices are the ones the catalog declares for the relevant provider

#### Scenario: A catalog addition reaches the interface without a code change

- **WHEN** a model or control is added to the catalog
- **THEN** the operator interface offers it without any change to the interface

### Requirement: The Hub validates overrides before spawning

The Hub SHALL validate every requested runtime override against the catalog before constructing a
provider invocation. An override naming an unknown control, or carrying a value the provider does
not permit, SHALL be refused with a stated reason and the turn SHALL NOT start.

The Hub MUST NOT rely on the provider to reject an invalid value. A provider that accepts an
invalid value and silently proceeds at its default would otherwise run a turn under settings the
operator did not choose, without reporting it.

#### Scenario: An unknown control is refused

- **WHEN** a turn requests an override for a control the provider does not declare
- **THEN** the request is refused with a stated reason and no provider process starts

#### Scenario: An impermissible value is refused rather than passed through

- **WHEN** a turn requests a control value outside the provider's permitted values
- **THEN** the request is refused with a stated reason and no provider process starts
- **AND** the value is not passed to the provider

#### Scenario: Silent provider fallback cannot occur

- **WHEN** a provider would accept an invalid control value by warning and using its default
- **THEN** the Hub has already refused the request, so no turn runs under an unrequested setting

### Requirement: A requested context window is carried to the provider unaltered

The Hub SHALL accept a declared window's identifier wherever it accepts a model identifier, and
SHALL pass the identifier the operator selected to the provider unchanged.

Whether an account is entitled to a given window is not something the catalog can state. Entitlement
belongs to the subscription the provider authenticates, not to the model, and the same identifier
may be available to one operator and refused to another.

Where a provider refuses a selected window, the Hub SHALL report the provider's own refusal rather
than substituting a window the operator did not choose. This is the reason the refusal is left to
the provider at all: the requirement that the Hub validate before spawning exists so an invalid
value cannot be silently absorbed by a provider continuing at its default, and a provider that
refuses loudly and runs nothing has not absorbed anything.

#### Scenario: A selected window reaches the provider intact

- **WHEN** an operator selects a declared context window for a turn
- **THEN** the identifier that selects it is the one passed to the provider

#### Scenario: An unentitled window is reported, not substituted

- **WHEN** a provider refuses a selected context window because the account is not entitled to it
- **THEN** the refusal is reported
- **AND** the turn does not proceed on a different window
