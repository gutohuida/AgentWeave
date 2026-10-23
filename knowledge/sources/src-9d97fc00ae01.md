# AgentWeave identity kit (2026-10-22)

Source: the operator's Design System artifact, https://claude.ai/artifact/TUUKwciug61DCayLS7XLHn
(README brand book, tokens, logo SVG/PNG assets, Logo / AppIcon / LoadingThread previews).
The artifact itself could not be fetched by an agent (it renders client-side behind claude.ai), so
this entry records the decisions behind it as they were made in the identity session and as they
shipped in the repository (commit 4b3eb07, merged to master e23cbc6). Where this summary and the
artifact disagree, the artifact is the source.

## The brief (operator's words)

- Concept: agents woven through the entire software lifecycle; one place to weave agents and
  processes together.
- Audience: people building an AI "factory"; companies that need traceability of what happened and
  why; developers and business people alike. Explicitly not "vibe coders".
- Feel: future, stability, visibility. Never murky, difficult or convoluted.
- Differentiator: other tools lack visibility and easy control of agents, make agentic workflows
  convoluted and ugly, or focus on agents instead of on the lifecycle's artifacts.

## Origin story

AgentWeave began as a way to get agents from different companies working together, each doing what
it does best. Then the real problem showed: work appeared out of thin air, and nobody could say who
made it or why. AgentWeave grew into full control of your AI factory: care for every artifact,
supervision, transparency.

## The red thread

In Goethe's *Elective Affinities*, every rope of the Royal Navy is spun with a red thread, so any
piece of it can be traced back to where it was made. AgentWeave does the same for software: one
thread runs requirement → task → run → evidence → review → merge, and every step names who took it.

- Tagline: **"Run your AI factory in the open."**
- Hero headline: **"Nothing appears out of thin air."**

## The mark

- "The loop": one thread draws a W and loops back over itself at the centre — the human in the loop.
  Masked crossing gap where the thread passes under itself.
- Master drawing for ≥48 px; a heavier small drawing for 16–32 px.
- App icon: the ink tile (madder thread on ink).
- Sidebar head order: logo, name, then the live-connection dot.
- Rules: keep marks to ≤4 parts; judge in monochrome first; check 16 px by rendering.

## Colour

- **Madder** (the brand thread): #B03A26 light / #CC4630 dark. Reserved for the logo and the
  red-thread diagram only — never a general accent or status colour. (An earlier #F07F68 was
  rejected for sitting ΔE 5 from Claude's own #d97757.)
- **Verdigris** (the single UI accent): #1D6B6E light / #5FB3B3 dark. State only — focus, active
  marker, selection — never a fill. Replaced the previous indigo ring.
- **Ink**: #15171C.
- Surfaces are monochrome: dark background #0A0A0B, surface #151518; light background #FAFAFA,
  surface #FFFFFF. Buttons are monochrome.
- Agent hue 2 moved from teal to magenta (#B8399A / #E066C0) so no agent colour collides with the
  accent.

## Type and motion (as applied in the app)

- UI type: DM Sans Variable; mono: JetBrains Mono.
- Motion tokens: fast 150 ms, base 250 ms, slow 500 ms, ease cubic-bezier(0.16, 1, 0.3, 1);
  every animation is disabled under prefers-reduced-motion.

## Where it lives in the repository

- App tokens: hub/ui/src/index.css (`--brand-madder`, accent, agent hues).
- Docs: docs/stylesheets/brand.css, docs/assets/agentweave-loop*.svg, docs/snippets/red-thread.html.
- Logo component: hub/ui/src/components/common/BrandLoop.tsx.
