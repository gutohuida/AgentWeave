## ADDED Requirements

### Requirement: An event's `run_id` SHALL name a run and nothing else

Every event the Hub persists or broadcasts SHALL use the key `run_id` only for the id of a run, one
agent's attempt at a turn. An event that refers to a job's firing record SHALL carry that id as
`job_run_id`, and SHALL NOT carry it as `run_id`. A route that answers with a firing record's id
SHALL name it the same way.

A run id and a firing record id share a prefix, so a reader cannot tell them apart by the value. A
reader that collects `run_id` from a stream of events and looks each up as a run then looks up
something that is not a run, and an operator reading the activity log sees a firing name a run that
cannot be found.

Events persisted before this requirement are not rewritten.

#### Scenario: A job's firing names its record under its own key

- **WHEN** a job fires, is skipped, or fails to fire
- **THEN** the event carries the firing record's id as `job_run_id`
- **AND** the event carries no `run_id`

#### Scenario: Pressing Run answers with the record's key

- **WHEN** the operator fires a job through the route and the firing writes a record
- **THEN** the answer names that record as `job_run_id`
- **AND** the answer carries no `run_id`

#### Scenario: Every run_id in the stream is a run

- **WHEN** a job fires and its agent's run completes
- **THEN** every `run_id` in the events persisted for that firing names a run that exists
