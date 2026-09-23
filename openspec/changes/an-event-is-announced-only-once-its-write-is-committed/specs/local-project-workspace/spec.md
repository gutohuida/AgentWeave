## ADDED Requirements

### Requirement: An event is announced only once the write it reports is committed
The Hub SHALL send a live event that reports a database write only after the transaction holding that write has committed, and MUST NOT send it when that transaction rolls back or ends without committing.

A write staged inside another function's transaction (one that writes its event row with
`commit=False` and leaves the commit to its caller) SHALL announce through a deferred form that is
published by the commit of that same session's root transaction. A failure to publish a deferred
announcement MUST NOT fail the commit or change what the calling route answers.

#### Scenario: A review refused at delivery does not announce a resolution
- **WHEN** entering review stages the resolution of a task's open divergence and the review is then refused and its transaction rolled back
- **THEN** no `run_divergence_resolved` event is sent on any stream
- **AND** the divergence is still open and no `run_divergence_resolved` event row exists

#### Scenario: A real resolution is announced once, before the route's own event
- **WHEN** the operator moves a task with one open divergence to `under_review` and the route commits
- **THEN** exactly one `run_divergence_resolved` event is sent, after the commit
- **AND** it is sent before the route's `task_updated` event

#### Scenario: A deferred announcement that cannot be sent does not fail the write
- **WHEN** a deferred announcement's payload cannot be serialised at commit
- **THEN** the commit succeeds, the other announcements of that commit are sent, and the failure is logged
