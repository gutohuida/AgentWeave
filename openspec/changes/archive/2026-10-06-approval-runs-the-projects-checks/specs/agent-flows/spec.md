## ADDED Requirements

### Requirement: A review turn is told the task's check result
In a project with checks, both review channels (the flow's review briefing and the review turn context) SHALL state the task's latest check result: passed, failed (naming the failing checks), running, or none yet. Where it is not `passed`, they SHALL say that `approved` will be refused until the checks pass, and that `revision_needed` with the failing output is the verdict that returns a failing task to its author.

#### Scenario: A reviewer is told the checks failed
- **WHEN** a review turn is given for a task whose latest check run failed
- **THEN** its briefing names the failing check and says `approved` will be refused and `revision_needed` returns it

#### Scenario: Nothing is said where there are no checks
- **WHEN** a review turn is given in a project with no checks configured
- **THEN** its briefing carries no check sentence
