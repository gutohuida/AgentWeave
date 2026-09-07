# Design — an agent without MCP is not told it has nothing

## D1. Two changes, HTTP first — and one gap that left this change entirely

The seed proposed splitting the operator's constraint into a no-MCP HTTP path and a `copilot`
runner, HTTP first, and asked R1 to confirm or overturn it with reasons.

**Confirmed.** The reasoning in `proposal.md` is the short form; the part worth recording here is
what re-deriving it *changed*.

The seed listed three gaps: (a) the credential is never disclosed, (b) the non-MCP branch tells the
agent it has nothing, (c) the workspace permission boundary lives in `mcp_server._decide` and is
unreachable without MCP. It flagged (c) as "the one that is a genuine design question rather than a
wiring job" and told R1 not to treat it as an oversight.

Re-measuring (c) found something better than an answer: **it is not this change's problem, and it
is not a capability-plane problem at all.**

`_decide` (`hub/hub/mcp_server.py:901-953`) is what Claude's `--permission-prompt-tool` calls back
into. Its subject is the *harness's own* tools — the `_PATH_KEYS` it inspects are `file_path`,
`path` and `notebook_path`, and it reads absolute paths out of a `command` string. It resolves each
against `AW_WORKSPACE_DIR` with `os.path.commonpath`. Its very first branch returns
`{"allow": True, "reason": "the Hub's own tools"}` for anything named `mcp__agentweave__*` — that
is, it explicitly declines to adjudicate the capability plane, because the plane authenticates and
scopes itself through the run credential.

So `_decide` is a boundary around an agent's filesystem and shell, not around AgentWeave. An agent
reaching the plane over HTTP is no less constrained than one reaching it over MCP: neither is
constrained by `_decide` for that traffic. Moving the plane's front door does not move this
boundary, weaken it, or bypass it.

What *is* true, and belongs to the Copilot change as a stated obligation rather than a discovery:
a harness with no `--permission-prompt-tool` analogue has **no** workspace boundary, because the
boundary was never server-side. `_decide` is consulted voluntarily by a harness that chooses to
ask. A harness that does not ask is not denied — it is simply never checked. That is a real hole
and it is the Copilot change's central design question, alongside the parser. Naming it here means
the next proposal starts with it rather than finding it in round 3.

## D2. Route parity is not the property the specification actually needs

The existing requirement says an adapter "MUST NOT duplicate queue, budget, identity, or lifecycle
business rules". Both defects this change fixes are *inversions* of that sentence: a rule that
exists **only** in the adapter and not in the contract at all.

- `archive_job` (`hub/hub/mcp_server.py:801-824`) always asks the operator. `POST
  /jobs/{job_id}/archive` (`hub/hub/api/v1/agent_actions.py:764-777`) never does.
- `ask_user` (`hub/hub/mcp_server.py:306-472`) blocks, orders, distinguishes decline from expiry,
  and reports the wait's end. Its three routes do none of that between them.

The requirement's existing scenarios could not catch either, and it is worth being precise about
why rather than calling it an oversight. "One operation has one persisted result" compares the
persisted effects of *equivalent valid actions*. Both defects pass it honestly: archiving over HTTP
persists exactly what archiving over MCP persists, and `POST /questions/batch` persists exactly the
questions `ask_user` persists. The difference is in what the caller is *made to do first*, and in
what happens in the gap afterwards — neither of which is a persisted effect.

The archive half is worse than a gap, and the distinction matters for how it gets fixed. It is not
that nobody wrote the rule down for the HTTP path — it is that somebody wrote down the *opposite*
and tested it. `hub/tests/test_agent_actions_governed.py:137-140` asserts a `200` for an archive
over HTTP under the standing allowance, with a comment saying archiving is governed by that
allowance like every other job mutation; `mcp_server.archive_job`'s docstring says the allowance
supplies capability and not direction, cites D18, and always asks. So the implementing window is not
adding a missing check to an indifferent route. It is resolving a disagreement, and one side of it
is currently green. `proposal.md` puts the choice to the operator and `tasks.md` §3.8 forbids
flipping the assertion quietly, because a test changed without its comment is how the losing side of
an argument disappears without anyone deciding it.

So the fix at requirement level is not a stricter version of the same test. It is a different
property: **a rule that governs one adapter's callers governs the contract's callers.** The delta
states it that way, and states it about governance and about waiting, because those are the two
kinds of rule that live in gaps rather than in rows.

## D3. Where the discovery surface lives

Three candidates, measured before choosing.

| Candidate | What it is today | Verdict |
|---|---|---|
| `src/agentweave/tool_surface.py` | zero importers in `src/` or `hub/`; the Hub keeps an independent mirror and says so at `hub/hub/launchability.py:194` | **No.** Reusing a module nothing imports would put the description one process boundary away from the only code that renders it. It is a corpse, and the seed was right to ask. |
| A charter | editable markdown, per-agent, operator-owned | **No.** The access path is a per-*run* fact decided at `agent_trigger.py:1006`, not a per-agent behaviour contract. An operator editing a charter could contradict the run's actual path. |
| `_tool_surface_lines` (`hub/hub/api/v1/agents.py:884`), injected at `:1543` | the canonical-context text an MCP agent reads today | **Yes.** |

`_tool_surface_lines` already is the single description of the plane's operations, and it is
already gated: `hub/hub/api/v1/agents.py:868-870` keeps an explicit list of tools it deliberately
does not describe, and `test_tool_surface_matches_server.py` fails the build when the description
and the server disagree. That test is the reason this is the right home — an HTTP rendering written
anywhere else would drift the first time a tool was added, silently, which is the exact failure
this change exists to stop repeating.

The rendering, not the content, is what varies by access path. The same operations described as
`send_message(...)` for MCP are described as `POST /api/v1/agent-actions/messages` for HTTP.

**A fetched discovery route was considered and rejected for this change.** It is defensible — an
agent that can make one request can make a discovery request — but it costs an agent one round-trip
before it knows anything, and it fails in the one condition where the agent most needs the text: it
cannot reach the Hub. Context text arrives before the first request and survives an unreachable
Hub. If a route is wanted later it can be added over the same source without changing this
requirement.

## D4. The credential is named, never valued — a boundary, not a preference

The seed asked how the credential is disclosed without leaking it.

The distinction that settles it: **the agent already has the value.** `AW_RUN_TOKEN` is in the
spawned process's environment (`hub/hub/api/v1/agent_trigger.py:1071`), and any agent with shell
access can read its own environment. Telling it the variable's *name* discloses nothing it does not
hold.

Telling it the *value* would be different in kind, and worse than it first looks. The notice is
prepended to the turn prompt at `agent_trigger.py:1006-1007`; the prompt is the durable record of
the turn. A credential in the notice is a credential in stored turn text, reachable by anything
that reads a run's prompt. `openspec/specs/agent-capability-plane/spec.md:17` already forbids
exposing it "in output, events, command arguments, or API responses", and this repository has a
fresh, concrete reason to take that literally: `scripts/drive/aw.py:15` carried a live `aw_live_`
Hub key as a hardcoded default in a tracked file of a public repository until 2026-09-07. Removing
it did not unpublish it.

So: the notice names `AW_RUN_TOKEN` and `HUB_URL` and shows the `Authorization: Bearer` shape. It
never interpolates either value. The delta states this as a prohibition, because the difference
between naming and interpolating is one f-string, and a requirement that only said "tell the agent
how to authenticate" would not catch it in review.

## D5. What is deliberately left open for the implementing window

Two decisions are stated as properties in the delta rather than mechanisms, because both have more
than one defensible implementation and neither can be chosen well without a running Hub — which
this window may not start.

**`archive_job`'s confirmation, moved server-side.** The rule must hold for every caller. Whether
the route blocks on `_ask_operator`'s equivalent, or returns a typed "confirmation required"
failure carrying a request id the caller then polls, is a mechanism question with a real trade-off:
the first keeps the MCP tool's shape unchanged, the second matches how `/permission-requests`
already works (`hub/hub/api/v1/agent_actions.py:887-954`) and does not hold a request open. The
delta requires the rule, not the mechanism.

**`ask_user`'s blocking, moved into the contract.** Same shape of question, larger: a long-held
request against a route, versus a documented poll-and-report protocol that the HTTP description
makes explicit and that `ask_user` is then re-expressed in terms of. The second is likely right —
it is what the adapter already does, so it is proven — but it means the *specification* carries the
protocol, including the wait-ended report, rather than a helpful adapter carrying it for one kind
of caller. Either way the decline/expiry distinction and the wait-ended report are load-bearing and
the delta names them: they are what a naive HTTP caller loses silently today.

## D6. What would make this change wrong

- Rendering an HTTP capability description that drifts from the tools. Mitigated by putting it
  behind `test_tool_surface_matches_server.py` rather than beside it (D3).
- Declaring parity on the strength of route parity again. That is the mistake this round was sent
  to check for, and it was present (D2).
- Shipping the corrected notice and never running an agent against it. This window cannot drive;
  `tasks.md` §5 makes the drive a task rather than a hope, and `proposal.md` says plainly which two
  claims are unverified source readings.
