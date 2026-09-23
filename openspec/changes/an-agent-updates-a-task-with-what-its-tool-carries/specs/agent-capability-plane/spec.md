## ADDED Requirements

### Requirement: An agent writes to a task only the fields its tool carries

An agent's update of a task SHALL accept the task's status, its notes and the requirements it serves, and SHALL refuse, before changing anything, any other field an operator may set, whichever access path the agent uses.

Who holds a task, its priority and its description are the operator's statements about the work.
An agent able to set the holder could take another agent's work, or name itself on finished work in
the same request that sends it to review. The tool an agent is given has never offered these fields,
and a direct request that could write them was a capability the adapter did not have.

The refusal SHALL name the fields it refused and say that an agent moves its task with status and
notes. The question tool and the message tool are unaffected.

#### Scenario: An agent tries to take a task

- **WHEN** an agent's run updates a task naming a new holder, over either access path
- **THEN** the update is refused and the task is unchanged, including any status the same request asked for
- **AND** the refusal names the holder field

#### Scenario: An agent links its task to a requirement

- **WHEN** an agent's run updates its task naming a requirement the project declares
- **THEN** the link is recorded as that agent's, over either access path

#### Scenario: The operator is unaffected

- **WHEN** the operator updates a task's holder, priority or description
- **THEN** the update is applied as before
