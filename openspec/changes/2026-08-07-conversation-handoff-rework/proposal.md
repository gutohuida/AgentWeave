# Handoff rework — skeleton, gated on exploration

> **STATUS: SKELETON. DO NOT IMPLEMENT.**
>
> This change has a proposal and an exploration task list. It deliberately has **no `design.md`
> and no `specs/`**, because the design is not known yet and writing it now would encode
> assumptions instead of findings.
>
> **Two gates, both hard:**
>
> 1. `2026-08-07-conversation-navigation` must be implemented first. This change consumes
>    `archive`, `origin` and `title`, none of which exist yet. Designing against them before they
>    are built means designing against a guess.
> 2. Section 1 of `tasks.md` — the exploration — must be completed, and `design.md` and `specs/`
>    written from what it finds, **before any task in section 2 or later is started**.
>
> Do not mark any task complete on the strength of this document existing.
>
> **`openspec validate --changes` fails on this change, and that failure is the gate working.**
> It reports *"Change must have at least one delta"* because `specs/` is deliberately absent. Do
> **not** silence it by writing placeholder requirements — that would encode the assumptions this
> change exists to avoid. The failure clears when task 1.10 writes the real specs, and not before.

## Why

The Handoff control does not do what it says. Traced end to end on 2026-08-07:

- The button sends a prompt instructing the agent to *"Invoke your `aw-checkpoint` skill"* and save
  under `.agentweave/shared/checkpoints/`
  (`hub/ui/src/components/agents/AgentOutputPanel.tsx:38`).
- **`aw-checkpoint` is never installed.** The template exists at
  `src/agentweave/templates/skills/aw-checkpoint.md`, and `get_skill_template()` has exactly one
  caller in the repository — a test. No code path writes any skill into any project.
- **`.agentweave/shared/checkpoints/` is never created.** `SHARED_DIR`
  (`src/agentweave/constants.py:12`) has three children — `context_usage/`,
  `compact_decision.md`, `copilot_otel/`. `checkpoints` is not among them.
- **`.agentweave/shared/context.md`, which the resume prefix instructs the successor to read
  (`AgentOutputPanel.tsx:44`), is never written.** A differently-named file,
  `.agentweave/ai_context.md`, is referenced only by `diagnostics.py`, whose remediation hint still
  tells the operator to run `agentweave sync-context` — a command removed in the 56→5 CLI cut.
- **Nothing verifies any of it.** "Handoff ready" is set when the run ends
  (`AgentOutputPanel.tsx:158-165`): a `completed` status line, or the agent merely transitioning out
  of `running`. No artifact is checked for. A capable agent improvises something plausible and the
  UI reports success either way.

This is the same defect shape as the one `2026-08-07-unasked-question-backstop` was built to fix: a
signal that looks like it works because nothing checks it. The current
`agent-conversation-handoff` spec is satisfied by this behaviour, because it only requires that the
prompt be *sent*.

There is also a design opportunity that only exists after the navigation change. A handoff is a
conversation transition — end this thread, carry its state into a fresh one — and that is exactly
what `archive` + `origin` + `title` describe. A handoff summary held in the Hub's own database and
delivered to the successor as an inbound queue entry is strictly more reliable than a file the
agent is asked to go and find, and it removes the filesystem dependency entirely from a product
whose stated architecture is that the Hub owns execution and state.

## What Changes

**This section is provisional.** It records the direction the exploration is testing, not decisions.
Every bullet is subject to being overturned by section 1 of `tasks.md`.

- The handoff artifact moves from a file on disk to a durable Hub record, attached to the successor
  conversation.
- The successor receives it as an **`InboundQueueEntry`** rather than through the canonical context
  renderer. This is the one mechanism already verified: `_render_hub_agent_context`
  (`hub/hub/api/v1/agents.py:820`) takes no `conversation_id` and writes one file per *agent*
  (`agent_trigger.py:339` → `.agentweave/context/<agent>.md`), so it cannot carry something that
  belongs to one specific successor conversation. The queue is conversation-scoped by construction
  (`InboundQueueEntry.conversation_id`), is delivered at turn start by machinery that already
  exists, and renders in the timeline.
- The predecessor conversation is **archived** on a successful handoff; the successor is created
  with **`origin: handoff`** and a title derived from its predecessor's, so the lineage is legible
  in the navigation tree.
- Handoff readiness is **verified against the artifact**, not against the run ending. A handoff that
  produced nothing is reported as failed.
- Handoff is **offered proactively** when an agent crosses its context-usage threshold
  (`AgentSummary.context_usage` already carries `percent`, `warning` and `threshold_warning`),
  surfaced in the same slot above the composer as the question and permission cards. Placement of
  the manual control is already settled by the navigation change: the conversation header.
- The dead references are removed: the `aw-checkpoint` instruction, `.agentweave/shared/checkpoints/`,
  `.agentweave/shared/context.md`, and `diagnostics.py`'s `sync-context` hint.

## Capabilities

**Not yet determined.** Filling this in is an output of the exploration, not an input to it.

The likely shape is a rewrite of `agent-conversation-handoff` — its three substantive requirements
(*Handoff checkpoints the selected conversation*, *The next conversation resumes the durable
handoff*, *Conversation transition state is visible and scoped to the agent*) all describe the file
mechanism and would become MODIFIED — plus a delta on `agent-conversation-workspace` if the
proactive offer needs one. Do not treat that as decided.

## Impact

**Not yet determined**, beyond two things already established:

- `agent-conversation-handoff` is affected in full; it currently specifies a mechanism that does not
  work.
- The stale prompt in `AgentOutputPanel.tsx:37-49` and the stale `sync-context` hint in
  `diagnostics.py:477` are **live defects today**, independent of this change and of the navigation
  change. They should be corrected without waiting for either — see `tasks.md` section 0.

## Prior exploration

Recorded in the session of 2026-08-07 (handoff `0015`). Established: the stale-reference chain
above; that the canonical context renderer is agent-scoped and therefore cannot carry a
conversation-specific summary; and that the inbound queue can. Not established: anything in the
*What Changes* list beyond the queue mechanism.
