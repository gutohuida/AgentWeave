# Design — Conversation-first specification workspace

## Decision 1 — The document belongs to the conversation view, and `tab: 'spec'` becomes a way in

**Chosen:** the open document becomes part of the conversation destination —
`{ kind: 'conversation'; projectId; agent; conversationId; document: string | null }` — carried in
the URL alongside the conversation. `tab: 'spec'` stays in `PROJECT_TABS` but resolves *into* that
destination: the agent's most recent conversation (or a new one), with the manifest home document
open.

Three consequences, all wanted:

- **Any conversation can open a document.** Not only ones reached through the Spec tab. That is the
  direct expression of "a thread is in a phase because a document is open in it" — the relationship
  is a link the operator makes, not a category the thread was born into.
- **There is one conversation surface, in one shape.** The reason A1's composer broke is that it was
  rendered somewhere structurally different from where it was designed. If the document is a panel
  *within* the conversation view, there is no second shape to keep in step.
- **Reload restores what you were looking at**, including which document — the same property the
  conversation destination already gives conversations.

**Rejected: delete the Spec tab.** Discoverability is real. Without an entry point, finding a
specification would require already being in a conversation and knowing to press Ctrl+K. The tab
costs one line in the tab bar and answers "where are the specs".

**Rejected: keep `tab: 'spec'` as its own page and just re-proportion it.** Cheaper, and it is the
option that leaves the defect in place: two left rails, two agent selectors, and a conversation
surface rendered somewhere it was not designed for. The overflow is a symptom; re-proportioning
treats the symptom and keeps the cause.

**Rejected: the document panel as ephemeral UI state, outside the URL.** Simplest, but it cannot be
linked to or restored, and the operator would lose their place on every reload.

## Decision 2 — Proportions: the document gets the larger share when open

"Composer takes centre stage" is about which surface is the *frame*, not about which is widest. A
specification is a document to read; a chat column that crowds it would trade one unreadable pane
for another.

| | Closed | Open |
|---|---|---|
| Hub rail | operator width (default 220) | same |
| Conversation | remaining width | **420–560, operator-sized, default ~480** |
| Document panel | — | remaining, minimum 560 |

480 is chosen because it is where the composer's control row fits without wrapping — the number
comes from the control row, measured, not from taste. Below the point where conversation minimum +
document minimum + rail no longer fit, the document panel becomes an overlay rather than a column,
reusing the drawer behaviour `SpecWorkspace` already has.

The divider is the shared `PaneResizer`, which A1 already taught to measure inside a container and
to size a right-hand pane.

## Decision 3 — Delete the library column; the picker already exists

`SpecNavigator` does two jobs: choose a document (Library / History) and move within one (outline).

- **Choosing** is already solved twice over. `SpecDocumentPicker` is a Ctrl+K search dialog with the
  full inventory, archived documents included, and it already switches the browser to History when
  an archived result is chosen. The column is a second, worse copy of it. It goes; a breadcrumb in
  the document panel header opens the picker.
- **Moving within** belongs next to the thing it indexes. The outline moves into the document panel
  — as a collapsible strip on its far side, so it appears only when there is a document to outline.

That deletes a column without deleting a capability, which is what makes room for the conversation
without stealing it from the rail.

## Decision 4 — The rail collapses only when the operator says so, and stays usable when it does

Two separate faults are being fixed and they need separating.

1. **Automatic.** `compact={activePage === 'spec'}` is removed outright. Nothing about which page is
   open should change what the operator can navigate to.
2. **Blank.** `Sidebar`'s compact mode gates *every* branch on `!compact`, so it renders the avatar
   and nothing else. If a collapsed state survives, it MUST remain navigable: project marks and
   agent marks as icons with accessible names and tooltips, the active one still indicated.

The collapsed state becomes an operator toggle, persisted next to the existing rail width. A rail
that cannot be navigated is not a collapsed rail; it is a hidden one, and hiding navigation is not a
layout decision the application gets to make on the operator's behalf.

## Decision 5 — The composer control row wraps instead of overflowing

The row (`Model` · `Effort` · `Permissions`, plus attach/send) currently assumes it will never be
narrow. It will now be shown between 420 and 560, and inside an overlay on small windows.

**Chosen:** the row wraps to a second line below its minimum, and each pill truncates its *value*
with the control name kept — `Permissions: Edit fi…` is useless, `Permissions ▾` with the value in
the tooltip and menu is not. Nothing is removed from the row at any width: a control that
disappears when the pane narrows is a control the operator cannot find.

**Rejected: an overflow menu.** It hides the permission posture, which is the one control whose
current value must be readable at a glance before sending — that is the whole point of the pill.

## Decision 6 — The iframe contract is carried across, not touched

`SpecFrame` renders with `sandbox="allow-scripts"` and deliberately without `allow-same-origin`, and
`specBridge.ts` therefore uses message identity in place of origin checking, with a path allowlist
for link resolution. Moving the frame into a panel changes its container and nothing else. No task
in this change edits `specBridge.ts`, and a test asserts the sandbox attributes are unchanged —
a layout change is exactly the kind of work that quietly relaxes a security boundary for
convenience.

## Decision 7 — `SpecChat` is deleted, not fixed

It exists to (a) pick an agent and (b) resolve which conversation is on screen. Under Decision 1 the
conversation view already *is* the destination, so both jobs are the destination's. The agent
`<select>` — the only raw select in the application, and a second agent-selection mechanism
alongside the rail — goes with it.

Recorded because it is the lesson, not the line: A1 removed a second implementation of a chat
surface and, in the same change, introduced a second implementation of agent selection. The test
that would have caught it is "how many ways does the application offer to do this?", and it is now
task 5.5.

## Verification note — why "it rendered" is not evidence

A1 drove a real browser, asserted `permission-request-perm-…` was in the DOM inside
`[data-testid="spec-chat-pane"]`, and reported the requirement verified. The element was there. It
was also inside a pane whose contents were overflowing their container, which the assertion could
not see and the agent never looked for.

So the live checks here measure geometry rather than existence:

```js
// For every interactive element in the panel, at each tested width.
const box = el.getBoundingClientRect(), host = panel.getBoundingClientRect()
box.right <= host.right + 1 && box.left >= host.left - 1        // no overflow
el.scrollWidth <= el.clientWidth + 1                             // no clipped text
```

plus pairwise overlap between interactive elements. Widths tested: the conversation minimum, the
default, the maximum, and the overlay breakpoint on either side. **A check that only proves an
element exists does not close a task in this change.**
