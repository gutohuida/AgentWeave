# Tasks — the control that asks holds the keyboard

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is UI-only.** No Python file is modified, which has two consequences an implementer
must not skip: the committed bundle in `hub/hub/static/ui` has to be rebuilt (§5), and the Python
lint set is not required — say so in the log rather than passing over it in silence (§8.1).

**It fixes two findings and must be verified as two.** `F309` is the focus half, `F310` the Escape
half. A run that closes one and reports the change done has closed half a change.

## 1. The hook stands down when something nearer has answered

- [ ] 1.1 In `hub/ui/src/hooks/useDialogFocus.ts`, the Escape branch (`:24-28`) returns without
  closing when `event.defaultPrevented` is already true. The Tab branch below it is **not** touched —
  that is `F307`, deliberately out of scope (`proposal.md`).
- [ ] 1.2 Keep the `document` binding and the bubble phase. Both are load-bearing: capture would put
  the hook *ahead* of the nested React handlers it is meant to defer to, and a panel binding would
  break Escape on the dialogs where focus never enters the panel (`design.md` D3).
- [ ] 1.3 Comment it at the point of the condition with *why* the check is sufficient — that a
  bubble-phase `document` listener is structurally the last to see the key — not merely that it
  exists. The next reader's question is "how can you be sure nothing nearer runs after us".

## 2. The nested owners declare that they handled it

- [ ] 2.1 `hub/ui/src/components/tasks/TaskDetailDrawer.tsx:413-415` calls `e.preventDefault()`
  before `setBlockingReason(null)`. This is the line that makes `F310`'s second gesture work, and it
  is the line whose effect has never been observable.
- [ ] 2.2 **Change nothing in `DirectoryPicker.tsx`.** It already calls `preventDefault()` at
  `:57-62`, so §1.1 repairs the `ProjectManagerModal` double-dismissal without an edit. Verify this
  by reading, and then verify it by driving (§7.4) — a repair nobody drove is a claim.
- [ ] 2.3 Leave the five Escape owners that are *not* inside a `useDialogFocus` panel alone
  (`Composer.tsx:242`, `ModelPicker.tsx:109`, `ConversationRow.tsx:183`, `FilesIndexTab.tsx:42`,
  `SpecDocumentBrowser.tsx:92`). Re-run the grep before believing this list: it is the boundary of
  the change, and `F311` exists because a list like it was trusted instead of re-derived.

## 3. The menu stands aside for the action that asks

- [ ] 3.1 `RowMenuItem` in `hub/ui/src/components/layout/RowMenu.tsx` gains an optional flag meaning
  *"choosing this opens a control that will take focus"*. Document it in the interface, in the same
  voice as `reason` and `disabled` above it.
- [ ] 3.2 `RowMenu` records whether the item last chosen carried the flag, and prevents Radix's
  `onCloseAutoFocus` in that case only. Default behaviour — focus returns to the trigger — is
  unchanged for every item that does not carry it.
- [ ] 3.3 **Clear the record on every close, however the menu closed.** Selection, Escape and a click
  outside all reach `onCloseAutoFocus`, which is where the reset belongs; a flag left set would make
  the *next* dismissal drop focus on `document.body`.
- [ ] 3.4 In `TaskDetailDrawer.tsx:285-311`, only the `blocked` item carries the flag. Every other
  move fires a mutation and leaves nothing on screen to hold focus, so it must keep returning focus
  to the trigger (`design.md` D4).
- [ ] 3.5 Do **not** add an `onCloseAutoFocus` passthrough prop to `RowMenu`, and do not set
  `modal={false}`. Both were considered and rejected with reasons (`design.md` D4, D7); the inert
  page disappears when the focus defect does.

## 4. The reason panel takes focus itself

- [ ] 4.1 **Remove `autoFocus`** from the blocking-reason input (`TaskDetailDrawer.tsx:410`) and
  focus it from a ref instead, when the panel becomes visible. One mechanism, not two
  (`design.md` D5).
- [ ] 4.2 Key the effect on *whether* a reason is being collected, not on its value — the state holds
  the text, so an effect depending on it would re-focus on every keystroke.
- [ ] 4.3 No `setTimeout`, no `requestAnimationFrame`, no delay of any kind. After §3.4 nothing else
  is competing for focus, so a scheduled focus would be a timing guess with no race left to win.

## 5. The bundle

- [ ] 5.1 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py` from the repo root
  (`make ui` is equivalent; `make` is not on PATH in Git Bash on this machine).
- [ ] 5.2 Commit `hub/ui/src` and `hub/hub/static/ui` **together**, including
  `ui-build-stamp.json` — that is what lets `/health` stop reporting `ui_stale`.

## 6. Unit coverage — what is worth asserting in jsdom, and what is not

- [ ] 6.1 `hub/ui/src/__tests__/taskDetailDrawer.test.tsx:117` (*closes on Escape*) must still pass
  **unchanged**. Nothing nearer owns Escape in that gesture, so a change to that test is a signal
  that §1.1 over-reached.
- [ ] 6.2 Add a case asserting the hook ignores an Escape whose `defaultPrevented` is already true,
  and answers one whose is not. That is a property of the hook and is honestly testable in jsdom:
  dispatch a `KeyboardEvent` on `document` with the default already prevented and assert `onClose`
  was not called.
- [ ] 6.3 **Mutation-check whatever you add** — break §1.1 and watch the new case fail, then restore
  it. A test that passes against both the fixed and the unfixed hook is decoration.
- [ ] 6.4 Do **not** write a jsdom test that claims to reproduce `F309` or `F310` end to end. Both
  depend on real focus and real event phases; jsdom's answer would be evidence about jsdom. The
  acceptance evidence is §7.

## 7. The drive — this is what closes the change

- [ ] 7.1 A real browser against a throwaway Hub serving **the rebuilt bundle** (§5). Check
  `netstat -ano | grep LISTEN` before choosing a port — `8011`, `8012` and `8013` have all been in
  use by other windows' drives this week — and stop what you start.
- [ ] 7.2 `py -3.11 scripts/drive/t_d1_0910_escape_across_the_dialogs.py` — **30 passed / 6 failed**
  today, and the six are `F309` and `F310` asserted the right way round. It must reach **36 passed /
  0 failed**. Anything else, including a different six, is not this change landing.
- [ ] 7.3 `py -3.11 scripts/drive/t_d1_0910_rowmenu_leaves_the_page_inert.py` — **18 passed /
  1 failed** today. It must reach **19 / 0**.
- [ ] 7.4 **Drive the third instance, which no harness covers yet.** Open the project modal, open the
  directory browser inside it, press Escape: the browser closes and **the modal is still open**.
  Extend one of the two harnesses rather than starting a third file. This is the only evidence that
  §2.2's "already correct" reading was right.
- [ ] 7.5 **Drive the ordinary move too, not just the broken one.** Choose a status move that is not
  `blocked` and assert focus returns to the trigger. §3.2 is the task most able to break something
  that works, and its failure mode is focus on `document.body`, which no assertion about the blocked
  path would notice.
- [ ] 7.6 Re-run `t_d9_clearing_instructions_postchange.py` and the clear-instructions operator legs.
  `ClearInstructionsDialog` uses the same hook and was driven 21/21 on 2026-09-10; it must still be
  21/21. Its leg E asserts `F307` is *unchanged*, so it is also the check that §1.1 did not silently
  alter the Tab branch.

## 8. Close it out

- [ ] 8.1 `cd hub/ui && npm run lint`, and `npx tsc --noEmit` if the project offers it. Record in the
  log that the Python lint set was **not** required and why, rather than omitting it.
- [ ] 8.2 Set `**Status:**` on `F309` and `F310` in `scripts/drive/FINDINGS.md` to `fixed <sha>`.
  Leave `F307` open and `F311` open — `F311` is ratcheted, not drained.
- [ ] 8.3 Note in `F307` that this change deliberately did not subsume it, so the next reader of that
  finding does not have to reconstruct why a fix landed in the same hook and left it standing.
- [ ] 8.4 If any task here turns out to want a decision — in particular anything that would move
  `useDialogFocus`'s binding off `document`, or change where focus lands when a confirm dialog opens
  — **stop and queue it**, do not decide it. That is `F307`, and it is the operator's.
