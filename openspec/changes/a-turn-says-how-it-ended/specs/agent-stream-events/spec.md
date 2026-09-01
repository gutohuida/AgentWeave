## ADDED Requirements

### Requirement: A run's terminal outcome is visible
The conversation SHALL show, for every run that ended, whether it completed, failed, was stopped or was interrupted, and SHALL show it again after a page reload.

A run whose row cannot be found is the only case that may present no outcome, and that case is
already reported by the Hub rather than swallowed.

#### Scenario: A stopped run says it was stopped

- **WHEN** the operator stops a turn and the run's status becomes `stopped`
- **THEN** the turn presents a terminal label naming the stop, rather than ending with no statement

#### Scenario: The outcome survives a reload

- **WHEN** a conversation containing a stopped, failed or interrupted run is loaded fresh, with no
  live stream having delivered anything
- **THEN** that run's terminal label is presented from persisted state alone

#### Scenario: A failed run is distinguishable from a silent one

- **WHEN** one run ended `failed` and another ended `completed` having produced no assistant text
- **THEN** the two turns present different terminal states rather than both presenting none

#### Scenario: A run still executing claims no outcome

- **WHEN** a run's status is `running`
- **THEN** no terminal label is presented for it

### Requirement: The timeline carries each run's own facts
The timeline response SHALL carry each run's recorded facts — status, exit code, start time and end time — read from the run's own row, and clients SHALL NOT reconstruct them from event names or event timestamps.

The response is an envelope of the events and a map of run facts keyed by `run_id`. The map is keyed
rather than listed because every consumer of it is a lookup or an unordered scan; a list would
require the client to build the index and would reintroduce the derivation this requirement removes.

The run query runs concurrently with the event queries and is therefore scoped by project and agent
rather than by the run ids the returned events happen to mention. The map MAY therefore describe
runs no returned event names. Narrowing it would serialise the concurrent queries.

#### Scenario: The response carries both halves

- **WHEN** a client requests an agent's timeline
- **THEN** the response contains the events and a map of run facts keyed by `run_id`

#### Scenario: The facts come from the run, not from the events

- **WHEN** a run's lifecycle events and its recorded status disagree, because the status was
  corrected after the events were written
- **THEN** the response reports the recorded status

#### Scenario: An unknown run degrades rather than fails

- **WHEN** a returned event names a `run_id` that has no row
- **THEN** the map omits that key and the client presents that run exactly as it presents a run with
  no outcome yet

#### Scenario: The map may exceed the events

- **WHEN** the agent has runs whose events fall outside the returned event window
- **THEN** the map MAY contain entries for them and this is not an error

### Requirement: A run's terminal status line is persisted
The Hub SHALL persist a run's terminal status line as durable output, not only broadcast it, so the exit code remains recoverable after the live stream is gone.

#### Scenario: The status line survives a reload

- **WHEN** a run ends and its output is fetched after the broadcast has been missed or the page
  reloaded
- **THEN** the run's output contains its terminal status row carrying the exit code

#### Scenario: Both spawn paths persist it

- **WHEN** a run ends on either the process path or the app-server path
- **THEN** the terminal status row is persisted in both cases

### Requirement: Payload-shaped model functions are tested against real route ordering
A model function that consumes an API payload SHALL be tested against a fixture whose ordering is the ordering that route actually produces, and the test SHALL fail if the route's ordering is reversed.

A fixture that asserts correct behaviour on an ordering the route never emits is not evidence. This
requirement exists because such a test was green while the behaviour it covered could not fire.

#### Scenario: The fixture matches the route

- **WHEN** a model function consumes a payload from a route that returns rows in a defined order
- **THEN** its test fixture presents the rows in that same order

#### Scenario: The test is sensitive to ordering

- **WHEN** a payload-shaped model function is correct only for one ordering, and the fixture's
  ordering is reversed
- **THEN** at least one test fails

#### Scenario: An order-independent function proves it

- **WHEN** a model function is intended to be independent of its input's ordering
- **THEN** a test asserts the same result for a shuffled input
