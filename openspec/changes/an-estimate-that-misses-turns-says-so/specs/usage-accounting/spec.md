## MODIFIED Requirements

### Requirement: Allowance and currency presentation cannot imply billing

When a runner reports remaining rate-limit allowance, the accounting presentation SHALL prefer it
to a monetary figure. Otherwise, any runner-reported monetary figure SHALL be labelled
"API-equivalent estimate" and MUST NOT be described as an amount charged. The system MUST NOT
invent a monetary figure from a model price catalog.

A monetary figure summed over turns SHALL state how many of those turns reported no cost and are
therefore not in it. A figure that leaves out any turn MUST NOT be presented as though it covered
them all.

#### Scenario: Allowance takes display precedence

- **WHEN** the latest accounting telemetry includes both rate-limit allowance and monetary data
- **THEN** the preferred display is the allowance

#### Scenario: Monetary telemetry is explicitly derived

- **WHEN** runner-reported monetary telemetry is displayed without allowance
- **THEN** it is labelled "API-equivalent estimate"
- **AND** it is not labelled spend, bill, or amount charged

#### Scenario: An estimate that leaves out turns says how many

- **WHEN** a project's turns include some that reported a cost and some that did not
- **THEN** the monetary figure is the sum of the reported costs
- **AND** the presentation states how many turns reported no cost and are not included

#### Scenario: A turn with no reported cost is not priced from its tokens

- **WHEN** a runner reports token usage for a turn but no cost
- **THEN** no monetary value is computed for that turn
- **AND** the turn is counted among those the monetary figure does not include
