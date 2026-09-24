## ADDED Requirements

### Requirement: A provider that publishes its own catalog is described from it

Where the installed provider command line keeps a machine-readable catalog of the models it offers, the Hub SHALL take that provider's models from it at runtime, and SHALL use its own built-in list for that provider only when that catalog is absent, unreadable, or lists no model.

The provider's server sends each installed client version its own list, so no list built into the
Hub can be right for every installed client. The list the installed client wrote is the list that
client will accept.

The models taken SHALL be those the provider's catalog marks for listing, in the provider's own
order, each with the provider's label and context window. The first SHALL be the default. A change
to the provider's catalog SHALL be reflected without restarting the Hub.

The catalog the Hub serves SHALL state, for each provider, whether its models came from the
provider's catalog, with that catalog's fetch time and client version, or from the built-in list,
with the reason the provider's catalog was not used.

Reading the provider's catalog SHALL NOT fail any request. A catalog that cannot be read SHALL
produce the built-in list and a stated reason.

The provider's runtime controls SHALL remain as the Hub declares them.

Where a run used a model the provider's catalog does not list but the built-in list declares, the
Hub SHALL still read that model's context window from the built-in list. This applies to reading a
run's usage only; it SHALL NOT make such a model acceptable where a model is newly set.

#### Scenario: The installed client's list is offered

- **WHEN** the provider's catalog is readable and lists models
- **THEN** the Hub offers exactly the listed models, in the provider's order
- **AND** accepts a runner on any of them
- **AND** refuses a runner on a model only its built-in list declares

#### Scenario: No provider catalog falls back, and says so

- **WHEN** the provider's catalog is absent, unreadable, or lists no model
- **THEN** the Hub offers its built-in list for that provider
- **AND** states that the list is built in and why

#### Scenario: A refreshed provider catalog is picked up

- **WHEN** the provider's catalog file changes while the Hub is running
- **THEN** the next read of the catalog reflects the change

#### Scenario: A model the provider no longer lists keeps its window

- **WHEN** the provider's catalog is readable and does not list a model the built-in list declares
- **AND** a run reports usage on that model
- **THEN** the run's context window is the built-in list's window for it
- **AND** a runner newly set to that model is still refused

#### Scenario: A malformed provider catalog fails nothing

- **WHEN** the provider's catalog is not a valid catalog document
- **THEN** reading the Hub's catalog and creating a runner both succeed against the built-in list
