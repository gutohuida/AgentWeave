# Task dependency board

The per-document layered view: what it draws, what it refuses to let anyone edit, and what it must
say when work is not moving.

## ADDED Requirements

### Requirement: The board lays work out by dependency depth, downward

The dependency board SHALL position a task according to how deep it sits in the dependency graph,
with work that depends on nothing at the top and work depending on it below.

Depth is chosen as the vertical axis because the two axes are not symmetric: the number of tasks that
can run at once is bounded by the project's agent budget, while the length of a dependency chain is
bounded by nothing. The unbounded dimension belongs on the axis where scrolling is cheap.

The layout SHALL accommodate a task depending on several others — the structure is a directed acyclic
graph, not a tree, and edges converge as well as diverge.

#### Scenario: Independent work is at the top

- **WHEN** a document's tasks are laid out
- **THEN** tasks with no dependencies appear in the topmost layer

#### Scenario: A task appears below everything it depends on

- **WHEN** a task depends on tasks in different layers
- **THEN** it appears below the deepest of them

#### Scenario: Converging dependencies are drawn

- **WHEN** two tasks are prerequisites of one task
- **THEN** the layout shows both relationships

### Requirement: The card carries the status the layout no longer can

Each task SHALL show its own status on its card.

Position cannot encode two things. On the status board a card's column states its status; on the
dependency board the position states depth instead, so the status has to live on the card or be lost.

#### Scenario: A card states its status

- **WHEN** a task is drawn on the dependency board
- **THEN** its status is shown on the card

### Requirement: The board draws structure and never authors it

The dependency board SHALL NOT offer any means of creating, removing or altering a dependency.

Dependencies are declared by a specification document. An edge that existed only on a board would be
a fact the document does not contain, which would make the document — the artefact that is supposed
to be the record — no longer a true account of the work.

Where an operator attempts to alter structure, the refusal SHALL say that dependencies are changed by
changing the document.

#### Scenario: Structure cannot be edited from the board

- **WHEN** the operator attempts to add or remove a dependency on the board
- **THEN** no dependency is changed

#### Scenario: The refusal names the document as the place to change it

- **WHEN** such an attempt is refused
- **THEN** the operator is told the dependency is changed by editing the document

### Requirement: The board distinguishes why work is not moving

Where a task cannot start, the board SHALL distinguish between waiting on prerequisites that are
progressing, waiting on prerequisites that nobody is reviewing, and waiting on prerequisites that
were rejected.

These are identical on the surface — a card that will not start — and have entirely different
remedies: wait, find a reviewer, or make a decision about abandoned work. Because a dependency is met
only at approval, an unattended review backlog stalls every downstream layer, and if the board cannot
distinguish that from ordinary waiting then a review problem is indistinguishable from the dependency
feature being broken.

#### Scenario: Waiting on review is stated as such

- **WHEN** a layer's prerequisites are complete and none is under review
- **THEN** the board reports that the layer is waiting on review

#### Scenario: Waiting on rejected work is stated as such

- **WHEN** a task's prerequisite has been rejected
- **THEN** the board reports the task as gated on rejected work and names it

#### Scenario: A dependent running on regressed work is marked

- **WHEN** a running task's prerequisite has left approved
- **THEN** the board marks that task

### Requirement: One board covers one document, and tasks without one have their own

The dependency board SHALL be scoped to a single specification document, chosen by the operator, and
a board SHALL exist for tasks that belong to no document.

A project accumulates finished work indefinitely, so a project-wide graph grows without bound; a
document's decomposition does not. Tasks created by hand belong to no document and would otherwise
appear on no board at all — the boardless case has to be reachable, not merely handled.

The chooser SHALL show how much work remains in each board, so that selecting one and seeing what is
left are the same act.

#### Scenario: Choosing a document shows its tasks only

- **WHEN** the operator selects a document's board
- **THEN** only tasks belonging to that document are shown

#### Scenario: Tasks with no document are reachable

- **WHEN** the operator selects the board for tasks with no document
- **THEN** tasks with no owning document are shown

#### Scenario: The chooser reports outstanding work

- **WHEN** the operator opens the chooser
- **THEN** each board reports how many of its tasks are outstanding

### Requirement: Finished layers collapse but remain reachable

A layer whose tasks have all reached a terminal state SHALL be collapsed to a single summary that the
operator can expand.

Scoping to one document bounds the graph but does not stop a finished document's board being a screen
of completed cards. Collapsing keeps the graph's shape legible — what depended on what is still
visible — while hiding a task entirely would leave edges pointing at nothing and make the remaining
graph look rootless.

#### Scenario: A finished layer is summarised

- **WHEN** every task in a layer has reached a terminal state
- **THEN** that layer is shown as a single summary

#### Scenario: A collapsed layer can be opened

- **WHEN** the operator expands a collapsed layer
- **THEN** its tasks are shown

#### Scenario: A partly finished layer is not collapsed

- **WHEN** a layer contains both finished and unfinished tasks
- **THEN** the layer is not collapsed

### Requirement: A dependency on another document's task is shown as leaving the board

An imported task SHALL be drawn as a reference that names the document it belongs to, rather than as
a task of this board.

The board is scoped to one document, and a foreign task is not this document's work to act on — but
the dependency is real and hiding it would make a gated task look gated by nothing. Naming the owning
document is what makes the blocker reachable.

#### Scenario: An imported dependency names its document

- **WHEN** a task depends on an imported task
- **THEN** the board shows the dependency and names the document the task belongs to

#### Scenario: An imported task is not drawn as local work

- **WHEN** an imported task is shown
- **THEN** it is distinguishable from the document's own tasks

### Requirement: The dependency board is an additional view, not a replacement

The status board SHALL remain available unchanged, and the dependency board SHALL be a view the
operator switches to.

The two answer different questions. A status board answers what is in flight; a dependency board
answers what can start. Neither contains the other, and removing the first would take away the view
that suits work already under way.

#### Scenario: The status board is unchanged

- **WHEN** the operator uses the status board
- **THEN** it behaves as it did before this change

#### Scenario: The operator can switch between views

- **WHEN** the operator switches to the dependency board and back
- **THEN** both views are available
