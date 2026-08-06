# An agent can act, knows where it is, and is told what its tools accept

**Approved:** 2026-08-06, operator

## Why

Operator testing of `proj-84d218db` (2 Claude/haiku, 2 Codex/gpt-5.4-mini) against a sixteen-item
list found eleven items passing and three failing. Diagnosing the three surfaced a fourth problem the
operator named directly:

> "this should be in the 'base knowledge' of every agent when it starts in the repo. To understand it
> works within agent tree. We have to review all the base files generated in agentweave that teach
> the context tools etc. We need a complete overhaul because so much has changed."

### A Claude agent cannot write a file, for two compounding reasons

A non-yolo Claude run is launched with `--permission-mode manual` (`hub/hub/runner_commands.py`,
introduced by `2026-08-06-claude-non-yolo-permission-mode`). `manual` means *ask the operator*. The
Hub spawns headlessly, there is no terminal, and no operator-facing approval surface exists — so
nothing can ever answer. Ground truth from `agent_outputs`, not the agent's own paraphrase:

```
Read  agentweave-testbed\.agentweave\context\haiku-2.md
  -> Claude requested permissions to read from ..., but you haven't granted it yet.
Read  agentweave-testbed\README.md   -> same
Write agentweave-testbed\notes.md    -> same (three attempts)
```

That change's own `design.md` recorded this as an open question — *"Whether `manual` is the right mode
for a fresh install … was never directly measured"*, and deferred any operator-facing refusal surface
to `2026-08-06-operator-in-the-loop-turns`. It has now been measured: `manual` is unusable without
that surface, which remains deferred.

**The second cause is separate and was not anticipated.** Every denied path above is the *project
root*, but the agent's working directory is its isolated git worktree
(`.agentweave/worktrees/haiku-2`) — proven by the same run's `Bash cat notes.md`, which executed
normally and reported "No such file". `README.md` and the context file both exist *inside* the
worktree. The agent addressed the project root because **nothing tells it otherwise**:
`worktrees.resolve_agent_workspace` puts a writing agent on its own branch in its own directory and
passes that path only as the process `cwd`. It appears in no prompt, no context section, and no
charter. The Codex agent in the same test succeeded solely because it happened to use a relative path.

### Codex's first `send_message` fails every time

`send_message`'s `message_type` is declared `message_type: str = "message"`
(`hub/hub/mcp_server.py:112`) — a bare `str`, no `Literal`, no parameter description. The MCP schema
therefore advertises `{"default": "message", "type": "string"}` and nothing else. The Hub then enforces
a hard allow-list server-side and returns 422:

```
type must be one of ['message', 'delegation', 'review', 'discussion', 'direct_trigger']
```

Across every recorded call: Claude *omits* the parameter and always succeeds; Codex *fills it in* with
`"text"`, gets the 422, retries with `"message"`, and succeeds. This is not a weaker model — it is a
schema that tells no client what the valid values are. Three sibling tools share the defect:
`create_task(priority)`, `create_job(session_mode)`, and `update_task(status)`, which has **no default
at all** and an eight-value lifecycle, so a model has no choice but to guess.

### The conversation does not follow new output, and opens at the oldest message

The autoscroll effect depends on `lines` — the legacy raw output log from `useAgentOutput`. What the
view actually renders is `timelineEntries` from `useAgentChatHistory`/`useAgentRecentChat`. New
conversation content therefore grows the DOM without ever firing the effect. Separately, nothing
scrolls to the bottom when a conversation is opened or switched; that code does not exist.

Both defects predate `2026-08-06-hub-collaboration-and-conversation-fixes`, but rendering every turn
expanded made them plainly visible where the content used to fit on a screen. The existing test passes
only because it drives new content through `outputLines`, never through the entries the timeline
renders — it validates the wrong dependency.

### What agents are told is stale, and one line of it is actively harmful

An audit of every string that reaches a model found:

- **No statement of the working directory or the worktree**, as above.
- **A line that is worse than absent.** The context emits ``- Canonical runtime context:
  `.agentweave/context/{agent}.md` `` — pointing the agent at a file whose contents it has *already
  received* as its system prompt. That is exactly the file `haiku-2` then tried to read, producing the
  first permission denial of the session.
- **A tool surface that is named but never specified.** The turn preamble lists four tool names with
  no parameters and no valid values — the other half of why Codex guessed `"text"`. Four further tools
  (`create_job`, `delete_job`, `toggle_job`, `run_job`) are never mentioned to agents at all.
- **All 21 seeded charters are stale, and charter text is inlined into the model context** — so this
  is live instruction, not documentation. Nearly every one opens with `Read roles.json, protocol.md,
  shared/context.md`, files the Hub has never created. Several reference `agentweave.yml`,
  `agentweave status`, and a "principal"; `spec.md` references the removed watchdog.
- **The CLI-fallback preamble names commands that no longer exist.** `access_path_notice`'s non-MCP
  branch instructs `agentweave msg send`, `task create`, `question ask`, `agent request`; `cli.py` was
  reduced to five commands on 2026-08-03.
- **`post_new_session_request`** still tells the agent "Your principal will start a fresh session."

## What changes

1. Claude gets a working non-yolo default (`acceptEdits`) and a per-conversation permission control
   beside Model and Effort.
2. Every constrained MCP tool parameter declares its valid values in the schema.
3. The conversation follows new output and opens at the newest message, with a jump-to-bottom control.
4. Canonical context states where the agent is, what its tools accept, and stops pointing at its own
   context file.
5. The seeded charters stop instructing agents to read files that do not exist.

## Impact

- **Affected specs:** `agent-run-sandboxing`, `agent-tool-surface`, `agent-context-onboarding`,
  `agent-conversation-workspace`, `agent-charter`.
- **Affected code:** `hub/hub/model_catalog.py`, `hub/hub/runner_commands.py`,
  `hub/hub/mcp_server.py`, `hub/hub/api/v1/agents.py`, `hub/hub/launchability.py`,
  `hub/hub/agent_status.py`, `hub/hub/data/charters/*.md`,
  `hub/ui/src/components/agents/AgentOutputPanel.tsx`, `src/agentweave/constants.py`.
- **Behaviour change:** a non-yolo Claude agent can now edit files in its own workspace without
  configuration. This is the intended product behaviour; the worktree remains the isolation boundary,
  and `manual` stays selectable for a deliberately locked-down turn.
- **No migration.** The permission control is a per-conversation override stored in the existing
  `Conversation.runtime_overrides`; absent one, the new default applies.

## Explicitly not in this change

- **The Hub-answered permission approver.** Claude's hidden `--permission-prompt-tool` flag would let
  the Hub answer each request itself, mirroring `codex_appserver.decide_approval` and giving true
  parity. Verified available (absent from `--help`, registered with `.hideHelp()`, accepts a value).
  Deferred to its own change by operator decision.
- **Deleting `src/agentweave/templates/`.** All 33 files are orphaned — `get_template` and its
  siblings have zero call sites outside their own module and two tests, and neither the Hub nor the
  five-command CLI writes them. Removal (keeping `handoff.md` and `resume.md`) is its own change.
