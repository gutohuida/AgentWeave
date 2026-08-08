# Conversation checkpoint — gates cleared, ready to implement

> **STATUS (2026-08-08): both gates cleared. Implementation may start.**
>
> 1. `2026-08-07-conversation-navigation` implemented ✅
> 2. Section 1 exploration complete ✅
>    (`openspec/explorations/2026-08-08-handoff-behaviour.md`), `design.md` written ✅,
>    `specs/` written ✅ — `openspec validate --changes --strict` now passes.
>
> The gate did its job. The exploration overturned two things this document assumed, and both are
> corrected below rather than quietly left standing:
>
> - **Handoff is the wrong name.** The record is a **checkpoint**, which is the vocabulary the
>   product already used before the terminal skill's name was borrowed.
> - **The agent should not write it.** This document assumed the artifact moves to a Hub record but
>   is still produced by the agent. The exploration found the agent's competence was borrowed from
>   the operator's personal skills, and that the Hub already holds everything needed to produce the
>   artifact itself. Generation is Hub-side.
>
> Two prerequisites were discovered by the exploration and folded into this change, because both
> block it and splitting them would produce changes that must land in a fixed order anyway:
> deterministic peer delivery (section 2) and context-usage measurement (section 3).
>
> Still binding: **do not mark any task complete on the strength of a plan existing.**

## Why

The Handoff control does not do what it says. Traced end to end on 2026-08-07:

- The button sends a prompt instructing the agent to *"Invoke your `aw-checkpoint` skill"*
  (`hub/ui/src/components/agents/AgentOutputPanel.tsx:39`) and save under
  `.agentweave/shared/checkpoints/` (`:41`). The constant spans `:37-41`.
- **`aw-checkpoint` is never installed.** The template exists at
  `src/agentweave/templates/skills/aw-checkpoint.md`, and `get_skill_template()` has exactly one
  caller in the repository — a test. No code path writes any skill into any project.
- **`.agentweave/shared/checkpoints/` is never created.** `SHARED_DIR`
  (`src/agentweave/constants.py:12`) has three children — `context_usage/`,
  `compact_decision.md`, `copilot_otel/`. `checkpoints` is not among them.
- **`.agentweave/shared/context.md`, which the resume prefix instructs the successor to read
  (`AgentOutputPanel.tsx:46`, in the `RESUME_HANDOFF_PREFIX` constant spanning `:43-49`), is never
  written.** A differently-named file,
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

Four deltas, written at task 1.10:

- **`conversation-checkpoint`** — ADDED. The new capability: the record, the worker that generates
  it, the computed/written split, anchoring, agent notes, verification against the Hub's own
  records, citations and recall, the two permission grants, lineage versus derived participation,
  threshold configuration, and visibility.
- **`agent-conversation-handoff`** — MODIFIED. Its three substantive requirements all specified the
  file mechanism and are rewritten: the Hub produces the checkpoint, delivers it into the successor
  as conversation-scoped queued input, and readiness follows the verified checkpoint rather than the
  run ending.
- **`agent-conversation-workspace`** — ADDED. Defines the **queue-routing contract**, a term this
  capability already referenced and which was defined nowhere.
- **`agent-context-usage`** — ADDED. A measured sample must identify its model, window metadata must
  persist across samples that omit it, and a catalog model with no declared window degrades to
  unknown rather than borrowing another model's.

## Impact

- `agent-conversation-handoff` is affected in full; it specified a mechanism that cannot work.
- **Peer delivery changes for every message.** Delivery binds to the sending conversation instead of
  the recipient's most recently touched thread. There is exactly one routing site — both the
  operator and agent routes funnel into `create_message_for_actor` — but the behaviour change is
  visible in the conversation tree.
- **Context usage begins reporting for Claude agents**, which it never has: 329 samples, zero usable
  percentages, because the samples carrying token counts carry no model id.
- The stale references are live defects today and are corrected with the rename in section 9:
  `AgentOutputPanel.tsx:48-60`, `agents.py:1444` and `:1474` (found during the exploration and
  missing from the original list), and `diagnostics.py:477`'s dead `agentweave sync-context` hint.
- `src/agentweave/templates/skills/aw-checkpoint.md` is deleted; the capability moves into the Hub.

## Prior exploration

Recorded in the session of 2026-08-07 (handoff `0015`). Established: the stale-reference chain
above; that the canonical context renderer is agent-scoped and therefore cannot carry a
conversation-specific summary; and that the inbound queue can. Not established: anything in the
*What Changes* list beyond the queue mechanism.
