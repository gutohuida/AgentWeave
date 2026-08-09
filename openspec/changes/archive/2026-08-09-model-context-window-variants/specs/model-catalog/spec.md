## MODIFIED Requirements

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

## ADDED Requirements

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
