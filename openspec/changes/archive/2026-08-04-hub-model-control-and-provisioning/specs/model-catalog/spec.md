## ADDED Requirements

### Requirement: The Hub declares a model catalog for every supported provider

The Hub SHALL maintain a catalog describing, for each provider it can spawn, the models available to
that provider and the runtime controls that provider accepts.

Each model entry SHALL carry the identifier passed to the provider's command line, a human-readable
label, any shorthand aliases the provider accepts, and the size of that model's context window where
it is known. A model whose context window is not known SHALL declare it as unknown rather than
declaring a substitute value.

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
