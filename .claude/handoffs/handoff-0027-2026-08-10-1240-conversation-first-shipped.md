# Handoff: the conversation became the frame, and the document opened beside it

**Date:** 2026-08-10T12:40 · **Branch:** hub-native-experience · **HEAD:** `0ba6871`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0026-2026-08-10-1152-spec-screen-rethought-and-proposed.md`
**Status:** change complete. 4 commits, **none pushed yet.** Working tree clean.

## Goal

The operator approved the proposal handoff 0026 left pending — *"$resume approved. Apply the spec."*
— and changed one standing rule with it: **write a handoff only when asked, or when a change is
done.** This is the second case.

So this session was implementation: all eight sections of
`2026-08-10-conversation-first-spec-workspace`, verified live rather than assumed.

## Current state

**`2026-08-10-conversation-first-spec-workspace` is implemented, verified, and synced.** Every
6.x check ran with real numbers; 7.1–7.5 are the operator's and are recorded as unrun. The deltas
are in `openspec/specs/spec-chat-session/` and `openspec/specs/hub-workspace-shell/`. The change
directory has **not** been archived — that is a separate `openspec-archive-change` step.

### The shape that shipped

- **The document lives in the destination.** `WorkspaceDestination`'s `conversation` variant gained
  `document: string | null`, carried in the URL, validated against the frontend twin of
  `validate_spec_path`. An illegal path resolves to `null`, never an error page, and never reaches
  the URL on the way out either.
- **`tab: 'spec'` is a way in, not a place.** It resolves (replace, not push) into a conversation
  with the manifest home document open — the agent's most recent conversation, or a new one.
- **`ConversationView`** (`components/agents/`) is the new frame: conversation column 420–560
  (default 480, persisted), document panel taking the rest with a 560 minimum, `PaneResizer`
  between them, and an overlay below the derived 981px threshold.
- **`SpecDocumentPanel`** (`components/spec/`) carries the frame, a breadcrumb that opens the Ctrl+K
  picker, the outline behind a toggle, the drift report, and the archived marker.
- **The rail collapses only when the operator says so**, and the collapsed state is a real icon rail
  with accessible names — not the blank 40px strip it was.
- **Deleted:** `SpecPage`, `SpecWorkspace`, `SpecNavigator`, and `SpecChat` with its `<select>`.
  `useWorkspaceWidth` and the drawer survive as `components/layout/useWorkspaceWidth.ts` and
  `components/layout/Drawer.tsx`.

## Files touched

Everything **committed**; `git status --short` is empty. Nothing is pushed.

### `27c9ec5` — sections 1–4

- `hub/ui/src/lib/navigation.ts` — `document` on the conversation destination; `isSpecDocumentPath`,
  `parseSpecDocument`, `withDocument`; serialise/parse.
- `hub/ui/src/components/agents/ConversationView.tsx` — **new**, the frame.
- `hub/ui/src/components/spec/SpecDocumentPanel.tsx` — **new**, the panel.
- `hub/ui/src/components/layout/Drawer.tsx`, `useWorkspaceWidth.ts` — **new**, lifted out of the
  deleted `SpecWorkspace`.
- `hub/ui/src/components/spec/specPreferences.ts` — rewritten to one value, `conversationWidth`.
- `hub/ui/src/App.tsx` — the spec entry-point effect, the rail collapse state, `ConversationView`.
- `hub/ui/src/components/layout/Sidebar.tsx` — `CompactRail` and the collapse toggle.
- `hub/ui/src/components/agents/Composer.tsx`, `ComposerModelControls.tsx`, `ModelPicker.tsx` — the
  control row wraps; pills truncate their value, never their name; the value moved into the tooltip.
- `hub/ui/src/components/agents/AgentOutputPanel.tsx`, `ConversationControls.tsx` — the header wraps
  and names the agent once (the duplicate identity block in `ConversationControls` is gone);
  `Jump to newest` takes a row instead of floating.
- Deleted: `components/spec/SpecPage.tsx`, `SpecWorkspace.tsx`, `SpecNavigator.tsx`, `SpecChat.tsx`.

### `2affa40` — section 5 (tests)

`specNavigationUi`, `specWorkspace`, `specDriftReport`, `specChatSurface` rewritten against
`ConversationView`; `urlNavigation` gained the document round-trip and the illegal-path cases;
`projectRail` gained the collapsed-rail suite; `App-mount` asserts the Spec tab resolves into a
conversation; `modelPicker` / `composerModelControls` / `conversationNavigation` updated.

### `bf5b9ee` — `hub/hub/static/ui` rebuilt · `0ba6871` — closeout + spec sync

## Key decisions

1. **The document is carried across a conversation change.** It is what the operator is working on,
   not a property of the thread they work on it in. `agentDestination` takes it as a fourth argument
   and `App.tsx` passes the current one through on every conversation move.
2. **`isSpecDocumentPath` lives in `navigation.ts`, not in the panel.** The destination is the first
   thing to see an untrusted path and the last that can refuse it before it becomes a fetch. It is
   applied on parse *and* on serialise — a destination is constructed in more places than parsed.
3. **The overlay is dismissible without closing the document.** Closing the drawer keeps the
   document in the destination and leaves a named bar to reopen it — which is also the stable
   element focus returns to. Tying the two together would have left focus nowhere.
4. **`Jump to newest` became a layout row rather than a float.** The float was the defect; reserving
   padding would only have avoided overlap at the very bottom of the scroll. The row costs ~28px and
   only while following is suspended, and the existing autoscroll layout effect absorbs the reflow.
5. **The duplicate agent identity in `ConversationControls` was deleted, not shrunk.** The header
   printed the agent's name and status twice; invisible at full width, three copies once narrowed.
6. **The collapsed rail shows projects and agents, not conversations.** 40px cannot name a
   conversation, and an unnamed row is not a destination anyone can choose.
7. **The composer pill's tooltip now carries the value** (`Permissions: Edit files`) because the
   value is the part that truncates. Three test files queried `getByTitle('Model')` and were
   updated to `/^Model:/` rather than reverting the behaviour.
8. **The geometry probe counts only elements that hit-test to themselves.** Its first version
   reported a false overlap — a fold toggle scrolled out of the output pane still reports a
   rectangle. The tightened version is also the stronger claim: the element is reachable where it
   says it is.

## Constraints and user directives (verbatim)

**From this session:**
- *"$resume approved. Apply the spec."*
- *"I want to change also de cadency of handoff. Apply a handoff only when prompted or a spec is
  done."* — **now the rule.** Saved to memory as `feedback_handoff_cadence.md`. Do not write a
  handoff at chunk boundaries or context thresholds; commit checkpoints instead.

**Carried and still binding:**
- **STANDING DIRECTIVE:** *"when creating the spec we have to think how to manually test this…"* —
  every change's `tasks.md` splits agent-verifiable from human-only and emits a user test guide.
- *"Wait. Are you already implementing? Should we dive in first…"* — lay out the plan before
  building anything non-trivial.
- *"Kind of lost"* — the operator is sensitive to volume. Answer briefly; point at one file.
- *"What is taking so long?"* — sensitive to wall-clock.
- *"The spec should still be generated as html"*; *"no need for backups everything is test env"*;
  *"B. fixed back to the agent's conversation. Yes, no agent deletion. Just archive."*;
  *"I don't want it to be colorful it should be like the chat box but maybe a little lighter"*;
  *"first I think we have to many we need to cut some of those"* (the 21 charters);
  *"the charter exists to give instructions so I can use agentweave for more then developing."*
- From `CLAUDE.md`: never create `.agentweave/`, `agentweave.yml` or `spec/` at the repo root; stage
  paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` is a committed artefact
  refreshed after `npm run build` and confirmed with `diff -rq`; never mark a task complete on the
  strength of a plan existing.
- From memory: commit each completed checkpoint without asking; live-verify prior claimed work on
  resume; ask the operator for agent + model choice when setting up agents.

## Dead ends

**New this session:**
- **`requestAnimationFrame` never fires and `ResizeObserver` never delivers in the `t3-code`
  automation tab.** Measured: both returned `false` inside a 1s window while `document.hidden` was
  `false`. So **responsive re-layout cannot be driven live** — narrowing a container at runtime does
  not reach the layout. The mount-time `getBoundingClientRect` path does work, so reach each width by
  **reloading into it** (persisted rail width, persisted conversation width) rather than resizing.
- **`preview_snapshot` returns ~25k tokens of accessibility tree and truncates.** Use it only when a
  screenshot is genuinely needed; `preview_evaluate` answers almost everything for a fraction.
- **`preview_click` did nothing at all** on one attempt (not just the schema error) — the
  element-`.click()` route through `preview_evaluate` is more reliable.
- **A bash heredoc containing an apostrophe inside a Python string broke the shell.** Write the
  script with the Write tool and run it.
- Running `npx vitest` from the **repo root** picks up a different project and fails alias
  resolution, and leaves an empty `node_modules/` at the root. Always `cd hub/ui` first.

**Carried and still true:**
- **The `t3-code` preview tools return a schema-validation error on every mutating call** — and the
  action usually happened anyway. Verify with `preview_evaluate` after. **`preview_press` does not
  work**; **`preview_resize` times out.**
- **`preview_evaluate` must return an object**, not a bare array.
- **Do not set `document.documentElement.dataset.mode` by hand** to test light mode — `App.tsx` owns
  it and the page ends up mixed.
- **PowerShell here-strings break on bash-style quote escaping.** Use a commit-message file.
- **PowerShell cwd persists between calls**; **`cd hub/ui` fails from the Bash tool** with a relative
  path — use the absolute one.
- **The spec API is at `/api/v1/projects/{id}/project/specs`.**
- **`openspec validate` wants SHALL/MUST on the *first line* of a requirement body.**
- **`npm run lint` does not work at all** (ESLint 9 needs a flat config); `tsc` checks.
- **`pytest hub/tests/ tests/` together fails collection** — run separately.
- **The default `python` on PATH has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **The Hub API rejects `X-API-Key`** — use `Authorization: Bearer <key>`.
- **Adding a hook to a component breaks every test that mocks that api module.** Stub the
  conversation component rather than adding a dozen api mocks.
- **`.claude/handoffs/LATEST.md` is not updated automatically.**

## Verification

**Ran this session, with real output:**
- `npx vitest run` — **73 files, 664 passed** (was 661).
- `npx tsc --noEmit` — clean.
- `pytest hub/tests/` — **1280 passed, 10 skipped**; `pytest tests/` — **372 passed, 3 skipped**.
  Unchanged; no backend file was touched.
- `npm run build` + `diff -rq hub/ui/dist hub/hub/static/ui` — identical.
- `npx openspec validate --specs --strict` — **27 passed, 0 failed.**
- **Live, against the Hub on `:8010`, project `proj-cddb0827`, document `spec/a1-probe.html`:**
  geometry clean (no overflow, no clipping, no overlap) at conversation 420 / 480 / 560; the derived
  breakpoint confirmed on both sides (**981 → two columns at exactly 420 + 560; 980 → overlay**);
  collapsed rail exposes every project and agent by accessible name with the active one marked;
  open/close/reload of the document panel; overlay focus trap, Escape, and focus return; **a real
  question answered** (Hub recorded `answer: "Yes"`) and **a real permission allowed** (
  `layout-probe.txt` written into `claude-1`'s worktree). Full numbers in the change's
  `tasks.md` closeout record.

**Explicitly NOT verified — do not assume:**
- **7.1–7.5 are unrun**, plus the five human-only items carried from A1 and the two older changes.
  One reduced-motion sitting still closes three tasks; one keyboard sitting closes two.
- **Screenshots exist for two of the four widths** (420 and 480), not all four. All four were
  measured numerically.
- **CI has still never run on this branch** — `ci.yml` triggers only on push/PR to `master`. Now
  **335 commits** (`git rev-list --count master..HEAD`) with no Linux, no macOS, no Python
  3.8/3.9/3.10/3.12.
- **Migration `0051` has only been applied to SQLite.**
- Carried: no live agent has called `submit_checkpoint_notes` or `recall`; `files_changed` has never
  been observed non-empty; the checkpoint final-warning banner has never been seen in a browser.

## Git state

Branch `hub-native-experience`, HEAD **`0ba6871`**, working tree clean, **4 commits unpushed**,
335 ahead of master.

| sha | what |
|---|---|
| `27c9ec5` | Make the conversation the frame and open the document beside it |
| `2affa40` | Rewrite the spec suites for a conversation with a document beside it |
| `bf5b9ee` | Refresh the committed UI build artefact |
| `0ba6871` | Close the conversation-first change and sync its two capabilities |

(A fifth, this handoff, follows.)

## Next steps

1. **Push.** Four commits are local only.
2. **Look at it.** The change is verifiable by measurement but not by taste; 7.1–7.3 are twenty
   minutes and decide whether the proportions were right.
3. **Archive `2026-08-10-conversation-first-spec-workspace`** once 7.x has been run — the deltas are
   already synced, so archiving is the only step left.
4. **One reduced-motion sitting closes three tasks** — charcoal 8.10, contextual-navigation 7.7, and
   this change's 7.5. One keyboard sitting closes A1 6.3, charcoal 8.8, and this change's 7.4.
5. **The contrast decision**, charcoal `tasks.md` **8.11** — AA 4.5 and lose the third text level,
   3.0 and keep it, or a recorded exemption. Still the only thing blocking that archive.
6. **The `ci.yml` branch trigger** — raised five times now, unanswered. One line.

## Open questions for the user

1. **Do the proportions feel right?** 7.1–7.3. The only thing measurement cannot answer.
2. **The contrast bar for 1.0** — AA 4.5, 3.0, or a recorded exemption. Blocks the charcoal archive.
3. **The `ci.yml` branch trigger** — yes or no.
4. **How many charters, and which non-software domains should the starter set demonstrate?**
   **Still blocks B0.**
5. **Is "explore" a phase, or just the absence of one?** Affects B5's phase model.
6. **Should the propose offer come from the agent mid-turn, or from the machine at a threshold?**
7. Carried and unanswered across twelve handoffs: **should `.claude/handoffs/` stay tracked?** Now
   113 files.
8. Carried: the two model-less default runners on `proj-cddb0827`;
   `testbed/CHECKPOINT-TEST-GUIDE.md` still names the old project `proj-84d218db`; peer-thread
   grouping deferred 2026-08-08; titling should migrate onto the Worker.

## Read on resume

- `openspec/changes/2026-08-10-conversation-first-spec-workspace/tasks.md` — **read the closeout
  record first.** Every measured number is there.
- `hub/ui/src/components/agents/ConversationView.tsx` — the frame, the proportions, the breakpoint.
- `hub/ui/src/components/spec/SpecDocumentPanel.tsx` — the panel.
- `hub/ui/src/lib/navigation.ts` — the destination and the path contract.
- `openspec/explorations/2026-08-10-specification-and-surface-program-roadmap.md` — the orientation
  document. Program A is complete bar its human checks; B is what follows, and B0 is blocked on the
  charter question above.
