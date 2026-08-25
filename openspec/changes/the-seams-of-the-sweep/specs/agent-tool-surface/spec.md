## ADDED Requirements

### Requirement: A malformed tool call is refused with the field, the shape, and an example

A tool that refuses a call for a malformed payload SHALL name which field was wrong, what shape it
expects, and SHALL give one minimal working example. Raw validator output SHALL NOT be the whole of
a refusal.

This applies the standard the rest of the surface already meets — *"an agent told merely 'forbidden'
retries the same call"* — to the tool carrying the largest payload, which is currently the one that
does not meet it.

The cost is measured, not assumed. One agent called the document-submission tool **ten times** in a
single turn, guessing at a nested schema from type errors and a link to a validator's website. That
turn recorded **718,650 input tokens** against 73,622 for the turn before it, because every retry
resends the whole conversation. One malformed call cost an order of magnitude more than the work
around it.

#### Scenario: A field is given the wrong type
- **WHEN** a tool call supplies a string where a structured object is required
- **THEN** the refusal SHALL name the field, state the expected shape, and include a minimal example

#### Scenario: A required field is missing
- **WHEN** a tool call omits a required field
- **THEN** the refusal SHALL name the missing field and what it is for

#### Scenario: The refusal is restated where the tool lives
- **WHEN** the standalone tool process shapes a refusal
- **THEN** it SHALL do so without importing beyond its permitted dependencies
- **AND** a test SHALL assert that its restatement and the Hub's own contract agree

### Requirement: The tools an agent may call are named to it

Canonical turn context SHALL name the tools available to the agent by their exact callable names,
so that reaching a tool does not depend on discovering it.

Measured 2026-08-24: an agent did the work correctly — edited the code, added a test, ran the suite,
committed — then looped on tool discovery and ended its turn `completed`, with a confident summary
and **zero evidence rows**. The same agent, asked to do nothing but make that one call, succeeded
immediately. The failure is invisible exactly where it matters: the run reports success while the
record it was asked to write does not exist.

#### Scenario: A turn expected to record evidence
- **WHEN** canonical context is assembled for a turn whose deliverable includes recording evidence
- **THEN** the context SHALL name the evidence-recording tool by its exact callable name

#### Scenario: A tool is named but not reachable
- **WHEN** a named tool cannot be called in this turn
- **THEN** the context SHALL say so rather than name it as available
