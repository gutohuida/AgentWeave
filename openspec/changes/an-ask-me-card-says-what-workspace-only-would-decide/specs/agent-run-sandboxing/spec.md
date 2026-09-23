## ADDED Requirements

### Requirement: An operator asked to decide a call is shown what the workspace posture would decide

Under the posture in which the operator answers each tool call, the request the operator is shown SHALL carry the decision the posture that checks each call against the run's workspace would have reached for the same call, with its reason, and that decision SHALL be presented as advice and SHALL NOT answer the request.

The operator is the last participant who can stop the call, and decides in seconds under a
timeout. The Hub already computes, for the same run, the boundary this posture would enforce. A
request that withholds it asks for a judgement without its most important input, and makes the
posture in which a human decides the one in which the boundary is least visible.

The decision SHALL be reached by the same check that answers under the workspace posture for that
run's provider, so that the advice and the enforced answer cannot disagree. Where no such decision
was reached, the request SHALL say nothing about the boundary rather than guess.

An allowed decision for a shell command SHALL NOT be presented as a statement that the command stays
inside the workspace. A command's text can name values the shell decides when it runs, and the check
reads text.

Carrying the decision SHALL NOT make asking the operator fail. A Hub that does not accept it SHALL
still be asked.

#### Scenario: A call outside the workspace is marked on the request

- **WHEN** a run under the operator-answered posture asks to write a path outside its workspace
- **THEN** the request shown to the operator states that the workspace posture would refuse it
- **AND** states the reason
- **AND** the operator can still allow it

#### Scenario: A call inside the workspace is marked as allowed, without a containment claim

- **WHEN** a run under the operator-answered posture asks to run a shell command the workspace
  posture would allow
- **THEN** the request states that the workspace posture would allow it
- **AND** does not state that the command stays inside the workspace

#### Scenario: No decision, no claim

- **WHEN** a request was opened without a workspace decision
- **THEN** the request states nothing about the workspace boundary

#### Scenario: An older Hub is still asked

- **WHEN** the Hub refuses a request because it carries the workspace decision
- **THEN** the request is opened without it
- **AND** the operator is still asked
