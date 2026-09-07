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

**The requirement wording had lost this, and R2 put it back.** The predicate above trims both sides
and always did; the delta's own English did not. The MODIFIED save scenario said *"does not replace
non-empty stored instructions with nothing"*, which is a different rule — under it a save writing a
single newline over four hundred lines is required to persist, while the added requirement requires
it to be confirmed first. Both requirements now spell out *"containing more than whitespace"* and
*"empty or only whitespace"* in their own words, because a requirement is read on its own and cannot
borrow a definition from its neighbour. Nothing in this design changed; what changed is that the
spec now says it.

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

## R2's results — what was re-derived, and what it changed

R2 read the component, the route, the model and the four confirmation shapes *before* the proposal,
and re-ran every measurement R1 quoted rather than carrying it forward. The argument survived. Four
things were wrong or unmeasured.

1. **The predicate's whitespace term was missing from the spec** — the finding above, folded into
   D1 and into both requirements. This is the only one that changed what the change *requires*.
2. **`grep -n instructions hub/hub/db/models.py` returns two lines, not three** (`:1061`, `:1065`);
   three needs `-i`. The count was the smaller problem: a single file's grep cannot establish "no
   history table" at all. `proposal.md` now carries the repository-wide measurement instead —
   `project_instructions` is referenced in exactly four places, none of them a second table or a
   foreign key, and no migration names it.
3. **The PUT's line range was wrong.** `row.content = content` is at
   `hub/hub/api/v1/instructions.py:61`; `:66` is the commit. The cited `:66-67` was the commit and
   the return, and contained neither of the two statements it was quoted for. Corrected.
4. **R1's unmeasured React Query belief is now measured, and it holds.** `@tanstack/react-query`
   `5.90.21`: `query-core/src/utils.ts:386-402` applies `replaceEqualDeep(prevData, data)` unless
   `structuralSharing` is `false`, and that returns the *previous* reference when the two are deeply
   equal — so a refetch returning unchanged content leaves `data` identity stable, the `[data]`
   effect does not re-run, and an in-progress edit is not clobbered. **No defect to file.** The
   adjacent hazard — a refetch returning content that genuinely *changed* would clobber an edit —
   was chased and is not reachable spontaneously either: `main.tsx:11` sets
   `refetchOnWindowFocus: false` for every query, so nothing refetches this key but mount, reconnect
   and the save's own invalidation. Also checked and unchanged: D5's double-confirm edge is real for
   the reason it gives, `useDialogFocus.ts:20-47` is the effect it is cited as, `JobCard.tsx:498-506`
   and `TaskDetailDrawer.tsx:22-33` are exact, the `actions` gate and `SettingsSection.tsx:58`/`:60`
   are as described, and the MODIFIED requirement's header and SHALL line are byte-identical to
   `openspec/specs/project-instructions/spec.md:34-35`.

## What R2 did not do, so R3 does not assume it

- **R2 drove nothing either.** No browser was opened, no Hub started, no PUT watched on a wire. Every
  claim in this document remains a source reading. The react-query result in particular is measured
  in the library's own source, not observed in the running page. **Driving is still owed, and it is
  R3's to take** — the clearing path as it exists today, select all, delete, Save, watching the wire.
- **R2 did not check the delta against every shipped requirement in the corpus.** It re-checked the
  two `project-instructions` neighbours R1 named and stopped there. The sweep across
  `project-environment-settings` that R1 claims to have done was not independently repeated.
- **The stored-side trim is still a judgement, not a measurement.** R2 made it *legible* — it is now
  stated in both requirements and pinned by a scenario clause rather than living in prose — but
  whether whitespace-only stored content deserves no interruption is still an unmeasured call, and
  it is still the smallest thing in this design.
