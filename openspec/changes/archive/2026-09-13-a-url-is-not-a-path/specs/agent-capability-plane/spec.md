## MODIFIED Requirements

### Requirement: A run whose harness cannot use MCP is told how to reach the plane

A turn started on an access path without MCP SHALL be told, before the operator's message, that the capability plane is reachable over HTTP, and SHALL be told the plane's base address, the name of the environment variable holding its run credential, how that credential is presented, and where the available operations are described.

The system holds everything such a run needs and, until 2026-09-09, said the opposite. The run
credential and the Hub's own address are placed in the spawned process's environment; the notice
prepended to the turn stated that no AgentWeave tool surface was available and instructed the agent
to report what it would have sent instead. An agent that is authenticated and told it is not will
not try, and the operator saw a turn that declined to do reachable work for a stated reason that was
false.

**Told is not the same as able, and only the first is required here.** Driven 2026-09-09, no
permission posture on a Claude harness let such a run make the request under its own power: the
default `workspace` posture read a URL's path out of the shell command and refused it as outside
the workspace (F300), and the `cli` path's `acceptEdits` has no approver to overrule a harness that
statically refuses an interpolated credential (F301). The first of those no longer holds where the
`workspace` posture's approver runs. A run is told this HTTP form on its first turn, before the
system has grounds to describe MCP, while that posture is deciding its shell commands, and a shell
command naming the run's own Hub address is now allowed there (`agent-run-sandboxing`, *"A network
address in a shell command is decided as a network address"*). The plane is genuinely reachable
from that process environment — the MCP adapter reaches it from exactly there — so the notice is
true, and on the `cli` path what it asks for still cannot be carried out by the agent's own tools.

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
