## MODIFIED Requirements

### Requirement: A task entering review must not still name its author as its holder

The system SHALL refuse a transition to `under_review` when the task's assignee is the **agent**
recorded as having moved it to `completed`. Where the task has no assignee the transition SHALL be
permitted.

This rule binds **every actor, including the operator**, and that is what distinguishes it from
author/reviewer separation above. That rule is about authority — who is entitled to sign work off —
and exempts the operator because a single-operator project must be able to approve anything. This
rule is about the state the move produces, which misdescribes the world whoever writes it: it
asserts that a reviewer holds the task while naming its author.

**The refusal SHALL name a remedy the refused actor can take, and SHALL NOT name a control that
actor does not have.**
- **To the operator,** it SHALL name the landing action as the way to review the work themselves,
  and SHALL NOT promise that landing approves it, because landing is subject to the approval gate.
  It SHALL also name the single API request that names a different reviewer and sends the task to
  review together, stated as a request rather than as a control in the app.
- **To an agent,** it SHALL state that none of the tools the agent is offered changes who holds a
  task, and SHALL name who can move the work on. It SHALL NOT tell the agent to change the task's
  holder by any route.

Measured on the operator's own project: agents met this refusal eight times and could act on none
of them. Its remedy, *"clear the assignee"*, is a field no agent tool carries and no control in the
app sends. The action that works sat unnamed beside it.

A refusal that tells an agent no agent *can* change a task's holder would be false. The agents'
HTTP task route accepts an assignee today, though neither rendering of the agent's tool surface
offers one. The refusal describes the surface the agent is given.

**A review dispatched by the operator and refused because the reviewer is the task's author SHALL
name a remedy that exists for the task's status**: the landing action for a `completed` task, and
the operator's own decision for an `under_review` task, which landing refuses.

**The refusal SHALL be true whether the assignee it judges was already recorded or was set by the
same operation**, and SHALL NOT state that the task is assigned to that agent. A dispatch writes the
reviewer before it transitions. A refused dispatch then discards that write, so a sentence saying
the task *is assigned to* the agent describes an assignment nobody can see.

**Where no completer is recorded, the system SHALL refuse the transition when the assignee is
recorded as having produced evidence for that task, and SHALL permit it otherwise.** The
unattributable case was previously permitted outright, on the asymmetry the offer rule uses — refuse
to *offer* finished work whose author cannot be ruled out, but permit an actor to *act* on it. That
asymmetry is sound only while acting remains possible. Once author/reviewer separation refuses an
evidence author's verdict on an operator-completed task, permitting the same agent to be named as
its holder produces a task that no actor can move out of `under_review`: the agent is refused every
review outcome, and because no transition on the task names it, the flow reports the review as
genuinely in progress and never restaffs it. Refusing the entry is what keeps the two rules
describing one world — the operator learns before a turn is spent, and the remedy is the one this
refusal already names.

An unassigned task claims that nobody holds it, so nothing is false and no work is stranded, and
that case stays permitted unchanged.

Because the assignee is read at the moment of the transition, any surface that sets both a status
and an assignee in one operation SHALL apply the assignee first, so that a single request naming a
reviewer and sending the task to review is accepted rather than refused on the assignee it replaces.

#### Scenario: Sending a task to review without reassigning it is refused

- **WHEN** a task is moved to `under_review` while still assigned to the agent that completed it
- **THEN** the request is refused with a typed error naming the remedy
- **AND** the task remains in its pre-request status

#### Scenario: The operator is bound by the same rule

- **WHEN** the operator makes that same move
- **THEN** it is refused on the same grounds

#### Scenario: The operator's refusal names the landing action

- **WHEN** the operator's move of a completed task still held by its author to `under_review` is
  refused
- **THEN** the refusal names the landing action as the way to review the work themselves
- **AND** it does not tell the operator to clear the assignee
- **AND** it does not state that landing approves the work

#### Scenario: An agent's refusal does not offer it a control it lacks

- **WHEN** an agent's move of a completed task held by that task's author to `under_review` is
  refused
- **THEN** the refusal states that none of the agent's tools changes who holds a task
- **AND** it does not tell the agent to clear the assignee or to assign a reviewer

#### Scenario: A dispatch refused for an under-review task does not name landing

- **WHEN** the operator dispatches a review of an `under_review` task to the agent recorded as
  completing it
- **THEN** the refusal names approving, rejecting or returning the task for revision
- **AND** it does not name the landing action

#### Scenario: A dispatch refused for a completed task names landing

- **WHEN** the operator dispatches a review of a `completed` task to the agent recorded as
  completing it
- **THEN** the refusal names the landing action
- **AND** it does not tell the operator to clear the assignee

#### Scenario: A refused dispatch does not claim an assignment it discarded

- **WHEN** a dispatch staffs the task's author as its reviewer and the transition is refused
- **THEN** the recorded reason does not state that the task is assigned to that agent
- **AND** the task's assignee is what it was before the dispatch

#### Scenario: Naming a reviewer in the same request succeeds

- **WHEN** one request sets the assignee to a different agent and the status to `under_review`
- **THEN** the request succeeds

#### Scenario: A task with no assignee may enter review

- **WHEN** a completed task with no assignee is moved to `under_review`
- **THEN** the request succeeds

#### Scenario: A task whose completer is unknown may enter review when its holder recorded nothing

- **WHEN** a completed task with no recorded completer is moved to `under_review` while assigned to
  an agent that recorded no evidence for it
- **THEN** the request succeeds

#### Scenario: A task whose completer is unknown is refused when its holder recorded the evidence

- **WHEN** a completed task with no recorded completer is moved to `under_review` while assigned to
  an agent that recorded evidence for it
- **THEN** the request is refused with a typed error naming the evidence as the reason
- **AND** the refusal does not state that any agent completed the task
- **AND** the task remains in its pre-request status

#### Scenario: The reviewer a flow staffs still enters review

- **WHEN** a flow staffs a reviewer for an operator-completed task and assigns the task to it before
  moving the task to `under_review`
- **THEN** the request succeeds, because a staffed reviewer is never an agent that recorded the
  task's evidence
