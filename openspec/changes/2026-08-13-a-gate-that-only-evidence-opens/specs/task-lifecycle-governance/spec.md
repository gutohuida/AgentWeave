# task-lifecycle-governance

## ADDED Requirements

### Requirement: Approval is refused while a gated requirement is unverified

Where a task links requirements whose document rigor is `gate`, the system SHALL refuse the
transition into `approved` while any of those requirements is not verified.

The check SHALL run inside the same transition service every status write already passes through,
and SHALL NOT exist as a second enforcement point. A second point is a second thing to bypass, and
the rule that no route may assign a task's status directly is what makes one point sufficient.

Verification SHALL be determined by the same coverage computation the document and project surfaces
use. A gate that computed its own answer could refuse a task while the document beside it reported
everything satisfied, and nothing would establish which was wrong.

`sketch` and `contract` requirements SHALL report their state and SHALL NOT block the transition.
A requirement that is structurally invalid or carries no identifier SHALL prevent a gate from
passing, and SHALL be reported as the diagnostic it is rather than as an unverified requirement.

The refusal SHALL be typed, and SHALL name each requirement that caused it together with what would
satisfy it — no linked evidence, evidence awaiting review, or evidence that no longer applies to the
current wording. A refusal that does not say what to do about it cannot be acted on, and an
unactionable gate is turned off.

The refusal SHALL hold identically across every access path: the operator's interface, an agent's
HTTP action, the tool surface, and a scheduled job.

#### Scenario: An unverified gated requirement refuses approval

- **WHEN** approval is requested for a task linking a `gate`-rigor requirement with no accepted
  evidence for its current wording
- **THEN** the transition is refused
- **AND** the task's status is unchanged
- **AND** no transition is recorded

#### Scenario: The refusal says what would satisfy it

- **WHEN** approval is refused by the gate
- **THEN** the response names each blocking requirement's identifier and why it is not verified

#### Scenario: Accepting the evidence opens the gate

- **WHEN** the evidence for the blocking requirement is accepted
- **AND** approval is requested again
- **THEN** the transition succeeds

#### Scenario: A sketch does not block

- **WHEN** approval is requested for a task whose linked requirements are all `sketch` rigor and
  unverified
- **THEN** the transition succeeds

#### Scenario: A contract does not block

- **WHEN** approval is requested for a task whose linked requirements are `contract` rigor and
  unverified
- **THEN** the transition succeeds
- **AND** their state is still reported

#### Scenario: A task linking nothing is unaffected

- **WHEN** approval is requested for a task with no linked requirements
- **THEN** the transition succeeds

#### Scenario: Completion is not blocked by the gate

- **WHEN** a task serving an unverified `gate` requirement is moved to `completed`
- **THEN** the transition succeeds

#### Scenario: The gate holds over every access path

- **WHEN** approval of a blocked task is attempted through the tool surface or a scheduled job
- **THEN** it is refused on the same terms as through the operator's interface

#### Scenario: A broken requirement blocks a gate rather than passing it

- **WHEN** a `gate`-rigor document contains a requirement with no identifier
- **AND** approval is requested for a task linking that document's requirements
- **THEN** the transition is refused, reporting the diagnostic

### Requirement: A transition records the policy that governed it

Every recorded transition SHALL carry the policy in force when it was decided.

Which rigor a document holds is editable by the operator. Without recording what governed a
decision, a gate that passed last month cannot be explained today — and the policy being editable is
what turns that from a theoretical concern into a live one.

#### Scenario: A passed gate stays explicable

- **WHEN** a task is approved under a gate
- **AND** the document's rigor is later changed
- **THEN** the recorded transition still states the policy that applied when it was approved
