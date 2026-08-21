## ADDED Requirements

### Requirement: Document creation is a plane operation with the plane's identity rules

Creating a specification document SHALL be offered on the agent capability plane under the same
terms as every other effect: authenticated by the run credential, attributed to the run, and refusing
any identity supplied by the caller.

It SHALL be reachable identically over HTTP and MCP, so that a client using one is not offered a
capability a client using the other lacks.

#### Scenario: An unauthenticated creation is refused

- **WHEN** document creation is called without a valid run credential
- **THEN** it is refused

#### Scenario: A creation is attributed to the calling run

- **WHEN** an agent creates a document
- **THEN** the resulting record attributes the creation to that run

#### Scenario: The operation exists on both surfaces

- **WHEN** the plane's operations are enumerated
- **THEN** document creation appears over both HTTP and MCP

### Requirement: Creating a document is not gated by a standing project allowance

Document creation SHALL be available to an agent without an operator first enabling it for the
project.

The plane already distinguishes two classes of effect. Scheduled jobs require a standing allowance
because a job is an instruction that invokes a model repeatedly, so an agent that creates one commits
spend the operator did not authorise per occurrence. Tasks, messages, questions and evidence require
none, because they cost nothing to hold and nothing to discard. A document belongs to the second
class.

A capability disabled by default is a capability that is never exercised, and the failure this
allowance would guard against — volume — has no evidence behind it yet.

#### Scenario: Creation works in a project with agent jobs disabled

- **WHEN** an agent creates a document in a project where scheduled agent jobs are not allowed
- **THEN** the creation succeeds
