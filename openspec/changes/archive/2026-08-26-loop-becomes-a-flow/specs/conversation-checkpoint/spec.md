## ADDED Requirements

### Requirement: A flow's checkpoint lineage is shared across the agents it fires

The Hub SHALL keep one checkpoint lineage per flow rather than one per agent, so that a checkpoint
recorded by one agent is inherited by the next firing whichever agent that firing starts.

Each checkpoint SHALL record the agent that wrote it, and a reader SHALL be able to tell which agent
wrote any checkpoint in a flow's lineage.

An agent writing a checkpoint in a flow SHALL be told that another agent may read it, so that what it
records is addressed to whoever continues the work rather than to itself.

#### Scenario: A checkpoint crosses from one agent to another

- **WHEN** a flow fires agent A, which records a checkpoint, and a later firing starts agent B
- **THEN** B's briefing includes A's checkpoint content

#### Scenario: A checkpoint's author is identifiable

- **WHEN** a flow's checkpoint lineage contains checkpoints written by more than one agent
- **THEN** each checkpoint identifies the agent that wrote it

#### Scenario: A loop's lineage is unaffected

- **WHEN** a loop declares no document and fires only its own agent
- **THEN** its checkpoint lineage behaves exactly as before
