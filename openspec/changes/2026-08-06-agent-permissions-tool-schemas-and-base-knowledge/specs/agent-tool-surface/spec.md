## ADDED Requirements

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
