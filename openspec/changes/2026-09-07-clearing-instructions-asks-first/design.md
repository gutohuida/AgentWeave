# Design — clearing instructions asks first

## D1. The predicate, and why it is stated in both directions

The confirmation fires when, and only when, all of these hold at the moment Save is clicked:

```
data !== undefined                 // the read succeeded — guaranteed by F271's gate, see D2
data.content.trim() !== ''         // something real is stored
content.trim() === ''              // nothing real is about to be written
```

**Trim is on both sides deliberately.**

On the *outgoing* side it is the load-bearing half. An operator who selects all and deletes usually
leaves `''`, but a textarea can as easily be left holding `'\n'` or two spaces, and that write
destroys the instructions just as completely as an empty one does. A predicate testing
`content === ''` would let the commonest near-miss through.

On the *stored* side it is a smaller judgement: instructions consisting only of whitespace are not
content anyone loses. Overwriting them is not destructive, so it is not worth an interruption.

What is **not** trimmed is what gets written. The confirmed save sends `content` exactly as typed,
unchanged, as every other save does. This change interposes a question; it does not edit the
operator's text.

## D2. Why the predicate needs no state check of its own

`data !== undefined` is in the list above for completeness, not because the implementation must test
it. Save is rendered only inside `actions={data ? … : undefined}` (`InstructionsPage.tsx:62`), so
`handleSave` is unreachable when `data` is undefined. F271 chose that shape over a `disabled`
attribute for exactly this reason — see its `tasks.md` 1.4, which records that an inert button
"leaves the two `data === undefined` routes to be closed by markup rather than by the write never
being possible."

The consequence for this change is worth stating plainly, because it is what `DIRECTION.md` asked
the round to confirm: **the confirmation cannot fire over a state that was never really loaded, and
it does not need a guard to prevent it.** The guard is structural and already shipped. An
implementer who moves Save out of `actions` and into the gated `{children}` keeps that property; one
who moves it out of the gate entirely breaks both this change and F271 at once.

## D3. The dialog says how much is about to be lost

A confirmation that only asks "are you sure?" transfers no information and earns its dismissal. This
one states the size of what would be discarded — a line count read off `data.content`, the content
that was actually read — so the operator can tell a three-word note from four hundred lines of
project rules before they answer.

It also states the fact the operator cannot discover anywhere else: **AgentWeave keeps no copy.**
That is measured, not asserted for effect (see `proposal.md`'s first section: one row, upserted).

The project's name belongs in the dialog for the same reason `ArchiveConfirmDialog` names the
document — the Instructions screen is per-project and a switcher sits beside it.

## D4. Cancel

Cancel issues nothing and changes nothing. The operator's empty textarea stays empty: they typed it,
and silently restoring the old text under them would be a second surprise answering the first. The
screen after Cancel is exactly the screen before Save was clicked.

Escape and a click on the scrim are Cancel. `useDialogFocus` already implements Escape, focus
trapping and focus restoration (`hooks/useDialogFocus.ts:20-47`); reusing it is most of the reason
to copy `ArchiveConfirmDialog`'s shape rather than write a new one.

## D5. Two edges taken deliberately, not overlooked

**Confirming twice for one clear.** `useSaveInstructions` invalidates the query on success, and
React Query serves the previous `data` while the refetch is in flight. So an operator who confirms a
clear and immediately clicks Save again, within that window, meets the dialog a second time —
`data.content` is still the pre-save text. The second write is a no-op. Asking twice about a no-op
is strictly safer than the alternative, which would be to derive the baseline from something other
than the last successful read, and D1 rules that out.

**A stale baseline.** If the row changed server-side since the last read, `data.content` is stale
and the dialog's line count is stale with it. Out of scope: this screen has always had a
last-writer-wins relationship with the row, this change neither improves nor worsens it, and the
dialog's central claim — *nothing here keeps a copy* — is true regardless of whose text is being
replaced.

## D6. Where the requirement lives

In `project-instructions`, with the editor it constrains, not in
`project-environment-settings`. The latter states the *grammar* of a settings surface — what a
section owes in every state, how a save reports its outcome. This is a rule about one particular
value's destruction, which is a property of instructions and not of settings sections in general.

The MODIFIED requirement in the delta is there for the reason `proposal.md` gives: *Hub UI provides
instructions editor*'s save scenario says the click persists, and after this change one class of
click asks first instead.

## D7. What this change does not do, so a later round does not assume it did

- It does not give instructions a history, an undo, or a restore. Those would make the confirmation
  unnecessary and are a much larger change; the confirmation is the cheap thing that makes the
  destruction visible.
- It does not touch `hub/hub/api/v1/instructions.py`. A caller with the API key can still blank the
  row in one request, and should be able to.
- It does not address F296 (`scripts/drive/t_d4_instructions_failed_load.py:316`, role `button`
  where the control is a `combobox`). That harness is adjacent to this change's drive and the fix is
  one word, but it is a separate, unowned item and folding it in silently would misreport what this
  change cost.

## Open for R2 and R3

1. **Drive the control before trusting this document.** Every claim above about the shipped
   component is read out of source at the line numbers given; none of it was driven in a browser
   this round. The specific thing to operate is the clearing path as it exists *today* — select all,
   delete, Save — and to watch the wire for the PUT.
2. **The `useEffect` at `:40-44` re-seeds `content` from `data` on every `data` change.** R1 believes
   React Query's structural sharing keeps `data`'s identity stable when a refetch returns unchanged
   content, so a background refetch does not clobber an in-progress edit — but R1 did not measure
   this, and it is exactly the kind of belief this repository's round discipline exists to falsify.
   If it is wrong, it is a pre-existing defect rather than one this change introduces, and it should
   be filed rather than absorbed.
3. **Whether `trim()` on the stored side is right.** D1 argues whitespace-only stored content is not
   worth protecting. That is a judgement, not a measurement, and it is the smallest thing in this
   design.
