## ADDED Requirements

### Requirement: A Copilot worker invocation is offered no tool

A worker or conversation-title invocation run on a `copilot` runner SHALL remove every tool Copilot would offer the model, and SHALL NOT rely on an empty tool allow-list to do so.

A worker's prompt is transcript text the Hub did not write, so a prompt injection in it must find
nothing to act with. Copilot's non-interactive mode requires every tool to be pre-approved, so any
tool left available is a tool the injected text could use without being asked. An empty allow-list
is read by Copilot as no filter at all, which would leave every tool available.

The invocation SHALL spawn the Copilot CLI's native executable, SHALL run under a Copilot home the
Hub owns for one-shot calls, and SHALL receive no GitHub token variable the Hub merely inherited. A
Copilot CLI that cannot be found SHALL be recorded as a spawn failure, not raised into the caller.

#### Scenario: A checkpoint generated on Copilot has no tools

- **WHEN** a checkpoint is generated with a `copilot` runner
- **THEN** the spawned command removes every built-in, MCP and custom tool
- **AND** the command carries no empty tool allow-list

#### Scenario: A missing Copilot CLI is recorded

- **WHEN** a worker invocation is requested on a `copilot` runner and no Copilot executable can be resolved
- **THEN** the invocation is recorded as a spawn failure naming the path that was looked for
- **AND** no exception propagates to the caller

#### Scenario: A Copilot title is taken from the answer

- **WHEN** a conversation on a `copilot` runner is titled
- **THEN** the title is taken from the answer inside Copilot's JSON output, not from the last line of that output
