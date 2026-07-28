## Why

The Hub Spec tab hardcodes `session_mode: 'new'` on every message sent to the spec
agent (`hub/ui/src/components/spec/SpecPage.tsx`). Each message therefore spawns a
brand-new CLI session: the agent re-reads its role, re-inventories `spec/`, and has no
memory of the spec under discussion. A multi-turn conversation about one spec is
impossible — every turn starts from zero.

This is specific to the Spec tab. The Agents tab does it correctly
(`hub/ui/src/components/agents/AgentOutputPanel.tsx`), which is why the bug is not
visible there.

The whole resume path below the UI already works and is runner-agnostic:

- `POST /api/v1/agent/trigger` (`hub/hub/api/v1/agent_trigger.py`) appends
  `[Session: <id>]` when `session_mode == "resume"` **and** a `session_id` is present,
  `[NewSession]` when `session_mode == "new"`, and **no tag otherwise**.
- The watchdog (`src/agentweave/watchdog.py`) treats an untagged message as
  "fall back to the agent's last saved session" via `_load_agent_session(agent)`,
  which returns `None` when the agent has no saved session.
- Every runner already declares a resume flag and a session source in
  `RUNNER_CONFIGS` (`src/agentweave/constants.py`): claude/claude_proxy/native
  `--resume`, kimi `--session` / `-S`, opencode `--session` (stable IDs), codex
  `exec resume`, copilot `--resume=`.

So sending `session_mode: 'resume'` **without** a `session_id` already produces exactly
the desired behaviour — resume the agent's most recent session, or start a new one if
there isn't one — for every runner, with no runner-specific work.

## What Changes

- The Spec tab MUST send `session_mode: 'resume'` and MUST NOT send a `session_id`,
  so the watchdog resolves the agent's last saved session.
- The Spec tab MUST provide a way to deliberately start a fresh session, because
  resume-always leaves no escape from a long or derailed session.
- No backend, watchdog, runner, or transport changes.

## Non-Goals

- Associating a session with a particular spec document. Resuming whatever the agent
  was last doing is desirable: it lets the user pull a warm agent into the Spec tab
  and continue talking to it.
- A session picker in the Spec tab. That belongs to the separate session-lifecycle
  work, and adding one here would add chrome to a pane that is already too wide.
- Fixing context tracking. A resumed session grows monotonically and there is no
  reliable context percentage today; that is tracked as its own change and is a
  prerequisite for any automatic session-reset behaviour.

## Capabilities

### New Capabilities

- `spec-chat-session`: How the Hub Spec tab's embedded agent chat selects and
  continues an agent session.
