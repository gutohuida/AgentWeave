## ADDED Requirements

### Requirement: A run's end closes the tool calls it left open
When a run ends as `stopped` or `failed` on a path that writes the run's terminal status line, the Hub SHALL persist, for each `tool_use` the run recorded with a call identifier and no matching `tool_result`, one closing `tool_result` carrying the same call identifier and tool, `is_error: false`, and `status: "interrupted"`, and SHALL persist those rows after every output the runner recorded and before the run's terminal status line. A failure to persist a closing row MUST NOT change how the run ended.

A provider is not relied on to close its own calls on a cancel. ACP assigns that to the client: on
`session/cancel` the client SHOULD mark every non-finished tool call of the turn as cancelled. A run
that ends without a terminal status line gains no closing rows: one whose runner transport raised,
one cancelled by a Hub shutdown, and one reconciled after a restart. Its calls are presented as
ended under *An ended run's unanswered tool call is presented as ended*.

The optional payload key `status` is additive under *Versioned kind-specific payloads*: `version`
stays 1 and the required `tool_result` fields are unchanged.

#### Scenario: Stop during a shell call closes the call

- **WHEN** a Copilot run records a `tool_use` for a shell command and the operator presses Stop
  before Copilot reports the call's result
- **THEN** the run's outputs, in the order the outputs route returns them, contain that `tool_use`,
  then a `tool_result` with the same call identifier and `status: "interrupted"`, then the terminal
  status row

#### Scenario: Rows the runner wrote after the call come before the closing row

- **WHEN** a run records a `tool_use`, then a non-work row such as a diagnostic notice or an error,
  and then ends as `stopped` or `failed` with the call unanswered
- **THEN** the outputs read `tool_use`, the non-work row, the closing `tool_result`, then the
  terminal status row

#### Scenario: A failed run closes its open calls

- **WHEN** a run ends as `failed` while a recorded `tool_use` has no result, including a turn that
  timed out and was cancelled
- **THEN** a closing `tool_result` with `status: "interrupted"` is persisted for it before the
  terminal status row

#### Scenario: A call the provider closed is not closed twice

- **WHEN** the provider reports a call's result after the cancel and before the turn ends
- **THEN** that call has exactly one `tool_result`, the provider's

#### Scenario: A completed run is not closed

- **WHEN** a run ends as `completed` while a recorded `tool_use` has no result
- **THEN** no closing `tool_result` is persisted for it

#### Scenario: A call without an identifier gets no invented result

- **WHEN** a run ends as `stopped` while a `tool_use` without a call identifier has no result
- **THEN** no closing `tool_result` is persisted for it

### Requirement: An ended run's unanswered tool call is presented as ended
The shared stream renderer SHALL present a tool call as `interrupted` when its result carries `status: "interrupted"`, or when no `tool_result` with its call identifier exists anywhere in its turn and its run's facts report `stopped`, `interrupted` or `failed`; SHALL present it as `no result` when no result for it exists anywhere in its turn and its run completed; SHALL present it as awaiting its result only when it has no result and its run is not known to have ended; and SHALL NOT count an `interrupted` call as a failure.

This holds for runs recorded before the Hub wrote closing rows, and for runs that ended without a
terminal status line, on a live view and after a reload. A call whose result was recorded in a
different work block of the same turn has a result, and is presented by that result. So is a call
whose provider reported a result after a cancel: a result the provider marked as an error is
presented as `failed`, even in a stopped run.

#### Scenario: A stopped run's unanswered call reads interrupted

- **WHEN** a conversation renders a run whose facts report `stopped` and whose outputs are a
  `tool_use` with no result followed by the terminal status row
- **THEN** the tool call is shown as `interrupted`, not as awaiting its result

#### Scenario: A closing row is not a failure

- **WHEN** a tool call's paired result carries `status: "interrupted"` and `is_error: false`
- **THEN** the call is shown as `interrupted` and its work block counts no failure for it

#### Scenario: A completed run's unanswered call says it has no result

- **WHEN** a run's facts report `completed` and a `tool_use` in it has no result anywhere in its
  turn
- **THEN** the tool call is shown as `no result`

#### Scenario: A result in another work block is the call's result

- **WHEN** a completed run records a `tool_use`, then a diagnostic notice, then the `tool_result`
  for the same call identifier
- **THEN** the tool call is shown with that result, as `completed`, and not as `no result` or as
  awaiting its result

#### Scenario: A run not known to have ended still awaits

- **WHEN** a tool call has no result in its turn and its run's facts are absent or not terminal
- **THEN** the tool call is shown as awaiting its result

### Requirement: Each work block carries its own state, and pairing spans the turn

Every work block in a turn SHALL carry its own expansion state and its own reported duration.
Expanding one block MUST NOT expand another.

A block's reported duration SHALL span that block's own first and last entry.

Tool-use and tool-result pairing SHALL be resolved across the turn, by call identifier. A turn is
the entries of one run, so pairing MUST NOT cross runs. The first tool result in the turn whose
call identifier matches a tool use in that turn SHALL be rendered inline with that tool use, in the
tool use's block, and MUST NOT also be rendered as a row of its own. Any other tool result,
including a later one with an identifier already paired and one whose identifier matches no tool
use in the turn, SHALL be rendered as a row of its own. A work block whose every entry is rendered
elsewhere SHALL NOT be presented. A block's failure count SHALL count the results rendered in that
block.

#### Scenario: Blocks expand independently

- **WHEN** a turn presents two work blocks and the operator expands the first
- **THEN** the second remains collapsed

#### Scenario: Duration describes the block

- **WHEN** a work block reports a duration
- **THEN** that duration spans the block's own first and last entry rather than the whole turn

#### Scenario: Pairing crosses blocks within a turn

- **WHEN** a turn records a tool use, then a non-work row such as a diagnostic notice, then the tool
  result for the same call identifier
- **THEN** the tool result is rendered inline with that tool use in the tool use's block, and is
  not rendered again on its own

#### Scenario: A result without its call still renders

- **WHEN** a turn holds a tool result whose call identifier matches no tool use in that turn
- **THEN** the tool result is rendered as a row of its own

#### Scenario: A second result for a call still renders

- **WHEN** a turn holds a tool use and two tool results with its call identifier
- **THEN** the first result is rendered inline with the tool use, and the second is rendered as a
  row of its own

#### Scenario: Pairing does not cross runs

- **WHEN** two runs each record a tool use with the same call identifier, and only the first run
  records a result for it
- **THEN** the second run's tool use is not presented with the first run's result

## REMOVED Requirements

### Requirement: Each work block carries independent state

**Reason**: Its rule that a tool result MUST NOT be paired with a tool use from a different block
leaves a real call reading `awaiting result` when its result is recorded after a non-work row. In
the trial DB that is 6 of 50 `tool_use` rows in 5 completed runs, and it would put this change's
own closing row in a block of its own (design D7, open question `wpc7-d`). Removed only under
`wpc7-d` (i); under (iii) this requirement stays and its replacement above is dropped.

**Migration**: Replaced by *Each work block carries its own state, and pairing spans the turn*,
which keeps the per-block expansion and duration rules word for word and resolves pairing across
the turn by call identifier.
