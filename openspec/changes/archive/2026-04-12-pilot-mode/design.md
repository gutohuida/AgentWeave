## Context

AgentWeave sessions currently assume all agents are automated — the watchdog polls for new messages and tasks, then fires the appropriate agent CLI without human intervention. There is no concept of a human-operated agent that participates in the session on its own schedule.

The existing `manual` runner type exists for copy-paste relay (e.g. Cursor), where there is no CLI and no session. Pilot mode is distinct: the agent has a running CLI session and full MCP connectivity, but it is driven by a human who decides when to pull their inbox and when to respond.

Per-agent context is already injected via `--append-system-prompt-file .agentweave/agent-context/{agent}.md` when the watchdog launches automated agents. This same file and mechanism is reused for pilot agents — nothing new is invented.

## Goals / Non-Goals

**Goals:**
- Allow any agent to be marked `pilot: true`, suppressing all auto-execution by the watchdog
- Allow a pilot agent to register its active `--resume` session ID with the Hub (one-time, replaceable)
- On registration, regenerate `.agentweave/agent-context/{agent}.md` with current roles and print the ready-to-use launch command
- Expose pilot flag and session registration in Hub UI (badge, form, disabled trigger button)
- Work for any runner type — native, claude_proxy, kimi, manual

**Non-Goals:**
- Heartbeat / liveness tracking for pilot agents
- Notifications pushed to the human when new messages arrive (the human polls manually)
- Any change to how other agents send messages (senders are unaware of pilot mode)
- Multi-session history — only the latest registered session ID is stored

## Decisions

### D1: Flag not runner type
`pilot` is a boolean on the existing agent config, not a new runner value. This allows multiple agents of different runner types to be pilot simultaneously (e.g. two developers each running their own Claude session on a shared Hub project).

Alternatives considered:
- New runner `interactive` — rejected because it conflates execution method (how the CLI is invoked) with control model (who decides when to invoke it)

### D2: Silent inbox — no sender acknowledgment
When a message is sent to a pilot agent, it is stored exactly as for any other agent. The sender receives no special status or acknowledgment. This keeps the messaging protocol uniform and avoids complexity around "delivery pending human review" states.

Alternatives considered:
- Return a `pending_human_review` status to senders — rejected; adds protocol complexity with no benefit since all AgentWeave messages are already async

### D3: Watchdog guard placement
The pilot check happens in the watchdog's HTTP poll path (`_check_once_http`) before the agent CLI is invoked. The message is still created in the Hub DB (so it appears in inbox) — only the execution step is skipped.

For the Hub-side trigger endpoint (`POST /api/v1/agent/trigger`), the endpoint still creates the message, but returns a response indicating the agent is in pilot mode. No execution is attempted.

### D4: Session registration regenerates agent-context file
`register_session` regenerates `.agentweave/agent-context/{agent}.md` with current roles as a side effect. This ensures the printed launch command is immediately usable — the user gets accurate context without a separate step.

### D5: Kimi pilot launch command
Since `--agent-file` is not used (kimi expects YAML, we use markdown), the kimi pilot launch command uses the same role-injection-into-prompt approach as automated kimi runs. The printed launch command for kimi includes `-p` with a preamble sourced from the agent-context file.

### D6: Hub DB — extend Agent model
`pilot` (Boolean, default False) and `registered_session_id` (String, nullable) are added to the existing Agent model rather than a new table. Agent records are created on first heartbeat/sync; pilot settings are updated via dedicated endpoints.

## Risks / Trade-offs

- **Stale session ID**: If a pilot registers sess-A then starts a new session sess-B without re-registering, the Hub shows the wrong session ID. Mitigation: print a reminder on startup to re-register, and make re-registration trivial (one MCP call or CLI command).
- **Pilot agent never processes inbox**: Messages accumulate indefinitely if the pilot never logs on. Mitigation: no automatic pruning — this is by design. The watchdog stale-message ping mechanism still fires for all agents, including pilots (it prints a warning but does not auto-execute).
- **Session.json vs Hub DB drift**: `pilot` flag lives in both `session.json` and Hub DB. If they diverge, Hub takes precedence for trigger decisions; local session.json governs watchdog behavior. Mitigation: `session.save()` already pushes to Hub via `_push_session_to_hub` — ensure pilot flag is included in that sync.

## Migration Plan

1. Deploy Hub with new DB columns (`pilot`, `registered_session_id`) — existing agents default to `pilot: false`, `registered_session_id: null`. No data migration needed.
2. Publish updated CLI with pilot flag support. Existing `session.json` files without `pilot` key default to `false` — backward compatible.
3. No breaking changes. Existing sessions, runners, and watchdog behavior are unchanged for non-pilot agents.

## Open Questions

- Should the Hub UI show a visual indicator (e.g. "inbox: 3 unread") on the pilot agent card? Out of scope for this change but natural follow-on.
- Should `agentweave watch` print a note when it skips a pilot agent's message? Leaning yes — useful for debugging.
