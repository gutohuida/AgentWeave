## MODIFIED Requirements

### Requirement: Automatic checkpointing is configured as a threshold in proportion or in tokens

The Hub SHALL let an operator configure whether checkpoints are produced automatically, and SHALL
accept the threshold either as a proportion of the context window or as an absolute token count.

Context windows differ enough between models that an absolute instruction is often the meaningful
one. An absolute threshold also requires no context window at all, so it remains usable for a model
whose window is unknown, where a proportion cannot be evaluated.

A threshold SHALL be expressed as a mode together with a value, so that exactly one interpretation
can ever apply. Token thresholds are entered in thousands.

Configuration SHALL resolve from the agent, then the project, then a built-in default. An agent's
threshold replaces the project's entirely, mode and value together; the two MUST NOT be combined
field by field, which would produce a threshold neither was configured to mean.

A token threshold at or above a known context window SHALL be refused, because it can never be
reached.

The configuration SHALL be reachable from the operator's own surfaces and not only over the API,
and where a context window is known the threshold SHALL be shown in both readings, because an
operator setting one unit is reasoning about the other.

Saving any part of a project's configuration SHALL preserve the parts not being edited. A surface
that submits a partial representation to a replacing endpoint silently discards settings the
operator never touched, which is indistinguishable from never having configured them.

#### Scenario: A token threshold is evaluated without a known window

- **WHEN** an agent's context window is unknown
- **AND** its threshold is expressed in tokens
- **THEN** the threshold is evaluated against the observed token count

#### Scenario: A proportional threshold requires a known window

- **WHEN** an agent's context window is unknown
- **AND** its threshold is expressed as a proportion
- **THEN** no automatic checkpoint is triggered from that unresolved window

#### Scenario: An agent threshold replaces the project threshold whole

- **WHEN** a project configures a proportional threshold
- **AND** an agent configures a token threshold
- **THEN** the agent's mode and value both apply
- **AND** the project's mode is not combined with the agent's value

#### Scenario: An unreachable token threshold is refused

- **WHEN** an operator sets a token threshold at or above a known context window
- **THEN** the configuration is refused

#### Scenario: A threshold is entered in the operator's own units

- **WHEN** an operator enters a token threshold
- **THEN** it is entered in thousands
- **AND** where the context window is known, the equivalent proportion is shown alongside it

#### Scenario: Editing one setting does not clear another

- **WHEN** an operator saves a project setting unrelated to checkpointing
- **THEN** the checkpoint configuration is unchanged
