## MODIFIED Requirements

### Requirement: The tools an agent may call are named to it

Canonical turn context SHALL name the tools available to the agent by their exact callable names,
so that reaching a tool does not depend on discovering it.

Where the harness a run executes in exposes those tools under a name of its own making, the context
SHALL use that name, not a shorter form the reader must translate. A note asking the reader to apply
a prefix is weaker than a name that is already correct: measured 2026-08-30 (F139), an agent told to
use the message tool reached for the harness's own similarly named tool, which continues the agent's
own sub-agents and cannot reach an AgentWeave agent, and reported the project's roster as unreachable.
Where the harness's own tools have names a reader could confuse with these, the context SHALL say
once that they are not AgentWeave's.

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

#### Scenario: A run described as having the injected surface, on a harness that prefixes it

- **WHEN** canonical context is assembled for a run described as having the injected tool surface, on a harness whose injected-tool prefix the Hub knows
- **THEN** each AgentWeave tool is named with that prefix, as the run would call it
- **AND** the context states that the harness's similarly named messaging tool does not reach AgentWeave agents

#### Scenario: A run described without the injected surface, on that harness

- **WHEN** canonical context is assembled for a run on that harness that is described in the request form
- **THEN** no tool is named with the injected prefix
- **AND** the context still states that the harness's similarly named messaging tool does not reach AgentWeave agents

#### Scenario: A run whose harness naming is not known

- **WHEN** canonical context is assembled for a run on a harness whose injected-tool naming the Hub does not know
- **THEN** the tools are named as they are declared, with a note that the harness may show them with a prefix
- **AND** the note does not assert that they are prefixed
