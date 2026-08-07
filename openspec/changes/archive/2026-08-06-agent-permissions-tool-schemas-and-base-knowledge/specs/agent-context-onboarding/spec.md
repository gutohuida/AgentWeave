## ADDED Requirements

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
