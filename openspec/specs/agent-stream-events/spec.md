# agent-stream-events Specification

## Purpose
TBD - created by archiving change add-agent-stream-kinds. Update Purpose after archive.
## Requirements
### Requirement: Canonical runner event envelope
The Hub's direct-execution path SHALL normalize supported runner output into a provider-neutral parser result containing
zero or more output events, an independent optional usage sample, optional session changes, and
control flags.

Each output event SHALL contain a `kind`, readable `content`, and versioned structured `payload`.

#### Scenario: One provider line produces multiple events
- **WHEN** a provider line contains multiple independently displayable content blocks
- **THEN** the parser result SHALL preserve those blocks as ordered output events

#### Scenario: Usage arrives without displayable output
- **WHEN** a provider event reports token usage but has no user-readable content
- **THEN** the parser result SHALL preserve the usage sample without fabricating an output event

### Requirement: Closed event-kind taxonomy
Normalized output events SHALL use exactly one of `text`, `thinking`, `tool_use`, `tool_result`,
`status`, `diagnostic`, or `error`.

Successful run completion SHALL be represented as `status`; failed run completion SHALL be
represented as `error`; a failed tool invocation SHALL remain `tool_result` with `is_error=true`.

#### Scenario: Runner completes successfully
- **WHEN** a runner reports successful turn completion
- **THEN** the Hub SHALL emit a `status` event whose payload phase is `completed`

#### Scenario: Tool returns an error
- **WHEN** a tool result reports failure
- **THEN** the Hub SHALL emit a `tool_result` event with `is_error=true` rather than a top-level `error`

### Requirement: Versioned kind-specific payloads
Every structured payload SHALL include `version=1` and satisfy the schema for its event kind.

Text and thinking payloads SHALL carry readable text. Tool-use and tool-result payloads SHALL carry
correlation and summary fields. Status payloads SHALL carry a lifecycle phase. Diagnostic payloads
SHALL identify stream and severity. Error payloads SHALL carry a stable code and readable message.

#### Scenario: Event is serialized
- **WHEN** a normalized event is sent to the Hub
- **THEN** its payload SHALL contain `version=1` and the fields required by its kind

#### Scenario: Payload is unavailable
- **WHEN** an old producer submits content without a structured payload
- **THEN** the Hub SHALL accept and preserve the readable content

### Requirement: Tool-call correlation
Tool-use and tool-result events SHALL retain the provider's call identifier as `call_id` whenever
the provider supplies one, and SHALL preserve a readable tool name and summary.

#### Scenario: Tool call has a provider identifier
- **WHEN** a provider emits a tool invocation followed by its result
- **THEN** both normalized events SHALL carry the same `call_id`

#### Scenario: Provider omits a call identifier
- **WHEN** a provider emits tool activity without a call identifier
- **THEN** the events SHALL remain renderable as unpaired tool activity without inventing a provider identifier

### Requirement: Run identity and deterministic ordering
Every Hub-triggered run SHALL receive a unique `run_id`, and each emitted event within that
run SHALL receive a monotonically increasing `sequence` assigned after normalization.

#### Scenario: Events share an invocation
- **WHEN** multiple output events are emitted by one runner invocation
- **THEN** they SHALL share a `run_id` and have strictly increasing sequence values

#### Scenario: Runner is retried
- **WHEN** the Hub starts another process attempt after a stale-session or transient failure
- **THEN** the new invocation SHALL receive a new `run_id`

### Requirement: Supported runner normalization
The system SHALL normalize the installed or documented streaming formats for Claude and Codex into
the canonical event contract.

#### Scenario: Claude emits content blocks
- **WHEN** Claude emits readable thinking, text, tool-use, tool-result, result, or error data
- **THEN** the adapter SHALL map each item to the corresponding canonical event and retain usage separately

#### Scenario: Codex emits JSONL items
- **WHEN** Codex emits reasoning, agent-message, command, file-change, MCP-call, web-search,
  plan-update, lifecycle, or error events
- **THEN** the adapter SHALL map them to canonical events without exposing raw JSONL as user content

### Requirement: Unknown provider events degrade safely
Runner adapters SHALL tolerate syntactically valid provider events that they do not recognize.
They SHALL either omit non-user-relevant events or emit bounded `diagnostic` events without
terminating the runner stream.

#### Scenario: Provider adds a new event type
- **WHEN** an adapter receives a valid but unknown event type
- **THEN** parsing SHALL continue and later recognized events SHALL still be emitted

#### Scenario: Stream line is malformed
- **WHEN** a runner produces malformed structured output
- **THEN** the Hub SHALL preserve a bounded diagnostic or readable fallback and continue when safe

### Requirement: Structured payload safety
The Hub SHALL recursively redact known secret patterns before transport and SHALL NOT persist
complete raw provider events, opaque reasoning blobs, or encrypted reasoning fields.

Redaction SHALL be bounded so that it does not consume identifiers that are not secrets. In
particular it SHALL NOT redact the Hub's own vocabulary — the MCP tool names it publishes and the
document slugs it mints from titles agents choose. A rule that matches any sufficiently long
identifier removes precisely the identifier that tells the operator *which* document an agent read,
and it does so to catch credentials the recognized-prefix rules have already caught.

The serialized payload SHALL be at most 64 KiB, and a retained tool-result excerpt SHALL be at most
8 KiB. Truncated payloads SHALL preserve readable content and set `truncated=true`.

#### Scenario: Tool input contains a secret
- **WHEN** normalized structured input contains a recognized credential or secret
- **THEN** the secret SHALL be redacted before the event leaves the Hub's direct-execution path

#### Scenario: A long identifier that is not a secret
- **WHEN** a payload contains a published MCP tool name or a Hub-minted document slug of any length
- **THEN** it SHALL survive redaction intact

#### Scenario: A credential with no recognized prefix
- **WHEN** a payload contains a long high-entropy token with no separators
- **THEN** it SHALL be redacted

#### Scenario: Tool output exceeds its bound
- **WHEN** a tool result is larger than 8 KiB
- **THEN** the stored result excerpt SHALL be bounded, the summary SHALL remain readable, and `truncated` SHALL be true

#### Scenario: Provider emits opaque reasoning
- **WHEN** a provider event contains encrypted or otherwise opaque reasoning data
- **THEN** that field SHALL NOT be copied into content or payload

### Requirement: Additive Hub persistence and transport
Agent output persistence, creation requests, responses, and SSE events SHALL support nullable
`kind`, `payload`, `run_id`, and `sequence` fields in addition to existing content, session, and
timestamp fields.

The Hub SHALL validate allowed kinds and payload bounds independently of upstream parser validation.

#### Scenario: New producer posts a structured event
- **WHEN** the Hub receives valid content with structured stream fields
- **THEN** it SHALL persist and return those fields through REST and SSE

#### Scenario: Hub receives an invalid kind or oversized payload
- **WHEN** an output creation request violates the event contract
- **THEN** the Hub SHALL reject the structured fields with a validation response and SHALL NOT persist unsafe payload data

### Requirement: Cross-version compatibility
The system SHALL remain compatible with existing text-only producers, text-only database rows, and
clients that ignore unknown response fields. Every new structured event SHALL retain meaningful
`content` as a plain-text and accessibility fallback.

#### Scenario: Legacy row is read
- **WHEN** an output row has null structured fields
- **THEN** APIs and UI SHALL treat it as ordinary plain text

#### Scenario: New CLI posts to an older Hub
- **WHEN** an older Hub ignores unsupported optional structured fields
- **THEN** readable content SHALL still represent the event

### Requirement: Chat history preserves stream semantics
When agent output is projected into per-agent chat history, the projection SHALL retain available
stream kind, payload, run identity, sequence, and timestamp rather than flattening the record back
to content alone.

#### Scenario: Structured output appears in spec chat
- **WHEN** chat history includes a thinking or tool event
- **THEN** the chat response SHALL provide the fields required by the shared renderer

### Requirement: Recent output retrieval
The default bounded output query SHALL return the newest N matching records and present those
records in chronological order with deterministic tie-breaking.

Incremental queries SHALL continue from their cursor in chronological order.

#### Scenario: More than N output rows exist
- **WHEN** a client requests output without a cursor and more than N matching rows exist
- **THEN** the response SHALL contain the newest N rows ordered oldest-to-newest

#### Scenario: Timestamps are equal
- **WHEN** two matching records have equal timestamps
- **THEN** run sequence and record ID SHALL provide stable ordering

### Requirement: Shared stream renderer
The Hub UI SHALL use one shared structured-event renderer for the agent output panel, spec chat,
and agent activity views. Rendering logic SHALL use `kind` and payload fields rather than string
prefix inspection when structured fields are present.

#### Scenario: Same event appears on different surfaces
- **WHEN** a structured event is shown in agent output, spec chat, and agent activity
- **THEN** all surfaces SHALL use the same semantic label, severity, and content treatment

#### Scenario: Legacy prefixed content appears
- **WHEN** a text-only legacy event contains an existing pre-canonical content prefix
- **THEN** compatibility handling SHALL preserve current visibility behavior without affecting structured events

### Requirement: Thinking presentation
Consecutive thinking events in one run SHALL render as a grouped live section. The section SHALL
automatically collapse when the first text event or terminal lifecycle event for that run arrives,
and SHALL remain user-expandable with a duration summary when timestamps permit.

#### Scenario: Thinking transitions to answer
- **WHEN** a run emits thinking followed by text
- **THEN** the thinking group SHALL collapse and the text SHALL remain visible

#### Scenario: Thinking is still live
- **WHEN** the latest event in an active run is thinking
- **THEN** the current thinking group SHALL remain visibly active

### Requirement: Tool and diagnostic presentation
Correlated tool-use and tool-result events SHALL render as a compact paired activity that can
expand to safe input and result details. Errors SHALL remain prominent, while diagnostics SHALL be
visually distinct and hideable without hiding errors or tool failures.

#### Scenario: Tool pair is rendered
- **WHEN** tool-use and tool-result events share a call ID
- **THEN** the UI SHALL present one expandable tool activity with its completion or failure state

#### Scenario: User hides diagnostics
- **WHEN** diagnostic visibility is disabled
- **THEN** diagnostic events SHALL be hidden while error events and failed tool results remain visible

### Requirement: Stream contract conformance tests
The repository SHALL include representative fixtures and tests for every supported runner adapter,
event persistence and delivery, legacy compatibility, payload bounds and redaction, ordering, and
shared UI rendering behavior.

#### Scenario: Provider fixture suite runs
- **WHEN** the stream adapter tests execute
- **THEN** fixtures for Claude and Codex SHALL produce the expected canonical events

#### Scenario: UI contract tests run
- **WHEN** the Hub UI test or build verification executes
- **THEN** structured and legacy records SHALL type-check and render through the shared component

### Requirement: Independent context-usage boundary
The canonical runner observation SHALL keep context-usage samples separate from display events.
Context samples SHALL use the `agent-context-usage` contract and SHALL NOT be persisted as
`AgentOutput` rows or rendered as stream event kinds.

#### Scenario: Parser reports output and usage
- **WHEN** one provider event contains both readable output and token usage
- **THEN** the parser SHALL return output events and the usage sample in separate result fields

#### Scenario: Collector reports usage without output
- **WHEN** an auxiliary provider collector reports a context sample
- **THEN** the invocation coordinator SHALL deliver the context snapshot without fabricating a stream event

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

### Requirement: A run's terminal outcome is visible
The conversation SHALL show, for every run that ended, whether it completed, failed, was stopped or was interrupted, and SHALL show it again after a page reload.

A run whose row genuinely cannot be found is the only case that may present no outcome. That is
distinct from a run whose row exists but was omitted from the response, which is a defect and is
forbidden by *The run facts cover every run the events name*.

#### Scenario: A stopped run says it was stopped

- **WHEN** the operator stops a turn and the run's status becomes `stopped`
- **THEN** the turn presents a terminal label naming the stop, rather than ending with no statement

#### Scenario: The outcome survives a reload

- **WHEN** a conversation containing a stopped, failed or interrupted run is loaded fresh, with no
  live stream having delivered anything
- **THEN** that run's terminal label is presented from persisted state alone

#### Scenario: A failed run is distinguishable from a silent one

- **WHEN** one run ended `failed` and another ended `completed` having produced no assistant text
- **THEN** the two turns present different terminal states rather than both presenting none

#### Scenario: A run still executing claims no outcome

- **WHEN** a run's status is `running`
- **THEN** no terminal label is presented for it

#### Scenario: A turn that produced nothing still reports what it cost

- **WHEN** a run ended without producing any visible agent output, so the only output row its turn
  carries is a terminal status row the conversation does not draw
- **THEN** the turn still presents its duration and token line, rather than losing it along with the
  row it was attached to

### Requirement: The timeline carries each run's own facts
The timeline response SHALL carry each run's recorded facts — status, exit code, start time and end time — read from the run's own row, and clients SHALL NOT reconstruct them from event names or event timestamps.

The response is an envelope of the events and a map of run facts keyed by `run_id`. The map is keyed
rather than listed because every consumer of it is a lookup or an unordered scan; a list would
require the client to build the index and would reintroduce the derivation this requirement removes.

The run facts are read by primary key, using the run ids the returned events name, after those
events have been merged and truncated. The map therefore describes exactly the runs the response
talks about: it is not scoped by project and agent, and it carries no bound that could be chosen
too small.

#### Scenario: The response carries both halves

- **WHEN** a client requests an agent's timeline
- **THEN** the response contains the events and a map of run facts keyed by `run_id`

#### Scenario: The facts come from the run, not from the events

- **WHEN** a run's lifecycle events and its recorded status disagree, because the status was
  corrected after the events were written
- **THEN** the response reports the recorded status

#### Scenario: An unknown run degrades rather than fails

- **WHEN** a returned event names a `run_id` that has no row
- **THEN** the map omits that key and the client presents that run exactly as it presents a run with
  no outcome yet

#### Scenario: The map is scoped to the events

- **WHEN** the agent has runs whose events fall entirely outside the returned event window
- **THEN** the map contains no entries for them

### Requirement: The run facts cover every run the events name
Every run named by a returned event SHALL be present in the run facts map, and the map SHALL be obtained by looking those runs up by id rather than by any query whose coverage depends on an ordering or a limit.

Coverage is the property; a bound is not a way to get it. A limit decides how many rows return, not
which, and no ordering available on the run row tracks the recency of the events that name it.
`run_reconciliation` sweeps every still-`running` row at Hub start and writes its lifecycle event
then, so an agent's newest events routinely name its oldest runs. A query ranked by start time and
capped at any number can miss exactly those.

Omitting a run the events name presents that turn as having no outcome — which is the defect this
change exists to remove, reintroduced by the fix for it, and blessed by *An unknown run degrades
rather than fails*. That is why the requirement is on the construction of the query and not on the
size of its result.

#### Scenario: An old run named by a recent event keeps its outcome

- **WHEN** a returned event names a run that started long before the agent's most recent runs,
  because the run's lifecycle event was written at Hub restart rather than when the run began
- **THEN** that run's facts are present in the map and its turn presents its terminal outcome

#### Scenario: Coverage does not depend on how many runs the window names

- **WHEN** the returned events name any number of distinct runs, up to the number of events returned
- **THEN** every one of those runs is present in the map

### Requirement: A run's terminal status line is persisted
The Hub SHALL persist a run's terminal status line as durable output, not only broadcast it, so the exit code remains recoverable after the live stream is gone.

This is bounded to the runs whose end the Hub observes — the two spawn paths' finalize blocks. A run
reconciled as `interrupted` after a Hub restart has no terminal status line and is not required to
gain one: there was no Hub process to write it. Such a run's outcome is carried by the run facts
map, under *A run's terminal outcome is visible*.

#### Scenario: The status line survives a reload

- **WHEN** a run ends and its output is fetched after the broadcast has been missed or the page
  reloaded
- **THEN** the run's output contains its terminal status row carrying the exit code

#### Scenario: Both spawn paths persist it

- **WHEN** a run ends on either the process path or the app-server path
- **THEN** the terminal status row is persisted in both cases

#### Scenario: It does not depend on the runner announcing its own completion

- **WHEN** a run ends on a runner whose output stream carries no completion sentinel of its own
- **THEN** the terminal status row is persisted for that run exactly as it is for a runner whose
  stream does carry one

### Requirement: Payload-shaped model functions are tested against real route ordering
A model function that consumes an API payload SHALL be tested against a fixture whose ordering is the ordering that route actually produces, and the test SHALL fail if the route's ordering is reversed.

A fixture that asserts correct behaviour on an ordering the route never emits is not evidence. This
requirement exists because such a test was green while the behaviour it covered could not fire.

#### Scenario: The fixture matches the route

- **WHEN** a model function consumes a payload from a route that returns rows in a defined order
- **THEN** its test fixture presents the rows in that same order

#### Scenario: The test is sensitive to ordering

- **WHEN** a payload-shaped model function is correct only for one ordering, and the fixture's
  ordering is reversed
- **THEN** at least one test fails

#### Scenario: An order-independent function proves it

- **WHEN** a model function is intended to be independent of its input's ordering
- **THEN** a test asserts the same result for a shuffled input
