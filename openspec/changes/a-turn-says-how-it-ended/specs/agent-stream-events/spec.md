## ADDED Requirements

### Requirement: A run's terminal outcome is visible
The conversation SHALL show, for every run that ended, whether it completed, failed, was stopped or was interrupted, and SHALL show it again after a page reload.

A run whose row genuinely cannot be found is the only case that may present no outcome. That is
distinct from a run whose row exists but was omitted from the response, which is a defect and is
forbidden by *The run facts cover every run the events name*.

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

#### Scenario: A turn that produced nothing still reports what it cost

- **WHEN** a run ended without producing any visible agent output, so the only output row its turn
  carries is a terminal status row the conversation does not draw
- **THEN** the turn still presents its duration and token line, rather than losing it along with the
  row it was attached to

### Requirement: The timeline carries each run's own facts
The timeline response SHALL carry each run's recorded facts — status, exit code, start time and end time — read from the run's own row, and clients SHALL NOT reconstruct them from event names or event timestamps.

The response is an envelope of the events and a map of run facts keyed by `run_id`. The map is keyed
rather than listed because every consumer of it is a lookup or an unordered scan; a list would
require the client to build the index and would reintroduce the derivation this requirement removes.

The run facts are read by primary key, using the run ids the returned events name, after those
events have been merged and truncated. The map therefore describes exactly the runs the response
talks about: it is not scoped by project and agent, and it carries no bound that could be chosen
too small.

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

#### Scenario: The map is scoped to the events

- **WHEN** the agent has runs whose events fall entirely outside the returned event window
- **THEN** the map contains no entries for them

### Requirement: The run facts cover every run the events name
Every run named by a returned event SHALL be present in the run facts map, and the map SHALL be obtained by looking those runs up by id rather than by any query whose coverage depends on an ordering or a limit.

Coverage is the property; a bound is not a way to get it. A limit decides how many rows return, not
which, and no ordering available on the run row tracks the recency of the events that name it.
`run_reconciliation` sweeps every still-`running` row at Hub start and writes its lifecycle event
then, so an agent's newest events routinely name its oldest runs. A query ranked by start time and
capped at any number can miss exactly those.

Omitting a run the events name presents that turn as having no outcome — which is the defect this
change exists to remove, reintroduced by the fix for it, and blessed by *An unknown run degrades
rather than fails*. That is why the requirement is on the construction of the query and not on the
size of its result.

#### Scenario: An old run named by a recent event keeps its outcome

- **WHEN** a returned event names a run that started long before the agent's most recent runs,
  because the run's lifecycle event was written at Hub restart rather than when the run began
- **THEN** that run's facts are present in the map and its turn presents its terminal outcome

#### Scenario: Coverage does not depend on how many runs the window names

- **WHEN** the returned events name any number of distinct runs, up to the number of events returned
- **THEN** every one of those runs is present in the map

### Requirement: A run's terminal status line is persisted
The Hub SHALL persist a run's terminal status line as durable output, not only broadcast it, so the exit code remains recoverable after the live stream is gone.

This is bounded to the runs whose end the Hub observes — the two spawn paths' finalize blocks. A run
reconciled as `interrupted` after a Hub restart has no terminal status line and is not required to
gain one: there was no Hub process to write it. Such a run's outcome is carried by the run facts
map, under *A run's terminal outcome is visible*.

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
