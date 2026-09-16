# agent-loops

## MODIFIED Requirements

### Requirement: A firing's briefing is bounded

The content composed ahead of a loop's job message for each firing SHALL include the loop's purpose, the item claimed for that firing, the acceptance criteria that item carries, and the prior checkpoint content when one exists.

The prior checkpoint content included SHALL be bounded to a fixed size, so that a long-running
loop's accumulated history cannot grow the size of what a single firing is asked to read.

The acceptance criteria included SHALL be bounded to a fixed size for the same reason, stated
differently: a firing's briefing is delivered to the runner as a single command-line argument, and
an operating system's limit on that argument is a limit on whether the turn can start at all. A
briefing that cannot be delivered is worse than one a reader must skim, so no part of it may grow
without a bound.

Where the criteria exceed that bound, the briefing SHALL include them up to it rather than omitting
them, and SHALL make the truncation visible, so that a reader is not left believing they have seen
the whole standard their work is judged against.

#### Scenario: A well-formed prior checkpoint fits in full

- **WHEN** a firing's inherited checkpoint content is within the fixed size bound
- **THEN** the briefing includes it in full

#### Scenario: An oversized prior checkpoint is truncated, not omitted

- **WHEN** a firing's inherited checkpoint content exceeds the fixed size bound
- **THEN** the briefing includes a truncated version up to that bound
- **AND** the briefing is not silently sent with no prior context at all

#### Scenario: A claimed item's acceptance criteria appear in the briefing

- **WHEN** a firing claims an item that carries acceptance criteria
- **THEN** the briefing includes them

#### Scenario: Oversized acceptance criteria are truncated, not omitted

- **WHEN** a claimed item's acceptance criteria exceed the fixed size bound
- **THEN** the briefing includes them up to that bound
- **AND** the briefing is not sent with the criteria silently dropped

#### Scenario: A reader can tell that criteria were truncated

- **WHEN** a claimed item's acceptance criteria are included only up to the bound
- **THEN** what the briefing carries shows that more criteria exist than are shown
