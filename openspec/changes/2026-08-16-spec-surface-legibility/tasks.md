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

- [ ] 3.1 In `hub/hub/requirement_coverage.py`: add `REJECTED = "rejected"` alongside the existing
      state constants; insert it into `PRECEDENCE` between `VERIFIED` and `IN_PROGRESS`
      (`design.md` D4). Import `REJECTED` from `requirement_evidence` (already imported: `ACCEPTED`,
      `AWAITING`).
- [ ] 3.2 In `_state()`: after the existing `accepted`/`awaiting` checks and before the `linked`
      checks, compute `rejected = [item for item in current if item.review_state == REJECTED]` and
      return `REJECTED` if `rejected` is non-empty (accepted/awaiting already returned above this
      point, so this only fires when every current-digest row is rejected).
- [ ] 3.3 Test: a requirement whose only current-digest evidence is rejected reports `state ==
      "rejected"`, `integration == "not_applicable"` (unchanged, per D4). A second test: the same
      requirement, then a later *accepted* current-digest submission, reports `state == "verified"`
      — proving the earlier rejection does not shadow a subsequent success. Mutation-check: revert
      3.2, confirm the first test fails (falls back to whatever `in_progress`/`not_started`/`unserved`
      the fixture's task linkage produces), then reapply.
- [ ] 3.4 `CoverageReport.totals` and any test enumerating "the seven states" by name updates to eight.
      Grep `hub/tests/` and `hub/hub/` for a hardcoded list of coverage states (e.g. a tuple literal
      matching `PRECEDENCE`) and update every one found — do not rely on finding only the ones this
      task anticipated.
- [ ] 3.5 Check every caller `requirement_coverage.py`'s docstring names (the document badge, the
      project total, "B4's gate") for a branch keyed on `state == "in_progress"` (or equivalent) that
      the new `rejected` state should now take instead — grep for `IN_PROGRESS` and `"in_progress"`
      across `hub/hub/`. If a gate treats `in_progress` as "not yet ready" in a way `rejected` should
      inherit unchanged, say so explicitly; if it needs its own branch, add one.
- [ ] 3.6 `hub/ui/src/components/spec/SpecCoverageBar.tsx`: add a `rejected` entry to `STATES`
      (`design.md` D4's tone — a distinct colour from `in_progress`'s neutral grey; `--red` or
      `--amber`, matching the codebase's existing severity vocabulary — check `TaskCard.tsx`'s
      `isBlocked`/`revision_needed` colour choices for precedent rather than picking a new one), with
      a `why` string naming what happened ("Evidence was submitted for the current wording and
      rejected. Nothing currently satisfies this requirement.").
- [ ] 3.7 UI test: a coverage entry with `state: 'rejected'` renders the new label and colour, not the
      `in_progress` one, in both the summary bar and the expanded row.

## 4. F6 — a ceiling on requirements per declared task

- [ ] 4.1 `hub/hub/spec_completeness.py`: `MAX_REQUIREMENTS_PER_TASK = 3` (module-level constant,
      `design.md` D6), a new finding code `task_too_coarse` appended in the existing per-task loop
      (alongside `task_without_requirement`) when `len(task.requirements) > MAX_REQUIREMENTS_PER_TASK`,
      naming the task key, the count, and the ceiling in the message.
- [ ] 4.2 Test: a document with one task naming 4 requirements is refused at `propose()` with
      `task_too_coarse`; the same document with that task split into two (2 and 2) proposes cleanly.
      A document with a task naming exactly 3 is not refused (proving the ceiling is inclusive, not
      exclusive, per D6's "at most 3" wording).
- [ ] 4.3 `hub/hub/data/charters/spec.md`'s "How to slice the work" section gets a new bullet stating
      the ceiling and why (points at the operator's own finding: one ticket carrying two-thirds of a
      specification on 42 words hid a rejected requirement inside an approved one). No code enforces
      charter text; this is guidance so the `propose()` refusal in 4.1 is the exception, not routine.
- [ ] 4.4 Add the new finding code to whatever surfaces `spec_completeness` findings to an operator or
      agent (check `hub/hub/api/v1/spec.py`'s propose endpoint and any UI that lists findings) — a
      finding a caller cannot see is a silent refusal.

## 5. F4 — requirement chips and cross-tab navigation

- [ ] 5.1 `TaskCard.tsx`: a chip row in the card header (not gated behind `expanded`) rendering one
      chip per `task.requirement_ids` entry — identifier text, `title` attribute carrying the
      statement from the matching `requirement_links` entry where present. Empty when
      `requirement_ids` is empty or absent — no placeholder, matching the card's existing pattern for
      other optional fields.
- [ ] 5.2 A chip whose linked requirement has `has_rejected_evidence: true` (already on
      `requirement_links`, per the proposal's F4 note) gets the `rejected` tone from 3.6's colour
      choice — the one place this signal already existed server-side and never reached a screen.
- [ ] 5.3 `hub/ui/src/lib/navigation.ts`: add `anchor?: string | null` to the `project`/`tab: 'spec'`
      destination variant (`design.md` D7). `projectDestination()` accepts an optional third-turned-
      fourth argument or an options object — check the existing call sites before choosing the
      signature, since every one needs updating consistently.
- [ ] 5.4 `SpecDocumentPanel.tsx`: accept an initial anchor (from the destination, on mount) the same
      way `pendingFragment` is already set from in-frame navigation, so a cross-tab click scrolls to
      the requirement, not just opens the document.
- [ ] 5.5 Clicking a chip resolves the requirement's `document_id` to a document path (via the
      existing document list the Spec tab already loads — no new endpoint, per `design.md` D7) and
      navigates with that anchor.
- [ ] 5.6 `SpecCoverageBar.tsx`: the existing `N task(s)` text becomes a link/button that switches to
      the Tasks tab with `TasksBoard.tsx` filtered to `linked_task_ids` (new `activeTaskIds` state,
      alongside the existing `activeFilter`, per `design.md` D7 — not a new filtering mechanism).
- [ ] 5.7 Tests: a task with requirement links renders the expected number of chips with the expected
      identifiers; clicking one calls the navigation function with the resolved path and anchor
      (mock the resolver, assert the call, matching this codebase's existing pattern of testing
      navigation intent rather than the full route change); a coverage row's task-count link, clicked,
      sets the board filter to the expected task ids.

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
