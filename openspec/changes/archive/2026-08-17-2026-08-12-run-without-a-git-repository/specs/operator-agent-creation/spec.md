# operator-agent-creation

## MODIFIED Requirements

### Requirement: Operator-created agents preserve runtime isolation

An operator-created agent SHALL be a Hub-owned project participant with its own queue, conversation
identity, and stable color. Creation SHALL NOT provision or mutate a Git worktree. The existing
scheduler SHALL provision the isolated worktree only when the agent first begins writing work, and
only where the project directory is a Git repository.

Where the project directory is a Git repository and the isolated worktree cannot be provisioned, the
Hub SHALL refuse the turn and state why. It MUST NOT run the agent in the primary checkout instead:
a project that has isolation SHALL NOT lose it silently.

#### Scenario: Creation has no filesystem side effect beyond Hub state

- **WHEN** an operator creates an agent but sends it no work
- **THEN** no agent worktree exists

#### Scenario: First writing turn provisions isolation

- **WHEN** the new agent begins its first writing turn
- **THEN** the scheduler provisions that agent's isolated worktree under the existing project guard
- **AND** other agents' worktrees and the primary checkout remain unchanged

#### Scenario: Isolation is available but cannot be prepared

- **WHEN** a writing agent's turn begins in a project that is a Git repository and provisioning its
  worktree fails
- **THEN** the turn does not start
- **AND** the reason names the provisioning failure
- **AND** the agent is not run in the primary checkout

## ADDED Requirements

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
