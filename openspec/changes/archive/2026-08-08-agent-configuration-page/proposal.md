# Agent configuration is a page, not a tab

## Why

Agent configuration currently lives in `AgentInfoTab.tsx` — a tab *inside* a conversation. That was
adequate when an agent had two editable settings. It is about to stop being adequate, and it is
already showing things that are not true.

**It is outgrowing its container.** `2026-08-07-conversation-handoff-rework` adds agent-level
configuration that has nowhere to go: automatic-checkpoint mode, a cutover threshold, a notes
threshold, the generating runner and model, and two independent access grants
(`read_checkpoint`, `recall`). Section 8 of that change has no destination for its UI. Building
those into a tab inside a conversation would put durable configuration behind a transient surface.

**It is displaying two fields that should not be there, for two different reasons.**
`hub/hub/schemas/agents.py:44-47` declares `role` and `yolo`, and `AgentInfoTab.tsx:110-153` renders
a *Collaboration Role* section and a *YOLO Mode* badge from them.

`role` no longer exists: the role subsystem was deleted, `CLAUDE.md` records that role-derived API
and UI fields "no longer exist and must not be recreated", and nothing in the Hub reads it. It is a
field no store can populate.

`yolo` is the opposite mistake. It is a **real, live setting** — stored in `Agent.config`, read at
`agent_trigger.py:288`, and used by `runner_commands.py` and `codex_appserver` to choose the run's
permission posture — rendered as a badge the operator can read but not change, in a tab that is
otherwise observation. The setting is not dead; its *presentation* is wrong, and its editable home
is **Execution**'s permission posture. Only the summary field and the badge are removed.

The adjacent `runner: str = "native"` (`:48-50`) carries a comment naming a runner enum
(`"native" | "claude_proxy" | "kimi" | "manual"`) that the Runner registry replaced.

This is the same defect shape this project has now found three times in a row — a surface that looks
like it works because nothing checks whether it still means anything.

**Configuration is not conversation state.** The project already solved this: project settings are a
destination with its own sections (`environmentSection` in `App.tsx:263-273`), not a dialog. Agents
deserve the same treatment, for the same reason — you configure an agent, then work with it; the two
are different activities.

## What Changes

- Agent configuration becomes its **own page**, reached from the agent, with section navigation in
  the style of project settings and a back control rather than the left navigation panel.
- Sections are reworked into: **Identity**, **Execution**, **Charter**, **Interaction**, **Context**,
  **Access**, and **Workspace**. Status and Sessions — which are observation, not configuration —
  stay with the conversation rather than moving to the settings page.
- `role` and `yolo` are removed from the agent schema and from the UI — `role` because it is dead,
  `yolo` because its presentation was read-only observation of a setting that belongs in Execution.
  `Agent.config["yolo"]` keeps driving the run. The stale runner-enum comment is corrected.
- **Creation-time settings are separated from later settings** by a stated rule: a setting is
  *offered* at creation when the agent's first turn would be materially different without it;
  everything else lives on the page. The rule governs what is offered, not what is required —
  charter remains optional under its existing no-charter contract.
- **An agent can be archived, and never deleted.** No `DELETE` route exists today; this commits to
  not adding one and provides the archival that makes its absence workable. Everything in the Hub is
  attributed to a run and every run to its agent, so deletion would either destroy the record of work
  that happened or orphan it.
- The page hosts, but does not define, the agent-level settings introduced by
  `2026-08-07-conversation-handoff-rework`. Those settings' semantics belong to that change; this one
  provides their home.

## Capabilities

- **`operator-agent-creation`** — ADDED. Creation already collects name, provider, model and charter
  (`AgentCreateDialog.tsx:128-217`), and nothing about that changes. What is added is the *rule*
  determining what belongs there versus on the page, so the boundary is a decision rather than an
  accident. The existing optional-charter contract is explicitly preserved.
- **`agent-configuration`** — ADDED. A new capability: configuration is a destination, its sections,
  what is configuration versus observation, archival in place of deletion, and that a setting with no
  backing state is not displayed.

## Impact

- `AgentInfoTab.tsx` is decomposed: configuration moves to the new page, observation stays.
- `hub/hub/schemas/agents.py` loses `role` and `yolo`. Any consumer of those fields must be found
  and updated — they are non-functional today, so removal should be behaviour-preserving, but that
  must be verified rather than assumed.
- Navigation gains an agent-settings destination, which the URL model must carry.
- `2026-08-07-conversation-handoff-rework` section 8 depends on this landing, or on its settings
  being placed provisionally and moved later.

## Sequencing

This change does **not** depend on the checkpoint change. It can land first, and should: the
checkpoint change's section 8 then has a destination rather than needing one invented mid-flight.

It does not attempt to host settings that do not exist yet. Sections are defined so that the
checkpoint settings drop into **Context** and **Access** without restructuring.
