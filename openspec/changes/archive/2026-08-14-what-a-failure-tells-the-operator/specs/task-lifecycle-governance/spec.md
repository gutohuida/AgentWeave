# task-lifecycle-governance

## MODIFIED Requirements

### Requirement: An integration that was skipped can be attempted again

The system SHALL offer a way to attempt integration again for an approved task whose work has not been integrated, and SHALL name that way when it reports a skip the operator can put right.

Integration is attempted when a task becomes approved. Where it is skipped, the cause is usually
something the operator can then put right — a main branch that was never named, a checkout with
uncommitted changes, a checkout parked on another branch. Restating the approval does not attempt it
again, because restating a status is deliberately a no-op, so without this the remediation the
system asked for accomplishes nothing.

A skip SHALL NOT instruct the operator to approve the task again. The task is already approved by the
time the skip is read, and following that instruction provably does nothing: the request succeeds,
the status is unchanged, no attempt is recorded, and nothing is merged. An instruction that fails
silently is worse than none, because it spends the operator's confidence as well as their time.

Where a skip names a cause the operator can put right, it SHALL point at the remedy that works —
retrying the integration, or the setting whose absence caused the skip.

Retrying SHALL be available to the operator and to agents, and SHALL be refused for a task that is
not approved.

Retrying a task whose work has already been integrated SHALL be permitted and SHALL merge nothing.
Whether work has reached the main line is a question about the repository, so it is asked again
rather than inferred from what was previously attempted.

Every retry SHALL be recorded exactly as a first attempt is.

An agent able to retry SHALL be able to read what the attempts reported. An agent that can act on an
outcome it cannot see is acting blind.

#### Scenario: Work a skip left behind is merged on retry

- **WHEN** an approved task's integration was skipped
- **AND** the cause is put right and integration is retried
- **THEN** the work is merged into the project's main branch
- **AND** the retry is recorded

#### Scenario: Retrying an unapproved task is refused

- **WHEN** integration is retried for a task that is not approved
- **THEN** the request is refused
- **AND** nothing is merged

#### Scenario: Retrying after a merge merges nothing

- **WHEN** integration is retried for a task whose work is already on the main branch
- **THEN** nothing is merged
- **AND** the attempt is recorded as skipped because the work is already there

#### Scenario: An agent reads and retries

- **WHEN** an agent asks what a task's integration attempts reported
- **THEN** it receives them
- **AND** it may retry the integration

#### Scenario: A skip does not send the operator back to approval

- **WHEN** integration is skipped because the checkout has uncommitted changes
- **THEN** the reason does not instruct the operator to approve the task again

#### Scenario: A skip names the remedy that works

- **WHEN** integration is skipped because the checkout has uncommitted changes or is on another
  branch
- **THEN** the reason directs the operator to retry the integration once the cause is put right

### Requirement: A task reports the requirement identifiers it was given

A task's representation SHALL report the requirement identifiers linked to it, in the form those identifiers are supplied in.

Identifiers are accepted when a task is created and when it is updated. Reporting them nowhere makes
the field write-only, so a caller cannot confirm what was recorded, and anyone diagnosing why work
did not merge sees a task that appears to be tied to nothing while the links that govern the merge
exist.

The identifiers reported SHALL be the same ones accepted, not the system's internal row identity, so
that what is read back can be submitted again.

Identifiers SHALL be reported in an order that reads as the operator numbered them, comparing the
numeric parts of an identifier by value. Ordering them as plain text places an eleventh requirement
between the first and the second, which reads as a defect in data that is correct and costs a
diagnosis every time someone checks what a task is tied to.

An identifier with no numeric part SHALL still be ordered deterministically. Identifiers are
authored by the operator and nothing constrains their shape.

References that resolved to no requirement SHALL NOT be reported among them. They are already
reported as unresolved, and repeating them here would invite a caller to resubmit a reference that
has already failed.

#### Scenario: A task reports the identifiers it was created with

- **WHEN** a task is created naming requirement identifiers
- **AND** the task is read back
- **THEN** it reports those identifiers

#### Scenario: Unresolved references are not reported as links

- **WHEN** a task names a requirement identifier that matches nothing
- **THEN** the identifier is reported as unresolved
- **AND** it is not reported among the task's linked identifiers

#### Scenario: Identifiers are ordered by number

- **WHEN** a task is linked to requirements numbered 1, 2 and 11
- **THEN** they are reported in that order

#### Scenario: An identifier without a number is still ordered

- **WHEN** a task is linked to a requirement whose identifier has no numeric part
- **THEN** the reported order is deterministic
