## Why

A run whose harness cannot use MCP is handed a working credential and the Hub's own address in its
environment, and is then told, in its first line of prompt, that it has no way to reach AgentWeave
at all.

Both halves are measured.

**The agent holds everything it needs.** `hub/hub/api/v1/agent_trigger.py:1061` mints the run
credential and `:1071` puts it in the spawned process's environment as `AW_RUN_TOKEN`;
`:1090-1114` puts the Hub's own base address there as `HUB_URL`, either from the parent
environment or from the port the server observed itself accepting a connection on. Nothing about
either depends on MCP. They are ordinary environment variables in an ordinary child process.

**The agent is told it holds nothing.** `hub/hub/launchability.py:325-330` is the whole non-MCP
branch of `access_path_notice`:

> `[AgentWeave] Tool access: no AgentWeave tool surface is available this turn, so you cannot send
> messages, create or update tasks, or ask the operator. Report what you would have sent as part of
> your reply instead.`

That text is prepended to the turn prompt at `hub/hub/api/v1/agent_trigger.py:1006-1007`, ahead of
the operator's own message. So the first thing such a run reads is an instruction to give up on a
capability it is at that moment authenticated for.

The branch was **emptied rather than repointed**, and the code says so. The comment at
`hub/hub/launchability.py:321-324` records that it used to name `agentweave msg send`, `task
create`, `question ask` and `agent request`, and that `2026-08-03-single-runtime` reduced the CLI to
five app-lifecycle commands, so every one of those instructions became wrong. Deleting them was
correct. What was never done is the other half: the HTTP plane those commands had been a wrapper
over did not go anywhere.

## This is a shipped requirement whose agent-facing half was never built

`openspec/specs/agent-capability-plane/spec.md:107` already requires it, and already names this
exact deployment:

> Direct HTTP SHALL be the application contract. MCP SHALL be a thin adapter over that contract with
> the same operations, validation, governance, attribution, and typed failure meaning. […] Two
> adapters exist rather than one because MCP is convenient where it is permitted and **some
> environments forbid MCP servers while still allowing ordinary local API calls.**

So the operator's company constraint — MCP prohibited by policy, ordinary local HTTP permitted — is
not a new requirement. It is the case the shipped requirement was written for. The change is
therefore not "add an HTTP mode". It is "make the adapter the specification already promises
reachable by the agent running inside it", plus two places where the promise is not currently kept.

## Where the promise is not kept — measured, not assumed

The seed for this round warned that a 26-tool mapping is a claim about **routes**, not about whether
a route behaves the same when reached without the adapter around it. That warning was correct, and
checking it found two things.

**Route parity holds.** All 26 `@mcp.tool()` functions in `hub/hub/mcp_server.py` reach the Hub
through one helper, `_hub_request` (`:151-183`), which targets `/api/v1/agent-actions{path}`. The
five job tools appear at a glance not to — they call `_job_effect` — but `_job_effect`
(`:580-582`) is a two-line pass-through to `_hub_request` and nothing else. No tool holds state
locally. `hub/hub/api/v1/agent_actions.py` declares 32 routes against those tools' 26, so HTTP is a
superset at the route level.

**Behaviour parity does not hold, in two named places.**

*`archive_job` enforces a governance rule the contract does not have.* `hub/hub/mcp_server.py:815`
calls `_ask_operator` before archiving, unconditionally and regardless of the run's permission
posture; its docstring cites design D18 and explains why — the standing scheduled-work allowance
grants the capability to reach the tool, not the direction to use it on this job, now. The route it
then calls, `POST /jobs/{job_id}/archive` at `hub/hub/api/v1/agent_actions.py:764-777`, asks the
operator nothing. It resolves the actor and delegates straight to `archive_job`. An agent reaching
the plane over HTTP — which is precisely what this change is for — archives jobs with no
confirmation at all. The rule is real, deliberate and documented, and it lives entirely in one
adapter.

**And the divergence is written down twice, in opposite directions, with the test green.**
`hub/tests/test_agent_actions_governed.py:137-140` posts to that route with a bearer run token and
asserts a `200`, under a comment reading *"Archiving is the real alternative (B2.2), governed by the
same allowance as every other agent-originated job mutation."* `archive_job`'s docstring says the
opposite in as many words: the standing allowance "grants the *capability* to reach this tool at
all, it does not supply the *direction* to use it on this job, right now," and an `auto` posture
would otherwise wave every call through unattended. One of those two is the product's rule. They
cannot both be, and today which one an agent meets depends only on which adapter it came through.
Resolving that contradiction is the operator's call and is recorded as such below.

*`ask_user` is a blocking call whose blocking lives in the adapter.* The tool
(`hub/hub/mcp_server.py:306-472`) is three HTTP calls and about 165 lines of logic between them:
`POST /questions/batch`, then a poll of `GET /questions/{id}` against `QUESTION_ANSWER_TIMEOUT`,
then `POST /questions/wait-ended` for the ones that expired. Everything an agent actually relies on
is in that gap — waiting at all, answers returned in the order asked, the distinction between
*declined* (the operator saw it and handed the decision back) and *expired* (silence), and the
wait-ended report that stops a parked task from claiming somebody is still waiting. An HTTP caller
of those three routes gets none of it unless it reimplements all of it, and the failure is silent:
`POST /questions/batch` succeeds, the turn continues, and the operator's answer arrives for nobody.

These are the same defect wearing two faces. The specification says an adapter must not hold
business rules; two rules are in an adapter; and nobody noticed because the requirement's existing
scenarios test *persisted effects of equivalent valid actions*, which route parity satisfies
completely.

## Why this is one change and not two

The seed asked whether a `copilot` runner and a documented no-MCP HTTP path are one change or two,
and proposed two with HTTP first. **Two, HTTP first, confirmed** — and re-deriving it moved one of
the seed's three gaps out of this change entirely.

The HTTP path stands alone: it is a live defect for *any* harness without MCP, it is already
required, and it needs nothing from Copilot. A Copilot runner does not stand alone — it is blocked
at four layers (`RUNNER_CLIS` at `hub/hub/db/models.py:300`, `RunnerCli` at
`hub/ui/src/api/runners.ts:5`, `SUPPORTED_RUNNERS` at `hub/hub/api/v1/agent_trigger.py:654`, and
the claude/else parser dispatch at `:2043`) — and the fourth cannot be settled at all without
Copilot's real output format, which this window is not permitted to go and find. Shipping the HTTP
path first means the Copilot change, when it is written, is a runner and a parser rather than a
runner, a parser and a capability plane.

The seed listed a third gap: the workspace permission boundary in `mcp_server._decide`
(`:901-953`), unreachable without MCP. **Re-measuring it moved it out of this change.** `_decide`
answers Claude's `--permission-prompt-tool` callback and adjudicates the *harness's own* file and
shell tools against `AW_WORKSPACE_DIR`; its first branch allows anything named
`mcp__agentweave__*` outright. It never guards an `/api/v1/agent-actions` route and this change
does not weaken it, because this change does not touch it. It is a real and unsolved problem for a
harness with no `--permission-prompt-tool` analogue — which is to say, it belongs to the Copilot
change. `design.md` records this so the next round does not have to re-derive it, and so the
Copilot proposal inherits it as a stated obligation rather than a surprise.

## What changes

1. **The non-MCP notice tells the truth.** It names the base address, names the environment
   variable holding the credential, names the route prefix, and points at a discovery surface —
   instead of instructing the agent to give up.
2. **A discovery surface exists that an HTTP agent can read.** The capability description an MCP
   agent gets today is `_tool_surface_lines` (`hub/hub/api/v1/agents.py:884`, injected into
   canonical context at `:1543`), and it is written in terms of tool calls. An HTTP agent needs
   the same operations described as requests.
3. **The two adapter-only rules move into the contract.** `archive_job`'s confirmation and
   `ask_user`'s blocking semantics become properties of the plane, so that reaching it over HTTP is
   not quietly a weaker deal than reaching it over MCP.

## What this change does not do

- It does not add a `copilot` runner, touch `RUNNER_CLIS`, or write a parser. Separate change,
  and one of its questions is unanswerable in this window.
- It does not put the credential's **value** anywhere. The agent is told the variable's name; it
  already has read access to its own environment, so naming `AW_RUN_TOKEN` discloses nothing the
  process does not hold. Writing the value into notice text would put a live credential into the
  turn prompt, which is persisted — and the shipped requirement at
  `openspec/specs/agent-capability-plane/spec.md:20` forbids exposing it in output. `design.md`
  D4 states this as a boundary, not a preference.
- It does not resolve `src/agentweave/tool_surface.py`, which has zero importers in `src/` or
  `hub/` — the Hub carries its own independent mirror and says so at
  `hub/hub/launchability.py:194`. Recorded so it is not mistaken for the discovery surface's home.
- It does not touch `.claude/skills/copilot-test-setup/SKILL.md`, which describes a watchdog
  architecture deleted on 2026-08-03. It is a fossil and belongs to the Copilot change; it is named
  here only so no round cites it as evidence of anything current.

## How reachable is this today

Worth stating precisely, because it decides whether this is a defect or only a future one.
`resolve_access_path` (`hub/hub/launchability.py:237-245`) returns `"cli"` — the branch that
denies everything — when the operator's `hub_client` config is `"cli"`, or when the runner is
outside `MCP_INJECTABLE_RUNNERS`. That set is `{"claude", "claude_proxy", "native", "codex"}`
(`:200-201`), and `RUNNER_CLIS` only permits two of them to exist as rows, so **today the branch is
reached only by an operator setting `hub_client: "cli"`.** It is live and operator-reachable now,
and it becomes the default path for every non-MCP harness the moment one is supported. It is not
dead code, and it is not yet a common one.

## One thing this proposal does not decide

Whether archiving a job requires the operator's direction every time (design D18, and what
`archive_job` does) or is governed by the standing scheduled-work allowance like every other job
mutation (what the HTTP route does, and what `test_agent_actions_governed.py:137-140` asserts) is a
product decision, not a wiring one. This proposal takes the position that D18 is the rule — it is
the more recent and more argued of the two, and the delta is written that way — but the operator
owns it, because the alternative is defensible and choosing it makes this half of the change a
two-line deletion instead.

What is *not* open is that the two paths must agree. Either answer is a coherent product; the
current state, where the answer depends on which adapter the agent came through, is not.

## Not verified here

This window may not start a Hub, drive a run, or browse the web. Every claim above is a source
reading with a citation. Specifically **not** established: that an HTTP request to
`/api/v1/agent-actions/*` carrying `AW_RUN_TOKEN` actually succeeds from inside a spawned run's
environment; and what a model does with the corrected notice when it reads it. Both are drive
questions, and this repository's own rule is that rounds check the argument while a drive checks
the product. They belong in the implementing window's verification, and `tasks.md` §5 names them.
