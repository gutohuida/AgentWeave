# Request (open, to come back to): review the settings UI. It is hard to find and confusing, for both general and agent settings

Recorded 2026-10-23 by Architect at the operator's request. The operator's words: "Improve the
settings UI. It's hard to find the settings. We need to review all of that. The settings are
confusing. Either create more classifications or make things easier to navigate. Both general
settings and agent settings."

Not yet specified. Needs an exploring spec with the operator before anything is built: the
direction (more categories, or easier navigation) is still open.

## What prompted it

The operator could not find the notification settings. They live in **Project settings → General**,
at the bottom (`GeneralSettings.tsx:431`), even though they apply to the whole app, not to a
project.

## How settings are reached today (from the code on master 5f5616c)

**Project settings**
- Reached from a gear in the top bar labelled "Project settings" (`TopBar.tsx:145-156`), or from a
  gear that only appears when hovering a project row in the sidebar (`Sidebar.tsx:310-318`).
- Sections (`ProjectSettingsScreen.tsx:23-33`): General, Manager, Runners, Charters, Instructions,
  Budgets, Quality, Worktrees, Diagnostics.
- The General page alone carries several unrelated things:
  - Collaboration, Reach, Integration (checks), Checkpointing and Project (`GeneralSettings.tsx`)
  - Sound and notifications, which is app-wide, not per project
  - Delete project (danger zone)
  - Spec steps (`SpecStepsSection`) and Traces (`TracesSection`), appended after
    (`ProjectSettingsScreen.tsx:68-73`)

**Agent settings**
- Reached from an agent row's "…" menu → "Agent settings" (`AgentTree.tsx:123`), or from the
  conversation bar or output panel.
- Pages (`AgentSettingsSections.tsx`): Identity, Execution (Runs as, Permissions), Access (Other
  agents' work, Authority), plus a runner-specific Copilot group (`AgentSettingsPage.tsx:279`).

**App-wide preferences: no home of their own**
- Theme: a top-bar toggle.
- Notifications and sound: inside a project's General page.
- The opening-sound switch is mirrored to `~/.agentweave/hub/app-window/sound.json`.

## Observed problems to examine (to confirm with the operator, not decided)

1. **No app-level settings place.** Preferences that belong to the operator or the whole Hub sit
   inside one project's settings, so they look per-project and are hard to find.
2. **General is a catch-all.** Five groups, notifications, deletion, spec steps and traces on one
   page.
3. **Entry points are hidden.** The sidebar gear appears only on hover; agent settings are behind
   a "…" menu. A top-bar gear named "Project settings" does not suggest "where all settings are".
4. **Overlapping layers.** The same kind of setting is decided at project and agent level, and per
   conversation (Reach vs an agent's Permissions vs a conversation's choice; project ceilings in
   Budgets vs agent runner choice). The rule "the narrower wins" is stated in group descriptions,
   but there is no view of what is in effect for an agent, or why.
5. **No search** across settings.

## Directions to explore (the operator named the first two)

- **More categories:** split General (for example Collaboration & reach, Integration & checks,
  Checkpointing, Spec workflow, Danger zone) and add an app-level Settings (Appearance,
  Notifications & sound, Hub).
- **Easier navigation:** one Settings entry with three clear scopes (App / Project / Agent), a
  visible way in, settings search, and links from where a setting matters ("muted? open Sound
  settings") to where it is changed.
- **An "effective settings" view** for an agent: what applies, and which level it came from.

Next step: an exploring spec in the app (Tier 1, UI only), started with an operator interview. The
existing mocks practice (`hub/ui/mock`) applies, so options can be shown as real components before
choosing.
