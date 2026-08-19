# conversation-side-panel

## Purpose

One shell beside a conversation, hosting one tab at a time.

Specification documents, the workspace file tree and the loops index each used to mean something
different by "open on the right". This capability makes them one surface with one set of rules: a
tab strip the operator controls, index tabs that launch keyed detail tabs, per-project tab
configuration with a single global width, and one resize/overlay rule that does not vary by what is
being shown.

## Requirements

### Requirement: A conversation hosts one panel shell showing one tab at a time

The conversation surface SHALL host at most one panel shell beside it. The shell SHALL present a
strip containing only the tabs currently open, and SHALL display the content of exactly one of them
at a time. Every open tab SHALL be closable, and closing the last one SHALL close the shell.

Tab kinds SHALL come from a fixed set defined in the Hub UI's own source. The Hub UI MUST NOT
construct a tab kind at runtime from external or dynamic input.

#### Scenario: The strip shows only what is open

- **WHEN** the operator has opened two tabs
- **THEN** the strip shows exactly those two, and no tab for a kind that is not open

#### Scenario: One tab's content is visible at a time

- **WHEN** the operator selects a different open tab
- **THEN** the shell shows that tab's content in the whole panel, replacing what was shown

#### Scenario: Closing the last tab closes the shell

- **WHEN** the operator closes the only open tab
- **THEN** the shell closes and the conversation occupies the full available width

### Requirement: The plus affordance opens a tab that is not already open

The shell SHALL present an affordance that opens a new tab. Choosing a kind that is already open as a
single-instance tab SHALL bring that tab into focus rather than opening a second one.

#### Scenario: The plus affordance opens a new tab

- **WHEN** the operator opens the plus affordance and chooses a kind that is not open
- **THEN** a tab of that kind is added to the strip and becomes the visible tab

#### Scenario: Choosing an already-open index refocuses it

- **WHEN** the operator chooses a kind whose single-instance tab is already open
- **THEN** that tab becomes the visible tab, and no second tab of that kind is created

### Requirement: An index tab opens a keyed detail tab for the item selected in it

Selecting an item from an index tab SHALL open a detail tab for that item. Selecting an item whose
detail tab is already open SHALL bring that tab into focus and re-reveal the selected item within it,
and MUST NOT open a second tab for the same item.

#### Scenario: Selecting an item opens its detail tab

- **WHEN** the operator selects an item from an index tab
- **THEN** a detail tab for that item opens and becomes the visible tab

#### Scenario: Selecting an already-open item refocuses rather than duplicating

- **GIVEN** a detail tab already open for an item
- **WHEN** the operator selects that same item from the index again
- **THEN** the existing tab becomes visible, its content is re-revealed, and no second tab exists for
  that item

### Requirement: A detail tab is keyed by its item's durable identifier where one exists

A detail tab SHALL be keyed by an identifier that survives the item being renamed, whenever the item
has such an identifier. A specification document's detail tab SHALL be keyed by the document's
identifier, not by its path. A file's detail tab SHALL be keyed by its path, a file having no other
identifier.

#### Scenario: Renaming a document does not break its open tab

- **GIVEN** an open detail tab for a specification document
- **WHEN** that document is renamed
- **THEN** the tab still shows the same document

### Requirement: Opening a file replaces the file tree tab

Opening a file from the tree SHALL close the tree tab as the file's detail tab opens, so that
navigation does not occupy a tab of its own once it has been used.

#### Scenario: The tree gives way to the file

- **GIVEN** the file tree tab is open
- **WHEN** the operator opens a file from it
- **THEN** the file's detail tab is open and visible, and the tree tab is no longer in the strip

### Requirement: Tab configuration is remembered per project; width is one global preference

Which tabs are open, which is visible, and whether the shell is open at all SHALL be remembered per
project, and restored when the operator returns to that project. This state MUST NOT be shared
between projects.

The shell's width SHALL persist as a single value shared across every project and conversation,
extending the same preference the specification document panel already persists.

#### Scenario: A project's tabs are restored

- **WHEN** the operator closes the shell in a project and later reopens it in that same project
- **THEN** the tabs that were open are open again, with the same one visible

#### Scenario: Tab configuration does not leak between projects

- **GIVEN** two projects with different tabs open
- **WHEN** the operator switches from one to the other
- **THEN** each shows its own tab configuration

#### Scenario: Width is shared

- **WHEN** the operator resizes the shell in one project and opens the shell in another
- **THEN** the shell opens at the width remembered from the first

### Requirement: Persisted tab state is versioned, reconciled, and never restores an empty shell

The persisted tab state SHALL carry a version, and SHALL be migrated on load when that version is
older than the current one. On load, a detail tab whose item no longer exists SHALL be dropped.

If migration or reconciliation removes every tab, the shell MUST NOT be restored as open. If it
removes the tab that was visible while others survive, one of the survivors SHALL be made visible
rather than restoring an open shell with nothing shown.

#### Scenario: A tab for a deleted file is dropped

- **GIVEN** persisted state naming an open detail tab for a file that no longer exists in the
  project's workspace
- **WHEN** the shell loads that state
- **THEN** that tab is not restored, and the remaining tabs are

#### Scenario: Losing every tab does not reopen an empty shell

- **WHEN** reconciliation or migration removes every persisted tab
- **THEN** the shell is restored closed, not open and empty

#### Scenario: Losing the visible tab promotes a survivor

- **WHEN** reconciliation removes the tab that was visible, and other tabs survive
- **THEN** one of the surviving tabs is shown, and the shell is not open with nothing displayed

### Requirement: The panel shell resizes and overlays using the same rule for every tab

The boundary between the conversation and the shell SHALL be the operator's to move, bounded only by
each side's own measured minimum width, with no maximum on either side that prevents the other from
being made smaller. Below the combined minimum width of the conversation and the visible tab, the
shell SHALL become an overlay rather than resize below either minimum, and dismissing that overlay
MUST NOT discard the open tabs — a control SHALL remain available to bring the shell back.

The combined minimum SHALL be derived from the visible tab's own minimum rather than a single
hardcoded value, so that the threshold and the layout cannot disagree.

#### Scenario: The operator resizes the boundary

- **WHEN** the operator drags the boundary between the conversation and the shell
- **THEN** either side can be made the larger one, down to its own measured minimum

#### Scenario: A narrow viewport overlays instead of resizing

- **WHEN** the combined minimum width of the conversation and the visible tab exceeds the available
  viewport width
- **THEN** the shell is shown as an overlay rather than a resized column

#### Scenario: Dismissing the overlay keeps the tabs

- **WHEN** the operator dismisses the shell overlay at a narrow viewport
- **THEN** a control remains to bring it back with the same tabs open and the same one visible

### Requirement: The file tree lists the project's workspace and opens a file for reading

The file tree tab SHALL present the project's workspace paths as a navigable tree, sourced from the
same path listing already used elsewhere in the Hub UI, and selecting a path SHALL open that file for
reading.

#### Scenario: The tree shows the workspace

- **WHEN** the operator opens the file tree tab
- **THEN** every path the workspace path listing returns for the project is shown as a navigable tree

#### Scenario: Selecting a text file shows its content

- **WHEN** the operator selects a text file from the tree
- **THEN** its content is shown in that file's detail tab

### Requirement: The file content endpoint's allowlist matches the workspace path listing exactly

The Hub SHALL serve a file's content only for a path that is, byte-for-byte, a member of what the
workspace path listing returns for the same project. The Hub MUST NOT serve content for any path
reachable only through a separate, independently reasoned containment or traversal check.

#### Scenario: A listed path is served

- **WHEN** a path the workspace path listing returns is requested for content
- **THEN** the Hub returns that file's content

#### Scenario: A path outside the listing is refused however it is expressed

- **WHEN** a path attempting traversal outside the project's workspace, or a path the listing would
  exclude for any reason — ignored, symlinked outside the workspace, or otherwise not returned — is
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
- **THEN** the response refuses it and states the file's size and the bound
- **AND** no partial content is returned in its place

### Requirement: The file content endpoint distinguishes binary content before rendering

The Hub SHALL determine whether a requested file is text or binary before it is rendered, and a
binary file SHALL be identified as such rather than rendered as garbled text.

#### Scenario: A text file renders

- **WHEN** a text file is requested
- **THEN** its content is rendered as text in its tab

#### Scenario: A binary file is identified rather than rendered

- **WHEN** a binary file is requested
- **THEN** the tab states that the file is binary and does not render its bytes as text

### Requirement: A file can be inserted into the composer in the format the composer already uses

Referencing a file from the file tree or a file's detail tab SHALL insert the same mention format the
composer's own path-completion trigger produces, so a mention inserted from either surface is
indistinguishable in the composed message.

#### Scenario: An inserted mention matches the composer's own format

- **WHEN** the operator inserts a file reference from the shell into the composer
- **THEN** the inserted text is the same mention format the composer's path trigger produces for that
  same file

### Requirement: The tab strip and plus affordance are fully keyboard operable

Every open tab, its close control, and the plus affordance SHALL be reachable and operable using only
the keyboard: reachable by sequential focus navigation, activatable with `Enter` or `Space`, and —
once the strip has focus — navigable between tabs using the arrow keys.

#### Scenario: A tab is reachable and activatable by keyboard alone

- **WHEN** the operator reaches a tab using only the keyboard and activates it
- **THEN** that tab becomes the visible tab, identically to a pointer click

#### Scenario: Arrow keys move between tabs

- **WHEN** the strip has keyboard focus and the operator presses an arrow key
- **THEN** focus moves to the adjacent tab in that direction

#### Scenario: A tab can be closed by keyboard

- **WHEN** the operator reaches an open tab's close control by keyboard and activates it
- **THEN** that tab closes

#### Scenario: The plus affordance is keyboard operable

- **WHEN** the operator reaches the plus affordance by keyboard and activates it
- **THEN** its menu opens and each entry is itself keyboard reachable and activatable
