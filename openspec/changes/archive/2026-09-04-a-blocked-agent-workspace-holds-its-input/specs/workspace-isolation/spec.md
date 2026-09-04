## ADDED Requirements

### Requirement: A refusal to provision names the workspace it is about and what would clear it

A refusal to provision a workspace SHALL identify which workspace could not be prepared — the
agent's own, or a named task's — and SHALL state what the operator would have to do to clear it.

Which workspace it is about is not a detail of the wording. It decides what is blocked: an agent's
own workspace carries every turn of that agent that is not about a task, and a task's checkout
carries one task's work. A refusal that names the agent for both sends the reader to the wrong
directory in one of the two cases, and leaves anything downstream deciding what is blocked to guess
from the sentence.

Stating the repair is required because the input is held. Where the system holds the operator's
input until they perform a repair, a refusal that names the obstruction but not the remedy asks them
to work it out from outside the product — and the wait continues until they do.

The remedy SHALL be stated per obstruction rather than as one sentence covering all of them. A
directory that is not the expected checkout, a link where a directory was expected, and a checkout
left mid-merge are cleared by different actions, and a single message covering all three sends the
operator looking for the wrong thing.

#### Scenario: The agent's own workspace is refused

- **WHEN** an agent's own workspace cannot be prepared
- **THEN** the refusal identifies it as that agent's workspace
- **AND** it states what would clear the obstruction it found

#### Scenario: A task's checkout is refused

- **WHEN** the checkout for a task cannot be prepared
- **THEN** the refusal names the task rather than the agent whose turn it was
- **AND** it states what would clear the obstruction it found

#### Scenario: Each obstruction states its own remedy

- **WHEN** provisioning is refused because a path exists that is not the expected registered checkout
- **THEN** the remedy stated is the one for that obstruction
- **AND** a different obstruction at the same path states a different remedy
