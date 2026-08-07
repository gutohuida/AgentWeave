## ADDED Requirements

### Requirement: A posture exists in which the workspace boundary is enforced per tool call

The Hub SHALL offer a permission posture under which each of a run's tool calls is decided against
the run's own workspace, rather than permitted in advance.

Under that posture a tool call confined to the run's workspace is allowed, and one reaching outside
it is refused with a reason stating what was refused and why. The comparison SHALL be made on fully
resolved paths, so that a relative traversal or a symbolic link cannot escape a boundary that an
unresolved comparison would have accepted.

The boundary enforced SHALL be the same one the agent is told it is working in. A boundary that is
described in one place and enforced from another can disagree, and the agent is given no way to tell
which is real.

Where the boundary cannot be established, the posture SHALL refuse rather than permit. An
unknown boundary is not an absent one.

#### Scenario: Work inside the workspace proceeds

- **WHEN** a run under this posture acts on a path inside its own workspace
- **THEN** the action is allowed

#### Scenario: Work outside the workspace is refused with a reason

- **WHEN** a run under this posture acts on a path outside its own workspace
- **THEN** the action is refused
- **AND** the refusal states what was refused and why

#### Scenario: Traversal and links cannot escape

- **WHEN** a path reaches outside the workspace only after relative traversal or link resolution
- **THEN** it is refused

#### Scenario: An unestablished boundary refuses

- **WHEN** the run's workspace cannot be determined
- **THEN** actions under this posture are refused

#### Scenario: Collaboration is not a filesystem decision

- **WHEN** a run under this posture uses the Hub's own tools
- **THEN** those calls are allowed

---

### Requirement: Every permission decision is answered, and answering never depends on the Hub

The Hub SHALL answer every permission request a run raises, including requests whose shape it does
not recognise, for which the answer is refusal.

A decision SHALL be reached without requiring a response from any other process. An unanswered
request does not fail a run, it suspends it indefinitely, so a decision path that can time out, be
refused a connection, or wait on a restart is a decision path that can hang a turn forever.

#### Scenario: An unrecognised request is answered

- **WHEN** a permission request is raised whose shape is not recognised
- **THEN** it is refused rather than left unanswered

#### Scenario: Decisions survive an unavailable Hub

- **WHEN** the Hub cannot be reached while a run is deciding a permission request
- **THEN** the request is still answered

---

### Requirement: A refused action is visible to the operator

Where a run's action is refused by the enforced boundary, the Hub SHALL make that refusal visible to
the operator.

An agent that is silently refused appears merely to have chosen differently. The operator is the only
participant who can widen a boundary or redirect the work, and cannot do either without knowing a
refusal happened.

Reporting a refusal MUST NOT alter or delay the decision it reports. Visibility is an observation of
a decision already reached, never a precondition of reaching it.

#### Scenario: A refusal reaches the operator

- **WHEN** an action is refused under the enforced boundary
- **THEN** the operator can see that the refusal happened

#### Scenario: Failed reporting changes nothing

- **WHEN** a refusal cannot be reported
- **THEN** the decision is unchanged
- **AND** the run continues

---

### Requirement: Introducing an enforced posture does not change existing runs

The default posture SHALL NOT change as a consequence of an enforced posture becoming available, and
runs that do not select it SHALL be spawned exactly as before.

A posture that decides each tool call is new machinery on the path of every action. Adopting it is a
deliberate choice, made per conversation, not a change imposed on every existing agent's next run.

Flags that serve the enforced posture SHALL be emitted only for that posture, and only where the
mechanism answering them is present.

#### Scenario: The default is unchanged

- **WHEN** a non-yolo run is spawned with no posture selected
- **THEN** it uses the same default posture as before the enforced posture existed

#### Scenario: Other postures carry no enforcement machinery

- **WHEN** a run selects a posture other than the enforced one
- **THEN** its command carries nothing referring to the enforcement mechanism

#### Scenario: No enforcement is claimed without an answerer

- **WHEN** the enforced posture is selected but no mechanism is present to answer its requests
- **THEN** the command does not claim enforcement it cannot perform
