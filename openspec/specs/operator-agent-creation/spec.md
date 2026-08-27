# operator-agent-creation Specification

## Purpose
Define how an operator creates a project-scoped, runner-bound agent from the Hub while preserving
launchability truth, optional charter guidance, stable identity, and lazy worktree isolation.
## Requirements
### Requirement: An operator can create an agent from the project workspace

Each project workspace SHALL expose an **Add agent** action. Creating an agent SHALL require a
valid project-unique name, a launchable provider, and a model that provider's catalog entry
declares. A charter MAY be selected but MUST NOT be required. The operator MUST NOT be asked to
choose a persona or organizational role.

The operator MUST NOT be required to have configured a runner beforehand. Selecting a provider and
a model SHALL be sufficient to create a working agent.

#### Scenario: A minimally configured agent is created

- **WHEN** the operator supplies a valid unused name and selects a launchable provider and a model
- **THEN** the agent is created with a stable project color and runner binding
- **AND** it appears in the project rail without a reload
- **AND** its conversation opens ready for input

#### Scenario: No runner need exist beforehand

- **WHEN** the operator selects a provider and model for which the project has no runner
- **THEN** creation succeeds and the agent is bound to a runner for that provider and model

#### Scenario: The offered models come from the catalog

- **WHEN** the operator selects a provider
- **THEN** the models offered are those the catalog declares for that provider

#### Scenario: A charter is optional

- **WHEN** the operator creates an agent without selecting a charter
- **THEN** creation succeeds with full project scope under the existing no-charter contract

#### Scenario: A duplicate name is refused without losing input

- **WHEN** the supplied name already identifies an agent in that project
- **THEN** creation is refused with a field-specific reason
- **AND** the dialog preserves the operator's other selections for correction

### Requirement: Agent creation exposes real runner launchability

The creation journey SHALL display every provider it offers with that provider's current
launchability. An unlaunchable provider SHALL remain visible with the reason it cannot run and MUST
NOT be selectable as ready. The server SHALL repeat launchability validation when creation is
submitted.

#### Scenario: An unavailable provider is explained

- **WHEN** a provider's CLI or authorization is unavailable
- **THEN** the provider is displayed disabled with the current reason
- **AND** submitting that provider cannot create an apparently ready agent

#### Scenario: Client state cannot bypass server validation

- **WHEN** provider launchability changes after the dialog loads but before submission
- **THEN** the server refuses creation with the current typed reason

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

### Requirement: Agent creation provisions its runner atomically

When agent creation requires a runner that does not exist, the Hub SHALL create the runner and the
agent as one atomic operation. A failure at any point SHALL leave neither record behind.

The Hub SHALL reuse an existing same-project runner whose provider and model match the operator's
selection rather than creating a duplicate.

#### Scenario: A matching runner is reused

- **WHEN** the operator creates a second agent on a provider and model that an existing runner in
  that project already describes
- **THEN** the new agent is bound to that existing runner
- **AND** no additional runner is created

#### Scenario: A failed creation leaves no runner behind

- **WHEN** agent creation fails after a runner would have been provisioned
- **THEN** no runner record remains from the attempt

#### Scenario: Provisioned runners are ordinary records

- **WHEN** a runner has been provisioned through agent creation
- **THEN** it appears in runner management and can be inspected, edited, and deleted like any other

### Requirement: Provider choice is presented by provider identity

Where the operator chooses an agent's provider, each provider SHALL be presented with its own visual
mark alongside its name.

A provider for which no mark is available SHALL be presented with its name alone and MUST NOT be
given another provider's mark. A mark MUST NOT be the only thing distinguishing one provider from
another — the provider's name SHALL always be present.

Provider marks MUST NOT introduce a second icon system, a webfont, or a network request to render.

Presenting a provider's mark MUST NOT change which providers are offered. Launchability remains the
sole determinant of whether a provider can be chosen.

#### Scenario: Providers are shown with their marks

- **WHEN** the operator opens the provider choice
- **THEN** each provider is shown with its mark and its name

#### Scenario: A provider without a mark still reads correctly

- **WHEN** a provider has no available mark
- **THEN** it is shown with its name
- **AND** is not given another provider's mark

#### Scenario: Marks do not gate availability

- **WHEN** a provider is launchable but has no mark
- **THEN** it remains selectable

#### Scenario: Marks need no second icon system

- **WHEN** provider marks are rendered
- **THEN** they resolve without a second icon system, a webfont, or a network request

### Requirement: What creation collects is decided by whether it changes the first turn

Agent creation SHALL offer a setting when the agent's first turn would be materially different
without it, and SHALL leave every other setting to the agent's configuration destination.

This capability already fixes *what* creation collects — a project-unique name, a launchable
provider, a model the catalog declares, and an optional charter. What it does not state is the rule
by which anything new is placed, so each future setting would be argued individually and creation
would grow by accretion.

The rule governs what is **offered**, not what is **required**. A charter is offered because it
shapes the first turn, and remains optional under the existing no-charter contract; nothing here
tightens that.

A setting with a workable default, which can be changed before it takes effect, MUST NOT be added to
creation. Lengthening creation is friction at the first moment an operator uses the product, and
buys nothing that the configuration destination cannot provide later.

#### Scenario: A setting affecting the first turn is offered

- **WHEN** a setting would materially change how the agent's first turn behaves
- **THEN** creation offers it

#### Scenario: A defaulted setting is left to configuration

- **WHEN** a setting has a workable default and can be changed before it takes effect
- **THEN** creation does not offer it
- **AND** it is available on the agent's configuration destination

#### Scenario: Offering does not imply requiring

- **WHEN** a setting is offered at creation
- **THEN** it may still be optional
- **AND** an existing optional contract for it is preserved

### Requirement: A project that is not a Git repository still runs its agents

Where a project's directory is not a Git repository, the Hub SHALL run a writing agent in that
directory rather than refusing the turn. Absence of a repository SHALL NOT be reported as a
condition the operator must resolve before working.

The Hub SHALL state the resulting posture rather than leave it to be discovered. The agent's
canonical turn context SHALL say that it is working in the project's shared directory and that no
isolated checkout is available, and the agent's workspace report SHALL distinguish an agent sharing
the project directory because no repository exists from one sharing it by configuration.

Concurrent writing agents in such a project SHALL be permitted. The Hub SHALL NOT serialize them,
lock the directory, or refuse a second writer. Because their edits can overwrite one another with no
conflict to resolve, and no mechanism for producing a conflict exists without a repository, the Hub
SHALL tell each agent that it shares the directory. That statement is the whole of the mitigation
and SHALL NOT be removed while the permission stands.

The Hub SHALL NOT create, initialize, or modify a Git repository in the project directory in order to
satisfy this requirement.

#### Scenario: A writing agent's first turn in a directory with no repository

- **WHEN** a writing agent is triggered in a project whose directory is not a Git repository
- **THEN** the turn starts with the project directory as its working directory
- **AND** no repository, worktree, or branch is created

#### Scenario: The queue does not report a repository as a blocker

- **WHEN** the operator inspects the queue status for an agent in a project with no repository
- **THEN** no waiting reason names the absent repository

#### Scenario: The agent is told which posture it has

- **WHEN** a turn's canonical context is built for an agent running in a project with no repository
- **THEN** the context states that the working directory is the project's shared directory and that
  no isolated checkout is available
- **AND** it states that another agent in the project works in that same directory and that their
  edits can overwrite each other

#### Scenario: A second writing agent is not refused or serialized

- **WHEN** two writing agents are triggered in the same project with no repository
- **THEN** both run, in that project's directory
- **AND** neither is refused, queued, or delayed on account of the other

#### Scenario: The workspace report distinguishes the two ways of sharing

- **WHEN** the operator views the workspace of an agent in a project with no repository
- **THEN** it reports the project directory as the working directory, with no branch, and states that
  no repository exists
- **AND** an agent that shares the project directory by configuration is reported without that
  statement

#### Scenario: A working directory override is refused only where isolation exists

- **WHEN** a writing agent's turn requests a working directory within a project that is a Git
  repository
- **THEN** the request is refused as overriding isolation
- **WHEN** the same request is made within a project that is not a Git repository
- **THEN** it is resolved as a project-relative path under the existing containment guard

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
