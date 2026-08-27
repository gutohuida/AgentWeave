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

A task that was already being worked on a per-agent branch when per-task isolation is introduced SHALL continue to be worked in that per-agent checkout for the remainder of its life, and SHALL NOT be given a task checkout.

No existing branch SHALL be renamed, deleted, split, or rewritten in order to introduce per-task isolation. There is no record of which commit on a per-agent branch belongs to which task — that absence is the defect being fixed — so any automatic split would be a guess, and a guess that rewrites history cannot be undone by the operator who did not ask for it.

Adopting such a branch as the task's own branch SHALL NOT be done either. The branch carries other tasks' commits, so adopting it would leave the system claiming that one approval lands one task's work while that claim was false for an unbounded set of tasks, and false silently.

The set of covered tasks SHALL be recorded once, when per-task isolation is introduced, and SHALL NOT be recomputed afterwards. Determining it from the state of the world at each turn — whether a branch exists, or whether a particular kind of commit was recorded — makes a task's scheme depend on things that change after the fact, so a task could move between schemes mid-life without anyone deciding it should. Because nothing writes the record after it is made, the set is fixed when the change ships and only shrinks.

The recorded set SHALL cover every task that has already been worked at all, whether or not a commit can be found for it. Covering a task that had nothing to preserve costs it only the isolation it never had; failing to cover a task that did have work costs that work its place in the checkout the agent is about to be given, with no statement that anything is missing. Those costs are not comparable, so the boundary is drawn on the safe side of it.

#### Scenario: A task already worked keeps its per-agent checkout

- **WHEN** a writing turn is taken on a task that was already worked before per-task isolation
- **THEN** the turn runs in that per-agent checkout
- **AND** no task branch is created for that task

#### Scenario: An agent that committed its own work does not lose it

- **WHEN** a writing turn is taken on a task whose earlier turns committed their work directly, so
  the system recorded no automatic snapshot for them
- **THEN** the turn still runs in the per-agent checkout, with that work present

#### Scenario: A task created afterwards is not covered

- **WHEN** a task is created after per-task isolation is introduced and given a writing turn
- **THEN** it runs in a checkout provisioned for that task

#### Scenario: No branch is destroyed to make room

- **WHEN** per-task isolation is introduced into a project with existing per-agent branches
- **THEN** every one of those branches still exists, at the same commit, with the same history

### Requirement: A task's checkout is worked by one turn at a time

While a writing turn is in flight for a task, the system SHALL refuse to start another writing turn for that same task on behalf of a different agent, and the refusal SHALL name the agent already holding it.

Before work was isolated per task, this held without being stated: a checkout belonged to an agent, and an agent could have only one turn in flight, so no two processes could share a working tree. Isolating per task removes that coupling — nothing else in the system prevents two agents from being pointed at the same task — and two live processes editing one working tree lose each other's changes silently, which is the outcome workspace isolation exists to prevent.

A turn started to **review** a task SHALL NOT be refused by this rule. A review runs in a checkout of the commit under review rather than in the task's own checkout, so there is nothing for it to collide with, and refusing it would stop a task being reviewed while it is being worked.

An agent that works in the project's shared checkout rather than an isolated one SHALL NOT be refused by this rule either. It has no isolated checkout to collide over, and the shared checkout's behaviour is unchanged by this requirement.

Nor SHALL a task still worked under the per-agent scheme be refused. Such a task has no checkout of its own to admit anybody to, and the coupling this rule replaces still holds for it, so refusing here would forbid something that is safe.

The refusal SHALL be temporary rather than terminal: input that was refused for this reason SHALL be retained and delivered once the holding turn ends, not discarded. The condition clears by itself, which is what distinguishes it from a refusal about a request that will never become valid.

#### Scenario: A second agent is refused while the first is working

- **WHEN** a writing turn is triggered for a task that another agent already has a run in flight for
- **THEN** the turn is refused
- **AND** the refusal names the agent holding the task

#### Scenario: The refused input is not thrown away

- **WHEN** a turn is refused because another agent holds the task, and that agent's turn then ends
- **THEN** the input that was refused is still pending
- **AND** it is delivered on a subsequent attempt rather than having been discarded

#### Scenario: A review is not refused

- **WHEN** a review turn is triggered for a task that an agent is currently working
- **THEN** the review turn starts

#### Scenario: The same agent's next turn is unaffected

- **WHEN** an agent's turn on a task ends and it is triggered on that task again
- **THEN** the turn starts in the same task checkout
