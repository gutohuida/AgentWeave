# Implications of moving Codex to `app-server`

Companion to `design.md` Decision 1a. Decision 1a is one sentence to state and a different shape of
runner to build. Everything here is a consequence implementation must answer deliberately — the cost
of the change is almost entirely in these, not in the JSON-RPC plumbing.

## 1. The process model inverts

`codex exec` is a **one-shot subprocess per turn**: spawn, stream stdout, exit. Its lifetime *is* the
turn, so "turn finished" and "process gone" are the same event and neither can leak.

`codex app-server` is a **persistent peer** holding threads and turns. Turn completion no longer
implies process exit. Two options, and the choice is load-bearing:

- **Per-turn process** — spawn app-server, `thread/start` or `thread/resume`, one `turn/start`, then
  shut down. Keeps today's lifecycle exactly, so nothing else in the Hub changes. Pays process
  startup per turn and gives up the protocol's main advantage.
- **Per-agent long-lived process** — one app-server per agent, reused across turns. Much better
  latency and the natural fit for steering and interruption, but introduces a process registry,
  health checks, restart, and orphan reaping the Hub has never needed.

**Recommendation: per-turn first.** It makes this a transport swap rather than a lifecycle rewrite,
and it can be verified against today's behaviour one-for-one. Long-lived processes are a follow-on
with their own evidence.

Either way the Hub gains a failure class it does not have today: **an app-server process that
outlives its turn.** Orphan reaping becomes a requirement, not housekeeping.

## 2. Silence becomes a deadlock

The most important operational consequence.

Under `exec` the Hub is a passive reader; if it stops reading it loses output. Under `app-server` the
Hub is a **counterparty with an obligation**. The server blocks on `mcpServer/elicitation/request`
and on every `*/requestApproval` until the client answers. A request the Hub fails to answer —
because it did not recognise the method, because a handler raised, because the reader thread died —
**hangs the turn indefinitely.**

The turn does not fail. It stops. Nothing times out on its own, and the agent looks busy forever.

Therefore:

- Every server-to-client request SHALL be answered, including unrecognised ones.
- The default answer for anything unrecognised is **deny** — never approve, and never nothing.
- Answering must not depend on the happy path. An exception raised inside a handler must still emit a
  denial before it propagates.
- The Hub keeps its own turn deadline, because the protocol supplies none.

## 3. The approval handler is a security boundary written in Hub code

Under `exec` the sandbox decision was a CLI flag. Under `app-server` it is **a function in the Hub**
deciding, per request, what an agent may do. That is a materially larger surface:

- Approve `mcpServer/elicitation/request` only when `_meta.codex_approval_kind` is `mcp_tool_call`
  **and** `serverName` matches the server the Hub registered. Both conditions, not either.
- The server name is Hub-supplied at spawn so it is not agent-controlled — but the check must be
  against the Hub's own registered name rather than a hardcoded literal, so the two cannot drift.
- Command, file-change, and permissions approvals follow the operator's sandbox selection. They are
  not tool-surface concerns and must not inherit the tool surface's approval.
- Approving a tool call MUST NOT be reusable as approval for anything else. The observed
  `_meta.persist: ["session", "always"]` shows the protocol offers persistence of a decision; the Hub
  should not use it without first deciding what a persisted approval means across turns.

## 4. Output parsing is replaced, not adapted

`runner_parsing.py`'s Codex path exists to reconstruct meaning from `--json` stdout. The protocol
supplies that meaning directly — `item/started`, `item/completed`, typed thread items, and
`turn/completed` carrying `usage` with real token counts.

A genuine improvement and a genuine risk: both paths must produce the *same* timeline, output
records, and usage accounting, or every downstream consumer shifts underneath. The mapping needs its
own tests, and keeping the `exec` path alive (task 2.8) is what makes a side-by-side comparison
possible.

`turn/completed.usage` may make the Codex context-window catalog lookup redundant. That interacts
with `2026-08-04-hub-model-control-and-provisioning` and should be checked, not assumed.

## 5. Session identity changes shape

`exec` resumes via `codex exec resume <session_id>`. `app-server` has `thread/start`,
`thread/resume`, and thread IDs of its own.

**Existing stored Codex session identifiers may not be resumable through the new path.** Establish
this rather than hope: if they are not, every existing Codex conversation either migrates or breaks,
and which one happens is an operator-visible decision. Verify before implementing; record the answer.

## 6. Two runner architectures now coexist

After this change the Hub drives Claude one way and Codex another — a permanent maintenance cost and
a source of subtle divergence, where a fix applied to one path silently does not apply to the other.
Task 2.15 checks whether Claude has the same MCP defect. If it does, the same reasoning argues for
the same treatment and the architectures reconverge. If it does not, the divergence is accepted
deliberately and should be stated in the runner module itself.

## 7. The protocol is experimental

`codex app-server` is labelled `[experimental]`, and this design rests on behaviour measured against
exactly one version (0.146.0). Method names, `_meta` keys, and approval shapes can change without a
major version.

Mitigations, in order of value:

1. Keep the `exec` path until app-server is verified equivalent (task 2.8).
2. Treat an unrecognised method as deny-and-continue, so a protocol addition degrades rather than
   breaks.
3. `codex app-server generate-json-schema --out <dir>` emits the installed CLI's own schema. A
   test-time check that the methods this Hub depends on are still present turns a silent behavioural
   regression into a loud one. Cheap, and worth doing.

## 8. What this unlocks, and what is deliberately not taken here

The protocol exposes far more than approvals: `turn/steer` (redirect a turn already running),
`turn/interrupt`, `item/commandExecution/terminalInteraction`, `item/tool/requestUserInput`, and
operator-answerable command approvals.

Steering a running agent is impossible today and becomes possible. Surfacing a command approval to
the operator instead of auto-denying it is the difference between an agent that stops dead at the
sandbox boundary and one that asks.

**None of that is in this change.** This change makes messaging work. Those belong to
`2026-08-06-operator-in-the-loop-turns`, which depends on this one.

## 9. Measured limitation — MCP-server-initiated elicitation does not reach the client

Tested directly on 0.146.0: an MCP server calling `ctx.elicit(...)` — standard MCP elicitation — is
**declined** rather than forwarded to the app-server client. The tool received a declined result in
every run. Declaring `mcpServerOpenaiFormElicitation: true` and `experimentalApi: true` in
`initialize` did not change the outcome; that capability is described as covering "OpenAI extended
form elicitations", which appears to be a different mechanism.

The precise cause was not established, and is not needed here. The consequence is what matters:

**`ask_user` cannot become a genuinely blocking, in-turn question by way of MCP elicitation on this
Codex version.** Any design assuming it can is unfounded. `ask_user` stays fire-and-forget plus
polling until either Codex forwards server elicitations, or the Hub blocks the tool call itself —
the route `2026-08-06-operator-in-the-loop-turns` takes.
