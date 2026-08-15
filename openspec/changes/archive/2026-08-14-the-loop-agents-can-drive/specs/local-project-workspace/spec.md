# local-project-workspace

## MODIFIED Requirements

### Requirement: A project ignores what the system creates, in every checkout the system creates

The system SHALL ensure a project's version control ignores the working artefacts the system itself creates, and those rules SHALL apply in every checkout the system provisions, not only in the operator's own.

Agents commit what they find. Without this, the isolated checkouts, logs, captured evidence and
rendered turn context the system places in the project directory are committed by the first agent
that runs, and the operator inherits them in their own history having never chosen them.

The rules SHALL also cover build and dependency artefacts the system's own commit would otherwise
sweep in. The system commits an agent's working tree wholesale, so anything left lying there becomes
the system's commit — bytecode caches and installed dependency trees included. This is a narrower
claim than "artefacts of the project's language": it covers what the system writes into history, not
what the project's ecosystem produces, and that is the test for anything added later.

The rules SHALL take effect without the system committing to the operator's repository. Repairing a
mess the system made by adding a commit the operator did not ask for is a worse outcome than the
mess.

The system SHALL NOT untrack what is already committed. Ignore rules govern untracked paths; undoing
a commit already made would mean rewriting the operator's index unasked, and a repository the system
has already dirtied stays dirty until its owner says otherwise.

Seeding SHALL NOT be limited to registration. A project registered before a rule existed never
passes through registration again, and it is precisely the project whose agents have already been
committing the artefact; the rules SHALL therefore also be applied when the system resolves a
workspace for an agent.

Seeding SHALL be additive and SHALL NOT remove or reorder rules the operator already has. Ignore
rules are the operator's; the system owning some of them is not a reason to rewrite the rest.

Seeding SHALL be idempotent, so that repeating it does not accumulate repeated rules. Where the
system's own set of rules has since changed, the system SHALL bring an already-seeded project up to
date rather than leaving it on the set it first received.

A project that is not under version control SHALL be left unchanged, and this SHALL NOT be an error.

Failure to seed SHALL NOT fail registration or a turn. Ignore rules are a convenience; a project
that cannot receive them is still a project.

#### Scenario: Registering seeds ignore rules

- **WHEN** a project under version control is registered
- **THEN** the system's own working artefacts are ignored

#### Scenario: The rules reach an agent's own checkout

- **WHEN** an agent works in the isolated checkout the system provisioned for it
- **AND** the system writes its own working files there
- **THEN** version control reports that checkout as clean
- **AND** the agent's commits do not carry the system's working files

#### Scenario: The system's commit does not sweep in build artefacts

- **WHEN** an agent's work leaves bytecode or installed dependencies in its checkout
- **AND** the system commits that checkout on the agent's behalf
- **THEN** those artefacts are not in the commit

#### Scenario: What is already committed stays committed

- **WHEN** a project already carries an artefact the system's rules now cover
- **THEN** seeding does not remove it from version control

#### Scenario: An already-registered project is covered without registering again

- **WHEN** a project registered earlier has a workspace resolved for an agent
- **THEN** the system's ignore rules are in place
- **AND** the operator was not asked to re-register it

#### Scenario: Existing rules are preserved

- **WHEN** a project with its own ignore rules is seeded
- **THEN** those rules remain
- **AND** the system's rules are added alongside them

#### Scenario: Re-seeding does not duplicate

- **WHEN** a project is seeded again
- **THEN** the ignore rules are not repeated

#### Scenario: A later rule reaches a project seeded by an earlier release

- **WHEN** the system's set of ignore rules has grown since a project was seeded
- **AND** that project is seeded again
- **THEN** the new rules are present
- **AND** everything outside the system's own rules is unchanged

#### Scenario: A project without version control is left unchanged

- **WHEN** a project not under version control is seeded
- **THEN** it succeeds
- **AND** no ignore file is created
