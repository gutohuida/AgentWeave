## ADDED Requirements

### Requirement: A review nobody is free to take names who holds what

Where no agent can be resolved for a review because none is available, the Hub SHALL surface a reason naming every agent on the project's roster and the reason that agent could not take it.

A sentence that says every agent is *"either running a turn, already holding active work, or is the
one that completed this task"* names nobody. It is the whole of what the operator is shown in place
of the queue. Measured on the operator's own flow, it stood for most of a night. The agent asked to
diagnose it blamed finished tasks, and the operator could not see that the holdings were follow-up
work outside the flow.

For each non-archived agent, the reason SHALL state the first of these that applies:
1. it is excluded from this review, stated with the reason the resolution applied to that agent;
2. it has no runner bound;
3. it holds tasks that still make it unavailable, naming each such task by identifier, status and
   the loop that holds it, where a bounded number MAY be named and the rest counted;
4. it is running a turn.

A task in an active status that nothing will move SHALL NOT be named as a reason an agent could not
take the review. Such a task does not make its assignee unavailable, so naming it would state a
cause that is not one. The set named here SHALL be the set the availability determination actually
used.

The count of held tasks named here MAY therefore differ from the count of active tasks the roster
shows for the same agent. The two answer different questions — what an agent holds, and what
prevents a flow giving it work — and the reason SHALL be worded so that a reader is not told the two
disagree about the same fact.

The facts SHALL come from the same determination that found the agent unavailable, never from a
second one. A reason built separately could name an agent the resolution considered free.

The reason SHALL NOT describe an agent as having completed the work when the resolution excluded
that agent for a different reason, such as having reviewed the task without recording a verdict.

The reason SHALL name a way to free a held agent that exists and that reaches every agent the
reason named. Ending a loop's claim on its tasks frees every agent whose holdings are only that
loop's, and rejecting an unwanted task frees whoever held it. The reason SHALL NOT name pausing,
which does not free an agent: a paused loop still holds, because resuming it briefs the assignee on
the same task again. Naming a control that does not have the stated effect is the defect this
requirement exists to end, and it is not cured by the control being easy to reach.

Where the reason names ending a loop's claim, it SHALL identify which loop, and that loop SHALL be
one other than the one whose review could not be staffed. Ending the latter would stop the work the
reason is asking the operator to unblock.

The reason SHALL name an action that exists for the task in its present status:
- for a `completed` task, the landing action as the operator's way to review it themselves. It
  SHALL NOT promise that landing approves it. Landing is subject to the approval gate, and at this
  point the task's evidence names a commit and is often not yet judged, so the gate may refuse;
- for an `under_review` task, the operator's own decision on it. It SHALL NOT name the landing
  action, which refuses a task in that status.

Where an agent is excluded for more than one reason, the reason SHALL state the most specific:
- having been recorded as completing the task outranks having reviewed it without a verdict;
- having reviewed it without a verdict outranks having merely worked on it.

The broader set of agents that may have authored a task includes whoever holds it and whoever ran
on it, and a silent reviewer is both.

The reason SHALL fit every surface that carries it. Where naming every agent would exceed that, the
remaining agents SHALL be counted rather than omitted without a count, and the action SHALL still be
named. Where the roster has any agent, the reason SHALL name at least one: an agent's held tasks are
counted before the agent itself is. Task identifiers may be chosen by whoever creates the task, and
a few long ones held by the first agent would otherwise leave a reason that names nobody, which is
the defect this requirement exists to end.

This requirement changes what the Hub **says** at the unstaffed rung. It does not change which
agents are available. *"A flow resolves a reviewer by declaration, then by availability"* still
decides that.

#### Scenario: Every agent that holds work is named with what it holds

- **WHEN** a flow cannot staff a review of a completed task, and the agents other than its author
  each hold tasks in active statuses
- **THEN** the surfaced reason names each of those agents
- **AND** it names each agent's held tasks by identifier and status, up to the bound, and counts the
  rest

#### Scenario: A task nothing will move is not named as a reason

- **WHEN** a flow cannot staff a review, and an agent other than the author is assigned a task in an
  active status that no live loop walks and no queued turn names
- **THEN** that agent is not described as held by that task
- **AND** the task's identifier does not appear in the surfaced reason

#### Scenario: The reason names the loop to end, and never the stuck one

- **WHEN** a flow cannot staff a review because every other agent holds tasks belonging to a
  different loop
- **THEN** the surfaced reason names each holding with the loop that holds it
- **AND** the way forward it offers names that other loop, not the loop whose review could not be
  staffed
- **AND** it does not offer pausing as a way to free an agent

#### Scenario: The author is named as excluded, not as busy

- **WHEN** the author of the task also holds other tasks in active statuses
- **THEN** the reason states the author's exclusion for this task
- **AND** it does not list the author's other holdings in its place

#### Scenario: A reviewer that gave no verdict is not said to have completed the work

- **WHEN** a review selected on availability ends without a verdict, and the second resolution finds
  nobody
- **THEN** the reason states that the agent which gave no verdict reviewed the task without
  recording one
- **AND** it does not state that this agent completed the task

#### Scenario: On operator-completed work the silent reviewer is still named as silent

- **WHEN** the operator completed the task, a review selected on availability ends without a
  verdict, and the second resolution finds nobody
- **THEN** the reason states that the agent which gave no verdict reviewed the task without
  recording one
- **AND** it does not describe that agent only as having worked on the task

#### Scenario: A completed task's reason does not promise approval

- **WHEN** the unstaffed task is `completed`
- **THEN** the reason names the landing action as the operator's own review
- **AND** it does not state that landing approves the task

#### Scenario: An empty roster is stated

- **WHEN** a flow cannot staff a review and the project has no non-archived agent
- **THEN** the reason states that the roster has no agent
- **AND** it still names the action

#### Scenario: An under-review task's reason does not name an action that refuses it

- **WHEN** the unstaffed task is `under_review`
- **THEN** the reason names approving, rejecting, or returning it for revision
- **AND** it does not name the landing action

#### Scenario: A large roster still produces a reason every surface accepts

- **WHEN** so many agents are unavailable that naming each would exceed the length the loop's run
  history accepts
- **THEN** the reason counts the agents it does not name
- **AND** it still names the action
- **AND** the job's run history is returned successfully

#### Scenario: Long task identifiers still leave an agent named

- **WHEN** the first agent in name order holds several tasks whose identifiers are as long as a
  task identifier may be
- **THEN** the reason names that agent, with as many of its held tasks as fit, and counts the rest
- **AND** it still names the action
