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

A stop the operator makes, whether stated directly or by archiving the loop's job, SHALL be recorded against the loop as an event carrying its reason, the loop, the job, the actor and the time, in the same operation that ends the loop, and SHALL be announced to listening clients as a stop of that loop.

A loop the operator stops SHALL record that it stopped, never that it completed, whatever the text of the reason given. A stop requested for a loop that has already ended SHALL be refused, with a statement naming how and when that loop ended, and SHALL leave the loop's recorded ending, reason and time exactly as they were; no caller SHALL change how, why or when a loop ended once that has been recorded. Archiving a loop, directly or with its job, and each change of its control SHALL likewise be recorded against the loop in the same operation as the change, so that a change is never recorded without its event or its event without the change.

#### Scenario: The operator's stop appears in the loop's own history

- **GIVEN** a loop that has not ended
- **WHEN** the operator stops it with a reason
- **THEN** the loop's history contains one stop event naming that reason and that loop

#### Scenario: A stop that cannot be recorded does not happen

- **WHEN** recording the operator's stop fails
- **THEN** the loop is not recorded as ended and its job is unchanged

#### Scenario: A stop sent for a loop that has already ended is refused and changes nothing

- **GIVEN** a loop that has already ended, with a recorded ending, reason and time
- **WHEN** a caller asks to stop it, giving a new reason
- **THEN** the request is refused as a conflict, stating that the loop already ended and naming its recorded reason
- **AND** the loop's recorded ending, reason and time are unchanged
- **AND** no further stop event is recorded against the loop

#### Scenario: The loop's view shows the real ending after a refused stop

- **GIVEN** a loop's view that still offers stopping, for a loop that has meanwhile ended
- **WHEN** the operator stops it from that view and the Hub refuses
- **THEN** the view shows the refusal's text
- **AND** the view then shows how the loop actually ended and no longer offers stopping

#### Scenario: Archiving the job of a loop that has already ended still succeeds

- **GIVEN** a loop that has already ended and whose job is not archived
- **WHEN** the operator archives the loop's job
- **THEN** the job and the loop are archived
- **AND** the loop's recorded ending, reason and time are unchanged

#### Scenario: An operator's stop is a stop whatever its reason says

- **GIVEN** a loop that has not ended
- **WHEN** the operator stops it giving the reason "loop queue is empty"
- **THEN** the loop records that it stopped, not that it completed

#### Scenario: Archiving a running loop's job is recorded in the loop's history

- **GIVEN** a loop that has not ended
- **WHEN** the operator archives the loop's job
- **THEN** the loop's history contains a stop event naming that it was archived with its job
- **AND** an event recording that the loop was archived

#### Scenario: A change of control that cannot be recorded does not happen

- **WHEN** recording a change of a loop's control fails
- **THEN** the loop's controller is unchanged
