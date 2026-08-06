# Agent-to-agent messaging actually reaches the Hub

**Approved:** 2026-08-06, operator

## Why

Agent-to-agent collaboration — the feature the whole product is named for — does not work. An
operator asks one agent to message another, the agent tries, and the message never arrives.

This was reproduced end-to-end on 2026-08-06 against a real local Hub with two Codex agents
(`codex-mini-1`, `codex-mini-2`, provider `codex`, model `gpt-5.4-mini`). It is not one bug. It is
two independent defects stacked on top of each other, and the first completely hides the second.

### Defect 1 — Codex silently auto-denies every AgentWeave tool call

The agent's own transcript:

```
Called agentweave.send_message
agentweave.send_message: user cancelled MCP tool call
Called agentweave.send_message
agentweave.send_message: user cancelled MCP tool call
```

`_build_codex_command` (`hub/hub/runner_commands.py`) registers the AgentWeave MCP server, then
spawns `codex exec` with `--sandbox workspace-write` and no approval configuration. `codex exec` is
non-interactive, so there is no operator present to approve a tool call; the approval request is
resolved as cancelled and the tool call dies. The Hub configured a tool surface the agent can see
and enumerate but cannot invoke.

The agent's own summary of the failure was *"the AgentWeave MCP call was cancelled by the tool
backend each time"* — it then offered to let the operator paste the message manually. Nothing
anywhere in the Hub recorded that a tool call had failed. The operator's only signal was a message
that never arrived.

Approval is only bypassed when an agent has `yolo` set, which adds
`--dangerously-bypass-approvals-and-sandbox`. That flag also removes the filesystem sandbox. The
Hub therefore currently offers exactly two states: *sandboxed and unable to collaborate*, or
*able to collaborate and completely unsandboxed*. Collaboration is not a dangerous capability and
must not be priced at the sandbox.

**This is a property of `codex exec`, not of Codex.** Measured against the CLI, no `exec`
configuration grants MCP tool calls while keeping the sandbox. But `codex app-server` — a
JSON-RPC protocol with a client attached — sends each approval to the client individually, and
was verified to let the Hub approve its own MCP server's tool calls while denying a write outside
the workspace in the same turn. The fix is therefore to change transport, not to loosen a policy.
See design.md Decision 1a.

### Defect 2 — the Hub tells agents to call a URL it is not serving

With `yolo` enabled the call left the agent and reached *something*:

```
Error calling tool 'send_message': Hub API error 405: Method Not Allowed
```

`hub/hub/api/v1/agent_trigger.py` builds the agent's callback URL as:

```python
env["HUB_URL"] = os.environ.get("HUB_URL", f"http://{host}:{settings.aw_port}")
```

`settings.aw_port` defaults to `8000` and is a *configuration* value. It is not the port the server
is actually bound to. The Hub under test was serving on `8010` (started with `uvicorn --port 8010`,
a CLI argument that never touches `settings`), so every agent it started was told to call
`http://127.0.0.1:8000`.

On this machine port 8000 was held by an **older, unrelated AgentWeave Hub** running in Docker,
still serving the removed `data-theme="cosmic"` UI. The agent's authenticated action was delivered
to the wrong Hub instance, which lacked the route and answered 405.

The mis-delivery is the serious part. The 405 was luck: an older Hub happened to reject it. A Hub
of a compatible version on that port would have **accepted the write** — the agent's message, task,
or question would have landed in a different project's database, attributed to a run that instance
never started. A process must not derive its own address from a default.

### Defect 3 — a failed tool call is invisible to the operator

Across both defects, the Hub recorded nothing. No event, no diagnostic, no banner. `send_message`
returning `{"success": True}` unconditionally on the happy path and raising an opaque
`RuntimeError` otherwise means neither the agent nor the operator can distinguish "the recipient
does not exist" from "your Hub is misconfigured" from "the call was denied before it left the
process."

## What changes

- **The Codex runner moves from headless `exec` to the `app-server` protocol.** The Hub becomes the
  client that answers approvals: it approves tool calls for the one MCP server it installed and
  answers everything else according to the sandbox the operator selected. Codex agents can
  collaborate with the sandbox fully intact, and `yolo` is not required for messaging.
- **The Hub derives the agent callback URL from the address it is actually serving on**, never from
  a configured default. If it cannot determine that address it refuses to start the run rather than
  handing out a guess.
- **A run's credential is only honoured by the Hub that minted it.** An agent action delivered to a
  different Hub instance is rejected as unattributable instead of being executed.
- **A failed agent tool call becomes a recorded, visible event** with the reason preserved, surfaced
  on the agent's timeline the same way other run failures are.
- **The auto-provisioned runner name stops being mojibake.** Runner names are currently written with
  a mis-encoded em dash (`Codex CLI â€” GPT-5.4-Mini`) — see design.md.

## Impact

- **Affected specs:** `agent-tool-surface`, `runtime-diagnostics`
- **Affected code:** `hub/hub/runner_commands.py`, `hub/hub/runner_parsing.py`,
  `hub/hub/api/v1/agent_trigger.py`, `hub/hub/api/v1/agents.py`, `hub/hub/mcp_server.py`,
  `hub/hub/agent_auth.py`, `hub/hub/config.py`; a new app-server JSON-RPC client module
- **Scope note:** section 2 is a transport rearchitecture of the Codex runner, not a flag change.
  Section 3 (the callback address) is independent, much smaller, and should land first.
  `codex app-server` is marked experimental; the `exec` path is kept until the new path is verified
  equivalent.
- **Not affected:** the transport layer, the CLI, and the messaging data model — the message
  never reached `create_message_for_actor`, whose logic is correct.

## Out of scope

- The `Run` identity staleness check in `create_message_for_actor` (`hub/hub/api/v1/messages.py`)
  that raises `409 "Message run identity is invalid or stale"`. It was suspected during
  investigation and cleared — no reproduction reached it. It is left alone deliberately.
- Docker-mode messaging. Per the operator's standing direction, Docker mode is not exercised.
