## ADDED Requirements

### Requirement: A firing's record for an agent SHALL conclude when that agent's work on it concludes, not when one attempt ends

The Hub SHALL keep a firing's record for an agent open while the input that firing gave the agent is
still to be delivered, and SHALL conclude it with the outcome of the attempt or the act that settles
that input. An attempt that fails and hands its input back to be retried SHALL NOT conclude the
record, and neither SHALL a Hub restart that hands a crashed attempt's input back.

A firing hands an agent input, and the Hub may take several attempts to deliver it: a crash, a
runtime that dies, or a spawn that fails all return the input to the queue, and a later attempt on
the same conversation carries the work out. A record concluded by the first failed attempt reports
failure for work that completed, and nothing afterwards can correct it, because a concluded record
is not reopened. The job's history is the view the operator reads to learn whether a job's work
happened.

The record SHALL be concluded when none of that firing's input for the agent is still queued and no
attempt on it is running: by the attempt that ends it, whatever that attempt ends as; as failed, with
the reason, where the Hub gives up on the input; and as stopped where the operator withdraws it.
Input someone other than the firing added to the same conversation SHALL NOT hold the record open.

Where the Hub starts and finds such a record open, it SHALL leave it open if its input is queued or
any attempt on it is running, and SHALL conclude it as failed otherwise. Whether an attempt is
running SHALL be asked of every attempt on the conversation, not of one chosen without an order.

#### Scenario: A retry after a crash completes, and the history says so

- **GIVEN** a firing whose agent's run is interrupted by a Hub crash
- **WHEN** the Hub starts, hands the input back, and a new run on the same conversation completes it
- **THEN** the firing's record for that agent reads completed
- **AND** it did not read failed at any point after the restart

#### Scenario: A failed attempt that will be retried does not conclude the record

- **WHEN** an agent's run for a firing fails before or after it spawns, and its input goes back to
  the queue
- **THEN** the firing's record for that agent is still in progress
- **AND** when the retry completes, the record reads completed

#### Scenario: Input the Hub gives up on concludes the record as failed

- **WHEN** a firing's input for an agent reaches the delivery limit and the Hub stops retrying it
- **THEN** the firing's record for that agent reads failed
- **AND** it carries the reason the Hub gave up

#### Scenario: Input the operator withdraws concludes the record as stopped

- **WHEN** the operator withdraws a firing's input while it waits to be retried
- **THEN** the firing's record for that agent reads stopped

#### Scenario: The operator's own follow-up does not hold the record open

- **GIVEN** a firing's run for an agent completes
- **AND** the operator has queued a message of their own into the same conversation
- **THEN** the firing's record for that agent reads completed

#### Scenario: A running retry is not written off at startup

- **GIVEN** a conversation with an interrupted earlier attempt and a running later one
- **WHEN** the Hub reconciles open firing records
- **THEN** the firing's record is left in progress

#### Scenario: A firing with nothing left to deliver is still reconciled at startup

- **GIVEN** a firing record in progress whose conversation has no queued input from the firing and no
  running attempt
- **WHEN** the Hub starts
- **THEN** that record reads failed
