# Design — a dialog takes the keyboard when it opens

**Built on the recommended answer to B11's F307 question** (ROUNDS.md D13, *"dialog initial
focus"*): **focus moves into the dialog on open, and a confirmation opens on Cancel.** If the
operator chooses the destructive button instead, D2's mark moves to it and the requirement's
confirmation scenario inverts; D1 and D3 stand either way.

## Context — measured on `ce086b6`

| Fact | Where |
|---|---|
| The effect records the opener, binds keys, and never moves focus | `hub/ui/src/hooks/useDialogFocus.ts:26-83` |
| A Tab from outside the panel now enters it (UI-1) | `useDialogFocus.ts:58-68` |
| Only the newest open dialog answers keys | `useDialogFocus.ts:16`, `:47`, `:53` (module-level `openDialogs`) |
| Confirm-only dialogs render Cancel, then the destructive button | `DeleteCharterDialog.tsx:61,64`; `ClearInstructionsDialog.tsx:70,73`; `ArchiveConfirmDialog.tsx:58,61` |
| `ArchiveConfirmDialog` disables both buttons while pending | `ArchiveConfirmDialog.tsx:58,61` (`disabled={isPending}`) |
| Three dialogs focus an input with `autoFocus` | `AgentCreateDialog.tsx:204`, `DeleteProjectDialog.tsx:67`, `ProjectManagerModal.tsx:140` |
| The drawer focuses its reason field itself, and removed `autoFocus` for F309 | `TaskDetailDrawer.tsx:212-223` |
| The drawer is not modal: no scrim, click-outside closes | `TaskDetailDrawer.tsx:227-230` |

## D1 — Focus moves in on open

At the start of the effect, after recording `returnFocusTo`:

```ts
const panel = panelRef.current
if (panel && !panel.contains(document.activeElement)) {
  const marked = panel.querySelector<HTMLElement>('[data-dialog-initial-focus]:not([disabled])')
  const first = panel.querySelector<HTMLElement>(FOCUSABLE)
  ;(marked ?? first ?? panel).focus()
}
```

- **The panel itself is the last resort**, for a dialog whose every control is disabled
  (`ArchiveConfirmDialog` while pending). Each panel gets `tabIndex={-1}` so it can hold focus
  without joining the Tab order.
- **Only when focus is outside the panel**, so a dialog that deliberately focused something inside
  itself is not overridden. After D3 no dialog does, but the guard costs nothing.

## D2 — A confirmation opens on the answer that changes nothing

The three confirm-only dialogs put `data-dialog-initial-focus` on Cancel. Two reasons, in order:

1. **An Enter pressed out of habit should cost nothing.** The operator arrived by pressing Save or
   Archive. A second Enter, arriving on a dialog that opened on its destructive button, would confirm
   a destruction the operator has not read yet. On Cancel it closes the question.
2. **It is the established pattern.** WAI-ARIA's dialog pattern recommends focusing the least
   destructive action when an action is irreversible. `ClearInstructionsDialog` clears what the
   operator typed; `DeleteCharterDialog` is a hard delete (F186).

A mark, not DOM order, because today's order happens to put Cancel first, and a later restyle that
swaps the buttons would silently move focus onto the destructive one.

## D3 — The hook alone moves focus on open, so it can record the opener

React applies `autoFocus` in the commit phase, when the host element mounts. The hook's `useEffect`
runs after the commit. So for `AgentCreateDialog`, `DeleteProjectDialog` and `ProjectManagerModal`,
`returnFocusTo` (`useDialogFocus.ts:28`) is read after the input has focus, and is that input. On
close, the cleanup focuses it (`:81`) after it has unmounted, which does nothing, and the keyboard is
left on `<body>`.

**Confirmed from source by R2, not yet by a run.** React DOM 18.3.1 (`hub/ui/package.json`) focuses
an `autoFocus` host element in `commitMount` (`react-dom.development.js:11029-11030`), which runs in
the layout phase; `useEffect` callbacks run after it, so `returnFocusTo` is the input. On close,
`AgentCreateDialog` returns `null` (`if (!open) return null`), the input is removed in the mutation
phase (the browser moves focus to `<body>`), and the passive cleanup's `returnFocusTo?.focus()`
targets a detached node. Task 1.6 stays as the failing test. If it somehow does not reproduce in
jsdom, D3 shrinks to "replace `autoFocus` with the mark anyway", because two mechanisms deciding
initial focus is the F309 shape that `TaskDetailDrawer` already removed once.

The three `autoFocus` attributes become `data-dialog-initial-focus`, so D1 is the only focus move on
open and it runs after `returnFocusTo` is captured.

## D4 — What the options were

| Option | What it would break | What it releases |
|---|---|---|
| **Focus in, Cancel on confirmations (this change)** | Nothing that works today: no dialog relies on focus staying on its trigger. | Enter-on-trigger, the unannounced dialog, and (if 1.6 reproduces) lost focus on close. |
| Focus in, the destructive button on confirmations | Makes a habitual Enter destructive. | Saves one Tab for an operator who means it. |
| Focus the panel itself, no control | Nothing; screen readers announce the dialog. | Enter does nothing until the operator Tabs, which is safe but adds a keystroke to every dialog. |
| Leave focus on the trigger (today) | — | — |

## Open questions

None beyond the decision this is built on.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: call sites re-derived by `grep "useDialogFocus("`: seven (`AgentCreateDialog`,
  `DeleteCharterDialog`, `DeleteProjectDialog`, `ClearInstructionsDialog`, `ProjectManagerModal`,
  `ArchiveConfirmDialog`, `TaskDetailDrawer`); `DirectoryPicker` and `InstructionsPage` only mention
  the hook. `DirectoryPicker` keeps its own focus and restore (`DirectoryPicker.tsx:48-49`) and is out
  of scope. `autoFocus` sites match (`:204`, `:67`, `:140`). D3's restore defect confirmed from React
  18.3.1's commit ordering (see D3); task 1.6 still measures it. No claim disagreed.
