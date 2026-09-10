# Tasks — the control that asks holds the keyboard

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is UI-only.** No Python file is modified, which has two consequences an implementer
must not skip: the committed bundle in `hub/hub/static/ui` has to be rebuilt (§5), and the Python
lint set is not required — say so in the log rather than passing over it in silence (§8.1).

**It fixes two findings and must be verified as two.** `F309` is the focus half, `F310` the Escape
half. A run that closes one and reports the change done has closed half a change.

## 1. The hook stands down when something nearer has answered

- [x] 1.1 In `hub/ui/src/hooks/useDialogFocus.ts`, the Escape branch (`:24-28`) returns without
  closing when `event.defaultPrevented` is already true. The Tab branch below it is **not** touched —
  that is `F307`, deliberately out of scope (`proposal.md`).
- [x] 1.2 Keep the `document` binding and the bubble phase. Both are load-bearing: capture would put
  the hook *ahead* of the nested React handlers it is meant to defer to, and a panel binding would
  break Escape on the dialogs where focus never enters the panel (`design.md` D3).
- [x] 1.3 Comment it at the point of the condition with *why* the check is sufficient — that a
  bubble-phase `document` listener is structurally the last to see the key — not merely that it
  exists. The next reader's question is "how can you be sure nothing nearer runs after us".

## 2. The nested owners declare that they handled it

- [x] 2.1 `hub/ui/src/components/tasks/TaskDetailDrawer.tsx:413-415` calls `e.preventDefault()`
  before `setBlockingReason(null)`. This is the line that makes `F310`'s second gesture work, and it
  is the line whose effect has never been observable.

- [x] 2.1a **This task does not work without §4.1, and that is not obvious.** The handler is bound to
  the `<input>` itself, so it runs only when focus is in the input — which is precisely what `F309`
  denies today. An implementer who lands §1.1 and §2.1 and stops will watch leg `C3` still fail and
  have no reason to suspect the focus work is the cause (`design.md` D9). Land §4.1 before
  concluding anything about this task.
- [x] 2.2 **`DirectoryPicker` must hold the keyboard it opened.** R1 and R2 both recorded that this
  file needed no edit because it already calls `preventDefault()` at `:57-62`. R3 measured the
  precondition and it does not hold: that `preventDefault()` sits in a React `onKeyDown` bound to the
  picker's root `div` (`:85-91`), nothing focuses that root, and opening the browser leaves focus on
  the `Browse…` button *outside* it (`ProjectManagerModal.tsx:153`). The handler never runs, so §1.1
  alone leaves the third instance broken (`design.md` D9). Focus the root from `rootRef` in an effect
  when the picker mounts. Keep `role="dialog"` and `tabIndex={-1}` — they are already there and are
  what makes it focusable.

- [x] 2.2a **Return focus to the trigger when the picker closes**, on every path — Escape, a click
  outside (`:32-38`), and choosing a directory. Without this, dismissing the browser unmounts the
  focused element and drops focus on `document.body`, which is the shape of `F307` arriving by a new
  route inside a change that is supposed to be reducing it. Capture the previously-focused element on
  mount and restore it in the same effect's cleanup, exactly as `useDialogFocus.ts:22`/`:41-44`
  already does; do not reach for `document.getElementById`.

- [x] 2.2b **Do not generalise this to the other panels.** "Every panel focuses itself when it opens"
  is `F307` and is excluded (`design.md` D8). §2.2 exists because one scenario in this change's own
  `hub-interaction-feedback` delta — *"A panel opened over another panel dismisses only itself"* —
  has no other surface that could demonstrate it. If it starts to look like the general fix, stop and
  queue it (§8.4).
- [x] 2.3 Leave the five Escape owners that are *not* inside a `useDialogFocus` panel alone
  (`Composer.tsx:242`, `ModelPicker.tsx:109`, `ConversationRow.tsx:183`, `FilesIndexTab.tsx:42`,
  `SpecDocumentBrowser.tsx:92`). Re-run the grep before believing this list: it is the boundary of
  the change, and `F311` exists because a list like it was trusted instead of re-derived.

## 3. The menu stands aside for the action that asks

- [x] 3.1 `RowMenuItem` in `hub/ui/src/components/layout/RowMenu.tsx` gains an optional flag meaning
  *"choosing this opens a control that will take focus"*. Document it in the interface, in the same
  voice as `reason` and `disabled` above it.
- [x] 3.2 `RowMenu` records whether the item last chosen carried the flag, and prevents Radix's
  `onCloseAutoFocus` in that case only. Default behaviour — focus returns to the trigger — is
  unchanged for every item that does not carry it.
- [x] 3.2a **The flagged item's own action runs from `onCloseAutoFocus` too, not from `onSelect`.**
  Not in the proposal. Added by §7.3's drive on 2026-09-10, after §3.2 and §4.1 had both landed and
  the reason input was *still* left on `document.body` — the exact `F309` symptom, against a bundle
  carrying the whole of §3 and §4. Measured in a browser, not reasoned: with the menu open,
  `focus()` on any element outside it is pulled back to the menu container within the same tick,
  and Radix flushes an item's `onSelect` synchronously (`dispatchDiscreteCustomEvent` wraps it in
  `flushSync`), so a control mounted by the selection takes the keyboard while the focus scope is
  still trapping, loses it at once, and is dropped on `document.body` when the menu unmounts.
  Standing aside on close is necessary and was not sufficient: the action has to run where the trap
  is already gone. The risk this creates — a deferred action that never fires — is guarded by
  `taskDetailDrawer.test.tsx:162`, which fails by name when the deferred call is removed
  (mutation-checked 2026-09-10).
- [x] 3.3 **Clear the record on every close, however the menu closed.** Selection, Escape and a click
  outside all reach `onCloseAutoFocus`, which is where the reset belongs; a flag left set would make
  the *next* dismissal drop focus on `document.body`.
- [x] 3.4 In `TaskDetailDrawer.tsx:285-311`, only the `blocked` item carries the flag. Every other
  move fires a mutation and leaves nothing on screen to hold focus, so it must keep returning focus
  to the trigger (`design.md` D4).
- [x] 3.5 Do **not** add an `onCloseAutoFocus` passthrough prop to `RowMenu`, and do not set
  `modal={false}`. Both were considered and rejected with reasons (`design.md` D4, D7); the inert
  page disappears when the focus defect does.

## 4. The reason panel takes focus itself

- [x] 4.1 **Remove `autoFocus`** from the blocking-reason input (`TaskDetailDrawer.tsx:410`) and
  focus it from a ref instead, when the panel becomes visible. One mechanism, not two
  (`design.md` D5).
- [x] 4.1a **Measured 2026-09-11 on the keyboard path**: after §4.1's programmatic focus the
  reason input matches `:focus-visible` and draws a ring (`outline auto 1px`,
  `box-shadow none`), read from `getComputedStyle` in `P6`. The engine matches
  `:focus-visible` on a focused text field whatever moved the focus there, so this is not a
  keyboard-versus-pointer discriminator and does not need to be: what §4.1a is exposed to is
  a *programmatic* focus losing the indicator, and that is exactly what is measured.
  **The focus has to be visible on the keyboard path.** `hub-interaction-feedback` already
  ships *"Keyboard focus is visible"* — a focus indicator drawn when focus arrives by keyboard — and
  §4.1 replaces a browser-driven focus with a programmatic one, which is the kind of substitution
  that silently loses `:focus-visible`. Drive it in §7.6, where the whole gesture is keyboard: the
  input shows its focus indicator. Do not "fix" this by forcing a ring on the pointer path; the
  shipped requirement is scoped to keyboard arrival and the pointer path is correct without one.

- [x] 4.2 Key the effect on *whether* a reason is being collected, not on its value — the state holds
  the text, so an effect depending on it would re-focus on every keystroke.
- [x] 4.3 No `setTimeout`, no `requestAnimationFrame`, no delay of any kind. After §3.4 nothing else
  is competing for focus, so a scheduled focus would be a timing guess with no race left to win.

## 5. The bundle

- [x] 5.1 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py` from the repo root
  (`make ui` is equivalent; `make` is not on PATH in Git Bash on this machine).
- [x] 5.2 Commit `hub/ui/src` and `hub/hub/static/ui` **together**, including
  `ui-build-stamp.json` — that is what lets `/health` stop reporting `ui_stale`.

## 6. Unit coverage — what is worth asserting in jsdom, and what is not

- [x] 6.1 `hub/ui/src/__tests__/taskDetailDrawer.test.tsx:117` (*closes on Escape*) must still pass
  **unchanged**. Nothing nearer owns Escape in that gesture, so a change to that test is a signal
  that §1.1 over-reached.
- [x] 6.2 Add a case asserting the hook ignores an Escape whose `defaultPrevented` is already true,
  and answers one whose is not. That is a property of the hook and is honestly testable in jsdom:
  dispatch a `KeyboardEvent` on `document` with the default already prevented and assert `onClose`
  was not called.
- [x] 6.3 **Mutation-check whatever you add** — break §1.1 and watch the new case fail, then restore
  it. A test that passes against both the fixed and the unfixed hook is decoration.
- [x] 6.4 Do **not** write a jsdom test that claims to reproduce `F309` or `F310` end to end. Both
  depend on real focus and real event phases; jsdom's answer would be evidence about jsdom. The
  acceptance evidence is §7.

## 7. The drive — this is what closes the change

- [x] 7.1 A real browser against a throwaway Hub serving **the rebuilt bundle** (§5). Check
  `netstat -ano | grep LISTEN` before choosing a port — `8011`, `8012` and `8013` have all been in
  use by other windows' drives this week — and stop what you start.
- [x] 7.2 **48 passed / 0 failed**, 2026-09-10, against served bundle `index-7rpxplrH.js`.
  `py -3.11 scripts/drive/t_d1_0910_escape_across_the_dialogs.py` — **30 passed / 6 failed**
  today, and the six are `F309` and `F310` asserted the right way round. It must reach **zero
  failed, and no fewer than 36 passed** — a floor, not an equality, because §7.4, §7.5 and §7.6 all
  add legs to these same two files and would otherwise make the stated total unreachable. A
  different six failing is still not this change landing.

- [x] 7.2a **A leg that skips is not a leg that passed.** The harness's `D2` block prints
  `no project-manager trigger reachable — skipped` and calls no `check()` at all
  (`t_d1_0910_escape_across_the_dialogs.py:472-473`), so an environment that hides that trigger
  lowers the count without failing anything. If the total comes in under the floor, read the
  output for a skip before concluding a leg regressed — and §7.4 depends on that same block
  opening, so a skip there means §7.4 was not driven either.

- [x] 7.3 **22 passed / 0 failed**, same bundle. This is the harness that found §3.2a.
  `py -3.11 scripts/drive/t_d1_0910_rowmenu_leaves_the_page_inert.py` — **18 passed /
  1 failed** today. It must reach **zero failed and no fewer than 19 passed**, on the same reading
  as §7.2.

- [x] 7.4 Green, and green for the right reason: the probe now prints
  `focus is inside the browser: True`, the modal survives and the typed path is intact. On
  2026-09-10 this leg's first assertion passed for the *wrong* reason — the browser was unmounted
  along with the modal — which is why the other two assertions are what carry it.
  **Drive the third instance, which no harness covers yet, and drive it from the focus state
  the operator is actually in.** Open the project modal, open the directory browser inside it, and —
  **without clicking anywhere inside the browser** — press Escape: the browser closes and **the modal
  is still open**. The "without clicking inside" is the whole leg, not a detail. R3 measured that the
  picker's Escape handler only fires when focus is already inside its subtree, so a leg that clicks a
  breadcrumb or a folder row first would pass against an unfixed `DirectoryPicker` and prove nothing
  (`design.md` D9). Extend one of the two harnesses rather than starting a third file.

- [x] 7.4a **Assert the leg fails before §2.2 and passes after.** Run it against a bundle with §1.1
  landed and §2.2 *not* landed: the modal must close, i.e. the leg must be red. That is the
  mutation-check for the one task in this change whose necessity two rounds denied, and it is cheap
  because §1.1 and §2.2 are separate files.

- [x] 7.4b Green: focus after Escape is `BUTTON 'Browse within the Hub instead'`, the opener.
  **Then drive the close path.** Escape out of the browser and assert focus is on the
  `Browse…` button, not on `document.body` — §2.2a's evidence, and the leg that would catch the
  picker's fix importing `F307`'s shape.
- [x] 7.5 Green, in `t_d1_0910_rowmenu_leaves_the_page_inert.py`'s `P1`/`P2` pair: an ordinary
  move ends on `task-status-menu-<id>` and the blocked move ends inside the reason panel. Both
  directions are asserted in the same leg, because asserting only one is how a fix for the second
  breaks the first. **Drive the ordinary move too, not just the broken one.** Choose a status move that is not
  `blocked` and assert focus returns to the trigger. §3.2 is the task most able to break something
  that works, and its failure mode is focus on `document.body`, which no assertion about the blocked
  path would notice.
- [x] 7.6 **Green, 2026-09-11, in `P6` — and it is the keyboard, not the mouse.** Enter on the
  focused trigger opens the menu, `ArrowDown` reaches `task-status-menu-<id>-blocked` (found
  by reading `document.activeElement` rather than by counting presses, so the leg does not
  encode the legal-move map's order), `Enter` takes it. The menu closes, the reason input
  **has the keyboard** (`INPUT`, `inReason=True`), the nineteen typed characters land in it,
  `Tab` reaches `task-block-confirm-<id>`, `Enter` confirms, and the Hub's own record reads
  `status='blocked' reason='the staging API key'`. So §3.2a's deferral to `onCloseAutoFocus`
  holds on both paths — which iteration 5 could only infer.
  **Drive the narrowed lifecycle scenario exactly as narrowed.** Open the menu, choose
  **Move to blocked** *with the keyboard* — arrow to the item and press Enter, do not click it —
  then type without touching the mouse and confirm. Assert what the delta now says: the keyboard
  is in the reason input once the menu has closed, the text appears there, and the move completes.
  Do **not** extend this leg backwards into "reached the ticket without a pointer at any point":
  that path runs through `F307` and this change does not deliver it (`design.md` D6). A leg
  asserting it would fail for a reason this change is not responsible for.
  Assert §4.1a in the same leg, while the gesture is already keyboard-only: the input carries a
  visible focus indicator when the keyboard arrives in it.

- [x] 7.7 **59 passed / 0 failed**, and leg E prints `F307 REPRODUCED ... TEXTAREA/'Project
  instructions'` — unchanged, which is the check that §1.1 left the Tab branch alone.
  Re-run `t_d9_clearing_instructions_postchange.py` and the clear-instructions operator legs.
  `ClearInstructionsDialog` uses the same hook; the figure written here on 2026-09-10 was **21/21**
  and is wrong — the harness carries 59 legs, and the escape harness's own docstring says 59. The
  acceptance is zero failed, not a total. Its leg E asserts `F307` is *unchanged*, so it is also the check that §1.1 did not silently
  alter the Tab branch.

- [x] 7.8 **Green, 2026-09-11, in `P7`** — select with the mouse, then type with no click of
  any kind in between: the field holds all 19 characters (`'the staging API key'`),
  `[role=menuitem]` count is `0`, and `document.body`'s computed `pointer-events` is `auto`.
  **Drive the scenario that no task produced evidence for.** The delta's
  *"Typing an answer does not operate the menu that asked for it"* had no leg behind it in any round
  before R3 — §7.2 and §7.3 name floors on harnesses that do not cover it, and §7.6 types without
  asserting anything about the menu. Type a reason **containing spaces** — `the staging API key`, the
  same nineteen characters `F309` measured — and assert three things at the end: the field holds the
  whole string, `document.querySelectorAll('[role=menuitem]').length` is `0`, and `document.body`'s
  computed `pointer-events` is not `none`. The last two are exactly what `F309`'s leg `P5` measured
  going wrong, and `t_d1_0910_rowmenu_leaves_the_page_inert.py` already carries the `PROBE` that
  reads both, so this extends an existing leg rather than building new machinery.

- [x] 7.8a **Honoured.** `P5` was not touched and is not counted: §7.8's evidence is `P7`, a
  separate leg on a separate ticket that reaches the field the way the operator does.
  **`P5` is not this leg and does not become redundant.** `P5` focuses the trigger by hand
  and presses Space, so it passes both before and after this change: it demonstrates the mechanism,
  it does not test the fix. Leave it asserting what it asserts, and do not count it as evidence
  for §7.8.

## 8. Close it out

- [x] 8.1 **Both clean, 2026-09-11**: `npm run lint` (eslint, `--max-warnings 0`) and
  `npx tsc --noEmit` in `hub/ui`. **The Python lint set was not required**, and the reason is
  the same one §0 gives: this change edits no file CI lints. CI runs
  `ruff check src/ hub/ tests/` and `black --check src/ hub/hub/ hub/tests/ tests/`; the only
  Python this change touches is `scripts/drive/`, which neither path list covers. It was run
  anyway — `ruff check src/ hub/ tests/` passes on this tree, and the two `UP032`/long-line
  findings the new legs added to the harness were fixed so the drive directory's standing
  count (271 at `HEAD`) did not grow. One `N806` remains and is deliberate: `FOCUS` matches
  the identical local the leg above it already uses.
- [x] 8.2 **Done 2026-09-11, and it is two findings and four commits, not two.** `F309`'s
  `**Status:**` names `7a0e5bc` (the menu hands the keyboard over — `RowMenu.takesFocus`, action
  deferred to `onCloseAutoFocus`) **and** `beb38d6` (the reason panel takes focus from a ref;
  `autoFocus` gone); `F310`'s names `9ed1d6d` (the hook stands down on `defaultPrevented`) **and**
  `beb38d6` (the input's handler now has a `preventDefault()` to call). A single-sha citation would
  have been wrong in both cases — §2.1a and §4.1a are the tasks that say why, and the ledger now
  says which commit did which half rather than leaving the next reader to `git log -S`. `F307` is
  left open and the classifier confirms it. **`F311` is left untouched, and the classifier does not
  read it as open — it reads `RESOLVED`, and it did so before this change too.** The marker is
  `NOT A DEFECT`, matched on `F311`'s own sentence *"Not a defect in the product"*, which is `F311`
  saying the product is fine while its bookkeeping ratchet is still undone. That is the weak arm
  the script's own header calls untrustworthy, it is pre-existing rather than anything this
  close-out did, and it was **not** quietly repaired here: editing `F311` to satisfy the instrument
  would be writing for the instrument, and repairing the instrument is a sweep with its own verdict
  diff. Recorded for the operator instead.
- [x] 8.3 **Done 2026-09-11.** A dated note inside `F307`, giving the three reasons in the order they
  bind: the operator answered `DAY-1` **no** on 2026-09-10 18:30 (`APPROVALS.md`), the Escape branch
  had a mechanism question and the Tab branch has a design one that is the operator's, and leg E of
  `t_d9_clearing_instructions_postchange.py` still prints `F307 REPRODUCED … TEXTAREA/Project
  instructions` against the served bundle that carries this change — so the note is evidence, not
  assertion.
- [x] 8.4 **Answered honestly, and the answer is no — nothing here wanted a decision, which is not
  the same as nothing being decision-shaped.** Both hazards this task names were checked rather than
  assumed:
  - **The binding did not move.** `useDialogFocus` is still bound to `document`, still in the bubble
    phase, and §1.1's comment now records that the phase is load-bearing (`design.md` D3) — capture
    would put the hook ahead of the owners it defers to. Nothing in the change proposes otherwise.
  - **Where focus lands when a confirm dialog opens was not changed.** The Tab branch is untouched
    and `F307` stands. §2.2 does move focus on one panel opening — `DirectoryPicker`'s root — and
    §2.2b is the task that anticipated this looking like the general fix. It did not: it stayed one
    call site, chosen because that panel is the only surface in this change's own delta that can
    demonstrate *"A panel opened over another panel dismisses only itself"*, and no other panel
    gained a self-focus effect. Re-grepped at close-out.

  **One decision-shaped thing did come out of the drive, and it is queued rather than taken.**
  `F315` (C), filed 2026-09-11 by §7.6's own leg: the *Mark waiting* / *Move to blocked* button
  gives no feedback for the 1.5-3 s its mutation takes, stays enabled, and a second press writes the
  move again. It is deliberately **not** repaired here — every status move in that menu shares the
  gap, so patching this one button would ship the inconsistency rather than the fix. It belongs to a
  change that owns optimistic feedback for task mutations, and it is recorded in `FINDINGS.md` and
  in the night window's notes for the operator, not decided by this change.
