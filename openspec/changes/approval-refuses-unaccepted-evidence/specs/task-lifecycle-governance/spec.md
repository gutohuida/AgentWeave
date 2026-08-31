## ADDED Requirements

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

**Rejected evidence SHALL NOT cause the refusal.** It has been judged, the judgement was the other
way, and the author's only legitimate next move is to record evidence that satisfies the wording. A
refusal there would wedge the task behind a decision its holder cannot reverse.

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
  rejected
- **THEN** the approval succeeds

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

#### Scenario: Work that can already be merged is approved and reported

- **WHEN** approval is requested for a task with accepted evidence naming a commit and further
  evidence still awaiting review
- **THEN** the approval succeeds
- **AND** the accepted work is merged
- **AND** the evidence still awaiting review is reported on the approval

### Requirement: Accepting evidence attempts the integrations that wanted it

The system SHALL attempt integration again, when evidence is accepted, for every approved task linked to that evidence's requirement whose commit is not already recorded as merged for that task.

Refusing approval while evidence is unaccepted tells the reader to accept it. Discharging that
instruction at the moment they follow it is what makes the sentence true; without it, an approved
task whose evidence is accepted afterwards stays unmerged, and approving again cannot merge it,
because restating a status is deliberately a no-op. The system would have asked for something and
then ignored it being done.

**The condition SHALL be a commit that is not in the product, and SHALL NOT be the reason the
previous attempt gave.** Approval merges what is accepted at the moment it runs, so a task that had
some accepted evidence and some awaiting has already recorded a *merge*, not a skip — and its
awaiting commit is exactly the one that still needs to land. A rule expressed in terms of the last
attempt's reason cannot reach it, and the newer commit would stay outside the product permanently
while the task sat terminal at `approved`. That is the defect this capability exists to remove,
arriving one commit smaller.

The attempt SHALL be made only where the accepted evidence names a commit. Evidence recording paths
produces nothing to merge, and an attempt that could only record a second identical skip adds noise
to a record whose purpose is to distinguish a no-op from work reaching the product.

An attempt SHALL be permitted to record a skip. Where the repository cannot take the commit — a
checkout with uncommitted changes, a checkout parked elsewhere — the attempt SHALL record that
reason rather than being suppressed. The operator accepted something and it did not land; saying so
is the account they need, and silence there is how work goes missing quietly.

The two "already there" cases are deliberately answered differently, and the difference is what each
one tells the reader. Where **this task has already recorded a merge of this commit**, no attempt is
made at all: repeating it could only append a row saying nothing happened, to a record that exists to
distinguish a no-op from work reaching the product. Where the commit is in the main branch by some
other route — merged by hand, or carried in by another task's integration — the attempt SHALL run and
SHALL record that it was already integrated, because that is a fact about the repository the reader
does not otherwise have. Whether a commit is present SHALL be settled by asking the repository rather
than by reading the record of previous attempts.

Rejecting evidence SHALL attempt nothing.

This SHALL apply whichever surface accepted the evidence — the operator's, or an agent granted the
capability. The remedy the refusal names is available to both, so the discharge of it must be too.

Accepting SHALL succeed even where the attempt that follows it does not. The decision is a judgement
about the evidence, and a repository failure SHALL NOT reverse it.

#### Scenario: Accepting the evidence merges the work that was waiting for it

- **WHEN** an approved task's integration was skipped because no accepted evidence named a commit
- **AND** that evidence is then accepted
- **THEN** the work is merged into the project's main branch
- **AND** the task is not reopened to achieve it

#### Scenario: An agent's acceptance merges it too

- **WHEN** an agent granted the capability accepts a peer's evidence for an approved task whose
  integration was skipped for want of it
- **THEN** the work is merged

#### Scenario: The work left over from a partial merge is merged when it is accepted

- **WHEN** an approved task's approval merged its accepted evidence and left a second piece awaiting
  review
- **AND** that second piece is then accepted
- **THEN** its commit is merged into the project's main branch
- **AND** the task is not reopened to achieve it

#### Scenario: A commit this task already merged is not attempted again

- **WHEN** evidence is accepted for an approved task that already has a recorded merge of that same
  commit
- **THEN** no attempt is made
- **AND** no further integration is recorded

#### Scenario: A commit that reached the main branch some other way is recorded, not merged again

- **WHEN** evidence is accepted for an approved task that has no recorded merge of that commit, and
  the commit is nevertheless already reachable from the main branch
- **THEN** nothing is merged
- **AND** the attempt records that it was already integrated

#### Scenario: An attempt that cannot proceed records why

- **WHEN** evidence naming a commit is accepted for an approved task while the checkout has
  uncommitted changes
- **THEN** nothing is merged
- **AND** the attempt is recorded with that reason

#### Scenario: Rejecting attempts nothing

- **WHEN** evidence for an approved task is rejected
- **THEN** no integration is attempted

#### Scenario: The decision is recorded even when the attempt fails

- **WHEN** accepting evidence triggers an attempt that raises
- **THEN** the evidence is still accepted

#### Scenario: A task that is not approved is left alone

- **WHEN** evidence is accepted for a task that has not been approved
- **THEN** no integration is attempted for it

## MODIFIED Requirements

### Requirement: An integration that cannot proceed does not block approval

The transition into `approved` SHALL still succeed where integration cannot be attempted, and the integration SHALL be recorded as skipped together with the reason. Integration cannot be attempted when the project has no configured main branch, when the project's working directory cannot be resolved, when the project is not a repository, when the primary checkout has uncommitted changes to tracked files, when the primary checkout is not on the main branch, or when no accepted evidence for the task names a commit to merge.

Two of those are enumerated here for the first time. An unresolvable working directory has always
been skipped this way and was simply missing from the list; it is added because this change argues
from the list being closed, and an argument from a list that is not actually closed is worth
nothing.

The last of them is narrower than it reads. Work recorded but not yet judged is refused at approval
rather than skipped after it, so what remains in this list is the task that genuinely produced no
commit anyone is waiting to accept: work whose
evidence records paths, work whose evidence was rejected, and work that produced no evidence at all.
For those, nothing being merged is the true account rather than a gap, and blocking approval would
block work the product supports.

Untracked files SHALL NOT prevent integration. The system writes specification documents into the
project directory, so untracked content is the ordinary state of a working project rather than a
signal that a merge is unsafe.

Where integration is attempted and fails, the transition SHALL NOT be rolled back. The approval is a
judgement that the work is good; a repository failure SHALL NOT reverse it. Coverage SHALL then
report the requirement as `verified, not integrated`, which is a true statement of what happened.

A project that is not a repository SHALL be no less approvable than before this capability existed.

#### Scenario: An unconfigured main branch does not block approval

- **WHEN** a task is approved in a project with no configured main branch
- **THEN** the approval succeeds
- **AND** nothing is merged
- **AND** the skipped integration is recorded with its reason

#### Scenario: A dirty primary checkout skips rather than merges

- **WHEN** a task is approved while the primary checkout has uncommitted changes to tracked files
- **THEN** the approval succeeds, no merge is attempted, and the reason is recorded

#### Scenario: Untracked files do not prevent a merge

- **WHEN** a task is approved while the project directory holds untracked files
- **THEN** the work is integrated

#### Scenario: A failed merge leaves the approval standing

- **WHEN** integration is attempted and the merge fails
- **THEN** the task remains `approved`
- **AND** coverage reports the served requirements as `verified, not integrated`

#### Scenario: A project without a repository approves unchanged

- **WHEN** a task is approved in a project whose evidence footprints record paths rather than commits
- **THEN** the approval succeeds and no integration is attempted

#### Scenario: A task whose evidence was rejected approves and merges nothing

- **WHEN** a task whose only evidence naming a commit was rejected is approved
- **THEN** the approval succeeds
- **AND** the skipped integration is recorded
