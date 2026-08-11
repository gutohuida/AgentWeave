## ADDED Requirements

### Requirement: A turn renders in execution order

The entries of a turn SHALL be presented in the order they occurred. Tool activity MUST NOT be
hoisted ahead of text that preceded it.

Consecutive tool activity SHALL be grouped into a single collapsible block positioned where that
activity occurred in the turn. A turn containing several separated runs of tool activity SHALL
present several such blocks, each in its own position.

#### Scenario: Work stays behind the text that preceded it

- **WHEN** a turn produced text, then tool activity, then further text, then further tool activity
- **THEN** the rendered order is that text, a work block, the further text, and a further work block

#### Scenario: Consecutive tool activity is one block

- **WHEN** a turn produced several tool calls with no intervening text
- **THEN** those calls are presented as a single work block

#### Scenario: A turn of only tool activity is unchanged

- **WHEN** a turn produced tool activity and no interleaved text
- **THEN** that activity is presented as one work block, as before

### Requirement: Each work block carries independent state

Every work block in a turn SHALL carry its own expansion state and its own reported duration.
Expanding one block MUST NOT expand another.

A block's reported duration SHALL span that block's own first and last entry.

Tool-use and tool-result pairing SHALL be resolved within a block. A tool result MUST NOT be paired
with a tool use from a different block.

#### Scenario: Blocks expand independently

- **WHEN** a turn presents two work blocks and the operator expands the first
- **THEN** the second remains collapsed

#### Scenario: Duration describes the block

- **WHEN** a work block reports a duration
- **THEN** that duration spans the block's own first and last entry rather than the whole turn

#### Scenario: Pairing does not cross blocks

- **WHEN** a turn presents several work blocks
- **THEN** each tool result is rendered inline with the tool use it pairs with inside the same block
