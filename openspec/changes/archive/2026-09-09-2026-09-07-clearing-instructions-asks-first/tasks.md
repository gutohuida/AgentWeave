# Tasks — clearing instructions asks first

Implementation is a night window's. Nothing here is complete on the strength of this plan existing;
only verified implementation closes a task.

**This change is UI-only.** No Python file is modified, which has two consequences an implementer
must not skip: the committed bundle in `hub/hub/static/ui` has to be rebuilt (§3), and the Python
lint set is not required — say so in the log rather than passing over it in silence (§5.1).

## 1. The dialog

- [x] 1.1 New `hub/ui/src/components/instructions/ClearInstructionsDialog.tsx`, copying the shape of
  `components/spec/ArchiveConfirmDialog.tsx` — `role="dialog"`, `aria-modal`, `aria-labelledby`, the
  `lifted-surface` panel over `var(--scrim)`, a ghost Cancel and a `destructive` Confirm — and
  reusing `hooks/useDialogFocus.ts` for Escape, focus trapping and focus restoration. Do **not**
  reuse `DeleteProjectDialog`'s type-to-confirm: its own docstring says it exists because no other
  destructive control removes as much at once, and this one does not.
- [x] 1.2 The dialog states three things, per `design.md` D3: the project it is about, how much
  content would be discarded (a line count taken from `data.content`, the text that was read), and
  that AgentWeave keeps no copy. The third is the fact the operator cannot discover anywhere else —
  it is measured in `proposal.md`, one row upserted in place, no history table.
- [x] 1.3 Cancel, Escape and a scrim click all do the same nothing: no write, no change to the
  editor's content. Do not restore the old text on Cancel — the operator typed the empty editor.
- [x] 1.4 **Mount it inside the `data` branch of `{children}`** (`InstructionsPage.tsx:71`), or wrap
  the component's return in a fragment. Named by the third review because no task said where the
  dialog goes: `InstructionsPage` returns a single `<SettingsSection>`, Save lives in the `actions`
  prop (`:62-69`) which renders in the section's heading, and `{children}` (`:71-152`) is a sibling
  of it — so the dialog cannot simply go "next to Save", and 2.3 forbids moving Save. This also
  decides `useDialogFocus`'s focus restoration, which returns focus to a control in the other
  subtree.

## 2. The gate

- [x] 2.1 In `hub/ui/src/components/instructions/InstructionsPage.tsx`, `handleSave` (`:54-56`)
  becomes conditional. Fire the dialog when `data.content.trim() !== '' && content.trim() === ''`;
  otherwise `saveMutation.mutate(content)` exactly as today.
- [x] 2.2 **Trim both sides, and do not trim what is written** (`design.md` D1). A predicate testing
  `content === ''` misses the commonest near-miss — a select-all-delete that leaves a newline — and
  that write is just as destructive. The confirmed save sends `content` byte-for-byte as typed.
- [x] 2.3 **Add no state guard for the unloaded case, and do not remove the structural one.** Save is
  rendered only inside `actions={data ? … : undefined}` (`:62`), so `handleSave` is unreachable while
  `data` is undefined — that is F271's own gate (its `tasks.md` 1.4), and it is what makes this
  change's confirmation impossible to reach over a state that was never read. Moving Save into the
  `data` branch of `{children}` preserves the property; moving it outside the gate breaks this change
  and F271 together.
- [x] 2.4 Leave `hub/hub/api/v1/instructions.py` and `hub/hub/db/models.py` alone. The empty string
  stays a legitimate value on the wire; this change is about the destructive-if-wrong UI action.

## 3. The bundle

- [x] 3.1 `cd hub/ui && npm run build`, then `python scripts/refresh_ui_bundle.py` (`make` is not on
  PATH in Git Bash on this machine). Commit `hub/ui/src` and `hub/hub/static/ui` together.
- [x] 3.2 **Prove the rebuild reached the bundle rather than assuming it.** Grep the dialog's own
  literal string in the served JS and confirm it occurs there and zero times in the bundle committed
  before, with a control string that *does* match in both so a zero is a real absence. Check
  `ui-build-stamp.json`'s `src_commit` moved. `AW_CHECK_UI_BUNDLE=1 pytest
  hub/tests/test_ui_build_stamp.py` must pass. Skipping this makes §4's drive re-measure the old page
  and report success.

## 4. Unit coverage — new file under `hub/ui/src/__tests__/`

Each must fail against the pre-change component. **Mutation-check by reverting the gate, not by
reasoning about it** — the sibling change found two of its eight tests passing before and after, and
only measurement showed which.

- [x] 4.1 Non-empty stored content, editor emptied, Save clicked → the dialog is present **and no PUT
  is issued**. Assert on the request, not on the dialog's markup: a test that only asserts the dialog
  appears passes against a page that renders it *and* fires the write.
- [x] 4.2 Cancel → still no PUT, and the textarea still holds what the operator typed.
- [x] 4.3 Confirm → exactly one PUT carrying the empty string, and the success acknowledgement is
  shown as for any other save. **The acknowledgement is a 2000 ms flash** (`InstructionsPage.tsx:46-52`)
  — measured by round 3's drive, present at 0.7 s and gone by 3.3 s. Assert inside that window, in
  jsdom and in the browser alike; an observer that arrives late reports a correct page as broken,
  which is exactly what happened on the drive harness's first run.
- [x] 4.4 Whitespace-only editor over non-empty stored content → the dialog is asked. This is the
  assertion `content === ''` would fail.
- [x] 4.5 A non-empty save → no dialog, one PUT, unchanged behaviour.
- [x] 4.6 An empty editor over **already-empty** stored content → no dialog, one PUT. The
  confirmation is about loss, and there is none. Assert the same for stored content that is **only
  whitespace**: the predicate trims the stored side too, and until R2 that half lived only in prose —
  it is now a clause in *A save that blanks nothing is not interrupted* and needs a test that would
  fail against a predicate testing `data.content !== ''`.
- [x] 4.7 Successful read, then a failing background refetch, then clear and Save → the dialog is
  still asked, measured against the content that was read. This is the scenario that would fail
  against an implementation deriving its baseline from anything but the last successful `data`, and
  it is the one that ties this change to F271's `data`-first ordering.
- [x] 4.8 Escape closes the dialog and issues no PUT.

## 5. The drive — this is what closes the change

- [x] 5.1 A drive harness under `scripts/drive/`, against a real browser and a real Hub. The decisive
  measurements, in this order: (a) with real stored text on screen, select all, delete, click Save —
  assert **zero PUTs on the wire** while the dialog is open, then read the row back over the API and
  assert it is byte-identical; (b) Cancel, read back again, still byte-identical; (c) Confirm, and
  only now does the row become `''`. Read the wire, not the DOM's `disabled` attributes.

  **Done 2026-09-10** — `scripts/drive/t_d9_clearing_instructions_postchange.py`, Chromium via
  Playwright, **59 passed / 0 failed**. All three measurements held in order: (a) the dialog on
  screen, `0` PUTs counted on the wire, the row read back over the API byte-identical at 1606 chars;
  (b) after Cancel still `0` PUTs and still byte-identical, with the editor left holding the
  emptiness as typed; (c) after Confirm **exactly one** PUT carrying `{"content": ""}` and the row
  finally `''`. Every count comes from a `page.route` interceptor on `**/project/instructions`, and
  no assertion in the file reads a `disabled` attribute. Leg 0 refuses to trust the run unless the
  JS asset the Hub is actually serving contains the dialog's own words, so a stale bundle cannot
  produce a green run.
- [x] 5.2 **Run it once against the pre-change bundle**, before the fix, so the instrument is known to
  be able to see the write it is asserting the absence of. The pre-change run must show one PUT and
  the row going to `''` on the first Save click. A drive that has only ever seen the passing state
  has proved nothing.

  **Done in advance by round 3, 2026-09-07** —
  `scripts/drive/t_d8_clearing_instructions_prechange.py`, 27 passed / 0 failed against bundle
  `eb1d1d7` on a throwaway `:8011` Hub. One PUT carrying `{"content": ""}`, zero dialogs, the row
  `''`, no undo anywhere on the page and `/instructions/history` 404. Its legs D, E and F pin the
  three cases the change must **not** interrupt or must interrupt for the trim's sake. This is the
  only task in this file closed before implementation, and it is closed because it is a measurement
  of the *pre-change* product: it is the one thing that stops being observable once §2 lands. §5.1's
  post-change harness is still owed and is not this file.
- [x] 5.3 Fresh Hub on a spare port started from source from `hub/`, throwaway project, deleted
  afterwards and confirmed absent. Never the repo's own registered project — that is
  `proj-d85a82bf4216` today; never `:8000`; leave `:8010` alone. No agent turn is needed, so nothing
  binds a model. *Corrected editorially 2026-09-08:* this task named `proj-5e960453` and
  `proj-18e5d4e0`, **both deleted in the 2026-09-07 clean slate**, so it forbade two IDs that no
  longer exist and did not name the one that now must be left alone. The sister change
  `2026-09-05-the-conversation-carries-its-own-run-facts` had the identical literal repaired at its
  task 0.1 by the second review; this occurrence was missed.

  **Done 2026-09-10** — a **new** Hub on `:8012`, `py -3.11 -m uvicorn hub.main:app` run with cwd
  `hub/` (never `agentweave --port`, whose bundled migrations lag this checkout), its own fresh
  database at `%TEMP%/aw-d9-drive/aw.db` migrated from empty to head `0102` at startup. `:8011` was
  left as it was and `:8010` untouched; `GET /` on `:8012` was checked to name `index-BvtjVm7p.js`
  rather than assumed. Fixture `proj-1ce9f451cb6e` (`d9-clearing`), **deleted at the end and
  confirmed absent** — `DELETE` returned `204` and `GET /projects` then returned `count 0`, so the
  instance holds no project at all. Not `proj-d85a82bf4216`; the harness carries that id in a
  `PROTECTED` set and refuses it by name. No agent turn was triggered, so nothing bound a model. Naming the class rather than the
  literal is what survives the next profile rebuild.
- [x] 5.4 Drive the dialog by keyboard as well as by mouse — Tab cycles within the panel, Escape
  cancels, focus returns to Save afterwards. That is `useDialogFocus`'s contract and no unit test in
  jsdom proves it in a real browser.

  **Driven 2026-09-10, and two of the three clauses hold. The Tab clause does not.** Leg E: Save
  focused by keyboard, `Enter` opens the same dialog a click does and writes nothing; `Escape`
  cancels with `0` PUTs and the row byte-identical; and **focus returns to Save**, read off
  `document.activeElement` — the one clause section 4 could not have proved and the reason this task
  exists.

  Tab is where the contract as written is wrong. Five presses, measured: press 1 lands on the
  instructions **textarea behind the scrim** (`inPanel: false`), presses 2-5 then cycle Cancel ↔
  "Clear instructions" correctly. The cycle is closed *once focus is inside*; `useDialogFocus` never
  moves it there on open and only traps at the panel's edges, so the first press follows native DOM
  order out. **Filed as F307 (B) and deliberately not fixed here:** the hook serves six dialogs and
  the two affected are exactly the confirm-only ones — `ArchiveConfirmDialog`, which shipped with
  this behaviour long before, and this dialog, which was shaped after it and inherited it by
  construction. Which control takes focus on open changes all six and is a design question for the
  round discipline, not a repair this window may make. The harness keeps **both** halves as
  assertions — the closed cycle and the escape — so it exits 0 meaning "this change's contract holds
  and F307 is unchanged", and a fix to F307 will fail it loudly.
- [x] 5.5 **Do not fold F296 into this harness.** `scripts/drive/t_d4_instructions_failed_load.py:316`
  queries role `button` where the control is a `combobox`, and its `NOT DRIVEN` print beside it is
  now false. It is one word, it is adjacent, and it is a separate unowned item — taking it here would
  misreport what this change cost. Take it as its own commit if the window has room.

  **Honoured 2026-09-10.** `t_d4_instructions_failed_load.py` was not opened and not touched; F296
  is still open and still its own item. The one finding this drive did file, F307, is a *result* of
  driving 5.4 rather than an unrelated repair folded in, and it is filed rather than fixed.

## 6. Close it out

- [x] 6.1 `cd hub/ui && npm run lint` and `tsc --noEmit`. State explicitly that `ruff`/`black`/`mypy`
  were not required because no file they cover is modified — do not skip them silently.

  **Done 2026-09-10.** `npm run lint` clean and `npx tsc --noEmit` **exit 0**, both run from an
  absolute `hub/ui` with `pwd` echoed in the same call, because the shell's working directory
  survives between calls and §4 lost a measurement to exactly that.

  `ruff`/`black`/`mypy` were **not required, and that is measured rather than assumed.** Across the
  whole change (`git diff --name-only e6da0a0..HEAD`) exactly **one** `.py` file is touched —
  `scripts/drive/t_d9_clearing_instructions_postchange.py`, §5's drive harness. `ruff` passes on it
  and CI's exact `ruff check src/ hub/ tests/` passes. `black` **would** reformat it and deliberately
  is not run over it: CI's black paths are `src/ hub/hub/ hub/tests/ tests/` and `scripts/` is in no
  path list, and the sibling `t_d8_clearing_instructions_prechange.py` is equally unformatted, so
  reformatting one would diverge inside the directory. CI-exact `black --check --target-version py311`
  over its four paths: **558 files unchanged**. `mypy src/` covers no file this change touches — no
  `src/` file is modified.
- [x] 6.2 `openspec-sync-specs` into `openspec/specs/project-instructions/spec.md`, then archive.
  **The delta carries two MODIFIED requirements, not one** — *Hub UI provides instructions editor*
  and *Save cannot write instructions that were never read*, the second added by round 3. Both
  scenarios gain the **same sentence, word for word**; a sync that lands one and not the other
  reinstates precisely the contradiction the second entry exists to remove, and the shipped file
  would then hold one conditioned and one unconditioned statement of the same rule.

  Drop the change-relative narration and keep the durable rationale. Concretely, three paragraphs are
  narration about *this* change and do not belong in a current-behaviour spec: *"The save scenario
  gains a second condition in this change"*, *"The condition names whitespace explicitly…"* (keep its
  **conclusion** — that the two requirements must use identical words — and drop the account of how
  the round found it), and *"Only the last scenario changes in this change…"*. And restore the
  sentence the delta reworded: the shipped file says the two requirements are *"below"*, which is
  true in the shipped file and locally checkable; the delta names
  `2026-09-06-an-unread-editor-cannot-overwrite` because in a delta they are not below. Sync back to
  *"below"*.

  **Archive through the `openspec-archive-change` skill, or with `--skip-specs`.** Round 3 checked
  this step for the failure mode the change itself is about, and found one. `openspec-sync-specs` is
  **agent-driven** — its own SKILL.md says so — so the hand-merge above is unguarded prose, and the
  bare CLI `openspec archive <name>` separately advertises "archive a completed change **and update
  main specs**" with a `--skip-specs` opt-out. Running the bare command after hand-syncing therefore
  puts a mechanical spec update on top of a hand-merged file whose whole value is the judgement in
  it: the narration dropped, the "below" restored, both MODIFIED entries reconciled. Whether it
  overwrites, double-applies or no-ops is **unverified** — measuring it would have meant archiving a
  live change. The skill path asks first (it treats "already synced" as its own case), which is the
  point. The exposure is bounded in the way the instructions row's is not: `openspec/specs/` is
  git-tracked and the archived delta is kept, so this is recoverable and the change's subject is not.

  Check whether any *other* spec needs syncing and record the answer either way. **Already
  measured, twice, independently:** `project-environment-settings` needs no edit — rounds 1 and 3
  both derived that, round 3 without carrying round 1's answer forward — and neither does any other
  spec mentioning instructions, all of which concern charter context rather than the editor.

  **Done 2026-09-10.** Hand-merged, by a script whose every replacement asserts it matched exactly
  once, so a silent no-op could not pass for a sync. All three blocks landed:

  - The **ADDED** requirement is placed immediately **above** *Save cannot write instructions that
    were never read*, not at the end of the file, because its own prose says "which the requirement
    below already states" — placed last, that sentence would be false in the shipped file. Its other
    delta-relative phrase, "The requirement above states this in its own words", is now "The
    statement above says this…": in the delta nothing sits above it, so the phrase could only have
    meant its own SHALL line, and with a neighbour above it in the shipped file the old wording would
    have read as a claim about that neighbour, which does not mention whitespace.
  - Both **MODIFIED** scenarios gained the condition, and this was checked the way the task demands
    rather than by eye. A literal grep would have found one and missed the other — the two wrap
    differently, one long line and one across three — so the check normalises whitespace first.
    **Shipped file: 2 hits. Delta: 2 hits.** Equal counts is the assertion.
  - Narration dropped and rationale kept, as instructed: `"in this change"` now occurs **0** times in
    the shipped spec. *"The save scenario gains a second condition in this change"* became a
    statement of what the condition is; *"The condition names whitespace explicitly…"* kept its
    conclusion — identical words, because a requirement is read on its own — and lost the account of
    how the round found it; *"Only the last scenario changes in this change…"* became a statement
    about what the last scenario is.
  - The reworded sentence is **restored to "below"**: the shipped file says *"stated by the two
    requirements below"*, and the delta's `2026-09-06-an-unread-editor-cannot-overwrite` reference
    does **not** appear in the synced spec.

  `openspec validate project-instructions --type spec --strict` → **valid**. Each ADDED requirement's
  `SHALL` is on its first physical line, which is all `--strict` reads.

  **Other specs: none need syncing, measured a third time.** Ten specs under `openspec/specs/` mention
  instructions; grepping the six non-`project-instructions` hits for the editor surface
  (`Instructions screen`, `instructions editor`, `instructions textarea`) returns **nothing** — every
  one is charter context (`agent-charter`, `agent-context-onboarding`, `agent-tool-surface`).
  `project-environment-settings` does not mention instructions at all.

  **Archived with `--skip-specs`**, per this task's own warning: the specs were already hand-merged,
  and the bare command advertises "archive a completed change **and update main specs**", which would
  put a mechanical update on top of a file whose whole value is the judgement in it. Validation still
  ran — `--skip-specs` and `--no-validate` are separate flags.

  **This change closes zero findings, and that is the honest outcome.** The proposal names F271, F296
  and F307. F271 was fixed and archived by `2026-09-06-an-unread-editor-cannot-overwrite` and is named
  here as the dependency this change builds on (`proposal.md:78`: "It is not a second attempt at
  F271"). F296 is the separate unowned item task 5.5 forbade folding in, and 5.5 was honoured, so it
  is still open. F307 was **filed by** §5's drive, is pre-existing in `useDialogFocus`, and is not
  caused by this change. No `fixed <sha>` Status line was written for any of the three.
