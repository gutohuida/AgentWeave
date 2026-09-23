## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: independently re-derive the call-site list from `grep`, each dialog's control order and `disabled` states, and whether any call site relies on focus staying on its trigger. Measure design D3's inference (task 1.6) before judging D3. Record in design's round log
- [ ] 0.2 R3: a second independent re-derivation; `openspec validate a-dialog-takes-the-keyboard-when-it-opens --strict` passes
- [ ] 0.3 The operator records the F307 initial-focus decision in `spec-queue/DECISIONS.md` (Cancel, or the destructive choice)

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

## 2. The fix

- [ ] 2.1 `useDialogFocus.ts`: after recording `returnFocusTo`, design D1's focus move
- [ ] 2.2 Add `tabIndex={-1}` to each call site's panel element
- [ ] 2.3 Mark Cancel with `data-dialog-initial-focus` in the three confirm-only dialogs
- [ ] 2.4 Replace `autoFocus` with `data-dialog-initial-focus` in `AgentCreateDialog`, `DeleteProjectDialog`, `ProjectManagerModal`
- [ ] 2.5 Update `scripts/drive/t_d9_clearing_instructions_postchange.py` leg E: on open, focus is on Cancel; press 1 now reaches "Clear instructions"
- [ ] 2.6 Full vitest suite and `npm run lint`; rebuild the bundle and commit `hub/ui/src` with `hub/hub/static/ui`. Record counts inline

## 3. Drive it

- [ ] 3.1 On a trial Hub serving the rebuilt bundle, drive leg E of `t_d9_clearing_instructions_postchange.py` in a real browser and record each press's `document.activeElement`
