# Tasks

Implementation MUST NOT begin until the proposal is approved.

Ordering is deliberate: the token ramp lands first because every later phase is verified against it,
and de-tokenised colour is removed before the ramp swap so no component silently keeps the old
palette.

## 1. Token ramp

- [x] 1.1 Replace the dark ramp in `hub/ui/src/index.css` with the neutral graphite values in
      `design.md` (`--bg`, `--rail`, `--top`, `--surface`, `--surface-2`, `--surface-3`).
- [x] 1.2 Replace the light ramp with its neutral counterpart from `design.md`.
- [x] 1.3 Make `--primary` / `--primary-foreground` monochrome in both modes; verify
      `--primary-hover` and `--primary-active` still read as distinct steps.
- [x] 1.4 Add `--rail-marker`, resolving to the mode's accent, and confirm `--ring` keeps the accent
      hue in both modes.
- [x] 1.5 Confirm the derived tokens (`--border*`, `--text*`, `--row-*`, `--lift-hi`, `--press-lo`,
      `--accent`) still resolve to usable values against the new ramp; re-author only those that do
      not. (All are alpha-over-ground or color-mix formulas — none needed re-authoring.)
- [x] 1.6 Verify every token is defined in both `[data-mode="light"]` and dark.

## 2. Remove de-tokenised colour

- [x] 2.1 Move `Badge.tsx`'s hardcoded status palette onto semantic tokens, preserving each status's
      current meaning and distinguishability.
- [x] 2.2 Move the remaining raw hex and `rgba()` literals in `hub/ui/src/components` onto tokens.
      Legitimate non-colour `rgba()` (shadows, scrims) may remain where a token already expresses it.
      (41 rgba() literals converted via `color-mix()`; genuine box-shadow rgba(0,0,0,…) left as-is;
      full-black dialog overlays converted to `var(--scrim)`.)
- [x] 2.3 Add a source contract asserting no component declares a raw hex colour, following the
      `hubVisualLanguage.test.ts` `readFileSync` pattern. (One exemption: `SetupModal.tsx`'s
      light/dark mode-preview swatches, which must stay fixed regardless of the active mode.)

## 3. Remove the inert theme system

- [x] 3.1 Remove the theme picker from `SetupModal.tsx`.
- [x] 3.2 Remove `ThemeId`, `theme`, and `setTheme` from `configStore.ts` and its persisted shape,
      leaving previously persisted values ignored rather than failing to load.
- [x] 3.3 Remove the `data-theme` attribute write from application startup. `SpecFrame.tsx` writes
      `data-theme` into *spec documents*, which have their own `:root[data-theme]` layer — left
      untouched. Also removed the dead `data-theme="cosmic"` default baked into `hub/ui/index.html`'s
      `<html>` tag, found during live verification (harmless — no CSS rule read it — but dead markup
      from the same removed system).
- [x] 3.4 Add a source contract asserting the application no longer writes `data-theme` to its own
      document.

## 4. Composer column

- [x] 4.1 Change `Composer.tsx` from a flex row to a column: text area on row one at full width.
- [x] 4.2 Add the control row with a leading slot and a trailing slot; place
      `ComposerAgentSelector` in the leading slot and send in the trailing slot.
- [x] 4.3 Restyle `ComposerAgentSelector` for the control row and confirm its popover still opens
      upward without being clipped by the composer surface.
- [x] 4.4 Confirm autogrow, `COMPOSER_MAX_HEIGHT_PX`, draft persistence, Enter-to-send, and the
      trigger menu's positioning are unchanged. (Unaffected — trigger menu positions against the
      textarea's own containing block, which survives row-to-column.)
- [x] 4.5 Add a test asserting the text area's left edge is inset from the composer surface by
      padding alone, with no control preceding it.

## 5. Rail active marker

- [x] 5.1 Remove the resting fill from `.row-item[data-active="true"]` in `index.css`.
- [x] 5.2 Add the leading marker, occupying layout at rest for every row and coloured only when
      active. (Implemented as a 2px `border-left`, always reserved at rest — the same
      "transparent border reserved at rest" principle the Button primitive uses.)
- [x] 5.3 Strengthen the active row's label treatment to carry the state that the fill carried.
      (Already `color: var(--text); font-weight: 550` — unchanged, matches design.md exactly.)
- [x] 5.4 Confirm the hover and press fills still apply to the active row.
- [x] 5.5 Confirm `projectRail.test.tsx` still passes — `data-active` and `aria-current` are
      unchanged by this change.

## 6. Project header

- [x] 6.1 Remove the fill and the bottom rule from `ProjectHeader.tsx`.
- [x] 6.2 Present the directory as path segments with middle elision, keeping the agent count.
- [x] 6.3 Expose the complete path from the header without navigation. (Via `title` on the segment
      span.)
- [x] 6.4 Confirm the unavailable-directory state still reports through `role="status"`.

## 7. Execution-order work blocks

- [x] 7.1 Replace `TurnBody`'s work/rest partition with an ordered reduction into blocks, opening a
      new work block on the first work entry following a non-work entry.
- [x] 7.2 Key each block's disclosure state independently.
- [x] 7.3 Compute `findPairedResult` within a block rather than across the turn.
- [x] 7.4 Compute each block's duration from its own first and last entry.
- [x] 7.5 Add tests: interleaved turn produces blocks in execution order; consecutive work collapses
      to one block; a work-only turn is unchanged; blocks expand independently; pairing does not
      cross blocks.

## 8. Verification

- [x] 8.1 `npm test` in `hub/ui`. (393 passed, up from 378 — 15 new tests.)
- [x] 8.2 `npx tsc --noEmit` in `hub/ui`. (Clean after removing 6 stale `theme:` fields from test
      `setState` calls that predated the configStore shape change.)
- [x] 8.3 `pytest hub/tests -q` — expected unchanged; this change touches no backend. (602 passed, 8
      skipped — identical to baseline.)
- [x] 8.4 `npm run build`, then refresh and commit `hub/hub/static/ui`.
- [x] 8.5 `pytest hub/tests/test_ui_staleness.py -q`. (5 passed.)
- [x] 8.6 `openspec validate 2026-08-04-hub-charcoal-visual-refresh --strict`. (Valid.)
- [x] 8.7 Live check in both modes against a real project (`proj-b9c0eebb`) at 1280×800: confirmed
      light ramp (`--bg:#fafafa`), dark ramp (`--bg:#0a0a0b`, `--rail:#101012`, `--primary:#fafafa`);
      composer textarea starts 13px from the surface edge (was 132px) at full width, control row
      renders below it; rail active row has transparent background + accent-coloured left border;
      project header has zero border-bottom and matches the ground plane exactly; a real turn
      rendered 2 independently-collapsible work blocks. 390×800 narrow-viewport pass not run
      (background-automation session had no interactive resize control available this session).
- [ ] 8.8 **Live keyboard pass through the composer control row.** *Partially verified 2026-08-10;
      the live half is still yours.*
      **Verified by the agent:** in the running Hub, the composer's tab order from the text area is
      `textarea → Model → Effort → Permissions`, all four with `tabIndex 0`, and the stylesheet does
      define `:focus-visible` treatments. The chat pane holds 12 focusable elements in total.
      **Do this:** click the message text area on any conversation, then press Tab four times, then
      Shift+Tab four times.
      **Expect:** focus lands on Model, Effort, then Permissions, each with a visible ring; Shift+Tab
      retraces the same path back to the text area; Enter or Space opens the focused pill's menu and
      Escape closes it, returning focus to the pill.
      **It failed if:** any pill is skipped, shows no visible ring, opens its menu without returning
      focus on Escape, or the order differs between Tab and Shift+Tab.
      *The agent cannot run this: the available automation's key press does not move real focus —
      re-tested 2026-08-10 with `Tab` from a focused text area, and `document.activeElement` did not
      change. Dispatching a synthetic `keydown` does not drive the browser's own focus engine.*

- [x] 8.9 **Contrast check: text and semantic colours against the new ramp, both modes.**
      **Run 2026-08-10.** The earlier "no automated contrast-checking tool available" is no longer
      true — WCAG 2.1 relative luminance is arithmetic, and it was computed directly from the token
      values in `index.css`, then cross-checked against 54 live rendered elements on the running Hub
      (28 failing, all of them one token).

      Ratios, AA thresholds 4.5 for normal text and 3.0 for large text and non-text UI:

      | | `--bg` | `--surface` | `--surface-2` | `--surface-3` |
      |---|---|---|---|---|
      | **dark** `--text` | 18.16 | 16.73 | 15.42 | 13.82 |
      | dark `--text-2` | 6.10 | 5.62 | 5.18 | 4.64 |
      | dark **`--text-3`** | **2.99** | **2.76** | **2.54** | **2.28** |
      | dark `--green` / `--amber` / `--blue` | 9.91 / 11.33 / 6.65 | 9.13 / 10.44 / 6.12 | 8.42 / 9.62 / 5.64 | 7.54 / 8.62 / 5.06 |
      | dark `--red` / `--purple` | 5.86 / 5.00 | 5.40 / 4.61 | 4.98 / 4.25 | 4.46 / 3.81 |
      | **light** `--text` | 16.97 | 17.72 | 16.12 | 14.62 |
      | light `--text-2` | 6.33 | 6.61 | 6.01 | 5.45 |
      | light **`--text-3`** | **3.11** | **3.24** | **2.95** | **2.68** |
      | light **`--green`** | **3.21** | **3.35** | **3.05** | **2.76** |
      | light **`--amber`** | **3.15** | **3.28** | **2.99** | **2.71** |
      | light `--red` / `--blue` / `--purple` | 4.46 / 4.89 / 5.35 | 4.65 / 5.10 / 5.59 | 4.23 / 4.64 / 5.08 | 3.84 / 4.21 / 4.61 |

      **Result: the check ran and the ramp does not pass.** `--text` and `--text-2` clear AA
      comfortably in both modes, and the accent (`--ring`, which resolves to `--blue`) clears the
      3.0 non-text bar everywhere. `--text-3` fails AA for normal text on **every** surface in
      **both** modes, and it is not decorative — timestamps, the session-continuity line, composer
      placeholders, status labels, and secondary metadata all use it. In light mode `--green` and
      `--amber` also fall below 4.5, and below 3.0 on `--surface-3`.

      **The remediation is a design decision, not a defect fix — see 8.11.**

- [ ] 8.10 **Reduced-motion check.** *Still unrunnable by the agent; re-confirmed 2026-08-10.*
      **Do this:** turn on Windows → Settings → Accessibility → Visual effects → Animation effects
      **off**, reload the Hub, then: resize a pane, collapse and expand the chat pane, open and close
      a compact drawer, and switch conversations.
      **Expect:** each of those changes state instantly, with no fade, slide, or width animation; and
      every state stays distinguishable without the motion — a collapsed pane still reads as
      collapsed, an open drawer still reads as open.
      **It failed if:** anything still animates, or a state that was only legible *because* it moved
      becomes ambiguous once it does not.
      *The agent cannot run this: `preview_set_appearance` emulates `prefers-color-scheme` only, and
      a CSS media query cannot be forced from page JavaScript.*

- [ ] 8.11 **DECISION (operator): what contrast bar does 1.0 hold itself to?** Raised by 8.9.
      Meeting **AA 4.5** for `--text-3` needs `#5c5c66 → #8c8c96` (dark) and `#8e8e98 → #686872`
      (light). Note what that costs: `#8c8c96` is within one step of today's `--text-2` (`#8e8e98`),
      so **AA at 4.5 collapses the three-level neutral text ramp into two.** The ramp is the thing
      the charcoal refresh was for.
      Meeting **3.0** — the bar for large text and non-text UI, and where many design systems put
      incidental text — needs only `#5c5c66 → #6f6f79` (dark) and `#8e8e98 → #85858f` (light), which
      preserves three distinct levels. Light-mode `--green → #0f9963` and `--amber → #bb760d` would
      clear 3.0 on every surface.
      Three options: hold AA 4.5 and lose the third level; hold 3.0 and keep it; or keep today's
      values and record the exemption deliberately. This is a look-and-feel call and it is yours —
      the operator chose this ramp, and no agent should quietly relight the product overnight.

**Note (found during 8.7):** `getComputedStyle` on `background-color` read a stale mid-transition
value while the browser tab was backgrounded (`preview_open` with `open:false`) — Chrome throttles
CSS transitions in hidden tabs. Confirmed as a tooling artifact, not an app defect, by forcing
`transition:none` and re-reading. Worth remembering for any future live check run against a
background tab.
