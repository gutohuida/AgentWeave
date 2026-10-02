## ADDED Requirements

### Requirement: The threshold, the notes point and the final warning are placed before the runner's own compaction

The system SHALL place a conversation's built-in checkpoint threshold, its built-in notes point and its final warning relative to the context proportion at which the runner the agent is bound to compacts a conversation by itself, so that each is reached before that runner's compaction.

Each runner SHALL declare that proportion. A runner that compacts earlier than another SHALL get
proportionally earlier built-in points. For a runner that compacts at about 95% of its window, the
built-in threshold, notes point and final warning SHALL remain 80%, 70% and 92%. For a runner that
compacts at about 80%, they SHALL be 65%, 55% and 77%.

A configured threshold that lies past the runner's final-warning point SHALL be lowered to that
point for that agent, whichever runner it is, including a runner that compacts at about 95%, for
which a configured 93% to 99% becomes 92%. The lowering SHALL be stated in the agent's checkpoint
settings whenever the agent's effective threshold is below its configured one, and in the project's
checkpoint settings whenever the project's threshold is lowered for any of its agents. It SHALL
NOT be refused, because a project's threshold is shared by agents on runners that compact at
different points. A notes point that is not below the lowered threshold SHALL be lowered with it.
For a runner that compacts earlier than at about 95% of its window, a threshold expressed in
tokens SHALL also be treated as crossed once the reading's proportion reaches the runner's
final-warning point, and a notes point expressed in tokens SHALL likewise be treated as reached once
the reading's proportion is ten points below that final-warning point. For a runner that compacts
at about 95%, a threshold or notes point expressed in tokens SHALL NOT be treated as crossed or
reached on the reading's proportion, because a threshold set in tokens is chosen for a window the
system cannot trust, and firing it early would also generate, and bill, a checkpoint the operator
did not configure.

#### Scenario: A Copilot agent is warned before Copilot compacts

- **WHEN** an agent bound to a runner that compacts at about 80% has no threshold of its own and
  its project has none
- **AND** checkpointing is configured to involve the operator
- **AND** its conversation's context reaches 66%
- **THEN** the conversation is reported as due for a checkpoint

#### Scenario: Claude's points are unchanged

- **WHEN** an agent bound to a runner that compacts at about 95% has no threshold of its own and its
  project has none
- **THEN** its threshold is 80%, its notes point 70% and its final warning 92%

#### Scenario: A project threshold past a runner's final warning is lowered for that runner

- **WHEN** a project's threshold is 80%
- **AND** one of its agents is bound to a runner that compacts at about 80%
- **THEN** that agent's effective threshold is 77%, reported as lowered for its runner
- **AND** the project's other agents keep 80%
- **AND** the project's checkpoint settings say that the threshold is lowered for that agent

#### Scenario: A configured threshold past Claude's final warning is lowered and says so

- **WHEN** an agent bound to a runner that compacts at about 95% has a configured threshold of 96%
- **THEN** its effective threshold is 92%
- **AND** its checkpoint settings say that its threshold is lowered to 92%

#### Scenario: A dismissed Copilot conversation gets its final warning before the compaction

- **WHEN** a conversation of an agent bound to a runner that compacts at about 80%, configured to
  involve the operator, had its warning dismissed
- **AND** its context reaches 77%
- **THEN** it is warned again, and that warning cannot be dismissed

#### Scenario: A token notes point beyond the window is still reached

- **WHEN** an agent bound to a runner that compacts at about 80% has a token threshold and a token
  notes point that its reading has not reached
- **AND** the reading's proportion reaches 67%
- **THEN** the agent is asked for its notes before the checkpoint

#### Scenario: A token threshold beyond the final-warning point still fires in time

- **WHEN** an agent bound to a runner that compacts at about 80% has a threshold expressed in tokens
  and its reading has not reached it
- **AND** the reading's proportion reaches 77%
- **THEN** the threshold is treated as crossed

#### Scenario: A Claude token threshold is not fired early

- **WHEN** an agent bound to a runner that compacts at about 95% has a threshold expressed in tokens
  and its reading has not reached it
- **AND** the reading's proportion is 92% or more
- **THEN** the threshold is not treated as crossed
- **AND** its checkpoint settings do not say that its threshold is lowered

#### Scenario: A Claude percent threshold of 95% is lowered to 92%

- **WHEN** an agent bound to a runner that compacts at about 95% has a configured threshold of 95%
- **THEN** its effective threshold is 92%
- **AND** its checkpoint settings say that its threshold is lowered to 92%
