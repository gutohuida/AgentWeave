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
- [ ] 8.8 Live keyboard pass: the composer control row is reachable and shows focus. Not run —
      deferred; unit coverage already exercises the control row's DOM structure and the two controls'
      accessible roles, but not a live Tab-key traversal.
- [ ] 8.9 Contrast check: text, primary controls, and the accent ring against the new ramp in both
      modes. Not run — no automated contrast-checking tool available this session; the ramp values
      were chosen for headroom per design.md but a numeric contrast ratio check is still open.
- [ ] 8.10 Reduced-motion check — carried forward as unavailable through current tooling
      (`preview_set_appearance` emulates `prefers-color-scheme` only). Still unresolved.

**Note (found during 8.7):** `getComputedStyle` on `background-color` read a stale mid-transition
value while the browser tab was backgrounded (`preview_open` with `open:false`) — Chrome throttles
CSS transitions in hidden tabs. Confirmed as a tooling artifact, not an app defect, by forcing
`transition:none` and re-reading. Worth remembering for any future live check run against a
background tab.
