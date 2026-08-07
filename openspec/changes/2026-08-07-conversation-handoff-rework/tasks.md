# Tasks — handoff rework

> **Sections 2 and beyond are placeholders and MUST NOT be started.** They exist to record what
> the exploration is expected to feed, not to be worked through. The real task list is written at
> task 1.9, from what section 1 finds.
>
> Gate: `2026-08-07-conversation-navigation` implemented, **then** section 1 complete, **then**
> `design.md` and `specs/` written, **then** implementation.

## 0. Correct the stale references now — not gated

These are live defects today. They do not depend on this change, on the navigation change, or on
the exploration. Do them independently.

- [ ] 0.1 `AgentOutputPanel.tsx:37-41` (`HANDOFF_PROMPT`) — the prompt instructs the agent to invoke an
      `aw-checkpoint` skill that is never installed and write to `.agentweave/shared/checkpoints/`,
      which is never created. Replace with an instruction the agent can actually satisfy, or state
      plainly in the prompt that it must produce the summary inline
- [ ] 0.2 `AgentOutputPanel.tsx:43-49` (`RESUME_HANDOFF_PREFIX`, the path at `:46`) — the resume
      prefix instructs the successor to read
      `.agentweave/shared/context.md`, which nothing writes. Remove or correct
- [ ] 0.3 `src/agentweave/diagnostics.py:477` — the remediation hint tells the operator to run
      `agentweave sync-context`, a command removed in the 56→5 CLI cut. Correct it
- [ ] 0.4 Decide and record whether `src/agentweave/templates/skills/aw-checkpoint.md` should be
      installed, rewritten, or deleted — it is currently packaged, referenced by a live prompt, and
      reachable by nothing

## 1. Exploration — REQUIRED BEFORE ANY IMPLEMENTATION

Each task below is answered with evidence, written into `openspec/explorations/`. "I think" is not
an answer; a file path, a captured transcript, or an observed run is.

**Observe what exists**

- [ ] 1.1 Trigger the current Handoff against a live Claude agent and capture the full transcript.
      What does the agent actually do when told to invoke a skill it does not have? Does it
      improvise something useful, refuse, or silently no-op?
- [ ] 1.2 Repeat against a live Codex agent. Codex has no project-level skill discovery at all
      (`scripts/sync_skills.py` header), so its behaviour may differ from Claude's
- [ ] 1.3 Send the follow-up message and capture what the successor conversation actually receives.
      Determine whether any current behaviour is worth preserving before it is replaced

**Determine the content**

- [ ] 1.4 Read `src/agentweave/templates/skills/handoff.md` (106 lines) and decide which of its
      sections apply to an AgentWeave conversation and which are specific to a single-agent coding
      session in a terminal
- [ ] 1.5 Decide whether the artifact is structured (columns or JSON, machine-checkable) or markdown
      (one blob, model-authored). Verification at task 1.11 depends on this answer
- [ ] 1.6 Determine what a handoff must carry that a single-agent session never had: the peer
      messages in the thread, the tasks the agent owns, outstanding questions, the conversation's
      runtime overrides

**The multi-agent question — most likely to reshape the slice**

- [ ] 1.7 `claude-1` hands off a conversation in which `haiku-1` participated. Does `haiku-1` need
      to be told? Its next message routes by `latest_open_conversation`, which will resolve to the
      successor — establish by test whether that is correct or merely convenient
- [ ] 1.8 Determine whether a handoff should carry the peer relationships forward at all, or whether
      a successor starting peer-blank is the right default

**Then, and only then**

- [ ] 1.9 Write `design.md` from 1.1–1.8. Replace sections 2+ of this file with a real task list
- [ ] 1.10 Write `specs/` — at minimum the `agent-conversation-handoff` deltas, which are a rewrite
      rather than an addition
- [ ] 1.11 Confirm the verification rule is testable against whatever 1.5 decided: a handoff that
      produced no artifact must be reportable as failed, which the current run-ended check cannot do

## 2. PLACEHOLDER — Durable artifact

*Not to be started. Shape depends on 1.5 and 1.6.*

- [ ] 2.1 Persist the handoff artifact as a Hub record attached to the successor conversation
- [ ] 2.2 Verify it exists before reporting the handoff ready

## 3. PLACEHOLDER — Delivery to the successor

*Not to be started. The queue mechanism is verified; nothing else here is.*

- [ ] 3.1 Deliver the artifact to the successor as an `InboundQueueEntry`, conversation-scoped
- [ ] 3.2 Do not route it through `_render_hub_agent_context` — it is agent-scoped and writes one
      file per agent, so it cannot carry a per-conversation payload

## 4. PLACEHOLDER — Lifecycle integration

*Not to be started. Depends on `2026-08-07-conversation-navigation` shipping.*

- [ ] 4.1 Archive the predecessor on a successful handoff
- [ ] 4.2 Create the successor with `origin: handoff` and a title derived from its predecessor's
- [ ] 4.3 Make the lineage legible in the navigation tree

## 5. PLACEHOLDER — Proactive offer

*Not to be started. Depends on 1.1–1.3 establishing what a handoff is worth offering.*

- [ ] 5.1 Offer a handoff when the agent crosses its context-usage threshold, in the card slot above
      the composer
- [ ] 5.2 Dismissible without suppressing it permanently
