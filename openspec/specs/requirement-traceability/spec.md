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

A retired requirement with no linked work SHALL be reported as retired rather than unserved: the
lowest tier means somebody should be building it, which is the one thing a retired requirement does
not ask for. Its rank is unchanged, and a retired requirement with evidence or linked work reports
what that evidence or work says.

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

#### Scenario: A retired requirement nothing serves is retired, not unserved

- **WHEN** a requirement is retired from its document and no task is linked to it
- **THEN** its coverage state is retired, never unserved

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

### Requirement: Evidence is decided only after the run that recorded it has ended

The Hub SHALL refuse to accept or reject a piece of evidence while the run that recorded it is still executing, and the refusal SHALL say that it clears when that run ends and that stopping that run ends it.

An agent records evidence while its work is uncommitted, and the Hub re-points the evidence at the
commit holding the work when the run ends. A decision taken before then judges a commit the Hub is
about to replace, and the decision's reason then disagrees with the row it is recorded on.

The refusal SHALL apply to the operator and to a granted agent alike. It SHALL NOT be answered as a
lack of permission: it is a conflict that clears on its own. Where the Hub cannot tell that the run
is executing — including a run left marked running by a Hub that stopped — the decision SHALL be
allowed.

A view of a piece of evidence SHALL say whether the run that recorded it is still executing, so a
screen can hold its decision instead of offering one the Hub will refuse.

Where the same run records the same demonstration again — same requirement, task, actor and commit —
while its earlier piece is still undecided, the Hub SHALL revise that piece rather than refuse the
second. The revision SHALL keep the piece's identity, SHALL say it was a revision, and SHALL take the
time of the revision as the time the piece was recorded, because it is the most recent recording of
that demonstration and whatever picks the most recent piece must pick it. A piece
recorded against an earlier wording of the requirement SHALL NOT be revised onto the current one.

A refusal of a duplicate recorded by an agent SHALL NOT tell the agent to commit its work, because
the agent is told the Hub commits it. Where the agent's checkout is one the Hub commits when the run ends and holds uncommitted changes, a piece
matching an earlier run's piece at the same commit SHALL be recorded rather than refused, because the
Hub re-points it at the commit holding those changes when the run ends.

#### Scenario: A decision during the recording run is refused

- **WHEN** the operator or a granted agent decides a piece of evidence whose recording run is still executing
- **THEN** the decision is refused as a conflict that names the run
- **AND** the refusal says that stopping the run ends it
- **AND** no review is recorded and the piece stays awaiting

#### Scenario: The same decision after the run ends is recorded

- **WHEN** the recording run has ended and its evidence has been re-pointed
- **THEN** the same decision is accepted and recorded against the re-pointed commit

#### Scenario: A run the Hub is not executing does not hold a decision

- **WHEN** the recording run is marked running but the Hub is not executing it
- **THEN** the decision is accepted

#### Scenario: The view says the run is still going

- **WHEN** a piece of evidence is read while its recording run is executing
- **THEN** the view says so

#### Scenario: A re-record in the same run revises the undecided piece

- **WHEN** a run records evidence for a requirement and task, then records it again in the same run before anything is committed
- **THEN** the first piece is revised with the second's summary and locator
- **AND** its recorded time is the time of the revision
- **AND** no second piece exists and nothing is refused

#### Scenario: An agent's duplicate refusal does not ask for a commit

- **WHEN** an agent's evidence is refused as a duplicate of a piece an earlier run recorded
- **THEN** the refusal does not tell the agent to commit its work

#### Scenario: A changed checkout re-records across runs

- **WHEN** an agent's new run records evidence matching a piece its earlier run recorded at the same commit, in a task or agent checkout the Hub commits at the end of the run, and that checkout holds uncommitted changes
- **THEN** the new piece is recorded and not refused

#### Scenario: A second record in a new turn revises that turn's own piece

- **WHEN** an agent's new run, with uncommitted changes, records a piece matching its earlier run's piece at the same commit and then records the same demonstration again in the same run
- **THEN** the new run's piece is revised
- **AND** exactly two pieces exist, one per run

### Requirement: An agent held from a decision is told when it can decide

The Hub SHALL tell an agent whose decision was refused because the recording run was still executing, once that run has ended, that the pieces it tried to decide can now be decided.

A refused agent's turn ends on the refusal, and nothing else would bring it back: an agent is often
woken to review work while the author's run is still going, and without this the refusal turns a
premature decision into a missing one. The note SHALL be queued to that agent like any other input,
in the conversation the refusal happened in, SHALL name each piece and the commit it names after the
run ended, and SHALL be sent once per ended run. The note SHALL come from the Hub, not from the
operator or an agent. It SHALL NOT be sent before the Hub has stopped counting the run as executing,
so a decision the note prompts is not refused again. A piece decided by someone else in the meantime
SHALL be left out of the note, and where none is left no note SHALL be sent.

Where the Hub restarted while the agent waited, the Hub SHALL NOT be required to send the note: after
a restart the run is no longer executing and the decision is already open.

#### Scenario: A refused reviewer is told when the run ends

- **WHEN** an agent's decision is refused because the recording run is executing, and that run then ends
- **THEN** the agent has one queued input from the Hub, in the conversation it was refused in, naming the piece and the commit it now names
- **AND** deciding the piece in the turn that input starts is recorded

#### Scenario: A piece decided in the meantime is not re-announced

- **WHEN** an agent's decision is refused while the run is executing, and the operator decides the piece after the run ends and before the agent's note is queued
- **THEN** no note naming that piece is queued

#### Scenario: The operator is not queued a note

- **WHEN** the operator's decision is refused because the recording run is executing, and that run then ends
- **THEN** nothing is queued for any agent on the operator's account

### Requirement: A decision is answered as recorded even when the merge it triggers fails

The Hub SHALL answer an accepted or rejected decision with the decision it recorded, even when integrating the work that was waiting for that decision fails.

Accepting evidence may merge an approved task's waiting work, and a repository failure there is
recorded as a skip rather than undoing the decision. The response SHALL NOT turn that failure into
a server error, because the decision stands and a client told otherwise would show a failure for a
decision that was made.

#### Scenario: An integration failure after accepting still answers the decision

- **WHEN** the operator or a granted agent accepts a piece of evidence that an approved task was waiting for, and integrating that task fails
- **THEN** the response reports the piece as accepted
- **AND** the stored piece reads accepted

### Requirement: The screen that says evidence awaits a decision can take it

Where the operator's coverage view reports that a requirement's evidence awaits a decision, the same view SHALL let the operator read each piece of that evidence and accept or reject it.

A screen that tells the operator a judgement is theirs and offers no way to make it leaves the
decision to a direct HTTP client, and accepted evidence is what approval merges.

Each piece SHALL be shown with what the operator needs to judge it: its summary, who recorded it,
its locator, the commit and branch its footprint names, the task it came from, its state, and for a
decided piece the latest decision's reason. Pieces SHALL be listed in the order the Hub records
them, with the most recently recorded marked. The mark SHALL NOT claim that piece is the one a
merge takes, because a merge is decided per task and per line of work, not per requirement.

Where accepting a piece can merge its commit into the main branch, the piece SHALL say so beside the
accept action, before the operator takes it: accepting evidence merges the work of an approved task
that was waiting for it, and a decision that can change the main branch must not look like a label.

A rejection SHALL carry a reason.

A refusal from the Hub SHALL be shown beside the piece it refused, in the Hub's words.

A decision SHALL be announced to every open view of the project, so coverage and the task board
reflect it without a reload. When a run that recorded evidence ends, that SHALL be announced too,
after the Hub has stopped counting the run as live, so a piece shown as still being recorded
becomes decidable without a reload.

#### Scenario: An awaiting piece can be accepted from the coverage view

- **WHEN** the operator opens a requirement in the coverage view whose evidence awaits a decision
- **THEN** each piece is listed with its summary, recorder, commit and branch
- **AND** accepting one records the operator's decision and the requirement's coverage updates

#### Scenario: A rejection needs a reason

- **WHEN** the operator rejects a piece without giving a reason
- **THEN** the rejection is not sent

#### Scenario: A refused decision says why

- **WHEN** the Hub refuses a decision
- **THEN** the Hub's sentence is shown beside that piece and its state is unchanged

#### Scenario: Another open view learns of the decision

- **WHEN** a piece of evidence is decided by the operator or by a granted agent
- **THEN** every open view of that project's coverage refreshes

#### Scenario: Accept says it may merge into main

- **WHEN** a piece awaiting a decision names a commit
- **THEN** the view states beside Accept that accepting may merge that commit into the main branch for an approved task waiting on it

#### Scenario: A piece still being recorded becomes decidable when its run ends

- **WHEN** the operator is viewing a piece shown as still being recorded, and the run that recorded it ends
- **THEN** the view refreshes without a reload and the piece can be decided
