## MODIFIED Requirements

### Requirement: Reading a checkpoint and recalling raw observations are separate permissions

The Hub SHALL treat permission to read a checkpoint and permission to recall raw observations as
independent grants, both closed by default.

A checkpoint is curated and bounded. A recorded observation is raw tool output that may contain file
contents, command output, or credentials from another agent's working directory. An agent that
benefits from understanding how work was done — including its dead ends — does not thereby need read
access to another agent's workspace.

Grants SHALL be held as structured configuration on the agent, and MUST NOT be expressed in a
charter. A charter is editable prose describing behaviour; allowing it to widen access would let an
edit to a paragraph change what an agent can read.

Authorisation SHALL be resolved from the identity bound to the running turn, and MUST NOT be
accepted from a request body or header.

The grant to read checkpoints SHALL reach every checkpoint in the project, from every conversation,
and the operator's control for it SHALL say so. A checkpoint does not restrict itself: no surface
could ever set such a restriction, and a control that described one told the operator the grant was
narrower than it is.

#### Scenario: A reader granted checkpoints is refused observations

- **WHEN** an agent permitted to read another agent's checkpoints requests a cited observation
- **AND** it holds no recall grant
- **THEN** the observation request is refused
- **AND** the checkpoint remains readable

#### Scenario: Access is closed without a grant

- **WHEN** an agent requests a checkpoint belonging to another agent with no grant
- **THEN** the request is refused

#### Scenario: Charter text cannot widen access

- **WHEN** a charter describes an agent as permitted to read other agents' work
- **THEN** that description does not grant access

#### Scenario: The grant reaches every conversation, and says so

- **GIVEN** an agent granted permission to read checkpoints
- **WHEN** another agent's checkpoint exists from a conversation the granted agent never took part in
- **THEN** the granted agent can read it
- **AND** the operator's control for the grant states that it reaches every conversation in the
  project
