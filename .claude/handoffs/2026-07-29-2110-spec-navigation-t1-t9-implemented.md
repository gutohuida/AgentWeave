# Handoff: Spec Navigation T1-T9 implemented; T10/T11 remain

**Date:** 2026-07-29T21:10:56+01:00 · **Branch:** `master` · **HEAD:** `1f8edc6`
**Agent:** Claude Code (Opus 5)
**Previous handoff:** `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md`
**Status:** chunk complete

## Goal

Make the Hub Spec page navigable so an operator can consult the project specification
without knowing repository paths and without the document being squeezed into
unreadability. Historical changes must stay easy to look up but must not pollute daily
navigation — that user constraint is the reason History is a separate browser rather than
an expanded archive tree.

This session resumed the prior handoff, took the `add-spec-navigation` proposal through its
approval gate, committed the previously uncommitted Change 4/6 archive, and implemented
tasks T1-T9 of the approved spec.

## Current state

Three commits were made this session, all on `master`, none pushed:

- `f7cfc94` — the Change 4/6 archive and its two canonical OpenSpec specs (this work was
  finished in the previous session but had been left uncommitted).
- `3d9f6e8` — the Spec Navigation proposal, approved.
- `1f8edc6` — the implementation of T1-T9.

`spec/changes/add-spec-navigation/spec.html` is `aw-spec-status="approved"`, approved by
`user` on `2026-07-29`, and shows **9 / 11 tasks complete**. T1-T9 are `data-status="done"`
with checked boxes. **T10 and T11 are still `data-status="pending"`** and are the whole of
the remaining work.

What is implemented and working:

- Documents project into a parent-aware library ordered by manifest `order`, then title,
  then path. Unindexed, unfiled, stale, missing, and parent-orphaned entries appear under a
  "Needs attention" heading instead of disappearing. Missing entries render as non-buttons
  so they are visible but cannot be opened.
- Paths under `spec/changes/archive/` are excluded from the library and appear only in a
  separate History browser, grouped by parent roadmap, newest first by the leading ISO date
  in the archive directory name, with unparented archives under "Other changes".
- Ctrl/Cmd+K opens a Radix Dialog document picker. Current readable results rank before an
  "Archived" group; missing results appear in a "Missing" group as disabled buttons. An
  archived change is matched by its change name (the archive directory with the date
  stripped), which is what supplies topic search without a tag taxonomy.
- Selection survives inventory refresh while readable, and otherwise falls back to manifest
  home, then `spec/spec.html`, then the first readable current document. An archive is never
  an automatic fallback, but an archive the user explicitly selected is kept.
- The iframe keeps `sandbox="allow-scripts"` with no `allow-same-origin`. An injected
  version-1 bridge posts `toc-ready`, `navigate`, and `active-section`; the shell validates
  exact source window, channel, version, type, field types, and bounds before changing any
  state. Same-document anchors scroll inside the frame; everything else is resolved by the
  shell and either opens a known readable document or leaves the current document alone and
  shows a dismissible `role="status"` `aria-live="polite"` message.
- The Hub sidebar collapses to a 52 px icon rail while the Spec page is active, driven by an
  explicit `compact` prop from `App.tsx` rather than inferred from page state.
- The workspace measures its own container with ResizeObserver. At >= 1140 px it renders a
  260 px navigation pane, a >= 520 px document region, and a 360 px chat pane. Below that,
  navigation and chat become Radix Dialog drawers with focus trapping, Escape, and explicit
  focus restoration to their trigger.
- Only `chatCollapsed` and `libraryMode` persist, in `localStorage` under
  `aw.spec.presentation.v1`. Corrupt, wrongly typed, and non-object payloads reset to
  defaults, and the writer emits only those two keys.

What is NOT done: no manual browser verification of any kind, and no independent code
review. Both are real tasks in the spec, not optional polish.

## Files touched

All of the following are **committed** in `1f8edc6` unless stated otherwise.

New source files:

- `hub/ui/src/components/spec/specNavigation.ts` — pure inventory projection: `buildInventory`,
  `resolveSelection`, `searchDocuments`, `ARCHIVE_PREFIX`. Finished.
- `hub/ui/src/components/spec/specBridge.ts` — bridge constants, `validateFrameMessage`,
  `resolveSpecLink`, `withSpecBridge`, `postScrollTo`, and the injected in-frame script.
  Finished.
- `hub/ui/src/components/spec/specPreferences.ts` — bounded `localStorage` preferences.
  Finished.
- `hub/ui/src/components/spec/SpecFrame.tsx` — iframe wrapper, message listener, deferred
  fragment scrolling, `withHubTheme` (moved here from SpecPage). Finished.
- `hub/ui/src/components/spec/SpecNavigator.tsx` — library tree, Needs attention, History
  groups, page outline. Finished.
- `hub/ui/src/components/spec/SpecDocumentPicker.tsx` — Ctrl/Cmd+K Radix search dialog.
  Finished.
- `hub/ui/src/components/spec/SpecWorkspace.tsx` — `useWorkspaceMode`, wide/compact layout,
  drawers, and the exported dimension constants. Finished.
- `hub/ui/src/components/spec/SpecChatPane.tsx` — the agent chat extracted verbatim from
  SpecPage. Finished.

Modified source files:

- `hub/ui/src/components/spec/SpecPage.tsx` — rewritten as an orchestrator. Retains
  `buildRepairMessage`, the drift banner, repair triggering, refresh, agent default
  selection, and the one-shot `startNewSession` flag. Finished.
- `hub/ui/src/components/layout/Sidebar.tsx` — added `compact` prop, `SIDEBAR_WIDTH` (220)
  and `SIDEBAR_COMPACT_WIDTH` (52) exports, `data-testid="sidebar"`. Finished.
- `hub/ui/src/components/layout/SidebarItem.tsx` — added `compact` prop; icon-only rendering
  with `aria-label`/`title` and a repositioned badge. Finished.
- `hub/ui/src/App.tsx` — passes `compact={page === 'spec'}` to Sidebar. Finished.

New test files:

- `hub/ui/src/__tests__/specNavigation.test.ts` — 21 tests, projection/search/fallback.
- `hub/ui/src/__tests__/specBridge.test.ts` — 26 tests, validation/link resolution/injection.
- `hub/ui/src/__tests__/specWorkspace.test.tsx` — 16 tests, mode boundary/drawers/preferences.
- `hub/ui/src/__tests__/specNavigationUi.test.tsx` — 17 tests, SpecPage integration.

Modified test file:

- `hub/ui/src/__tests__/specManifestRepair.test.tsx` — imported `within`; the final test
  ("prefers the manifest home over spec/spec.html") no longer asserts
  `getByDisplayValue('spec/agentweave-spec.html')` because the flat `<select>` it probed is
  what this change removes. It now scopes to `spec-document-list` and asserts the library row
  has `aria-current="true"`. Everything else in that file is untouched and still passes.

Spec artifacts:

- `spec/changes/add-spec-navigation/spec.html` — approved (metadata, visible pill, Approval
  section, plus a new `.pill.approved` and `.approval.approved` CSS rule), then T1-T9 marked
  done and the progress block set to `data-done="9"` / "9 / 11 tasks complete".
- `spec/index.json` — this document's `status` changed `draft` -> `approved`. No other entry
  touched.
- `spec/roadmaps/agentweave-reconstruction.html` — R5 "Child spec" row relabelled
  `(draft)` -> `(approved)`. The R5 slice `Status` deliberately remains `planned`.

Uncommitted, and intentionally so:

- `.claude/handoffs/LATEST.md` — modified; will point at this handoff.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` —
  untracked. The previous session's handoff was never committed. `.claude/handoffs/` IS a
  tracked directory (see commit `f6663a9` "Track session handoff notes"), so this file and
  the new one are candidates for a future commit if the user wants the chain in git.

## Key decisions

- **The 1140 px breakpoint measures the Spec workspace container, not the viewport.**
  260 + 520 + 360 = 1140 exactly, and the 52 px Hub rail sits *outside* the measured element
  because it is rendered by `App`, not `SpecPage`. A first draft of the workspace test added
  the rail into that budget, computed 1192 > 1140, and failed; the test was wrong, not the
  spec. Do not "fix" this by shrinking a pane.
- **A zero-width ResizeObserver measurement is ignored rather than treated as narrow.**
  JSDOM reports every width as 0, and a real browser reports 0 before first layout. Acting on
  it would both break every existing SpecPage test and flash the compact drawers on load.
  Rejected: defaulting to compact, and special-casing the test environment.
- **Focus restoration is explicit via Radix's `onCloseAutoFocus`, not Radix's default.**
  Radix restores to whatever was focused when the dialog mounted; that did not fire reliably
  under test, and for Ctrl+K there is no trigger element at all. Drawers restore to a
  `triggerRef`; the picker restores to an element the *page* captures in `searchOriginRef`
  before opening, because the picker has two entry points. Rejected: relying on the default,
  and giving the picker a single fake trigger.
- **`event.origin` is never consulted.** `srcDoc` frames without `allow-same-origin` have an
  opaque origin, so origin is the string "null" and carries no authority. Identity is
  `event.source === iframe.contentWindow`. Rejected: origin matching, and adding
  `allow-same-origin` to make origin meaningful.
- **`resolveSpecLink` rejects any resolved path containing `%` or `..`.** Manifest paths
  never percent-encode, and refusing encoding stops an encoded traversal from slipping past
  the `spec/` prefix check. Order matters: the `spec/` prefix check runs *before* the
  `.html` check, so `../../../etc/passwd` reports `unsafe` rather than `not-html`.
- **Chat state was lifted, not duplicated.** `selectedAgent` and `startNewSession` live in
  `SpecPage` and are passed into `SpecChatPane`, because the manifest-repair button shares
  the same one-shot session flag and the same fallback agent. Rejected: giving the chat pane
  its own copy, which would have silently desynchronised repair from the chat selector.
- **The library derives a display title for documents the manifest does not describe.**
  `spec/changes/foo/spec.html` displays as `foo`, not the repeated basename `spec.html`.
  This also keeps the full path out of the rendered text, which is what lets the existing
  "missing path appears exactly once" assertion in `specManifestRepair.test.tsx` keep passing
  — the path is only in the `title` attribute.
- **One existing assertion was changed rather than preserved.** See Files touched. The
  behavior under test (manifest home beats `spec/spec.html`) is unchanged; only the UI probe
  moved, because FR-1 removes the control it probed.
- **ESLint was left broken.** See Dead ends.

## Constraints and user directives (verbatim)

From this session:

- `"Approve as-is"` — the user's approval decision for
  `spec/changes/add-spec-navigation/spec.html`.
- `"Commit both, then implement"` — commit the Change 4/6 archive and the approved proposal
  as separate commits before implementation.

Carried forward and still binding:

- `"Kimi's session-status service (task 3.10) is intentionally not implemented — do not silently implement it."`
- `"New commits, not amends."`
- `"Zero new runtime dependencies (stdlib only)."`
- `"Never commit .agentweave/*; use template loading not hardcoded template strings; lock task mutations; preserve unrelated dirty work; target Kimi v0.29.x only."`
- `"Live CLI probes must run in isolated scratch directories outside the repo, cleaned up after."`
- Pushing has still not been requested. There are now **three unpushed commits**.

Constraints from the approved spec itself, which bind any continuation:

- The iframe must keep `sandbox="allow-scripts"` and must never gain `allow-same-origin`.
- No backend, database, REST schema, SSE vocabulary, or authored-HTML contract change.
- No new runtime dependency, no topic taxonomy, no application-wide router, no resizable
  splitter.
- Per `aw-spec-apply`: never flip `aw-spec-status` without the user; the only permitted
  `spec.html` edits during implementation are task status, the checkbox, the progress
  counter, or a spec fix the user confirmed.

## Dead ends

- **PowerShell here-string syntax (`@'...'@`) in the Bash tool.** Used it for the first
  commit message; Git Bash took the `@` literally and produced a commit whose subject line
  was `@`. Fixed with `git reset --soft HEAD~1` and `git commit -F <file>`. The Bash tool
  documents this prohibition explicitly. Use `git commit -F` with a written file.
- **`cd hub/ui` inside the Bash tool persists across calls.** A later call using the
  repo-relative path `hub/ui/...` failed with "No such file or directory", and Grep/Read
  paths silently referred to the wrong place. Use absolute paths, or re-`cd` deliberately.
- **`.venv/Scripts/python.exe` is required for pytest.** Bare `python` resolves to
  `C:\Users\huida\AppData\Local\hermes\hermes-agent\venv` which has no pytest. `PYTHONPATH=src`
  is still needed for `agentweave` imports.
- **`agentweave.spec_manifest` has no `reconcile` function.** The real API is
  `discover_spec_files(root) -> (dict, diagnostics)`, `load_manifest(text) -> (manifest, diagnostics)`,
  and `compute_intrinsic_conflicts(manifest, discovered)`. An initial probe importing
  `reconcile` failed with ImportError.
- **`fireEvent.click` does not focus the clicked element in JSDOM**, so any focus-restore
  assertion after it fails. `userEvent.setup()` + `await user.click(...)` does focus.
- **A structural checker that greps the whole HTML for `href="#..."` reports false dangling
  anchors**, because the document's own inline script builds a selector string
  (`'#' + entry.target.id`). Strip `<script>` bodies before validating anchors.
- **The same checker initially asserted every task was `pending`**, which was correct at
  approval time and wrong the moment T1 completed. It now accepts `pending|done` and
  cross-checks the progress counter and checkbox count.
- **`npm run lint` cannot run at all in this repo.** ESLint 9.39.4 requires a flat
  `eslint.config.js` and none exists (nor any `.eslintrc.*`, and git has no record of one).
  This predates this change and was deliberately left alone as out of scope. The CI lint
  step is presumably already failing.
- **A first attempt at the cross-document routing test navigated the wrong direction.** The
  manifest home is the roadmap, so the initially-open document is
  `spec/roadmaps/agentweave-reconstruction.html`; a `../../roadmaps/...` href from there
  resolves outside `spec/` and is correctly rejected as unsafe. The test was fixed to
  navigate roadmap -> change spec. This was a test bug, not an implementation bug.

## Verification

Ran and passed, from `hub/ui/` unless noted:

- `npx vitest run` — **167 passed, 20 files, 0 failed.** (Was 134 in 18 files before this
  session; the 4 new files add 33 tests.)
- `npx tsc --noEmit` — clean, no output.
- `npm run build` (`tsc && vite build`) — succeeded, 497 modules, `dist/assets/index-*.js`
  407.20 kB / 117.21 kB gzip. Emits one pre-existing warning about a duplicate `case` clause
  in `src/lib/eventSummary.ts`, unrelated to this change.
- From the repo root: `PYTHONPATH=src .venv/Scripts/python.exe -m pytest tests/test_spec_manifest.py -q`
  — **40 passed, 1 skipped.**
- Live manifest reconciliation with `discover_spec_files(Path('spec'))` —
  `discovered=4 manifest=4 diagnostics=0 conflicts=0`.
- Structural self-check of `spec.html` (script at
  `C:\Users\huida\AppData\Local\Temp\claude\C--Users-huida-Documents-projects-AgentWeave\b26d86c7-d482-4628-a536-effcab7e3b20\scratchpad\check_spec.py`,
  a scratchpad file that will not survive the session) —
  `requirements=11 acceptance=13 tasks=11 ids=43 hrefs=78`, `PASS`. It checks metadata,
  approval reflected in the visible body, unique ids, no dangling anchors, task attributes,
  requirement coverage by both tasks and acceptance criteria, progress/checkbox consistency,
  no external assets, both theme layers, the anchor interceptor, the manifest entry, and the
  reciprocal roadmap link.
- `git diff --check` — passed.

**Explicitly NOT tested:**

- **No manual browser pass of any kind.** Nothing in this session ran the Hub or opened the
  Spec page in a real browser. Real iframe scrolling, IntersectionObserver active-section
  tracking, the injected in-frame bridge script actually executing, relative-link routing
  end to end, focus traps under real focus, light/dark theme injection, and geometry above
  and below 1140 px are all unverified. JSDOM cannot prove any of them — the approved spec
  says so in its own Coverage limit block. This is task T10.
- **The injected bridge script (`BRIDGE_SCRIPT` in `specBridge.ts`) has never executed.**
  Tests cover the shell side of the contract and assert the script's text contains the
  channel and bounds, but no test parses or runs it. A syntax error in that template literal
  would not be caught by anything currently in the suite.
- **No independent code review** (task T11). The author reviewed their own work only.
- `npm run lint` — could not run; see Dead ends.
- No Hub backend tests, no CLI test suite beyond `tests/test_spec_manifest.py`, and no
  `openspec validate` run this session (there are no active OpenSpec changes).
- Nothing was pushed.

## Git state

- Branch: `master`.
- HEAD: `1f8edc6` ("Make the Hub spec viewer navigable").
- Worktree: nearly clean. `git diff --stat HEAD` shows only
  `.claude/handoffs/LATEST.md | 2 +-`.
- Untracked: `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md`
  and this new handoff file.
- **Unpushed commits (3):** `1f8edc6`, `3d9f6e8`, `f7cfc94`. `origin/master` is at `f6663a9`.
- `.claude/handoffs/` is tracked; `.agents/` is ignored. Continue the chain under
  `.claude/handoffs/`.

## Next steps

1. **Run the Hub and do the T10 manual browser pass.** Start the Hub
   (`cd hub && docker compose up -d`) and the UI dev server (`cd hub/ui && npm run dev`,
   http://localhost:5173), open the Spec page, and check, recording pass/fail for each:
   real iframe scrolling; clicking a relative cross-document link inside a spec document
   (e.g. the R5 "Child spec" link in the roadmap) and confirming the shell switches documents
   rather than blanking the frame; the page outline appearing and its active section
   following scroll; Escape closing the Ctrl+K picker and the compact drawers with focus
   returning to the trigger; light and dark themes; and window widths either side of
   1140 px. Then set T10's `data-status="done"` and check its box in
   `spec/changes/add-spec-navigation/spec.html`, bump the progress block to `data-done="10"`
   and "10 / 11 tasks complete".
2. If the browser pass finds defects, fix them under the existing requirement IDs and add a
   regression test before re-marking T10.
3. **T11 independent review.** No AgentWeave session, `agentweave.yml`, or `.agentweave/`
   exists in this repo, so there is no reviewer agent to delegate to and `data-agent` is
   empty on every task. Either ask the user to review, or run `/code-review` on the branch.
   Scope per the task: iframe isolation, bridge bounds, path handling, text-only rendering of
   document-provided labels, focus behavior, responsive minimums, persistence exclusions, and
   Spec-page regressions.
4. Decide with the user whether to `git push` the three unpushed commits, and whether to
   commit the two handoff files under `.claude/handoffs/`.
5. Once T10 and T11 are both done, run `/aw-spec-archive`-equivalent steps for this change.
   Note that `/aw-spec-archive` is **not** installed in this repo — the `aw-spec-*` skills are
   templates this repo *ships* at `src/agentweave/templates/skills/`. Read
   `src/agentweave/templates/skills/aw-spec-archive.md` and follow it manually, as was done
   for `aw-spec-apply.md` this session.

## Open questions for the user

- Should the three unpushed commits be pushed to `origin/master`?
- Should `.claude/handoffs/*.md` be committed (the directory is tracked but the last two
  handoff files are not), or gitignored as session notes?
- Should the missing `eslint.config.js` be added? `npm run lint` currently fails for the
  whole repo, independent of this change.

## Read on resume

- `spec/changes/add-spec-navigation/spec.html` — the approved, authoritative spec; sections
  9 (Evidence and Coverage Limits) and 12 (Tasks) define exactly what T10 and T11 require.
- `hub/ui/src/components/spec/specBridge.ts` — the security-sensitive surface and the
  never-executed injected script; the main target of T11 review and of the T10 browser pass.
- `hub/ui/src/components/spec/SpecWorkspace.tsx` — the 1140 px logic and drawer focus
  handling, the part JSDOM proves least.
- `hub/ui/src/components/spec/SpecPage.tsx` — the orchestrator, to see how the pieces are
  wired and what FR-11 behavior must keep working.
- `src/agentweave/templates/skills/aw-spec-apply.md` — the procedure being followed;
  `aw-spec-archive.md` beside it is what step 5 needs.
- `.claude/handoffs/2026-07-29-1803-change4-6-archived-spec-navigation-proposed.md` — the
  previous handoff; the Change 4/6 archive it describes is now committed as `f7cfc94`, so
  read it only for the product rationale behind the proposal.
