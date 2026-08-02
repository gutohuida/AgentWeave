# Handoff: Phase 1 (Feel foundation) complete and visually confirmed

**Date:** 2026-07-31T21:11:57+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `eedbe46`
**Agent:** Claude Code / Opus 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md`
**Status:** chunk complete — Phase 1 done (17/18, only its own handoff task remained), nothing committed

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly, using
T3 Code as a studied reference rather than forking it. Phase 1 is the *material* layer only —
typography, icons, motion, radius, surfaces, controls — deliberately changing nothing about the
information architecture.

Full reasoning lives in `openspec/changes/2026-07-30-hub-native-experience/`
(`proposal.md`, `design.md` with 12 numbered decisions, `tasks.md` with 27 closed decisions and
16 phases, `mock.html` as the visual reference, and 10 delta specs totalling 73 requirements /
204 scenarios).

## Current state

**Phase 1 is complete and the user has visually confirmed it**, in their words: *"It's working and
it looks like the same app but better built, more polished."* That was the intended outcome — the
mock's layout (project tree, tabs, conversation timeline) is Phases 8–11 and was explicitly not
attempted here.

Green across the board: `npx tsc --noEmit` clean, `npm run build` clean, **21 test files / 180 tests
passing**.

**Both servers are currently running in the background:**
- Hub — `http://127.0.0.1:8000`, started with
  `cd hub && DATABASE_URL="sqlite+aiosqlite:///./data/agentweave-dev.db" python -m uvicorn hub.main:app --host 127.0.0.1 --port 8000`
- Vite — `http://localhost:5174` (5173 was occupied by an unrelated stale dev server from an
  earlier session — **ignore 5173, it does not serve this source**)

`pip install -e ./hub` was run this session, so the `hub` package and its dependencies are now
importable from the ambient Python.

## Files touched

**Phase 1 implementation (this session and the previous one, all uncommitted):**

- `hub/ui/package.json`, `hub/ui/package-lock.json` — added `@fontsource-variable/dm-sans` and
  `@fontsource/jetbrains-mono` (`^5.3.0`). Finished.
- `hub/ui/index.html` — removed both `fonts.googleapis.com` stylesheets and their preconnects.
  Finished.
- `hub/ui/src/index.css` — rewritten (114 → ~267 lines): font imports, full dark and light token
  sets, radius scale from one 10px base, motion scale, lift/press shadow tokens, 8-hue agent
  identity palette, overlay scrollbars, a global control base layer giving every un-migrated button
  a reserved transparent border, coarse-pointer targets, reduced-motion block. Finished.
- `hub/ui/tailwind.config.ts` — `fontFamily.sans` was `['Roboto', …]` for a font never loaded;
  now DM Sans Variable plus a `mono` family. Radius rewired to the new scale plus `content`.
  Added duration/easing tokens and a plugin providing `pointer-coarse` / `pointer-fine`
  (v4 variants unavailable on this project's Tailwind 3.4.17). Finished.
- `hub/ui/src/components/common/Icon.tsx` — reimplemented on `lucide-react` behind the existing
  `name` string API, 42-entry map, warns once per unknown name. Finished.
- `hub/ui/src/components/common/EmptyState.tsx` — renders `<Icon>` instead of an inline
  `material-symbols-rounded` span. Finished.
- `hub/ui/src/components/ui/button.tsx` — **new**. cva-based control primitive, 4 variants,
  7 sizes, implementing reserved border, border-compensated padding, press inversion, subordinate
  icons, coarse-pointer targets. Finished but **still unused by any call site**.
- `hub/ui/src/components/layout/PaneResizer.tsx` — **new**. 11px hit strip owning a 1px line;
  pointer drag with guarded pointer capture, keyboard resize (arrows, shift for larger step, Home
  to reset), double-click reset, `role="separator"` with `aria-value*`. Finished.
- `hub/ui/src/components/layout/Sidebar.tsx` — removed `background: var(--surface)` and
  `borderRight`; accepts a `width` prop; added `SIDEBAR_MIN_WIDTH` (180) and `SIDEBAR_MAX_WIDTH`
  (420) exports. Finished.
- `hub/ui/src/components/layout/SidebarItem.tsx` — `border: 'none'` (which overrode the global
  control base) replaced with a reserved `1px solid transparent`; hardcoded
  `rgba(255,255,255,0.04/0.06)` replaced with `var(--accent)`; motion scale applied; border colours
  in on highlight. Finished.
- `hub/ui/src/components/layout/StatusBar.tsx` — divider changed from `--border` to
  `--border-region`. Finished.
- `hub/ui/src/App.tsx` — owns `sidebarWidth` state, restored lazily from `localStorage` key
  `aw.sidebarWidth` so the first paint is already correct; renders `PaneResizer` between rail and
  content, suppressed on the Spec page where the rail is icon-only. Finished.
- `hub/ui/src/components/agents/AgentCard.tsx` — hardcoded `rgba(255,255,255,0.05)` → `var(--accent)`.
  Finished.
- `hub/ui/src/components/logs/LogLine.tsx` — same substitution on hover. Finished.
- `hub/ui/src/components/tasks/TaskCard.tsx` — hardcoded `0.15s` transition → motion scale. Finished.
- `hub/ui/src/__tests__/PaneResizer.test.tsx` — **new**, 7 cases. Finished.
- `hub/ui/src/__tests__/SidebarItem.test.tsx` — three assertions rewritten from literal
  `rgba(255,255,255,…)` to the `var(--accent)` token, plus two new cases asserting the reserved
  border. Finished.
- `hub/hub/static/ui/**` — regenerated from `hub/ui/dist`. Shows as one modified `index.html` and
  two deleted old asset files in `git status`.
- `openspec/changes/2026-07-30-hub-native-experience/**` — the specification. `tasks.md` updated:
  Phase 1 marked 17/18 done, and four new defects registered as tasks 3.20–3.22 (see below).
- `openspec/explorations/2026-07-31-future-directions.md` — parked ideas.

**Also written outside this repo:**
`AICollective/ResearchClub/spec-driven-development/spec-as-contract.md` (+ that folder's `README.md`).

**Pre-existing dirty work from a PREVIOUS session — NOT part of this work, preserve it:**
`hub/hub/api/v1/agent_trigger.py`, `agents.py`, `tasks.py`, `hub/hub/agent_status.py` (untracked),
`hub/tests/test_agents.py`, `hub/ui/src/lib/agentStatus.tsx`,
`hub/ui/src/components/spec/SpecChatPane.tsx`, `hub/ui/src/__tests__/agentStatus.test.tsx`,
`hub/ui/src/__tests__/specChatSession.test.tsx`, and four untracked handoff files.

## Key decisions

All 27 are in `tasks.md` §0; 12 full decisions with rejected alternatives are in `design.md`.
Decisions made *during this session's implementation*:

1. **Reimplement `Icon` behind its existing API rather than rewrite 24 call sites.** Same outcome,
   one file, no churn. *Rejected:* editing every call site to import lucide directly.
2. **A global CSS base layer for un-migrated buttons**, excluded via `:not([data-slot="button"])`.
   Every existing ad-hoc button gains the reserved-border and motion treatment without being
   touched. *Rejected:* migrating all buttons to the `Button` primitive first — churn against
   something the user had not yet seen.
3. **Do not blanket-fix the 12 remaining `border: 'none'` inline overrides.** Each adds 1px and
   could regress a layout the user has just approved. Only `SidebarItem` — the highest-traffic
   interactive surface — was fixed. The other 11 are listed under Next steps.
4. **The resizer owns the divider line, not the sidebar.** Gives one separation signal and free
   hover feedback. Sidebar background is transparent.
5. **Update tests to assert tokens, not literal colours.** The failing assertions encoded the
   light-mode bug being fixed.

## Constraints and user directives (verbatim)

- "After every threshold of implementation you must run the skill /handoff (this is not so we can
  clear and resume but if the tokens expire mid implementation I can just resume with another
  model)."
- "Before starting a new implementation revise the entire session for the spec."
- "I'm open to trying things other then the CLI (I'm not very attached to what was built already.
  If it's genuinely better to remake something and toss it out even if it's more work don't
  hesitate)."
- "let's make sure it works with claude and codex first locally" — Copilot second.
- "The block is in the github copilot that does not allow connections to 3rd party MCP" — the
  employer blocks third-party MCP **in GitHub Copilot only**; PyPI and general installs are
  unrestricted there.
- "the spec screen should be as good and nice as the agents one"
- "We don't need that withe square around the message queued user message." — queued state is
  opacity plus a chip, never a dashed border.
- Project `CLAUDE.md` rules still apply, including never committing `.agentweave/tasks/`,
  `messages/`, `agents/`, `session.json`, `transport.json`.

## Dead ends

- **`pointer-coarse:` as a Tailwind utility** — a v4 variant; this project is Tailwind 3.4.17, so it
  silently emits nothing. Fixed with an `addVariant` plugin, and the coarse-pointer target is
  *also* implemented directly in `index.css`, which is what actually covers un-migrated buttons.
- **`import.meta.env.DEV`** — fails `tsc` (`TS2339`); no `vite-env.d.ts` and no `types` entry in
  `tsconfig.json`. Replaced with a module-level `Set` warning once per unknown icon name.
- **`setPointerCapture` in jsdom** — unimplemented, threw during the double-click test. Now guarded
  in `PaneResizer`, which also makes real-browser behaviour degrade gracefully.
- **Asserting `btn.style.border` contains `'1px solid'`** — jsdom collapses the shorthand to
  `'1px transparent'` when `borderColor` is set separately. Assert `borderWidth` and `borderColor`.
- **Telling the user to look at the UI without rebuilding `hub/hub/static/ui/`** — cost a full
  round trip. The Hub served a bundle from 2026-07-20 and the work looked like it had not applied.

## Verification

**Ran and passed:**
- `npx tsc --noEmit` — clean.
- `npm run build` — clean, ~2.6s. Fonts bundled (10 `.woff2` in `dist/assets`).
- `npm test` — **21 files, 180 tests, 0 errors.**
- Served-output checks: `0` googleapis references and `0` material-symbols references in both the
  dev server and the rebuilt Hub static bundle.
- Auth flow end to end: Hub generates a key on first run → `GET /api/v1/setup/token` returns it →
  `Authorization: Bearer <key>` on `/api/v1/agents` returns **200**. (An earlier 401 was operator
  error — `X-API-Key` instead of Bearer.)
- Alembic migrations ran on Hub start from the source directory.
- **User visually confirmed** the result in a browser.

**NOT tested:**
- **Light mode has never been viewed.** Its palette was authored blind. Several fixes this session
  were specifically light-mode correctness (`--accent` replacing hardcoded white), all unverified.
- No formal pass against any `hub-interface-feel` or `hub-visual-language` scenario; verification
  was informal ("looks better"), not scenario-by-scenario.
- The `Button` primitive is untested and unrendered anywhere.
- Reduced-motion behaviour not verified in a browser.
- No Python tests run this session (`pytest hub/tests/` not executed).
- Drag-resize was verified by unit test and by the user's own use, not by an automated
  pointer-event integration test.

## Git state

- Branch `hub-native-experience`, **HEAD `eedbe46`**, no commits on this branch — everything
  uncommitted.
- 27 files changed, 624 insertions, 182 deletions vs HEAD, plus untracked `openspec/changes/…`,
  `openspec/explorations/…`, `hub/ui/src/components/ui/`, and handoff files.
- Git warns repeatedly that CRLF will be converted to LF on several touched files.
- No upstream for this branch; nothing pushed.

## Next steps

1. **Commit Phase 1**, keeping it separate from the preserved prior-session work. Stage explicitly —
   never `git add -A`:
   `git add hub/ui/index.html hub/ui/package.json hub/ui/package-lock.json hub/ui/tailwind.config.ts hub/ui/src/index.css hub/ui/src/App.tsx hub/ui/src/components/ui/ hub/ui/src/components/layout/PaneResizer.tsx hub/ui/src/components/layout/Sidebar.tsx hub/ui/src/components/layout/SidebarItem.tsx hub/ui/src/components/layout/StatusBar.tsx hub/ui/src/components/common/Icon.tsx hub/ui/src/components/common/EmptyState.tsx hub/ui/src/components/agents/AgentCard.tsx hub/ui/src/components/logs/LogLine.tsx hub/ui/src/components/tasks/TaskCard.tsx hub/ui/src/__tests__/PaneResizer.test.tsx hub/ui/src/__tests__/SidebarItem.test.tsx hub/hub/static/ui openspec/`
2. **View the app in light mode** and fix what the blind palette got wrong. Toggle via the mode
   control in `StatusBar`; the tokens are in `hub/ui/src/index.css` under `[data-mode="light"]`.
3. Begin **Phase 2 — Streaming replaces polling** (`tasks.md` §2). Start at task 2.1: inventory the
   9 `refetchInterval` call sites in `hub/ui/src/api/` against the 9 event kinds in
   `hub/ui/src/hooks/useSSE.ts` and record which entities have no event coverage.
4. Optionally clean up the 11 remaining inline `border: 'none'` overrides listed by
   `grep -rn "border: 'none'" hub/ui/src --include=*.tsx`, one file at a time with a visual check.

## Open questions for the user

- Whether the preserved prior-session work (agent heartbeat / spec-chat queued-start) should be
  committed, reverted, or left dirty. Unresolved across three sessions now.
- Whether Phase 1 should be merged to `master` before Phase 2 starts, since it is independently
  shippable.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — the plan; §0 has the 27 closed
  decisions and the ordering-revision table explaining why phases sit where they do.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — decisions with rejected
  alternatives; sections E–G hold the decoded T3 control-system mechanics.
- `hub/ui/src/index.css` — the token layer everything builds on.
- `hub/ui/src/components/ui/button.tsx` — the control system to propagate.
- `hub/ui/src/components/layout/PaneResizer.tsx` — the resizer pattern, reusable for the Spec
  workspace panes later.
- `.claude/handoffs/2026-07-31-2049-hub-native-phase1-feel-foundation.md` — the previous handoff.
