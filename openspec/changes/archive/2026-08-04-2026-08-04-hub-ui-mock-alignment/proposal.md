# Hub UI mock alignment and agent creation

## Why

The running Hub is functionally ahead of its visual shell, but it no longer resembles the approved
full design mock at `openspec/changes/2026-07-30-hub-native-experience/mock-full.html`. The current
near-black single-plane theme, persistent global status strip, dense bordered cards, underspecified
project actions, and inconsistent control styling make the product feel like an implementation
dashboard rather than the calm project workspace the mock established.

Two visible defects sharpen the problem. `ProjectManagerModal` paints its panel with the undefined
token `--surface-1`, so the panel is transparent. `Sidebar` renders corrupted encoded strings for
the create-project and expand/collapse symbols. The mock also shows an **Add agent** action in the
project header, while the product has no operator journey for creating and binding an agent.

This change restores the mock as the primary visual reference, adopts the restrained interaction
qualities visible in T3's interface, fixes the concrete defects, and completes operator agent
creation before the specification workspace is expanded.

## What changes

- Recompose the desktop workspace shell to match the approved mock's hierarchy: an indigo project
  rail, an ink content plane, project identity/actions in the content header, compact project tabs,
  and quiet overview summaries rather than a dashboard-wide status strip and uniformly filled
  cards.
- Align dark/light palette, spacing, density, typography, radii, borders, hover/press/focus states,
  and content widths with the mock. T3 informs interaction restraint, translucent lifted surfaces,
  compact rounded controls, and physical press feedback; AgentWeave keeps its own palette and
  identity.
- Make every dialog a visibly opaque lifted surface on a scrim, using defined semantic tokens in
  both themes.
- Replace literal and corrupted project action glyphs with Lucide icons and accessible names.
- Add an operator agent-creation API and an **Add agent** project-header journey. The operator names
  the agent, selects a launchable runner, and may select a charter. Creation assigns a stable color,
  preserves project scope, broadcasts live state, and makes the agent immediately addressable.
- Rebuild and commit the production UI bundle after verification.

## Non-goals

- Redesigning the Spec document, evidence, proposal, or verification experience. That remains the
  next specification-program change and will build on this shell.
- Pixel-copying T3 branding, its pink accent, chat-specific navigation, account surfaces, or
  proprietary product structure.
- Agent templates, agent-request approval policy, automatic agent creation, or charter scope
  enforcement. This change covers direct operator creation from existing runners and charters.
- Reworking runner or charter authoring; their existing environment screens remain the source for
  managing those records.
- Changing project lifecycle, conversation identity, queue semantics, or worktree isolation.

## Impact

- **Frontend:** application shell, status/rail/header composition, overview, shared controls and
  dialogs, project manager, project tabs, agent creation dialog, React Query hooks, and tests.
- **Backend:** one project-scoped operator endpoint for agent creation plus validation, SSE event,
  and tests.
- **Static assets:** the committed production UI bundle is refreshed after the source build.
- **Specifications:** adds authoritative workspace-shell and operator-agent-creation capabilities;
  records that the distinct related rail/content planes in the approved mock supersede the older
  umbrella wording that required a single identical fill.

## Approval gate

Implementation MUST NOT begin until the user explicitly approves this proposal.

**Approved:** 2026-08-04
