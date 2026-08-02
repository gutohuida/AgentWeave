# Handoff: Hub native experience — spec complete, Phase 1 feel foundation partially implemented

**Date:** 2026-07-31T20:49:41+01:00 · **Branch:** `hub-native-experience` · **HEAD:** `eedbe46`
**Agent:** Claude Code / Opus 5 (1M context)
**Previous handoff:** `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md`
**Status:** in progress — Phase 1 roughly half done, build and tests green

## Goal

Rebuild the AgentWeave Hub into a local-first application that owns agent execution directly,
using T3 Code as a *studied reference* rather than forking it. The user's complaint was that
AgentWeave is "clunky", "ugly and stale", and that connecting/triggering agents feels manual and
unreliable next to T3, Antigravity, and Kiro.

The *why*: every symptom was traced to a concrete cause, not taste. The Hub does not own the
execution boundary — it ships as a Docker container and therefore cannot spawn host agent CLIs, so
a 5-second polling watchdog exists as its host-side limb. The interface gaps are equally concrete
(fonts from a CDN, one CSS transition in the entire stylesheet, two icon systems).

The differentiating bet, decided this session: **requirement-level traceability** — the loop
requirement → task → diff → verified, in one place, self-hosted. Spec *authoring* is crowded
(Spec Kit, Kiro, Tessl); closing that loop is not.

## Current state

**The specification is complete and is the main artifact of this session.** Nothing is committed.

`openspec/changes/2026-07-30-hub-native-experience/` contains:
- `proposal.md`, `design.md` (12 numbered decisions with rejected alternatives), `tasks.md`
  (16 phases, 27 closed decisions), `mock.html` (a working interactive mock — open it in a
  browser; it is the visual reference for the two interface specs)
- 10 delta specs under `specs/`: `hub-native-runtime`, `hub-interface-feel`, `hub-visual-language`,
  `agent-inbound-queue`, `agent-conversation-timeline`, `agent-composer`, `agent-tool-surface`,
  `agent-identity-and-skills`, `spec-traceability`, `spec-authoring`
- **73 requirements, 204 scenarios total.**

**Phase 1 (Feel foundation) implementation status — tasks 1.1 through 1.12 substantially done:**

Done and verified building:
- Fonts self-hosted via `@fontsource` (DM Sans Variable + JetBrains Mono). Google Fonts links
  removed from `index.html`. Bundled `.woff2` confirmed in `dist/`.
- Icons migrated from Material Symbols to `lucide-react` **without touching the 24 call sites** —
  `Icon.tsx` was reimplemented behind its existing `name` string API with a 42-entry name→component
  map. `EmptyState.tsx` migrated off its inline Material Symbols span.
- Design tokens rewritten in `index.css`: one ground plane, `--border-region` lighter than
  `--border`, motion scale (`--dur-fast/base/slow`, `--ease`), radius scale from one base
  (10px, was 6px) with `sm/md/lg/xl` + `--radius-content: 24px`, lift/press shadow tokens, and an
  8-hue agent identity palette in both light and dark.
- Overlay scrollbars (no track, no steppers, inset handle via transparent border + content-box).
- `prefers-reduced-motion` block.
- `Button` primitive created at `hub/ui/src/components/ui/button.tsx` (cva-based, 4 variants,
  7 sizes) implementing reserved-transparent-border, border-compensated padding, press inversion,
  subordinate icons, coarse-pointer targets.
- A global base layer in `index.css` gives **every existing ad-hoc button** the reserved-border +
  motion + focus-ring treatment without editing 24 files, excluded via `:not([data-slot="button"])`.

**Not yet done in Phase 1:** tasks 1.13–1.17 — collapsing navigation and content onto one ground
plane in the actual layout components, restricting distinct fills to lifting surfaces, resizable
panes, and the verification pass. The `Button` primitive is created but **no call site uses it yet**.

## Files touched

**This session's Phase 1 work (all uncommitted):**

- `hub/ui/package.json` — added `@fontsource-variable/dm-sans` and `@fontsource/jetbrains-mono`
  (both `^5.3.0`). Finished.
- `hub/ui/package-lock.json` — lockfile for the above. Finished.
- `hub/ui/index.html` — removed both `fonts.googleapis.com` stylesheet links and the two
  `preconnect` hints; replaced with an explanatory comment. Finished.
- `hub/ui/src/index.css` — largely rewritten (117 → ~267 lines). Font imports, full token set for
  dark and light, radius/motion scale, scrollbar treatment, global button base layer,
  coarse-pointer targets, reduced-motion block. Finished for Phase 1's token scope.
- `hub/ui/tailwind.config.ts` — `fontFamily.sans` was `['Roboto', …]` for a font that was **never
  loaded**; now DM Sans Variable, plus a `mono` family. `borderRadius` rewired to the new scale
  plus `content`. Added `transitionDuration`/`transitionTimingFunction` tokens. Added a plugin
  providing `pointer-coarse` / `pointer-fine` variants. Finished.
- `hub/ui/src/components/common/Icon.tsx` — reimplemented on `lucide-react`; 42-name map;
  warns once per unknown name via a module-level `Set`; keeps `name`/`size`/`weight` API.
  Finished.
- `hub/ui/src/components/common/EmptyState.tsx` — now renders `<Icon>` instead of an inline
  `material-symbols-rounded` span. Finished.
- `hub/ui/src/components/ui/button.tsx` — **new file**, new directory. Finished, unused so far.
- `openspec/changes/2026-07-30-hub-native-experience/**` — **new**, the entire specification
  (proposal, design, tasks, mock.html, 10 delta specs). Complete.
- `openspec/explorations/2026-07-31-future-directions.md` — **new**; parks AgentWeave Colab,
  non-development agent packages, and the sandbox→provisioning-platform idea. Complete.

**Also written this session, outside this repo:**
- `C:\Users\huida\Documents\projects\AICollective\ResearchClub\spec-driven-development\spec-as-contract.md`
  — new research doc on spec-as-gate vs spec-as-documentation, rigor levels, both failure modes,
  and whether spec rigor substitutes for model capability. Indexed in that folder's `README.md`
  (also modified).

**Pre-existing dirty work from a PREVIOUS session — NOT mine, do not attribute or revert:**
The prior handoff records this explicitly: *"There is still unrelated dirty work in the tree
concerning agent heartbeat/stalled status and Spec chat queued-start behavior. Its origin and
disposition remain unresolved. Preserve it."*
- `hub/hub/api/v1/agent_trigger.py`, `hub/hub/api/v1/agents.py`, `hub/hub/api/v1/tasks.py`
- `hub/hub/agent_status.py` (untracked)
- `hub/tests/test_agents.py`
- `hub/ui/src/lib/agentStatus.tsx`, `hub/ui/src/components/spec/SpecChatPane.tsx`
- `hub/ui/src/__tests__/agentStatus.test.tsx`, `hub/ui/src/__tests__/specChatSession.test.tsx`
- `.claude/handoffs/LATEST.md` and four untracked handoff files

## Key decisions

All 27 are recorded in `tasks.md` §0 with reasoning; `design.md` carries 12 full decisions with
rejected alternatives. The ones that most affect implementation:

1. **Do not fork T3.** Upstream is a 244 MB alpha at ≥100 commits/week, v0.0.32, 923 open issues.
   Study it instead. Its full original source (577 files) was recovered from sourcemaps in the
   installed desktop build and extracted to `C:\Users\huida\t3src` — that extraction still exists
   and is re-creatable via `C:\Users\huida\extract_t3.py`. *Rejected:* forking (maintenance
   treadmill), and the research folder's own proxy-to-Hub plan (reintroduces a second runtime and
   makes onboarding worse than it is now).
2. **Keep the stack.** React + Radix + Tailwind + React Query + Zustand + FastAPI + SQLite stay.
   Every measured symptom is applied craft, not technology. *Rejected:* Effect-TS/typed RPC —
   months of migration fixing none of the six measured symptoms.
3. **The Hub runs natively; Docker becomes optional.** Verified empirically: `agentweave-hub`
   0.35.0 installs from PyPI into a clean venv and serves the full UI with no Docker
   (`/` 200, `/health` 200, `/api/v1/agents` 401). The only blocker is `cmd_hub_start`
   (`cli.py:3316`) calling `_docker_available()`. *Two defects found while testing:* `alembic.ini`
   is not in package-data so migrations silently skip; the server binds `0.0.0.0` and ignores the
   documented port variable.
4. **`uv tool install` is the distribution channel.** No npm — Python is the runtime, so an npm
   wrapper adds Node without removing Python.
5. **One uniform inbound queue per agent**, holding operator input and peer messages alike, with a
   typed origin. Turns start whenever the queue is non-empty and the agent is idle. Hop budget
   default **6**, drain cap default **10**. *Rejected:* adding a `channel` field to Message — keeps
   one table with two lifecycles and leaves the discriminator available to get wrong.
6. **One git worktree per writing agent, optimistic, no file locking.** In a shared directory there
   is no merge — only silent lost updates. *Rejected:* file/function locks — agents do not declare
   edit intent up front, and a lock serializes exactly the work being parallelized.
7. **MCP inverts.** The Hub pushes turn-start state in; the tool surface only carries intent out.
   ~9 of 24 tools survive. The two duplicate MCP servers collapse into one.
8. **Agent identity is injected by the Hub at spawn.** `cli.py:1519` currently reads
   `sender=args.from_agent or "unknown"` from an optional flag documented "Sender (any agent
   name)" — i.e. any agent can impersonate any other. Every governance requirement depends on
   fixing this.
9. **Personas are retired; charter + skills replace them.** `VALID_ROLE_IDS` (21 job titles) and
   `templates/roles/` are deleted. *Rejected:* pure skills with no charter — loses addressability,
   scope, and predictability.
10. **Requirement-level traceability is the product bet** (see Goal).
11. **Rigor is per document — sketch / contract / gate — defaulting to sketch.**

**Plan ordering was revised on 2026-07-31**; the revision table is at the top of `tasks.md`. Four
things moved (identity binding and worktree isolation ahead of the queue; crash recovery into the
runtime phase; approval gates after specs) and one missing phase was added (multi-project support).

## Constraints and user directives (verbatim)

- "After every threshold of implementation you must run the skill /handoff (this is not so we can
  clear and resume but if the tokens expire mid implementation I can just resume with another
  model)."
- "Before starting a new implementation revise the entire session for the spec."
- "I'm open to trying things other then the CLI (I'm not very attached to what was built already.
  If it's genuinely better to remake something and toss it out even if it's more work don't
  hesitate)."
- "let's make sure it works with claude and codex first locally" — Copilot support comes second.
- "The block is in the github copilot that does not allow connections to 3rd party MCP" — the
  user's employer blocks third-party MCP **in GitHub Copilot only**; PyPI and general installs are
  unrestricted on that machine. Command-based operation must stay first-class.
- "the spec screen should be as good and nice as the agents one"
- "We don't need that withe square around the message queued user message." — queued state is
  opacity + a chip, never a dashed border.
- "Also we should have something separating the left control panel. But I don't know why in your
  last version that separations felt heave" — resolved as: one separation signal, never two.
- Project `CLAUDE.md` rules still apply, including: never commit `.agentweave/tasks/`, `messages/`,
  `agents/`, `session.json`, `transport.json`; all task modifications use `with lock("name")`;
  templates via `get_template("name")`.

## Dead ends

- **`pointer-coarse:` as a Tailwind class** — that is a Tailwind v4 variant and this project is on
  v3.4.17. Silently produces no CSS. Fixed by adding an `addVariant` plugin in
  `tailwind.config.ts`; the coarse-pointer target is *also* implemented directly in `index.css`
  via `@media (pointer: coarse)`, which is what actually covers the un-migrated buttons.
- **`import.meta.env.DEV` in `Icon.tsx`** — fails `tsc` with
  `TS2339: Property 'env' does not exist on type 'ImportMeta'`; there is no `vite-env.d.ts` in this
  project and no `types` entry in `tsconfig.json`. Replaced with a module-level `Set` that warns
  once per unknown icon name.
- **Rewriting 24 files to swap icon libraries** — considered and rejected as unnecessary churn.
  Reimplementing `Icon` behind its existing `name` API achieves the same result in one file.

## Verification

**Ran and passed:**
- `npx tsc --noEmit` — clean, no output.
- `npm run build` — succeeds in ~2.6s. Fonts confirmed bundled: `dm-sans-latin-wght-normal-*.woff2`
  (36.93 kB), `jetbrains-mono-latin-{400,500}-normal-*.woff2`. CSS 49.49 kB (gzip 20.54 kB).
- `npm test` — **20 test files, 171 tests, all passing.** (Stack traces in the output are an
  intentional throw inside `ErrorBoundary.test.tsx`.)
- Earlier in the session: `pip install agentweave-hub` into a clean venv, then ran it — `/` 200,
  `/health` 200, `/api/v1/agents` 401. The venv and process were cleaned up afterwards.

**NOT tested:**
- **The UI has not been opened in a browser since these changes.** No visual confirmation that
  fonts render, that icons look right at their call sites, or that hover/press treatments read
  correctly. This is the single biggest gap.
- No verification that the 42-entry icon map produces *sensible* glyphs — only that every mapped
  lucide export exists.
- Light mode is untouched by any visual check.
- No Python-side tests were run this session (`pytest hub/tests/` not executed); the Python files
  in the tree are the previous session's work.
- No scenario in any of the 10 delta specs has been formally verified.

## Git state

- Branch `hub-native-experience`, created this session from `master` at `eedbe46`.
- **HEAD is `eedbe46`** — no commits made on this branch. Everything is uncommitted.
- Working tree dirty: 16 modified files, 8 untracked paths (see "Files touched" — note the split
  between this session's work and the preserved prior-session work).
- No upstream configured for this branch; nothing pushed.
- `git status` warns that `hub/ui/tailwind.config.ts` will have CRLF→LF converted.

## Next steps

1. **Open the Hub UI in a browser and look at it.** Run `cd hub/ui && npm run dev`, open
   `http://localhost:5173`. Confirm: DM Sans renders (not Segoe UI), icons appear at first paint,
   buttons gain a border on hover *without any layout shift*, and the scrollbar is an inset pill.
   This is task 1.17's verification and it has never been done.
2. Finish tasks **1.13–1.14** in `tasks.md`: in the layout components (`components/layout/Sidebar.tsx`,
   `StatusBar.tsx`, and `App.tsx`), remove the sidebar's distinct background fill and reduce its
   boundary to a single hairline using `var(--border-region)`. Distinct fills stay only on menus,
   popovers, dialogs, the composer, and content cards.
3. Task **1.15**: make the sidebar/content boundary draggable — target wider than the visible line,
   clamped 190–460px, persisted, double-click to reset. `--side-w` is already defined in
   `index.css`. `mock.html` has a working implementation to copy the mechanics from.
4. Migrate the most visible ad-hoc buttons to the new `Button` primitive
   (`components/ui/button.tsx`), starting with `components/layout/` and `components/agents/`.
5. Re-run `npx tsc --noEmit`, `npm run build`, `npm test`; then `/handoff` again.
6. Consider committing Phase 1 separately from the prior session's dirty work — use targeted
   `git add` of only the files listed under "This session's Phase 1 work", never `git add -A`.

## Open questions for the user

- Whether to commit Phase 1 now, and whether the preserved prior-session work (agent heartbeat /
  spec chat queued-start) should be committed, reverted, or left dirty. The previous handoff left
  its disposition unresolved and it is now two sessions old.
- Light-mode palette values were authored but never reviewed by eye.

## Read on resume

- `openspec/changes/2026-07-30-hub-native-experience/tasks.md` — the plan; §0 has all 27 closed
  decisions, and the ordering-revision table explains why phases sit where they do.
- `openspec/changes/2026-07-30-hub-native-experience/design.md` — the 12 decisions with reasoning
  and rejected alternatives; sections E–G contain the decoded T3 control-system mechanics so
  implementation never needs to open T3 again.
- `openspec/changes/2026-07-30-hub-native-experience/mock.html` — open in a browser; the live
  visual reference for `hub-visual-language` and `hub-interface-feel`.
- `hub/ui/src/index.css` — the token layer everything else builds on.
- `hub/ui/src/components/ui/button.tsx` — the control system, currently unused; the pattern to
  propagate.
- `.claude/handoffs/2026-07-30-1912-spec-navigation-closed-r1-audit-next.md` — the prior handoff,
  for the provenance of the preserved dirty work.
