## ADDED Requirements

### Requirement: The approval preview says whether the work would merge cleanly

Where the Hub can test-merge a task's work into the project's main branch, the preview of what approving the task would write SHALL say whether that work merges cleanly, and SHALL name the conflicting paths and commit where it does not.

Approval is refused when the work would conflict, and that refusal is otherwise the only place the
conflict is stated: after it, the operator reopening the task would read nothing about it, and
before the first approval they cannot learn it at all. The preview SHALL ask the same question the
refusal asks, with the same test merge, so the two cannot disagree.

The preview SHALL NOT move any branch or change any working tree or index, and SHALL NOT record
anything in the Hub. (The test merge may write objects into the repository's object database, which
nothing references.) Its answer SHALL be computed when it is asked, so it does not outlive a change
to the branch or to the evidence that names the commit.

The preview SHALL NOT say that approval will merge, cleanly or otherwise, when approval would merge
nothing, and where it states how many commits approval would merge, it SHALL state the real number.

Where the Hub cannot ask — no main branch configured, no resolvable workspace, a directory that is
not a repository, or no branch by the configured name — the preview SHALL say that whether the work
merges cleanly is checked at approval, and SHALL NOT fail.

Where asking git fails — a git call that raises or times out, whether while testing the merge or
while working out what approval would merge — the preview SHALL still answer successfully, SHALL
NOT ask git again within the same request, and SHALL state that it could not ask rather than state
that there is nothing to merge.

#### Scenario: A conflicting task's preview names the conflict before approval

- **WHEN** a task's work would conflict with the main branch and the operator opens its preview
- **THEN** the preview says approval would be refused, naming the conflicting paths and the commit
- **AND** no branch has moved and the working tree and index are unchanged

#### Scenario: The preview agrees with the refusal

- **WHEN** approval of that task is attempted and refused for the conflict
- **THEN** the preview read afterwards names the same paths and commit

#### Scenario: A clean task's preview says it merges cleanly

- **WHEN** a task's work merges cleanly into the main branch
- **THEN** the preview says so, with the number of commits approval would merge

#### Scenario: Nothing to merge is not a clean merge

- **WHEN** the Hub can test-merge but approval would merge no commit for the task
- **THEN** the preview says there is nothing to merge
- **AND** it does not say that the work merges cleanly

#### Scenario: Where the Hub cannot ask, the preview says it has not

- **WHEN** the project has no main branch configured or its directory is not a repository
- **THEN** the preview says the merge is checked at approval
- **AND** it answers successfully

#### Scenario: A git failure is stated, not a failed request

- **WHEN** a git call raises while the preview works out what approval would merge for a task whose work comes from its own branch
- **THEN** the preview answers successfully
- **AND** it says the Hub could not ask git, not that the task has no branch
