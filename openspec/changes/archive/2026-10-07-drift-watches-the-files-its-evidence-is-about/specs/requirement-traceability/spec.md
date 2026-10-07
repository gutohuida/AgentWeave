## ADDED Requirements

### Requirement: A footprint watches the files its evidence is about

A footprint SHALL record, for drift, only the files its evidence is about, taken from the first of these that names any file: the paths its locator names that exist in the tree, the files changed by the commit an operator's locator names, and the files changed on its line of work since that line left the main line.

The sources are tried **in order**, not combined: combined, every agent row would watch its task's
whole diff whatever its locator names, and one commit to a shared file would still raise a candidate
for most rows (measured 2026-09-24: 22 of 46 accepted rows on the operator's instance). A locator is
read as the words it is made of, and only a word that is a path, or a directory holding paths, in the
footprinted tree counts; nothing is guessed from a word that is not in the tree.

A footprint that recorded the whole tree would make one commit to any file a drift candidate for
every piece of evidence on that branch. The question drift asks — *which one was wrong?* — is then
asked about work nobody touched, and a feature that asks it forty times for one commit is switched
off.

A footprint that can name no such file SHALL watch nothing, and SHALL say so: the footprint reports
where what it watches came from, and a list of accepted evidence that watches nothing SHALL be
available together with the reason. Recording evidence SHALL NOT be refused because it watches
nothing.

A footprint recorded before the footprint recorded what it watches SHALL be rebuilt, where its
commit's merge into the main line can be found, from the locator and the files that merge brought in
(measured 2026-09-24: 42 of 46 accepted rows); one that cannot be rebuilt SHALL NOT be scanned, and
SHALL be listed as watching nothing for that reason. A footprint rebuilt from its locator SHALL keep
the commit it was verified at as its baseline; one rebuilt from its merge SHALL take the main line as
it stands when it is rebuilt, so that its first scan does not ask about every file that merge brought
in that anyone has touched since (F525: 19 of 28 rows on the trial instance, mostly ledgers and logs).

#### Scenario: A change to a file the evidence is not about raises nothing

- **WHEN** evidence whose locator names one file is accepted
- **AND** a later commit changes only a different file
- **THEN** no drift candidate is raised for that evidence

#### Scenario: A change to the named file raises a candidate

- **WHEN** evidence whose locator names one file is accepted
- **AND** a later commit on the line of work it is compared against changes that file
- **THEN** a drift candidate is raised naming that file

#### Scenario: Work on a branch is watched by what it changed

- **WHEN** an agent's evidence is footprinted at a commit that is not yet on the main line
- **THEN** the footprint watches the files changed between the point that line left the main line
  and that commit

#### Scenario: Evidence that names nothing is listed, not silently ignored

- **WHEN** accepted evidence names no file and no commit, and its work changed nothing off the main
  line
- **THEN** it watches nothing
- **AND** it appears in the list of unwatched evidence with the reason that it names no file

#### Scenario: A locator naming a file narrows agent evidence

- **WHEN** an agent's evidence names one file of the several its task branch changed
- **THEN** the footprint watches that file only, and not the rest of the branch's changes

#### Scenario: Prose in a locator counts only where it names files in the tree

- **WHEN** a locator reads `src/engine.js (Engine.currentRun); test/engine.test.js`
- **THEN** the footprint watches `src/engine.js` and `test/engine.test.js`, which exist in the tree, and nothing for the other words

#### Scenario: Evidence recorded before watching is rebuilt where it can be

- **WHEN** accepted evidence recorded before footprints recorded what they watch has a commit whose merge into the main line can be found
- **THEN** its footprint is rebuilt to watch the files its locator names, or else the files that merge brought in
- **AND** a footprint rebuilt from its merge raises nothing for a change made before it was rebuilt
- **AND** evidence whose merge cannot be found is listed as recorded before watching

#### Scenario: Agent evidence recorded mid-turn is narrowed when its run ends

- **WHEN** an agent records evidence with its work uncommitted, and its run ends and is snapshotted
- **THEN** the re-stamped footprint records where its watched files came from, and is scanned

#### Scenario: The recorder sees what is watched

- **WHEN** evidence is recorded and a footprint is captured
- **THEN** the response reports where the watched files came from and how many there are

## MODIFIED Requirements

### Requirement: A changed implementation raises a candidate, never an edit

Where evidence is recorded, the Hub SHALL capture the implementation footprint it was produced
against: in a git repository, the commit and the blob identifiers of the files the evidence is
about; where the project is not a repository, those paths and a content hash of each. Both SHALL be supported, because a
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
see which tree their evidence was attached to at the moment they can still correct it. An agent's
footprint taken before its run's work is committed SHALL be reported as provisional until the run
ends.

A later change to a file a linked footprint watches, with no new requirement revision and no
explicit resolution, SHALL raise a drift candidate. A footprint that watches nothing -- it names no
file, or it was recorded before footprints recorded what they watch and could not be rebuilt -- SHALL
NOT be scanned, and SHALL be listed as unwatched with its reason instead.

The Hub SHALL NOT edit a specification document in response to drift. That an implementation changed
is observable; that a requirement *should* change is a judgement, and inferring it would rewrite an
approved specification on the strength of a file diff.

An operator SHALL resolve a candidate as specification updated, implementation corrected, or no
specification change required. The resolution SHALL record the digest and fingerprint current at that
moment, so the same change is not reported again.

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

- **WHEN** a file a requirement's evidence footprint watches changes and the requirement does not
- **THEN** a drift candidate exists for that requirement

#### Scenario: A footprint that watches nothing is listed, not scanned

- **WHEN** accepted evidence's footprint watches nothing
- **THEN** no drift candidate is raised for it
- **AND** it is listed as unwatched with its reason

#### Scenario: A project without a repository still records a footprint

- **WHEN** evidence is recorded in a project that is not a git repository
- **THEN** the footprint names the paths the evidence is about and a content hash of each
- **AND** a later change to one of them raises a drift candidate

#### Scenario: The footprint describes the commit the recorder named

- **WHEN** an operator records evidence whose locator names a commit in the project's repository
- **THEN** the footprint names that commit, the files it watches there, and whether it is
  reachable from the main branch
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
- **THEN** the response describing that evidence reports the footprint, and marks it provisional
  when an agent's footprint was taken mid-turn

#### Scenario: Drift never rewrites the document

- **WHEN** a drift candidate is raised
- **THEN** the specification document is unchanged

#### Scenario: A resolved candidate does not return

- **WHEN** an operator resolves a drift candidate
- **THEN** the same change does not raise the candidate again

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
