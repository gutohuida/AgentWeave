# Sidequest run — 2026-09-07

Two spec loops the operator asked for, run **apart from** the daily FILL/DECIDE/FIX cycle.

## Iteration 0 — set up by the interactive session, 2026-09-07 afternoon

Not an agent iteration. This entry exists so the first firing has context.

### Why this run is separate from the daily cycle

The operator asked for two spec loops on subjects unrelated to the cycle's queue, and asked that
they run now rather than waiting for tomorrow's FILL window: *"You can schedule those loops as
something apart to run now. They don't need to fall inside the normal scheduler for agentweave
work."*

The daily cycle owns the main checkout at `C:\Users\huida\Documents\projects\AgentWeave` on
`autonomous/2026-09-07-daily`. `AgentWeaveArmNight` fires at **22:55 tonight** and arms the FIX
window onto whatever branch that checkout is on, and `arm-cycle.ps1` refuses to arm onto a dirty
tree. A second unattended process in the same working tree would therefore either steal the branch
or poison the arming. So this run lives in a **separate git worktree** on its own branch, with its
own state file, its own driver log and its own scheduled task. The two cannot see each other.

| | daily cycle | this run |
|---|---|---|
| checkout | `…\AgentWeave` | `…\AgentWeave-sidequest` |
| branch | `autonomous/2026-09-07-daily` | `autonomous/2026-09-07-sidequest` |
| state | `STATE-day.json` / `STATE-night.json` | `STATE-sidequest.json` |
| task | `AgentWeaveArmDay` / `AgentWeaveArmNight` | `AgentWeaveSidequest` |
| driver log | `driver.log` | `driver-sidequest.log` |

Branched from `8ee61b1`, the cycle branch's head at the time.

### What the two subjects are

1. **AgentWeave where MCP is blocked and Copilot is the house CLI.** The operator's own company
   constraint. Seed: `openspec/explorations/2026-09-07-agentweave-without-mcp-and-with-copilot.md`.
2. **What is actually separable from this repo**, with a folder per surviving candidate in the
   parent directory and a spec loop inside each. Seed:
   `openspec/explorations/2026-09-07-what-is-actually-separable.md`.

Both seeds were written from surveys that read the code on 2026-09-07. **Both contain a claim that
was spot-checked and found FALSE, left in and labelled**, so no round treats a seed as settled.

### The headline finding from the setup, before any round has run

The 2026-09-06 exploration this run was asked to validate is **wrong on seven claims**, including
both halves of its central recommendation. Most importantly: it recommended extracting the two
mechanisms with the *least* production evidence and recommended against the one with the *most*,
and the reason it gave for declining that one was a market argument, not a separability argument —
which is not the question the operator asked. Detail in the second seed's Part 1.

### Found while surveying, unrelated to either subject and already fixed

`scripts/drive/aw.py:15` carried a live `aw_live_` Hub key as a hardcoded default in a **tracked**
file, in a repository `gh repo view` reports **PUBLIC**. Default removed on the cycle branch at
`2d4131b`. Removal does not unpublish it — the value is in git history and must be treated as
disclosed. Rotation is the operator's call and is the first row in `decisions_for_user`.

### Next

`next_action` is `S-1`. Read `STATE-sidequest.json` for the queue and the limits, then do exactly
that one item.

---

## Iteration 1 — S-1, spec loop R1: AgentWeave reachable where MCP is blocked

State verified before starting: branch `autonomous/2026-09-07-sidequest`, head `ba6e35e`, parent
`8ee61b1`, clean tree. All match `STATE-sidequest.json`. Nothing to reconcile.

**Written:** `openspec/changes/2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing/` —
`proposal.md`, `design.md`, `tasks.md`, and a delta on `agent-capability-plane`.
`openspec validate --strict` passes.

### The seed's question 1, answered: two changes, HTTP first

Confirmed, and re-deriving it moved one of the seed's three gaps out of the change. The HTTP path is
already required, is a live defect for any harness without MCP, and needs nothing from Copilot. A
Copilot runner is blocked at four layers and the fourth — the parser — cannot be settled without
Copilot's real output, which this window may not go and find.

### The delta is MODIFIED, not just ADDED

`openspec/specs/agent-capability-plane/spec.md:107` already requires HTTP/MCP parity and already
names the deployment ("some environments forbid MCP servers while still allowing ordinary local API
calls"). So the company constraint is a shipped requirement whose agent-facing half was never built.
The delta adds one requirement (a run without MCP is told how to reach the plane) and **modifies**
the parity requirement, because checking it found the requirement itself is currently breached.

### Measured, not inherited

Every seed claim this proposal leans on was re-measured. What held:

- 26 `@mcp.tool()` functions, all reaching the Hub through `_hub_request`
  (`mcp_server.py:151-183`) at `/api/v1/agent-actions{path}`. The five job tools look like
  exceptions and are not — `_job_effect` (`:580-582`) is a two-line pass-through. 32 routes against
  26 tools, so HTTP is a route-level superset.
- `AW_RUN_TOKEN` at `agent_trigger.py:1071` and `HUB_URL` at `:1090-1114` are both in the spawned
  process's environment, while `launchability.py:325-330` tells that same run it has no tool surface
  at all. Both halves confirmed verbatim.
- The four Copilot blocking layers. One correction to my own first reading, not the seed's: I
  initially recorded the seed's parser claim as false, because `agent_trigger.py:2043` sets
  `parse_line = None` rather than `parse_codex_line`. Line `:2061` completes it —
  `parse_line(line) if parse_line is not None else parse_codex_line(line, model=model)`. The seed
  was right; a one-line citation was not enough to see it.

### Two findings the seed did not have

**Route parity is not behaviour parity, and the gap has two named instances.** The seed warned to
check `ask_user` first. That was the right instinct and it generalised.

1. `ask_user` (`mcp_server.py:306-472`) is three routes and ~165 lines of logic *between* them:
   waiting at all, answers in the order asked, *declined* versus *expired*, and the wait-ended
   report that stops a parked task claiming somebody is still waiting. An HTTP caller of those three
   routes gets none of it, and fails silently — `POST /questions/batch` succeeds, the turn goes on,
   and the operator's answer arrives for nobody.
2. `archive_job` (`mcp_server.py:815`) always asks the operator, regardless of permission posture,
   citing design D18. `POST /jobs/{job_id}/archive` (`agent_actions.py:764-777`) asks nothing.

Neither is catchable by the requirement's existing scenarios, and it is worth being exact about why
rather than calling it an oversight: "One operation has one persisted result" compares *persisted
effects of equivalent valid actions*, and both defects pass it honestly. The difference is in what
the caller is made to do first, and in what happens in the gap afterwards. So the modified
requirement states a different property — a rule that governs one adapter's callers governs the
contract's callers.

**The archive divergence is written down twice, in opposite directions, and the test is green.**
This was found by checking a claim I had written and had not measured. `tasks.md` §5.3 originally
said "no test in the repo reaches the routes the way a spawned agent would." False —
`test_agent_actions_governed.py:20-34` mints a run row and sends `Authorization: Bearer`, and
`:137-140` archives over HTTP under the standing allowance and asserts `200`, under a comment saying
archiving is "governed by the same allowance as every other agent-originated job mutation" — the
exact opposite of what `archive_job`'s docstring and D18 say.

So the implementing window is not adding a missing check to an indifferent route; it is resolving a
live disagreement with one side currently green. That goes to the operator (`proposal.md`, "One
thing this proposal does not decide") rather than being guessed, and `tasks.md` §3.8 forbids
flipping the assertion quietly. §5.3 was rewritten to say what the in-process tests *do* cover and
what only a spawn can.

### A seed gap that left the change

The seed flagged the workspace boundary in `mcp_server._decide` (`:901-953`) as "a genuine design
question rather than a wiring job" and told R1 not to treat it as an oversight. Re-measuring moved
it out of this change entirely: `_decide` answers Claude's `--permission-prompt-tool` callback about
the *harness's own* file and shell tools against `AW_WORKSPACE_DIR`, and its first branch allows
anything named `mcp__agentweave__*` outright — it explicitly declines to adjudicate the capability
plane. It is not a capability-plane boundary, this change does not touch it, and moving the plane's
front door cannot weaken it.

What is true, and now belongs to the Copilot change as a stated obligation rather than a round-3
surprise: a harness with no `--permission-prompt-tool` analogue has **no** workspace boundary at
all, because the boundary was never server-side. A harness that does not ask is not denied; it is
never checked. `design.md` D1 records it.

### Decisions this round chose rather than deferred

- **Discovery surface lives in `_tool_surface_lines`** (`agents.py:884`, injected `:1543`), not in
  a charter and not in `src/agentweave/tool_surface.py` — which has zero importers in `src/` or
  `hub/`, the Hub keeping an independent mirror and saying so at `launchability.py:194`. The
  deciding reason is `test_tool_surface_matches_server.py`: a rendering not behind that test drifts
  the first time a tool is added, silently.
- **The credential is named, never valued.** `AW_RUN_TOKEN` is already in the agent's environment,
  so naming the variable discloses nothing; interpolating the value would put a live credential in
  the turn prompt, which is durable, and breach `spec.md:17`. Stated as a prohibition in the delta
  because the difference is one f-string.
- **A fetched discovery route was considered and rejected** — it costs a round-trip before the
  agent knows anything and fails in the one condition where the text matters most, an unreachable
  Hub.

### Left open on purpose

Two mechanisms (`design.md` D5): how the archive confirmation is expressed server-side, and how
waiting is expressed in the contract. Both have more than one defensible answer and neither can be
chosen well without a running Hub, which this window may not start. The delta requires the rule, not
the mechanism.

### Not verified

No Hub was started, nothing was driven, no web was browsed — all per this run's limits. Every claim
above is a source reading with a citation. `tasks.md` §5.3–§5.5 carry the two questions only a drive
can answer into the implementing window rather than leaving them as assumptions.

### Next

`next_action` is `S-2` — R2, an independent re-derivation against the code. Its first job is the one
this round could not do for itself: re-measure the citations above.

---

## Iteration 2 — S-2, spec loop R2: the notice is wrong in both directions

State verified before starting: branch `autonomous/2026-09-07-sidequest`, head `8155735`, parent
`8ee61b1`, clean tree. All match `STATE-sidequest.json`. Nothing to reconcile.

**Changed:** `proposal.md`, `design.md`, `tasks.md` and the `agent-capability-plane` delta of
`openspec/changes/2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing/`.
`openspec validate --strict` passes. No product code touched.

### Every citation R1 leaned on was re-measured. Most held.

Confirmed at the stated lines: the credential and address in the spawned environment
(`agent_trigger.py:1061`, `:1071`, `:1090-1114`); the notice's injection point (`:1006-1007`); the
non-MCP branch and its comment (`launchability.py:321-330`); 26 `@mcp.tool()` functions and 32
`agent-actions` routes, **all 32 behind `Depends(get_agent_actor)`**; `_job_effect` (`:580-582`) as
a two-line pass-through; `_decide` (`:901-953`) allowing `mcp__agentweave__*` outright;
`_tool_surface_lines` (`agents.py:884`) injected at `:1543` and gated by `UNDESCRIBED_TOOLS`;
`src/agentweave/tool_surface.py` with zero importers; `RUNNER_CLIS` (`models.py:300`) and
`RunnerCli` (`runners.ts:5`); `SUPPORTED_RUNNERS` (`runner_commands.py:52`, gate at
`agent_trigger.py:654`); the parser dispatch at `:2043`/`:2061`. The `MODIFIED` block reproduces all
four scenarios of the requirement it replaces — none was silently dropped.

Every `archive_job` claim held exactly, including the sharpest one: `mcp_server.py:815` always asks,
`agent_actions.py:764-777` never does, and `test_agent_actions_governed.py:137-140` asserts the
`200` under a comment stating the opposite rule. R1's best finding survives untouched.

### What R2 changed

**1. The proposal was wrong about `ask_user`, and the truth is a better defect.** R1 wrote that
blocking, ordering, decline-versus-expiry and the wait-ended report all live in the adapter and that
"an HTTP caller of those three routes gets none of it". Measured, three of the four are in the
contract: `_record_the_wait_and_park` (`agent_actions.py:440-529`) is called *by the routes* at
`:553` and `:595` and both stamps the deadline and parks the run's task; `declined`/`declined_at`
and `batch_index`/`batch_size` are persisted columns on `QuestionResponse`
(`schemas/questions.py:65-77`); and an unreported wait is swept at the run boundary by
`run_divergence.evaluate_run_end` (`:644`), which the park's own docstring names as that fallback.

What is genuinely missing is smaller and sharper: the contract offers no way to wait, and
**`wait_expires_at` is written at `agent_actions.py:496` and appears on no response schema** — so
the Hub judges a caller's `wait-ended` report against a deadline (`run_task_binding.py:817`) it
never disclosed. The adapter does not read it either; it recomputes the number from
`AW_QUESTION_TIMEOUT` (`mcp_server.py:891`, default `240`), which is `QUESTION_WAIT_DEFAULT`
(`agent_trigger.py:501`, also `240`) restated in the module that may not import the Hub. Two
literals, one number, and an HTTP caller holding neither. `tasks.md` §3.5 now forbids reimplementing
what already exists and §3.6 asks for the disclosure instead.

**2. The defect faces the other way too, and that changed the change's scope.** R1's reachability
section — the `cli` branch is reached today only by an explicit `hub_client: "cli"` — is correct and
incomplete. `resolve_access_path` used to probe; `d279d22` ("Phase 7: unify governed agent tool
surface") replaced the probe with an unconditional `return "mcp"` because the Hub now injects its own
MCP server into the spawn (`runner_commands.py:231-243`, `:298-310`). Injection makes the server
configured, not honoured — and a harness with MCP disabled by policy is exactly where those come
apart. So in the deployment this change exists for, the resolved path is `"mcp"` and the agent is
told the MCP tools *are* available. Correcting the `cli` branch never touches that run.

**Measured, not read.** Importing `hub.launchability`, patching `probe_mcp_registered` to `False`
exactly as `conftest.py:496-507` does, and calling `resolve_access_path('claude','claude',override)`
returns `mcp` / `mcp` / `cli` for `None` / `'mcp'` / `'cli'`. Three consequences, all from one import
and three calls, no Hub and no network:

- the autouse fixture's docstring — "every test gets the `cli` access path" — has been false since
  `d279d22`; every `claude` test gets `mcp`;
- `test_agent_trigger.py:793-830` patches the probe to *raise* and asserts an explicit
  `hub_client: "mcp"` yields the MCP notice. Nothing probes, so the raise cannot fire, and `None`
  and `'mcp'` give identical output — the assertion cannot distinguish the branch it names. `F190`
  again;
- `access_path_notice` on the unconfigured result begins "the `agentweave` MCP tools are available".

This is the one round-2 finding that changed scope rather than wording. The delta gains a second
ADDED requirement — *a run is told the access path it actually has* — stated as a property with
three mechanisms laid out in `design.md` D7 (re-aim the probe; make `hub_client` operator-visible and
authoritative, noting it appears in no `.ts`/`.tsx` file today; or describe both paths). `tasks.md`
gains §4, six tasks including fixing both stale tests.

**3. The product's own config recommends the broken setting for this exact case.**
`src/agentweave/config.py:714` reads `# hub_client: cli   # uncomment if MCP is blocked by company
policy`, four lines under `runner: copilot`. Both halves are stale on their own terms —
`generate_agentweave_yml` has no caller outside `tests/`, and `copilot` is not a value `RUNNER_CLIS`
accepts — but the setting is live through session sync (`launchability.py:387-390`). An operator
following the product's advice about a policy that forbids MCP lands on the branch that tells their
agent it can do nothing.

**4. Two retired requirements sit thirty lines below the one this delta edits.**
`openspec/specs/agent-capability-plane/spec.md:140-185` still states the unasked-question backstop
and its operator conversion. That feature was retired 2026-08-20 at the operator's request, its
table is dropped by migration `0082_drop_unasked_questions.py`, `CLAUDE.md` forbids reintroducing
it, and `openspec/changes/2026-08-07-unasked-question-backstop` is still unarchived. Found while
checking that the `MODIFIED` block reproduced its requirement faithfully. **Deliberately not folded
in** — removing them belongs to retiring that change — but recorded in `proposal.md`, `design.md`
D8, and put to the operator.

### Housekeeping this round did

`tasks.md`'s round-2 section was appended as §6 and sat between §3 and §4; renumbered so the file
reads in order (§4 access path, §5 docs, §6 verification), with every cross-reference updated.
`design.md`'s new sections were appended ahead of its closer; renumbered D6–D8 with D9 last. Four
line ranges R2 cited from memory were corrected against the files after writing
(`agent_trigger.py:1087`, `agent_actions.py:440-529`, `conftest.py:496-507`).

### Verification

`openspec validate --strict` passes. The `resolve_access_path` measurement above was executed. No
product code changed, so no suite run and no lint set applies — `ruff`/`black`/`mypy` cover `src/`,
`hub/` and `tests/`, none of which this iteration touched. Nothing was driven: no Hub was started, no
agent turn was run, no web was browsed, all per this run's limits.

### Next

`next_action` is `S-3` — R3, a third independent pass. Its assigned targets are (a) whether every
mutating agent-facing route depends on the run credential rather than the older project key, and (b)
what happens to `mcp_server._decide`'s permission boundary for an agent with no MCP. On (a) this
round measured the cheap half — all 32 `agent-actions` routes take `Depends(get_agent_actor)` — and
left the real question open: whether `get_agent_actor` can be satisfied by anything other than a
live run's credential, and whether any *other* router exposes a mutating agent-facing route outside
that prefix. R3 should also check the two things R2 asserted and did not prove: that
`probe_mcp_registered`'s `<cli> mcp list` would in fact report a policy-blocked server as absent,
and that no test outside the two named ones was written believing conftest's false docstring.
