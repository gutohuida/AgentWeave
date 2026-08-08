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

> **Ordering correction (2026-08-08): 0.1 is NOT independent — run 1.1–1.3 first.**
> Task 1.1 asks what the agent does when told to invoke a skill it does not have. Rewriting
> `HANDOFF_PROMPT` destroys the condition 1.1 exists to observe. 1.1 and 1.2 have now been run and
> are written up in `openspec/explorations/2026-08-08-handoff-behaviour.md`; 1.3 has not. Do not
> touch 0.1/0.2 until it is.
>
> **What 1.1 already establishes about 0.1's shape:** the destination is not merely absent, it is
> *unreachable*. `.agentweave/shared/checkpoints/` lies outside the agent's allowed working
> directory (its worktree), so a Claude agent is sandbox-blocked from it and a Codex agent
> silently creates a second, nested `.agentweave/shared/` inside its own worktree. Installing
> `aw-checkpoint` therefore cannot fix 0.1 on its own — the path is wrong independently of the
> skill being missing, which also bears directly on 0.4.

- [ ] 0.1 `AgentOutputPanel.tsx:48-52` (`HANDOFF_PROMPT`) — the prompt instructs the agent to invoke an
      `aw-checkpoint` skill that is never installed and write to `.agentweave/shared/checkpoints/`,
      which is never created. Replace with an instruction the agent can actually satisfy, or state
      plainly in the prompt that it must produce the summary inline
- [ ] 0.2 `AgentOutputPanel.tsx:54-60` (`RESUME_HANDOFF_PREFIX`, the path at `:57`) — the resume
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

Findings live in `openspec/explorations/2026-08-08-handoff-behaviour.md`.

**Observe what exists**

- [x] 1.1 Trigger the current Handoff against a live Claude agent and capture the full transcript.
      What does the agent actually do when told to invoke a skill it does not have? Does it
      improvise something useful, refuse, or silently no-op?
      **Answered:** it improvises, well, by silently substituting the operator's own Claude Code
      `/handoff` skill — and ignores three of the prompt's four instructions (skill name, reason,
      destination). Artifact landed at `<worktree>/.handoffs/`, which no Hub record references.
      On a second press with the artifact in context it stops improvising and asks the operator
      for clarification instead, producing nothing. Both runs set "Handoff ready".
- [x] 1.2 Repeat against a live Codex agent. Codex has no project-level skill discovery at all
      (`scripts/sync_skills.py` header), so its behaviour may differ from Claude's
      **Answered, and the premise needs correcting.** Codex has no *project*-level skill
      discovery, but it reads `~/.agents/skills/` — it found and followed the *same* handoff skill
      Claude used. Both runtimes silently substitute the operator's personal handoff skill; neither
      has ever run `aw-checkpoint`. Codex resolves the destination relative to its own worktree,
      creating a nested `worktrees/codex-1/.agentweave/shared/checkpoints/` — confirmed on disk.
      **The rescue is borrowed, not a product property:** a user without those personal skill
      directories gets 1.1's second-run behaviour — no artifact, a question back. Section 0 cannot
      assume the competence observed here.
- [x] 1.3 Send the follow-up message and capture what the successor conversation actually receives.
      Determine whether any current behaviour is worth preserving before it is replaced
      **Answered: nothing is worth preserving.** The successor receives exactly
      `RESUME_HANDOFF_PREFIX + "\n\n" + typed message` in a brand-new conversation — no history, no
      peer messages, no tasks, no overrides, no artifact reference. Both paths the prefix names are
      wrong: `.agentweave/shared/` exists nowhere, and the real context file is
      `.agentweave/context/<agent>.md` (already injected into the prompt, so that half is redundant
      even when corrected). Codex's round-trip closes **by coincidence** — it resolved both the
      write and the read against its own worktree. Claude's does not: six failed lookups, one
      sandbox block, then a bare `Glob("*")` rescued it.

**Determine the content**

- [x] 1.4 Read `src/agentweave/templates/skills/handoff.md` (106 lines) and decide which of its
      sections apply to an AgentWeave conversation and which are specific to a single-agent coding
      session in a terminal
      **Answered:** three groups. **Drop** §1 (the operator already chose by pressing the button),
      §2's git gathering (the Hub auto-commits every turn at `worktrees.py:243-258`, so the tree is
      *always* clean and the log is *always* identical auto-snapshots — observed), §2's upstream
      probe, §2's prior-handoff search, §3's `.handoffs/`+`LATEST.md` chain, §4's "run /resume".
      **Stamp, don't ask:** the whole header block plus Files touched, all Hub-known and all got
      wrong or non-answered by the model. **Keep, model-authored:** Goal, Current state, Key
      decisions, Dead ends, Verification, Next steps, Open questions, Read on resume.
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
