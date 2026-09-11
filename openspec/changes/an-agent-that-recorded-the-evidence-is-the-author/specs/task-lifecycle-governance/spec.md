## MODIFIED Requirements

### Requirement: An agent cannot approve the work it produced

The system SHALL refuse a transition to `approved` requested by an agent when that same **agent** recorded the task's transition into `completed`. Author and reviewer MUST be distinct **agents**.

Distinctness is on agent identity, not run identity. Every turn an agent takes is a new run, so a
rule requiring only "a different run" is satisfied by an agent continuing its own work and forbids
nothing — observed in live use on 2026-08-10, when an agent completed a task on one run and
approved it on the next.

**Where no agent is recorded as completing the task, the system SHALL refuse the transition when the
requesting agent is recorded as having produced evidence for that task.** An operator completion
records no agent, and a task written straight into `completed` records nothing at all; in both the
comparison this rule is built on has nothing to compare, and permitting on that basis let an agent
approve work it had itself recorded as its own — measured on a live Hub on 2026-09-09, where an
agent recorded implementation evidence for a task, the operator marked the task finished, and the
same agent's approval was accepted with nothing refusing it and nothing recording that it had
happened.

This does not weaken the permission that an unattributable move receives. Refusing every move the
system cannot attribute would stop legitimate work over a missing history row; this refuses on the
strength of a **record that exists** — an evidence row in which the agent named this task as the
subject of its own work.

**That fallback SHALL be the evidence record alone, and SHALL NOT be the wider determination of
which agents may have authored the task.** The wider determination includes the agent the task is
assigned to, and a task dispatched for review is assigned to its reviewer — so comparing against it
would refuse the reviewer the system itself staffed, on every operator-completed task, which is the
whole of the review path this rule exists to protect. Of the records that associate an agent with a
task, the evidence is the one the act of reviewing does not create.

**Evidence SHALL refuse its author whatever the state of its review.** An agent whose evidence was
rejected, or whose evidence is still awaiting a decision, still produced the work the row records.
Keying the refusal on a review decision would make the authority to review a task depend on the
outcome of the review being requested.

**Evidence recorded by the operator SHALL NOT refuse any agent.** A person recording what
demonstrates the work is not an agent claiming authorship of it, so a task whose evidence came only
from the operator remains reviewable by any agent.

This rule binds agent runs only. The operator SHALL be permitted to approve work regardless of who
produced it — a single-operator project would otherwise be unable to approve anything — and the
history states that an operator did so.

#### Scenario: Self-approval by the completing agent is refused

- **WHEN** the agent that moved a task to `completed` requests the move to `approved`
- **THEN** the request is refused with a typed error stating that approval requires a different
  actor
- **AND** the task remains in its pre-request status
- **AND** no transition is recorded

#### Scenario: A new run of the same agent is still refused

- **WHEN** the agent that completed a task requests `approved` on a later run
- **THEN** the request is refused
- **AND** the refusal states that starting a new run does not make it a different actor

#### Scenario: A different agent may approve

- **WHEN** an agent other than the one that completed the task requests `approved`
- **AND** the transition is otherwise legal
- **THEN** the request succeeds

#### Scenario: The agent that recorded the evidence is refused on operator-completed work

- **WHEN** the operator recorded a task's move to `completed`, and an agent that recorded evidence
  for that task requests `approved`
- **THEN** the request is refused with a typed error naming the evidence as the reason
- **AND** the refusal does not state that any agent completed the task
- **AND** the task remains in its pre-request status
- **AND** no transition is recorded

#### Scenario: The reviewer the flow staffed is not refused

- **WHEN** a flow staffs a reviewer for an operator-completed task, assigning the task to that
  reviewer, and the reviewer requests `approved`
- **AND** that reviewer recorded no evidence for the task
- **THEN** the request succeeds

#### Scenario: Awaiting or rejected evidence refuses its author just the same

- **WHEN** an agent's evidence for an operator-completed task is still awaiting a decision, or was
  rejected, and that agent requests `approved`
- **THEN** the request is refused

#### Scenario: Evidence the operator recorded refuses nobody

- **WHEN** an operator-completed task's only evidence was recorded by the operator, and an agent
  that no other record associates with the task requests `approved`
- **THEN** the request succeeds

#### Scenario: The operator may approve any work

- **WHEN** the operator approves a task, including one they moved to `completed` themselves
- **THEN** the request succeeds
- **AND** the transition is recorded as an operator action

#### Scenario: Rejection and revision carry the same separation

- **WHEN** the agent that completed a task requests `rejected` or `revision_needed` on it
- **THEN** the request is refused on the same grounds as self-approval

#### Scenario: The evidence fallback covers rejection and revision too

- **WHEN** an agent that recorded evidence for an operator-completed task requests `rejected` or
  `revision_needed` on it
- **THEN** the request is refused on the same grounds as its refused approval
