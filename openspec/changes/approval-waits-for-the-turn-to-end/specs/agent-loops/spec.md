## ADDED Requirements

### Requirement: A loop does not staff a review of its own agent's work

A loop's firing SHALL NOT select one of its own completed tasks for review, and SHALL NOT report a review it could not staff for such a task.

A loop has one agent and no second party. Every review it could staff would name the agent that completed the work, which author/reviewer separation refuses on arrival — so the review leg produces no reviewer, and the machinery it runs on the way there produces sentences that are false for a loop. The requirements that resolve a reviewer are written for a flow, which declares a specification document and can therefore resolve someone who is not the author; applying them to a loop is what makes a loop ask for a commit it was never going to be given.

Where a loop's task reaches `completed`, the loop SHALL leave it for the operator rather than attempting to advance it, and its firings SHALL NOT report the task as a step the flow could not staff. Nothing about the task is wrong, so nothing about it belongs in the report of what a firing could not do.

Leaving it SHALL NOT mean saying nothing about it. Where a loop has nothing to claim and its queue holds completed work, the reason its firings give SHALL name that work as waiting for the operator to land it. A queue reported only as having no claimable task states a fact and withholds the one thing the operator needs, which is that the work is finished and the next move is theirs — and a loop in that position stays in it on every firing, forever, unless something says so.

This requirement removes a loop's own **selection** of a review and nothing else. The operator SHALL still be able to dispatch a review of a loop's completed task by hand, and a loop's task already recorded in `under_review` under its own author's name SHALL still be recovered by reassignment without moving status. Neither is a loop staffing a review: the first is a person deciding, and the second repairs a holder that was already wrong.

#### Scenario: A completed loop task is not selected for review

- **WHEN** a loop fires and one of its queue's tasks is `completed`
- **THEN** no agent is fired to review that task
- **AND** the task's status is unchanged

#### Scenario: A loop does not ask for evidence its declaration excused

- **WHEN** a loop that declared its work does not need evidence has a task in `completed`
- **THEN** no firing reports that the task has no recorded evidence or no commit to review

#### Scenario: A loop's unstaffed report stays empty for its own completed work

- **WHEN** a loop fires with a completed task in its queue and nothing else to do
- **THEN** the firing reports no review it could not staff

#### Scenario: The firing says the work is waiting for the operator

- **WHEN** a loop fires with a completed task in its queue and nothing it can claim
- **THEN** the reason it reports names that task as finished work waiting for the operator to land it
- **AND** it is not reported merely as a queue with no claimable task

#### Scenario: The operator can still review a loop's completed task by hand

- **WHEN** the operator dispatches a review of a loop's completed task, naming a reviewer that is not its author
- **THEN** the review is staffed and the turn begins, exactly as it would for any other task

#### Scenario: A loop's wedged review still recovers

- **WHEN** a loop's task is in `under_review` and still held by the agent recorded as completing it
- **THEN** a reviewer that is not the author is resolved for it and the assignee is replaced
- **AND** the task remains in `under_review`

#### Scenario: A flow's review leg is unaffected

- **WHEN** a flow fires and one of its document's tasks is `completed`
- **THEN** a reviewer that is not the author is resolved and fired, exactly as before

### Requirement: A loop's approved work is landed in one operator action

The Hub SHALL offer one operator action that carries a loop's completed task to `approved`, performing every transition the lifecycle requires rather than requiring the operator to issue them one at a time.

Landing a loop's work is the only route by which that work reaches the operator's main branch, and it costs three separate calls today, two of which begin as refusals — the task is still held by its author, and `completed` does not reach `approved` directly. Both refusals are correct, and neither is the operator's mistake: they are the shape of a route the product knows and the operator has to rediscover.

The transitions performed SHALL be the ones that already exist, and each SHALL be recorded. The operator taking this action is the reviewer, which is what clearing the author's hold and passing through review already means; a route that recorded fewer transitions would be claiming a history that did not happen. No new edge SHALL be declared for it: the action composes moves the transition map already grants the operator, so the recorded history describes a sequence that was legal one step at a time.

Each recorded transition SHALL name the operator as having asked for it, rather than as a move the system made on their behalf. The operator asked for all three; that they said it in one word instead of three does not make two of them the system's own bookkeeping.

The action SHALL be refused on the same terms as approval itself. Where approval would be refused — including while the task's turn is still live — this action SHALL be refused with the same typed refusal, and SHALL perform none of its transitions.

A refusal arising at any step SHALL leave the task as the action found it, and this SHALL hold for every reason a step can be refused rather than only for the ones the action can foresee. Checking approval's own preconditions first is what makes the refusal the one approval would have given; it is not what makes the action safe, and an action that had only that would release the author's hold before meeting a refusal on the step after.

#### Scenario: One action lands a loop's completed work

- **WHEN** the operator takes the landing action on a loop's completed task whose turn has ended
- **THEN** the task reaches `approved`
- **AND** its work is merged into the project's main branch

#### Scenario: The history records each transition

- **WHEN** the landing action completes
- **THEN** the task's transition history records the release of its author's hold, the move into review, and the approval
- **AND** each is attributed to the operator

#### Scenario: The action is refused while the turn is live

- **WHEN** the operator takes the landing action while the task's agent still has a running turn
- **THEN** the action is refused with the same typed refusal approval would have given
- **AND** the task's status is unchanged

#### Scenario: A refused landing leaves nothing half-applied

- **WHEN** the landing action is refused for any reason
- **THEN** the task's holder, status and integration record are all unchanged

#### Scenario: A refusal on a later step undoes the earlier ones

- **WHEN** the landing action's first transition succeeds and a later one is refused
- **THEN** the task still names the holder it had before the action began
- **AND** no transition from the action is recorded in its history
