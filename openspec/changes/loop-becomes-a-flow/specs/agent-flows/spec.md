## ADDED Requirements

### Requirement: A flow is a loop that declares a specification document

The Hub SHALL treat a loop that declares a specification document as a flow, and SHALL apply the
requirements in this capability to it. A loop that declares no document SHALL be unaffected by them
and SHALL behave exactly as it does today.

No separate record SHALL be introduced for a flow. The distinction SHALL be the presence of the
declared document and nothing else.

#### Scenario: A loop with a document is a flow

- **WHEN** a loop declares a specification document
- **THEN** its firings select an agent as well as a task

#### Scenario: A loop without a document is unchanged

- **WHEN** a loop declares no specification document
- **THEN** every firing fires the job's own agent, as before

#### Scenario: A flow with one agent and no declared reviewers behaves as a loop

- **WHEN** a flow's project holds exactly one agent and its document declares no reviewers
- **THEN** every firing fires that agent
- **AND** the observable behaviour is identical to the same queue run as a loop

### Requirement: A firing determines both the task and the agent

Each firing of a flow SHALL determine deterministically which task or tasks are worked and which
agent works each of them. No firing SHALL leave either choice to a firing agent's own judgement.

The agent determined for a task SHALL be one the Hub can actually start. A firing SHALL NOT select an
agent with no runner bound, and SHALL treat such an agent as unavailable rather than failing the
firing.

#### Scenario: The agent is chosen by the Hub, not the agent

- **WHEN** a flow fires and a task needs an agent other than the one that produced it
- **THEN** the Hub determines which agent is fired
- **AND** no agent is asked to nominate one

#### Scenario: An agent with no runner is not selected

- **WHEN** the only otherwise-eligible agent has no runner bound
- **THEN** that agent is not fired
- **AND** the firing reports that it could not staff the step

### Requirement: A completed task is claimable by an agent that did not complete it

The Hub SHALL allow a task in `completed` to be claimed by an agent other than the one recorded as
moving it to `completed`, and SHALL NOT allow it to be claimed by that agent.

This SHALL use the same determination of who completed a task that author/reviewer separation uses
for reaching a review outcome, so that a task the Hub offers to an agent is never one that agent
would then be refused for approving.

#### Scenario: A different agent may take a completed task

- **WHEN** a flow fires and a queued task is `completed`, and an eligible agent is not the one that
  completed it
- **THEN** that agent may be fired for it

#### Scenario: The author may not take back its own completed task

- **WHEN** the only available agent is the one that completed the task
- **THEN** it is not fired for that task
- **AND** the firing reports that it could not staff the review

#### Scenario: Claimability and the approval guard agree

- **WHEN** an agent is fired for a task in `completed`
- **THEN** that agent moving the task to a review outcome is not refused by author/reviewer
  separation

### Requirement: A flow resolves a reviewer by declaration, then by availability

Where a task declares a reviewer, the Hub SHALL attempt to resolve that declaration to an agent in
this project. Where it does not resolve, or where none is declared, the Hub SHALL select any agent
that is not running a turn and holds no task in an active status.

Where neither yields an agent, the flow SHALL surface that it could not staff the step, naming the
task. The flow's job SHALL remain enabled and SHALL remain scheduled.

#### Scenario: A declared reviewer that resolves is used

- **WHEN** a task declares a reviewer that resolves to an eligible agent
- **THEN** that agent is fired for the review

#### Scenario: An unresolvable declaration falls back to availability

- **WHEN** a task declares a reviewer that resolves to no agent in this project
- **THEN** an agent that is not running and holds no active task is fired instead

#### Scenario: A busy agent is not selected

- **WHEN** an otherwise eligible agent is running a turn, or holds a task in an active status
- **THEN** it is not selected while another eligible agent is available

#### Scenario: No eligible agent surfaces rather than stalling silently

- **WHEN** no agent can be resolved or found for a task
- **THEN** the operator is notified, naming the task
- **AND** the flow's job remains enabled and scheduled

#### Scenario: A single-agent project reaches the same outcome by the same rule

- **WHEN** a flow's project holds only the agent that completed the task
- **THEN** the flow surfaces that it could not staff the review
- **AND** no special-case path is taken to reach that outcome

### Requirement: A flow may start every task whose dependencies are met

A firing of a flow MAY start more than one task, and SHALL start only tasks whose dependencies are
met and for which an agent was resolved. The number started SHALL be bounded by the graph and by the
agents available, and SHALL NOT be read from any configured limit.

An agent SHALL NOT be started for two tasks in the same firing.

#### Scenario: Two independent tasks start together

- **WHEN** a flow fires, two queued tasks have all their dependencies met, and two eligible agents
  are available
- **THEN** both tasks are started

#### Scenario: Width is bounded by available agents

- **WHEN** three tasks are startable and one eligible agent is available
- **THEN** one task is started
- **AND** the others keep their status and gain no assignee

#### Scenario: A dependent task does not start alongside its prerequisite

- **WHEN** one queued task depends on another and neither has been approved
- **THEN** only the prerequisite is started

#### Scenario: One agent is not started twice in one firing

- **WHEN** two tasks would both resolve to the same agent
- **THEN** that agent is started for one of them only

### Requirement: A flow's checkpoint lineage belongs to the flow

The Hub SHALL maintain one checkpoint lineage per flow, shared by every agent the flow fires, and
each checkpoint SHALL record which agent wrote it.

A firing SHALL be briefed with the most recent checkpoint of its flow regardless of which agent
recorded it.

#### Scenario: A reviewer is briefed with the implementer's checkpoint

- **WHEN** a flow fires an agent for a task another agent completed, and that agent recorded a
  checkpoint
- **THEN** the fired agent's briefing includes that checkpoint's content

#### Scenario: A checkpoint names its author

- **WHEN** a checkpoint is read from a flow whose firings involved more than one agent
- **THEN** the agent that wrote it is identifiable

### Requirement: A firing's briefing states which tier the agent is working inside

The briefing of each firing SHALL state whether the agent is working inside a flow or a loop, and
SHALL state what follows for the agent — in particular that an agent in a flow completes its task and
stops, because routing the work onward is the flow's responsibility and not the agent's.

#### Scenario: A flow's briefing says routing is not the agent's job

- **WHEN** a flow fires an agent
- **THEN** the briefing states that the flow routes the work onward

#### Scenario: A loop's briefing does not claim a flow's behaviour

- **WHEN** a loop with no document fires its agent
- **THEN** the briefing does not state that anything will route its work onward
