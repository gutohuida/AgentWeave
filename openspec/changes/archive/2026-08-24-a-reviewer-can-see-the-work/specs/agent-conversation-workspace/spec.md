## ADDED Requirements

### Requirement: A review turn is given a checkout of the code under review

A review turn's workspace SHALL be a git checkout of the exact commit the reviewed work's evidence
names, and SHALL NOT be the reviewing agent's own working checkout.

The reviewing agent SHALL be able to read every file in that checkout, search it, and execute its
test suite. It SHALL NOT be able to reach the authoring agent's working checkout, which remains
outside its workspace boundary.

The checkout SHALL be detached from any branch, so that git itself reports the reviewing role and
an accidental commit is orphaned rather than accumulated.

The Hub SHALL provide the same shared dependencies to a review checkout that it provides to a
working checkout. A review checkout that cannot run the project's tests does not satisfy this
requirement.

#### Scenario: A reviewer reads code that is not on the main branch

- **GIVEN** an authoring agent has completed work on its own isolated checkout and recorded evidence naming a commit
- **AND** that commit has not been integrated into the project's main branch
- **WHEN** the Hub starts a review turn for a different agent
- **THEN** the reviewing agent's workspace contains that commit's version of the code
- **AND** the reviewing agent can read files the main branch does not contain

#### Scenario: A reviewer can run the tests it is asked to trust

- **GIVEN** a review turn whose workspace is a checkout of the commit under review
- **WHEN** the reviewing agent runs the project's test suite
- **THEN** the suite executes against the code under review
- **AND** the result is the reviewing agent's own observation rather than a claim it was given

#### Scenario: A reviewer cannot reach the author's working checkout

- **GIVEN** a review turn is in progress
- **WHEN** the reviewing agent attempts to read or write inside the authoring agent's working checkout
- **THEN** the attempt is refused as outside its workspace

#### Scenario: A review turn has exactly one workspace

- **GIVEN** a reviewing agent that also has a working checkout of its own
- **WHEN** it is given a review turn
- **THEN** its workspace for that turn is the review checkout alone
- **AND** its own working checkout is outside its workspace boundary for the duration of that turn

### Requirement: A review checkout names the commit the most recent evidence cites

The Hub SHALL resolve the commit for a review turn from the most recent evidence recorded for the
task under review.

Where earlier evidence for the same task names a different commit, the Hub SHALL state that in the
reviewing agent's turn context. It SHALL NOT silently present the newest commit as though it were
the only one.

#### Scenario: One piece of evidence

- **GIVEN** a task with a single piece of recorded evidence naming a commit
- **WHEN** a review turn begins
- **THEN** the review checkout is detached at that commit

#### Scenario: Evidence that names two different commits

- **GIVEN** a task with two pieces of recorded evidence naming different commits
- **WHEN** a review turn begins
- **THEN** the review checkout is detached at the commit named by the more recent evidence
- **AND** the reviewing agent is told that earlier evidence named a different commit

#### Scenario: A task with no evidence

- **GIVEN** a task that has reached completion with no recorded evidence
- **WHEN** a review turn is requested
- **THEN** no review checkout is created
- **AND** the reason states that there is no evidence naming a commit to review

### Requirement: A review checkout is bounded and reused

The Hub SHALL place a review checkout at a path it determines, keyed by the reviewing agent, and
SHALL reuse that path across successive reviews by the same agent rather than creating a new
location per review.

The reviewing agent SHALL NOT be required to construct, choose or be told a path by another agent.

#### Scenario: A second review reuses the same location

- **GIVEN** an agent that has already completed one review
- **WHEN** it is given a review turn for a different task
- **THEN** its review checkout is at the same path as before, now detached at the new commit

#### Scenario: The number of review checkouts is bounded by the roster

- **GIVEN** a project whose agents have performed many reviews
- **WHEN** the project's checkouts are enumerated
- **THEN** the number of review checkouts does not exceed the number of agents that have reviewed
