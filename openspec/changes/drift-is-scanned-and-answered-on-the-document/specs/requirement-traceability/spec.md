## MODIFIED Requirements

### Requirement: A changed implementation raises a candidate, never an edit

Where evidence is recorded, the Hub SHALL capture the implementation footprint it was produced
against: in a git repository, the commit and the changed blob identifiers; where the project is not
a repository, the changed paths and a content hash of each. Both SHALL be supported, because a
project without a repository is a supported first-class case and would otherwise be permanently
unverifiable.

**Which tree is described is decided by what the recorder named, not by where they are standing.**
An agent's footprint SHALL be taken from its own working checkout, whose content is the work in
progress and which a later re-stamp corrects once that work is committed. An operator's footprint
SHALL be taken from the commit their locator names where it names one, and from their own checkout
otherwise; where a named commit is not present in the repository the recording SHALL be refused
rather than footprinted against the checkout. A locator counts as naming a commit only when it is a
bare git object name — a locator is otherwise a path, and reading paths as revisions would be a
guess with a refusal attached to it.

A footprint that silently describes a tree other than the one named is worse than absent evidence,
because review and integration both act on it: a review turn is checked out to the footprinted
commit, and integration merges on whether that commit is reachable from the main branch.

Where a footprint is captured, the response to the recording SHALL report it, so the recorder can
see which tree their evidence was attached to at the moment they can still correct it.

A later change to a linked footprint, with no new requirement revision and no explicit resolution,
SHALL raise a drift candidate.

The Hub SHALL NOT edit a specification document in response to drift. That an implementation changed
is observable; that a requirement *should* change is a judgement, and inferring it would rewrite an
approved specification on the strength of a file diff.

An operator SHALL resolve a candidate as specification updated, implementation corrected, or no
specification change required. The resolution SHALL record the digest current at that moment. A
resolution of specification updated or no specification change required SHALL also record the
fingerprint current at that moment, so the same change is not reported again. A resolution of
implementation corrected SHALL NOT record a fingerprint: its claim is that the implementation was
put back, so the same change still present at a later scan, or returning after it, is drift again. A
resolution that silenced the change it claims was undone would turn a mistaken or premature answer
into a permanent blind spot.

Overlap between a footprint and a later change is a candidate signal, not proof of divergence.

**A footprint SHALL report where the run that produced it wrote outside the directory the footprint
was taken from.** A run's writes are not confined to its workspace — that boundary is a working
directory, not a wall — so a footprint taken there can describe a tree missing part of the very work
it is offered as evidence of. That is the failure the paragraph above already names as worse than
absent evidence, arriving without anyone having named the wrong tree.

The footprint SHALL NOT be moved to the other tree. There may be several, one of them may be the
operator's own checkout sitting on unrelated work, and choosing one would be that same failure with a
choice attached to it. The evidence SHALL NOT be refused either: an observation must not become a
gate. What changes is only that the footprint stops implying a completeness it cannot have.

#### Scenario: A changed footprint is noticed

- **WHEN** a file named in a requirement's evidence footprint changes and the requirement does not
- **THEN** a drift candidate exists for that requirement

#### Scenario: A project without a repository still records a footprint

- **WHEN** evidence is recorded in a project that is not a git repository
- **THEN** the footprint names the changed paths and a content hash of each
- **AND** a later change to one of them raises a drift candidate

#### Scenario: The footprint describes the commit the recorder named

- **WHEN** an operator records evidence whose locator names a commit in the project's repository
- **THEN** the footprint names that commit, its tree, and whether it is reachable from the main
  branch
- **AND** it does not name the commit the operator's own checkout is on

#### Scenario: A locator naming an absent commit is refused

- **WHEN** an operator records evidence whose locator names a commit the repository does not have
- **THEN** the request is refused
- **AND** no evidence and no footprint are recorded

#### Scenario: A locator that is not a commit leaves the footprint alone

- **WHEN** an operator records evidence whose locator is a path rather than a git object name
- **THEN** the footprint is taken from the operator's own checkout

#### Scenario: An agent's locator does not move its footprint

- **WHEN** an agent records evidence whose locator names a commit
- **THEN** the footprint is still taken from the agent's own working checkout

#### Scenario: Recording evidence reports the footprint it captured

- **WHEN** evidence is recorded and a footprint is captured for it
- **THEN** the response describing that evidence reports the footprint

#### Scenario: Drift never rewrites the document

- **WHEN** a drift candidate is raised
- **THEN** the specification document is unchanged

#### Scenario: A resolved candidate does not return

- **WHEN** an operator resolves a drift candidate as no specification change required
- **THEN** the same change does not raise the candidate again

#### Scenario: A correction that did not happen is asked again

- **WHEN** an operator resolves a drift candidate as implementation corrected
- **AND** the same change is still present when drift is next scanned
- **THEN** a new drift candidate is raised for it

#### Scenario: Evidence from a run that wrote outside its workspace says so

- **WHEN** evidence is recorded by a run that wrote outside the directory its footprint is taken from
- **THEN** the footprint reports that the run wrote outside it
- **AND** the footprint still describes the directory it was taken from

#### Scenario: An outside write does not move the footprint

- **WHEN** a run wrote into a directory other than the one its footprint is taken from
- **THEN** the footprint is not taken from that other directory

#### Scenario: An outside write does not refuse the evidence

- **WHEN** a run that wrote outside its workspace records evidence
- **THEN** the evidence is recorded
- **AND** the recording is not refused for having written outside

## ADDED Requirements

### Requirement: Drift is raised and answered where the operator reads the requirement

The operator's view of a specification document SHALL offer a scan for drift, SHALL show that document's open drift candidates, and SHALL let the operator answer each one there.

A state whose remedy cannot be performed on the surface that shows it is a defect even when the
state is correct. The coverage of a document already reports *drifting* and the approval gate
already names answering the candidate as the way through; both SHALL be performable without an
HTTP client.

Raising and answering SHALL ship together. A scan with no way to answer would make one call enough to
leave a `gate` requirement permanently unapprovable, because a scan never raises the same question
twice and so cannot undo itself.

Each candidate SHALL be shown with the requirement's identifier, the files that moved, and the
evidence that had been verified. A candidate SHALL be answered once: an answer to a candidate that is
no longer open SHALL be refused, naming the answer it already has. Scanning and answering SHALL be
announced to every open view of the project.

The approval gate's refusal for a drifting requirement SHALL say that the operator answers it and
where, and that an agent cannot.

#### Scenario: The operator scans from the document

- **WHEN** the operator scans for drift from a document's view
- **THEN** the scan runs across the project
- **AND** the view reports how many candidates were raised, and how many belong to this document

#### Scenario: A candidate is answered where it is shown

- **WHEN** a document has an open drift candidate
- **THEN** its view shows the requirement's identifier, the files that moved and the evidence that
  was verified
- **AND** the operator can answer it as specification updated, implementation corrected, or no change
  required

#### Scenario: Answering clears drifting

- **WHEN** the operator answers the only open candidate for a requirement
- **THEN** the requirement no longer reports drifting in that view or in any other open view

#### Scenario: A candidate is not answered twice

- **WHEN** an answer is submitted for a candidate that has already been answered
- **THEN** it is refused
- **AND** the refusal names the answer already recorded
- **AND** the recorded answer is unchanged

#### Scenario: The gate's remedy names who can perform it

- **WHEN** approval is refused because a gated requirement is drifting
- **THEN** the refusal says that the operator answers the drift candidate on the document
- **AND** it says that an agent cannot answer it
