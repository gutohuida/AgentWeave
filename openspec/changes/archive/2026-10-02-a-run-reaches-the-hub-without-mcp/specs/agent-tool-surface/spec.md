## ADDED Requirements

### Requirement: The call command is on the run's path and is the program its Hub loaded

The Hub SHALL put a command named `aw-tool` first on the executable search path of every run it spawns, on Windows and on POSIX, and that command SHALL run the tool server program the Hub pinned at start, in its call mode, with no other program in between.

The call command must be the pinned program for the same reason the tool-protocol server must: a
Hub's routes are fixed when it starts, and a program read at another moment can call routes the Hub
does not have. The command is not named `aw`, because that name is already the application's own
command-line interface, and a run whose search path lost the Hub's entry would silently reach that
interface instead.

A run's shell may be a POSIX shell or PowerShell, and on Windows either can be the one a harness
gives it, so the command SHALL resolve by its bare name in both.

Call mode SHALL NOT load the tool-protocol library, so that each call costs a process start and not
a server start, and the program SHALL still be one file, so that the pinned copy remains a
byte-for-byte copy of the program the Hub loaded.

#### Scenario: The command resolves by its bare name in both shells

- **WHEN** a run's shell resolves `aw-tool` by name, in a POSIX shell and in PowerShell
- **THEN** it runs the Hub's launcher for this Hub's pinned tool server

#### Scenario: The launcher runs the pinned program

- **WHEN** the tool server's source file changes on disk after the Hub started
- **AND** a run then calls an operation through `aw-tool`
- **THEN** the program that runs is the one the Hub held at start

#### Scenario: The callable operations are the served operations

- **WHEN** `aw-tool --list` is run from the pinned program, from a directory that is not the package
  root
- **THEN** it lists exactly the tools the server serves over its transport, less the approval
  endpoint the harness calls

#### Scenario: A launcher that cannot be made refuses the run

- **WHEN** the Hub cannot write the launcher for a run
- **THEN** the run is not started, and the reason names the failure to prepare the tool server

### Requirement: A run without the tool-protocol surface is told each tool's call-command form

When a run is described the call command, its canonical context SHALL render every operation it describes in the call-command form, from the same single description of the operations the tool-protocol rendering uses, and SHALL state once that any operation named elsewhere in the turn by its short name is called through the call command.

Operations are named by their short names in many places a turn reads: the checkpoint prompt, the
specification notices, the task instructions. Rewriting every one of them for each access path would
be a second description of each; one rule stated once maps them all.

An operation that waits for the operator SHALL be described with the time it waits, so that the run
can give the command a longer timeout than its shell's default.

#### Scenario: Each operation is rendered as a command

- **WHEN** the canonical context of a run described the call command is rendered
- **THEN** each operation it describes is shown as `aw-tool <operation>` with the argument names its
  arguments file takes

#### Scenario: Short names elsewhere map onto the command

- **WHEN** a run described the call command reads an instruction naming an operation by its short
  name
- **THEN** the context it was given states that the operation is called as `aw-tool <name>` with an
  arguments file

#### Scenario: A waiting operation states its wait

- **WHEN** the context describes asking the operator a question through the call command
- **THEN** it states how many seconds that call waits for this agent
