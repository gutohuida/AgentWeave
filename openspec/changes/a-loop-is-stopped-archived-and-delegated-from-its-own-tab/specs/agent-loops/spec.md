## ADDED Requirements

### Requirement: A loop's own view offers the operator's actions on that loop

The application SHALL offer, in the view of a single loop, every action the operator alone may take on that loop: stopping it while it has not ended, archiving it once it has ended and is not archived, and delegating or taking back control of its queue while it has not ended. Each action SHALL be offered only in the states in which the Hub would accept it, and a refusal the Hub returns SHALL be shown with the Hub's own text.

The view SHALL state who currently decides additions to the loop's queue. Stopping SHALL NOT interrupt a firing already under way, and the view SHALL say so before the operator confirms.

#### Scenario: A running loop can be stopped from its own view

- **GIVEN** a loop that has not ended
- **WHEN** the operator stops it from the loop's view and confirms
- **THEN** the loop records that it stopped, with the operator's reason
- **AND** no further firing of it starts

#### Scenario: A stop does not interrupt the firing under way

- **GIVEN** a loop whose firing is in progress
- **WHEN** the operator opens the stop confirmation
- **THEN** the confirmation states that the running firing finishes and that none starts after it

#### Scenario: An ended loop offers archiving, not stopping

- **GIVEN** a loop that has completed or stopped and is not archived
- **WHEN** the operator opens the loop's view
- **THEN** archiving is offered and stopping is not
- **AND** archiving it removes it from the default loop listing and keeps it under the listing that includes archived loops

#### Scenario: Control is delegated and taken back from the loop's view

- **GIVEN** a loop that has not ended and whose queue additions the operator decides
- **WHEN** the operator delegates control from the loop's view
- **THEN** the view states that the loop's agent decides additions to its queue
- **AND** taking control back from the same view returns the decision to the operator

#### Scenario: A refusal is shown in the Hub's words

- **WHEN** the Hub refuses one of these actions
- **THEN** the loop's view shows the refusal's own text
- **AND** the view then shows the loop as the Hub records it

### Requirement: An operator's stop is recorded in the loop's history as a firing's stop is

A stop the operator makes SHALL be recorded against the loop as an event carrying its reason, the loop, the job, the actor and the time, in the same operation that ends the loop, and SHALL be announced to listening clients as a stop of that loop. An operation that changes the recorded reason of a loop that had already ended SHALL NOT record a second stop.

#### Scenario: The operator's stop appears in the loop's own history

- **GIVEN** a loop that has not ended
- **WHEN** the operator stops it with a reason
- **THEN** the loop's history contains one stop event naming that reason and that loop

#### Scenario: A stop that cannot be recorded does not happen

- **WHEN** recording the operator's stop fails
- **THEN** the loop is not recorded as ended and its job is unchanged

#### Scenario: Rewording an ended loop's reason is not a second stop

- **GIVEN** a loop that has already ended
- **WHEN** a caller supplies a new stop reason for it
- **THEN** no further stop event is recorded against the loop
