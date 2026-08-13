# A posture that survives the handoff

## Why

Found by driving the product end to end
(`openspec/explorations/2026-08-13-explore-to-development-end-to-end.md`). Two defects, independent
in the code and compounding in practice.

**An agent could write code and never run it.** A non-yolo Claude run with no operator choice gets
`--permission-mode acceptEdits`. That accepts edits and still prompts for `Bash` — and headless
there is nothing to answer the prompt. Observed twice, both times reported honestly by the agent:

> *"every `python`/`py` invocation in this session … is blocked with 'This command requires
> approval', and there's no interactive user available to grant it … this should be treated as
> unverified-by-execution."*

Same agent, same code, `permission_mode: workspace`: **14/14 tests ran and passed.**

The rationale recorded when this default was chosen says `acceptEdits` replaced `manual` so that a
run "can do work". Running the tests *is* the work — a spec-driven loop whose builder cannot produce
evidence is the failure the loop exists to prevent. It is also **runner-dependent**: the Codex
reviewer executed freely throughout the same run, so whether an agent can verify its own output
depends on which CLI it happens to be bound to.

**And the operator's choice silently disappears at a handoff.** Runtime overrides live on the
conversation, and every trigger without a `conversation_id` opens a *new* one:

| conversation | how it started | overrides |
|---|---|---|
| `conv-1ab659d3` | operator's composer | `{"permission_mode": "workspace"}` |
| `conv-3c7a302c` | peer message from the reviewer | **`None`** |

So the operator picks a posture, the builder hands work to the reviewer, the reviewer messages back,
and the resulting run has a posture the operator never chose — reverting to the one it cannot
execute under. The UI always sends a `conversation_id`; jobs and peer messages do not.

## What Changes

- **The default Claude posture becomes `workspace`.** The Hub answers each request against the run's
  own worktree, which is *stricter* than `acceptEdits` for writes — that mode accepts edits with no
  boundary check at all — and permits the execution an agent needs to verify itself.
- **The default degrades safely.** `workspace` is `manual` plus an answerer, and the answerer is the
  Hub's MCP server. A run configured without that server keeps `acceptEdits`, because naming an
  approver that is not there refuses *everything* — the failure this replaces, reintroduced.
- **A conversation opened by a peer message or a scheduled job inherits the agent's most recent
  runtime overrides**, so a posture chosen in the composer survives the hop to a run the operator
  did not start. A conversation the *operator* opens still begins clean — that is a deliberate,
  specified property (`agent-conversation-workspace`), and it holds because the operator is at the
  composer and can choose. Nobody is, when a peer or a job opens one.
- **`bypassPermissions` is never inherited.** Full access is a deliberate act for a thread the
  operator is watching; propagating it into runs they did not start is the one case where carrying
  the choice forward is clearly wrong.

## Capabilities

### Modified Capabilities

- `agent-run-sandboxing`: the default posture SHALL permit an agent to verify its own work.
- `agent-conversation-workspace`: a conversation opened by a peer or a job SHALL inherit the agent's
  most recent overrides; one the operator opens SHALL continue to begin clean.

## Impact

**Behaviour** — a Claude agent can run its own tests without the operator choosing anything, and a
peer-triggered run keeps the posture the operator set.

**Security** — the default becomes *narrower* for writes: `acceptEdits` performed no path check,
`workspace` refuses anything resolving outside the run's workspace. It is wider for execution, and
deliberately so; isolation is carried by the agent's own git worktree, which this does not change.

**No migration, no schema, no UI.**

## Non-Goals

- **Not changing what `workspace` allows.** `_decide` is unchanged; only which runs get it by
  default.
- **Not settling whether a peer message should reuse the agent's conversation entirely.** That is a
  broader question about threading and cold starts, still open. This change carries the *overrides*
  across the gap without deciding the thread's identity.
- **Not making overrides agent-global.** They stay per-conversation; an inheriting conversation
  copies a starting point rather than reading a shared setting.
- **Not changing what the operator's own new conversation does.** `agent-conversation-workspace`
  already requires it to begin clean, and a test pinned it. That requirement was right for the case
  it described and is left intact — this change adds the case it did not describe.
