## ADDED Requirements

### Requirement: A run whose harness cannot use MCP is told how to reach the plane
A turn started on an access path without MCP SHALL be told, before the operator's message, that the capability plane is reachable over HTTP, and SHALL be told the plane's base address, the name of the environment variable holding its run credential, how that credential is presented, and where the available operations are described.

The system holds everything such a run needs and, today, says the opposite. The run credential and
the Hub's own address are placed in the spawned process's environment; the notice prepended to the
turn then states that no AgentWeave tool surface is available and instructs the agent to report what
it would have sent instead. An agent that is authenticated and told it is not will not try, and the
operator sees a turn that declined to do reachable work for a stated reason that is false.

This is the deployment the equal-capability requirement was written for: MCP forbidden by policy,
ordinary local API calls permitted. Capability that exists and is unreachable because it was never
described is not capability.

What is named is a variable, never a value. The notice is prepended to the turn prompt, which is the
durable record of the turn, so a credential written into it is a credential written into stored
text. The agent can already read its own environment, so naming the variable discloses nothing it
does not hold; interpolating the value would breach the credential requirement above.

The description of operations is the same description the MCP path is given, rendered for this
access path. It is not a separate list. One source of truth for what the plane offers means an
operation added to the plane cannot be described to one kind of caller and hidden from the other.

#### Scenario: A run without MCP is told the plane is reachable

- **WHEN** a turn begins on an access path that offers no MCP tool surface
- **THEN** the text delivered ahead of the operator's message states that the capability plane is
  reachable, and identifies the plane's base address, the environment variable holding the run
  credential, how that credential is presented on a request, and where the operations are described
- **AND** it does not state that the agent has no way to send messages, create or update tasks, or
  ask the operator

#### Scenario: The credential is named and not disclosed

- **WHEN** any text is delivered to a run describing how to reach the plane
- **THEN** it contains the name of the environment variable holding the run credential
- **AND** it does not contain the credential's value

#### Scenario: One description of the operations, two renderings

- **WHEN** an operation is available on the capability plane
- **THEN** a run on an access path with MCP and a run on an access path without MCP are each told
  that operation is available, in the form their access path uses

## MODIFIED Requirements

### Requirement: HTTP and MCP access have equal capability
Direct HTTP SHALL be the application contract. MCP SHALL be a thin adapter over that contract with the same operations, validation, governance, attribution, and typed failure meaning. An adapter MUST NOT duplicate queue, budget, identity, or lifecycle business rules, MUST NOT hold a governance or waiting rule that the contract does not itself impose on every caller, and MUST NOT silently convert failures into empty or successful results.

Two adapters exist rather than one because MCP is convenient where it is permitted and some
environments forbid MCP servers while still allowing ordinary local API calls. The command-line
interface is **not** one of them: it manages the local application instance and carries no agent
capabilities.

Equal capability is a property of behaviour, not of the route list. Two rules currently live in one
adapter and not in the contract, and both are invisible to a comparison of persisted effects:
archiving scheduled work always puts that exact request to the operator regardless of the run's
permission posture, and asking the operator is a call that waits — returning answers in the order
asked, distinguishing an answer the operator declined to give from one that never arrived, and
reporting the wait's end so that parked work stops claiming somebody is still waiting. A caller that
reaches the same routes directly is subject to neither. The difference is not in what is persisted;
it is in what the caller is required to do first, and in what happens in the gap afterwards.

So a rule that governs one adapter's callers governs the contract's callers. Where a rule cannot be
moved, the adapter holding it is not thin and the capability is not equal, and that is a defect
rather than a division of labour.

#### Scenario: One operation has one persisted result

- **WHEN** equivalent valid actions are performed through HTTP and through MCP
- **THEN** their persisted effects have equivalent content and attribution

#### Scenario: Failure meaning survives adaptation

- **WHEN** the application API returns validation, denied, not-found, or conflict failure
- **THEN** MCP callers receive the same failure meaning

#### Scenario: A governance rule reaches every caller

- **WHEN** an agent action requires the operator's explicit direction before it takes effect
- **THEN** that direction is required of a caller reaching the action directly over HTTP, on the
  same terms as a caller reaching it through an adapter

#### Scenario: Archiving scheduled work is directed, on either path

- **WHEN** an authenticated run archives a scheduled job
- **THEN** the operator's explicit direction for that job is required first, whichever access path
  the run used
- **AND** a standing allowance to create or manage scheduled work does not satisfy it

#### Scenario: A call that waits, waits for every caller

- **WHEN** an authenticated run asks the operator a question through the capability plane
- **THEN** the contract provides that caller a way to wait for the answers, to receive them in the
  order asked, to tell an answer the operator declined to give from one that never arrived, and to
  report that it has stopped waiting
- **AND** none of these depends on which access path the run used

#### Scenario: The CLI offers no agent capability

- **WHEN** an agent attempts to affect shared state through a command-line invocation
- **THEN** no such command exists

#### Scenario: No full project credential is present

- **WHEN** the Hub starts an agent with either adapter available
- **THEN** the process receives its run credential
- **AND** it does not receive a project/operator API key
