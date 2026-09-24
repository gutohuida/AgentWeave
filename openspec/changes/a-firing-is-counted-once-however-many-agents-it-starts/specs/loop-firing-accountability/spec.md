## ADDED Requirements

### Requirement: A firing SHALL be counted once, however many agents it starts

The Hub SHALL count a job's firings as firings: a firing that queues work for at least one agent
SHALL add exactly one to the job's firing count, whether it queues work for one agent or several. A
firing that queues work for no agent SHALL NOT add to it.

A firing counts where it queues its input, not where an agent's turn begins, so a firing whose turn
then fails to begin still counts once: the job did fire, and its record carries why the turn did
not begin.

Each agent a firing starts has its own record, because each agent's work is correlated to its own
conversation and concludes on its own. Those records are the firing's dispatches, and they SHALL
NOT each count as a firing. A job's card SHALL name the count as firings, not as runs, because a run
is one agent's attempt at a turn and the app uses the word for that everywhere else.

#### Scenario: A flow firing that starts two agents counts once

- **GIVEN** a flow with two independent startable tasks and two eligible agents
- **WHEN** the flow fires once and starts both
- **THEN** two records are written for that firing, one per agent
- **AND** the job's firing count rises by one

#### Scenario: A firing that starts one agent counts once

- **WHEN** a plain job or a single-agent loop fires and starts its agent
- **THEN** the job's firing count rises by one

#### Scenario: A refused firing does not count

- **WHEN** a loop's firing is refused because its queue is stalled
- **THEN** the job's firing count does not change

#### Scenario: The card names firings

- **WHEN** the operator reads a job's card
- **THEN** the count is labelled as firings
- **AND** it is not labelled as runs
