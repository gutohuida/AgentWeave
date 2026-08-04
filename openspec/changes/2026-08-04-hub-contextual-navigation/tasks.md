# Tasks

Implementation MUST NOT begin until the proposal is approved.

Ordering is deliberate: tokens and the control primitive land first, because every later phase
depends on them and doing them last would mean restyling the same components twice.

## 1. Interaction foundation

- [x] 1.1 Add `--row-hover`, `--row-active`, `--row-selected` to `hub/ui/src/index.css` for both
      `[data-mode="light"]` and dark, following the T3 ratios recorded in `design.md`.
- [x] 1.2 Extend the global control baseline in `index.css` so a control with no explicit treatment
      still gains a hover fill, rather than only reserving a transparent border.
- [x] 1.3 Add a shared row treatment (hover / pressed / `data-active` selected) usable by the rail,
      the section list, project tabs, and list rows.
- [x] 1.4 Suppress `::-webkit-inner-spin-button`, `::-webkit-outer-spin-button`, and Firefox's
      spinner on `input[type=number]`, globally.
- [x] 1.5 Add a group-hover reveal utility for row-level secondary actions that occupies layout at
      rest.
- [x] 1.6 Verify every new token is defined in both themes.

## 2. Adopt the control primitive

- [x] 2.1 Replace the inline-styled buttons in `Sidebar`, `ProjectHeader`, `ProjectTabs`, and the
      `App.tsx` navigation with `components/ui/button.tsx` variants.
- [x] 2.2 Replace them in `ConversationControls`, `AgentTimeline`, and `Composer`. (`AgentTimeline`
      uses the `.fold-control`/`.work-disclosure` row-treatment classes rather than the `Button`
      primitive — its controls are a `<summary>` and dashed-outline pills, not buttons in the
      primitive's sense; this is the row-treatment alternative the primitive was designed alongside.)
- [x] 2.3 Replace them across the eight environment panels.
- [x] 2.4 Audit the remaining Hub UI for activatable elements outside the shell, conversation, and
      environment screens; adopt the shared control or row treatment anywhere that still lacks the
      required resting, hover, pressed, selected, or focus states. Fixed in
      `OverviewPage`, `AgentCreateDialog`, `TasksBoard`, `SpecPage`, `SpecChatPane`, `SetupModal`,
      `ComposerAgentSelector`, `JobCard`, `JobsPage`, `JobForm`, `SpecWorkspace`, `SpecNavigator`,
      `LogsView`, `QuestionInterruptCard`, and `ErrorBoundary` — every genuinely inert control found
      (a `<button>` pinning its own `background` via inline `style`, which blocks the CSS `:hover`
      rule regardless of specificity). `AgentsPage`, `AgentCard`, `AgentDetailPanel`,
      `AgentActivityTab`, `StatusBar`, `MessagesFeed`, and `MessageCard` were confirmed unreachable
      from `App.tsx` (no live import path) and were left as-is — dead code, not a user-facing defect.
      `AgentInfoTab` and `AgentTimeline` were checked and already met the bar (no inline-pinned
      background on their controls).
- [x] 2.5 Add a source contract asserting that shell components use the primitive rather than
      hand-rolled `<button style={…}>`, following the `hubVisualLanguage.test.ts` `readFileSync`
      pattern.

## 3. Contextual rail

- [x] 3.1 Give `Sidebar` a mode derived from the active destination: project mode, or section mode
      for an `environment` destination. Do not store the mode in component state.
- [x] 3.2 Build section mode: back control, the project it configures, and the eight environment
      sections as selectable rows.
- [x] 3.3 Add the configuration gear to each project row, revealed on group-hover/focus and
      persistent for the active project, with an accessible name naming the project.
- [x] 3.4 Add the `Add agent` row at the end of each expanded project's agent list.
- [x] 3.5 Remove the environment section column from `App.tsx`; the content area renders only the
      selected section.
- [x] 3.6 Remove `environment` from `PROJECT_TABS` while leaving `environmentDestination`,
      `parseDestination`, and the `?tab=environment&section=…` URL contract intact.
- [x] 3.7 Remove the gear and the `Add agent` button from `ProjectHeader`.
- [x] 3.8 Confirm the back control reaches the project overview in one action. Covered by
      `projectRail.test.tsx` ("derives section mode from the environment destination and returns in
      one action"); not additionally confirmed in a live browser.

## 4. Environment screens

- [x] 4.1 Add a shared settings-section layout: title, description, and hairline-separated rows
      pairing label plus explanation with a control.
- [x] 4.2 Port `ProjectSettingsPanel` to it, removing `max-w-3xl` capping, and write the explanation
      text for hop budget, per-turn delivery cap, agent budget, token budget, and agent jobs.
- [x] 4.3 Port `QualityHealthPanel`, `InstructionsPage`, `RunnersPage`, `ChartersPage`,
      `WorktreesPanel`, `DiagnosticsPanel`, and `AccountingPanel`.
- [x] 4.4 Give every section a title and a one-line statement of what it governs. Verified by reading
      each ported panel — all eight now open with `SettingsSection`'s `title`/`description`.
- [ ] 4.5 Confirm each section fills the content region at a wide viewport with no dead area. NOT
      confirmed — requires a live browser at a wide viewport, not run this session. Watch item: the
      section content still sits inside `App.tsx`'s 1180px `workspace-content` wrapper while
      `.settings-section-rows` caps at 920px — check for a visible gap between the two bounds.
- [ ] 4.6 Confirm numeric constraints still reject invalid input with an explanation once the
      steppers are gone. NOT confirmed — native HTML `required`/`min` validation UI does not reliably
      reproduce in jsdom; needs a live browser.
- [ ] 4.7 Confirm save success and save failure are both reported in the section. Only
      `ProjectSettingsPanel` explicitly reports both (`role="status"` / `role="alert"` in-section).
      `RunnersPage`/`ChartersPage` report create/delete errors via their own dialog/inline alert but
      not a section-level success message; `InstructionsPage` has its own "Saved" indicator;
      `AccountingPanel`'s Apply/Disable report no outcome at all. Not uniformly true across all eight
      sections — left unchecked rather than claimed.

## 5. Conversation surface

- [x] 5.1 Rebuild the header in `AgentOutputPanel`: no fill, no rule, translucent with backdrop
      blur, carrying the project breadcrumb, agent identity, model, and run state.
- [x] 5.2 Replace the literal `←` back control with an icon control carrying an accessible name.
- [x] 5.3 Move `Fold all turns` and `Stop turn` into the header; leave conversation switching,
      handoff, and agent details in the overflow menu.
- [x] 5.4 Remove the filled footer strip and its top border; render the composer region as a
      gradient fade to the ground plane.
- [x] 5.5 Make the composer a lifted surface — own fill, outline, shadow, content radius,
      focus-within treatment on the whole surface.
- [x] 5.6 Keep the banner stack and continuity line above the composer, unboxed.
- [x] 5.7 Widen the stream in `AgentTimeline` to the mock's measure, gutters, and entry spacing.
- [x] 5.8 Give the work disclosure a bounded surface and a summary hover; give the folded-turn
      control a hover treatment.
- [x] 5.9 Confirm queue handling, hop budget, handoff, autoscroll, context usage, and
      provider-identity confinement are unchanged. No logic in these areas was touched this
      iteration (UI/CSS only); the full `npm test` suite — including `agentHandoff.test.tsx`,
      `conversationControls.test.tsx`, and the context-usage and autoscroll tests — passes unchanged
      at 376/376.

## 6. Specification reconciliation

- [x] 6.1 Record in `openspec/changes/2026-07-30-hub-native-experience/` that rail-owned contextual
      navigation supersedes its wording forbidding project-scoped views from the navigation region,
      with the work-view versus configuration distinction from `design.md`.
- [x] 6.2 Run `openspec validate 2026-08-04-hub-contextual-navigation --strict`.

## 7. Verification

- [x] 7.1 `pytest hub/tests -q` — 602 passed, 8 skipped; unchanged from before this iteration.
- [x] 7.2 `npm test` in `hub/ui` — 376 passed (46 files).
- [x] 7.3 `npx tsc --noEmit` — passed, no output.
- [x] 7.4 `npm run build`, then refresh and commit `hub/hub/static/ui`. Build passed (2091 modules;
      pre-existing chunk-size warning only); `index-DHU9fHCd.js`/`index-DYT0Hhdp.css` replaced the
      previous hashed bundle files and `index.html` was refreshed. Not yet committed — commit is a
      separate, user-confirmed step.
- [x] 7.5 `pytest hub/tests/test_ui_staleness.py -q` — 5 passed.
- [ ] 7.6 Live check at 1280×800 and 390×800 in both themes: hover and selected states on every rail
      row, tab, and section row; the gear reveal; rail section mode and back; a settings section with
      no stepper buttons and no dead area; the conversation with no bands and a lifted composer. NOT
      run — no browser was launched this session.
- [ ] 7.7 Live check with reduced motion on: states still distinguishable, transitions suppressed. NOT
      run.
- [ ] 7.8 Keyboard-only pass: the revealed gear, the rail back control, and the header turn controls
      are all reachable and show focus. NOT run.
