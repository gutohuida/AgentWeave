# Tasks — agent configuration page

> Sequenced **before** `2026-08-07-conversation-handoff-rework` section 8, so that change's
> agent-level settings have a destination rather than needing one invented mid-flight. This change
> does not depend on that one.

## 1. Remove the fields that have no backing state

Do this first. It is small, it is independent of the page, and it shrinks what the page has to
render.

- [x] 1.1 Find every consumer of `role` and `yolo` — API responses, UI, tests, fixtures. **Removal
      is only behaviour-preserving if nothing reads them; establish that rather than assuming it**

      **Done, and it overturned this change's own premise.** The two fields are not alike:

      - **`role` is dead.** One producer (`agents.py:508`, from `agent_meta`), two consumers
        (`api/agents.ts:14`, `AgentInfoTab.tsx:40,110-122`). Nothing reads it for behaviour.
        (`specManifestRepair.test.tsx`'s "spec-role agent" means an agent *named* `spec`, not
        `agent.role` — not a consumer.)
      - **`yolo` is live and stays live.** Stored in `Agent.config` (`models.py:503`) and session
        config; read at `agent_trigger.py:288` → `runner_commands.py:187,201,246`
        (`--dangerously-skip-permissions` vs `--permission-mode`) and
        `codex_appserver._thread_policy`/`decide_approval`; also `agents.py:210`
        (collaboration-readiness refusal) and `_runner_summary:746`. The claim in the original
        proposal that it is `bool = False` with nothing behind it was **wrong** —
        `agents.py:509` populated it from `agent_meta`. Only the **read-only summary field and its
        badge** are removed. `proposal.md`, `design.md` and the spec delta were corrected.
      - Response-field consumers found in tests: `test_agents_self_registered.py:393,471`.
        The `config["yolo"]` assertions at `:460-462` are a different surface and stay.
- [x] 1.2 Remove `role` and `yolo` from `hub/hub/schemas/agents.py:44-47` — and their population at
      `agents.py:508-509`
- [x] 1.3 Remove the *Collaboration Role* section and *YOLO Mode* badge from
      `AgentInfoTab.tsx:110-153`, and `ROLE_CONFIG` with them if it has no other caller — done;
      `ROLE_CONFIG` had no other caller. The heading *"Roles & Configuration"* became
      *"Configuration"*. Also removed the `agent.yolo` ⚡ indicator from `AgentCard.tsx:49`, a
      consumer this task list had not listed (the component is unreachable but still compiled)
- [x] 1.4 Correct the stale enum comment on `runner` (`schemas/agents.py:48-50`), which names
      `"native" | "claude_proxy" | "kimi" | "manual"` — an enum the Runner registry replaced.
      Corrected in `schemas/agents.py` and in `api/agents.ts:16`, which repeated it
- [x] 1.5 Test asserting the agent response carries no `role` or `yolo`, so they cannot return
      unnoticed — `test_agent_summary_carries_no_role_or_yolo`, which also asserts
      `config["yolo"]` survives, so the removal cannot silently widen into a behaviour change
- [x] 1.6 Full suite after removal — this touches a response schema

## 2. The destination

- [ ] 2.1 Add a fourth destination shape carrying the agent — `{ kind: 'agent-settings', projectId,
      agent, section }` — to `lib/navigation.ts` and the URL. **Not** an `ENVIRONMENT_SECTIONS`
      entry: those carry no subject, so they cannot address one agent
- [ ] 2.2 Page shell following the environment pattern at `Sidebar.tsx:173-191` — the sidebar becomes
      the section list plus a back control, rather than sections nesting inside the surrounding
      navigation
- [ ] 2.3 Back goes to a **fixed** target: the agent's most recent conversation. No stored origin,
      matching `App.tsx:207`'s fixed "Back to {project}"
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
- [ ] 3.8 Binding a runner or charter shows what is bound and allows rebinding through the existing
      picker (`AgentInfoTab.tsx:352,394`). It does **not** link through to the runner or charter
      record — rebinding one agent and editing a record bound by many are different acts

## 3b. Archival

An agent is archived, never deleted. No `DELETE` route exists today; this is a commitment not to add
one, plus the archival that makes its absence workable.

- [ ] 3b.1 `lifecycle` column on `Agent`, constrained to `open` or `archived`, mirroring
      `models.py:255,280` for conversations. Migration guarded for a missing table; bump the head
      assertions in `hub/tests/test_migrations.py` **and** `hub/tests/test_project_persistence.py`
- [ ] 3b.2 Archive and unarchive from the configuration destination. Archival is reversible
- [ ] 3b.3 Refuse to archive an agent with a run in progress, following `archivable()`
      (`conversations.py:172`), which refuses rather than destroying
- [ ] 3b.4 An archived agent stops being offered wherever a working agent is offered — the rail,
      peer-message recipients, task assignment, the new-conversation surface. **Enumerate these by
      search rather than by memory; one missed site leaves an archived agent selectable**
- [ ] 3b.5 An archived agent keeps its history: conversations remain readable, runs and messages keep
      their attribution
- [ ] 3b.6 Define what happens when a peer sends to an archived agent. The checkpoint change defines
      the archived-*conversation* case; the archived-*agent* case belongs here
- [ ] 3b.7 Test asserting no route hard-deletes an agent, so one cannot be added without the
      decision being revisited

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
