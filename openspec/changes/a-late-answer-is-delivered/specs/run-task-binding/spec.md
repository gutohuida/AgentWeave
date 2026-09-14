## MODIFIED Requirements

### Requirement: An answer reaches an asker whose run has ended

Where a blocking question is answered after the asking run has ended, or after that run's wait for it has ended, the system SHALL deliver the answer as queued input rather than relying on the asking run to receive it as a result.

A blocking ask holds its tool call open only for the length of its wait, and the run lives on past
the wait. A question that outlived its wait has nobody waiting to receive the answer. It may have
timed out, the run may have failed, or the run may still be working on without it. That is precisely
the question that caused a task to be recorded as waiting. An answer that reaches no one leaves the
operator believing they have unblocked work that is still stopped, and leaves the agent believing it
was never answered.

The wait has ended once the asking run has reported the wait expired without receiving that
question's resolution, or once the system has recorded the wait's end at the run's end. The expiry
report names only what the run did not receive. So where a question it names had already been
answered by the time the report arrived, the system SHALL treat that answer as never received, and
SHALL deliver it on the same terms as an answer given after the wait. A question declined by then
SHALL NOT be recorded as having gone ahead without an answer, since a decline is a decision handed
back, not silence. The same holds where the system itself records the wait's end at the run's end:
a question declined by the time that record is written SHALL NOT receive it.

The system SHALL decide whether to deliver only after it has recorded the answer or the wait's end,
and against recorded state. An answer and an expiry report that arrive together SHALL NOT both
decline to deliver. A duplicate costs the agent a turn; a lost answer costs the operator their
decision.

Where the system cannot establish that the asking run has ended, or that its wait has ended, it
SHALL assume the asker is still waiting.

The operator's view SHALL state that nobody is waiting for a question from the moment its wait has
ended, not only from the moment its run has ended.

#### Scenario: The answer is queued when the asker has ended

- **WHEN** a blocking question is answered after its asking run has ended
- **THEN** the answer is queued for the agent

#### Scenario: The answer is queued when the wait has ended and the run lives on

- **GIVEN** a blocking question whose asking run reported its wait expired without an answer
- **AND** that run is still running
- **WHEN** the operator answers the question
- **THEN** the answer is queued for the agent
- **AND** it is delivered as a new turn once the agent is free

#### Scenario: An answer given between the last check and the expiry report is delivered

- **GIVEN** a blocking question that the operator answered after the asking run last checked for
  it
- **WHEN** the asking run then reports that its wait expired without an answer to it
- **THEN** the report is accepted
- **AND** the answer is queued for the agent

#### Scenario: A batch reported together is delivered once

- **GIVEN** a batch of blocking questions, two of which were answered after the asking run last
  checked for them
- **WHEN** the asking run reports both as expired in one report and the batch is complete
- **THEN** exactly one delivery carrying the whole batch is queued

#### Scenario: An answer that lands while the expiry report is being recorded is delivered

- **GIVEN** a blocking question whose asking run's expiry report has read it unanswered
- **AND** the operator's answer is recorded before that report records the wait's end
- **WHEN** both have been recorded
- **THEN** the answer is queued for the agent

#### Scenario: A decline that lands while the expiry report is being recorded is not called an absence

- **GIVEN** a blocking question whose asking run's expiry report has read it unresolved
- **AND** the operator's decline is recorded before that report records the wait's end
- **WHEN** both have been recorded
- **THEN** the question does not record that its wait ended
- **AND** the task it was bound to does not say it proceeded without the operator's answer

#### Scenario: A decline that lands while the run's end is being recorded is not called an absence

- **GIVEN** a bound run that has ended, whose end check has read its blocking question unresolved
  with the wait expired
- **AND** the operator's decline is recorded before that check records the wait's end
- **WHEN** both have been recorded
- **THEN** the question does not record that its wait ended
- **AND** the task it was bound to does not say it proceeded without the operator's answer

#### Scenario: The answer is not duplicated for an asker still waiting

- **WHEN** a blocking question is answered while its asking run is still waiting for it
- **THEN** the answer is not also queued

#### Scenario: An answer returned in the tool's last check is not duplicated

- **GIVEN** a blocking question answered after the system's deadline for its wait but before the
  asking run's final check for it
- **WHEN** the asking run receives the answer as its result and reports nothing expired for it
- **THEN** the answer is not also queued

#### Scenario: The operator's view says nobody is waiting once the wait has ended

- **GIVEN** a blocking question whose asking run reported its wait expired
- **AND** that run is still running
- **WHEN** the operator's view lists the question, and when it shows that question alone
- **THEN** both state that nobody is waiting for it
