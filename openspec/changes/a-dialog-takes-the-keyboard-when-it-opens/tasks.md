## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: independently re-derive the call-site list from `grep`, each dialog's control order and `disabled` states, and whether any call site relies on focus staying on its trigger. Measure design D3's inference (task 1.6) before judging D3. Record in design's round log (done 2026-09-24; see the round log)
- [x] 0.2 R3: a second independent re-derivation; `openspec validate a-dialog-takes-the-keyboard-when-it-opens --strict` passes (bundle R3, then the 2026-09-24 operator review, both in the round log)
- [x] 0.3 The operator records the F307 initial-focus decision in `spec-queue/DECISIONS.md` (Cancel, or the destructive choice). The 2026-09-24 review (`spec-queue/tracks/reviews/B11-2026-09-24.md`) approved this change's Cancel design once the four dialogs were folded in; copy that into DECISIONS.md

## 1. Tests first — each must fail on today's code unless marked as a control

In `hub/ui/src/__tests__/useDialogFocus.test.tsx` unless named otherwise.

- [x] 1.1 A harness dialog with two buttons, the first marked `data-dialog-initial-focus`, opened from a trigger button that holds focus: after mount, `document.activeElement` is the marked button. Record that it FAILS today (it is the trigger) — confirmed red (`hub/ui/src/__tests__/useDialogFocus.test.tsx`, "initial focus on open (D1)"), then green after 2.1/2.2
- [x] 1.2 The same harness with the mark on the **second** button: focus lands on the second. Fails if the implementation uses DOM order instead of the mark. Passes today — 2.1/2.2 already implement `marked ?? first ?? panel`
- [x] 1.3 No mark: focus lands on the first focusable control. Passes today, same reason as 1.2
- [x] 1.4 Every control disabled: `document.activeElement` is the panel. Passes today, same reason as 1.2
- [x] 1.5 Per confirm-only dialog (`DeleteCharterDialog`, `ClearInstructionsDialog`, `ArchiveConfirmDialog`), in `confirmDialogInitialFocus.test.tsx`: on open, focus is on Cancel, and a `keydown` Enter followed by the click the browser would dispatch calls `onCancel`, not `onConfirm`. All three **pass today, not FAILS**: none of the three marks any control with `data-dialog-initial-focus` yet (2.3 is unticked), but D1's fallback chain is `marked ?? first ?? panel`, and in all three components the ghost "Cancel" button is the first focusable control in DOM order (JSX renders it before Confirm/Delete/Clear/Archive) — so `first` already resolves to Cancel. Same situation as 1.2-1.4: the task text predates 2.1/2.2 landing. These stand as regression coverage for the DOM-order fallback on these three dialogs specifically, not red-then-green evidence; 2.3's mark will make the "first" case explicit and defend against the two buttons ever being reordered
- [x] 1.6 **Measure D3 first.** Render a trigger button, focus it, open `AgentCreateDialog` (its `autoFocus` input), close it with Escape: record where `document.activeElement` is. If it is `<body>` (the inference), this is the failing test for D3; if it is the trigger, record that and mark D3's restore claim refuted in the round log — measured `<body>`, confirming D3 (`hub/ui/src/__tests__/agentCreateDialogFocusRestore.test.tsx`, named otherwise per this section's header; see design's round log)
- [x] 1.7 After the fix, 1.6's sequence leaves focus on the trigger, and the input still had focus while the dialog was open — confirmed: `agentCreateDialogFocusRestore.test.tsx` now passes (its line 43 assertion already covered the input-focus-while-open half; line 52 covers the restore half), both green after task 2.4
- [x] 1.8 Controls, PASS before and after: all seven existing cases in the file (Escape stand-down, Tab from outside, Shift+Tab, Tab inside, the two-dialog cases) — before: iteration 2's pre-change baseline full-suite run (`3 files / 5 tests failed`, none in this file) confirms all seven were green before any D1 code existed; after: `npx vitest run src/__tests__/useDialogFocus.test.tsx` at `096829c`, **11/11 passed** (the seven plus D1's four), re-run standalone this iteration to confirm, not inferred from the batch total
- [x] 1.9 `CharterForm` (in `chartersUi.test.tsx`): from a focused "New Charter" button, opening the form puts focus on the Name input; Escape calls `onCancel` and, once the form unmounts, focus is back on the button — done: confirmed red (focus stayed on the trigger) by stashing 2.5's component change and re-running, then green after it (18/18 in the file, 1 new)
- [x] 1.10 `RunnerForm` (in `runnersUi.test.tsx`): the same three assertions from the "add runner" button — done, same red/green method, same file batch (11/11, 1 new)
- [x] 1.11 `JobForm` (in `jobFormLoopDeclaration.test.tsx` or a new `jobFormFocus.test.tsx`): opening puts focus on the Job Name input, **not** the header's Close button (so the test fails if the mark is missing and D1 falls back to DOM order); Escape calls `onCancel`; closing returns focus to the opener. Record that it FAILS today — done, new `jobFormFocus.test.tsx` written before 2.6's component change: confirmed red for real (focus stayed on the "New Job" trigger; the dialog stayed open on Escape, since `JobForm` called no dialog-focus hook at all), then green after 2.6 (2/2)
- [x] 1.12 `SetupModal` (in `setupModalAccessibility.test.tsx`): with a trigger button focused, render `open`: focus is on the Hub URL field (the existing assertion stays green); rerender `open={false}`: focus is back on the trigger. Record that the restore half FAILS today (focus is on `<body>`) — done: new test written test-first, confirmed red for real on the untouched component (focus landed on `<body>`), then green after 2.7 (2/2 in the file)
- [x] 1.13 `ArchiveConfirmDialog`: open with `isPending={false}`, focus the Archive button, rerender with `isPending={true}`: `document.activeElement` is the panel, not the disabled button. Record that it FAILS today. The same for `JobForm` with its submit button focused and `isPending` becoming true — done: new test in `confirmDialogInitialFocus.test.tsx` (direct-render `ArchiveHarness`, `rerender`) and a new test in `jobFormFocus.test.tsx` (direct-render `JobForm`, `rerender`), both confirmed red for real against the untouched components (focus stayed on the now-disabled button, not the panel), then green after 2.8

## 2. The fix

- [x] 2.1 `useDialogFocus.ts`: after recording `returnFocusTo`, design D1's focus move
- [x] 2.2 Add `tabIndex={-1}` to each call site's panel element — 8 call sites, not R2/R3's 7:
      `grep "useDialogFocus("` today also finds `StartFlowDialog.tsx:31`, added after the 2026-09-24
      rounds and not in design's context table or D5. It already follows the same `panelRef`/`role="dialog"`
      shape as the other seven, so it got `tabIndex={-1}` here too; flagged for 2.9's re-grep, not a
      blocker for this slice
- [x] 2.3 Mark Cancel with `data-dialog-initial-focus` in the three confirm-only dialogs — done: `DeleteCharterDialog.tsx`, `ClearInstructionsDialog.tsx`, `ArchiveConfirmDialog.tsx`. `confirmDialogInitialFocus.test.tsx` (1.5) stayed green throughout, now passing on the explicit mark rather than the DOM-order fallback (14/14 with `useDialogFocus.test.tsx`)
- [x] 2.4 Replace `autoFocus` with `data-dialog-initial-focus` in `AgentCreateDialog`, `DeleteProjectDialog`, `ProjectManagerModal` — done; all three already call `useDialogFocus` (`AgentCreateDialog.tsx:164`, `DeleteProjectDialog.tsx:34`, `ProjectManagerModal.tsx:73`), so the mark is live immediately
- [x] 2.5 `CharterForm` and `RunnerForm`: a `panelRef` on the `role="dialog"` element with `tabIndex={-1}`, `useDialogFocus(true, panelRef, onCancel)`, and `data-dialog-initial-focus` on the Name input (design D5) — done: `ChartersPage.tsx` (`CharterForm`), `RunnersPage.tsx` (`RunnerForm`), `#charter-name`/`#runner-name` marked
- [x] 2.6 `JobForm`: the same, with the mark on the Job Name input — done: `panelRef`/`tabIndex={-1}` on the `role="dialog"` element, `useDialogFocus(true, panelRef, onCancel)`, `data-dialog-initial-focus` on the Job Name input. Unlike `CharterForm`/`RunnerForm` (2.5), this one changes observed behaviour: the header's Close button is first in DOM order, so without the mark D1's fallback would have focused Close instead
- [x] 2.7 `SetupModal`: remove its focus effect (`:20-22`) and the `urlInput` ref if nothing else reads it; a `panelRef` on its `role="dialog"` element with `tabIndex={-1}`, `useDialogFocus(open, panelRef, onClose)`, and the mark on the Hub URL input. The hook call stays above `if (!open) return null` — done: effect and ref removed, `panelRef`/`tabIndex={-1}` on the dialog `div`, `useDialogFocus(open, panelRef, onClose)` called above the early return, `data-dialog-initial-focus` on the Hub URL input
- [x] 2.8 `ArchiveConfirmDialog` and `JobForm`: design D6's effect, focusing the panel when `isPending` becomes true — done: `useEffect(() => { if (isPending) panelRef.current?.focus() }, [isPending])` added to both, verbatim from design D6
- [x] 2.9 Re-run the grep from design's context table (`role="dialog"`, `role="alertdialog"`,
      `aria-modal` under `hub/ui/src`, excluding `__tests__`) — 13 components carry the role, 12 of
      them `aria-modal="true"`, confirming every one of the 12 calls `useDialogFocus` and the 13th
      (`DirectoryPicker.tsx:108`, `role="dialog"` with no `aria-modal`) keeps its own focus/restore
      (`:46-50`) and stays out of scope, matching R2/R3's note. The list:
      `AgentCreateDialog.tsx` (`:164`/`:198`), `ChartersPage.tsx`/`CharterForm` (`:249`/`:260`, D5),
      `DeleteCharterDialog.tsx` (`:30`/`:42`), `DeleteProjectDialog.tsx` (`:34`/`:51`),
      `ClearInstructionsDialog.tsx` (`:37`/`:48`), `JobForm.tsx` (`:57`/`:138`, D5),
      `SetupModal.tsx` (`:21`/`:50`, D5), `ProjectManagerModal.tsx` (`:73`/`:125`),
      `RunnersPage.tsx`/`RunnerForm` (`:230`/`:241`, D5), `ArchiveConfirmDialog.tsx` (`:29`/`:42`),
      `StartFlowDialog.tsx` (`:31`/`:90`) and `TaskDetailDrawer.tsx` (`:271`/`:318`).
      `StartFlowDialog.tsx:31` folded into the D5-shape list explicitly here: it already carried its
      own `panelRef`/`role="dialog"` before this change (found live during task 2.2, not one of
      design D5's original four), so it only needed `tabIndex={-1}` (done in 2.2) — it did not need
      a new `panelRef`, `useDialogFocus` call or `data-dialog-initial-focus` mark the way the four
      D5 dialogs did. No new hand-built dialog found since R3's 09127ba derivation other than this
      one, already accounted for
- [x] 2.10 Updated `scripts/drive/t_d9_clearing_instructions_postchange.py` leg E: the pre-fix
      walk (Save held focus on open, press 1 escaped to the textarea behind the scrim — F307,
      kept as a reproduction) is replaced with a post-fix assertion that focus lands on Cancel the
      moment the dialog opens (`data-dialog-initial-focus` + D1), then four Tab presses cycle
      `["Clear instructions", "Cancel", "Clear instructions", "Cancel"]`, all `inPanel`. Also
      updated the module docstring's leg-E one-liner and the walk's `print` label to match (five
      presses from Save -> four from Cancel). `py -3.11 -m py_compile` on the file: clean. Not run
      live here — it needs a real Hub/browser and is this change's own group-3/-drive queue item,
      not this static edit
- [x] 2.11 Full vitest suite: **176 files / 1805 tests passed** (`npx vitest run`; the two printed
      "Error: boom" stacks are `ErrorBoundary.test.tsx`'s own intentional throw, not failures).
      `npm run lint`: clean (`eslint . --ext ts,tsx --report-unused-disable-directives
      --max-warnings 0`, zero output). `npm run build` (`tsc && vite build`): succeeded, 2715
      modules transformed. `py -3.11 scripts/refresh_ui_bundle.py`: refreshed
      `hub/hub/static/ui` and wrote `ui-build-stamp.json`. Committed `hub/ui/src` (unchanged by
      this task) with `hub/hub/static/ui` and `ui-build-stamp.json` in one commit, per
      `.claude/rules/hub-ui.md`

## 3. Drive it

- [x] 3.1 On a trial Hub serving the rebuilt bundle, drive leg E of `t_d9_clearing_instructions_postchange.py` in a real browser and record each press's `document.activeElement` —
      done: a fresh throwaway Hub on `:8012` (`~/.agentweave/hub/profiles/drive1002/agentweave.db`,
      a clean profile, not `:8010`/`:8000`), serving bundle `index-Cyk3sQbn.js` (`ui-build-stamp.json`
      `src_commit: 096829c`, the bundle committed at task 2.11). Ran
      `scripts/drive/t_d9_clearing_instructions_postchange.py` against it: **59/59 checks passed**.
      Leg E, in order: Save holds keyboard focus before the dialog opens; Enter on Save opens it;
      focus moves straight into the panel, onto Cancel (`{'tag': 'BUTTON', 'text': 'Cancel',
      'inPanel': True}`) — F307's pre-fix behaviour (press 1 escaping to the textarea) is gone; four
      Tab presses cycle `['Clear instructions', 'Cancel', 'Clear instructions', 'Cancel']`, every one
      `inPanel: True`; Escape closes it and returns focus to Save. Full output recorded in
      `scripts/drive/FINDINGS.md`'s F307 entry.
- [x] 3.2 In the same browser, open and close each of the four D5 dialogs from its trigger with the keyboard alone (Escape to close), and record where focus is on open and after close —
      done: new one-off script `scripts/drive/t_d10_dialog_focus_sweep.py` (not a durable regression
      harness like `t_d9`'s; this task's own evidence), against the same `:8012` throwaway Hub.
      For each of `CharterForm` ("New Charter"), `RunnerForm` ("New Runner"), `JobForm` ("New Job")
      and `SetupModal` ("Hub setup"): focused the trigger button, pressed Enter, read
      `document.activeElement`, pressed Escape, read it again. **21/21 checks passed** — in every
      case focus landed inside the panel (on its `data-dialog-initial-focus` element: the name/path
      input) the instant it opened, and Escape returned focus to the trigger that opened it. One
      probe bug found and fixed along the way: the focus probe borrowed D9's `scrim.firstElementChild`
      panel lookup, which assumes `role="dialog"` sits on a wrapper around the focus-trapped panel
      (true for `ClearInstructionsDialog`); all four D5 dialogs put `role="dialog"` directly on
      `panelRef` itself, so that lookup under-counted "inPanel" until corrected to treat the
      `role="dialog"` element as the panel — a probe defect, not a product one (confirmed by reading
      `ChartersPage.tsx:258-260`, `RunnersPage.tsx:239-241`, `JobForm.tsx:135-138`,
      `SetupModal.tsx:47-50`, all four `ref={panelRef}` ... `role="dialog"` on the same element).
