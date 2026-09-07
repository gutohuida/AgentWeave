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
- `ask_user` (`hub/hub/mcp_server.py:306-472`) blocks, and the contract gives a direct caller no
  way to. **This bullet said much more than that until round 2 measured it** — see D6, which is
  where the corrected version lives; the short form is that ordering, the decline/expiry
  distinction, the deadline stamp and the task park are all already the contract's, and what is
  missing is the wait itself and the disclosure of the deadline.

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
is currently green. `proposal.md` puts the choice to the operator and `tasks.md` §3.9 forbids
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

Three decisions are stated as properties in the delta rather than mechanisms, because each has more
than one defensible implementation and none can be chosen well without a running Hub — which this
window may not start. The third was added by round 2.

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
of caller. Round 2 cut this one down — most of what the paragraph above assumed was missing turns
out to be in the contract already (D6), so the open question is narrower than it reads: how a caller
is offered a wait, and how the deadline the Hub already stamps is disclosed to it.

**How the system establishes which access path a run really has.** Added by round 2; three
mechanisms, laid out in D7, and the same reason for leaving it open — the choice needs a harness
whose MCP is actually blocked, which this window cannot produce.

## D6. What round 2 re-measured — the ask_user claim, cut down

Round 1 wrote that `ask_user`'s three routes carry none of what the tool provides. Four routes, and
three of the four properties are in the contract:

| Property | Where it actually lives |
|---|---|
| The task is parked while the run waits | `_record_the_wait_and_park`, `hub/hub/api/v1/agent_actions.py:440-529` — the **route**, called at `:553` and `:595` |
| The wait has a deadline | same function, `:492-496`, stamped from the Hub's own `effective_question_wait` |
| Answers in the order asked | `batch_index` / `batch_size` on `QuestionResponse`, `hub/hub/schemas/questions.py:65-67` |
| *Declined* is not *expired* | `declined` / `declined_at` columns on the same response, `:74-77` |
| The wait ended | `POST /questions/wait-ended` is a route with its own server-side refusals; `run_divergence.evaluate_run_end` (`hub/hub/run_divergence.py:644`) sweeps whatever the caller never reported |
| **Waiting itself** | **the adapter only** — `hub/hub/mcp_server.py:367`'s poll loop |
| **Knowing the deadline** | **nowhere the caller can see it** — `wait_expires_at` is written at `agent_actions.py:496` and is on no response schema |

The second of those two is the better defect, and it was invisible while the first was overstated.
The Hub stamps a deadline, judges the caller's `wait-ended` report against it (`run_task_binding.py:817`),
and never tells the caller what it is. The adapter compensates by computing its own copy from
`AW_QUESTION_TIMEOUT` (`mcp_server.py:891`, default `240`), which is `QUESTION_WAIT_DEFAULT`
(`agent_trigger.py:501`) restated in the module that may not import the Hub — a duplication that is
correct today only because both literals read `240`, and that an HTTP caller has neither copy of.

So the delta requires disclosure, not reimplementation: give the caller the deadline the Hub already
holds, and a stated way to wait. That is a smaller change than round 1 described and a more
defensible requirement, because it asks the contract for something it already knows.

## D7. The mirror defect, and why it is in scope

Round 1 established that the `cli` access path is reached today only by an explicit
`hub_client: "cli"`. True. What it did not ask is what the *other* branch asserts, and the answer
changes what this change has to cover.

`resolve_access_path` stopped probing in `d279d22` and now returns `"mcp"` unconditionally for any
runner in `MCP_INJECTABLE_RUNNERS`. The commit's reasoning is in the docstring it wrote — "now that
the Hub injects its canonical server" — and against 2026-08 that was sound: the Hub adds
`--mcp-config` (Claude, `runner_commands.py:231-243`) or `-c mcp_servers.agentweave...` (Codex,
`:298-310`) itself, so probing whether the operator had registered the server by hand answered a
question nobody was asking anymore.

The assumption underneath it is that a configured server is an available one. **The operator's
constraint is the case that breaks it.** A harness with MCP disabled by policy takes the injected
config and does nothing with it, and the run is told, in its first line, to call tools that are not
there.

That is not a separate change. It is the same requirement — what a run is told about its access path
must be true — and a change that fixed only the `cli` branch would ship a correct notice on the one
path the operator's deployment never takes. The delta therefore states the property and leaves the
mechanism open, because there are at least three and the choice needs a running Hub:

- **restore the probe**, now behind the injected config rather than a hand-registered one. It costs
  a subprocess per cache miss (`_PROBE_TTL_SECONDS = 300`) and is the only option that needs nothing
  from the operator. `probe_mcp_registered` still exists, unused, and would need re-aiming: `<cli>
  mcp list` on a policy-blocked harness is the thing to check it actually reports.
- **make `hub_client` an operator-visible setting** and treat it as authoritative. Cheapest, and
  honest about being a declaration rather than a measurement — but it is invisible in the UI today,
  so this is a UI change, and this change is otherwise Hub-Python-only.
- **describe both paths** and let the agent use whichever works. Wasteful in context, and the two
  descriptions can disagree about which is real, which is the failure this change exists to stop.

Whichever is chosen, the property is the same and the delta states it that way: do not assert a
surface the system has no grounds to believe is there.

## D8. Two retired requirements in the file this delta edits

`openspec/specs/agent-capability-plane/spec.md:140-185` still carries "A turn that ends on an unasked
question is surfaced to the operator" and "The operator can convert an unasked question into a real
one". The feature was retired on 2026-08-20 at the operator's request; migration
`0082_drop_unasked_questions.py` drops the table; `CLAUDE.md` states plainly that it must not be
reintroduced; and `openspec/changes/2026-08-07-unasked-question-backstop` is still in `changes/`
rather than `changes/archive/`.

Found while checking that this delta's `MODIFIED` block reproduced the requirement above them
faithfully — which it does. Deliberately **not** folded in: removing them is part of retiring that
change, and mixing a two-requirement deletion into a delta about reachability would make both harder
to review. It is in `proposal.md` under what this change does not do, and it goes to the operator.

## D9. What would make this change wrong

- Rendering an HTTP capability description that drifts from the tools. Mitigated by putting it
  behind `test_tool_surface_matches_server.py` rather than beside it (D3).
- Declaring parity on the strength of route parity again. That is the mistake this round was sent
  to check for, and it was present (D2).
- Shipping the corrected notice and never running an agent against it. This window cannot drive;
  `tasks.md` §6 makes the drive a task rather than a hope, and `proposal.md` says plainly which two
  claims are unverified source readings.
- Fixing the `cli` branch alone and calling the operator's deployment served. That branch is not the
  one their runs take (D7). Round 2 added the mirror for this reason, and it is the finding most
  likely to be lost if a later window trims scope.
