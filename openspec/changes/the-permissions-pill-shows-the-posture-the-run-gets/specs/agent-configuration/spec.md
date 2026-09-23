## MODIFIED Requirements

### Requirement: An agent has a default permission posture

An agent SHALL carry an optional default permission posture, chosen from the same postures the
per-run permission control offers and presented with the same labels, editable from the execution
section.

The Hub SHALL apply that default to any run whose conversation has not chosen a posture — including
runs started by a peer message or a schedule, where no operator is present to choose one. A
conversation's own choice SHALL take precedence over it.

An agent's stored autonomy flag is the older two-valued spelling of this same setting, not a second
setting. Writing the posture SHALL update that flag so the two cannot disagree, and clearing the
posture SHALL clear it, since an agent left at full access after full access was cleared would
contradict what the operator was told.

Where the posture is shown at rest — the composer's permission control — it SHALL show what the run
will actually do, and showing it SHALL NOT record it as a choice made for that conversation.

#### Scenario: An unattended run has an answer

- **WHEN** a peer message triggers an agent whose conversation states no posture
- **AND** the agent has a default posture
- **THEN** the run is spawned under that posture

#### Scenario: A conversation overrides the default

- **WHEN** the operator chooses a posture for one conversation
- **THEN** that posture is used for its runs
- **AND** the agent's default is unchanged

#### Scenario: The autonomy flag follows the posture

- **WHEN** an operator sets an agent's default posture to full access
- **THEN** the agent's stored autonomy flag reads as set
- **AND** clearing the posture clears the flag

#### Scenario: An agent with no default shows the built-in posture

- **WHEN** an agent that states no default posture is shown in the composer or its settings
- **THEN** the posture shown is the one its next run would be spawned under
- **AND** showing it does not record it as a choice
