## ADDED Requirements

### Requirement: Creating a flow is a distinct tool from creating a loop

The tool surface SHALL offer a distinct tool for creating a flow, rather than distinguishing a flow
from a loop by an optional parameter of one tool.

Creating a flow SHALL require a specification document and SHALL be refused without one. Creating a
loop SHALL be refused when a document is supplied, and the refusal SHALL name the tool that creates a
flow. Each refusal SHALL state why, in the manner the surface already uses for a loop created with no
stop condition.

#### Scenario: Creating a flow without a document is refused

- **WHEN** an agent creates a flow and names no specification document
- **THEN** the call is refused, stating that a flow executes a declared decomposition

#### Scenario: Creating a loop with a document is refused and redirected

- **WHEN** an agent creates a loop and names a specification document
- **THEN** the call is refused, naming the tool that creates a flow

#### Scenario: The two tools write the same records

- **WHEN** a flow and a loop are each created
- **THEN** both produce a job and a loop record, differing only in the declared document
