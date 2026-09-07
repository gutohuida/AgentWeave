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

*`ask_user` waits, and only the waiting is the adapter's.* **Round 1 claimed more than the code
supports, and round 2 measured it down.** The tool (`hub/hub/mcp_server.py:306-472`) is four routes
and about 165 lines between them, and round 1 read that gap as holding everything an agent relies
on — waiting, ordering, decline-versus-expiry, and the wait-ended report. Three of those are in the
contract already:

- the ask **parks the run's bound task and stamps the deadline**, in the route rather than in the
  tool (`_record_the_wait_and_park`, `hub/hub/api/v1/agent_actions.py:440-529`, called at `:553`
  and `:595`);
- *declined* and *expired* are two persisted columns carried on every question response
  (`declined`, `declined_at` — `hub/hub/schemas/questions.py:74-77`), so the distinction belongs to
  the contract and is not something the adapter computes;
- the order asked travels as `batch_index` / `batch_size` on the same response
  (`hub/hub/schemas/questions.py:65-67`);
- and a caller that never reports its wait ended is still swept at the run boundary by
  `run_divergence.evaluate_run_end` (`hub/hub/run_divergence.py:644`), which
  `_record_the_wait_and_park`'s own docstring names as exactly that fallback.

What remains is smaller, sharper, and provable without a Hub. **The contract offers no way to wait,
and it never tells the caller how long the wait it just started will last.** `wait_expires_at` is
written by the route (`hub/hub/api/v1/agent_actions.py:496`) and appears on no response schema —
its only other readers are inside the Hub (`hub/hub/run_task_binding.py:817`). The adapter does not
read it either: it reconstructs the same number independently from `AW_QUESTION_TIMEOUT`
(`hub/hub/mcp_server.py:891`, default `240`), which is the Hub's own `QUESTION_WAIT_DEFAULT`
(`hub/hub/api/v1/agent_trigger.py:501`, also `240`) restated in the one module that may not import
it. So an HTTP caller must either guess that number or read an environment variable the Hub writes
only when the operator configured one (`agent_trigger.py:1087`) — and the deadline its
`POST /questions/wait-ended` report is judged against is the one it was never shown.

That is still a real defect and still the same shape: a caller reaching the contract directly gets a
weaker deal than one reaching it through the adapter. It is a gap in what the plane *discloses*
rather than 165 lines of reimplementation, and stating it correctly is what makes it cheap to fix.

Both defects survive for one reason. The requirement's existing scenarios test *persisted effects of
equivalent valid actions*, and route parity satisfies that completely — an archive over HTTP
persists what an archive over MCP persists, and `POST /questions/batch` persists the questions
`ask_user` persists. Neither a rule about what the caller must do first, nor a fact the caller is
never told, is a persisted effect. That is why the modified requirement below states a different
property rather than a stricter version of the same test.

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
3. **The two adapter-only rules move into the contract.** `archive_job`'s confirmation becomes a
   property of the plane, and so does the wait `ask_user` starts — the contract offers a way to
   wait, and discloses the deadline it already stamps — so that reaching the plane over HTTP is not
   quietly a weaker deal than reaching it over MCP.
4. **A run is told the access path it actually has.** Today the tool-protocol path is asserted for
   every `claude` and `codex` run because the Hub injected a server config, whether or not the
   harness honours it. Where the system has no grounds for that assertion it describes the HTTP
   form instead — which is the only way this change reaches the deployment it was written for.

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
- It does not remove the two requirements at `openspec/specs/agent-capability-plane/spec.md:140-185`
  — "A turn that ends on an unasked question is surfaced to the operator" and "The operator can
  convert an unasked question into a real one". Round 2 found them while checking that this delta's
  `MODIFIED` block reproduced the requirement it replaces. They describe a feature **retired on
  2026-08-20 at the operator's request**, whose table migration `0082_drop_unasked_questions.py`
  drops and which `CLAUDE.md` forbids reintroducing; `openspec/changes/2026-08-07-unasked-question-backstop`
  is still sitting unarchived. So the current-behaviour corpus states, thirty lines below the
  requirement this change edits, that the product does something it was deliberately made to stop
  doing. Fixing that belongs to retiring that change, not to this one — but it is recorded here and
  put to the operator, because a false requirement that stays readable is how a later round inherits
  it as evidence.

## How reachable is this today — and the defect facing the other way

Worth stating precisely, because it decides whether this is a defect or only a future one — and
because round 2 found the likelier half of it pointing the other way.

`resolve_access_path` (`hub/hub/launchability.py:237-245`) returns `"cli"` — the branch that
denies everything — when the operator's `hub_client` config is `"cli"`, or when the runner is
outside `MCP_INJECTABLE_RUNNERS`. That set is `{"claude", "claude_proxy", "native", "codex"}`
(`:200-201`), and `RUNNER_CLIS` (`hub/hub/db/models.py:300`) only permits two of them to exist as
rows, so **today the branch is reached only by an operator setting `hub_client: "cli"`.**

It is not an obscure setting. The product's own generated configuration recommends it for this
exact situation, in the block for this exact harness: `src/agentweave/config.py:714` reads
`# hub_client: cli   # uncomment if MCP is blocked by company policy`, four lines below
`runner: copilot`. An operator following the product's own advice about a policy that forbids MCP
arrives at the branch that tells their agent it can do nothing. Both halves of that block are stale
on their own terms — `generate_agentweave_yml` has no caller outside `tests/`, and `copilot` is not
a value `RUNNER_CLIS` accepts — but the *setting* is live regardless: it travels through session
sync (`hub/hub/launchability.py:387-390`) and is read at `agent_trigger.py:1006`.

**And the opposite branch is now asserted rather than checked.** `resolve_access_path` used to
probe — `return "mcp" if probe_mcp_registered(cli) else "cli"` — until `d279d22` ("Phase 7: unify
governed agent tool surface") replaced the probe with an unconditional `return "mcp"`, on the
stated ground that the Hub now injects its own MCP server into the spawn
(`hub/hub/runner_commands.py:231-243` for Claude, `:298-310` for Codex). Injection makes the server
*configured*. It does not make it *honoured*, and a harness whose MCP is disabled by company policy
is precisely where those two come apart.

So in the deployment this change exists for — MCP forbidden by policy, runner `claude`,
`hub_client` unset — the resolved path is `"mcp"`, and the first line of the turn prompt tells the
agent that "the `agentweave` MCP tools are available — call send_message / create_task /
update_task / ask_user directly." They are not. Being told you hold a surface you do not is the
same defect as being told you lack one you do, and correcting the `cli` branch does not touch it.
`hub_client` is also settable nowhere in the Hub UI — it appears in no `.ts`/`.tsx` file — so the
documented remedy is reachable only by editing session-sync JSON.

`probe_mcp_registered` (`hub/hub/launchability.py:207-234`) survived that removal with **no
production caller**. The only references left are two tests, and both are now shaped by a fact that
is no longer true:

- `hub/tests/conftest.py:496-507`, an autouse fixture that patches the probe to `False` under a
  docstring stating this gives "every test ... the `cli` access path unless it explicitly overrides
  this fixture's patch". False since `d279d22`: nothing probes, so every `claude` test now gets
  `"mcp"`.
- `hub/tests/test_agent_trigger.py:793-830`, which patches the probe to *raise* and asserts that an
  explicit `hub_client: "mcp"` still produces the MCP notice, "even though conftest's autouse
  fixture defaults the probe to False". Nothing probes, so the raise cannot fire; and with no
  override the result would be identical, so the assertion cannot distinguish the branch it names.
  It passes for reasons its own docstring denies.

That is the shape `CLAUDE.md` records as `F190`: a green test covering behaviour that can no longer
fire.

**This one is measured rather than read.** Importing `hub.launchability`, patching
`probe_mcp_registered` to `False` exactly as the fixture does, and calling `resolve_access_path`
returns `'mcp'` for `hub_client=None`, `'mcp'` for `hub_client='mcp'`, and `'cli'` only for
`hub_client='cli'` — so the fixture does not produce the `cli` path it claims, the two inputs the
override test distinguishes produce the same output, and `access_path_notice` on the unconfigured
result begins "the `agentweave` MCP tools are available". No Hub, no spawn, no network: one import
and three calls. It is the only claim in this proposal that is not a source reading. It is named here because it is why nobody noticed, not to widen the change — §4 of
`tasks.md` fixes both tests alongside the requirement they stopped covering.

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

## What round 2 changed

Round 2 re-derived this argument against the code rather than re-reading round 1, and re-measured
every citation round 1 leaned on. Recorded plainly, because a round that finds nothing is a real
outcome and a round that finds something should be legible about which.

**Held, unchanged.** Every `archive_job` citation and the whole test contradiction; the credential
and `HUB_URL` environment claims (`agent_trigger.py:1061`, `:1071`, `:1090-1114`); the notice's
injection point (`:1006-1007`); 26 `@mcp.tool()` functions and 32 agent-actions routes, all 32 of
them behind `Depends(get_agent_actor)`; `_job_effect` as a two-line pass-through; `_decide`'s scope
and its `mcp__agentweave__*` allow-branch; `_tool_surface_lines` and its gating test as the
discovery surface's home; `src/agentweave/tool_surface.py` having zero importers. The `MODIFIED`
block reproduces all four of the original requirement's scenarios — none was silently dropped.

**Corrected.** Round 1's `ask_user` defect was overstated: parking, the deadline stamp, ordering and
the decline/expiry distinction are all in the contract, and a caller that never reports is swept at
the run boundary. The real gap is that the contract offers no wait and never discloses the deadline
it stamps.

**Added.** The mirror defect — a run whose harness cannot honour MCP is told it *can*, because
`d279d22` replaced the probe with an assertion. Without this, the change does not reach the
deployment it was written for. This is the one round-2 finding that changed the *scope* rather than
the wording.

**Noted and left out of scope.** The two retired requirements still in the capability's own
current-behaviour document.

## Not verified here

This window may not start a Hub, drive a run, or browse the web. Every claim above is a source
reading with a citation. Specifically **not** established: that an HTTP request to
`/api/v1/agent-actions/*` carrying `AW_RUN_TOKEN` actually succeeds from inside a spawned run's
environment; and what a model does with the corrected notice when it reads it. Both are drive
questions, and this repository's own rule is that rounds check the argument while a drive checks
the product. They belong in the implementing window's verification, and `tasks.md` §6 names them.
