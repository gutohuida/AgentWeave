## MODIFIED Requirements

### Requirement: Approval is refused when the work cannot be merged cleanly

Where the work to be integrated would conflict with the project's main branch, the system SHALL refuse the transition into `approved`, and the refusal SHALL name a remedy that the party it refuses can actually take.

The conflict SHALL be detected before the transition is recorded, by a test merge that modifies
neither the working tree nor the index. A conflict discovered during the merge itself would leave a
task recorded as approved and a repository in a state the operator did not ask for.

The refusal SHALL be carried in the same typed refusal that reports unverified requirements, and
SHALL name the conflicting paths. An operator learning that approval failed SHALL learn why in the
same response, not by inspecting the repository.

The refusal SHALL name the commit it judged. A conflict is a fact about one commit and the main
branch, not about a branch as a whole. A reader told only that "this task's work" conflicts cannot
check the claim, cannot tell which of a branch's commits was probed, and cannot tell whether a change
they have since made to that branch was seen at all.

**The remedy SHALL be determined by where the judged commit came from.** The system resolves what a
task's approval would merge in one of two ways, and an instruction that clears the refusal under one
of them does not clear it under the other:

- Where the commit is named by **accepted evidence**, resolving the conflict on the branch SHALL NOT
  be stated as the remedy. It does not clear the refusal: the resolution is a new commit that no
  evidence names, the system goes on judging the commit the evidence still names, and the answer
  cannot change however many times approval is retried. The remedy SHALL instead be to resolve the
  conflict, record evidence naming the resolved commit, and have that evidence accepted — and SHALL
  say that accepting is the operator's unless an agent has been granted it, in the same terms the
  refusal for unjudged evidence already uses.
- Where the commit is the task's **own branch tip**, resolving the conflict on the branch and
  approving again SHALL be stated as the remedy, because there the commit judged is whatever the
  branch then points at.

The remedy for the evidence route SHALL state which branch the fresh evidence must name, where the
system's choice of what to merge depends on it. A remedy that is followable only by accident is a
remedy that has not been stated.

Where the judged commit is **no longer present on the branch the refusal names it on**, the refusal
SHALL say so. That state is reached by rewriting the branch — the reasonable response to a remedy
that appeared not to work — and it is the state in which a reader comparing the refusal against the
repository finds the two disagree with no way to tell which is stale. Where the system cannot
determine whether the commit is on that branch, it SHALL say nothing rather than guess.

This refusal SHALL apply regardless of rigor. It is not an assertion about whether the work is
verified; it is an assertion that the work cannot go where approval says it goes.

The check SHALL live inside the single transition service, and SHALL NOT introduce a second
enforcement point.

#### Scenario: A conflicting branch refuses approval

- **WHEN** approval is requested for a task whose evidence commit conflicts with the main branch
- **THEN** the transition is refused
- **AND** the refusal names the conflicting paths
- **AND** the task's status is unchanged
- **AND** no merge is attempted

#### Scenario: A conflict refuses approval even at sketch rigor

- **WHEN** approval is requested for a task with conflicting work whose documents are all `sketch`
- **THEN** the transition is refused

#### Scenario: The refusal names the commit it judged

- **WHEN** approval is refused because the work would not merge cleanly
- **THEN** the refusal names the commit that was tested against the main branch
- **AND** it names it in the same sentence a reader is given, not only in the refusal's structured half

#### Scenario: An evidence-named commit is not answered with "resolve it on the branch"

- **WHEN** approval is refused for a task whose merge target came from accepted evidence
- **THEN** the refusal does not instruct the reader to resolve the conflict on the branch and approve again
- **AND** it instructs them to record evidence naming the resolved commit and have it accepted
- **AND** it states that accepting the evidence is the operator's, or a capability an agent must be granted

#### Scenario: Following the stated remedy clears the refusal

- **WHEN** the conflict is resolved, evidence naming the resolved commit is recorded and accepted, and approval is requested again
- **THEN** the transition is permitted
- **AND** the resolved commit is what integration merges

#### Scenario: A branch-tip commit is answered with the branch

- **WHEN** approval is refused for a task whose merge target is its own branch tip
- **THEN** the refusal instructs the reader to resolve the conflict on the branch and approve again
- **AND** approving after the branch is resolved is permitted, because the commit judged is the branch's new tip

#### Scenario: A judged commit that has left its branch is reported as such

- **WHEN** approval is refused over a commit that is no longer reachable from the branch the refusal names
- **THEN** the refusal says the commit is no longer on that branch

#### Scenario: An undeterminable branch is not asserted about

- **WHEN** the refusal cannot determine whether the judged commit is on the branch it names
- **THEN** it makes no claim either way
