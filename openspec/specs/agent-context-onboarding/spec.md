# agent-context-onboarding Specification

## Purpose
Define generated model-facing context, project operating profiles, and Hub/MCP onboarding, sourced from Hub-owned records, so every agent the Hub knows starts work with complete, fresh, non-placeholder project context — including the names of the peers it can address.
## Requirements
### Requirement: Canonical per-agent runtime context
The Hub SHALL build canonical runtime context for each configured agent and supply it to every run.
It MAY materialize that context inside a run workspace when a runner requires a file.

#### Scenario: Hub generates canonical context for each configured agent
- **WHEN** the Hub prepares a run for a configured agent
- **THEN** it builds context containing the agent's project operating profile, team context, quality gates, charter guidance, project instructions, and project context when available

#### Scenario: Run preparation uses current configuration
- **WHEN** agent, runner, project, charter, or quality configuration changes before a run
- **THEN** the next run receives context generated from the current Hub-owned configuration

#### Scenario: Runtime launch injects generated context
- **WHEN** the Hub launches a supported runner
- **THEN** it supplies canonical context using that runner's supported prompt or file mechanism

---

### Requirement: Project operating profile generation
The system SHALL generate a concise project operating profile from Hub-owned project, agent, runner,
and charter records. The project's identity and its agent roster MUST be derived from those records
and MUST NOT depend on `agentweave.yml` or on synced session state, neither of which a Hub-owned
project has.

Configuration that the Hub does not yet own natively MAY continue to be read from synced session
state where that is its only home, provided it never determines an agent's identity, its roster, or
what work it is permitted to do.

The profile SHALL name every agent registered in the project, so that an agent can address a peer
without guessing. For each agent it SHALL state that agent's name, its bound runner's CLI, and its
configured model, and SHALL mark which entry is the reading agent itself. Environment variables SHALL
be identified by name only, never by value.

Sections describing configuration the Hub does not hold SHALL be omitted rather than rendered empty
or populated with invented defaults.

#### Scenario: Profile names the real roster
- **WHEN** generated context is built for an agent in a project containing other agents
- **THEN** the profile lists every registered agent by name with its runner CLI and configured model
- **AND** marks the reading agent's own entry

#### Scenario: Profile does not depend on a synced session
- **WHEN** generated context is built for a project that has never synced session state
- **THEN** the profile is still complete, sourced from the Hub's own project, agent, and runner records
- **AND** does not report the project session as missing

#### Scenario: Secrets are never included
- **WHEN** an agent's runner declares environment variables
- **THEN** the profile includes their names only
- **AND** includes no value

#### Scenario: Absent configuration is omitted
- **WHEN** the Hub holds no quality-gate or scheduled-job configuration for a project
- **THEN** generated context omits those sections entirely
- **AND** does not render an empty or placeholder section in their place

#### Scenario: Profile includes quality gates when configured
- **WHEN** the Hub holds quality-gate configuration for the project
- **THEN** generated context includes actionable instructions for docs threshold, docs path, review
  requirement, echo-chamber guard, attribution tagging, and dependency checking

---

### Requirement: Layered project and role context
The system SHALL layer stable charter guidance, generated project facts, long-lived project context, project-wide instructions, and live session state without duplicating stale information across files.

#### Scenario: Charter content remains a stable contract
- **WHEN** a charter is authored or edited through the Hub UI
- **THEN** it describes agent scope, responsibilities, boundaries, handoff rules, quality behavior, definition of done, and escalation paths without embedding a full copy of project instructions

#### Scenario: Placeholder project context is not silently injected
- **WHEN** `.agentweave/ai_context.md` contains known untouched template placeholders
- **THEN** generated context omits the placeholder content or includes a clear missing-context warning instead of presenting the placeholder as project facts

#### Scenario: Live shared context is prompt-level for Hub-triggered runs
- **WHEN** the Hub triggers an agent from a peer message and `.agentweave/shared/context.md` is non-empty
- **THEN** the system prepends the shared context to the prompt as current session focus without requiring regeneration of `.agentweave/context/<agent>.md`

---

### Requirement: Agent context onboarding API
The Hub/MCP interface SHALL provide `get_agent_context(agent)` for retrieving runtime context by
agent name. Whether an agent is known SHALL be determined by whether the Hub has a record of it, and
by nothing else.

An agent the Hub knows SHALL receive full runtime context. The system MUST NOT instruct a known agent
to withhold work, to refrain from modifying files, to refrain from claiming tasks, or to wait for
another agent to assign it work. An agent the operator created and addressed is an agent the operator
intends to act.

Generated context MUST NOT refer to `agentweave.yml`, to an agent being "declared", or to a
"principal", unless a real registered agent holds that position.

#### Scenario: A known agent receives runtime context
- **WHEN** `get_agent_context(agent)` is called for an agent the Hub has a record of
- **THEN** the response returns full runtime context including the project profile, the real agent
  roster, project instructions, bound charter guidance or a clear no-charter notice, and communication
  guidance
- **AND** contains no instruction to stand by or withhold work

#### Scenario: A known agent is not told to wait for a principal
- **WHEN** generated context is built for any agent the Hub has a record of
- **THEN** it contains no direction to await assignment before acting
- **AND** names no recipient that is not a registered agent of that project

#### Scenario: Unknown agent receives registration guidance
- **WHEN** `get_agent_context(agent)` is called for an agent the Hub has no record of
- **THEN** the response explains how to register with AgentWeave and does not provide work-taking
  instructions beyond read-only orientation

#### Scenario: Agent context response exposes machine-readable status
- **WHEN** `get_agent_context(agent)` returns successfully
- **THEN** the response includes machine-readable fields for agent name, known status, registered
  status, charter identity, missing context inputs, and markdown context content

---

### Requirement: Role context lookup compatibility
The system SHALL preserve `get_context(charter)` as a direct charter-content lookup while making `get_agent_context(agent)` the preferred onboarding/runtime context API.

#### Scenario: Existing charter lookup still works
- **WHEN** an agent calls `get_context(charter)` with a valid charter identifier
- **THEN** the system returns that charter's content compatible with existing clients

#### Scenario: Charter lookup directs agents to richer context
- **WHEN** `get_context(charter)` returns charter content
- **THEN** the returned content or metadata indicates that `get_agent_context(agent)` should be used for full project and onboarding context when the caller knows its agent name

---

### Requirement: Context diagnostics
The system SHALL provide diagnostics that explain what context each agent receives and whether it is fresh enough to trust.

#### Scenario: Diagnostics list context inputs and outputs
- **WHEN** AgentWeave context diagnostics run
- **THEN** the output lists relevant source files, generated per-agent context files, root bootstrap files, and runner-specific injection mechanisms

#### Scenario: Diagnostics detect incomplete generated context
- **WHEN** generated context is missing required inputs or sections
- **THEN** diagnostics report the issue and identify the Hub-owned configuration that needs attention

#### Scenario: Diagnostics flag placeholder project context
- **WHEN** `.agentweave/ai_context.md` still contains known template placeholders
- **THEN** diagnostics warn that project context is incomplete and identify the file to update

---

### Requirement: An agent is told where it is working

Generated context SHALL state the absolute directory the agent's run executes in, and whether that
directory is an isolated workspace or the project's shared checkout.

Where the workspace is isolated, the context SHALL name the branch it is on and state that other
agents work in separate workspaces whose contents this agent cannot see.

An agent that is not told where it is resolves paths by guessing, and a guess that lands outside its
workspace is refused.

#### Scenario: The working directory is stated

- **WHEN** generated context is built for a run
- **THEN** it names the absolute directory that run will execute in

#### Scenario: Isolation is disclosed, not implied

- **WHEN** the run's workspace is an isolated one
- **THEN** the context says so, names its branch, and states that peers work elsewhere

#### Scenario: A shared checkout is described as shared

- **WHEN** the run executes in the project's shared checkout rather than an isolated workspace
- **THEN** the context describes it as such and does not claim isolation

---

### Requirement: An agent is told what its tools accept

Generated context SHALL describe the tool surface available to the agent, including for each tool the
parameters it takes and, where a parameter is constrained, the values it accepts.

Every tool the agent can call SHALL be described. A tool that exists but is never mentioned cannot be
used deliberately.

The description SHALL derive from the same source as the tool definitions themselves.

#### Scenario: Constrained parameters are described with their values

- **WHEN** generated context describes a tool with a constrained parameter
- **THEN** it lists the accepted values for that parameter

#### Scenario: No callable tool is omitted

- **WHEN** the described tools are compared with the tools the agent can actually call
- **THEN** every callable tool is described

---

### Requirement: Context does not point at content it already contains

Generated context MUST NOT direct an agent to read a file whose contents that same context already
carries.

Such a pointer invites a read that is at best redundant and, where the file lies outside the agent's
permitted paths, is refused — turning delivered information into an apparent failure.

#### Scenario: No pointer to the agent's own context file

- **WHEN** generated context is built
- **THEN** it contains no instruction to read the file that context was written to

### Requirement: A turn bound to a task names the specification that task implements

The system SHALL name, in the turn context, the specification document a bound task implements, and SHALL say how to read it.

An agent given a task and no document path cannot reach the thing it is supposed to build against.
It will guess paths, fail, and fall back to whatever summary it was handed — which is how an
implementation quietly stops matching what was approved.

The wording SHALL treat the document as what the work implements, not as something the operator
happens to be looking at. The two are different claims, and the second one tells an agent not to act
on it.

The system SHALL NOT present a task-derived document as an instruction to author a specification. A
turn spent writing a document instead of implementing one is worse than a turn with no document at
all.

Where the operator is also viewing that same document, the system SHALL render one statement rather
than two. Saying the same thing twice in two framings invites the agent to pick the weaker one.

#### Scenario: A task-bound turn names its document

- **WHEN** an agent's turn is bound to a task that implements a document
- **THEN** the context names that document
- **AND** says how to read it

#### Scenario: The framing is to implement, not to observe

- **WHEN** the context names a document a task implements
- **THEN** it does not describe it as what the operator is viewing

#### Scenario: A task-derived document does not start an authoring turn

- **WHEN** the document was derived from the bound task rather than opened by the operator
- **THEN** the turn is not framed as a specification-authoring turn

#### Scenario: One statement when both would name the same document

- **WHEN** the operator is viewing the same document the bound task implements
- **THEN** the context names it once

### Requirement: An agent granted a capability is told it has it

The system SHALL tell an agent, in its turn context, which operator-conferred capabilities it holds.

A capability an agent does not know it has is one it does not use. An agent that guesses instead is
refused in the middle of a turn, having already spent it.

#### Scenario: A granted agent is told

- **WHEN** an agent has been granted evidence acceptance
- **THEN** its turn context says so

#### Scenario: An ungranted agent is not told it has it

- **WHEN** an agent has not been granted evidence acceptance
- **THEN** its turn context does not claim it has

### Requirement: A withheld capability is stated as plainly as a granted one

Canonical turn context SHALL state the capabilities an agent does **not** hold, alongside those it
does, and SHALL say what to do instead. Announcing a capability only when it is granted SHALL NOT be
treated as sufficient.

The reasoning is already recorded in the code: *a capability an agent does not know it holds is one
it does not use, and one it guesses at is a 403 in the middle of a turn it has already spent.* That
principle is currently applied in one direction only. Measured cost: a reviewer spent a full turn —
a genuine review, running the suite twice and writing a reproducer — before discovering it could not
record the verdict.

Saying what to do instead is load-bearing rather than courteous. Unable to record its verdict, that
reviewer wrote the review to a file inside its own worktree, which is isolated by design, so its
conclusion landed on a branch nobody reads.

#### Scenario: An agent without evidence-decision authority
- **WHEN** canonical context is assembled for an agent not granted evidence-decision authority
- **THEN** the context SHALL state that evidence decisions belong to the operator here
- **AND** SHALL state where to put a verdict instead

#### Scenario: An agent with evidence-decision authority
- **WHEN** canonical context is assembled for an agent granted that authority
- **THEN** the existing granted-capability guidance SHALL be emitted unchanged

#### Scenario: A readable capability that is not writable
- **WHEN** an agent can list a queue it is not permitted to answer
- **THEN** the context SHALL say so before the turn spends effort on it

#### Scenario: Every operator grant, not only the one that was noticed
- **WHEN** canonical context is assembled for any agent
- **THEN** each capability the operator can grant or withhold SHALL be stated in whichever direction applies
- **AND** a grant SHALL NOT be announced when held and silent when withheld

The audit this requirement asked for found the principle applied to one grant of three. The other
two — reading a peer's checkpoints, and recalling the observations a checkpoint cites — appeared in
neither direction: the recall tool was listed among the agent's tools with no mention that a grant
is required, beside a tool that did say so.

#### Scenario: A refusal that is indistinguishable from absence
- **WHEN** a capability's refusal is reported as "not found" rather than as a refusal
- **THEN** the boundary SHALL be stated in context before the turn meets it

This is why the withheld direction matters even where nothing is granted. A refusal that announced
itself would confirm the record exists, so it correctly cannot; the consequence is that an agent
which meets the boundary unprepared concludes the record is missing rather than that it is not
permitted to see it, and reports a broken system in good faith.
