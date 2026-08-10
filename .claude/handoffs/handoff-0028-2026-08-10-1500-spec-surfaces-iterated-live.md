# Handoff: the spec surfaces, iterated live against the operator

**Date:** 2026-08-10T15:00 · **Branch:** hub-native-experience · **HEAD:** `58d7cc0`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0027-2026-08-10-1240-conversation-first-shipped.md`
**Status:** **mid-flight, not closed.** *"I'm still testing. There are some minor changes that we
need to do yet."* 11 commits, **none pushed.** Working tree clean.

## Goal

Handoff 0027 closed `2026-08-10-conversation-first-spec-workspace`. This session is what happened
when the operator actually used it: six reports, each one diagnosed and fixed or turned into a
decision, then four more rounds of the same. It is iteration against a live operator, not a
planned change — nothing here belongs to an openspec change that was not already closed.

**Expect more.** They are still testing and have said there are minor changes outstanding.

## Current state

Everything below is shipped, live on `:8010`, and verified. The order is the order it happened,
because several items are corrections to earlier items in the same session.

### Defects fixed

1. **The picker was painted over by the conversation header** (`e428958`).
   `.conversation-header-surface` carries `z-index: 3`; the Radix portals in `SpecDocumentPicker`
   and `Drawer` carried none, so `auto` lost to it. Both now `z-50`, matching every other modal.
2. **The rule under the document panel header** — deleted. The divider is already the boundary.
3. **A spec document got *narrower* as its container got wider** (`ea7d8f1`, then really
   `cef5d92`). Two causes, and the first fix was aimed at the wrong one:
   - The TOC appeared below the width at which nav + full-measure `main` both fit, so crossing it
     cost the text 215px in the shipped skeleton.
   - **The real cause:** `specBridge` sets `nav.toc { display: none }` once it has read the
     anchors. A layout with a fixed track for the nav drops `main` into that track when it
     vanishes — the mock's `grid-template-columns: 220px 1fr` squashed the text to 140px.
4. **No table of contents at all, at rest** (`cef5d92`). The bridge's removal of the in-document
   TOC was unconditional; the panel's outline strip was opt-in and defaulted closed. It now
   defaults open.
5. **Overview's Spec card landed on Environment → Quality** (`de184ad`) — dead since the tab was
   deleted earlier in the day. Fixed by the tab returning.

### Decisions the operator made, and reversed

- **The 560 cap on the conversation is gone** (`1fa0e15`). It made the document panel impossible
  to shrink. Minimums 380/360; the ceiling is only what the measurement leaves.
- **`tab: 'spec'` was deleted, then brought back as a different screen** (`1fa0e15`, `de184ad`).
  The composer's **Spec pill** is the specification *beside* a conversation; the **Spec tab** is
  the specification on its own. Both exist and mean different things.
- **The spec tree moved into the rail** (`4a0bdb0`), replacing the project tree the way
  Environment does, with a back control. *"Two navigations are weird."* `SpecPage` is now just the
  document.
- **Prose is capped, not the container** (`b2cf28b`). Tables and task lists break out to the full
  width; body text stops at the measure; everything shares one left edge.

### Built

- `components/spec/SpecTree.tsx` — the folder hierarchy, shared by the Ctrl+K picker and the rail.
  Collapsible folders, persisted (`aw.spec.treeCollapsed`), shared between both homes.
- `components/spec/SpecRailNav.tsx` — the rail's spec mode.
- `components/spec/SpecPage.tsx` — the focused screen (document only).
- `components/agents/ComposerSpecControl.tsx` — the Spec pill.
- `lib/navigation.ts` — `buildPathTree`, `isSpecDestination`; the project destination carries a
  `document` for the Spec tab.
- `testbed/mock-spec/` — a change-spec and a roadmap written to `html-spec-conventions.md`, plus
  `upload.py`. **Uncommitted by design** (`testbed/` is disposable). Re-upload with
  `python testbed/mock-spec/upload.py`.

### The last exchange, which is the most transferable thing here

The operator asked: *"by measuring pixels aren't you making things a little bit too catered to my
monitor?"* They were right, and it was worse — the number was tuned to a **font**. `78ch` is 673px
in system-ui, 766px in Georgia, 841px at a 20px base, and the breakpoint guarding it was a fixed
`940px`. Unifying the units was *also* not enough: media-query `em` ignores `html { font-size }`,
losing 230px at 945.

**So the breakpoint is gone** (`58d7cc0`). The nav is `flex: 1 1 var(--nav)` in a wrapping row and
`main`'s basis is `calc(var(--measure) + var(--gutter))`. They sit side by side exactly when both
fit. Swept 320–2400px across three fonts at four base sizes: prose never reflows shorter, and the
wrap point *moves* (765 / 940 / 1175 / 1410).

## Files touched

All committed; `git status --short` empty. **Nothing pushed.**

| sha | what |
|---|---|
| `e428958` | z-index on the portals; the panel rule removed |
| `1fa0e15` | free-drag boundary; Spec pill; `tab: 'spec'` deleted |
| `6ec4d50` | the two reversed decisions recorded; `spec-chat-session` synced |
| `ea7d8f1` | the narrowing defect, first (partial) fix — the breakpoint |
| `cef5d92` | the real fix — layout must survive its TOC being hidden; outline defaults open |
| `680d275` | the picker opens on the folder tree |
| `9877978` | the open document carried across a change of agent |
| `de184ad` | the Spec screen returns, with no conversation |
| `4a0bdb0` | the tree moves into the rail; folders fold |
| `b2cf28b` | prose capped, wide blocks break out |
| `58d7cc0` | the wrap point derived rather than hardcoded |

**Product code outside the UI:** only
`src/agentweave/templates/skills/references/html-spec-conventions.md` — three times. It is shipped
to users and every generated spec is written from it.

## Key decisions

1. **Two routes to a specification, deliberately.** Pill = beside a conversation. Tab = on its own.
   Deleting the tab and bringing it back is not churn; the second one is a different screen.
2. **The rail is the navigation.** A screen that needs navigation takes the rail over with a back
   control, as configuration already did. It does not grow a second one.
3. **`SpecTree` is one component in two homes.** The picker had it inline; extracting it when the
   rail needed it was the alternative to a second copy.
4. **The document is in the destination** on both surfaces — linkable, survives reload.
5. **Carried, not stored.** The open document rides along on conversation navigations but is null
   anywhere that is not a conversation, so a shared link never resurrects one.
6. **Closing is the panel's control, never the pill's.** A control that means "open" sometimes and
   "close" other times is two controls wearing one hat.
7. **No magic number in the document layout.** Derive the wrap from what has to fit.

## Constraints and user directives (verbatim)

**From this session:**
- *"Two navigations are weird."*
- *"just to focus on spec"* — the Spec screen carries no conversation.
- *"a memory between agents"* — the open document survives an agent change.
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* —
  **the standing lesson: a measured constant is still a constant. Derive it or express it in the
  same unit as the thing it guards.**
- *"I'm still testing. There are some minor changes that we need to do yet."*

**Carried and still binding:**
- **Handoff cadence:** only when asked, or when an openspec change is done. This one was asked for.
- **STANDING DIRECTIVE:** every change's `tasks.md` splits agent-verifiable from human-only and
  emits a user test guide.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and to wall-clock.
- *"The spec should still be generated as html"*; *"no need for backups everything is test env"*;
  *"first I think we have to many we need to cut some of those"* (the 21 charters);
  *"the charter exists to give instructions so I can use agentweave for more then developing."*
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage paths
  explicitly; openspec never aw-spec skills; `Icon` is the only icon system; `approve_tool_call`
  keeps **no return annotation**; `hub/hub/static/ui` refreshed after `npm run build` and confirmed
  with `diff -rq`; never mark a task complete on the strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **Measure the real input.** A sweep of the document fetched from the API came back clean while
  the bug was live: the frame renders `srcdoc`, *after* `withHubTheme` and `withSpecBridge`. Take
  `frame.getAttribute('srcdoc')` and render it in a **same-origin probe iframe** (no `sandbox`) —
  that is the only way to measure inside it.
- **`ch` against a `px` breakpoint is a silent trap.** So is `rem` against a media-query `em` when
  the document sets `html { font-size }`.
- **A bash heredoc containing an apostrophe inside a Python string breaks the shell.** Twice now.
  Write the script with the Write tool, or use the Edit tool.
- **`preview_snapshot` returns ~25k tokens** and truncates; it also started failing outright late
  in the session. `preview_evaluate` answers nearly everything for a fraction.
- **`preview_click` sometimes does nothing at all.** Prefer `element.click()` via
  `preview_evaluate`.
- **Radix `Dialog.Content` is also labelled** — `getByLabelText('Search documents')` matches the
  dialog *and* the input. Query the input by placeholder.
- Running `npx vitest` from the **repo root** picks up a different project, fails alias resolution,
  and leaves an empty `node_modules/`. Always `cd hub/ui` first.

**Carried and still true:**
- **`requestAnimationFrame` never fires and `ResizeObserver` never delivers in the automation tab.**
  Responsive *re*-layout cannot be driven live; reach each width by reloading into it.
- The `t3-code` mutating calls return a schema error and usually worked anyway; **`preview_press`
  and `preview_resize` do not work.**
- **`preview_evaluate` must return an object**, not a bare array.
- **PowerShell here-strings break on bash-style quote escaping**; **`cd hub/ui` fails from Bash with
  a relative path.**
- **The spec API is at `/api/v1/projects/{id}/project/specs`**; the Hub rejects `X-API-Key` — use
  `Authorization: Bearer`.
- **`npm run lint` does not work at all**; `tsc` checks. **`pytest hub/tests/ tests/` together fails
  collection** — run separately. **The default `python` has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.

## Verification

**Ran, with real output:**
- `npx vitest run` — **75 files, 697 passed** (was 664 at the last handoff).
- `npx tsc --noEmit` — clean. `pytest tests/` — 372 passed, 3 skipped.
- `npm run build` + `diff -rq` on `hub/hub/static/ui` — identical, refreshed on every UI commit.
- `npx openspec validate --specs --strict` — 27 passed (at `6ec4d50`).
- **Live**, throughout: the picker painting above the header; the tree in the rail at 220 with the
  project tree gone; folding `changes` hiding its nested directory and its document, and
  `{"spec/changes":true}` in storage; the document carried across an agent change and staying
  closed when closed; prose holding at 672px from 859 through 2000 while the table grows to 1120.

**Not verified, and deliberately:**
- **`pytest hub/tests/` has not been re-run since `0ba6871`.** No Hub file was touched after it, so
  it should still be 1280/10 — but that is inference, not a measurement.
- **No screenshot since `4a0bdb0`.** `preview_snapshot` began failing; everything after is measured
  numerically only. **Someone should look at it.**
- The five human-only items (7.1–7.5) from the closed change remain unrun, and the layout has
  changed substantially since they were written — 7.1 and 7.2 in particular are now about a
  different screen.
- **CI has still never run on this branch** — 347 commits ahead of master, no Linux, no macOS, no
  Python 3.8–3.12.

## Git state

Branch `hub-native-experience`, HEAD **`58d7cc0`**, working tree clean, **16 commits unpushed**,
**347 ahead of master**.

## Next steps

1. **Ask the operator what the outstanding minor changes are.** They said there are some; they did
   not say what. Do not guess.
2. **Look at the thing.** Nothing has been seen since `4a0bdb0`; if `preview_snapshot` still fails,
   open it manually.
3. **Re-run `pytest hub/tests/`** to turn the inference above into a measurement.
4. **Push**, when they want it — 16 commits.
5. **Then** the human-only checks, rewritten for the surfaces as they now are.
6. Still open and unanswered: the contrast bar (charcoal 8.11), the `ci.yml` branch trigger, and
   the charter count that blocks B0.

## Open questions for the user

1. **What are the outstanding minor changes?** Blocking next-step 1.
2. **The agent-settings round trip loses the open document** — the settings destination has no
   `document` field. Worth adding, or leave it?
3. **The contrast bar for 1.0** — AA 4.5, 3.0, or a recorded exemption. Blocks the charcoal archive.
4. **The `ci.yml` branch trigger** — yes or no. Raised six times.
5. **How many charters, and which non-software domains?** Still blocks B0.
6. Carried: should `.claude/handoffs/` stay tracked (now 114 files); the two model-less runners on
   `proj-cddb0827`; `testbed/CHECKPOINT-TEST-GUIDE.md` names the old project.

## Read on resume

- **This file's "last exchange" section first** — it is the standing lesson, not a detail.
- `src/agentweave/templates/skills/references/html-spec-conventions.md` — the only shipped
  non-UI file touched, and the one with the most reasoning per line.
- `hub/ui/src/components/spec/SpecTree.tsx` and `SpecRailNav.tsx` — the navigation as it now is.
- `hub/ui/src/components/agents/ConversationView.tsx` — the conversation-with-document surface.
- `openspec/changes/2026-08-10-conversation-first-spec-workspace/tasks.md` — the closeout **and**
  the amendment recording the two reversed decisions.
