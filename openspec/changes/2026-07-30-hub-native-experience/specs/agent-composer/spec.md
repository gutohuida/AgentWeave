## ADDED Requirements

### Requirement: The composer accepts multi-line input with predictable submission

The agent conversation surface SHALL provide a composer that grows with its content up to a bound
and then scrolls. Submission and newline insertion MUST be distinct, predictable gestures.

#### Scenario: The composer grows and then scrolls

- **WHEN** the operator types content exceeding one line
- **THEN** the composer grows to fit up to its maximum height
- **AND** beyond that height it scrolls rather than growing further

#### Scenario: Submit and newline are distinct

- **WHEN** the operator presses the submit key without the newline modifier
- **THEN** the message is sent
- **WHEN** the operator presses the submit key with the newline modifier
- **THEN** a newline is inserted and nothing is sent

#### Scenario: Draft content survives navigation

- **WHEN** the operator types a draft, navigates away from the conversation, and returns
- **THEN** the draft is still present

### Requirement: The composer detects inline triggers at the cursor

The composer SHALL detect an active trigger at the cursor position and report its kind, its query
text, and the text range it occupies. Supported kinds SHALL include a path reference, a slash
command, and a skill reference.

A slash command SHALL be recognized only at the start of a line. A path or skill reference SHALL be
recognized only at the start of a whitespace-delimited token.

#### Scenario: A slash command is recognized at line start

- **WHEN** the cursor follows a slash-prefixed token at the beginning of a line
- **THEN** a slash-command trigger is reported with the typed query

#### Scenario: A slash inside prose is not a command

- **WHEN** the cursor follows a slash that is not at the start of a line, such as within a URL or path fragment
- **THEN** no slash-command trigger is reported

#### Scenario: Path and skill references are recognized at token start

- **WHEN** the cursor follows a token beginning with the path-reference sigil
- **THEN** a path trigger is reported with the remainder of the token as the query
- **WHEN** the cursor follows a token beginning with the skill sigil
- **THEN** a skill trigger is reported with the remainder of the token as the query

#### Scenario: A trigger closes when its token ends

- **WHEN** the operator types a whitespace character after a path or skill reference
- **THEN** no trigger is reported

### Requirement: Trigger results are chosen from a keyboard-navigable menu

When a trigger is active the composer SHALL present matching results in a menu navigable entirely
by keyboard. Accepting a result SHALL replace exactly the trigger's text range and place the cursor
immediately after the inserted text.

#### Scenario: The menu is operable without a pointer

- **WHEN** a trigger menu is open
- **THEN** the operator can move the selection, accept the selection, and dismiss the menu using the keyboard alone

#### Scenario: Acceptance replaces the trigger range and positions the cursor

- **WHEN** the operator accepts a result
- **THEN** only the trigger's range is replaced by the result's insertion text
- **AND** the cursor is positioned directly after the inserted text

#### Scenario: References containing spaces remain intact

- **WHEN** an accepted path reference contains spaces or quotation marks
- **THEN** it is inserted in a form that preserves it as a single reference

#### Scenario: Dismissal preserves typed text

- **WHEN** the operator dismisses an open trigger menu
- **THEN** the typed text is left unchanged and the composer retains focus

### Requirement: The composer displays live context-window usage

The conversation surface SHALL display the agent's current context-window consumption, derived
from the most recent context-usage event reported for that agent.

The indicator SHALL animate between values, SHALL show a distinct state when consumption is
critically high, and SHALL expose exact figures on demand.

#### Scenario: Usage reflects the latest reported event

- **WHEN** a context-usage event is received for the displayed agent
- **THEN** the indicator reflects the values from that event

#### Scenario: The indicator animates rather than jumping

- **WHEN** reported usage changes
- **THEN** the indicator transitions to the new value over a duration from the shared motion scale

#### Scenario: Critical consumption is visually distinct

- **WHEN** reported usage exceeds the critical threshold
- **THEN** the indicator renders in its critical treatment

#### Scenario: Exact figures are available on demand

- **WHEN** the operator hovers or focuses the indicator
- **THEN** used and maximum token counts and the used percentage are shown in abbreviated, tabular form

#### Scenario: Unknown capacity degrades gracefully

- **WHEN** the maximum context size is unknown
- **THEN** consumed tokens are shown without a percentage or progress fill

### Requirement: The active agent can be changed from the conversation

The operator SHALL be able to see which agent is handling a conversation and change it without
leaving the conversation. The selector SHALL be searchable when more than a handful of choices
exist, and SHALL indicate which choices are currently launchable.

#### Scenario: The active agent is visible and switchable in place

- **WHEN** the operator opens the agent selector from the conversation
- **THEN** the current agent is indicated
- **AND** selecting another agent applies to the next turn without leaving the conversation

#### Scenario: Choices are searchable and filterable by typing

- **WHEN** the operator types in the selector
- **THEN** the list narrows to matching choices

#### Scenario: Unavailable agents are marked

- **WHEN** a configured agent is not currently launchable
- **THEN** it is shown with its unavailability and the stated reason
