# agent-conversation-workspace

## ADDED Requirements

### Requirement: Message-level conversation entries render Markdown, safely

Operator input, agent text output, and peer traffic SHALL be rendered as Markdown — fenced code,
emphasis, lists, links, and tables render as their formatted equivalents rather than as literal
syntax characters. A single newline with no following blank line SHALL render as a line break within
the same paragraph, not be collapsed into it.

The renderer MUST NOT interpret raw HTML found in entry content as markup. Content that is not valid
or recognized Markdown SHALL render as plain text, visually equivalent to rendering it with no
Markdown syntax present at all.

This requirement covers message-level text only. Tool-call content (a tool's input or output, and
its summary label) is governed by the tool-call formatting requirement below and is unaffected by
this one.

#### Scenario: Formatting syntax renders as formatting

- **WHEN** a conversation entry's content contains Markdown syntax (a fenced code block, a bulleted
  list, bold or italic emphasis, or a link)
- **THEN** it is rendered as the corresponding formatted element
- **AND** no literal Markdown syntax character is visible in the rendered output

#### Scenario: A single newline is preserved as a line break

- **WHEN** an entry's content contains two lines separated by exactly one newline, with no blank
  line between them
- **THEN** both lines are rendered with a visible break between them
- **AND** they are not collapsed into a single unbroken line

#### Scenario: Raw HTML in content is never interpreted as markup

- **WHEN** an entry's content contains a literal HTML tag
- **THEN** the tag's characters are rendered as visible text
- **AND** no corresponding DOM element is created from it

#### Scenario: Plain text is unaffected

- **WHEN** an entry's content contains no Markdown syntax
- **THEN** its rendered appearance is unchanged from rendering it as plain text

### Requirement: A tool call is formatted by what kind of tool it was

A tool-call entry in the conversation timeline SHALL be presented with an icon and a label specific
to the tool it names, drawn from a fixed mapping keyed on the tool's recorded name. A tool name the
mapping does not recognize SHALL fall back to a generic icon and label rather than rendering no icon
or throwing.

Where a tool call's recorded input can be parsed as carrying both a prior and a new value for the
same content — the shape a file-editing tool call carries — its expanded view SHALL render that
change as a diff, distinguishing added and removed content, rather than as two independent blocks of
raw text.

Where a tool call's recorded input cannot be parsed this way, was truncated before being recorded, or
does not carry both values, its expanded view SHALL render the existing raw input and output text
unchanged. A diff MUST NOT be attempted against content known to have been truncated.

#### Scenario: A recognized tool shows its own icon and label

- **WHEN** a tool-call entry names a tool the mapping recognizes
- **THEN** it is rendered with that tool's icon and label
- **AND** a different recognized tool in the same conversation renders with a different icon and
  label

#### Scenario: An unrecognized tool falls back, not blank

- **WHEN** a tool-call entry names a tool the mapping does not recognize
- **THEN** it is rendered with the fallback icon and label
- **AND** rendering does not fail

#### Scenario: An edit-shaped tool call renders as a diff

- **WHEN** a tool-call entry's recorded input parses to an object carrying both a prior and a new
  value for the same content
- **THEN** its expanded view renders the change as a diff
- **AND** added and removed content are visually distinguished from each other and from unchanged
  content

#### Scenario: A malformed or truncated tool call falls back to raw text

- **WHEN** a tool-call entry's recorded input cannot be parsed as carrying both a prior and a new
  value, or is recorded as truncated
- **THEN** its expanded view renders the existing raw input and output text
- **AND** no diff is attempted against it
