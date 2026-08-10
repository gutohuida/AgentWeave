# Handoff: the spec and the tab strip stop announcing themselves; the branch is pushed at last

**Date:** 2026-08-10T15:38+01:00 · **Branch:** hub-native-experience · **HEAD:** `b2bc346`
**Agent:** Claude Opus 5 (1M context) (Claude Code)
**Previous handoff:** `.claude/handoffs/handoff-0028-2026-08-10-1500-spec-surfaces-iterated-live.md`
**Status:** **chunk complete.** *"This is really good. I think my testing is done."* Two commits,
working tree clean, **branch pushed — 0 unpushed for the first time in this chain.**

## Goal

Handoff 0028 ended mid-flight: the operator was still testing the spec surfaces and had said
there were "minor changes" outstanding without naming them. This session asked, got three
concrete reports, and fixed all three. The through-line in all of them is one idea worth
carrying: **a surface that paints its own plane declares itself a separate region, and it should
only do that if it actually is one.**

Their testing is now closed. The next target has **not been named.**

## Current state

All three reports fixed, verified live in both light and dark, committed, and pushed.

### 1. The tab strip (`28c17c3`)

*"The color on the overview, task, spec, jobs, activity tabs is different then the rest of the
screen. It popes up in a bad way."*

`ProjectTabs.tsx` painted `background: var(--top)`. `--top` turned out to be defined in the
palette for **that one element and nothing else** — grep found no other consumer. In light mode
it was `#ffffff` against a `#fafafa` page, so the strip read as a band laid over the screen.

The strip now paints nothing and sits on `--bg` with everything else; the active tab's own fill
already marks position. `--top` is **deleted from both palettes**, not left unreferenced.

### 2. The scrollbar (`28c17c3`)

*"The scroll wheel on the spec in light mode is dark."*

Not a colour bug — a `color-scheme` bug, and the most transferable thing in this session.
The spec document declares `color-scheme: light dark`, which tells the browser *"this page
handles both, you choose"* — and the browser chooses from the **OS**, not from the Hub. The
operator's OS is dark, so a light Hub still got a dark scrollbar. `data-theme` has no influence
on UA chrome whatsoever.

Inside the frame the mode is not a preference to be honoured, it is already decided, so the
embedding pins `color-scheme` to the Hub's active mode.

### 3. The spec background — fixed twice, and the first fix was wrong (`28c17c3`, then `b2bc346`)

First ask: *"Can you make the background of the spec the same color as the composer background?"*
→ pointed the document at `--surface`.

That was **the wrong target**, and the operator caught it: *"In dark mode the spec background
still looks gray in comparison and in light mode it looks white. Can you see that where the spec
lives doesn't blend well?"*

On the Spec screen **there is no composer**. Measuring the frame's ancestor chain settled it —
every ancestor paints `--bg`. The document is not a card sitting in a region, it **is** the
region, so any lift colour could only read as a slab over the page.

**The ground alone could not move.** The conventions' own `--surface` is `#f6f7f9`, which is
*darker* than the Hub's light `--bg` of `#fafafa` — re-grounding without remapping the rest
would have inverted every lifted block, sinking notes and code instead of lifting them. So the
whole neutral ramp moves together: `--bg`, `--surface`, `--surface-2`, `--border`, `--fg`,
`--muted`. A side effect is that the document leaves its blue-tinted grey for the Hub's neutral
graphite, which is why the `.note` block had looked slightly off-hue.

`--accent`, `--warn`, `--done`, `--danger` are **deliberately not remapped** — they carry meaning
inside the specification. A test asserts the override never names them.

**The fix is retroactive.** Already-generated `spec.html` files in user projects still carry the
old `color-scheme` and ramp, but the Hub rewrites both at render time, so every existing spec
renders correctly with no regeneration. Only opening an old file *standalone, outside the Hub*
keeps the original bug — which is why the conventions file was fixed too.

## Files touched

All committed and pushed; `git status --short` is empty.

| path | what | done? |
|---|---|---|
| `hub/ui/src/components/layout/ProjectTabs.tsx` | dropped `background: var(--top)`; comment recording why | yes |
| `hub/ui/src/index.css` | `--top` removed from the dark block and the light block | yes |
| `hub/ui/src/components/spec/SpecFrame.tsx` | `HUB_NEUTRALS` (replaces the earlier `HUB_SURFACE`), `themeOverride()`, injection in `withHubTheme`, iframe element back to `var(--bg)` | yes |
| `hub/ui/src/__tests__/hubVisualLanguage.test.ts` | `--top` assertions removed + a `not.toMatch(/--top:/)` guard; tab-strip contract rewritten; `SpecFrame.tsx` added to `HEX_EXEMPT`; new 5-test describe block | yes |
| `src/agentweave/templates/skills/references/html-spec-conventions.md` | `color-scheme` resolved per `data-theme`; prose on the Hub's neutral remap | yes |
| `hub/hub/static/ui/**` | rebuilt artefact, refreshed on both commits | yes |

**Product code outside the UI:** only `html-spec-conventions.md`, as in the previous session. It
ships to users and every generated spec is written from it.

## Key decisions

1. **`--top` deleted, not orphaned.** A palette entry with no consumer is a colour waiting to be
   reintroduced by accident.
2. **The neutral ramp moves as a unit.** Rejected: moving only `--bg`. That inverts the lift
   relationship in light mode, because the document's `--surface` is darker than the Hub's `--bg`.
3. **Only neutrals are remapped.** Rejected: mapping the full palette. The chromatic tokens are
   the specification's own semantics, not the Hub's to restyle.
4. **The literal hexes in `SpecFrame.tsx` are pinned by a test, not waived.** The frame is
   sandboxed onto an opaque origin, so `var(--surface)` cannot cross into it and the values must
   travel as literals. `hubVisualLanguage.test.ts` asserts each one still matches `index.css`,
   which is the house pattern from `CLAUDE.md` for `mcp_server.py`'s restated constants. Only
   *then* was `SpecFrame.tsx` added to `HEX_EXEMPT`.
5. **The override is `!important`, not source-ordered.** The conventions' `:root[data-theme=…]`
   outranks a bare `:root`, and where the injected `<style>` lands relative to it varies.
6. **The override is appended, never prepended.** A `<style>` ahead of `<!DOCTYPE html>` drops the
   document into quirks mode. Asserted by a test.
7. **The override is stripped before being re-added**, so re-theming does not stack stylesheets.
   Verified live across a real theme toggle: count stayed 1 and the values flipped.

## Constraints and user directives (verbatim)

**From this session:**
- *"The color on the overview, task, spec, jobs, activity tabs is different then the rest of the
  screen. It popes up in a bad way... Make it the same color, it looks weird."*
- *"The scroll wheel on the spec in light mode is dark."*
- *"Can you make the background of the spec the same color as the composer background?"*
- *"In dark mode the spec background still looks gray in comparison and in light mode it looks
  white. Can you see that where the spc lives doesn't blend well?"* — **the standing lesson:
  match a surface to the region it occupies, not to a component it merely sits near. Measure the
  ancestor chain before choosing a token.**
- *"This is really good. I think my testing is done."*
- Chose **"Push, then handoff"** over handoff-only.
- Chose **"Leave it — decide next session"** on the CI trigger.

**Carried and still binding:**
- **Handoff cadence:** only when asked, or when an openspec change is done. This one was asked for.
- **STANDING DIRECTIVE:** every change's `tasks.md` splits agent-verifiable from human-only and
  emits a user test guide.
- *"Kind of lost"* / *"What is taking so long?"* — sensitive to volume and to wall-clock.
- *"The spec should still be generated as html"*; *"no need for backups everything is test env"*;
  *"first I think we have to many we need to cut some of those"* (the 21 charters);
  *"the charter exists to give instructions so I can use agentweave for more then developing."*
- *"by measuring pixels aren't you making things a little bit too catered to my monitor?"* — a
  measured constant is still a constant. Derive it, or express it in the same unit as the thing
  it guards.
- From `CLAUDE.md`: never `.agentweave/` / `agentweave.yml` / `spec/` at the repo root; stage
  paths explicitly; openspec never aw-spec skills; `Icon` is the only icon system;
  `approve_tool_call` keeps **no return annotation**; `hub/hub/static/ui` refreshed after
  `npm run build` and confirmed with `diff -rq`; never mark a task complete on the strength of a
  plan existing.
- From memory: commit each completed checkpoint without asking; live-verify on resume.

## Dead ends

**New this session:**
- **`git push` does NOT trigger CI on this branch.** `.github/workflows/ci.yml` triggers only on
  `push: branches: [master]` and `pull_request: branches: [master]`. Pushing
  `hub-native-experience` ran nothing — `gh run list --branch hub-native-experience` is empty.
  A **draft PR to master** would trigger the full matrix without editing any workflow; the
  operator deferred that decision.
- **PowerShell here-strings (`@'…'@`) mangle a commit message in the Bash tool.** The subject
  became `@ Let the tab strip…` and the body was executed as shell. Recovered with
  `git commit --amend -F <file>`. **Write the message with the Write tool and use `-F`.**
- **`cp -r dist/* ../hub/static/ui/` merges rather than replaces** — two stale hashed assets
  survived and `diff -rq` failed. Must `rm -rf` the destination first.
- **A blunt source assertion matches your own prose.** `not.toMatch(/background/)` on
  `ProjectTabs.tsx` failed against the comment explaining the removal. Scope it:
  `not.toMatch(/style=\{\{[^}]*background/)`.
- **The raw-hex contract scans comments too.** Writing `#ffffff` in a comment in
  `src/components/**/*.tsx` fails `declares no raw hex colour…`. Describe colours in words there.
- **`data-theme` has no effect on UA chrome.** Scrollbars and form controls follow `color-scheme`
  only, and `color-scheme: light dark` defers to the OS.

**Carried and still true:**
- **Measure the real input.** The frame renders `srcdoc`, *after* `withHubTheme` and
  `withSpecBridge`. Take `frame.getAttribute('srcdoc')` and render it in a **same-origin probe
  iframe** (no `sandbox`) — the only way to measure inside it. Used repeatedly this session and it
  worked every time.
- **`requestAnimationFrame` never fires and `ResizeObserver` never delivers in the automation
  tab.** Reach each width by reloading into it.
- **`preview_snapshot` returns ~25k tokens and truncates**, and has been failing outright.
  `preview_evaluate` answered everything this session. **`preview_press` and `preview_resize` do
  not work**; prefer `element.click()` over `preview_click`.
- **`preview_evaluate` must return an object**, not a bare array.
- **`ch` against a `px` breakpoint is a silent trap**, as is `rem` against a media-query `em`.
- **`cd hub/ui` first** — `npx vitest` from the repo root resolves a different project.
- **`npm run lint` does not work at all**; `tsc --noEmit` is the check.
- **`pytest hub/tests/ tests/` together fails collection** — run separately. **The default
  `python` has no pytest** — use
  `C:\Users\huida\AppData\Local\Programs\Python\Python311\python.exe`.
- **The spec API is `/api/v1/projects/{id}/project/specs`**; the Hub rejects `X-API-Key` — use
  `Authorization: Bearer`.

## Verification

**Ran this session, with real output:**
- `pytest hub/tests/ -q` — **1280 passed, 10 skipped** (twice: once on resume to convert handoff
  0028's *inference* into a measurement, once at the end).
- `pytest tests/ -q` — **372 passed, 3 skipped.**
- `npx vitest run` — **75 files, 703 passed** (was 697).
- `npx tsc --noEmit` — clean.
- `npx openspec validate --specs --strict` — **27 passed, 0 failed.**
- `npm run build` + `rm -rf` + copy + `diff -rq` — identical, on both commits.
- **Live in both modes, via same-origin probe:** container `rgba(0,0,0,0)` over `--bg`; document
  body `#0a0a0b` dark / `#fafafa` light — **equal to its container**; `.note` lifting to `#151518`
  / `#ffffff`; text on `#f5f5f6` / `#18181b`; `color-scheme` resolving to a single mode;
  `compatMode: CSS1Compat`; doctype still at index 0; override count 1 across a real theme toggle.
- Tab strip live: `backgroundColor` now `rgba(0, 0, 0, 0)` in both modes.

**Not verified, and deliberately:**
- **CI has still never run on this branch** — now **350 commits ahead of master**. No Linux, no
  macOS, no Python 3.8–3.12. Everything above is Windows, one Python, one browser. Pushing did not
  change this (see Dead ends).
- **No screenshot taken by the agent since `4a0bdb0`** — `preview_snapshot` is unreliable. All
  visual claims this session are numeric measurements. The operator, however, *did* look, twice,
  and signed off: *"This is really good."*
- The five human-only items (7.1–7.5) of the closed `2026-08-10-conversation-first-spec-workspace`
  change remain formally unrun, though the operator's own testing has now covered these surfaces
  substantially.

## Git state

Branch `hub-native-experience`, HEAD **`b2bc346`**, working tree **clean**, **0 unpushed** (the
branch now tracks `origin/hub-native-experience`), **350 commits ahead of master**.

## Next steps

1. **Ask the operator to name the next target.** They closed this one with *"can we wrap this and
   move to the next target?"* and did not say what it is. Do not pick one from the backlog and
   start — nothing below is agreed work.
2. **If they want CI signal:** open a **draft PR from `hub-native-experience` to `master`**. That
   triggers `ci.yml`'s `pull_request` matrix (3 OSes × 5 Pythons) with no workflow edit, and
   closing it reverts nothing. This is the single largest unknown in the branch.
3. **Optional, offered and not taken:** record this session's two decisions (the `color-scheme`
   resolution and the region-grounding) as an amendment in
   `openspec/changes/2026-08-10-conversation-first-spec-workspace/tasks.md`. They currently live
   only in commit messages and code comments.
4. Then the human-only checks 7.1–7.5, rewritten for the surfaces as they now are.

## Open questions for the user

1. **What is the next target?** Blocking next-step 1.
2. **The `ci.yml` branch trigger** — deferred again this session; **now raised seven times.**
3. **The contrast bar for 1.0** — AA 4.5, 3.0, or a recorded exemption. Blocks archiving the
   charcoal change (8.11).
4. **How many charters, and which non-software domains?** Still blocks B0.
5. **The agent-settings round trip loses the open document** — the settings destination has no
   `document` field. Worth adding, or leave it?
6. Carried: should `.claude/handoffs/` stay tracked (**now 116 files, confirmed not gitignored**);
   the two model-less runners on `proj-cddb0827`; `testbed/CHECKPOINT-TEST-GUIDE.md` names the old
   project.

## Read on resume

- **This file's section 3 and the `color-scheme` explanation in section 2** — the two standing
  lessons, not details.
- `hub/ui/src/components/spec/SpecFrame.tsx` — `HUB_NEUTRALS` and `themeOverride()` carry the most
  reasoning per line of anything written this session.
- `src/agentweave/templates/skills/references/html-spec-conventions.md` — the only shipped non-UI
  file touched, and what every generated spec is written from.
- `hub/ui/src/__tests__/hubVisualLanguage.test.ts` — the palette contracts, including the
  hex-exemption rationale and the lift-relationship assertion.
- `.github/workflows/ci.yml` — 8 lines, and the reason the branch has no CI.
- `openspec/changes/2026-08-10-conversation-first-spec-workspace/tasks.md` — the closed change
  these surfaces came from, plus the amendment recording the reversed decisions.
