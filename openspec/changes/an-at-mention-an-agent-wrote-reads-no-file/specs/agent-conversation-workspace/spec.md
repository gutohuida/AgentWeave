## MODIFIED Requirements

### Requirement: A delivered turn reaches the model intact

Every queued input the Hub marks as delivered SHALL reach the agent's model in full. The Hub
MUST NOT report an input as delivered when the mechanism used to start the run cannot carry it.

Where a platform's process-launch path can alter, truncate, or reinterpret a run's arguments —
for example a command interpreter that parses a command line before the target program receives
it — the Hub SHALL use a launch path that preserves them exactly, including argument content
that spans multiple lines.

In full does not mean byte for byte in one respect. An input the operator did not write reaches the
prompt with each file mention neutralised, as `agent-run-sandboxing` requires (*Text the operator
did not write reaches a run without a file mention its harness would expand*). That is the only
change delivery makes to an input's content: nothing is dropped, and every other character reaches
the prompt as it was queued.

#### Scenario: A multi-line turn prompt is delivered whole

- **WHEN** the Hub starts a run whose turn prompt spans several lines
- **THEN** the agent receives every line of that prompt

#### Scenario: Delivery state reflects what the model actually received

- **WHEN** a queued input is marked delivered against a run
- **THEN** that input's full content formed part of the prompt that run was started with, with its
  file mentions neutralised where the operator did not write it

#### Scenario: Neutralising a mention drops nothing

- **WHEN** a queued input from another agent that contains a file mention is delivered
- **THEN** every character of its content reaches the prompt, and the only difference is the
  neutralisation of each mention
