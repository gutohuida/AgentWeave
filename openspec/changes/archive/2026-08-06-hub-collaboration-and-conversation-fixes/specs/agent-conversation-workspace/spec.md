## ADDED Requirements

### Requirement: A delivered turn reaches the model intact

Every queued input the Hub marks as delivered SHALL reach the agent's model in full. The Hub
MUST NOT report an input as delivered when the mechanism used to start the run cannot carry it.

Where a platform's process-launch path can alter, truncate, or reinterpret a run's arguments —
for example a command interpreter that parses a command line before the target program receives
it — the Hub SHALL use a launch path that preserves them exactly, including argument content
that spans multiple lines.

#### Scenario: A multi-line turn prompt is delivered whole

- **WHEN** the Hub starts a run whose turn prompt spans several lines
- **THEN** the agent receives every line of that prompt

#### Scenario: Delivery state reflects what the model actually received

- **WHEN** a queued input is marked delivered against a run
- **THEN** that input's full content formed part of the prompt that run was started with

---

### Requirement: A turn's folded state is set by the operator, never by its position

A turn SHALL render expanded unless the operator has folded it. Foldedness MUST NOT be derived from
a turn's position in the conversation, and appending a new turn MUST NOT change the folded state of
any existing turn.

Every turn SHALL be foldable, including the most recent one. A turn the operator has folded SHALL
stay folded, and a turn the operator has expanded SHALL stay expanded, as the conversation grows.

#### Scenario: Sending a message does not collapse what the operator was reading

- **WHEN** the operator is reading an expanded turn and submits a new message
- **THEN** that turn remains expanded when the new turn appears

#### Scenario: Every turn can be folded

- **WHEN** a conversation contains a single turn
- **THEN** a control to fold that turn is available

#### Scenario: A manual fold survives new turns

- **WHEN** the operator folds a turn and a new turn is then appended
- **THEN** the folded turn remains folded

---

### Requirement: The operator's own messages are neutral, not accented

An operator message SHALL be distinguished from an agent message by placement and by neutral
surface treatment. It MUST NOT be tinted with the interface's chromatic accent colour, which is
reserved for focus and selection state.

#### Scenario: The operator's message carries no accent hue

- **WHEN** an operator message is rendered in the conversation
- **THEN** its background and border derive from the neutral surface and border scales
- **AND** neither derives from the accent colour

---

### Requirement: The composer is separated from the conversation by its border alone

The composer surface SHALL be distinguished from the page ground plane by its border and its own
surface colour. It MUST NOT be surrounded by a shadow, gradient, or fill that reads as a second,
darker region enclosing it.

#### Scenario: No enclosing dark region

- **WHEN** the composer is displayed against the conversation background
- **THEN** no shadow or gradient draws a darker area around it
- **AND** its separation is carried by its border and surface colour
