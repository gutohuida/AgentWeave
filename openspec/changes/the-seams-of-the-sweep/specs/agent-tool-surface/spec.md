## ADDED Requirements

### Requirement: A structured tool parameter advertises its shape in the tool schema

Every structured parameter of a tool SHALL declare its type in the schema clients receive, so that
an object or array parameter is discoverable as such before the tool is called.

**This requirement replaces one that briefly held the opposite, and the reversal is recorded here
rather than dropped.** The measured problem was real: an agent called the document-submission tool
**ten times** in a single turn, guessing at a nested schema from type errors and a link to a
validator's website, and that turn recorded **718,650 input tokens** against 73,622 for the turn
before it, because every retry resends the whole conversation. The first remedy shaped a refusal
that named the field, its shape and a working example. Shaping it required the wrong value to reach
the tool's own code, which meant untyped annotations — so the seven structured fields stopped
advertising `object`/`array` at all. The operator weighed that trade on 2026-08-25 and chose the
schema.

The refusal machinery was removed rather than kept alongside the restored annotations. The framework
validates arguments before a tool body runs, so with the types declared nothing could ever have
reached it — and code that cannot be reached, kept because it looks like a safeguard, is the exact
defect this same change found in its own turn-outcome check. A safeguard nobody can trigger is worse
than no safeguard, because it is counted as one.

#### Scenario: A parameter that takes an object
- **WHEN** a client reads a tool's input schema
- **THEN** a parameter that requires an object SHALL be declared as an object
- **AND** SHALL NOT be declared as accepting any type

#### Scenario: A parameter that takes a list
- **WHEN** a client reads a tool's input schema
- **THEN** a parameter that requires a list SHALL be declared as an array

#### Scenario: The declaration is what is tested
- **WHEN** the tool surface is exercised by a test
- **THEN** the assertion SHALL be made against the schema a client actually receives
- **AND** an untyped parameter SHALL fail that assertion

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
