# Proposal — a dialog takes the keyboard when it opens

**Round 1, 2026-09-24** (bundle B11, `spec-queue/tracks/B11.md`). Finding: **F307 (B)**, the
initial-focus half the operator split off as its own question (`DAY-1`, 2026-09-10; ROUNDS.md D13
*"dialog initial focus"*). Its Tab half is fixed (UI-1, 2026-09-23). Re-verified on `ce086b6`.
**Nothing here is implemented yet.**

## Why

`useDialogFocus` (`hub/ui/src/hooks/useDialogFocus.ts`) never moves focus when a dialog opens. Its
effect records `document.activeElement` to restore later (`:28`), binds a key handler, and stops.
UI-1 made the first Tab enter the panel (`:64-68`), and its comment says where focus *starts* is
"D13's separate question". So today, when a confirm-only dialog opens, the keyboard is still on the
control that opened it, behind the scrim:

- **Enter or Space acts on the trigger again**, not on the dialog. For `ClearInstructionsDialog`
  that trigger is Save.
- **A screen reader is not taken into the dialog**, so the question it asks is not announced.

Seven components use the hook (`grep -rln useDialogFocus hub/ui/src --include=*.tsx`, less the hook
and its test): `AgentCreateDialog`, `DeleteProjectDialog`, `ProjectManagerModal` (each `autoFocus`
an input), `DeleteCharterDialog`, `ClearInstructionsDialog`, `ArchiveConfirmDialog` (two buttons
each, Cancel first in the DOM), and `TaskDetailDrawer`.

**A second defect in the same effect, inferred and not yet measured** (design D3): for the three
dialogs that use `autoFocus`, React focuses the input during the commit, before the hook's effect
runs, so the element the hook records to restore on close is that input, which unmounts with the
dialog. Closing such a dialog would then leave the keyboard on `<body>`, not on the button that
opened it. Task 1.6 measures it before anything is built on it.

## What Changes

- **The hook moves focus into the panel when it opens** (design D1): to the element marked
  `data-dialog-initial-focus`, else the panel's first focusable control, else the panel itself.
- **A confirmation opens on the answer that changes nothing** (design D2). The three confirm-only
  dialogs mark Cancel. The mark, not DOM order, decides it, so reordering the buttons cannot flip a
  destructive dialog onto its destructive button.
- **The hook records where focus was before anything in the dialog takes it** (design D3). The three
  `autoFocus` inputs become `data-dialog-initial-focus`, so the hook is the only thing that moves
  focus on open and it can record the opener first.
- `TaskDetailDrawer` takes the same default (its first focusable control). Its blocking-reason field
  keeps focusing itself when that panel appears (`TaskDetailDrawer.tsx:219-223`, F309), which
  happens after open and is unaffected.

UI only. No backend, no migration.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `hub-interaction-feedback`: a new requirement, *A dialog takes the keyboard when it opens and gives
  it back when it closes*.

## Impact

- `hub/ui/src/hooks/useDialogFocus.ts`, the six dialogs above that need a mark or lose `autoFocus`,
  and `hub/ui/src/__tests__/useDialogFocus.test.tsx` plus per-dialog tests.
- **A UI bundle**: it reaches `:8000`'s live app on the next reload once committed. No backend half,
  so no restart ordering.
- `scripts/drive/t_d9_clearing_instructions_postchange.py` leg E currently asserts the old first
  press; F307's entry says fixing it "will fail that file loudly". Update the leg in the same commit.
