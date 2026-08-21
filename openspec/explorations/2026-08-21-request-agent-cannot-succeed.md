# Exploration — `request_agent` is advertised to every agent and cannot succeed (2026-08-21)

**Status:** OPEN. Found while sweeping `new_conversation` call sites for `conversations-continue`.
The operator's reaction — *"I don't think I use this endpoint anymore this is some legacy stuff"* —
is right, and the measurement is stronger than that: it is not merely unused, it **cannot work.**

## The chain

`request_agent` is one of the 20 agent-callable MCP tools (`hub/hub/mcp_server.py:494`), described
to every agent as *"Request a new agent from a pre-approved template under the project agent
budget."* It posts to `/agents/request`, which resolves the template like this:

```
hub/hub/api/v1/agents.py:1360
    session_data = await _get_session_data(project_id, session) or {}
    templates = session_data.get("agents", {}) or {}
    template_config = templates.get(body.template)
    if not isinstance(template_config, dict):
        raise HTTPException(400, f"Agent template '{body.template}' is not pre-approved …")
```

`_get_session_data` (`agents.py:111-121`) reads the `ProjectSession` table, and says where the rows
come from:

> *"Populated by the CLI/watchdog via `push_session()` on every session save."*

**The watchdog was deleted.** `CLAUDE.md` lists it under "Deleted, and not to be recreated:
`watchdog.py`, `messaging.py`, `runner.py`, `transport/local.py`, `transport/git.py`, and the role
subsystem."

What survives is a stub with nothing driving it. `push_session` still exists in
`src/agentweave/session.py:387` and `transport/http.py:530`, reached from `Session.save()` at
`session.py:153` — but the CLI is down to five commands (`status`, `doctor`, `stop`, `hub_start`,
`reset`), and **none of them constructs or saves a `Session`**. Verified: no `Session(` and no
`.save()` anywhere in `src/agentweave/cli.py`.

So:

```
   agent calls request_agent
        │
        ▼
   POST /agents/request
        │
        ▼
   _get_session_data → ProjectSession   ── 0 rows, always ──┐
        │                                                   │
        ▼                                                   │
   templates = {}                                           │
        │                                                   │
        ▼                                                   ▼
   400 "template '<x>' is not pre-approved for this project"
```

Measured: `project_sessions` held **0 rows** in the beta database before it was rebuilt, and holds 0
now. There is no writer left, so it stays 0.

## Why this matters more than a dead endpoint

The tool surface has a requirement about exactly this shape —
`agent-tool-surface`, *"An endpoint the harness calls is not advertised as a capability"* — written
when `approve_tool_call` was found sitting in the agent's tool list. The reasoning generalises: a
tool an agent is told it has, but which cannot succeed, costs more than an absent one.

- It occupies a slot in every agent's tool list, on every turn, in every project.
- An agent that reaches for it burns a turn on a 400 whose message (*"not pre-approved for this
  project"*) reads like a **permissions** problem the operator could fix, not a dead path. A
  capable agent will reasonably ask the operator to pre-approve a template — and there is no
  surface anywhere that does that.
- It is the only remaining consumer of `ProjectSession`, which is itself a survivor of the deleted
  session subsystem. The dead tool is what keeps a dead table looking load-bearing.

## An adjacent defect, noted and deliberately not fixed

The same code path opens a conversation for the requested agent
(`agents.py:1403`, `origin="peer"`) and never sets `bound_sender_conversation_id`, even though the
requester's conversation is on hand three lines below (`conversation_id=source_run.conversation_id`,
line 1416). Under the binding contract that means the requesting agent's first follow-up message
would miss the binding and open a *second* thread — the same defect
`conversations-continue` fixes elsewhere.

It is **not** being fixed there, because the line is unreachable: the 400 fires before it. Recorded
so that whoever revives or removes this path knows the bug is sitting in it.

## Open questions

1. **Remove, or revive?** Operator-driven agent creation already exists and works
   (`operator-agent-creation`). Is agent-driven creation still wanted at all, or was it always a
   feature of the deleted roster subsystem?
2. If revived, **what is the template source?** `ProjectSession` is the wrong home — it is the last
   fragment of the CLI session model the Hub replaced. Charters and runners are the current way a
   project describes what an agent should be, and a "pre-approved template" is plausibly just a
   (runner, charter) pair.
3. If removed, does `ProjectSession` and the `session_sync` route go with it? `request_agent` and
   `/agents/configured` (`agents.py:134`) appear to be its only readers.
4. Is anything else in the 20 advertised tools in the same state — reachable in code, unreachable
   in practice? This one was found by accident while looking for something else, which is not a
   method.

Question 4 is the one worth acting on regardless of what happens to `request_agent`.
