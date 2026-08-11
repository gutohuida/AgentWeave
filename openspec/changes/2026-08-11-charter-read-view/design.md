# Design — Charter read view

## Context

The charters screen already has every piece of data it needs. `useCharters()` returns each record's
full `content`, and the list renders it — clamped to two lines. Nothing has to be fetched, and no
endpoint has to change. What is missing is a way to *see* what is already in the browser's memory.

That is worth stating plainly, because it sets the size of this change: the defect is an affordance,
not a capability. The temptation is to answer it with a redesign.

## Goals / Non-Goals

**Goals:**

- An operator can read any charter in full without opening anything that can be saved.
- An operator can compare two charters without closing either.
- The screen still scans as a list when nothing is expanded.

**Non-Goals:**

- Rendering markdown, redesigning the screen, or touching the editor, the API, or seeding.

## Decisions

### D1 — A disclosure in the list, not a second dialog

The job is *choosing between* charters, not *inspecting* one. A read-only modal would fix the
"reading requires an editor" defect and leave the actual task — comparing nine of them — exactly as
hard as it is now, because a modal is one-at-a-time by construction.

Expanding in place allows two open at once, keeps the other rows visible as context, and needs no
navigation model, no focus trap, and no escape handling.

*Rejected: a read-only modal.* It is the smaller diff and it solves the smaller half of the problem.
The operator's report was that they cannot judge *the set*.

*Rejected: a two-pane browser (list left, content right).* It is the better long-term shape and it is
a redesign of the screen, with a selection model, a responsive story, and an empty state. If the
charters screen grows into a browsing surface, that is the change that should do it deliberately —
not a side effect of fixing a clamp.

### D2 — No markdown renderer, and the content is shown as authored

`hub/ui` has no markdown renderer today. Adding one is a real decision: a runtime dependency in a
self-hosted app, plus a sanitisation question, because charter content is operator-authored text that
would then be interpreted rather than displayed.

Against that, the benefit is modest. Charter markdown is headings, bullets and bold — it is readable
as written, and `#` and `-` do not obstruct the judgment being made. The content is also *the exact
string injected into the agent's turn*, so showing it verbatim is arguably more honest than showing a
rendering of it: what the operator reads is what the model receives.

So: `white-space: pre-wrap`, the existing monospace face already used for charter content in the
editor, and the existing type scale.

*Rejected: adding `react-markdown` or similar.* Reconsider it if operators start authoring long
charters and complain about legibility — that is evidence this change does not have.

*Rejected: a hand-rolled mini-renderer.* A partial markdown implementation is the worst option: it
carries the sanitisation burden of a renderer and the fidelity of neither.

### D3 — Expansion is independent per row, and defaults to collapsed

Every row opens and closes on its own; opening one does not close another. That is the whole point of
D1, and it is why this is not an accordion.

All rows start collapsed. A screen that opens with nine charters expanded is a wall of text that has
lost the list, and the collapsed list is a genuinely useful summary — it is only its exclusivity that
was the defect.

Expansion state is component state. It is not persisted, not in the URL, and not in the query cache:
it describes what the operator is looking at right now, and restoring it across a reload would be
restoring a scroll position, not a decision.

### D4 — The disclosure is a real button, and reading is visibly not editing

The control is a `<button>` with `aria-expanded` and an accessible name that includes the charter's
name, so nine of them are distinguishable in a screen reader's control list. It uses the existing
`Icon` component, per the repository's single-icon-system rule.

The expanded region is styled as text, not as a form: no border, no input background, no focus ring
of its own, and no cursor change. This matters beyond aesthetics — the defect being fixed is that
reading and editing were the same surface, so the read surface has to be visibly incapable of
accepting input. A read-only `<textarea>` would reintroduce exactly the ambiguity this change exists
to remove.

### D5 — Clicking the row body toggles too, but the delete button is not in that target

Making the whole row a toggle target is the affordance an operator expects from a list like this.
The risk is the destructive control sitting in the same row: a click intended for the row that lands
on delete is unrecoverable.

Delete and edit already live in their own control cluster and stop propagation, so the toggle target
is the row's text region only. Stated here because a later refactor that "simplifies" the row into
one clickable container would silently put a destructive action inside a casual toggle target.

## Risks / Trade-offs

- **Long charters make the list tall** → that is the operator opening a document deliberately; the
  collapsed default and independent toggling keep it under their control.
- **Unrendered markdown reads as noisy to someone expecting a document** → D2 accepts this, and 7.1
  of the test guide asks the operator directly whether it is good enough, so the evidence for
  reconsidering is collected rather than assumed.
- **Expansion state lost on refresh** → deliberate (D3), and cheap to reverse if it turns out to
  matter.
- **This does not help while binding a charter to an agent**, which is the other moment the text is
  wanted → named as a non-goal so it is a known follow-up rather than an oversight.
