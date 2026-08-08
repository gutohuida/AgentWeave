# Tasks — agent configuration page

> Sequenced **before** `2026-08-07-conversation-handoff-rework` section 8, so that change's
> agent-level settings have a destination rather than needing one invented mid-flight. This change
> does not depend on that one.

## 1. Remove the fields that have no backing state

Do this first. It is small, it is independent of the page, and it shrinks what the page has to
render.

- [ ] 1.1 Find every consumer of `role` and `yolo` — API responses, UI, tests, fixtures. **Removal
      is only behaviour-preserving if nothing reads them; establish that rather than assuming it**
- [ ] 1.2 Remove `role` and `yolo` from `hub/hub/schemas/agents.py:44-47`
- [ ] 1.3 Remove the *Collaboration Role* section and *YOLO Mode* badge from
      `AgentInfoTab.tsx:110-153`, and `ROLE_CONFIG` with them if it has no other caller
- [ ] 1.4 Correct the stale enum comment on `runner` (`schemas/agents.py:48-50`), which names
      `"native" | "claude_proxy" | "kimi" | "manual"` — an enum the Runner registry replaced
- [ ] 1.5 Test asserting the agent response carries no `role` or `yolo`, so they cannot return
      unnoticed
- [ ] 1.6 Full suite after removal — this touches a response schema

## 2. The destination

- [ ] 2.1 Add an agent-settings destination to the navigation model and URL, resolving the open
      question in `design.md` — under the project's `environment` grouping, or hanging off the agent
- [ ] 2.2 Page shell following the project-settings pattern: a section list replacing the tab strip,
      not nested inside it
- [ ] 2.3 Back control rather than the left navigation panel, returning to the originating context
      rather than to a fixed location
- [ ] 2.4 Entry points from the agent's navigation row and its conversation header
- [ ] 2.5 The destination survives reload and is linkable

## 3. Sections

Named for what an operator is trying to do, not for the shape of the data.

- [ ] 3.1 **Identity** — name, description
- [ ] 3.2 **Execution** — runner binding, model, default permission posture
- [ ] 3.3 **Charter** — charter binding
- [ ] 3.4 **Interaction** — permission timeout, question timeout (moved from `AgentInfoTab`'s
      *Waiting for you*)
- [ ] 3.5 **Context** — defined here, populated by the checkpoint change. Renders whatever context
      settings exist at the time
- [ ] 3.6 **Access** — defined here, populated by the checkpoint change
- [ ] 3.7 **Workspace** — worktree, working directory
- [ ] 3.8 Binding a runner or charter shows what is bound and allows rebinding; it does **not** edit
      the runner or charter record, which have their own destinations

## 4. Split configuration from observation

- [ ] 4.1 Status, `latest_status_msg`, `last_seen` and the session list **stay with the
      conversation**. They are observation, they change without anyone configuring anything, and
      they are useful while working
- [ ] 4.2 `AgentInfoTab` retains only observation, or is removed if nothing is left to justify a tab
- [ ] 4.3 No setting appears in both places

## 5. Creation-time boundary

- [ ] 5.1 State the rule in the creation surface's own terms: a setting is **offered** at creation
      if the agent's **first turn** would be materially different without it. The rule governs what
      is offered, not what is required
- [ ] 5.2 Confirm the current four — name, provider, model, charter — satisfy it. **Charter stays
      optional**: `operator-agent-creation` states it "MAY be selected but MUST NOT be required" and
      defines a no-charter contract. Do not tighten that
- [ ] 5.3 Do **not** add thresholds, timeouts, or access grants to creation. They have workable
      defaults and can be changed before they matter; lengthening creation is friction at exactly
      the wrong moment
- [ ] 5.4 A newly created agent opens somewhere sensible — decide whether that is its settings page
      or its first conversation

## 6. Verification

- [ ] 6.1 Component tests for the page: sections render, edits persist, the back control returns to
      the originating context
- [ ] 6.2 Navigation test: the destination is reachable from both entry points, survives reload, and
      is linkable
- [ ] 6.3 Confirm no setting is editable from two surfaces
- [ ] 6.4 **Drive it in a browser.** Standing gap across recent sessions — the operator has found
      two defects by using surfaces that passed their tests
- [ ] 6.5 Light and dark mode both checked by eye, not by token audit
- [ ] 6.6 Full sweep: `pytest hub/tests/`, `npx vitest run`, `npx tsc --noEmit`,
      `npx openspec validate --changes --strict`, `npm run build` copied to `hub/hub/static/ui`
      confirmed with `diff -rq`
