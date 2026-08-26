## MODIFIED Requirements

### Requirement: A claimed task is still the loop's current item

A task claimed by a firing SHALL be reported among the loop's current items even before any later
step moves it to an in-progress status. The Hub MUST NOT omit a claimed task from a loop's summary
solely because of the status a claim assigns it.

A firing MAY claim more than one task, so a loop's current items are a set rather than a single
value. Where one is claimed the set holds one; a caller SHALL NOT have to distinguish the two cases.

Each reported current item SHALL name the agent fired for it, since under a flow the agent differs
between items in the same firing.

#### Scenario: A freshly claimed task is reported

- **GIVEN** a firing that has claimed its queue's item and not yet begun its turn
- **WHEN** the loop's summary is retrieved
- **THEN** the claimed task is reported among the loop's current items

#### Scenario: Several tasks claimed by one firing are all reported

- **GIVEN** a firing that has claimed two tasks
- **WHEN** the loop's summary is retrieved
- **THEN** both are reported, each naming the agent fired for it

### Requirement: Consecutive firings of one loop occupy one row

A run of consecutive conversations created by the same loop **and belonging to the same agent** SHALL
be presentable, where conversations are listed, as a single row expandable to the firings it stands
for. A loop left running fills the list with threads the operator never began; naming each one is not
sufficient once there are enough of them.

A change of agent SHALL break the run. Consecutive firings by different agents are different events —
under a flow, an implementer followed by a reviewer is the ordinary case, and collapsing them
together would hide the handover that is the most informative thing on the list.

Collapsing SHALL NOT reorder the list. Only *consecutive* conversations may be collapsed together,
so that a conversation which fell between two firings keeps its place between them.

Collapsing SHALL NOT hide that a firing needs the operator: a run containing a conversation waiting
for them SHALL say so without being expanded. A run containing the conversation currently open SHALL
present it.

#### Scenario: A run of firings is one row

- **GIVEN** several consecutive conversations created by the same loop and the same agent
- **WHEN** the operator lists them
- **THEN** they occupy a single row naming the loop and stating how many there are
- **AND** expanding it presents each firing

#### Scenario: A change of agent breaks the run

- **GIVEN** consecutive conversations created by one flow, the first two by one agent and the third
  by another
- **WHEN** the operator lists them
- **THEN** the third does not collapse into the row holding the first two

### Requirement: A firing claims its queue's current item before the turn begins

Each time a loop's job fires and proceeds to claim, the Hub SHALL select the queue's current item or
items deterministically — the queue's existing tasks in an active, non-terminal status if any exist,
else its oldest tasks in an entry status — and SHALL mark each as claimed by that firing before the
firing's agent begins its turn. No firing SHALL leave the choice of which queued task to work to the
firing agent's own judgement.

Where the loop is a flow, the Hub SHALL also determine which agent works each selected task, by the
same standard: deterministically, and never by asking an agent.

A firing SHALL NOT reach the claim at all when it is refused beforehand, whether by the loop's stop
condition, by its agent already running, or by its queue being stalled. A refused firing SHALL claim
nothing, SHALL queue no input for any agent, and SHALL leave every task's status and assignee
unchanged.

#### Scenario: A firing claims the oldest open item when nothing is already in progress

- **WHEN** a loop's job fires and its queue holds only tasks in an entry status
- **THEN** the firing claims the oldest one by creation time
- **AND** that task is marked as claimed before the agent's turn begins

#### Scenario: A firing resumes an item a prior firing left unfinished

- **WHEN** a loop's job fires and its queue already holds a task in an active, non-terminal status
- **THEN** the firing claims that task rather than starting a different one

#### Scenario: A firing with an empty queue claims nothing

- **WHEN** a loop's job fires and its queue holds no task in an entry or active status
- **THEN** the firing claims no item
- **AND** whether the fire proceeds at all is governed by the loop's stop condition, unchanged by
  this requirement

#### Scenario: A refused firing leaves the queue untouched

- **WHEN** a firing is refused before the claim
- **THEN** no task changes status or assignee
- **AND** no input is queued for any agent

#### Scenario: A flow's firing determines the agent alongside the task

- **WHEN** a flow's firing selects a task
- **THEN** it also determines which agent is fired for it, without asking any agent
