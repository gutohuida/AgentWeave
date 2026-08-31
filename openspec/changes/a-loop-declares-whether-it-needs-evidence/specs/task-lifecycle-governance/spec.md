## ADDED Requirements

### Requirement: Work that no evidence governs is integrated from the task's own branch

The system SHALL integrate an approved task whose loop declares that its work needs no evidence from that task's own branch, merging the single commit that branch's tip names, and SHALL NOT merge any branch belonging to an agent.

A task's own branch carries that task's work and nothing else, which is the property per-task
isolation exists to provide. An agent's branch carries every task that agent has ever touched, so
merging one when a single task is approved places unapproved and unreviewed work in the product under
the record of an approval that was never asked about it. The distinction is not a preference: merging
an agent's branch is the defect this product has already recorded once, at its highest severity.

What is merged SHALL be a commit rather than a branch, so that what reached the main branch is a
fact stated in the integration record and not a name whose meaning changes as work continues. The
commit SHALL be the one the task's branch names at the moment the merge is attempted, and the system
SHALL report every other commit that reached the main branch alongside it, exactly as it does for a
commit named by evidence.

**Where the task has no branch of its own, nothing SHALL be merged and the reason SHALL say so.** A
task whose turns ran in a shared per-agent checkout, a task worked only by an agent that may not
write, and a task in a project that is not a repository all reach approval with no branch of their
own. In each of them the work, if any, is on a branch that carries other tasks, and the system SHALL
NOT substitute it. Approval SHALL still succeed.

Where the commit the task's branch names is already reachable from the main branch, the system SHALL
record that it was already there rather than recording a merge, on the same terms it does for a
commit named by evidence.

Before approval is granted, the system SHALL test the commit it would merge for conflicts with the
main branch on the same terms it tests a commit named by evidence, and SHALL refuse approval where it
would not merge cleanly. Work reaching the main branch by this route SHALL NOT be the one route that
was never checked first.

Where evidence governs a task, this requirement SHALL NOT apply to it, and evidence remains the only
thing that names what is merged. Evidence governs a task whose loop declares that its work needs
evidence, a task belonging to no loop at all, and — by the default stated in `agent-loops` — a task
whose loop declares a specification document, and a task that is linked to a requirement, where
neither has had a declaration made about it either way. **A task belonging to a flow SHALL NOT have
its branch merged in place of the commit its accepted evidence names**, because a flow that made no
declaration has not thereby asked to stop being governed by the requirements it decomposed. **Nor
SHALL a task that is linked to a requirement**, for the same reason and one that is sharper: such a
task's integration already merges what its accepted evidence names, including evidence another task
recorded against a requirement they share, and no branch of this task's own can carry that commit.

So this requirement applies to a task on a loop that declares no specification document, that is
linked to no requirement, and about which no declaration was made — the task for which no evidence
can ever name a commit — and to any task whose loop declared that its work needs no evidence.

#### Scenario: A task linked to a requirement is unaffected by this requirement

- **WHEN** a task on a loop that declares no specification document, and about which no declaration
  was made, is linked to a requirement and is approved with accepted evidence naming a commit
- **THEN** the commit that evidence names is what is merged
- **AND** the tip of that task's own branch is not merged in its place

#### Scenario: A flow's task is unaffected by this requirement

- **WHEN** a task belonging to a loop that declares a specification document, and that has made no
  declaration about evidence, is approved with accepted evidence naming a commit
- **THEN** the commit that evidence names is what is merged
- **AND** the tip of that task's own branch is not merged in its place

#### Scenario: An approved task on an evidence-free loop merges its own branch

- **WHEN** a task belonging to a loop that declares its work needs no evidence is approved, in a
  project with a configured main branch
- **THEN** the commit at the tip of that task's own branch is merged into the main branch
- **AND** the integration record names that commit and that branch

#### Scenario: An agent's branch is never the substitute

- **WHEN** such a task is approved and has no branch of its own
- **THEN** the approval succeeds
- **AND** nothing is merged
- **AND** the recorded reason states that the task has no branch of its own
- **AND** no branch belonging to an agent is merged

#### Scenario: A conflicting branch refuses approval on an evidence-free loop

- **WHEN** approval is requested for such a task whose branch tip would not merge cleanly into the
  main branch
- **THEN** the transition is refused
- **AND** the refusal names the conflicting paths
- **AND** no merge is attempted

#### Scenario: A task branch already in the main branch records that, not a merge

- **WHEN** such a task is approved and its branch tip is already reachable from the main branch
- **THEN** no merge is recorded
- **AND** the record states that the commit was already there

## MODIFIED Requirements

### Requirement: An integration that cannot proceed does not block approval

The transition into `approved` SHALL still succeed where integration cannot be attempted, and the integration SHALL be recorded as skipped together with the reason. Integration cannot be attempted when the project has no configured main branch, when the project's working directory cannot be resolved, when the project is not a repository, when the primary checkout has uncommitted changes to tracked files, when the primary checkout is not on the main branch, when evidence governs the task and no accepted evidence for it names a commit to merge and no evidence awaiting review names one either, or when evidence does not govern the task and the task has no branch of its own.

Two of those were enumerated for the first time by `approval-refuses-unaccepted-evidence`. An
unresolvable working directory had always been skipped this way and was simply missing from the list;
it was added because that change argues from the list being closed, and an argument from a list that
is not actually closed is worth nothing.

The evidence clause carries a second clause of its own, so that this requirement's normative sentence
does not say approval succeeds in precisely the case the refusal requirement says it is refused. A
reconciliation that lives only in explanatory prose is not a reconciliation; the two SHALLs have to
agree on their own terms.

**This change qualifies that clause with "where evidence governs the task", and adds the sixth
entry.** Both halves are the same correction: the old sentence assumed evidence is the only thing
that can name what to merge, which was true of every task when it was written and is no longer true
of a task on a loop that declares its work needs no evidence. Such a task with no accepted evidence
is not a task with nothing to merge — its branch is what merges — so leaving the clause unqualified
would excuse a skip in exactly the case this change exists to end. The sixth entry is the case that
genuinely remains: no evidence governs the task and it has no branch either, so there is no commit
this system is willing to name.

So what remains in this list is the task that genuinely produced no commit anyone is waiting to
accept: work whose evidence records paths, work whose evidence was rejected, work that produced no
evidence at all on a loop where evidence governs, and work with no branch of its own on a loop where
it does not. Work recorded but not yet judged is refused at approval rather than skipped after it, so
it never reaches this list. For those that do, nothing being merged is the true account rather than a
gap, and blocking approval would block work the product supports.

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

#### Scenario: A task with no evidence governing it and no branch approves and merges nothing

- **WHEN** a task on a loop that declares its work needs no evidence is approved and has no branch of
  its own
- **THEN** the approval succeeds
- **AND** the skipped integration is recorded, naming the absence of a branch

### Requirement: An integration that was skipped can be attempted again

The system SHALL offer a way to attempt integration again for an approved task whose work has not been integrated, and SHALL offer it only where attempting it again could change the outcome.

Integration is attempted when a task becomes approved. Where it is skipped, the cause is often
something the operator can then put right — a checkout with uncommitted changes, a checkout parked on
another branch. Restating the approval does not attempt it again, because restating a status is
deliberately a no-op, so without this the remediation the system asked for accomplishes nothing.

A skip SHALL NOT instruct the operator to approve the task again. The task is already approved by the
time the skip is read, and following that instruction provably does nothing: the request succeeds,
the status is unchanged, no attempt is recorded, and nothing is merged. An instruction that fails
silently is worse than none, because it spends the operator's confidence as well as their time.

Where a skip names a cause the operator can put right, it SHALL point at the remedy that works —
retrying the integration, or the setting whose absence caused the skip.

**Whether retrying can change the outcome SHALL be decided by the same component that produces the
reason, and SHALL be carried on the record of the attempt wherever that record is read.** A surface that offers the retry SHALL read that answer
rather than deriving one from the wording of the reason. A reason is a sentence written for a person;
deriving behaviour from its text means every new reason is offered a retry by default, including the
ones that are terminal, and the surface making the offer is the one place that cannot know which is
which.

**A skip whose cause a retry cannot clear SHALL NOT be offered one.** A retry offered on a cause
nothing has changed re-runs the same question, receives the same answer, and appends a second record
identical to the first: the operator is told to act, acts, and observes nothing happen. That is the
same failure as instructing them to approve again, reached by a different route. Where the cause is
something the operator can put right somewhere else, the skip SHALL point there instead.

Retrying SHALL be available to the operator and to agents, and SHALL be refused for a task that is
not approved. This requirement constrains what is **offered**, not what is permitted: a retry
requested directly SHALL still be attempted and recorded, whatever the previous reason was, because
the world may have moved in a way no classification made at the time of the skip could know about.

#### Scenario: A retryable skip offers the retry

- **WHEN** an approved task's integration was skipped because the primary checkout had uncommitted
  changes
- **THEN** the record marks the attempt as one worth repeating
- **AND** the operator is offered a way to attempt it again

#### Scenario: A terminal skip offers no retry

- **WHEN** an approved task's integration was skipped because there was nothing to merge, or because
  the task has no branch of its own, or because the commit was already in the main branch
- **THEN** the record marks the attempt as one repeating cannot change
- **AND** no retry is offered for it

#### Scenario: A missing main branch points at the setting

- **WHEN** an approved task's integration was skipped for want of a configured main branch
- **THEN** no retry is offered
- **AND** the operator is pointed at the setting, whose saving attempts the integration

#### Scenario: A retry requested directly is attempted whatever the reason was

- **WHEN** a retry is requested for an approved task whose last skip was one no retry is offered for
- **THEN** the integration is attempted
- **AND** its outcome is recorded
