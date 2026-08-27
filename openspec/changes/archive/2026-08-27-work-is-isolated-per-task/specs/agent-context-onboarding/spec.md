## MODIFIED Requirements

### Requirement: An agent is told where it is working

Generated context SHALL state the absolute directory the agent's run executes in, and whether that directory is an isolated workspace or the project's shared checkout.

Where the workspace is isolated, the context SHALL name the branch it is on and state that other agents work in separate workspaces whose contents this agent cannot see.

Where the workspace belongs to a task rather than to the agent, the context SHALL say so, and the branch it names SHALL be that task's branch rather than a branch named after the agent. An agent told it is on a branch named after itself, while its process is in a checkout on a different branch, will resolve its own history wrongly — and the branch name is what it uses to ask what it has already done.

Where the agent holds other tasks whose work is on other branches, the context SHALL NOT imply that work is present in this checkout.

An agent that is not told where it is resolves paths by guessing, and a guess that lands outside its workspace is refused.

#### Scenario: The working directory is stated

- **WHEN** generated context is built for a run
- **THEN** it names the absolute directory that run will execute in

#### Scenario: Isolation is disclosed, not implied

- **WHEN** the run's workspace is an isolated one
- **THEN** the context says so, names its branch, and states that peers work elsewhere

#### Scenario: A task's workspace is named as the task's

- **WHEN** the run's workspace was provisioned for the task the turn is bound to
- **THEN** the context names that task's branch
- **AND** the branch it names is the one the run's process is actually on

#### Scenario: An unbound turn names the agent's own branch

- **WHEN** the run is bound to no task and runs in the agent's own isolated workspace
- **THEN** the context names the agent's own branch

#### Scenario: A shared checkout is described as shared

- **WHEN** the run executes in the project's shared checkout rather than an isolated workspace
- **THEN** the context describes it as such and does not claim isolation
