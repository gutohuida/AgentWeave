## ADDED Requirements

### Requirement: The approval preview says whether the work would merge cleanly

Where the Hub can test-merge a task's work into the project's main branch, the preview of what approving the task would write SHALL say whether that work merges cleanly, and SHALL name the conflicting paths and commit where it does not.

Approval is refused when the work would conflict, and that refusal is otherwise the only place the
conflict is stated: after it, the operator reopening the task would read nothing about it, and
before the first approval they cannot learn it at all. The preview SHALL ask the same question the
refusal asks, with the same test merge, so the two cannot disagree.

The preview SHALL NOT change the repository, the working tree or the index, and SHALL NOT record
anything. Its answer SHALL be computed when it is asked, so it does not outlive a change to the
branch or to the evidence that names the commit.

Where the Hub cannot ask — no main branch configured, no resolvable workspace, a directory that is
not a repository, or no branch by the configured name — the preview SHALL say that whether the work
merges cleanly is checked at approval, and SHALL NOT fail.

#### Scenario: A conflicting task's preview names the conflict before approval

- **WHEN** a task's work would conflict with the main branch and the operator opens its preview
- **THEN** the preview says approval would be refused, naming the conflicting paths and the commit
- **AND** the repository is unchanged

#### Scenario: The preview agrees with the refusal

- **WHEN** approval of that task is attempted and refused for the conflict
- **THEN** the preview read afterwards names the same paths and commit

#### Scenario: A clean task's preview says it merges cleanly

- **WHEN** a task's work merges cleanly into the main branch
- **THEN** the preview says so

#### Scenario: Where the Hub cannot ask, the preview says it has not

- **WHEN** the project has no main branch configured or its directory is not a repository
- **THEN** the preview says the merge is checked at approval
- **AND** it answers successfully
