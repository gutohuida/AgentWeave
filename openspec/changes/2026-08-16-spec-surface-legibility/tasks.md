# Tasks — spec surface legibility

Ordered per `design.md` D1: F2 before F1 (colour needs the right background first), F3/F6 are
independent backend-only work, F4 before F5 (the drawer reuses F4's chips).

## 1. F2 — realign the document's neutral CSS variables with the Hub's theme override

- [x] 1.1 In `hub/hub/spec_render.py`'s `_STYLE`, rename the six neutral custom properties per
      `design.md` D2's table (`--aw-bg`→`--bg`, `--aw-fg`→`--fg`, `--aw-muted`→`--muted`,
      `--aw-rule`→`--border`, `--aw-chip-bg`→`--surface-2`, `--aw-code-bg`→`--surface`) everywhere
      they are defined (`:root`, the `prefers-color-scheme` media query, both `[data-theme]` rules)
      and everywhere they are read (every `var(--aw-...)` reference in the same string). Leave
      `--aw-accent` untouched. Add a one-line note in the module docstring stating the mapping exists
      so the next reader does not have to diff against `SpecFrame.tsx` to discover it.
- [x] 1.2 Add the pinning test (`design.md` D2): every key in `SpecFrame.tsx`'s `HUB_NEUTRALS['light']`
      (equivalently `'dark'` — same key set) has a corresponding custom-property name present in
      `spec_render.py`'s `_STYLE`. Mutation-check: temporarily revert 1.1's rename on one property,
      confirm this test fails, then reapply.
- [x] 1.3 Existing `spec_render.py` tests (`hub/tests/test_spec_render.py` or wherever rendering is
      tested today — locate it, do not assume the filename) still pass unmodified in substance; update
      only literal string assertions that named the old variable names.
- [x] 1.4 If `scripts/uishot.py` is available: capture the `aw-loop10` (or a throwaway document with
      requirements) spec document in both themes, `page.evaluate` the frame's computed
      `background-color`, and assert equality with `HUB_NEUTRALS[mode].bg`. If the harness is
      unavailable, record that plainly and rely on 1.2 alone — do not claim the pixel was checked when
      it was not. **Done, with a wrinkle:** `aw-loop10`'s one existing document was rendered and
      stored *before* this change, so pointing the live Hub UI at it (via a scratch Playwright script,
      not `uishot.py` directly, since checking computed style needs `page.evaluate` inside the iframe,
      which `uishot.py`'s CLI does not expose) initially showed the OLD colours — not because the fix
      is wrong, but because spec documents are rendered once at write time and stored
      (`spec_service.py`'s `render_document()` calls), so editing `spec_render.py` does not retroactively
      re-render what is already on disk. Confirmed by reading `spec_service.py`, not assumed. Rendered
      a fresh throwaway payload with the current code instead (`SpecPayload(title="F2 verification
      doc", ...)` through today's `render_document()`), applied the identical override `<style>`
      `SpecFrame.tsx`'s `themeOverride()` emits, and opened it directly in Chromium: computed
      `body` background is `rgb(250, 250, 250)` in light and `rgb(10, 10, 11)` in dark — exact matches
      for `HUB_NEUTRALS.light.bg` (`#fafafa`) and `HUB_NEUTRALS.dark.bg` (`#0a0a0b`). Screenshots
      confirm visually: no navy. `aw-loop10`'s own document was left untouched — re-rendering it would
      mutate the only preserved project's data, out of scope for this task and not needed to prove the
      renderer change works.

## 2. F1 — colour that carries meaning

- [x] 2.1 Add `--aw-warn` (amber-family literal, in both `:root` light/dark blocks and both
      `[data-theme]` rules) alongside the existing `--aw-accent`, per `design.md` D3. **Done:**
      `#9a6700` light / `#d29922` dark — GitHub Primer's `attention.fg` tokens, chosen for the same
      "already tuned for text-on-background contrast in both modes" reason `--aw-accent`'s existing
      values were.
- [x] 2.2 `.aw-modal` styled by value: `MUST` → `--aw-accent`, bold (already bold via existing
      `.aw-modal { font-weight: 600 }` — add colour only); `SHOULD` → `--aw-warn`; `MAY` → unchanged
      (`--aw-fg`, normal weight). Implemented via a per-value CSS class the renderer emits
      (`_requirements()` in `spec_render.py` already has the modal string in hand) — e.g.
      `aw-modal-must`/`aw-modal-should`/`aw-modal-may` — not inline `style=`, so the mapping lives in
      one place (`_STYLE`) rather than being repeated per requirement. **Done:** `SHALL` (a fourth
      value `spec_payload.py`'s `MODALS` allows, not named in `design.md` D3) is mapped to the same
      "must" tone via `_MODAL_TONE`, since MUST/SHALL are equal obligation in RFC2119 language and an
      unhandled fourth value would have rendered with no colour at all.
- [x] 2.3 `.aw-requirement`'s left border takes the same modal-derived colour as 2.2, via the same
      per-value class on the containing `<div>`.
- [x] 2.4 The `rigor` chip in the document header takes a tone from a small fixed mapping already
      derivable from `RIGOR_META`'s values — state the mapping and cite where those values are
      enumerated (`spec_payload.py` or wherever `rigor` is validated) rather than inventing new ones.
      `phase` chip stays neutral, per `design.md` D3. **Done:** mapping cites `SPEC_RIGORS` in
      `hub/hub/db/models.py` (`"sketch"`, `"contract"`, `"gate"`), per Entry 13's correction that this
      is the value enumeration, not `RIGOR_META` (a different constant — the meta-tag name). `sketch`
      (default, blocks nothing) stays the plain neutral chip; `contract` takes `--aw-warn`, `gate`
      takes `--aw-accent` — same accent-is-strongest ordering as 2.2, since `gate` is the rigor level
      that can block a task's approval.
- [x] 2.5 A test asserting each modal value's requirement renders with its distinct class/colour
      (three fixture requirements, one per modal value, assert three different class names present) —
      this is what "colour is applied" means as a machine check; it does not check the actual hex
      values look good together, which is 6.4-equivalent taste, deferred to section 7. **Done:**
      `test_each_modal_value_renders_with_its_own_distinct_class`,
      `test_shall_takes_the_same_tone_as_must`, and
      `test_the_rigor_chip_takes_a_tone_for_contract_and_gate_but_not_sketch` in
      `hub/tests/test_spec_render.py`. Mutation-checked: reverted `SHOULD`'s tone to `"must"` in
      `_MODAL_TONE`, confirmed `test_each_modal_value_renders_with_its_own_distinct_class` fails
      (only two distinct classes present instead of three), reapplied.

## 3. F3 — a `rejected` coverage state

- [x] 3.1 In `hub/hub/requirement_coverage.py`: add `REJECTED = "rejected"` alongside the existing
      state constants; insert it into `PRECEDENCE` between `VERIFIED` and `IN_PROGRESS`
      (`design.md` D4). Import `REJECTED` from `requirement_evidence` (already imported: `ACCEPTED`,
      `AWAITING`). **Done:** imported directly (no local `REJECTED = "rejected"` restatement — the
      import binds the name into this module's namespace, which is what the "exactly one
      implementation" test walks via `vars(requirement_coverage)`).
- [x] 3.2 In `_state()`: after the existing `accepted`/`awaiting` checks and before the `linked`
      checks, compute `rejected = [item for item in current if item.review_state == REJECTED]` and
      return `REJECTED` if `rejected` is non-empty (accepted/awaiting already returned above this
      point, so this only fires when every current-digest row is rejected). **Done**, exactly as
      specified.
- [x] 3.3 Test: a requirement whose only current-digest evidence is rejected reports `state ==
      "rejected"`, `integration == "not_applicable"` (unchanged, per D4). A second test: the same
      requirement, then a later *accepted* current-digest submission, reports `state == "verified"`
      — proving the earlier rejection does not shadow a subsequent success. Mutation-check: revert
      3.2, confirm the first test fails (falls back to whatever `in_progress`/`not_started`/`unserved`
      the fixture's task linkage produces), then reapply. **Done:**
      `test_rejected_evidence_alone_reports_the_rejected_state` and
      `test_a_later_acceptance_moves_past_an_earlier_rejection` in `hub/tests/test_requirement_coverage.py`.
      Mutation check: reverted 3.2's `if rejected: return REJECTED` branch, the first test failed with
      `AssertionError: assert 'unserved' == 'rejected'` (fell through to `unserved`, since this
      fixture links no task) rather than a pass; reapplied, both tests pass again.
- [x] 3.4 `CoverageReport.totals` and any test enumerating "the seven states" by name updates to eight.
      Grep `hub/tests/` and `hub/hub/` for a hardcoded list of coverage states (e.g. a tuple literal
      matching `PRECEDENCE`) and update every one found — do not rely on finding only the ones this
      task anticipated. **Done:** the only hardcoded enumeration found was
      `test_the_precedence_is_the_one_the_specification_states`'s tuple literal in
      `hub/tests/test_requirement_coverage.py`, updated to eight with `"rejected"` between
      `"verified"` and `"in_progress"`. `CoverageReport.totals` needed no change — it already builds
      its dict from `PRECEDENCE` itself (`dict.fromkeys(PRECEDENCE, 0)`), so it picked up the eighth
      state automatically. The `"unserved"` hit in `hub/hub/api/v1/spec.py` is a different, unrelated
      list (`requirement_links.unserved()`, the identifiers of requirements with no linked task at
      all) — checked, not a coverage-state enumeration, left alone.
- [x] 3.5 Check every caller `requirement_coverage.py`'s docstring names (the document badge, the
      project total, "B4's gate") for a branch keyed on `state == "in_progress"` (or equivalent) that
      the new `rejected` state should now take instead — grep for `IN_PROGRESS` and `"in_progress"`
      across `hub/hub/`. If a gate treats `in_progress` as "not yet ready" in a way `rejected` should
      inherit unchanged, say so explicitly; if it needs its own branch, add one. **Done:** only one
      real caller keys off coverage's `IN_PROGRESS` — `requirement_gate.py`'s `REMEDY` dict. Gave
      `REJECTED` its own branch (`"the evidence recorded for it was reviewed and rejected — record
      evidence that satisfies the current wording"`) rather than falling back to `REMEDY.get(state,
      "it is not verified")`'s generic text, since a rejected requirement has a more specific and more
      actionable remedy than "not verified" — the evidence exists, it was judged, and the judgement is
      why the gate is refusing. Every other `in_progress`/`IN_PROGRESS` hit in `hub/hub/` (grepped
      across the whole tree) is `Task.status`, a same-named but unrelated enum on a different object —
      confirmed by reading each site, not assumed from the string match. Also corrected two comments
      that had gone stale the moment 3.2 landed: `hub/hub/api/v1/tasks.py`'s
      `has_rejected_evidence`/`rejected_evidence_count` block claimed coverage "has no precedence
      level for tried and rejected" and "falls through... to `in_progress` either way" — no longer
      true, so reworded to explain why that per-task signal still earns its place *alongside* the new
      coverage state (it survives a later acceptance that moves coverage on to `verified`; coverage's
      `rejected` does not). Same correction to `test_task_rejected_evidence_signal.py`'s module
      docstring. **Also added this iteration:** the `REMEDY` branch itself had no test exercising it
      end to end through the gate (only `requirement_coverage`'s own unit tests covered `_state()`
      returning `rejected`) — added `test_rejected_evidence_blocks_with_its_own_remedy` to
      `hub/tests/test_requirement_gate.py`, following `test_the_refusal_names_every_blocking_requirement_and_its_reason`'s
      pattern of asserting on the structured `blocking` payload. Mutation-checked: removed the
      `REJECTED` entry from `REMEDY`, the test failed (`assert 'rejected' in 'it is not verified'`),
      reapplied, 26/26 pass in the file.
- [x] 3.6 `hub/ui/src/components/spec/SpecCoverageBar.tsx`: add a `rejected` entry to `STATES`
      (`design.md` D4's tone — a distinct colour from `in_progress`'s neutral grey; `--red` or
      `--amber`, matching the codebase's existing severity vocabulary — check `TaskCard.tsx`'s
      `isBlocked`/`revision_needed` colour choices for precedent rather than picking a new one), with
      a `why` string naming what happened ("Evidence was submitted for the current wording and
      rejected. Nothing currently satisfies this requirement."). **Done:** `--red`, matching
      `OverviewPage.tsx`'s and `TasksBoard.tsx`'s existing precedent that `revision_needed` *and*
      Task's own `rejected` status both already read as `var(--red)` — the closer precedent than
      `TaskCard.tsx`'s `isBlocked`, which is amber for a different meaning (blocked, not rejected).
      Positioned between `verified` and `in_progress` in the `STATES` array, matching `PRECEDENCE`'s
      order. Also added the new type member to `hub/ui/src/api/spec.ts`'s `CoverageEntry['state']`
      union and updated the module comment's stale "seven distinct states" to "eight".
- [x] 3.7 UI test: a coverage entry with `state: 'rejected'` renders the new label and colour, not the
      `in_progress` one, in both the summary bar and the expanded row. **Done:** two tests added to
      `hub/ui/src/__tests__/specCoverage.test.tsx`. Mutation check: removed the `rejected` `STATES`
      entry, both new tests failed (`findByTestId('coverage-count-rejected')` timed out; the expanded
      row rendered the lowercase raw `entry.state` fallback `— rejected` instead of the labelled
      `— Rejected`, so `toHaveTextContent('Rejected')` failed) — reapplied, both pass.

## 4. F6 — a ceiling on requirements per declared task

- [x] 4.1 `hub/hub/spec_completeness.py`: `MAX_REQUIREMENTS_PER_TASK = 3` (module-level constant,
      `design.md` D6), a new finding code `task_too_coarse` appended in the existing per-task loop
      (alongside `task_without_requirement`) when `len(task.requirements) > MAX_REQUIREMENTS_PER_TASK`,
      naming the task key, the count, and the ceiling in the message. **Done**, exactly as specified —
      the branch is `elif`, mutually exclusive with `task_without_requirement` (a task with zero
      requirements cannot also be "too coarse").
- [x] 4.2 Test: a document with one task naming 4 requirements is refused at `propose()` with
      `task_too_coarse`; the same document with that task split into two (2 and 2) proposes cleanly.
      A document with a task naming exactly 3 is not refused (proving the ceiling is inclusive, not
      exclusive, per D6's "at most 3" wording). **Done:**
      `test_a_task_naming_four_requirements_is_too_coarse`,
      `test_a_task_naming_exactly_three_requirements_is_not_refused`,
      `test_the_same_document_split_into_two_and_two_proposes_cleanly` in
      `hub/tests/test_spec_completeness.py`, following the file's own established pattern of testing
      `spec_completeness.check()` directly rather than the full `propose()` API round trip —
      `spec_service.propose()` calls `check()` verbatim with no additional logic between the two, and
      every other finding code in this file (`task_without_requirement`, `non_goals_empty`, etc.) is
      tested the same way, not through the API. Mutation check: disabled the new branch
      (`elif False and len(...)`), reran — the 4-requirement test failed with `StopIteration` (no
      `task_too_coarse` finding produced), the other two still passed as expected since they assert
      absence; reapplied, all 16 tests in the file pass.
- [x] 4.3 `hub/hub/data/charters/spec.md`'s "How to slice the work" section gets a new bullet stating
      the ceiling and why (points at the operator's own finding: one ticket carrying two-thirds of a
      specification on 42 words hid a rejected requirement inside an approved one). No code enforces
      charter text; this is guidance so the `propose()` refusal in 4.1 is the exception, not routine.
      **Done:** new bullet added after the existing "task count is not scope" bullet, naming the
      ceiling, citing the 6-of-9-on-42-words finding, and stating the consequence ("if a task would
      need more than 3, it is several tasks"). No manifest checksum or charter-content test exists to
      update — checked `charters.json` for a hash field, found none.
- [x] 4.4 Add the new finding code to whatever surfaces `spec_completeness` findings to an operator or
      agent (check `hub/hub/api/v1/spec.py`'s propose endpoint and any UI that lists findings) — a
      finding a caller cannot see is a silent refusal. **Checked, nothing to add:** `propose_document`
      (`hub/hub/api/v1/spec.py:890-919`) returns `blocking` as a plain list of `finding.to_dict()`
      dicts with no per-code filtering or allow-list — every code `check()` produces already reaches
      the caller, `task_too_coarse` included. `SpecPhaseBar.tsx` (the only UI consumer of `blocking`,
      confirmed by grep across `hub/ui/src`) renders `finding.code`/`where`/`message` generically in a
      loop with no per-code switch, and `SpecBlockingFinding.code` in `hub/ui/src/api/spec.ts` is typed
      as a bare `string`, not a closed union — no UI code or type needed a change. Confirmed this is
      backend-only, per the phase's own note.

## 5. F4 — requirement chips and cross-tab navigation

- [x] 5.1 `TaskCard.tsx`: a chip row in the card header (not gated behind `expanded`) rendering one
      chip per `task.requirement_ids` entry — identifier text, `title` attribute carrying the
      statement from the matching `requirement_links` entry where present. Empty when
      `requirement_ids` is empty or absent — no placeholder, matching the card's existing pattern for
      other optional fields. **Done:** iterates `task.requirement_ids` (not `requirement_links`
      directly) so a bare identifier with no matching link still renders rather than being silently
      dropped, per the task's own wording ("where present"); looks up the link by identifier for the
      `title`, the resolved document, and the rejected tone.
- [x] 5.2 A chip whose linked requirement has `has_rejected_evidence: true` (already on
      `requirement_links`, per the proposal's F4 note) gets the `rejected` tone from 3.6's colour
      choice — the one place this signal already existed server-side and never reached a screen.
      **Done, with one addition:** `hub/ui/src/api/tasks.ts`'s `RequirementLink` TypeScript interface
      had no `has_rejected_evidence`/`rejected_evidence_count`/`latest_rejection_reason` fields at
      all — the backend (`hub/hub/api/v1/tasks.py:184-189`) has sent them since 3.5, but nothing on
      the frontend read them yet. Added the three fields to the interface as part of this task rather
      than as a separate one, since F4 is the first consumer.
- [x] 5.3 `hub/ui/src/lib/navigation.ts`: add `anchor?: string | null` to the `project`/`tab: 'spec'`
      destination variant (`design.md` D7). `projectDestination()` accepts an optional third-turned-
      fourth argument or an options object — check the existing call sites before choosing the
      signature, since every one needs updating consistently. **Done:** a fourth positional parameter,
      defaulted to `null` — every one of the 9 existing call sites (`App.tsx` ×7, `navigation.ts`
      internal ×3, plus every test file constructing a destination) keeps working unchanged, and the
      returned object omits the `anchor` key entirely when absent (mirroring how `document` is
      already omitted) so no `toEqual` fixture anywhere needed touching. Also carried through
      `serializeDestination`/`parseDestination` (an `anchor` query param, only ever alongside
      `document`) and `isSpecDestination`'s type predicate, for the same reason `document` already
      round-trips through the URL — an anchor is as much "where you are" as the document itself.
- [x] 5.4 `SpecDocumentPanel.tsx`: accept an initial anchor (from the destination, on mount) the same
      way `pendingFragment` is already set from in-frame navigation, so a cross-tab click scrolls to
      the requirement, not just opens the document. **Done, with a case the literal wording didn't
      cover:** a chip click that names the document already open never fires a fresh `toc-ready`
      message (nothing about the document changed), so seeding `pendingFragment` alone from
      `initialAnchor` would never be consumed on that path. Added a second branch, keyed off a
      `(path, anchor)` pair already applied: a *new* anchor for the *same* document scrolls directly
      via the existing `frameRef.current?.scrollToSection()`; a new document keeps working the
      original way, through `pendingFragment` and the `toc-ready` handshake `SpecFrame.tsx` already
      has.
- [x] 5.5 Clicking a chip resolves the requirement's `document_id` to a document path (via the
      existing document list the Spec tab already loads — no new endpoint, per `design.md` D7) and
      navigates with that anchor. **Done:** `TaskCard.tsx` calls `useSpecDocuments()` directly (the
      same hook `SpecPhaseBar.tsx` already uses to resolve a path to its record — confirmed by
      reading that file rather than assuming the `design.md` reference to `SpecDocumentPicker.tsx`
      was exact) and builds an `id → path` map. The anchor passed is the requirement's stored
      `anchor` field with its leading `#` stripped (`spec_render.py`'s `requirement_anchor()` writes
      `#FR-n`; every in-frame fragment — `pendingFragment`, `TocAnchor.id`, `resolveSpecLink`'s
      output — is bare, without the `#`, so this is the format the rest of the fragment machinery
      already expects), falling back to the bare identifier when a link carries no `anchor` at all.
- [x] 5.6 `SpecCoverageBar.tsx`: the existing `N task(s)` text becomes a link/button that switches to
      the Tasks tab with `TasksBoard.tsx` filtered to `linked_task_ids` (new `activeTaskIds` state,
      alongside the existing `activeFilter`, per `design.md` D7 — not a new filtering mechanism).
      **Done, with the state placed in a small Zustand store** (`hub/ui/src/store/taskFilterStore.ts`)
      rather than literally local `useState` in `TasksBoard.tsx`: the click that sets it happens on
      the Spec tab, before `TasksBoard` is even mounted, so nothing in the component tree can hold it
      as local state at the moment it needs to be set. `SpecCoverageBar` takes an optional
      `onOpenTasks` prop (renders the plain, unclickable text when absent, so every existing caller
      and test is unaffected); `App.tsx` wires it to `setActiveTaskIds` + a tab-switch navigation.
      `TasksBoard` shows a dismissible banner naming the count when the store's filter is active,
      applies it in both the kanban columns and the rejected section, alongside — not instead of —
      the existing `activeFilter`.
- [x] 5.7 Tests: a task with requirement links renders the expected number of chips with the expected
      identifiers; clicking one calls the navigation function with the resolved path and anchor
      (mock the resolver, assert the call, matching this codebase's existing pattern of testing
      navigation intent rather than the full route change); a coverage row's task-count link, clicked,
      sets the board filter to the expected task ids. **Done:** `taskRequirementLinks.test.tsx` gained
      a `the requirement chip row (F4)` describe block (chip count/identifiers, rejected tone, click
      resolution via a mocked `useSpecDocuments`, and a disabled chip when resolution fails) and one
      pre-existing test needed `within(...)` added since "FR-1" now also renders as a chip, matching
      the "Serves" block's own text; `specCoverage.test.tsx` gained two tests (task-count is a button
      that calls `onOpenTasks` with the linked ids; renders as plain text with no `onOpenTasks`);
      `urlNavigation.test.ts` gained a describe block for the anchor's carry/drop/round-trip rules;
      a new `tasksBoardFilter.test.tsx` covers the store→board wiring (unfiltered by default, filtered
      with a banner when set, cleared restores everything). Every new assertion mutation-checked:
      stripping the anchor's `#`, disabling the board filter, zeroing `onOpenTasks`'s argument, and
      hard-coding the rejected tone to `false` were each reverted in turn and confirmed to fail the
      test written against it, then reapplied. Full `hub/ui` suite (`npm test -- --run`): 887 passed
      on a clean run — a first run showed 19 file-level timeouts, all resolved on rerun with no code
      changed between the two, consistent with this repo's documented full-suite resource contention
      (`STATE.json` `dead_ends`) rather than anything this phase broke; `npx tsc --noEmit` and
      `npm run lint` both clean of anything new (lint's pre-existing 9 warnings, itemised in
      `decisions_for_user`, are unchanged). Bundle rebuilt (`npm run build` +
      `refresh_ui_bundle.py`). Backend sanity check (no backend file changed by this phase):
      `test_tasks.py`, `test_task_rejected_evidence_signal.py`, `test_task_requirement_ids_readable.py`,
      `test_spec_render.py` — 54 passed.

## 6. F5 — task detail as a drawer

- [ ] 6.1 New `hub/ui/src/components/tasks/TaskDetailDrawer.tsx`, following the dialog-pattern
      precedent (`AgentCreateDialog.tsx`, `DeleteProjectDialog.tsx`): `role="dialog"`, focus trap,
      Escape to close, click-outside (on the board, not a modal backdrop, per `design.md` D8) to
      close. Right-anchored, full height.
- [ ] 6.2 Move everything `TaskCard.tsx`'s current inline expansion renders into the drawer, unchanged
      in behaviour: description, acceptance criteria, deliverables, notes, the transition-move menu,
      the blocking-reason input, the divergence-policy control. `TaskCard.tsx`'s collapsed state keeps
      title, status, assignee, and 5.1's requirement chips; its own expansion state and toggle are
      removed in favour of an explicit "open" action that opens the drawer.
- [ ] 6.3 The drawer additionally renders 5.1/5.2's requirement chips with their full statement text
      (not just the identifier, since there is now room) and, where `has_rejected_evidence` is true,
      the `latest_rejection_reason` already on `requirement_links` — never surfaced anywhere before
      this change.
- [ ] 6.4 Behaviour-parity tests: every control that worked inline (start a transition, set a blocking
      reason, change divergence policy) still works from the drawer, same assertions as whatever
      existing `TaskCard.tsx` tests cover those paths today, relocated rather than rewritten from
      scratch where the existing test already proves the right thing.
- [ ] 6.5 Machine-checkable no-clipping check (`design.md` D8): with a task carrying a long
      description and 3 requirement chips (the F6 ceiling, so this is a realistic worst case, not an
      arbitrary stress value), assert the drawer body's `scrollHeight <= clientHeight` is *not* the
      constraint that matters — the body should scroll, not clip — so the actual assertion is that no
      *fixed-height* ancestor clips it (`overflow: hidden` with a height less than content) — state
      precisely what is asserted, since "does not clip" is ambiguous between "never scrolls" and
      "never cuts off silently"; this change wants the latter.

## 7. Human-only verification

- [ ] 7.1 **F1 — does the document read as colourful/scannable now, or still "texty"?** Taste. Screenshot
      via `scripts/uishot.py` if available (both themes), `Read` it, but do not tick this task on the
      strength of the screenshot existing — only the operator's own read counts.
- [ ] 7.2 **F2 — does the background actually match, to the eye, not just by variable name?** 1.4's
      computed-style check (if run) is strong evidence but the operator's original complaint was a
      felt mismatch, not a value; confirm by looking, in both themes.
- [ ] 7.3 **F5 — does the drawer feel like Jira, or like something else entirely?** Taste, per the
      operator's own comparison. Open a task with a long description and several requirement chips.
- [ ] 7.4 **F4 — does the navigation between board and document actually feel connected now**, or does
      it still feel like two separate screens with a link between them? This is the operator's own
      framing ("the navigation between the two is hard") and is broader than "does the click work,"
      which 5.7 already proves.
- [ ] 7.5 **F3/F6 — drive the flow that motivated them**: reject one piece of evidence, confirm the
      coverage bar reads `rejected` rather than `in_progress`; try to propose a document with an
      over-sized task, confirm the refusal message is one the operator would understand without
      reading this file.

## 8. User test guide

**Setup.** A project with a proposed or approved specification document carrying at least 4
requirements, evidence for at least one rejected, and at least one task linked to more than one
requirement. `aw-loop10` already has this shape — use it read-only (view only, do not submit new
evidence against it) or build an equivalent throwaway.

1. **Open the specification document, in both light and dark mode** (toggle the Hub's theme switch,
   not your OS setting). — *Expect:* the document's background matches the rest of the app in each
   mode. MUST/SHOULD/MAY requirements are visually distinct at a glance, not just by reading the word.
2. **Open the coverage summary** (the bar above the document, or expand it). Find a requirement whose
   evidence was rejected. — *Expect:* it reads as "rejected" (or similar), not "in progress." It is
   visually distinct from a requirement genuinely being worked on.
3. **Open the task board.** Find a task tied to a specification requirement. — *Expect:* the card
   shows which requirement(s) it serves, without expanding it. Click one — *Expect:* you land on that
   requirement in the document, scrolled into view, not just the top of the document.
4. **Open a task with a long description.** — *Expect:* a full-size view (not a cramped in-card
   expansion) with room to read everything, including which requirements it serves.
5. **Try to get a specification document proposed with one task doing too much** (if you are
   authoring one — ask an agent to write a task that claims most of the requirements in one go).
   — *Expect:* the Hub refuses to move the document forward until the task is split, with a message
   that says why.

**Where it would go wrong:** if step 1 still shows a colour that does not match the app, or step 3's
click lands on the document without scrolling to the right place, say so with the theme/browser you
used — those are the two places this change is most likely to be right in the code and wrong on
screen.
