## MODIFIED Requirements

### Requirement: A conversation's attention state is visible in navigation

Navigation SHALL show, for each listed conversation, whether it is running, waiting on the operator, or idle. A conversation is waiting on the operator when it holds a question that is unanswered and still being waited on, an undecided permission request, or an undismissed unasked-question flag.

The waiting state MUST be distinguishable from the running state, because a waiting run consumes
its configured timeout while the operator is unaware of it.

That reason is also this requirement's limit, and it is why the question clause now says *still being
waited on*. Once the configured timeout has been consumed and the run has gone back to work, nothing
is being held open and the operator is no longer unaware of anything — the state would persist for
the rest of the run, outranking the running state it is presented against, about a conversation that
is running and waiting for nothing. The permission clause has always worked this way: a decision
request that expired stops raising the state, and only questions had no expired state to leave.

An answer arriving afterwards is still delivered, and the question is still the operator's to answer
if they want to. Not being waited on is not the same as being closed.

#### Scenario: A blocked conversation is visible without opening it

- **WHEN** a run in one conversation opens a question and blocks
- **AND** the operator is looking at a different conversation
- **THEN** navigation shows that conversation as waiting on the operator

#### Scenario: Running and waiting are distinguishable

- **WHEN** one conversation is running and another is waiting on the operator
- **THEN** navigation presents the two states differently

#### Scenario: The state clears when the operator answers

- **WHEN** the operator answers the outstanding question
- **THEN** navigation no longer shows that conversation as waiting

#### Scenario: The state clears when the run stops waiting

- **GIVEN** a conversation shown as waiting on the operator
- **WHEN** the run's wait for that question ends without an answer and the run carries on
- **THEN** navigation no longer shows that conversation as waiting on the operator

#### Scenario: A permission request raises the same state

- **WHEN** a run opens a permission request and blocks
- **THEN** navigation shows that conversation as waiting on the operator
