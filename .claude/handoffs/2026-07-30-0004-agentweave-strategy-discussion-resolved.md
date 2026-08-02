# Handoff: AgentWeave strategy discussion resolved — no code changed this session

**Date:** 2026-07-30T00:04:30+01:00 · **Branch:** `master` · **HEAD:** `1f8edc6`
**Agent:** Claude Code (Opus 5 / Sonnet 5)
**Previous handoff:** `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md`
**Status:** chunk complete (discussion, not code)

## Goal

Resume the prior Spec Navigation handoff. While verifying git state, unrelated uncommitted
work turned up in the tree, and untangling what it was led into a real, separate topic: the
user has been feeling friction using AgentWeave itself — specifically, having to design roles
before implementing anything — and wanted to pressure-test whether that friction is evidence
AgentWeave's whole multi-agent-first premise is the wrong one, using research they'd already
done on single-vs-multi-agent operating models. This session is that pressure-testing
conversation, not implementation work. **No files in this repository were edited.** The
Spec Navigation work (T10/T11) is exactly where the previous handoff left it.

## Current state

The strategy discussion ran to a resolved conclusion and is fully written up in two places
outside this repo's normal working tree:

- `C:\Users\huida\Documents\projects\AICollective\ResearchClub\agent-operating-model\agentweave-strategy-discussion.md`
  — the full discussion: diagnosis, market scan, decision framework, and the resolved
  conclusion. This is the source of truth; read it before continuing the strategy thread.
- `C:\Users\huida\.claude\projects\C--Users-huida-Documents-projects-AgentWeave\memory\project_strategy_pivot_discussion.md`
  — a persistent-memory pointer to the above, auto-loaded into future AgentWeave sessions via
  `MEMORY.md`.

**The conclusion reached** (see the strategy doc for full reasoning):

1. The friction has a concrete, code-grounded cause: `agentweave init`
   (`src/agentweave/cli.py:266-271`) defaults `mode="hierarchical"` and writes role files for
   a fixed agent roster **before any task exists**. `src/agentweave/roles.py` +
   `constants.py` define roles as job-title personas (`tech_lead`, `architect`, `backend_dev`,
   `frontend_dev`, `qa_engineer`) with no tool/permission/scope binding — personas, not
   capability contracts.
2. This is a **default-ordering bug**, not proof the substrate (task ledger, transport, Hub)
   is wrong. The fix direction, if/when implemented: single-agent-first at `init`, with
   delegation (mode/role) introduced per-task once a task passes a delegation test, not chosen
   once for the whole session. **This fix has not been implemented. It is a proposed
   direction only.**
3. A market scan (multi-harness coordination, session-handoff/memory tools, spec-driven-dev
   platforms, oversight/governance layers, skills/role marketplaces) found most of
   AgentWeave's candidate pivot directions already crowded by 2026 OSS tools (vibe-kanban,
   amux, ralphy, ai-memory, GitHub Spec Kit, Tessl, etc.). Two candidates looked genuinely
   uncontested: the spec navigator + AI-authoring UI, and the review/approval queue.
4. Decided **against** decomposing AgentWeave into multiple products and **against** a full
   pivot, for now — both are packaging decisions that would be made before there's real usage
   evidence, not after.
5. Decided **for**: fixing the `init`/roles default (not yet done), continuing to dogfood the
   Hub on real work (including finishing T10/T11), and — the final resolved point — testing
   the spec-UI idea as a **small, from-scratch side project**, explicitly *not* extracted from
   AgentWeave's existing `SpecFrame`/`SpecNavigator`/`specBridge` code (that extraction would
   itself be the decomposition-surgery cost this path is meant to avoid), scoped to the
   unvalidated piece (AI-assisted authoring, not navigation, which is already proven), with a
   real-pull signal defined before starting. **This side project has not been started.**

None of steps 2, 3 (implementing anything), or the side project have begun. This was entirely
a discussion-and-documentation session.

## Files touched

None in this repository (`AgentWeave`). Files written this session were outside it:

- `C:\Users\huida\Documents\projects\AICollective\ResearchClub\agent-operating-model\agentweave-strategy-discussion.md`
  — new file, created then updated with the resolved side-project conclusion. Finished for
  now; would need a further update if the strategy thread continues.
- `C:\Users\huida\.claude\projects\C--Users-huida-Documents-projects-AgentWeave\memory\project_strategy_pivot_discussion.md`
  — new memory file, created then updated to reflect the resolved conclusion. Finished.
- `C:\Users\huida\.claude\projects\C--Users-huida-Documents-projects-AgentWeave\memory\MEMORY.md`
  — one index line appended pointing at the memory file above. Finished.

This handoff file and `.claude/handoffs/LATEST.md` are the only writes inside this repo.

## Key decisions

- **The friction diagnosis was grounded in code before trusting it as real**, not accepted on
  feeling alone: read `cli.py:266-271` and `roles.py` directly to confirm `init` really does
  default to `hierarchical` mode + persona roles before a task exists. Rejected: taking the
  user's stated frustration as sufficient evidence without checking the actual default.
- **Decompose and pivot were both rejected as premature**, using the same discipline the
  user's own research applies to agent delegation ("don't add a worker until the task proves
  it needs one") applied one level up to product scope. Rejected: acting on the market scan's
  "open ground" findings as if they were demand signals — being less crowded is necessary but
  not sufficient evidence anyone wants it.
- **The side project must be built disconnected from AgentWeave's code**, not extracted from
  it, specifically so testing the idea doesn't itself incur the decomposition cost the whole
  discussion was trying to avoid paying prematurely. Rejected: reusing `SpecFrame`/
  `SpecNavigator`/`specBridge` directly, which are entangled with Hub auth/task/DB/manifest
  conventions.
- **The pivot discussion was documented as a standalone research file, not stuffed into
  narrow "memory" entries.** The persistent-memory system is for durable facts an agent
  should recall automatically, not a place for a multi-thousand-word discussion; the full
  reasoning lives in the user's own research repo (`AICollective/ResearchClub`) where it sits
  next to the source research it built on, and memory holds only a short pointer plus the
  headline conclusion.

## Constraints and user directives (verbatim)

From this session:

- `"I want to keep pressure testing this. Exhausting everything."` — the user's explicit mode
  for this whole conversation: thorough, skeptical discussion, not quick answers.
- `"I want to take all of this information and discussion and store it so we do not loose the
  main points."` — why the strategy doc and memory pointer exist.
- `"yeah update with this conclusion"` — confirmed the side-project resolution should be
  written into the strategy doc as final (for now).

Carried forward from the previous handoff and still binding on the Spec Navigation change
whenever that work resumes:

- `"Kimi's session-status service (task 3.10) is intentionally not implemented — do not
  silently implement it."`
- `"New commits, not amends."`
- `"Zero new runtime dependencies (stdlib only)."`
- The iframe spec-viewer sandbox and no-`allow-same-origin` constraint, and the rest of the
  approved `add-spec-navigation` spec's binding constraints — see the previous handoff for
  the full list, unchanged.
- Pushing has still not been requested. There are still **three unpushed commits**
  (`1f8edc6`, `3d9f6e8`, `f7cfc94`).

## Dead ends

None this session — no implementation was attempted, so nothing failed. (Prior session's
dead ends, e.g. PowerShell here-string syntax in the Bash tool, `cd hub/ui` persisting across
Bash calls, still apply and are recorded in the previous handoff.)

## Verification

Nothing to verify — no code was written or changed. Verified only:

- `git status --short` / `git diff --stat HEAD` / `git log --oneline -8` — confirmed HEAD and
  dirty-file state are unchanged from the previous handoff (see Git state below).
- Read `src/agentweave/cli.py:177-273` and `src/agentweave/roles.py:1-80` directly to confirm
  the `init` default and role-persona claims before writing them into the strategy doc.

**Explicitly NOT done this session:** no code changes, no tests run, no implementation of the
`init`/roles fix, no side project started, T10 (manual browser pass) and T11 (independent
review) on the Spec Navigation change remain exactly as untouched as in the previous handoff.

## Git state

- Branch: `master`.
- HEAD: `1f8edc6` ("Make the Hub spec viewer navigable") — **unchanged from the previous
  handoff.**
- Dirty, and **unexplained, unrelated to Spec Navigation or this session's discussion** — this
  was flagged to the user at the start of this session and is still unresolved:
  - Modified: `hub/hub/api/v1/agent_trigger.py`, `hub/hub/api/v1/agents.py`,
    `hub/hub/api/v1/tasks.py`, `hub/tests/test_agents.py`,
    `hub/ui/src/__tests__/agentStatus.test.tsx`, `hub/ui/src/__tests__/specChatSession.test.tsx`,
    `hub/ui/src/components/spec/SpecChatPane.tsx`, `hub/ui/src/lib/agentStatus.tsx` — a
    coherent, apparently-finished feature (agent-heartbeat "stalled" status detection plus a
    "queued but didn't start" chat warning) that is **not** the stalled-status feature the
    user later clarified was unrelated to their research topic — its origin is still unknown.
    The user said "It's no the stale status. Is something that came off out of a research
    that I did" when asked about it, meaning: this drift is confirmed **not** connected to the
    strategy research, but what it actually is / whether to keep, commit, or discard it was
    never resolved. Do not touch these files without asking first.
  - New: `hub/hub/agent_status.py` — the new module backing the above.
  - `.claude/handoffs/LATEST.md` — modified; will point at this handoff once written.
  - Untracked handoff files from the previous two sessions (see previous handoff).
- **Unpushed commits (3):** `1f8edc6`, `3d9f6e8`, `f7cfc94`. `origin/master` is at `f6663a9`.

## Next steps

1. **Ask the user which thread to resume**: (a) the Spec Navigation T10 manual browser pass —
   see the previous handoff's Next Steps §1 for the exact procedure — or (b) starting the
   spec-UI side project per the resolved conclusion above, or (c) implementing the
   `agentweave init` default-ordering fix, or (d) finally resolving what the unexplained
   `agent_status.py` / "stalled" drift actually is. Do not assume; the user has not indicated
   priority order among these as of this handoff.
2. If resuming Spec Navigation: read `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md`
   in full — this handoff intentionally does not repeat its content.
3. If starting the side project: read
   `AICollective/ResearchClub/agent-operating-model/agentweave-strategy-discussion.md`'s
   "Resolved: side project instead of decomposing or pivoting" section for the three
   conditions (build disconnected from AgentWeave's code, scope to the authoring gap only,
   define the pull signal before starting) before writing anything.
4. If implementing the `init` fix: re-read `src/agentweave/cli.py:229-273` and
   `src/agentweave/roles.py` fresh, since this handoff only cites specific lines rather than
   reproducing the surrounding logic — confirm the diagnosis still holds before changing
   behavior.

## Open questions for the user

- Which of the four threads above should the next session pick up?
- The unexplained heartbeat/"stalled" drift in the working tree — is it wanted work to finish
  and commit, or should it be discarded? (Carried forward, still unanswered.)
- Should the three unpushed Spec Navigation commits be pushed to `origin/master`? (Carried
  forward, still unanswered.)

## Read on resume

- `AICollective/ResearchClub/agent-operating-model/agentweave-strategy-discussion.md` — the
  full strategy discussion and resolved conclusion; read this first if continuing the
  strategy thread.
- `AICollective/ResearchClub/agent-operating-model/single-vs-multi-agent-research.md` — the
  underlying research the whole discussion was pressure-testing.
- `.claude/handoffs/2026-07-29-2110-spec-navigation-t1-t9-implemented.md` — the previous
  handoff; read this first if resuming Spec Navigation T10/T11 instead.
- `src/agentweave/cli.py` (around line 177-273) — the `init`/mode-default code the diagnosis
  is grounded in, if implementing the fix.
- `src/agentweave/roles.py` and `src/agentweave/constants.py` — the persona-based role
  definitions, if implementing the fix or scoping what "capability-bound roles" would mean.
