# Design: Hub UI mock alignment and agent creation

## Visual authority

The primary visual reference is
`openspec/changes/2026-07-30-hub-native-experience/mock-full.html`, specifically its reachable
project rail, project overview, project tabs, conversation shell, controls, and light/dark tokens.
The static mock does not override implemented product behavior: current multi-project routing,
project tabs, conversation identity, accessibility, and responsive behavior remain authoritative.

T3 contributes qualities rather than assets or brand identity:

- quiet, compact controls with visible but restrained hover and focus states;
- rounded lifted surfaces with subtle rings and backdrop treatment;
- `active:scale`/depressed feedback with reduced-motion accommodation;
- low-noise hierarchy where controls appear when context makes them useful; and
- a calm content ground with a clearly related navigation plane.

AgentWeave retains the mock's indigo/ink palette, agent colors, typography, and information
architecture. No T3 logo, accent color, copy, or account/chat navigation is copied.

## Shell composition

At desktop widths the shell is:

1. a resizable project rail using the mock's `--rail` plane and 252 px default width;
2. a content plane using `--bg`;
3. a project header containing project name, agent/task/path summary, Project settings, and Add
   agent;
4. compact project tabs immediately beneath the header; and
5. a bounded content area with a maximum width around the mock's 1180 px.

The existing global `StatusBar` is not a permanent dashboard strip on desktop. Connection loss,
pending questions, live-run state, and other actionable conditions remain visible in their owning
surfaces or a compact contextual indicator. Theme/settings access moves to the rail/header without
losing keyboard reachability.

The overview follows the mock's composition: agent roster, pending-input callout, task/spec/job
summaries, and recent activity use mostly transparent/quiet summary regions. A filled surface is
reserved for content that is genuinely lifted or self-contained.

At narrow widths the rail may collapse to the existing compact form or an overlay. Nothing in this
change removes the existing URL-backed project/agent destinations or resize persistence.

## Token alignment

Use the mock's named values as the starting contract:

- dark `--bg #10131b`, `--rail #171b2a`, `--top #141827`, `--surface #1b2030`, and
  `--surface-2 #242a3c`;
- light `--bg #f5f6fa`, `--rail #e9ecf5`, `--top/#surface #fff`, and
  `--surface-2 #eef1f7`;
- primary indigo `#7c8cff` dark / `#5063d8` light;
- 10 px base radius, 24 px substantial-content radius, and the existing 150/250/500 ms motion
  scale; and
- DM Sans Variable plus JetBrains Mono, already self-hosted by the production app.

Compatibility aliases may remain temporarily, but every component touched by this change uses the
canonical tokens. Dialogs use `--surface`, never the nonexistent `--surface-1`. The scrim remains
separate from the dialog fill. Automated tests assert every referenced semantic token is defined in
both themes.

## Project actions and icons

All project actions use `lucide-react`, the application's one icon system:

- open existing: `FolderOpen` plus accessible name;
- create new: `FolderPlus` plus accessible name;
- expand/collapse: `ChevronRight` / `ChevronDown` with stateful accessible name; and
- add agent: `UserPlus` with visible **Add agent** text in the project header.

No control renders a hand-authored symbol for an action. Tests scan the rail for replacement
characters and the known mojibake sequences so encoding regressions fail visibly.

## Operator agent-creation contract

Add `POST /api/v1/projects/{project_id}/agents` on the operator-authenticated project router.

Request:

```json
{
  "name": "reviewer",
  "runner_id": "runner-...",
  "charter_id": "charter-..."
}
```

`charter_id` is optional. `name` uses the shared agent-name validation. The service:

1. verifies project availability;
2. validates name and refuses a duplicate within the project;
3. resolves a same-project runner and refuses a missing/unlaunchable runner with a typed reason;
4. resolves an optional same-project charter;
5. inserts a Hub-owned, non-self-registered agent with `watchdog-spawn` contact mode, stable next
   color, runner/charter bindings, safe default config, and no fabricated heartbeat/session;
6. commits and emits project-scoped `agent_created`; and
7. returns the created agent contract.

Creation does not eagerly provision a worktree. The existing scheduler provisions one on the first
writing turn, retaining its current guarded lifecycle.

The UI dialog loads runners, launchability, and charters under project-keyed React Query keys.
Unavailable runners remain visible but disabled with their reason. The first launchable runner may
be selected initially; no runner means the confirmation action remains disabled with guidance.
After success, project and agent queries invalidate, the dialog closes, and navigation opens the
new agent conversation. Failure preserves entered values and shows a typed inline error.

## Accessibility and verification

- Dialogs trap focus, close on Escape, restore focus to their trigger, and use labelled controls.
- Icon-only controls have accessible names and fine/coarse pointer targets.
- Keyboard focus, hover, press, light/dark, reduced-motion, 1280×800, and narrow-width behavior are
  verified.
- Unit/component tests cover token definition, icon semantics, opaque dialogs, API creation,
  duplicate/cross-project/unlaunchable validation, query invalidation, and navigation after create.
- Live verification uses `testbed/two-codex-agents/`, adds a third disposable agent, launches one
  minimal turn, and confirms the rail/header/dialog visually against the mock.

## Risks and mitigations

- **Broad visual churn:** migrate shell and shared primitives first, then pages. Do not mechanically
  rewrite unrelated feature logic.
- **Mock conflicts with newer behavior:** preserve current routes and behavior; use the mock for
  hierarchy and feel, not stale sample functionality.
- **False visual confidence from unit tests:** require shared-browser comparison in both themes and
  two viewport widths.
- **Agent creation bypasses launchability:** share the existing launchability resolver on the
  server and display the same result in the client.
