# requirement-traceability Specification

## Purpose
TBD - created by archiving change 2026-08-13-a-requirement-knows-its-work. Update Purpose after archive.
## Requirements
### Requirement: A requirement is addressable outside its document

The Hub SHALL maintain an index of the requirements a project's specification documents declare,
keyed by the stable identifier the Hub mints, so that other records can point at a requirement
without copying its wording.

The index SHALL be derived from the documents and SHALL NOT be authoritative. It SHALL be
reconstructible from the files alone, and it SHALL NOT hold wording that is not in a document.

Each indexed requirement SHALL carry its stable identifier, the document declaring it, whether it is
active or retired, its current semantic digest, and where it sits in the rendered document.

An identifier SHALL be unique within the document that declares it. Identifiers are minted per
document, so the same identifier names a different requirement in a different document; a record
pointing at a requirement SHALL therefore point at the indexed requirement itself rather than at its
identifier as text. Where an identifier is supplied by name and more than one document in the project
declares it, resolution SHALL be refused as ambiguous rather than resolved to either — choosing one
would link work to a requirement nobody named, and being wrong would be invisible until someone read
both documents.

The semantic digest SHALL be computed from one definition used by every surface, and SHALL cover what
a reader must satisfy: the obligation, the statement, the side of the boundary it binds, and the
criteria demonstrating it. It SHALL NOT cover explanatory prose. The canonicalization producing it
SHALL be recorded with each digest, so a digest taken under an earlier rule is distinguishable from a
rewording.

A requirement that is removed from its document SHALL become retired rather than disappear. Work and
evidence already pointing at it remain pointed at it — what a retired requirement once demanded, and
what was built for it, is a question that outlives the requirement.

Each change of a requirement's semantic digest SHALL be recorded append-only with the digest before,
the digest after, whether the change arrived through the Hub or from an external edit, and the actor.

#### Scenario: A saved document populates the index

- **WHEN** a specification document is saved with requirements
- **THEN** each requirement is indexed under its stable identifier with its current digest

#### Scenario: The index is rebuildable

- **WHEN** the index is discarded and rebuilt from the project's documents
- **THEN** it describes the same requirements, identifiers and digests as before

#### Scenario: A removed requirement is retired, not deleted

- **WHEN** a requirement is removed from its document
- **THEN** it is marked retired
- **AND** records pointing at it still resolve

#### Scenario: A reworded requirement records the change

- **WHEN** a requirement's statement changes so its semantic digest changes
- **THEN** the previous and current digests are recorded with the actor who caused the change

#### Scenario: A changed obligation is a changed requirement

- **WHEN** a requirement's modal changes and its statement does not
- **THEN** its semantic digest changes

#### Scenario: A reworded rationale is not a changed requirement

- **WHEN** only a requirement's rationale changes
- **THEN** its semantic digest is unchanged

#### Scenario: An identifier naming two documents is refused

- **WHEN** work names an identifier that more than one of the project's documents declares
- **THEN** resolution is refused as ambiguous rather than resolved to one of them

### Requirement: Work is linked to the requirements it serves

A task SHALL be linked to the requirements it serves by reference, not by copied text.

A free-text list naming requirements cannot be joined, cannot be checked, and does not notice when
the requirement it names is reworded or retired. Observed in a live run: a task carried
`"FR-8 — initialize-members"` as a string, and nothing in the system could answer whether FR-8 had a
task, whether it had changed since, or whether anything had verified it. The agent building that task
could not read the specification at all and worked from that copied string, which made it the
contract in practice.

A link SHALL record which actor created it and, where an agent did, the run.

Links SHALL NOT be removed when a task reaches a terminal state. What work served a requirement is
asked mostly about finished work.

Where existing tasks carry legacy free-text references, migration SHALL convert those that resolve
to a requirement in the same project into links, and SHALL preserve the remainder verbatim as
unresolved references. It SHALL NOT discard a value it cannot interpret, and SHALL NOT create a
requirement to match one.

#### Scenario: A task names the requirements it serves

- **WHEN** a task is created naming requirement identifiers
- **THEN** a link exists from that task to each named requirement

#### Scenario: Links survive completion

- **WHEN** a linked task reaches a terminal status
- **THEN** its links remain

#### Scenario: A recognizable legacy reference becomes a link

- **WHEN** a task carries a legacy reference naming an identifier that exists in its project
- **THEN** migration creates a link to that requirement

#### Scenario: An uninterpretable legacy reference is kept, not dropped

- **WHEN** a task carries a legacy reference that resolves to no requirement
- **THEN** it is preserved as an unresolved reference with its original text
- **AND** no requirement is created for it

### Requirement: Evidence names what produced it and what it was produced against

Evidence for a requirement SHALL record its kind, the location of its artifact, the actor that
produced it, the run where an agent produced it, and **the requirement digest it was produced
against**.

Evidence SHALL be whatever demonstrates the work — a test run, a screenshot, a diff, a path. The set
of kinds SHALL be open to additions, because constraining evidence to what was imaginable at design
time is how the record stops describing what was actually done.

Pinning evidence to a digest rather than to a requirement is what makes staleness detectable:
evidence accepted against one wording says nothing about a different wording, and without the pin
the difference is unobservable after the fact.

Evidence SHALL be stored as an artifact in the project's own directory, with the record holding its
location rather than its content. An operator SHALL be able to read, move and archive evidence with
ordinary tools, and the database SHALL NOT become an artifact store.

Retention SHALL be a project policy with `never` among its choices. Removing an artifact SHALL NOT
remove its evidence record: that something was verified, by whom, and against which digest is the
record, and the artifact is its attachment. A record whose artifact is gone SHALL report that state
rather than disappear.

**An agent's assertion SHALL NOT by itself constitute evidence.** A run reporting that it verified
something produces a record awaiting review, not a verified requirement. A live run produced an
agent that correctly reported its work as unverified-by-execution; a less careful one would have
reported success in the same words with the same authority, and the record must be able to tell them
apart. What distinguishes them is that the artifact is a fact and the claim about what it proves is
not — so producing evidence is open, and **accepting** it is the controlled act.

Acceptance and rejection SHALL be recorded append-only, attributed to the actor that decided, with
no update and no delete.

Evidence MAY be accepted by an agent the operator has granted that capability, and by the operator.
The capability SHALL be granted per agent by the operator; it SHALL NOT be conferred by a charter or
by anything an agent can assert about itself, because a charter describes behaviour and behaviour is
not authority.

**An agent SHALL NOT accept evidence it produced.** Distinctness is on agent identity, not run
identity — the same rule, for the same reason, that already governs task approval.

Where a project has granted no agent that capability, acceptance SHALL fall to the operator. That is
a supported way to work, not a degraded one.

#### Scenario: Evidence carries its actor and digest

- **WHEN** evidence is recorded for a requirement
- **THEN** it names its kind, its producing actor, and the requirement digest current at that moment

#### Scenario: An agent's report awaits review

- **WHEN** an agent records evidence for a requirement
- **THEN** that evidence is awaiting review rather than accepted

#### Scenario: A decision is attributed and kept

- **WHEN** evidence is accepted or rejected
- **THEN** the decision is appended with its actor's attribution and never overwritten

#### Scenario: A granted agent may accept evidence another agent produced

- **WHEN** an agent the operator granted the capability accepts evidence produced by a different
  agent
- **THEN** the acceptance is recorded with that agent as the actor

#### Scenario: An agent cannot accept its own evidence

- **WHEN** an agent attempts to accept evidence it produced
- **THEN** it is refused

#### Scenario: An ungranted agent cannot accept evidence

- **WHEN** an agent without the capability attempts to accept evidence
- **THEN** it is refused

#### Scenario: With no granted agent the operator decides

- **WHEN** a project has granted no agent the capability
- **THEN** evidence can still be accepted by the operator

#### Scenario: A removed artifact does not remove the record

- **WHEN** an evidence artifact is deleted under the project's retention policy
- **THEN** the evidence record remains and reports that its artifact is gone

### Requirement: Coverage is one computation with one precedence

The Hub SHALL compute a requirement's coverage state from a single definition, and every surface
reporting coverage SHALL use it.

Two implementations of "is this verified" disagree eventually, and the disagreement is invisible
until someone compares two screens.

The precedence, highest first, SHALL be: an unresolved drift record; evidence that no longer applies
to the current digest; current-digest evidence awaiting review; sufficient accepted current-digest
evidence; linked work in progress or completed without evidence; linked work not started; no linked
work at all.

A requirement that is structurally invalid or carries no identifier SHALL be reported as a
diagnostic outside coverage rather than assigned a coverage state. It is not unserved; it is broken.

A project SHALL be able to report, for a document, which of its requirements have no linked work.

Coverage SHALL also report whether the evidence's implementation footprint is reachable from the
project's main line of work, and **no surface reporting a coverage state may omit it**. Approved work
in this product currently remains on a per-agent branch that nothing merges, so a requirement can
hold accepted evidence for code that is not in the product. Reporting `verified` alone would be true
of the branch and false of the product; reporting both makes the gap visible where the work is, not
only to someone inspecting branches by hand.

Integration SHALL NOT be a coverage state. The precedence ranks how good the evidence is;
integration is an independent fact about the same evidence, and ranking them together would force a
choice between "stale but merged" and "verified but unmerged" that has no correct answer.

#### Scenario: A requirement nothing serves is reported as such

- **WHEN** a document has a requirement with no linked task
- **THEN** its coverage state is that no work is linked

#### Scenario: Evidence against an older wording is not verification

- **WHEN** a requirement has accepted evidence and its statement is then reworded
- **THEN** its coverage state reports the evidence as no longer applying

#### Scenario: Two surfaces agree

- **WHEN** a requirement's coverage is shown on its document and counted in a project total
- **THEN** both derive from the same computation

#### Scenario: Verified work that has not landed says so

- **WHEN** a requirement has accepted evidence whose footprint is not reachable from the project's
  main line of work
- **THEN** its coverage reports both that it is verified and that it is not integrated

#### Scenario: A coverage state is never shown without its integration answer

- **WHEN** any surface reports a coverage state
- **THEN** it also reports whether that evidence is integrated

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

### Requirement: A requirement and its work are navigable in both directions

From a requirement it SHALL be possible to reach the work linked to it and the evidence recorded for
it; from a task it SHALL be possible to reach the requirements it serves.

An agent recording evidence SHALL be identified by its run credential, never by a value it supplies.

#### Scenario: From a requirement to its work

- **WHEN** a requirement has linked tasks and evidence
- **THEN** both are reachable from it

#### Scenario: From a task to its requirements

- **WHEN** a task is linked to requirements
- **THEN** those requirements are reachable from it, with their current statements

#### Scenario: An agent cannot claim to be another actor

- **WHEN** an agent records evidence
- **THEN** the recorded actor is the one its run credential establishes

