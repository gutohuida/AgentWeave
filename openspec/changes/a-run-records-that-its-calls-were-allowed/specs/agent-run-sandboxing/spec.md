## ADDED Requirements

### Requirement: A run records how many of its calls were allowed and refused

The Hub SHALL record, for each run whose calls reach a permission decision the Hub observes, how many of those decisions allowed the call and how many refused it, and SHALL NOT record an event for each allowed call.

Without this, a run that asked and was always allowed leaves exactly the same record as a run that
never asked, and a claim that an agent was silently refused can be neither confirmed nor refuted from
anything stored. The count answers that question without burying refusals among allowed calls.

A run for which no decision reached the Hub SHALL be distinguishable from a run whose decisions were
all allowed. The record SHALL survive the Hub stopping during the run at least to the extent of
whether any call was allowed and whether any was refused.

Recording the count SHALL NOT alter or delay the decision it counts. The decision's answer SHALL NOT
wait on a durable write of the count.

A count once recorded SHALL NOT be lowered by a later, less complete write for the same run.

#### Scenario: A run whose calls were all allowed says so

- **WHEN** a run's calls reach the permission decision several times and every one is allowed
- **THEN** the run's record states how many were allowed and that none was refused

#### Scenario: A run that never reached a decision is not reported as allowed

- **WHEN** a run ends without any of its calls reaching a permission decision the Hub observes
- **THEN** the run's record states that no decision was observed, not that none was refused

#### Scenario: Allowed calls add no events

- **WHEN** a run's call is allowed
- **THEN** no event is recorded for that call

#### Scenario: A Hub that stops mid-run keeps that a call was allowed

- **WHEN** the Hub stops during a run after at least one of its calls was allowed
- **THEN** the run's record still states that at least one call was allowed

#### Scenario: The decision's answer does not wait for the count

- **WHEN** a run reports the first allowed decision it received
- **THEN** the report is answered without waiting for the count to be written
- **AND** the count is written afterwards

#### Scenario: A late partial count does not lower the final one

- **WHEN** a run's exact count has been recorded at its end
- **AND** a write carrying an earlier, smaller count for the same run arrives afterwards
- **THEN** the run's record still states the exact count

#### Scenario: Failing to count changes nothing

- **WHEN** a decision cannot be counted
- **THEN** the decision is unchanged
- **AND** the run continues
