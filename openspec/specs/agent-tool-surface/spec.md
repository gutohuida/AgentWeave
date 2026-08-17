# agent-tool-surface

## Purpose

Defines what an agent may do through HTTP and MCP, and how that access is
established. Originated by `openspec/changes/2026-07-30-hub-native-experience`; the identity
requirement below carries the `openspec/changes/agent-capability-plane` revision (run-credential
authentication in place of environment-variable binding). `openspec/changes/single-runtime` removed
the per-runner access-path selection and command-based-fallback requirements below, since it deletes
the CLI collaboration commands they depended on — HTTP and MCP are the only two paths now.

**Reconciled 2026-08-07.** The first requirement below previously limited the surface to *causing
effects*, while the next one required an agent to read the task ledger and receive an answer — a
contradiction recorded in `openspec/explorations/2026-08-02-product-direction.md`. The effect-only
sentence is replaced by the least-privilege read boundary that document prescribes; the prohibition
on reading around the delivery system is preserved unchanged.
## Requirements
### Requirement: The Hub supplies state; the tool surface carries intent

The system SHALL supply everything an agent needs in order to begin a turn — its queued entries,
the roster of its collaborators, its charter, and its project's instructions — at the start of
that turn.

Turn-start supply is an onboarding and delivery guarantee, **not** a prohibition on reading during a
turn. The boundary on reads is least privilege rather than grammatical shape: a tool MAY return
information the agent needs for its own work, scoped to the current project and run — for example a
task's detail, or the answer to a question it asked. A tool MUST NOT let an agent read around
delivery or governance — another agent's undelivered queue, secrets, hidden operator state, or
configuration outside its scope — and MUST NOT let an agent alter its own configuration or scope.

#### Scenario: An agent begins a turn already holding what it needs

- **WHEN** a turn begins
- **THEN** the agent has its queued entries, roster, charter, and project instructions
- **AND** it need invoke no tool to obtain them

#### Scenario: Coordination state cannot be read around the Hub

- **WHEN** an agent attempts to read queued or undelivered entries directly
- **THEN** no tool provides them

#### Scenario: An agent cannot widen its own scope

- **WHEN** an agent attempts to alter its own charter, scope, or configuration
- **THEN** no tool permits it

### Requirement: Outbound intent remains available

An agent SHALL retain the ability to message another agent, to create and update work in the shared
task ledger, to read the task ledger, and to ask the operator a question and receive an answer.

These SHALL remain available because they are the agent's only means of affecting shared state, and
each is attributable to the agent and turn that performed it.

#### Scenario: An agent can affect shared state

- **WHEN** an agent sends a message, creates or updates a task, or asks the operator a question
- **THEN** the effect is applied
- **AND** it is attributed to that agent and turn

#### Scenario: Messages sent through the tool surface obey the queue

- **WHEN** an agent sends a message to another agent
- **THEN** it enters the recipient's queue as an entry with a hop depth
- **AND** it is subject to the hop budget

### Requirement: Creating agents and scheduling recurring work are governed, not free

A tool that causes a new agent to exist SHALL be subject to the project's agent budget. A tool that
creates, enables, or triggers recurring scheduled work SHALL be governed by the operator, either by
budget or by explicit approval.

No tool SHALL allow an agent to bring another agent into existence outside the agent budget.

#### Scenario: Agent creation cannot escape the budget

- **WHEN** an agent uses the tool surface to request a further agent
- **THEN** the request is subject to the project's agent budget and approval rules

#### Scenario: Scheduling recurring work requires governance

- **WHEN** an agent creates, enables, or triggers recurring scheduled work
- **THEN** the action is either within a configured allowance or awaits operator approval

### Requirement: An agent's identity is bound by the Hub, never asserted by the agent

An agent's identity SHALL be established by the Hub when it starts the agent, and every effect the
agent causes SHALL be attributed to that identity and run. The application API and every adapter
MUST NOT accept an identity supplied by the caller, and MUST NOT fall back to an unattributed or
placeholder identity.

An agent MUST NOT be able to cause an effect attributed to another agent. Binding an environment
variable without validating a live run credential SHALL NOT by itself satisfy this requirement.

A run credential SHALL be honoured only by the Hub instance that issued it. A Hub instance
receiving an agent action bearing a credential it did not issue SHALL refuse the action and SHALL
NOT apply its effect, whatever database that instance holds.

#### Scenario: Identity comes from authenticated run capability

- **WHEN** an agent causes any effect through HTTP, MCP, or command access
- **THEN** it is attributed to the live run credential established by the Hub
- **AND** no caller-supplied identity is accepted

#### Scenario: Impersonation is impossible

- **WHEN** an agent attempts to cause an effect as another agent
- **THEN** the attempt is refused or remains attributed to its authenticated run

#### Scenario: There is no unattributed effect

- **WHEN** any effect is recorded
- **THEN** it names the agent and run that caused it
- **AND** no effect is recorded against an unknown or placeholder identity

#### Scenario: A credential from another instance is refused

- **WHEN** a Hub instance receives an agent action bearing a run credential it did not issue
- **THEN** the action is refused as unattributable
- **AND** no effect is written to that instance's records

### Requirement: One tool surface, configured automatically

The Hub SHALL configure one tool surface for a spawned run, and an agent SHALL receive it without
the operator wiring anything by hand.

**The surface SHALL be verified as the process actually serves it.** The server is spawned as a
script, and a check that imports the module instead observes a different program: an import executes
the whole file, while running it as a script stops wherever the entry-point guard is and never
returns. A tool defined below that guard registers for every importing test and for no agent.

Verification SHALL therefore spawn the server the way the Hub spawns it, from a working directory
that is not the package root, and read the advertised tools over the transport. The spawned surface
and the imported surface SHALL be equal, and a difference SHALL fail rather than be reported.

#### Scenario: The served surface is read from a spawned process

- **WHEN** the tool surface is verified
- **THEN** the server is started as a subprocess and its tools are listed over its transport

#### Scenario: Spawning and importing agree

- **WHEN** the tools advertised by the spawned server differ from those registered on import
- **THEN** the difference is reported as a failure, naming which tools are missing from which

#### Scenario: A tool below the entry-point guard is caught

- **WHEN** a tool is defined after the block that starts the server
- **THEN** verification fails, rather than passing because the check imported the module

### Requirement: An agent is told the address of the Hub that started it

The Hub SHALL supply each run with the address of the Hub instance that started it, and that
address SHALL be the address the instance is actually serving on.

The address MUST NOT be derived from a configured default, an assumed port, or any value that can
differ from the address in use. Where the operator has explicitly supplied an external address for
the Hub, that address SHALL take precedence, because it is a deliberate deployment statement rather
than an assumption.

If the Hub can determine neither an operator-supplied address nor the address it is serving on, it
SHALL refuse to start the run and record the reason. It MUST NOT start a run carrying a guessed
address.

#### Scenario: The supplied address matches the serving address

- **WHEN** a Hub serving on a given address starts a run
- **THEN** the run is given that address
- **AND** the address does not depend on any configured default

#### Scenario: A non-default port is handled correctly

- **WHEN** a Hub is started on a port other than its configured default and then starts a run
- **THEN** the run is given the port the Hub is actually serving on

#### Scenario: An explicit external address wins

- **WHEN** the operator has explicitly supplied an external address for the Hub
- **THEN** runs are given that address in preference to the observed one

#### Scenario: An undeterminable address stops the run

- **WHEN** the Hub can determine neither an explicit nor an observed address
- **THEN** it refuses to start the run
- **AND** records the reason

### Requirement: A failed tool call is reported, not silently absorbed

When a tool call made by an agent fails, the failure SHALL be reported to the agent with enough
detail to distinguish its cause, and SHALL be recorded by the Hub where the Hub is able to observe
it.

The report SHALL identify which endpoint the call was directed at, so that a call delivered
somewhere other than the intended Hub is diagnosable from the agent's own record of the turn.

A failure the Hub observes SHALL be recorded as an event on the causing agent's timeline, alongside
the run's other recorded outcomes.

#### Scenario: A failure names its destination

- **WHEN** an agent's tool call fails
- **THEN** the reported failure identifies the endpoint the call was directed at

#### Scenario: A failure distinguishes its cause

- **WHEN** an agent's tool call fails
- **THEN** the report distinguishes a rejected request from an unreachable or unintended destination

#### Scenario: An observed failure reaches the operator

- **WHEN** the Hub observes a tool call fail
- **THEN** an event recording the failure and its reason appears on the causing agent's timeline

---

### Requirement: An invocable tool surface is the default, not an opt-in

The Hub SHALL select an invocable configuration by default, wherever a provider offers more than
one way to start a run and only some of those ways permit approvals to be answered per request.

An operator MUST NOT be required to set a flag, edit a runner record, or know a sentinel value in
order for a newly created agent's tool surface to be callable. A runner created through the Hub's
own agent-creation flow, with no further configuration, SHALL produce runs whose tool surface the
agent can actually call.

Where a less capable transport is retained for diagnostic or compatibility reasons, it SHALL be
reachable only by explicit opt-out, and the reported readiness of an agent SHALL reflect the
transport that will actually be used for its next run.

#### Scenario: A newly created agent can collaborate without configuration

- **WHEN** an operator creates an agent through the Hub's agent-creation flow and changes nothing else
- **AND** that agent's provider requires approvals before a tool call proceeds
- **THEN** its runs use a transport in which the Hub answers those approvals
- **AND** its tool calls to the Hub's own surface succeed

#### Scenario: The degraded transport requires an explicit opt-out

- **WHEN** a runner has not opted out of the invocable transport
- **THEN** the invocable transport is used

#### Scenario: Reported readiness matches the transport that will run

- **WHEN** an agent's collaboration readiness is reported
- **THEN** it reflects the transport its next run will actually use
- **AND** an agent that will use an invocable transport is not reported as unable to collaborate

---

### Requirement: A constrained tool parameter declares its valid values

Where a tool parameter accepts only certain values, the tool's published schema SHALL declare those
values. An agent MUST NOT have to discover a constraint by having a call rejected.

The declared values SHALL derive from the same source as the validation that enforces them, so the
two cannot diverge.

A rejection SHALL state, in a sentence a model can act on, what was wrong and what is accepted. It
MUST NOT surface the validator's internal error structure.

#### Scenario: The valid values are visible before the call

- **WHEN** an agent inspects a tool whose parameter accepts only certain values
- **THEN** the schema lists those values

#### Scenario: The schema and the validator agree

- **WHEN** the values a tool declares are compared with the values its server enforces
- **THEN** they are identical

#### Scenario: A rejection is actionable

- **WHEN** a tool call is rejected for an invalid value
- **THEN** the error names the offending parameter and the accepted values in prose

### Requirement: An endpoint the harness calls is not advertised as a capability

A tool that exists to serve the runtime SHALL NOT be described to the agent as one of its own
capabilities, even where it is registered on the same server as the agent's collaboration tools.

The described tool surface exists so an agent knows what it can deliberately use. Listing an endpoint
the harness invokes on the agent's behalf misrepresents what the agent is for and invites calls that
accomplish nothing.

This narrows what is described, not what exists. The requirement that every tool the agent can
deliberately use is described SHALL continue to hold.

#### Scenario: A runtime endpoint is omitted from the described surface

- **WHEN** generated context describes the agent's tools
- **THEN** it does not list a tool that exists solely for the runtime to call

#### Scenario: Collaboration tools remain fully described

- **WHEN** generated context describes the agent's tools
- **THEN** every tool the agent can deliberately use is still described

