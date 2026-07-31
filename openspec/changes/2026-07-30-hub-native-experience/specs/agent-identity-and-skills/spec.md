## ADDED Requirements

### Requirement: Execution capability, participant identity, and behaviour are separate concepts

The system SHALL model three distinct concepts:

- a **runner** — the capability to execute, comprising an agent CLI, a model, and its environment;
- an **agent** — an addressable participant within a project, holding a name, a runner, a working
  directory, an identity colour, an inbox, and session continuity;
- **behaviour** — what an agent is for, what it may touch, and what capability it invokes.

A runner SHALL be reusable by any number of agents across any number of projects. Changing an
agent's runner MUST NOT change its identity, its queue, or its history.

#### Scenario: One runner serves many agents

- **WHEN** a runner is configured once
- **THEN** agents in any project may be created against it without reconfiguring it

#### Scenario: Identity survives a runner change

- **WHEN** an agent's runner is changed
- **THEN** its name, queue, identity colour, and history are unchanged

### Requirement: Agent names are unique addresses within their project

An agent's name SHALL be unique within its project, because it is the address to which work and
messages are directed. Two agents in the same project MUST NOT share a name.

The same name MAY be used in different projects, and MUST refer to distinct agents.

#### Scenario: A duplicate name is refused

- **WHEN** an agent is created with a name already in use in that project
- **THEN** the creation is refused with a stated reason

#### Scenario: Names are scoped to their project

- **WHEN** two projects each contain an agent with the same name
- **THEN** they are distinct agents with separate queues, sessions, and histories

### Requirement: Adding an agent requires no declaration of persona

Creating an agent SHALL require only a runner and a name. The operator MUST NOT be required to
choose a job title, persona, or organisational position in order to create a working agent.

Available runners SHALL be presented with their current launchability, so an operator is not
offered a runner that cannot run.

An agent created without further configuration SHALL be immediately usable and SHALL operate within
the full scope of its project.

#### Scenario: An agent is created and immediately usable

- **WHEN** the operator supplies a runner and a name
- **THEN** the agent is created and can be given work immediately
- **AND** no persona, job title, or organisational position was requested

#### Scenario: Only launchable runners are offered as ready

- **WHEN** the operator is choosing a runner
- **THEN** each is shown with its current launchability and, where unavailable, the reason

### Requirement: An agent's behaviour is defined by a charter, not a persona

An agent MAY carry a charter declaring its **purpose**, its **scope**, and the **skills** it loads
by default. A charter SHALL express a boundary — what the agent is for and what it may act upon —
rather than a personality or professional identity.

Scope SHALL constrain what the agent may act upon. An empty charter SHALL mean the full scope of
the project.

Job-title personas SHALL NOT be part of an agent's definition.

#### Scenario: A charter constrains what an agent acts upon

- **WHEN** an agent's charter limits its scope
- **THEN** work outside that scope is not performed silently
- **AND** the limitation is reported

#### Scenario: An empty charter means full project scope

- **WHEN** an agent has no charter
- **THEN** it may act within the full scope of its project

#### Scenario: Personas are not part of agent definition

- **WHEN** an agent is created or configured
- **THEN** no job-title persona can be assigned to it

### Requirement: Skills are invocable capability available to any agent

Skills SHALL be invocable units of capability, available to any agent regardless of its charter. A
charter MAY cause skills to load by default, but MUST NOT be the only way an agent can reach a
skill.

Invoking a skill MUST NOT change the agent's identity or its scope.

#### Scenario: Any agent may invoke any available skill

- **WHEN** an agent invokes a skill available in its project
- **THEN** the skill's capability is applied

#### Scenario: Default skills load without preventing others

- **WHEN** an agent's charter names default skills
- **THEN** those skills are available from the start of a turn
- **AND** the agent may still invoke other available skills

#### Scenario: A skill does not widen scope

- **WHEN** an agent invokes a skill whose capability exceeds its scope
- **THEN** the agent's scope is unchanged and the limitation is reported

### Requirement: Agent templates make repeated instantiation possible

A template SHALL capture a runner, a charter, and default skills, so that equivalent agents can be
created repeatedly. Instantiating a template SHALL produce a distinct agent with its own name,
queue, session, and identity colour.

#### Scenario: A template produces several distinct agents

- **WHEN** the same template is instantiated more than once in a project
- **THEN** each instantiation is a distinct agent with its own name, queue, session, and colour
- **AND** each carries the template's charter and default skills

#### Scenario: Instantiation resolves the name conflict

- **WHEN** a template is instantiated and its suggested name is already in use
- **THEN** a distinct name is proposed rather than the creation failing

#### Scenario: Later template edits do not rewrite existing agents

- **WHEN** a template is modified after agents were instantiated from it
- **THEN** existing agents are unchanged

### Requirement: Agents receive a live roster of their collaborators

When a project contains more than one agent, each turn SHALL begin with a roster naming the other
agents in that project, each agent's purpose, and its current state.

The roster SHALL reflect state at the time the turn starts, not a value recorded when the project
was configured.

#### Scenario: An agent learns who else is working

- **WHEN** a turn begins in a project containing several agents
- **THEN** the agent receives the other agents' names, purposes, and current states

#### Scenario: The roster is current

- **WHEN** an agent's state changes and another agent's turn then begins
- **THEN** the roster reflects the changed state

### Requirement: A single-agent project carries no multi-agent overhead

When a project contains exactly one agent, no roster, collaboration protocol, or delegation
instruction SHALL be injected into its turns.

Multi-agent capability SHALL appear when a second agent is added, without reconfiguring the first.

#### Scenario: A lone agent is told nothing about collaboration

- **WHEN** a turn begins in a project containing exactly one agent
- **THEN** no roster or collaboration instruction is included

#### Scenario: Adding a second agent enables collaboration in place

- **WHEN** a second agent is added to a project
- **THEN** subsequent turns for both agents include the roster
- **AND** the first agent required no reconfiguration

### Requirement: An agent may request a new agent within a budget

An agent MAY request that a further agent be created. Each project SHALL carry a configurable
budget limiting how many agents may be created this way.

A request within budget, naming a template the operator has approved for automatic instantiation,
SHALL be fulfilled automatically. Any other request SHALL be presented to the operator as a
decision awaiting response, and MUST NOT create an agent until answered.

#### Scenario: An approved request within budget is fulfilled

- **WHEN** an agent requests a further agent from a template approved for automatic instantiation,
  and the project is within its budget
- **THEN** the agent is created and the requesting agent is told

#### Scenario: A request beyond budget awaits the operator

- **WHEN** an agent requests a further agent and the project's budget is exhausted
- **THEN** no agent is created
- **AND** the request is presented to the operator as a decision awaiting response

#### Scenario: An unapproved template always awaits the operator

- **WHEN** an agent requests a further agent from a template not approved for automatic instantiation
- **THEN** no agent is created until the operator answers

#### Scenario: Agent creation is attributable

- **WHEN** an agent is created at another agent's request
- **THEN** the requesting agent and the request are recorded

### Requirement: Behaviour resolves in a defined order

An agent's effective behaviour SHALL be composed from, in increasing order of specificity: project
instructions, the agent's charter, invoked skills, and the acceptance criteria of the work in hand.
Where these conflict, the more specific SHALL prevail.

The effective composition for a given turn SHALL be inspectable.

#### Scenario: The more specific instruction prevails

- **WHEN** a task's acceptance criteria conflict with a project instruction
- **THEN** the acceptance criteria govern that work

#### Scenario: The composition is inspectable

- **WHEN** an operator examines a turn
- **THEN** the project instructions, charter, skills, and acceptance criteria that composed its
  behaviour are identifiable
