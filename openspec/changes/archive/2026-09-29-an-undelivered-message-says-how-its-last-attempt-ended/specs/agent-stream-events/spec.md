## MODIFIED Requirements

### Requirement: A run's terminal status line is persisted
The Hub SHALL persist a run's terminal status line as durable output, not only broadcast it, where the write can be made, and where it cannot, SHALL log the failure naming the run and SHALL leave the run's own recorded outcome and exit code as the record of how it ended.

This is bounded to the runs whose end the Hub observes — the two spawn paths' finalize blocks. A run
reconciled as `interrupted` after a Hub restart has no terminal status line and is not required to
gain one: there was no Hub process to write it. Such a run's outcome is carried by the run facts
map, under *A run's terminal outcome is visible*.

The status line is the fast signal a conversation settles on as the run ends. It is not the only
record: the run's row carries its outcome and exit code, and the conversation reads them from the
run facts it is served. So a status line that could not be written costs the conversation the
moment the fast signal would have given, and not the fact. A failure to write it SHALL NOT relabel a
run that has already ended, and SHALL NOT go unrecorded.

#### Scenario: The status line survives a reload

- **WHEN** a run ends and its output is fetched after the broadcast has been missed or the page
  reloaded
- **THEN** the run's output contains its terminal status row carrying the exit code

#### Scenario: Both spawn paths persist it

- **WHEN** a run ends on either the process path or the app-server path
- **THEN** the terminal status row is persisted in both cases

#### Scenario: It does not depend on the runner announcing its own completion

- **WHEN** a run ends on a runner whose output stream carries no completion sentinel of its own
- **THEN** the terminal status row is persisted for that run exactly as it is for a runner whose
  stream does carry one

#### Scenario: A status line that cannot be written leaves the outcome intact

- **WHEN** a run ends and writing its terminal status line fails
- **THEN** the failure is logged naming the run
- **AND** the run's recorded outcome is unchanged
- **AND** the conversation's run facts still carry that outcome and the exit code

## ADDED Requirements

### Requirement: A run's facts SHALL carry the error its row recorded

The run facts a conversation or an agent timeline is served SHALL include the error the run's own
row recorded, where it recorded one, and SHALL carry nothing in its place where it recorded none.

A run that failed before its process started writes no output at all, so the reason it failed is on
its row and in a broadcast event, and nowhere a conversation reads. The facts are the one place the
conversation reads a run's outcome from.

#### Scenario: A run that failed to start carries its error

- **WHEN** a run failed before its process spawned, and a conversation's entries name it
- **THEN** that run's facts in the conversation's response include the error its row recorded

#### Scenario: A run with no error carries none

- **WHEN** a run completed
- **THEN** its facts carry no error
