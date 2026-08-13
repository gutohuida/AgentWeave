# agent-tool-surface

## MODIFIED Requirements

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
