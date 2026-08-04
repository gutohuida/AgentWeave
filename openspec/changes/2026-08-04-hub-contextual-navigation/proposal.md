# Contextual navigation, live interaction feedback, and the conversation surface

## Why

The previous change (`2026-08-04-hub-ui-mock-alignment`) recomposed the workspace *shell* against the
approved mock. It did not touch the agent conversation, the environment screens, or the interaction
model, and operator review found each of those three still wrong.

**The conversation screen never changed.** Commit `89b837e` touched `App.tsx`, `Sidebar`,
`ProjectHeader`, `ProjectTabs`, `OverviewPage`, and `index.css`. `AgentOutputPanel`,
`AgentTimeline`, `Composer`, and `ConversationControls` were out of scope and remain as they were:
a filled `--surface-2` header closed by a hard rule, a literal `←` character as the back control,
and a filled `--surface-2` footer strip — also closed by a rule — that boxes the composer in with
the banner stack and the continuity line. The approved mock specifies the opposite: a borderless
header floating on the ground plane, a stream on that same plane, and a composer that lifts as its
own rounded surface over a gradient fade, with no strip and no dividing rules at all.

**Configuration has two entry points and neither is where navigation belongs.** The operator reaches
the environment through both the `Environment` project tab and the gear in the project header. Once
inside, its eight sections are navigated by a bare 160px column *inside the content area*, so the
screen carries navigation that the rail should own.

**Nothing responds to the pointer.** `hub/ui/src/components/ui/button.tsx` defines a complete
control primitive with hover fills, border colouring, and press inversion — and **no component in
the application imports it**. Across all of `hub/ui/src` there are eleven `hover:` occurrences, five
of which are inside that unused primitive. The global baseline at `index.css:235` reserves a
transparent border and declares transitions but never sets a hover background, so almost every
control in the product — rail rows, agents, project tabs, environment sections, tabs, list rows — is
visually inert under the pointer. The mock specifies hover and active fills for every one of these
(`.navitem:hover`, `.tab:hover`, `.project-agent:hover`, `.agent-row:hover`, `.project-link:hover`,
`.work summary:hover`, `.fold:hover`).

**The environment screens waste their space.** Panels cap themselves (`ProjectSettingsPanel` uses
`max-w-3xl p-4`) inside an 1180px bounded container, leaving a large dead region, and numeric fields
render the browser's default increment/decrement spinners, which do not belong to the visual
language.

## What changes

- **The left rail becomes contextual.** It has a project mode (the project tree) and a section mode.
  Entering configuration replaces the rail's contents with that area's navigation, headed by a back
  control that returns to project mode. Navigation that today sits inside the content area moves
  into the rail. This is the pattern T3 uses for its settings, and it is the operator's explicit
  direction: *"any navigation should be applied to the nav on the left."*
- **Configuration gets exactly one affordance:** a gear on the project's own row in the rail. The
  `Environment` project tab and the project-header gear are both removed. The environment
  destination and its URL parameters are unchanged, so deep links continue to resolve.
- **`Add agent` moves into the rail**, as a row at the end of each expanded project's agent list,
  mirroring `+ Add project`. The project-header button is removed.
- **Every activatable element gains hover, press, and selected feedback** resolved from semantic
  tokens, plus the group-hover reveal that lets a row expose its secondary actions without carrying
  them permanently. The existing `Button` primitive becomes the actual control of the application
  rather than dead code.
- **The conversation surface is rebuilt against the mock**: borderless floating header carrying
  identity and turn-level actions, stream on the ground plane at the mock's bounded width, and a
  lifted rounded composer over a gradient fade — no filled strips, no dividing rules.
- **Environment screens adopt a settings-row layout**: bounded single column of labelled rows
  grouped under section headings with hairline separation, each section titled and described.
  Numeric fields present no stepper buttons; values are typed.

## Non-goals

- Redesigning the Spec workspace. That remains the next specification-program change.
- Changing what any environment section *does*, or the runner/charter/quality/budget data models.
  This change governs how those screens are navigated and laid out, not their behaviour.
- Changing conversation semantics: queue handling, hop budget, handoff, autoscroll, context usage,
  and provider-identity confinement all keep their current specified behaviour.
- Reproducing T3 branding, palette, product copy, or account surfaces. T3 informs the interaction
  model only.
- Adding new environment sections or new project tabs.

## Impact

- **Frontend:** `Sidebar` (contextual modes, gear, add-agent row), `App.tsx` (rail-owned section
  navigation, tab-strip removal), `ProjectHeader` (action removal), `ProjectTabs`,
  `AgentOutputPanel`, `AgentTimeline`, `ConversationControls`, `Composer`, all eight environment
  panels, `index.css` (row-state tokens, spinner suppression), and adoption of
  `components/ui/button.tsx` across the shell.
- **Backend:** none. No API, schema, or event changes.
- **Static assets:** the committed production UI bundle is refreshed after the source build.
- **Specifications:** modifies `hub-workspace-shell` and `agent-conversation-workspace`; adds
  `hub-interaction-feedback` and `project-environment-settings`. Records that rail-owned contextual
  navigation supersedes the in-flight `hub-native-experience` wording that forbade any
  project-scoped view from appearing in the navigation region.

## Approval gate

Implementation MUST NOT begin until the user explicitly approves this proposal.

**Approved:** 2026-08-04
