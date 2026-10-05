## MODIFIED Requirements

### Requirement: Approval is refused while a gated requirement is unverified

Where a task links requirements whose document rigor is `gate`, the system SHALL refuse the
transition into `approved` while any of those requirements is not verified.

The check SHALL run inside the same transition service every status write already passes through,
and SHALL NOT exist as a second enforcement point. A second point is a second thing to bypass, and
the rule that no route may assign a task's status directly is what makes one point sufficient.

Verification SHALL be determined by the same coverage computation the document and project surfaces
use. A gate that computed its own answer could refuse a task while the document beside it reported
everything satisfied, and nothing would establish which was wrong.

`sketch` and `contract` requirements SHALL report their state and SHALL NOT block the transition,
except that a requirement whose state is `rejected` SHALL block it at every rigor. `rejected` means
every piece of evidence recorded for the requirement's current wording was reviewed and rejected;
approving a task over it records as done a requirement whose only proof was judged not to prove it
(the FR-11 incident). The way out is the author's own: recording new evidence moves the
requirement out of `rejected`.
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
  unverified, and none is `rejected`
- **THEN** the transition succeeds

#### Scenario: A rejected requirement blocks at every rigor

- **WHEN** approval is requested for a task serving a `sketch`, `contract` or `gate` requirement
  whose every piece of evidence for its current wording was rejected
- **THEN** the transition is refused, naming that requirement, its state `rejected`, and the remedy
  to record evidence that satisfies the current wording
- **AND** the task's status is unchanged

#### Scenario: New evidence lifts the block

- **WHEN** new evidence is recorded for that requirement, and accepted
- **AND** approval is requested again on a `sketch` document
- **THEN** the transition succeeds

#### Scenario: A rejected contract requirement is refused, not reported

- **WHEN** approval is refused for a task serving a `rejected` `contract` requirement
- **THEN** the requirement appears once, among the refusal's blocking requirements, and not among
  the reported ones

#### Scenario: A contract does not block

- **WHEN** approval is requested for a task whose linked requirements are `contract` rigor and
  unverified, and none is `rejected`
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

Approval of a task that serves requirements is governed at every rigor, because a `rejected`
requirement blocks it at every rigor. So its transition SHALL record the state and rigor of each
requirement the task serves, `sketch` included. A task serving no requirement was governed by no
requirement policy, and its transition SHALL record none.

#### Scenario: A passed gate stays explicable

- **WHEN** a task is approved under a gate
- **AND** the document's rigor is later changed
- **THEN** the recorded transition still states the policy that applied when it was approved

#### Scenario: A sketch approval records its policy

- **WHEN** a task serving `sketch` requirements is approved
- **THEN** the recorded transition carries the policy: each served requirement's state and rigor

#### Scenario: A task serving nothing records no policy

- **WHEN** a task serving no requirement is approved
- **THEN** the recorded transition carries no policy

### Requirement: Approval is refused while evidence that would merge sits unaccepted

The system SHALL refuse the transition into `approved` where the task has evidence awaiting review that names a commit and no accepted evidence naming a commit.

Approval is what places work in the product. Where a commit has been produced and recorded but never
judged, approving records that the work is good and merges nothing, and the account of what happened
is a skip reading "no accepted evidence names a commit" — which is true of the merge and false about
the world, because the commit exists and is waiting for a person. A terminal state that can mean
either "shipped" or "sitting unread on a branch" cannot answer the question it exists to answer.

**The refusal SHALL fire only where evidence exists and is unaccepted.** A task with no evidence at
all SHALL remain approvable, unchanged. Research, documentation and decision work produces no commit
and must not be blocked by machinery about merging; approval must never be blocked by the *absence*
of an integration, only by one that would fail.

**Evidence that names no commit SHALL NOT cause the refusal.** Accepting it could not change what
integration merges, so refusing on it would state a remedy that does not work: the operator accepts
it, approval is refused again for the same reason, and there is no further move.

**Rejected evidence SHALL NOT cause this refusal.** It has been judged, the judgement was the other
way, and the author's only legitimate next move is to record evidence that satisfies the wording. A
refusal *about merging* there would wedge the task behind a decision its holder cannot reverse. A
requirement whose evidence is all rejected refuses approval separately, under "Approval is refused
while a gated requirement is unverified", whose remedy is that next move.

**The refusal SHALL NOT fire where integration could not be attempted in any case** — where the
project has no configured main branch, where its working directory cannot be resolved, where it is
not a repository, or where it has no branch by the configured name. Accepting the evidence would
merge nothing in those projects, so the refusal would block every task in them behind a remedy that
changes nothing. These are the same conditions under which work that will not merge is not refused
either, and they SHALL be the same conditions rather than a second list that can drift from it.

This refusal SHALL apply regardless of the rigor of any document the task's requirements belong to.
It is not an assertion that the work is unproven; it is an assertion that approving now would place
nothing in the product while something is waiting to be placed there. Were it conditional on rigor
it would be absent from a default project, where every document begins at the rigor that enforces
nothing.

The refusal SHALL be carried in the same typed refusal that reports unverified requirements and work
that will not merge, and SHALL name each piece of evidence that is waiting rather than only how many
there are.

**Each named piece SHALL say which task recorded it.** Evidence is reached through the requirements a
task serves, and a requirement may be served by more than one task, so a task can be refused over
evidence recorded by another one — and would be, since that evidence's commit is part of what this
task's approval merges. Naming only the requirement and the commit would show the reader a fact with
no route back to its cause. Where the recording task is not the task being approved, the refusal
SHALL say so.

**The refusal SHALL name both remedies: accepting the evidence, and granting an agent the capability
to accept it.** Accepting evidence is the operator's unless an agent has been granted it, and no
agent is granted it by default, so an agent that reads this refusal can take neither remedy itself
and needs to know what to ask a person for. A refusal naming a remedy its reader cannot reach, and
not saying so, spends the reader's time and then the operator's.

The check SHALL live inside the single transition service, and SHALL NOT introduce a second
enforcement point.

#### Scenario: Evidence awaiting review refuses approval

- **WHEN** approval is requested for a task whose only evidence names a commit and is awaiting review
- **THEN** the transition is refused
- **AND** the refusal names that evidence
- **AND** the task's status is unchanged
- **AND** nothing is merged

#### Scenario: The refusal names both ways out

- **WHEN** approval is refused for unaccepted evidence
- **THEN** the refusal states that the evidence can be accepted
- **AND** states that an agent can be granted the capability to accept it

#### Scenario: A task with no evidence approves unchanged

- **WHEN** a task with no recorded evidence is approved
- **THEN** the approval succeeds

#### Scenario: Evidence naming no commit does not refuse

- **WHEN** approval is requested for a task whose only awaiting evidence records paths rather than a
  commit
- **THEN** the approval succeeds

#### Scenario: Rejected evidence does not refuse

- **WHEN** approval is requested for a task whose only evidence naming a commit was reviewed and
  rejected, and each requirement it serves also has accepted evidence naming no commit
- **THEN** the approval succeeds, and nothing is merged

#### Scenario: Evidence all rejected is refused by the requirement, not by this refusal

- **WHEN** approval is requested for a task serving a requirement whose every piece of evidence was
  rejected
- **THEN** it is refused as a `rejected` requirement, with the remedy to record evidence, and not as
  evidence awaiting review

#### Scenario: The refusal says whose evidence it is

- **WHEN** approval is refused over evidence recorded by a different task that serves the same
  requirement
- **THEN** the refusal names that task

#### Scenario: Unaccepted evidence refuses approval even at sketch rigor

- **WHEN** approval is requested for a task with awaiting evidence naming a commit, whose documents
  are all `sketch`
- **THEN** the transition is refused

#### Scenario: A project with no main branch is not blocked

- **WHEN** approval is requested for a task with awaiting evidence naming a commit, in a project with
  no configured main branch
- **THEN** the approval succeeds
- **AND** the skipped integration is recorded with its reason

#### Scenario: A project that is not a repository is not blocked either

- **WHEN** approval is requested for a task with awaiting evidence naming a commit, in a project
  whose directory is not a git repository
- **THEN** the approval succeeds

#### Scenario: Every waiting piece of evidence is named, not just one per branch

- **WHEN** approval is refused for a task carrying two pieces of awaiting evidence that name
  different commits on the same branch
- **THEN** the refusal names both of them

#### Scenario: Work that can already be merged is approved and reported

- **WHEN** approval is requested for a task with accepted evidence naming a commit and further
  evidence still awaiting review
- **THEN** the approval succeeds
- **AND** the accepted work is merged
- **AND** the evidence still awaiting review is reported on the approval
