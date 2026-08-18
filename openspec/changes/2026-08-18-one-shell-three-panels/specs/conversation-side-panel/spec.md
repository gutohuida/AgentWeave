# conversation-side-panel

## ADDED Requirements

### Requirement: A conversation hosts one panel shell, registering a fixed set of panels

The conversation surface SHALL host at most one panel shell beside it at a time, and the shell SHALL
offer exactly the panels named in a fixed, literal registration list — `spec`, `loop`, and `files` —
each declaring an id, a title, an icon, and that it is a singleton. The Hub UI MUST NOT construct a
panel's registration at runtime from external or dynamic input.

Opening a panel that is already open SHALL bring it into focus rather than opening a second instance
of it.

#### Scenario: Opening a registered panel shows it

- **WHEN** the operator opens one of the three registered panels from a conversation with no panel
  currently shown
- **THEN** the shell appears showing that panel's content

#### Scenario: Reopening an already-open panel refocuses it

- **WHEN** the operator opens a panel that is already the shell's active panel
- **THEN** the same panel remains shown, and no second instance of it is created

#### Scenario: Switching between registered panels

- **WHEN** the operator opens a different registered panel while another is active
- **THEN** the shell replaces the active panel's content with the newly opened one
- **AND** the previously active panel's own state (e.g. its scroll position or open document) is not
  discarded, only hidden, for a singleton panel switched away from and back to within the same
  conversation

### Requirement: The plus affordance offers every registered panel unconditionally

The shell SHALL present an affordance that opens every registered panel, regardless of whether any
panel is currently open. No registered panel SHALL be hidden or omitted from this affordance based on
project state, permissions, or any other runtime condition.

#### Scenario: The plus affordance lists all three panels

- **WHEN** the operator opens the shell's plus affordance
- **THEN** `spec`, `loop`, and `files` are each offered, regardless of whether a document exists, a
  loop exists, or the project's workspace is empty

### Requirement: Panel width is one global preference; the open panel is conversation-scoped

The shell's width SHALL persist as a single value shared across every conversation, extending the
same preference the specification document panel already persists. Which panel is active, and
whether the shell is open at all, SHALL be part of the conversation's own addressed destination, and
SHALL NOT be shared with any other conversation.

#### Scenario: Width is remembered across conversations

- **WHEN** the operator resizes the shell in one conversation, then opens a panel in a different
  conversation
- **THEN** the shell opens at the width remembered from the first conversation

#### Scenario: The active panel does not leak between conversations

- **WHEN** the operator has the loop tab open in one conversation and switches to a different
  conversation
- **THEN** the second conversation's shell shows whatever panel state that conversation's own
  destination records — open or closed, and on whichever panel — not the first conversation's loop
  tab

#### Scenario: The open panel survives a reload

- **WHEN** the operator reloads with a panel open
- **THEN** the same conversation reopens with the same panel active

### Requirement: The panel shell resizes and overlays using the same rule for every panel

The boundary between the conversation and an open panel SHALL be the operator's to move, bounded only
by each side's own measured minimum width, with no maximum on either side that prevents the other
from being made smaller. Below the combined minimum width of the conversation and the active panel,
the shell SHALL become an overlay rather than resize below either minimum, and closing that overlay
MUST NOT discard the panel's open state — a distinct control SHALL remain available to reopen it.

This generalizes the specification document panel's existing resize-then-overlay behavior to
whichever panel is active, using each panel's own measured minimum rather than a single hardcoded
value.

#### Scenario: The operator resizes the boundary

- **WHEN** the operator drags the boundary between the conversation and any active panel
- **THEN** either side can be made the larger one, down to its own measured minimum

#### Scenario: A narrow viewport overlays instead of resizing

- **WHEN** the combined minimum width of the conversation and the active panel exceeds the available
  viewport width
- **THEN** the active panel is shown as an overlay rather than a resized column

#### Scenario: Dismissing the overlay does not close the panel

- **WHEN** the operator dismisses the panel overlay at a narrow viewport
- **THEN** a control remains in the conversation to reopen the same panel without reselecting it

### Requirement: The loop tab shows a loop's queue, claimed item, and stop state

The `loop` panel SHALL show, for the loop bound to the conversation's job (when one exists): the
loop's purpose, its stop condition and whether it is still running, per-status counts of its queue,
the item currently claimed by the most recent firing (if any), and its count of open questions. A
task claimed by a firing but not yet resumed to an in-progress status SHALL still be shown as the
claimed item — the loop tab MUST NOT omit a claimed task solely because its status is `assigned`
rather than `in_progress`.

#### Scenario: An active loop's summary is shown

- **WHEN** the operator opens the loop tab for a conversation whose job has a loop with tasks in its
  queue
- **THEN** the tab shows the loop's purpose, queue counts by status, and its currently claimed item

#### Scenario: A freshly claimed task is visible

- **WHEN** a firing has claimed a queue item by setting its status to `assigned`, and no later step
  has yet moved it to `in_progress`
- **THEN** the loop tab still shows that item as the claimed item

#### Scenario: A conversation with no loop shows an empty, legible state

- **WHEN** the operator opens the loop tab for a conversation whose job has no loop
- **THEN** the tab states plainly that this conversation is not part of a loop, rather than showing
  an empty table with no explanation

### Requirement: The loop tab shows whether the loop's job has a run active right now

The `loop` panel SHALL indicate whether an agent is currently, visibly active on the loop's job — not
merely whether the job's roster-wide agent status field reports `running`. The indicator SHALL be
derived from the same lifecycle-event-and-streamed-status-line signal already used elsewhere in the
Hub UI to avoid a false-negative the moment an agent's turn produces any output, scoped to the loop's
job's own current run rather than to whichever agent conversation the operator happens to have open.

#### Scenario: A firing in progress on a different conversation still shows as active

- **WHEN** the loop's job has a firing currently producing output, in a conversation other than the
  one the operator has open
- **THEN** the loop tab's active-now indicator shows active

#### Scenario: An agent that has spoken but not finished still shows as active

- **WHEN** the loop's current firing has produced text output but its run has not yet settled
- **THEN** the active-now indicator remains active, not idle

#### Scenario: A settled run shows as not active

- **WHEN** the loop's most recent firing has fully settled with no run currently in progress
- **THEN** the active-now indicator shows not active

### Requirement: Motion in the loop tab is reserved for the active-now indicator

Only the active-now indicator SHALL animate. The queue progress display and the stop-reason or
terminal-state indication SHALL be static, updating their displayed value without a transition
animation on the change itself.

Any animation used in the loop tab SHALL respect a reduced-motion preference. A CSS-driven animation
inherits the Hub's existing blanket reduced-motion rule; an animation implemented outside CSS SHALL
check the same preference directly rather than relying on that blanket rule.

#### Scenario: The active-now indicator animates while a run is active

- **WHEN** the active-now indicator is showing active
- **THEN** it renders with a motion effect distinguishing it from a static badge

#### Scenario: Queue and stop-state changes do not animate

- **WHEN** the loop's queue counts or stop reason change while the tab is open
- **THEN** the displayed value updates with no transition animation on the change

#### Scenario: Reduced motion is respected

- **WHEN** the operator has a reduced-motion preference set
- **THEN** the active-now indicator's animation is suppressed or reduced to near-zero duration

### Requirement: The file tab navigates the project's workspace and previews a file's content

The `files` panel SHALL present the project's workspace paths as a navigable tree, sourced from the
same path listing already used elsewhere in the Hub UI, and SHALL let the operator select a path to
preview its content inline.

#### Scenario: Opening the files tab shows the workspace tree

- **WHEN** the operator opens the files tab
- **THEN** every path the workspace path listing returns for the project is shown as a navigable tree

#### Scenario: Selecting a file previews its content

- **WHEN** the operator selects a text file from the tree
- **THEN** its content is shown inline within the tab

### Requirement: The file content endpoint's allowlist matches the workspace path listing exactly

The Hub SHALL serve a file's content only for a path that is, byte-for-byte, a member of what the
workspace path listing endpoint currently returns for the same project. The Hub MUST NOT serve
content for any path reachable only through a separate, independently-reasoned containment or
traversal check.

#### Scenario: A listed path is served

- **WHEN** a path the workspace path listing returns is requested for content
- **THEN** the Hub returns that file's content

#### Scenario: A path outside the listing is refused regardless of how it is expressed

- **WHEN** a path attempting traversal outside the project's workspace, or a path the listing would
  exclude for any reason (ignored, symlinked outside the workspace, or otherwise not returned), is
  requested for content
- **THEN** the request is refused

### Requirement: The file content endpoint bounds size and refuses rather than truncates

A file's content SHALL be served in full up to a fixed size bound. A file exceeding the bound SHALL
be refused with a response stating its size and the bound, and MUST NOT be served as a silently
truncated partial file.

#### Scenario: A file within the bound is served in full

- **WHEN** a file at or under the size bound is requested
- **THEN** its complete content is returned

#### Scenario: An oversized file is refused, not truncated

- **WHEN** a file exceeding the size bound is requested
- **THEN** the response refuses to serve it and states the file's size and the bound
- **AND** no partial content is returned in its place

### Requirement: The file content endpoint distinguishes binary content before rendering

The Hub SHALL determine whether a requested file is text or binary before it is rendered inline, and
a binary file SHALL be identified as such rather than rendered as garbled text.

#### Scenario: A text file renders inline

- **WHEN** a text file is requested
- **THEN** its content is rendered as text in the panel

#### Scenario: A binary file is identified rather than rendered as text

- **WHEN** a binary file is requested
- **THEN** the panel states that the file is binary and does not attempt to render its bytes as text

### Requirement: A file selected in the files tab can be inserted into the composer

Selecting a file from the files tab and choosing to reference it SHALL insert the same mention format
the composer's own path-completion trigger already produces, so a mention inserted from either
surface is indistinguishable in the composed message.

#### Scenario: Inserting a file from the tree matches the composer's own mention format

- **WHEN** the operator inserts a file from the files tab into the composer
- **THEN** the inserted text is the same mention format the composer's `@path` trigger produces for
  the same file

### Requirement: The tab strip and plus affordance are fully keyboard reachable

Every registered panel's tab, and the plus affordance that opens a not-yet-open panel, SHALL be
reachable and activatable using only the keyboard: reachable via sequential focus navigation,
activatable with `Enter` or `Space`, and — once the tab strip has focus — navigable between tabs
using the arrow keys.

#### Scenario: A panel tab is reachable and activatable by keyboard alone

- **WHEN** the operator navigates to a panel's tab using only the keyboard and activates it
- **THEN** that panel becomes the shell's active panel, identically to a pointer click

#### Scenario: Arrow keys move focus between tabs

- **WHEN** the tab strip has keyboard focus and the operator presses an arrow key
- **THEN** focus moves to the adjacent tab in the pressed direction

#### Scenario: The plus affordance is keyboard operable

- **WHEN** the operator reaches the plus affordance by keyboard and activates it
- **THEN** its menu of registered panels opens and each entry is itself keyboard reachable and
  activatable
