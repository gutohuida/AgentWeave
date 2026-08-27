## MODIFIED Requirements

### Requirement: Operator-created agents preserve runtime isolation

An operator-created agent SHALL be a Hub-owned project participant with its own queue, conversation identity, and stable color. Creation SHALL NOT provision or mutate a Git worktree. The existing scheduler SHALL provision an isolated worktree only when the agent first begins writing work, and only where the project directory is a Git repository.

**The unit of isolation SHALL be the task, where the turn is about one.** A writing turn bound to a task SHALL run in a checkout provisioned for that task, on a branch that carries that task's work and no other task's. A writing turn bound to no task SHALL run in a checkout provisioned for the agent, on that agent's own branch. Which checkout a turn gets is therefore decided by what the turn is about, not by who is doing it.

A per-agent branch carries every task its agent has ever worked on, so any operation that merges such a branch — or merges a commit on it, since merging a commit brings its whole ancestry — integrates work that was never approved. A branch that corresponds to a task is what makes "this task's work" a thing the system can name.

Where the project directory is a Git repository and the isolated checkout cannot be provisioned, the Hub SHALL refuse the turn and state why. It MUST NOT run the agent in the primary checkout instead: a project that has isolation SHALL NOT lose it silently.

#### Scenario: Creation has no filesystem side effect beyond Hub state

- **WHEN** an operator creates an agent but sends it no work
- **THEN** no agent worktree exists

#### Scenario: First writing turn provisions isolation

- **WHEN** the new agent begins its first writing turn
- **THEN** the scheduler provisions that turn's isolated checkout under the existing project guard
- **AND** other checkouts and the primary checkout remain unchanged

#### Scenario: A turn about a task works in that task's own checkout

- **WHEN** a writing agent's turn is bound to a task
- **THEN** it runs in a checkout provisioned for that task, on a branch dedicated to that task

#### Scenario: Two tasks held by one agent do not share a branch

- **WHEN** the same agent takes turns on two different tasks
- **THEN** each turn runs on its own task's branch
- **AND** neither branch carries the other task's commits

#### Scenario: A turn about no task works in the agent's own checkout

- **WHEN** a writing agent's turn is bound to no task
- **THEN** it runs in the checkout provisioned for that agent, on that agent's own branch

#### Scenario: Isolation is available but cannot be prepared

- **WHEN** a writing agent's turn begins in a project that is a Git repository and provisioning its
  checkout fails
- **THEN** the turn does not start
- **AND** the reason names the provisioning failure

## ADDED Requirements

### Requirement: Work already under way keeps the checkout it started in

A task that already carries committed work on a per-agent branch when per-task isolation is introduced SHALL continue to be worked in that per-agent checkout for the remainder of its life, and SHALL NOT be given a task checkout.

No existing branch SHALL be renamed, deleted, split, or rewritten in order to introduce per-task isolation. There is no record of which commit on a per-agent branch belongs to which task — that absence is the defect being fixed — so any automatic split would be a guess, and a guess that rewrites history cannot be undone by the operator who did not ask for it.

Adopting such a branch as the task's own branch SHALL NOT be done either. The branch carries other tasks' commits, so adopting it would leave the system claiming that one approval lands one task's work while that claim was false for an unbounded set of tasks, and false silently.

The condition SHALL be determined from recorded fact rather than inferred from a date or a version: a task whose earlier runs produced no commit has no work to preserve and is not covered by this requirement.

Because a task's first writing turn provisions its task checkout from that point on, the set of tasks covered by this requirement is fixed when the change ships and only shrinks.

#### Scenario: A task with committed work on a per-agent branch keeps it

- **WHEN** a writing turn is taken on a task that already produced a commit on its agent's branch
- **THEN** the turn runs in that per-agent checkout
- **AND** no task branch is created for that task

#### Scenario: A task whose earlier turns produced nothing is not covered

- **WHEN** a writing turn is taken on a task that has earlier runs but none that produced a commit
- **THEN** the turn runs in a checkout provisioned for that task

#### Scenario: No branch is destroyed to make room

- **WHEN** per-task isolation is introduced into a project with existing per-agent branches
- **THEN** every one of those branches still exists, at the same commit, with the same history
