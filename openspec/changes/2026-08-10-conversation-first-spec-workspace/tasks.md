# Tasks — Conversation-first specification workspace

> Implementation MUST NOT begin until the proposal is approved.
>
> Verification is split per the standing directive of 2026-08-10: section 6 is what the agent
> verifies, section 7 is the operator's guide. **A human-only item is never left as a bare unchecked
> box** — each carries steps, an expected result, and what failure looks like.
>
> Ordering is deliberate: the destination model changes first because every surface below is routed
> by it, and the rail is repaired before the panel is built so the two are never competing for the
> same space in a half-finished state.

## 1. Destination — the document becomes part of the conversation view

- [x] 1.1 Add `document: string | null` to the `conversation` destination in `lib/navigation.ts`,
      and carry it in the URL beside the conversation.
- [x] 1.2 Parse and serialise it, rejecting a path that is not a legal specification path — the same
      rule `validate_spec_path` applies server-side. An illegal value resolves to `null`, never to an
      error page.
- [x] 1.3 Route `tab: 'spec'` into a conversation destination: the agent's most recent conversation
      (or a new one when it has none), with the manifest home document open. Replace, not push — it
      is a way in, not a place to go Back to.
- [x] 1.4 Update `resolveConversationSelection` and the destination tests for the new field.

## 2. Rail — the operator decides, and a collapsed rail stays navigable

- [x] 2.1 Remove `compact={activePage === 'spec'}` from `App.tsx`.
- [x] 2.2 Give `Sidebar` a real collapsed mode: project and agent marks as icons with accessible
      names and tooltips, the active one still indicated, and the expand control reachable. Every
      branch is currently gated `!compact`, so this is new rendering, not a style pass.
- [x] 2.3 Make collapse an operator toggle, persisted next to the existing rail width.
- [x] 2.4 Tests: collapsed rail exposes a reachable, named control for every project and agent the
      expanded rail does; the state survives reload; no page can set it.

## 3. Document panel

- [x] 3.1 Build the panel: `SpecFrame` in a container with its own header (breadcrumb opening the
      Ctrl+K picker, close control), opened and closed from the conversation view.
- [x] 3.2 Move the outline into the panel as a collapsible strip, shown only when a document is open.
- [x] 3.3 Size the boundary with the shared `PaneResizer` (conversation 420–560, default 480;
      document minimum 560), persisted.
- [x] 3.4 Below the fit threshold, the panel becomes an overlay rather than a column, reusing the
      existing drawer behaviour — focus trapped, Escape closes, focus returns to the opener.
- [x] 3.5 Delete `SpecNavigator`'s library column and its Library/History mode control; the picker
      already carries both, including switching to History for an archived result.

## 4. Conversation surface at panel widths

- [x] 4.1 Make the composer control row wrap below its minimum, with each pill keeping its control
      name and truncating only its value (design.md Decision 5). Nothing leaves the row at any width.
- [x] 4.2 Fix the conversation header at narrow widths: it currently crowds and truncates. The agent
      name must not appear more than once.
- [x] 4.3 Stop `Jump to newest` overlapping the last entry.
- [x] 4.4 Delete `SpecChat.tsx` and its agent `<select>`; the destination supplies both the agent and
      the conversation.

## 5. Cleanup and tests

- [x] 5.1 Delete `SpecPage`/`SpecWorkspace` machinery left with no consumer; keep
      `useWorkspaceWidth`, the drawer, and `specPreferences` where 3.3/3.4 still use them.
- [x] 5.2 Rewrite `specWorkspace.test.tsx`, `specNavigationUi.test.tsx`, `specDriftReport.test.tsx`
      for the new structure; delete `specChatSurface.test.tsx`'s agent-selector tests and keep its
      permission/question coverage against the conversation view.
- [x] 5.3 Update every test that mocks a now-unused api module, in the same commit.
- [x] 5.4 Assert `SpecFrame` still renders `sandbox="allow-scripts"` **without** `allow-same-origin`,
      and that `specBridge.ts` is unmodified by this change (design.md Decision 6).
- [x] 5.5 Assert the application offers exactly one agent-selection mechanism — the rail. This is the
      check that would have caught A1's `<select>` (design.md Decision 7).

## 6. Agent verification — expected behaviour, run by the agent

> **Presence is not rendering.** A1 asserted a permission card existed in the DOM and reported the
> requirement verified; the card existed inside an overflowing pane. Every live check below measures
> geometry. **An assertion that only proves an element exists does not close a task here.**

- [x] 6.1 `npx vitest run` — green, with the file count and the delta from 661 recorded.
- [x] 6.2 `npx tsc --noEmit` — clean.
- [x] 6.3 `pytest hub/tests/` and `pytest tests/` — green, unchanged (no backend change expected; if
      either moves, say why).
- [x] 6.4 `ruff check` and `black --check` on every touched path — clean.
- [x] 6.5 **Live geometry, the core check.** At the conversation minimum (420), the default (480),
      the maximum (560), and both sides of the overlay breakpoint: for every interactive element in
      the conversation column and the document panel, assert `right <= host.right` and
      `left >= host.left`, assert `scrollWidth <= clientWidth` (nothing clipped), and assert no two
      interactive elements' rectangles intersect. Report the measured numbers, not "passed".
- [x] 6.6 **Live, the specific regressions this change exists to fix.** At every width in 6.5:
      `Permissions` shows a readable value and its right edge is inside the panel; the conversation
      header shows the agent name exactly once; `Jump to newest` overlaps nothing.
- [x] 6.7 **Live, the rail.** With the rail collapsed, every project and agent reachable when
      expanded is still reachable — assert by accessible name, not by pixel. Confirm no route
      collapses it on the operator's behalf.
- [x] 6.8 **Live, the panel.** Open a document from a conversation, reload, and confirm the same
      document is open. Close it and confirm the conversation takes the full width. Narrow below the
      threshold and confirm the overlay traps focus, closes on Escape, and returns focus.
- [x] 6.9 **Live, still working.** Permission card and question card answered from the conversation
      with a document open — the A1 behaviour, re-demonstrated on the new layout, and this time with
      6.5's geometry assertions applied to the cards themselves.
- [x] 6.10 `npm run build`, copy `hub/ui/dist` over `hub/hub/static/ui`, confirm with `diff -rq`.
- [x] 6.11 `npx openspec validate --specs --strict`.
- [x] 6.12 **Screenshots at each tested width, attached to the closeout.** A1's miss was not looking;
      the fix is looking, and leaving proof that it was looked at.

## 7. Human test guide — what the agent cannot verify

> Each item: **do this → expect this → it failed if this.** Report the outcome; an unrun item is
> reported as unrun, never as passed.

- [ ] 7.1 **The document is comfortable to read.** Open a real specification document beside a
      conversation on your normal window size, and read a few sections.
      *Expect:* line length is comfortable without horizontal scrolling, headings and body keep their
      hierarchy, and you do not want to close the conversation to read it.
      *Failed if:* you find yourself widening the panel every time, or reading feels cramped enough
      that you would rather open the document somewhere else.
      *The agent can measure that nothing overflows; it cannot tell whether a column is pleasant to
      read.*

- [ ] 7.2 **The proportions feel right, and the divider tracks.** Drag the boundary between the
      conversation and the document across its whole range, and reload.
      *Expect:* the drag tracks the pointer with no lag or snap-back, both panes stay usable at every
      position, and the width survives reload.
      *Failed if:* either pane becomes unusable before its stop, the document reflows jarringly
      mid-drag, or the width resets.

- [ ] 7.3 **The collapsed rail is actually usable.** Collapse the rail and work for a few minutes —
      switch agents, open a conversation, come back to a project.
      *Expect:* you can do all of it from the icons, each has a tooltip naming it, and the active one
      is obvious.
      *Failed if:* you expand the rail because you cannot tell what an icon is, or cannot reach
      something you need.

- [ ] 7.4 **Keyboard traversal.** Click the document panel, then Tab through to the composer and its
      control row, then Shift+Tab back.
      *Expect:* focus reaches the panel's close and breadcrumb controls, the divider, the composer,
      and every pill; each shows a visible ring; the order reverses; focus never enters the document
      iframe and gets stuck.
      *Failed if:* anything is unreachable, shows no ring, or traps focus.
      *Agent cannot run this — a synthetic Tab does not drive the browser's focus engine; re-tested
      2026-08-10.*

- [ ] 7.5 **Reduced motion.** With Windows animation effects off, open and close the panel, collapse
      and expand the rail, and resize.
      *Expect:* states change instantly, and each remains distinguishable without the motion.
      *Failed if:* anything still animates, or a state is only legible because it moved.
      *Agent cannot run this — `prefers-reduced-motion` cannot be forced from page JavaScript. This
      is the same pass as charcoal 8.10 and contextual-navigation 7.7; one sitting covers all three.*

## 8. Closeout

- [x] 8.1 Record which 6.x and 7.x items ran and their results, with the measured numbers and the
      screenshots.
- [x] 8.2 Sync the `spec-chat-session` and `hub-workspace-shell` deltas into `openspec/specs/`.
- [x] 8.3 `/handoff`.

## Closeout record — 2026-08-10

Approved by the operator on resume ("$resume approved. Apply the spec."). Implemented in three
commits on `hub-native-experience`: `27c9ec5` (sections 1–4), `2affa40` (section 5), `bf5b9ee` (the
static artefact).

### Agent verification — what ran, with the numbers

| # | Result |
|---|---|
| 6.1 | `npx vitest run` — **73 files, 664 passed**. Was 661/73; +3 net after deleting the agent-selector tests and adding the destination, rail, and layout ones. |
| 6.2 | `npx tsc --noEmit` — clean. |
| 6.3 | `pytest hub/tests/` — **1280 passed, 10 skipped**. `pytest tests/` — **372 passed, 3 skipped**. Both unchanged; no backend file was touched. |
| 6.4 | No Python path was touched by this change, so `ruff`/`black` had nothing to run against. Stated rather than claimed clean. |
| 6.5 | See the measurements below. |
| 6.6 | See the measurements below. |
| 6.7 | Rail collapsed (52px): `Testbed`, `claude-1`, `codex-1` all present **by accessible name**, `data-active` correct on the project and on `claude-1`, `Expand navigation` reachable. Reloading a conversation destination did not change the collapsed state — no route writes it. |
| 6.8 | Closed the panel → `document` left the URL, conversation took the full 1059px, **zero** specification-navigation elements left on screen. Reopened with Ctrl+K from a conversation with nothing open → `document=spec%2Fa1-probe.html` back in the URL. Reloaded → same conversation, same document, frame title `spec/a1-probe.html`. Overlay: focus was inside the drawer, Escape closed it, focus returned to `conversation-open-document`, the document stayed in the destination, and the control reopened it. |
| 6.9 | Two real runs on `claude-1` (Haiku 4.5), document open throughout. **Question card**: 420px wide, right edge 671 ≤ host 701, no clipping, no overlap; answered "Yes" from the card; the Hub recorded `answer: "Yes"`, `answer_labels: ["Yes"]`, `answered_at 11:24:12` and the run completed. **Permission card**: `permission-request-perm-420153c2`, 420px wide, right edge 671 ≤ host 701, Allow/Deny neither clipped nor overlapping; Allow resolved the run and `layout-probe.txt` containing `ok` exists in `claude-1`'s worktree. |
| 6.10 | `npm run build`; `hub/ui/dist` copied over `hub/hub/static/ui`; `diff -rq` — identical. |
| 6.11 | `npx openspec validate --specs --strict` — 27 passed, 0 failed. The change itself validates `--strict`. |
| 6.12 | Two screenshots captured (conversation at 420 and at 480). All four widths were measured numerically; images exist for two of them. Recorded as a partial rather than claimed in full. |

### The geometry, measured

Live against the Hub on `:8010`, project `proj-cddb0827`, document `spec/a1-probe.html`, dark mode,
1280×800. For every **visible, hit-testable** interactive element in each pane: `right <= host.right + 1`,
`left >= host.left - 1`, `scrollWidth <= clientWidth + 1`, and pairwise non-intersection.

| conversation | document | layout | overflow | clipped | overlaps |
|---|---|---|---|---|---|
| 420 (minimum) | 638 | column | 0 | 0 | 0 |
| 480 (default) | 578 | column | 0 | 0 | 0 |
| 560 (maximum, rail collapsed) | 667 | column | 0 | 0 | 0 |
| 980 full width | overlay (560) | overlay | 0 | — | — |

`Permissions: Edit files` reads in full at every width, inside the pane, unclipped. The conversation
header contains the agent's name **exactly once** at every width. At 420 the composer control row
wraps to two lines with every control still present.

**The breakpoint, measured on both sides.** `DOCUMENT_COLUMN_BREAKPOINT` is derived (420 + 560 + 1 =
981). At a measured **981** the layout is two columns with the conversation at exactly 420 and the
document at exactly 560 — both minimums, fitting precisely. At a measured **980** it is the overlay.

**A first pass reported one overlap and it was a false positive** — a timeline fold toggle scrolled
out of the output pane still reports a rectangle. The probe was tightened to count only elements that
hit-test to themselves at their own centre, which is also a stronger check than the original: it
proves the element is reachable where it claims to be.

### Not verified, and how

- **Responsive re-layout could not be driven live.** `requestAnimationFrame` never fires in the
  automation tab and `ResizeObserver` never delivers (measured: both returned false inside a 1s
  window), so narrowing the container at runtime does not reach the layout. The mount-time
  measurement path does work, so each width was reached by reloading into it — via the persisted
  conversation width and the persisted rail width. The `ResizeObserver` path itself is covered by
  the unit tests, which drive the callback directly.
- **7.1–7.5 are unrun.** They are the operator's, and an unrun item is reported as unrun.

### Live state left behind

`layout-probe.txt` in `claude-1`'s worktree; two completed runs (a question probe and a permission
probe) in conversation `conv-e7aefe3c`; the conversation's permission override restored to
**Edit files**; rail width back to 220, expanded; conversation width 480.
