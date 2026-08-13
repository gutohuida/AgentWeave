# agent-tool-surface

## MODIFIED Requirements

### Requirement: An endpoint the harness calls is not advertised as a capability

A tool that exists to serve the runtime SHALL NOT be described to the agent as one of its own
capabilities, even where it is registered on the same server as the agent's collaboration tools.

The described tool surface exists so an agent knows what it can deliberately use. Listing an endpoint
the harness invokes on the agent's behalf misrepresents what the agent is for and invites calls that
accomplish nothing.

This narrows what is described, not what exists. The requirement that every tool the agent can
deliberately use is described SHALL continue to hold.

**That agreement SHALL be enforced rather than maintained by attention.** Every tool the server
advertises SHALL be either described in the agent's tool surface, or named in an explicit exclusion
carrying the reason it is not — a runtime endpoint, or a tool delivered in the narrower context where
it applies. An omission SHALL fail the build rather than reach an agent.

A described surface that is silently incomplete is worse than one that is absent. Where the same
context both instructs an agent to use a tool and enumerates a surface without it, the agent is given
a contradiction and resolves it against the enumeration — concluding it lacks a capability it holds,
and stopping. This is not hypothetical: it cost a completed interview whose specification was never
written, and it is the second time the hand-maintained list has fallen behind the server.

#### Scenario: A runtime endpoint is omitted from the described surface

- **WHEN** generated context describes the agent's tools
- **THEN** it does not list a tool that exists solely for the runtime to call

#### Scenario: Collaboration tools remain fully described

- **WHEN** generated context describes the agent's tools
- **THEN** every tool the agent can deliberately use is still described

#### Scenario: A newly served tool cannot be silently undescribed

- **WHEN** a tool is added to the served surface and neither described nor explicitly excluded
- **THEN** the discrepancy is reported as a failure

#### Scenario: An exclusion states its reason

- **WHEN** a served tool is excluded from the described surface
- **THEN** the exclusion records why the agent does not need it there

#### Scenario: An instruction never names a tool the surface omits

- **WHEN** generated context instructs the agent to use a named tool
- **THEN** that tool is present in the described surface
