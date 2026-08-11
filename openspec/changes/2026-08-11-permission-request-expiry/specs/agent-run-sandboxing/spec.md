## ADDED Requirements

### Requirement: A permission request does not outlive the wait it represents

A permission request SHALL reach a terminal status whenever the run that raised it stops waiting —
by answering, by timing out, by being stopped, or by ending for any other reason. It SHALL NOT
remain pending once nothing is waiting on it.

Reaching that terminal status SHALL NOT depend on the run successfully reporting it. A run that is
killed, crashes, or cannot reach the Hub still stops waiting, and the request SHALL still be closed.

Reporting that a wait has ended MUST NOT alter or delay the decision the run already reached. As with
reporting a refusal, this is an observation of something already true.

#### Scenario: A request whose wait timed out is closed

- **WHEN** a run's wait for an operator decision runs out
- **THEN** the request reaches a terminal status rather than remaining pending

#### Scenario: A request outliving its run is closed

- **WHEN** a run ends while a permission request it raised is still pending
- **THEN** that request reaches a terminal status

#### Scenario: A killed run's request is still closed

- **WHEN** a run is stopped or dies without reporting that its wait ended
- **THEN** its pending permission requests are still closed

#### Scenario: Closing twice is harmless

- **WHEN** a request's wait is reported as ended after the request has already been closed
- **THEN** the request is unchanged and no error is surfaced to the run

### Requirement: A decision is refused once nobody is waiting for it

The Hub SHALL refuse an operator decision on a permission request that is no longer pending, and
SHALL say that the run has moved on.

An accepted decision is a record that the operator authorised an action. Recording an approval for a
call that already proceeded without it — or was already refused — states an authority that was never
exercised, which is worse than refusing the decision outright.

#### Scenario: Deciding a closed request is refused

- **WHEN** an operator submits a decision for a request that has already reached a terminal status
- **THEN** the decision is refused and the operator is told the run has moved on

#### Scenario: A refused decision does not alter the record

- **WHEN** a decision on a closed request is refused
- **THEN** the request's status, decision time, and decider are unchanged

### Requirement: The operator can see that an agent stopped waiting

A permission request that ended without an operator decision SHALL remain visible to the operator and
SHALL be presented as expired, distinctly from one they answered.

The operator is the only participant who can widen the wait or be present for the next one, and
cannot do either without learning that an agent gave up. A request that disappears silently withholds
exactly that.

An expired request SHALL NOT be answerable.

#### Scenario: An expired request is shown as expired

- **WHEN** a permission request expires without an operator decision
- **THEN** it remains visible to the operator, marked as expired rather than removed

#### Scenario: An expired request offers no decision

- **WHEN** the operator views an expired permission request
- **THEN** it presents no way to allow or deny it

#### Scenario: An expired request is distinguishable from an answered one

- **WHEN** the operator views a permission request that expired and one they decided
- **THEN** the two are visibly different
