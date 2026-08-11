# Charter read view

## Why

An operator cannot read a charter without opening the editor for it.

`hub/ui/src/components/charters/ChartersPage.tsx:86` renders each charter's content with
`line-clamp-2`. Two lines of a sixty-line document is enough to see that a charter exists and not
enough to see what it says. The only other surface is the pencil at
`ChartersPage.tsx:91`, which opens `CharterForm` — an edit dialog presenting the text in a
`<textarea>` (`ChartersPage.tsx:184`).

So the only way to read a charter is to open a writable form over it. That is wrong in three
separate ways:

- **It makes reading a risky operation.** The read path and the write path are the same path. An
  operator who opens nine charters to compare them has opened nine editors, any of which can be
  altered by a stray keystroke and saved.
- **It defeats the purpose at the moment it matters most.** A charter is behaviour an operator is
  about to bind to an agent. Deciding *which* charter to bind is exactly when its full text is
  needed, and that is the one thing the screen will not show.
- **It cannot answer a question about the set.** Comparing charters — which is what choosing between
  them is — means holding two of them side by side. Nine sequential modal editors cannot do that.

Found while verifying `2026-08-11-charter-set-reshape`: the operator was asked to judge whether nine
charters read as a set worth picking from, and reported *"I don't know what contains in each from
inside the hub so it's hard to judge we need some way to view"*. The charter set re-shape cannot be
evaluated on its merits until its content is legible, so this blocks that change's section 7.

## What Changes

- **Each charter in the list can be expanded in place to reveal its full content**, read-only, with
  no editing affordance and nothing to save or cancel.
- **More than one charter can be open at once**, so two can be compared without closing either. This
  is the capability the modal editor structurally cannot provide, and it is the reason the read view
  is a disclosure in the list rather than a second dialog.
- **The two-line clamp remains the collapsed state.** It is a good summary; it was only ever wrong as
  the *only* state.
- **The edit dialog is unchanged.** Editing stays exactly where it is. This change removes the need
  to enter it in order to read, it does not alter what it does.

## Capabilities

### New Capabilities

None. This adds a read affordance to a shipped capability's existing management screen.

### Modified Capabilities

- `agent-charter`: "Charter management is available through the Hub UI" currently requires list,
  create, edit, and delete. It gains reading a charter's full content as a first-class operation,
  distinct from editing it, and requires that reading never opens a writable surface.

## Impact

**UI** — `hub/ui/src/components/charters/ChartersPage.tsx` gains a disclosure control and an expanded
read region per row. No API, schema, or backend change: `useCharters()` already returns full
`content` for every charter, which is why the list can clamp it today.

**No new dependency.** `hub/ui` has no markdown renderer (`package.json` dependencies are Radix,
React Query, Zustand, `lucide-react`, `date-fns`, the two fonts) and this change does not add one —
see design D2. The content is displayed as authored.

**Tests** — `hub/ui/src/__tests__/` gains coverage for the read view. No existing test asserts the
clamp is the only surface, so nothing is expected to break.

## Non-Goals

- **Not rendering markdown.** Adding a renderer is a dependency decision, and a legibility
  improvement rather than the defect. See design D2.
- **Not redesigning the charters screen** into a two-pane browser. Expanding in place answers the
  question that is blocked today at a fraction of the cost.
- **Not changing the edit dialog**, the charter API, or what is seeded.
- **Not adding a preview to the agent binding flow.** Reading a charter while choosing one to bind is
  a real adjacent need, and a separate change.
