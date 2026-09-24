## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: independently re-derive the call-site list from `grep`, each dialog's control order and `disabled` states, and whether any call site relies on focus staying on its trigger. Measure design D3's inference (task 1.6) before judging D3. Record in design's round log (done 2026-09-24; see the round log)
- [x] 0.2 R3: a second independent re-derivation; `openspec validate a-dialog-takes-the-keyboard-when-it-opens --strict` passes (bundle R3, then the 2026-09-24 operator review, both in the round log)
- [x] 0.3 The operator records the F307 initial-focus decision in `spec-queue/DECISIONS.md` (Cancel, or the destructive choice). The 2026-09-24 review (`spec-queue/tracks/reviews/B11-2026-09-24.md`) approved this change's Cancel design once the four dialogs were folded in; copy that into DECISIONS.md

## 1. Tests first — each must fail on today's code unless marked as a control

In `hub/ui/src/__tests__/useDialogFocus.test.tsx` unless named otherwise.

- [ ] 1.1 A harness dialog with two buttons, the first marked `data-dialog-initial-focus`, opened from a trigger button that holds focus: after mount, `document.activeElement` is the marked button. Record that it FAILS today (it is the trigger)
- [ ] 1.2 The same harness with the mark on the **second** button: focus lands on the second. Fails if the implementation uses DOM order instead of the mark
- [ ] 1.3 No mark: focus lands on the first focusable control. Record that it FAILS today
- [ ] 1.4 Every control disabled: `document.activeElement` is the panel. Record that it FAILS today
- [ ] 1.5 Per confirm-only dialog (`DeleteCharterDialog`, `ClearInstructionsDialog`, `ArchiveConfirmDialog`), in each component's own test file or a new `confirmDialogInitialFocus.test.tsx`: on open, focus is on Cancel, and a `keydown` Enter followed by the click the browser would dispatch calls `onCancel`, not `onConfirm`. Record that each FAILS today
- [ ] 1.6 **Measure D3 first.** Render a trigger button, focus it, open `AgentCreateDialog` (its `autoFocus` input), close it with Escape: record where `document.activeElement` is. If it is `<body>` (the inference), this is the failing test for D3; if it is the trigger, record that and mark D3's restore claim refuted in the round log
- [ ] 1.7 After the fix, 1.6's sequence leaves focus on the trigger, and the input still had focus while the dialog was open
- [ ] 1.8 Controls, PASS before and after: all seven existing cases in the file (Escape stand-down, Tab from outside, Shift+Tab, Tab inside, the two-dialog cases)
- [ ] 1.9 `CharterForm` (in `chartersUi.test.tsx`): from a focused "New Charter" button, opening the form puts focus on the Name input; Escape calls `onCancel` and, once the form unmounts, focus is back on the button. Record that it FAILS today (focus stays on the button; Escape does nothing)
- [ ] 1.10 `RunnerForm` (in `runnersUi.test.tsx`): the same three assertions from the "add runner" button. Record that it FAILS today
- [ ] 1.11 `JobForm` (in `jobFormLoopDeclaration.test.tsx` or a new `jobFormFocus.test.tsx`): opening puts focus on the Job Name input, **not** the header's Close button (so the test fails if the mark is missing and D1 falls back to DOM order); Escape calls `onCancel`; closing returns focus to the opener. Record that it FAILS today
- [ ] 1.12 `SetupModal` (in `setupModalAccessibility.test.tsx`): with a trigger button focused, render `open`: focus is on the Hub URL field (the existing assertion stays green); rerender `open={false}`: focus is back on the trigger. Record that the restore half FAILS today (focus is on `<body>`)
- [ ] 1.13 `ArchiveConfirmDialog`: open with `isPending={false}`, focus the Archive button, rerender with `isPending={true}`: `document.activeElement` is the panel, not the disabled button. Record that it FAILS today. The same for `JobForm` with its submit button focused and `isPending` becoming true

## 2. The fix

- [ ] 2.1 `useDialogFocus.ts`: after recording `returnFocusTo`, design D1's focus move
- [ ] 2.2 Add `tabIndex={-1}` to each call site's panel element
- [ ] 2.3 Mark Cancel with `data-dialog-initial-focus` in the three confirm-only dialogs
- [ ] 2.4 Replace `autoFocus` with `data-dialog-initial-focus` in `AgentCreateDialog`, `DeleteProjectDialog`, `ProjectManagerModal`
- [ ] 2.5 `CharterForm` and `RunnerForm`: a `panelRef` on the `role="dialog"` element with `tabIndex={-1}`, `useDialogFocus(true, panelRef, onCancel)`, and `data-dialog-initial-focus` on the Name input (design D5)
- [ ] 2.6 `JobForm`: the same, with the mark on the Job Name input
- [ ] 2.7 `SetupModal`: remove its focus effect (`:20-22`) and the `urlInput` ref if nothing else reads it; a `panelRef` on its `role="dialog"` element with `tabIndex={-1}`, `useDialogFocus(open, panelRef, onClose)`, and the mark on the Hub URL input. The hook call stays above `if (!open) return null`
- [ ] 2.8 `ArchiveConfirmDialog` and `JobForm`: design D6's effect, focusing the panel when `isPending` becomes true
- [ ] 2.9 Re-run the grep from design's context table (`role="dialog"`, `role="alertdialog"`, `aria-modal` under `hub/ui/src`): every hand-built modal dialog calls `useDialogFocus` or is `DirectoryPicker`. Record the list inline
- [ ] 2.10 Update `scripts/drive/t_d9_clearing_instructions_postchange.py` leg E: on open, focus is on Cancel; press 1 now reaches "Clear instructions"
- [ ] 2.11 Full vitest suite and `npm run lint`; `cd hub/ui && npm run build`, then `py -3.11 scripts/refresh_ui_bundle.py` (writes `ui-build-stamp.json`), and commit `hub/ui/src` with `hub/hub/static/ui` in one commit. Record counts inline

## 3. Drive it

- [ ] 3.1 On a trial Hub serving the rebuilt bundle, drive leg E of `t_d9_clearing_instructions_postchange.py` in a real browser and record each press's `document.activeElement`
- [ ] 3.2 In the same browser, open and close each of the four D5 dialogs from its trigger with the keyboard alone (Escape to close), and record where focus is on open and after close
