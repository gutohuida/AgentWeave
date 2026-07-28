# Design

## Context

`SpecPage.tsx` sends every message with `session_mode: 'new'`. Everything below the
UI already supports resume, so this is a UI-only defect.

The resolution chain, confirmed end to end:

```
SpecPage  ──POST /api/v1/agent/trigger──▶  agent_trigger.py
                                              │
        session_mode=="resume" && session_id ──┼──▶ append "[Session: <id>]"
        session_mode=="new"                  ──┼──▶ append "[NewSession]"
        session_mode=="resume" && no id      ──┴──▶ (no tag)
                                              │
                                              ▼
                                        watchdog.py
        "[Session: <id>]"  ──▶ resume that id
        "[NewSession]"     ──▶ session_id = None  (new)
        (no tag)           ──▶ _load_agent_session(agent)   ← the desired path
                                   │
                                   └─ returns None if the agent has no saved session
```

`_load_agent_session` / `_save_agent_session` persist one session id per agent in
`.agentweave/agents/<agent>-session.json`. This is runner-agnostic; each runner's
resume flag and session source are declared in `RUNNER_CONFIGS`.

## Goals / Non-Goals

**Goals**

- A multi-turn conversation in the Spec tab keeps its context.
- A user can pull a warm agent into the Spec tab and keep talking to it.
- No runner-specific handling in the UI.

**Non-Goals**

- Spec-scoped sessions, a session picker, or session naming.
- Any change to context tracking or automatic session reset.

## Decisions

### Send `resume` with no `session_id`, rather than resolving an id in the UI

The alternative is to fetch the agent's sessions in the UI (as `AgentOutputPanel`
does), take the newest, and send it explicitly. Rejected because:

- It duplicates in TypeScript a resolution rule that already exists in the watchdog,
  creating two places to disagree.
- It requires the Spec tab to load and track session state it otherwise does not need.
- The untagged path is the documented fallback in `agent_trigger.py` and is already
  the behaviour for CLI-originated triggers, so using it keeps surfaces consistent.

Trade-off: the UI cannot display *which* session id will be resumed without a
separate query. Accepted — the requirement is only that continuity is apparent, not
that the id is shown.

### "New session" is a one-shot user action, not a persistent mode

A persistent "always new" toggle would reintroduce the current bug as an option and
invites the user to leave it on by accident. Instead the user explicitly starts a
fresh session; the following message resumes it like any other.

This means the flag must be cleared after the message that consumes it.

### Do not associate sessions with spec documents

Considered keying the resumed session on `(agent, specPath)`. Rejected because the
user explicitly wants cross-context resume: grabbing an agent that was working on
something else and continuing that conversation in the Spec tab is a feature, not a
leak. It also keeps this change to the UI.

## Risks

| Risk | Mitigation |
|---|---|
| A resumed session grows without bound; there is no reliable context percentage today, so the user gets no warning before hitting a wall | The deliberate new-session control is the manual escape. Automatic reset depends on the separate context-tracking work and is explicitly out of scope. |
| The resumed session may be unrelated to the open spec, which could confuse a user who expected spec-scoped chat | Accepted by design; the visible session-continuity indicator makes the state legible. |
| A stale saved session id may no longer be resumable by the underlying CLI | Pre-existing behaviour shared with the Agents tab and CLI triggers; not introduced here. Worth verifying that a failed resume surfaces an error rather than silently producing an empty run. |

## Migration

None. No schema, API, or config changes.
