## Why

An operator who has the project's instructions in front of them, selects all, deletes, and clicks
Save loses them. There is no confirmation, no undo, and no copy kept anywhere in the product.

The store is one row, replaced in place. `hub/hub/db/models.py:1058-1071` declares
`ProjectInstructions` with `project_id` as the primary key, a `content` column and an `updated_at`;
there is no second table, no revision column and no soft delete — `grep -n instructions
hub/hub/db/models.py` returns three lines, all inside that one class. The PUT handler at
`hub/hub/api/v1/instructions.py:66-67` is `row.content = content` followed by a commit. **The
previous text is not written anywhere before it is overwritten.** Nothing in AgentWeave can return
it.

The client offers no recovery either. `InstructionsPage.tsx:40-44` resets the textarea from `data`
whenever `data` changes, and `useSaveInstructions` invalidates the query on success
(`api/instructions.ts:24-26`), so the successful blanking save is immediately followed by a refetch
that re-seeds the editor with the empty string. Whatever the browser's own undo stack held for a
controlled `<textarea>` is not reachable after that.

So the single most destructive act available on this screen is also the one that costs the fewest
keystrokes, and it is indistinguishable to the product from an ordinary save.

## What this change is, and what it is not

**It is:** a confirmation step in the Instructions screen, on exactly one path — a save that would
replace non-empty stored instructions with nothing.

**It is not a change to what the route accepts.** The empty string stays a legitimate, intentional
value. `InstructionsUpdate`'s docstring (`hub/hub/api/v1/instructions.py:18-25`) records why the
field is named rather than read out of an untyped dict: so that no malformed body can blank the row
by accident. That guard is server-side, correct, and untouched here. The gap this change closes is
the opposite one — a *well-formed* request the operator meant to send only if they understood what
it would cost.

**It is not a second attempt at F271.** `2026-09-06-an-unread-editor-cannot-overwrite` shipped
(component `c7e615c`, bundle `676eba4`, archived 2026-09-06) and is `APPROVED`. It fixes the
*misleading* empty editor: a screen that shows an empty textarea because the read failed or has not
settled. This change is about the *honest* empty editor — the read succeeded, the operator saw the
real content, and cleared it on purpose. Neither substitutes for the other, and this change depends
on F271 having shipped: without its gate, "non-empty stored content" would have no reliable
baseline (see below).

**It does not confirm a replacement.** Overwriting instructions with *different* instructions is
outside scope. The operator's own new text is on screen and the act announces itself; a clear leaves
nothing behind to notice.

## What "non-empty" is measured against — the question the round was told to answer

`DIRECTION.md`'s 2026-09-07 section requires this round to confirm which of the component's
post-F271 states the confirmation's baseline is, *"so the confirmation cannot fire over a state that
was never really loaded"*. Read out of the shipped component:

| render branch | `InstructionsPage.tsx` | Save control | can the confirmation be reached? |
|---|---|---|---|
| `data` present | `:71-113` | rendered, via `actions` at `:62-69` | **yes — this is the only one** |
| `isError` | `:114-146` | `actions={undefined}` | no |
| neither (in flight, or no project selected) | `:147-151` | `actions={undefined}` | no |

The `actions` prop is `data ? (…) : undefined` at `:62`, and `SettingsSection` renders `actions`
in its heading (`components/environment/SettingsSection.tsx:58`), outside the `{children}` the three
branches live in (`:60`). So there is **no Save control at all** in the two states where nothing was
read — F271 chose absence over an inert button precisely so the write is impossible rather than
merely refused. The confirmation therefore cannot fire over an unloaded state, because there is
nothing to press.

**The baseline is `data.content`**, the value React Query holds for
`['project', projectId, 'instructions']` — the content that was actually read, for the project that
is actually selected. Three baselines that would have been wrong, ruled out explicitly:

- **`content`'s previous local value.** It starts at `''` (`:37`) and thereafter holds what the
  operator typed, not what is stored.
- **A dirty flag.** It cannot tell clearing from editing, which is the whole distinction.
- **`data.content` read under an `isError`-first render.** It is not, and this matters: the shipped
  component tests `data` first, and React Query keeps the last successful `data` across a failing
  background refetch. So after a refetch fails, `data.content` is still the last content
  successfully read — the correct baseline — and the editor is still on screen. An `isError`-first
  ordering would have removed the editor instead, which F271's design deliberately rejected.

## Which confirmation primitive — check before inventing one

There is no generic confirm component in `hub/ui/src/components/ui/` (it holds `button.tsx`,
`buttonVariants.ts`, `input.tsx` and nothing else). Four confirmation shapes already ship, and they
form a deliberate ladder:

| shape | where | weight |
|---|---|---|
| Type-to-confirm modal | `environment/DeleteProjectDialog.tsx` | heaviest — reproduce the project's name |
| Named-target modal | `spec/ArchiveConfirmDialog.tsx` + `hooks/useDialogFocus.ts` | modal, Cancel + destructive Confirm |
| Inline two-button swap | `jobs/JobCard.tsx:498-506` | lightest, replaces the control in place |
| Inline pre-emptive note, *deliberately not a dialog* | `tasks/TaskDetailDrawer.tsx:22-33` | no interruption at all |

**Proposed: the `ArchiveConfirmDialog` shape**, as a new small component reusing
`useDialogFocus`. The reasoning is the ladder's own. `DeleteProjectDialog`'s docstring says its
type-to-confirm exists because "no other destructive control in this product removes this much at
once" — clearing one project's instructions is not that, so type-to-confirm is too heavy.
`ArchiveConfirmDialog`'s docstring says a modal is warranted where the act has "no path back" while
its neighbours are reversible — which is exactly this act's shape, and unlike archiving there is not
even a record left behind.

`TaskDetailDrawer`'s note is the one that has to be answered rather than ranked, because it argues
*against* dialogs: "approval is the correct, designed behaviour and a confirmation step would teach
the operator to dismiss it." That objection is real and it is why this change confirms **only the
clearing path**. A confirmation on every Save would be dismissed within a week and would then be
worse than none. A confirmation an operator meets perhaps twice in the product's life is one they
will read.

Generalising the four into one shared `ConfirmDialog` is **not** proposed here. It would touch three
shipped surfaces with different weights for a change that needs one of them, and each carries a
docstring explaining why it is not the others.

## The tension with a shipped requirement, and how it is resolved

`project-instructions`'s *Hub UI provides instructions editor* carries the scenario:

> **WHEN** the stored instructions have been read, the user edits the textarea and clicks Save
> **THEN** content is persisted via PUT and UI confirms success

Read literally, that requires the click to persist — which a confirmation step breaks for the
clearing case. This is not a reason to abandon the change; it is a delta the change owes. The
requirement is MODIFIED so its save scenario governs saves that do not blank stored content, and the
new requirement owns the clearing path. Without that edit the change would ship contradicting a
requirement that shipped one day earlier.

Checked and found **not** in tension: *Save cannot write instructions that were never read* (this
change adds a gate strictly downstream of that one, and cannot weaken it); *Saving reports its
outcome* in `project-environment-settings:70` (a declined confirmation is not a save, so there is no
outcome to report — and the operator's typed state is preserved, which that requirement's second
scenario asks for anyway); *Settings may be changed one at a time* in the same spec, whose
"SHALL remain distinguishable from clearing it deliberately" this change reinforces rather than
contradicts.

## Impact

- `hub/ui/src/components/instructions/InstructionsPage.tsx` — the gate on `handleSave`.
- A new `hub/ui/src/components/instructions/ClearInstructionsDialog.tsx`.
- `hub/ui/src/__tests__/` — new coverage, mutation-checked.
- `hub/hub/static/ui` — the committed bundle, which **must** be rebuilt or the drive re-measures the
  old page and reports success.
- No Python changes. `hub/hub/api/v1/instructions.py` and `hub/hub/db/models.py` are untouched.
