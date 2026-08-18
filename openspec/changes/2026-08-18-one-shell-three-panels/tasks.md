# Tasks — one shell, three panels

Nothing in this file has been started. Every box below is unchecked because this change is a spec
only — CLAUDE.md: "Never mark a task complete on the strength of a plan existing."

## 1. The `"assigned"` query fix (`hub/hub/api/v1/jobs.py`)

Sequenced first because it is independent of everything else here, already fully specified (design
D6), and is the one piece of this change with zero UI dependency.

- [ ] 1.1 `_batch_loop_summaries`'s `current_task` candidates query: add `"assigned"` to the
      `Task.status.in_(...)` clause.
- [ ] 1.2 Test: a task claimed via `status="assigned"` (constructed directly, since
      `2026-08-18-a-loop-writes-its-own-queue` may not yet be implemented when this task runs) appears
      as `current_task` in `_batch_loop_summaries`'s output. Existing tests for `in_progress`/
      `blocked`/`pending` candidates continue to pass unchanged.
- [ ] 1.3 Mutation-check: revert the clause, confirm the new test in 1.2 fails by name.

## 2. Panel shell — layout and registry (`hub/ui/src/components/agents/ConversationView.tsx`)

- [ ] 2.1 New `PanelShell` component (or equivalent) replacing the spec-specific hosting block
      (`:150-291`): owns the tab strip, the plus affordance, and the resize/`Drawer`-overlay logic,
      parameterized by whichever panel is active rather than hardcoded to the spec panel (design D1).
- [ ] 2.2 New descriptor array — `spec`, `loop`, `files` — each with `id`, `title`, `icon`,
      `singleton: true` (design D2). A separate, code-level lookup maps each `id` to its content
      component; the descriptor array itself holds no component references.
- [ ] 2.3 `ConversationView`'s destination props gain `activePanel: 'spec' | 'loop' | 'files' | null`
      and `panelOpen: boolean`, owned by the same caller that owns `document`/`onOpenDocument` today
      (design D5). `document` keeps its existing meaning, now scoped to "which document the `spec`
      panel shows" rather than "whether any panel is open."
- [ ] 2.4 `shellMinWidth` is computed from whichever panel is active, generalizing
      `DOCUMENT_COLUMN_BREAKPOINT`'s existing derived-not-written pattern; `files` and `loop` need
      their own measured minimum widths (design's proposal notes none exist yet — measure against the
      loop and file panel's actual built content before hardcoding a number, do not guess).
- [ ] 2.5 Reopening an already-active singleton panel refocuses it rather than reconstructing it —
      assert no remount occurs (e.g. via a render-count probe in the test) when the same panel is
      reopened.
- [ ] 2.6 Tests: opening each of the three panels from an empty state; switching between them without
      closing; reopening the active panel is a no-op; closing the shell and reopening restores the
      previously active panel, not a default.

## 3. Migrating `SpecDocumentPanel` into the `spec` panel slot

- [ ] 3.1 `SpecDocumentPanel`'s existing props (`path`, `inventory`, `onSelectPath`, `onClose`, …) are
      threaded from the shell's `spec` slot rather than from `ConversationView` directly (design D3).
      No change to `SpecDocumentPanel.tsx`'s own internals — breadcrumb, archived marker, `SpecPhaseBar`,
      `SpecCoverageBar`, `SpecProposalsPanel`, `SpecDocumentTasksLink`, the `SpecFrame` bridge, and the
      outline rail all keep working exactly as before.
- [ ] 3.2 Tests: every existing `SpecDocumentPanel`/`ConversationView` interaction test (document open,
      document closed, picker reopened, phase/coverage bars rendering) passes unchanged after the
      re-hosting — a regression here means the migration touched behavior it was not supposed to.

## 4. Loop tab (`hub/ui/src/components/agents/LoopPanel.tsx`, new)

- [ ] 4.1 New `LoopPanel` component consuming `LoopSummary` (already returned by
      `_batch_loop_summaries` via the jobs API, per task 1's fix) for purpose, stop condition/reason,
      per-status queue counts, claimed item, and open-questions count — the same data `JobCard.tsx`'s
      existing `LoopBlock` (`:88-172`) already renders, adapted to this surface rather than
      re-derived.
- [ ] 4.2 New job-scoped live-ness lookup (design D6): reuse the lifecycle-event/streamed-status-line
      signal `AgentTimeline.tsx`'s `runVisiblyActive` (`:104`) already derives, scoped to the loop's
      job's most recent `JobRun.conversation_id` rather than to the currently open conversation's
      agent. Read `AgentTimeline.tsx`'s gate logic in full before deciding whether to extract a shared
      hook or duplicate the derivation at the new scope — the design leaves this open.
- [ ] 4.3 Empty state: a conversation whose job has no loop states so plainly, rather than an empty
      table.
- [ ] 4.4 Live updates via the existing `useSSE` hook, invalidating the loop summary query on
      `job_run_failed`, `loop_stopped`, `loop_queue_exhausted` (produced by
      `2026-08-18-a-loop-writes-its-own-queue`, consumed here for the first time), and task-status
      events — no polling.
- [ ] 4.5 Motion: only the active-now indicator animates (design D8), CSS-driven where possible to
      inherit `index.css:708-715`'s reduced-motion rule for free; a `matchMedia` check if any part of
      it is implemented outside CSS. Queue progress and stop-state badges render with no transition on
      value change.
- [ ] 4.6 Icons: audit `Icon.tsx`'s existing name map before assuming one exists for "loop" or
      "claimed task" — none was confirmed present during the exploration. Add missing names to the
      existing `lucide-react` wrapper map (CLAUDE.md's standing rule against a second icon system);
      do not introduce a second icon source.
- [ ] 4.7 Tests: summary fields render from a fixture `LoopSummary`; a claimed task in `assigned`
      status renders (regression guard for task 1's fix actually being consumed here); the active-now
      indicator reflects the live-ness lookup's true/false states; `loop_queue_exhausted`'s
      `pending_request` payload, when present, is shown; reduced-motion preference suppresses the
      indicator's animation (a jsdom `matchMedia` mock, matching this codebase's existing pattern for
      testing reduced-motion behavior elsewhere, if one exists — otherwise establish it here).

## 5. File content endpoint (`hub/hub/api/v1/workspace.py`, `hub/hub/workspace_paths.py`)

- [ ] 5.1 New `GET /api/v1/workspace/file?path=...`, project-scoped via the same
      `project_workspace.resolve_project_workspace` dependency `get_workspace_paths` already uses.
- [ ] 5.2 Allowlist (design D7): call `list_workspace_paths(workspace.root)` and refuse (404) unless
      the requested `path` is an exact member of the returned list — no separate resolve-and-
      contains-check.
- [ ] 5.3 Size bound (design D7): refuse (413 or an equivalent explicit response) a file exceeding
      `1_048_576` bytes (reusing `hub/hub/config.py`'s `aw_max_body_size` constant rather than a new
      literal), naming the file's actual size and the bound in the response body.
- [ ] 5.4 Binary detection (design D7): read the first 8,000 bytes, check for a NUL byte; if found,
      respond with a shape the client can distinguish from text content (e.g. a `binary: true` field)
      rather than attempting to serve raw bytes as a text response.
- [ ] 5.5 Tests: a listed path returns its content; a path not in the listing (traversal attempt,
      symlink outside the workspace root, or a gitignored path) is refused; a file over the size bound
      is refused with size and bound named, and confirmed to return no partial content; a binary
      fixture file is identified as binary and not returned as text; a text file at exactly the bound
      is served in full (boundary case).
- [ ] 5.6 Mutation-check: temporarily widen the allowlist check to a prefix/contains check instead of
      exact membership, confirm the traversal-refusal test in 5.5 fails by name.

## 6. File tab (`hub/ui/src/components/agents/FilePanel.tsx`, new)

- [ ] 6.1 New `FilePanel` component: fetches the project's workspace paths (the existing `GET
      /api/v1/workspace/paths`) and builds a tree using `hub/ui/src/components/spec/
      specNavigation.ts`'s existing `buildPathTree` (`:320-364`) rather than a second tree-building
      implementation, per the exploration's §7 recommendation.
- [ ] 6.2 Selecting a file fetches its content from the new endpoint (task 5) and renders it inline;
      a binary response renders the "this file is binary" state instead.
- [ ] 6.3 "Insert into composer" reuses the existing `@path` mention format the composer's trigger
      already produces (design, "insert into composer" — check `composerTrigger.ts`'s exact mention
      string shape before implementing a second one that merely looks similar).
- [ ] 6.4 Tests: the tree renders from a fixture path list; selecting a file shows its content;
      selecting a binary-flagged file shows the binary state, not garbled text; the inserted mention
      string is byte-identical to what the composer's own `@path` trigger would produce for the same
      path.

## 7. Keyboard reachability (`hub/ui/src/components/agents/ConversationView.tsx` or the new
   `PanelShell`)

- [ ] 7.1 Tab strip implements the ARIA `tablist` pattern: `Tab`/`Shift+Tab` reaches the strip,
      `Enter`/`Space` activates the focused tab, arrow keys move focus between tabs while the strip
      has focus.
- [ ] 7.2 The plus affordance and its menu are keyboard reachable and operable using whatever pattern
      this codebase's other menus already use (do not invent a second menu-interaction pattern).
- [ ] 7.3 Tests: keyboard-only activation of a tab produces the same `activePanel` state change as a
      pointer click; arrow-key navigation moves focus without activating; the plus affordance's menu
      opens and its items activate via keyboard.

## 8. Full-suite verification — agent-verifiable

- [ ] 8.1 `py -3.11 -m pytest hub/tests -q` — full backend suite green, including every new test in
      tasks 1 and 5.
- [ ] 8.2 `py -3.11 -m mypy hub/hub/` clean.
- [ ] 8.3 `cd hub/ui && npm run lint` and the UI test suite (`npm test` or the project's equivalent)
      green, including every new test in tasks 2, 3, 4, 6, 7.
- [ ] 8.4 `npx openspec validate --changes --strict` passes with this change included (already
      confirmed for the spec text itself; re-run after implementation in case a later edit to this
      file drifted from the delta).
- [ ] 8.5 `npm run build` in `hub/ui`, then `py -3.11 scripts/refresh_ui_bundle.py` — confirm the
      rebuild is not accidentally reported `ui_stale` afterward (the false-positive this session's Q4
      fixed; do not reintroduce a reason for it to fire).

## 9. Human-only verification

- [ ] 9.1 **Does the shell actually read like "just like T3 does," or like AgentWeave's own thing
      wearing T3's layout?** The operator's own comparison — drive the shell in a browser, open all
      three tabs, and judge whether the tab strip, plus affordance, and resize behavior feel coherent
      with the rest of the Hub UI, not merely functionally equivalent to the reference.
- [ ] 9.2 **Is the loop tab's active-now indicator legible without being distracting?** The one place
      this change deliberately adds motion (design D8) — watch it during a real firing and judge
      whether it communicates "something is happening" without drawing attention away from the
      conversation itself.
- [ ] 9.3 **Does the file panel's binary-file state read as informative or as a dead end?** Open a
      binary fixture (an image or compiled artifact already in the repo) through the file tab and
      judge whether the response tells the operator what to do next, or just that something failed.
- [ ] 9.4 **Does switching to the loop or files tab ever feel like it lost the document?** Open a
      document, switch to the loop tab, switch back — confirm by eye (not only by test) that the
      document reappears exactly as left, with no flash of an empty picker state in between.
- [ ] 9.5 **Keyboard-only pass.** Navigate the entire tab strip and plus affordance using only the
      keyboard, on a real keyboard, not simulated events — confirm focus is visibly indicated at every
      step, since a test asserting the correct element receives focus does not prove the operator can
      *see* where focus is.

## 10. User test guide

**Setup.** A project registered in the Hub with at least one conversation, one specification document
already created, and — if `2026-08-18-a-loop-writes-its-own-queue` has shipped by the time this is
tested — a loop with at least one queued task. A project workspace containing at least one small text
file, one file over the 1 MiB bound, and one binary file (e.g. a `.png`), for the file tab.

1. **Open a conversation with a document already attached.** — *Expect:* the document opens in the
   shell's `spec` tab, exactly as it does today.
2. **Open the plus affordance and select the `loop` tab.** — *Expect:* the shell switches to the loop
   tab; the document is not closed. If the conversation's job has no loop, the tab states this
   plainly rather than showing an empty table.
3. **Switch back to the `spec` tab.** — *Expect:* the same document reappears, not a picker.
4. **Open the `files` tab and navigate to a small text file.** — *Expect:* the tree shows the
   project's files; selecting the text file shows its content inline.
5. **Select the oversized file.** — *Expect:* a refusal naming the file's size and the bound, not a
   truncated partial render.
6. **Select the binary file.** — *Expect:* the panel states it is binary, not garbled text.
7. **Insert the text file into the composer from the files tab, then type `@` and the same filename
   in the composer directly.** — *Expect:* the two mentions are the same text.
8. **Resize the shell, then reload the page.** — *Expect:* the same width, the same active panel, and
   (if a document was open) the same document all survive the reload.
9. **Narrow the browser window below the shell's combined minimum width.** — *Expect:* the panel
   becomes an overlay; dismissing it leaves a control to reopen the same panel, not a lost state.
10. **If a loop with an active firing is available, open its loop tab while the firing runs.** —
    *Expect:* the active-now indicator animates while the firing is in progress, and stops animating
    once it settles.

**Where it would go wrong:** if step 3 shows a document picker instead of the same document, the
`activePanel`/`document` state split (design D5) likely collapsed into a single field somewhere and
lost the document's identity on tab switch. If step 5 returns a truncated file instead of a refusal,
the size-bound check (design D7, task 5.3) is truncating rather than refusing. If step 10's indicator
never animates, check that the live-ness lookup (task 4.2) is scoped to the loop's job's current run
and not accidentally reading the roster-wide polled `agent.status` field the design explicitly
rejected.
