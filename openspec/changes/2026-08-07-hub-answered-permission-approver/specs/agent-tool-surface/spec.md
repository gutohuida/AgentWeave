## ADDED Requirements

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
