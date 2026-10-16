## ADDED Requirements

### Requirement: A run told the call command is told to name each arguments file afresh

Wherever the Hub describes the call command to a run, in the turn-start notice and in the tool
section of the canonical context, it SHALL tell the run to use a new arguments file name for each
call, and to write corrected arguments to a new file rather than editing an earlier one, because the
run's file-writing tool may refuse to overwrite a file that already exists.

A specification turn keeps a tool that creates a file but none that replaces one. A name reused
within a turn therefore leaves such a run only the shell fallback, and leaves any run reading a file
it did not mean to reuse. A new name for each call never meets an existing file.

#### Scenario: The notice says to use a new name for each call

- **WHEN** a run is told at turn start to reach the Hub through the call command
- **THEN** the notice says to use a new file name for each call and to write corrected arguments to a
  new file

#### Scenario: The tool section says the same

- **WHEN** the canonical context of a run described the call command is rendered
- **THEN** its tool section says to use a new arguments file name for each call
