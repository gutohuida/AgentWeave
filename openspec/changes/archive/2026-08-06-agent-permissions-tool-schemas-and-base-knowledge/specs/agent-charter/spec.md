## ADDED Requirements

### Requirement: Seeded charters describe only what the runtime provides

Seeded charters SHALL describe only mechanisms the runtime actually offers. A charter's content is
injected into an agent's context verbatim, so a charter is instruction, not documentation.

A seeded charter MUST NOT instruct an agent to read a file the system does not create, run a command
that does not exist, or address a participant the roster does not contain.

Where a charter would once have told an agent to gather its orientation, it SHALL instead rely on the
context it is given: the roster, the project instructions, and the charter itself all arrive with the
turn, and nothing needs to be read before starting.

#### Scenario: A seeded charter cites no absent file

- **WHEN** a seeded charter's content is examined
- **THEN** it instructs the agent to read no file the system does not create

#### Scenario: A seeded charter cites no absent command

- **WHEN** a seeded charter's content is examined
- **THEN** it names no command the shipped runtime does not provide

#### Scenario: Orientation comes from the turn, not from retrieval

- **WHEN** a seeded charter describes how an agent should begin
- **THEN** it relies on the roster, instructions, and charter already supplied with the turn
