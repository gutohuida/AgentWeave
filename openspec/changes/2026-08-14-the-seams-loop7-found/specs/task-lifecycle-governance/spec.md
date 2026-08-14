# task-lifecycle-governance

## ADDED Requirements

### Requirement: An integration that was skipped can be attempted again

The system SHALL offer a way to attempt integration again for an approved task whose work has not been integrated.

Integration is attempted when a task becomes approved. Where it is skipped, the cause is usually
something the operator can then put right — a main branch that was never named, a checkout with
uncommitted changes, a checkout parked on another branch. Restating the approval does not attempt it
again, because restating a status is deliberately a no-op, so without this the remediation the
system asked for accomplishes nothing.

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

### Requirement: Naming the main branch attempts the integrations that wanted one

The system SHALL attempt integration again, when a project's main branch is set, for approved tasks whose most recent integration was skipped for want of one.

Skipping for want of a main branch tells the operator to choose one in the project's settings.
Discharging that instruction at the moment the operator follows it is what makes the sentence true;
leaving it undischarged means the system asked for something and then ignored it.

Only that cause SHALL be answered this way. Naming a branch says nothing about a checkout with
uncommitted changes or one parked elsewhere, and a merge that failed outright wants a person rather
than a repetition.

Setting the branch SHALL succeed even where the attempt that follows it does not. The operator
changed a setting, and that must stand or fall on its own terms.

#### Scenario: Setting the branch merges the work that was waiting for it

- **WHEN** an approved task's integration was skipped because no main branch was set
- **AND** the operator sets the project's main branch
- **THEN** the work is merged
- **AND** the task is not reopened to achieve it

#### Scenario: Other skips are left alone

- **WHEN** an approved task's integration was skipped because the checkout had uncommitted changes
- **AND** the operator sets the project's main branch
- **THEN** that task's integration is not attempted again

#### Scenario: The setting is saved even when the attempt fails

- **WHEN** setting the main branch triggers an attempt that raises
- **THEN** the main branch is still saved

### Requirement: A task reports the requirement identifiers it was given

A task's representation SHALL report the requirement identifiers linked to it, in the form those identifiers are supplied in.

Identifiers are accepted when a task is created and when it is updated. Reporting them nowhere makes
the field write-only, so a caller cannot confirm what was recorded, and anyone diagnosing why work
did not merge sees a task that appears to be tied to nothing while the links that govern the merge
exist.

The identifiers reported SHALL be the same ones accepted, not the system's internal row identity, so
that what is read back can be submitted again.

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
