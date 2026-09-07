# Tasks — clearing instructions asks first

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is UI-only.** No Python file is modified, which has two consequences an implementer
must not skip: the committed bundle in `hub/hub/static/ui` has to be rebuilt (§3), and the Python
lint set is not required — say so in the log rather than passing over it in silence (§5.1).

## 1. The dialog

- [ ] 1.1 New `hub/ui/src/components/instructions/ClearInstructionsDialog.tsx`, copying the shape of
  `components/spec/ArchiveConfirmDialog.tsx` — `role="dialog"`, `aria-modal`, `aria-labelledby`, the
  `lifted-surface` panel over `var(--scrim)`, a ghost Cancel and a `destructive` Confirm — and
  reusing `hooks/useDialogFocus.ts` for Escape, focus trapping and focus restoration. Do **not**
  reuse `DeleteProjectDialog`'s type-to-confirm: its own docstring says it exists because no other
  destructive control removes as much at once, and this one does not.
- [ ] 1.2 The dialog states three things, per `design.md` D3: the project it is about, how much
  content would be discarded (a line count taken from `data.content`, the text that was read), and
  that AgentWeave keeps no copy. The third is the fact the operator cannot discover anywhere else —
  it is measured in `proposal.md`, one row upserted in place, no history table.
- [ ] 1.3 Cancel, Escape and a scrim click all do the same nothing: no write, no change to the
  editor's content. Do not restore the old text on Cancel — the operator typed the empty editor.

## 2. The gate

- [ ] 2.1 In `hub/ui/src/components/instructions/InstructionsPage.tsx`, `handleSave` (`:54-56`)
  becomes conditional. Fire the dialog when `data.content.trim() !== '' && content.trim() === ''`;
  otherwise `saveMutation.mutate(content)` exactly as today.
- [ ] 2.2 **Trim both sides, and do not trim what is written** (`design.md` D1). A predicate testing
  `content === ''` misses the commonest near-miss — a select-all-delete that leaves a newline — and
  that write is just as destructive. The confirmed save sends `content` byte-for-byte as typed.
- [ ] 2.3 **Add no state guard for the unloaded case, and do not remove the structural one.** Save is
  rendered only inside `actions={data ? … : undefined}` (`:62`), so `handleSave` is unreachable while
  `data` is undefined — that is F271's own gate (its `tasks.md` 1.4), and it is what makes this
  change's confirmation impossible to reach over a state that was never read. Moving Save into the
  `data` branch of `{children}` preserves the property; moving it outside the gate breaks this change
  and F271 together.
- [ ] 2.4 Leave `hub/hub/api/v1/instructions.py` and `hub/hub/db/models.py` alone. The empty string
  stays a legitimate value on the wire; this change is about the destructive-if-wrong UI action.

## 3. The bundle

- [ ] 3.1 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py` (`make` is not on
  PATH in Git Bash on this machine). Commit `hub/ui/src` and `hub/hub/static/ui` together.
- [ ] 3.2 **Prove the rebuild reached the bundle rather than assuming it.** Grep the dialog's own
  literal string in the served JS and confirm it occurs there and zero times in the bundle committed
  before, with a control string that *does* match in both so a zero is a real absence. Check
  `ui-build-stamp.json`'s `src_commit` moved. `AW_CHECK_UI_BUNDLE=1 pytest
  hub/tests/test_ui_build_stamp.py` must pass. Skipping this makes §4's drive re-measure the old page
  and report success.

## 4. Unit coverage — new file under `hub/ui/src/__tests__/`

Each must fail against the pre-change component. **Mutation-check by reverting the gate, not by
reasoning about it** — the sibling change found two of its eight tests passing before and after, and
only measurement showed which.

- [ ] 4.1 Non-empty stored content, editor emptied, Save clicked → the dialog is present **and no PUT
  is issued**. Assert on the request, not on the dialog's markup: a test that only asserts the dialog
  appears passes against a page that renders it *and* fires the write.
- [ ] 4.2 Cancel → still no PUT, and the textarea still holds what the operator typed.
- [ ] 4.3 Confirm → exactly one PUT carrying the empty string, and the success acknowledgement is
  shown as for any other save.
- [ ] 4.4 Whitespace-only editor over non-empty stored content → the dialog is asked. This is the
  assertion `content === ''` would fail.
- [ ] 4.5 A non-empty save → no dialog, one PUT, unchanged behaviour.
- [ ] 4.6 An empty editor over **already-empty** stored content → no dialog, one PUT. The
  confirmation is about loss, and there is none.
- [ ] 4.7 Successful read, then a failing background refetch, then clear and Save → the dialog is
  still asked, measured against the content that was read. This is the scenario that would fail
  against an implementation deriving its baseline from anything but the last successful `data`, and
  it is the one that ties this change to F271's `data`-first ordering.
- [ ] 4.8 Escape closes the dialog and issues no PUT.

## 5. The drive — this is what closes the change

- [ ] 5.1 A drive harness under `scripts/drive/`, against a real browser and a real Hub. The decisive
  measurements, in this order: (a) with real stored text on screen, select all, delete, click Save —
  assert **zero PUTs on the wire** while the dialog is open, then read the row back over the API and
  assert it is byte-identical; (b) Cancel, read back again, still byte-identical; (c) Confirm, and
  only now does the row become `''`. Read the wire, not the DOM's `disabled` attributes.
- [ ] 5.2 **Run it once against the pre-change bundle**, before the fix, so the instrument is known to
  be able to see the write it is asserting the absence of. The pre-change run must show one PUT and
  the row going to `''` on the first Save click. A drive that has only ever seen the passing state
  has proved nothing.
- [ ] 5.3 Fresh Hub on a spare port started from source from `hub/`, throwaway project, deleted
  afterwards and confirmed absent. Never `proj-5e960453` or `proj-18e5d4e0`; never `:8000`; leave
  `:8010` alone. No agent turn is needed, so nothing binds a model.
- [ ] 5.4 Drive the dialog by keyboard as well as by mouse — Tab cycles within the panel, Escape
  cancels, focus returns to Save afterwards. That is `useDialogFocus`'s contract and no unit test in
  jsdom proves it in a real browser.
- [ ] 5.5 **Do not fold F296 into this harness.** `scripts/drive/t_d4_instructions_failed_load.py:316`
  queries role `button` where the control is a `combobox`, and its `NOT DRIVEN` print beside it is
  now false. It is one word, it is adjacent, and it is a separate unowned item — taking it here would
  misreport what this change cost. Take it as its own commit if the window has room.

## 6. Close it out

- [ ] 6.1 `cd hub/ui && npm run lint` and `tsc --noEmit`. State explicitly that `ruff`/`black`/`mypy`
  were not required because no file they cover is modified — do not skip them silently.
- [ ] 6.2 `openspec-sync-specs` into `openspec/specs/project-instructions/spec.md`, dropping the
  delta's change-relative narration and keeping its durable rationale, then archive. Check whether
  any *other* spec needs syncing and record the answer either way — the sibling change checked
  `project-environment-settings` and correctly concluded it needed no edit.
