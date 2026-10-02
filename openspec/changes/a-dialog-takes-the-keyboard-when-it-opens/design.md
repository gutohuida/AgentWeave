# Design — a dialog takes the keyboard when it opens

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B11-2026-09-24.md`, §3) returned **REVISE
(spec scope)**, and the operator decided it: *"Dialogs: the four dialogs missing from the hook move
onto `useDialogFocus`."* Applied here:

- **HIGH, scope.** The ADDED SHALL covers every dialog, but four `aria-modal` dialogs neither take
  focus on open nor return it on close through the hook: the charter form (`ChartersPage.tsx:255`),
  `JobForm` (`JobForm.tsx:126`), the runner form (`RunnersPage.tsx:219`) and `SetupModal`, which
  focuses its field itself (`SetupModal.tsx:20-22`) and never restores. All four move onto
  `useDialogFocus` in this change (D5), each with a test that fails today (tasks 1.9-1.12). The Radix
  dialogs (`Drawer`, `CommandPalette`, `SpecDocumentPicker`) and `DirectoryPicker` already comply
  and are untouched.
- **LOW.** `ArchiveConfirmDialog` disables both buttons while pending, so the Archive button that was
  just pressed drops the keyboard to `<body>`. Focus moves to the panel while pending (D6, task 1.13).
- **Process.** R3 is now in the round log, with this review as the round after it.

The F307 decision this change is built on (focus in, Cancel on confirmations) is unchanged; the
review approved it once the scope was fixed.

**Built on the recommended answer to B11's F307 question** (ROUNDS.md D13, *"dialog initial
focus"*): **focus moves into the dialog on open, and a confirmation opens on Cancel.** If the
operator chooses the destructive button instead, D2's mark moves to it and the requirement's
confirmation scenario inverts; D1 and D3 stand either way.

## Context — measured on `ce086b6`, re-derived at `09127ba`

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
| Four more `aria-modal` dialogs do not use the hook at all (re-derived at `09127ba` by `grep -rn 'role="dialog"\|role="alertdialog"\|aria-modal' hub/ui/src`) | `ChartersPage.tsx:255` (`CharterForm`), `JobForm.tsx:126`, `RunnersPage.tsx:219` (`RunnerForm`), `SetupModal.tsx:49` |
| `SetupModal` focuses its URL field from its own effect and records nothing to restore | `SetupModal.tsx:20-22` |
| The Radix dialogs trap and restore focus themselves; `DirectoryPicker` records and restores its own | `layout/Drawer.tsx`, `palette/CommandPalette.tsx`, `spec/SpecDocumentPicker.tsx`; `DirectoryPicker.tsx:46-50` |

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

## D5 — The four dialogs outside the hook move onto it

Each gains a `panelRef` on its `role="dialog"` element, `tabIndex={-1}` on that element, a
`useDialogFocus(active, panelRef, onCancel)` call, and `data-dialog-initial-focus` on its first
field:

| Dialog | `active` | Marked field | Close callback |
|---|---|---|---|
| `CharterForm` (`ChartersPage.tsx:230`) | `true` (mounted only while shown, `:180`, `:191`) | the Name input (`#charter-name`) | `onCancel` |
| `RunnerForm` (`RunnersPage.tsx:177`) | `true` (mounted only while shown, `:142`, `:155`) | the Name input (`#runner-name`) | `onCancel` |
| `JobForm` (`JobForm.tsx:31`) | `true` (mounted only while shown, `JobsPage.tsx:193`) | the Job Name input (`:149`); the header's Close button (`:138`) is first in the DOM, so without the mark D1 would land on Close | `onCancel` |
| `SetupModal` | `open` (it is always mounted, `App.tsx:617`) | the Hub URL input; its own focus effect (`:20-22`) is **removed**, for D3's reason: a second focus mechanism on open would run before the hook records the opener | `onClose` |

Two consequences, both deliberate:

- **Escape now closes these four**, as it already closes the seven hook dialogs and as the Escape
  requirement in `hub-interaction-feedback` expects of a panel. For `JobForm` this matches a click
  on its scrim, which already calls `onCancel` even while a create is pending.
- **`SetupModal` cannot be escaped while the Hub is unconfigured**: `App.tsx:617` passes
  `open={!isConfigured || setupOpen}`, so `onClose` clears `setupOpen` and the dialog stays. That is
  today's rule for its submit path too, and is unchanged. Opened from the rail's settings control
  (`App.tsx:611`), closing it now returns the keyboard to that control.

## D6 — A dialog whose control is disabled under the keyboard keeps the keyboard

`ArchiveConfirmDialog` disables Cancel and Archive while the archive is pending
(`ArchiveConfirmDialog.tsx:58,61`). The operator pressed Archive, so Archive holds focus when it is
disabled, and a browser drops focus from a disabled control to `<body>`, behind the scrim. D1 cannot
help: it runs once, on open.

The dialog moves focus to its panel (which holds `tabIndex={-1}` after task 2.2) when `isPending`
becomes true:

```ts
useEffect(() => {
  if (isPending) panelRef.current?.focus()
}, [isPending])
```

When the archive fails, focus stays on the panel beside the error; the next Tab enters the panel's
first control (UI-1). When it succeeds the dialog unmounts and the hook's cleanup returns focus to the
opener. No other hook dialog disables the control that holds focus: `JobForm`'s pending state
disables its fields and buttons too, but its submit is by Enter or by the Create button, so the same
drop applies. `JobForm` gets the same effect (task 2.8) rather than a rule that forgets one.

## Open questions

None. The decision is recorded in the operator review above.

## Round log

- R1 2026-09-24: written.
- R2 2026-09-24: call sites re-derived by `grep "useDialogFocus("`: seven (`AgentCreateDialog`,
  `DeleteCharterDialog`, `DeleteProjectDialog`, `ClearInstructionsDialog`, `ProjectManagerModal`,
  `ArchiveConfirmDialog`, `TaskDetailDrawer`); `DirectoryPicker` and `InstructionsPage` only mention
  the hook. `DirectoryPicker` keeps its own focus and restore (`DirectoryPicker.tsx:48-49`) and is out
  of scope. `autoFocus` sites match (`:204`, `:67`, `:140`). D3's restore defect confirmed from React
  18.3.1's commit ordering (see D3); task 1.6 still measures it. No claim disagreed.
- R3 2026-09-24 (bundle-level, `spec-queue/tracks/B11.md:584-647`): 40 load-bearing claims across
  the bundle re-checked at the worktree's HEAD; five disagreed, none of them in this change. R3 did
  not re-derive the set of dialogs, which is the gap the review below found.
- Operator review 2026-09-24 (`spec-queue/tracks/reviews/B11-2026-09-24.md` §3): REVISE for scope.
  Applied as D5 and D6 (see the section at the top). Every citation above re-derived at `09127ba`:
  hook `:26-83`, `:58-68`, `:16/:47/:53`, confirm-dialog button lines, the three `autoFocus` lines,
  `TaskDetailDrawer.tsx:212-223`, and the four dialogs' lines all match. The `role="dialog"` /
  `aria-modal` grep lists 11 hand-built dialogs: the seven hook users plus the four D5 moves.
  `DirectoryPicker.tsx:108` carries `role="dialog"` without `aria-modal` and restores its own focus.
- Impl 2026-10-01 (tasks 1.1, 2.1, 2.2): `grep "useDialogFocus("` now finds an **eighth** call site,
  `StartFlowDialog.tsx:31`, not in R2/R3's seven or in this document's context table or D5 — added to
  the hook after the 2026-09-24 rounds. It already has its own `panelRef` on a `role="dialog"` element,
  so it took `tabIndex={-1}` alongside the other seven; task 2.9's re-grep should fold it into the
  D5-shape list explicitly. Also: D1 firing on mount moves focus into the panel's first focusable
  control before any Tab is pressed, which changed the starting state two of `useDialogFocus.test.tsx`'s
  existing Tab-wrap controls (task 1.8) assumed (focus still on the trigger when `tab()` is called) —
  both now call `trigger.focus()` again after the hook mounts, to put focus back outside the panel and
  still exercise the "Tab recovers focus from outside" path the tests are named for.
- Impl 2026-10-02 (task 1.6): measured, not inferred. `agentCreateDialogFocusRestore.test.tsx`
  mounts a real trigger and `AgentCreateDialog`, focuses the trigger, clicks it open (confirming
  `autoFocus` has already moved focus onto the name input), fires Escape, and checks
  `document.activeElement`. **It is `<body>`, confirming D3's inference exactly as predicted**: the
  cleanup's `returnFocusTo?.focus()` targets the now-detached input. The test's assertion is written
  as the post-fix behaviour (`expect(trigger).toHaveFocus()`), which is red today for that reason —
  this is 1.6's failing test, and 1.7 is the same assertion passing once the three `autoFocus`
  attributes become D1 marks.
- Impl 2026-10-02 (tasks 2.5, 1.9, 1.10): applied D5's row for `CharterForm` and `RunnerForm` — a
  `panelRef` on each `role="dialog"` element with `tabIndex={-1}`, `useDialogFocus(true, panelRef,
  onCancel)`, and `data-dialog-initial-focus` on `#charter-name`/`#runner-name`
  (`ChartersPage.tsx`, `RunnersPage.tsx`). Wrote 1.9/1.10's tests after the implementation this time
  (not test-first, unlike 1.6/2.4); to still get genuine red-then-green evidence rather than a
  passing-today record, the two component files were `git stash`-ed with the tests kept staged, the
  suite re-run (both new assertions failed — focus stayed on the trigger, matching the pre-fix
  claim — 16/18 passed, the 2 new ones red), then the stash was popped and the suite re-run again
  (18/18, 11/11). `npm run lint` and `openspec validate --strict` both clean.
- Impl 2026-10-02 (tasks 2.7, 1.12): `SetupModal` joined `useDialogFocus` — its own focus effect
  (`:20-22`) and the `urlInput` ref removed, `panelRef`/`tabIndex={-1}` on the `role="dialog"` div,
  `useDialogFocus(open, panelRef, onClose)` called above the `if (!open) return null` early return
  (its `active` argument is the `open` prop itself, since `App.tsx:617` always mounts this component
  and only toggles `open` — confirmed by task 1.12's rerender-based test, not an unmount/remount).
  `data-dialog-initial-focus` moved from the removed ref onto the Hub URL input. Wrote 1.12's test
  test-first (the deviation iteration 13 flagged for 1.9/1.10, continued from 1.11): extended
  `setupModalAccessibility.test.tsx` with a trigger-button harness, `rerender`-ing the same component
  instance between `open={false}` and `open` per the task text, rather than `fireEvent.keyDown`
  Escape as the other restore tests use — ran alone first against the untouched component and
  confirmed genuinely red (focus landed on `<body>`, matching the task's prediction exactly), then
  green after the component change (2/2 in the file).
- Impl 2026-10-02 (tasks 1.13, 2.8): wrote both halves of D6's test test-first — a new test in
  `confirmDialogInitialFocus.test.tsx` (a direct-render `ArchiveHarness` wrapping
  `ArchiveConfirmDialog`, `rerender`-ing the same instance from `isPending={false}` to `true`) and a
  new test in `jobFormFocus.test.tsx` (direct-render `JobForm`, same `rerender` shape). Both focus
  the Archive/Create button, assert it holds focus, rerender with `isPending={true}`, then assert
  `document.activeElement` is the panel (found by `container.querySelector('[tabindex="-1"]')`, since
  the panel carries no `role` of its own — the outer scrim `div` is `role="dialog"`) and is not the
  now-disabled button. Ran both against the untouched components first: **confirmed red for real** —
  `document.activeElement` stayed the disabled button in jsdom (it does not auto-blur a focused
  element when `disabled` is set, unlike D6's stated browser behaviour, but the assertion the test
  needs — that focus ends up on the panel — is false either way without the effect, so the test is
  still a genuine red for the fix this task adds). Added D6's effect verbatim
  (`useEffect(() => { if (isPending) panelRef.current?.focus() }, [isPending])`) to both components;
  both tests green (7/7 in the two files together).
