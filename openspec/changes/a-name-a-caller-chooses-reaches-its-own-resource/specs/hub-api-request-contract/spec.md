## ADDED Requirements

### Requirement: A name a caller chooses reaches its own resource

The Hub SHALL refuse a caller-chosen name for an agent or a task that its own API would route to a different resource, and SHALL say which route claims the name.

Where a route for a fixed word sits beside a route for a caller-chosen name at the same place in the
address, the fixed route answers for that word. A resource created under that word exists, is listed,
and can never be read at its own address: the operator's panel for it receives some other
resource's answer.

The set of refused words SHALL follow from the Hub's routes, and a route added beside a caller-chosen
name SHALL NOT be able to ship without its word being refused.

#### Scenario: An agent cannot be named after a route beside its own

- **WHEN** a caller creates an agent whose name is a fixed route word at the same place as an agent's
  own routes
- **THEN** the request is refused
- **AND** the refusal names the route that would answer for that name

#### Scenario: A task cannot be given an id that is a route

- **WHEN** a caller creates a task with an id that is a fixed route word at the same place as a
  task's own address
- **THEN** the request is refused, naming the id

#### Scenario: A new route beside a chosen name is caught

- **WHEN** a fixed route is added beside a route for a caller-chosen name
- **AND** its word is not refused as a name
- **THEN** verification fails, naming the route and the word
