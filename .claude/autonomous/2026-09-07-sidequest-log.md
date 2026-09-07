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

---

## Iteration 3 — S-3, spec loop R3: the access path decides the posture, not just the notice

State verified before starting: branch `autonomous/2026-09-07-sidequest`, head `e1bf932`, parent
`8ee61b1`, clean tree. All match `STATE-sidequest.json`. Nothing to reconcile.

**Changed:** `proposal.md`, `design.md`, `tasks.md` and the `agent-capability-plane` delta of
`openspec/changes/2026-09-07-an-agent-without-mcp-is-not-told-it-has-nothing`.
`openspec validate --strict` passes. No product code touched.

### Target (a) — the run credential is the plane's only key. Confirmed, and it sharpens the premise.

`get_agent_actor` (`hub/hub/agent_auth.py:40-80`) accepts nothing but a credential prefixed
`aw_run_` that hashes to the `capability_token_hash` of a `Run` with `status == "running"` and a
matching instance id. An operator `aw_live_` key fails on the prefix before any lookup. Measured
three ways: all 32 `agent_actions` routes carry `Depends(get_agent_actor)` (parsed, not eyeballed —
0 without); no module outside `agent_actions.py` imports it; and a scan of every
`POST`/`PUT`/`PATCH`/`DELETE` decorator under `hub/hub/api/v1/` found no mutating route lacking an
auth dependency (four apparent hits were my scanner mis-parsing multi-line decorators — each was
read and each has `get_project` or `get_agent_actor`).

The part neither earlier round said: `_hub_request` (`hub/hub/mcp_server.py:151-183`), the one
helper every MCP tool goes through, authenticates with `os.environ["AW_RUN_TOKEN"]` against
`os.environ["HUB_URL"] + "/api/v1/agent-actions"`. **The adapter is literally a wrapper around the
two environment variables the notice tells the agent it has nothing to do with.** That is the
shortest proof of this change's premise available, and it is one import away.

### Target (b) — the boundary does not vanish. It is traded, through this change's own variable.

R3 was told that if `_decide`'s boundary simply disappears for a no-MCP agent, the proposal must say
so rather than ship a silently weaker adapter. It does not disappear. What it does is worse for the
argument: **`design.md` D1's claim that the notice and the boundary are unrelated is wrong, because
they share a variable.**

`mcp_command` is set **iff** `access_path == "mcp"` (`agent_trigger.py:1025-1028`). The approver is
itself an MCP tool, so `_build_claude_command` reads `mcp_command` to pick the posture
(`runner_commands.py:219-222`, `:244-254`). **Measured** by calling `build_command` twice — a pure
function, no Hub, no spawn:

| | `"mcp"` | `"cli"` |
|---|---|---|
| `--mcp-config` | present | absent |
| `--allowedTools` | `mcp__agentweave__*` | absent |
| `--permission-prompt-tool` | `mcp__agentweave__approve_tool_call` | **absent** |
| `--permission-mode` | `manual` (this repo's `workspace`) | **`acceptEdits`** |

So a run on the `cli` path has no `_decide` at all — not merely none for plane traffic. The repo's
own comment prices it: `workspace` "is *narrower* than `acceptEdits`, which accepted every edit with
no path check at all" (`runner_commands.py:66-67`). The fallback is deliberate and argued
(`:69-73`), so this is a considered trade, not a bug — but §1 of this change makes an agent able to
mutate shared state through the plane on exactly the path where its filesystem is least contained,
and each of D7's three mechanisms moves a run's containment as a side effect of deciding what the
run is *told*. An operator ticking "my harness has no MCP" would widen their agents' file
permissions from a control that says nothing about permissions.

**The delta therefore gains one scenario** — *a truer description does not silently widen
permission* — stated as a property about containment not changing as an undeclared consequence of
attribution. `design.md` D9 carries the measurement; `tasks.md` §4.8 carries the obligation.

### And the mirror may not be a wording defect at all

In the deployment this change exists for — `claude`, MCP blocked by policy, `hub_client` unset — the
path resolves to `"mcp"`, so the Hub emits `--permission-prompt-tool
mcp__agentweave__approve_tool_call` into a harness that will not provide that tool.
`runner_commands.py:245-248` states the consequence in its own words: *"naming an approver that will
not be there makes every tool call fail, which the model reports as a broken approval system."*

If that comment is right, such a run cannot edit a file or run a command — it is not an agent
misinformed about its tools, it is a run that cannot act. **That is the repository's own prediction
and it has never been driven.** Labelled unverified; `tasks.md` §6.5 now says to read the run's tool
calls, not only its prose, and §4.9 says to establish it before choosing a mechanism.

### Two corrections to round 2

**1. Restoring the probe is self-defeating, and D7 listed it first.** `probe_mcp_registered` shells
a **separate** `[cli, "mcp", "list"]` process with no `--mcp-config`. The server in question is
injected on the turn's own command line, per invocation. A separate process cannot see it. So a
restored probe answers `False` for essentially every Hub-injected run, resolves the path to `cli`,
and thereby removes the injection it was asked about — making its own answer true, and taking the
workspace posture with it (D9). §4.2 previously said to check what `mcp list` reports on a
policy-blocked harness; still worth doing, still not enough, because the probe asks the wrong
question on a *permitted* harness too. Only the exact output of `claude mcp list` is unverifiable
here; that the probe runs a process never given the config is a source reading.

**2. Three test files, not two.** R2 wrote that the probe's only remaining references were
`conftest.py` and `test_agent_trigger.py`. `hub/tests/test_launchability.py:390-429` is a third — a
`TestAccessPath` class whose docstring says the path "is probed per runner rather than assumed",
holding two more `F190`-shaped tests: `test_explicit_override_wins_without_probing` (`:406-413`)
guards against a probe call that cannot happen for *any* input, and
`test_auto_override_is_treated_as_unset_and_probes` (`:421-423`) has "and probes" in its name and
passes identically with the probe patched `True` or `False`. One test in the class is honest and
load-bearing — `test_injectable_runner_needs_no_global_registration` (`:424-429`) is the only place
the current unconditional behaviour is pinned, and §4.1's mechanism must update it deliberately.
`tasks.md` §4.7 names all of them. This is also the first answer to §4.4's standing question of
whether any test was written believing conftest's false docstring: yes, in a different file.

### Re-measured and held

R2's central measurement reproduces exactly: with the probe patched `False` as `conftest.py` patches
it, `resolve_access_path('claude','claude',…)` returns `mcp` / `mcp` / `cli` / `mcp` for `None` /
`'mcp'` / `'cli'` / `'auto'`, and `mcp` for `codex`; `access_path_notice('cli')` is word for word as
the proposal quotes it. `_decide`'s first branch allows `mcp__agentweave__*` outright
(`mcp_server.py:908-909`), so R1's decision to move it to the Copilot change stands — with D9's
qualification attached.

### Verification

`openspec validate --strict` passes. Two measurements executed under `py -3.11` against the source
tree: `resolve_access_path` / `access_path_notice`, and `build_command` for both access paths. No
product code changed — `git status` shows four openspec markdown files and nothing else — so no
suite run and no lint set applies (`ruff`/`black`/`mypy` cover `src/`, `hub/`, `tests/`; the
TypeScript set covers `hub/ui`, untouched). Nothing was driven: no Hub started, no agent turn, no
web, per this run's limits.

### Next

The first spec loop is complete at three rounds. `next_action` is `S-4` — decide the extraction
candidate set from `openspec/explorations/2026-09-07-what-is-actually-separable.md`, answer its
question 1 (are P1 and P2 one project or two), and create the sibling folders under
`C:\Users\huida\Documents\projects\` with `git init` and no remote.

One new item for the operator: whether `hub_client: cli` should keep meaning `acceptEdits`. Today
the product's own advice for "MCP is blocked by company policy" (`config.py:714`) lands an operator
on a path with no workspace check, and nothing tells them.

## Iteration 4 — S-4, the candidate set: one project, because the fork already happened

**Item:** S-4 — decide which extraction candidates get a folder, answer the seed's question 1, and
create the sibling repositories.

**Outcome:** one folder, not two. `C:\Users\huida\Documents\projects\continuity-kit`, `git init`,
no remote, openspec scaffolded and validated, first commit `0eb373d`. P2 folded into it. S-7 and
S-8 are therefore skipped, exactly as the queue anticipated.

### The finding that decided it, and it was not in either seed

**The capability this run was asked to extract is already forked, inside AgentWeave, by hand, with
nothing keeping the copies in sync.**

AgentWeave both *uses* the continuity kit and *ships* it:

| Copy | Path | Lines |
|---|---|---|
| in use | `.claude/skills/handoff/SKILL.md` | 341 |
| shipped | `src/agentweave/templates/skills/handoff.md` | 336 |
| in use | `.claude/skills/resume/SKILL.md` | 127 |
| shipped | `src/agentweave/templates/skills/resume.md` | 127 — byte-identical |
| in use | `.claude/handoffs/DEAD-ENDS.md` | 260 — **not shipped at all** |

`handoff.md` differs from the live `SKILL.md` on **11 lines** (`diff | grep -c '^[<>]'`). Every one
of them strips a reference to `/review-iteration`, a repo-local skill not shipped to users — so the
divergence is deliberate and hand-maintained. `tests/test_handoff_resume_templates.py` guards the
shipped copies with substring assertions (`"handoff-NNNN"`, `"DEAD-ENDS.md"`, `"Git state"`,
`"Pairs with /resume"`) and **never asserts that the two copies agree** about anything else.

That answers the seed's question 4 — *"is this an extraction or a fork?"* — empirically rather than
by argument: the fork already happened. A third hand-maintained copy in a sibling repository was
the default outcome of this queue item unless something prevented it, and now the new repo's own
seed requires R1 to name the upstream copy and the reconciliation mechanism before proposing
anything.

Second consequence, and a good first requirement for P1: **`DEAD-ENDS.md` is the one third of the
contract AgentWeave's users never receive**, and it is the third the skill argues hardest for in
its own text — *"individual facts were dropped and re-learned between three and seven times each,
with gaps of up to 46 handoffs."*

### The axis nobody had measured: inbound coupling

Both prior explorations ranked candidates by **outbound** dependency footprint — what a candidate
would drag with it. That is half an extraction. The other half is **inbound**: how many call sites
in AgentWeave would afterwards depend on an external package. Measured by `grep -rln` over
`hub/hub` and `src`:

| Candidate | Inbound importers | Verdict |
|---|---|---|
| `handoff` + `resume` + `DEAD-ENDS.md` | **0** — no product code reads them | extract |
| `hub/hub/checkpoint_policy.py` | 5 non-test modules | leave |
| `hub/hub/spec_lifecycle.py` | **17** modules under `hub/hub/` alone | leave |

`spec_lifecycle.py` ranked *fourth-most separable* on the outbound axis (390 lines, two tables) and
is close to unextractable on the inbound one — reached from `agents.py`, `agent_actions.py`,
`agent_trigger.py`, `loops.py`, `spec.py`, `tasks.py`, `db/models.py`, migration `0074`, and eight
`spec_*` modules. Extracting it would make AgentWeave a consumer of an external package for the
thing AgentWeave is *for*. The continuity documents are the mirror image, and for a structural
reason: they are read by the **agent**, not by the program. The only references anywhere in the
tree are a comment at `hub/tests/browser/conftest.py:58` and the distribution test above.

### Question 1 answered: one project

The deciding measurement is in `run-iteration.ps1`. It reads exactly **six** of the eighteen fields
its arming script writes, and the six split cleanly in half:

| Field | Line | Kind |
|---|---|---|
| `branch` | `:124` | continuity — used for precisely what `resume`'s Step 2 does by hand: check the stored position still describes the tree |
| `next_action` | `:132` | continuity — what the handoff template's `## Next steps` §1 already requires |
| `log_file` | `:114` | continuity — it names the per-iteration prose log, which *is* a handoff chain |
| `runner` | `:104` | launch configuration |
| `permission_mode` | `:105` | launch configuration |
| `model` | `:110` | launch configuration |

So the loop's machine contract is three continuity fields plus three fields telling a driver how to
spawn a process. The continuity three are a **strict subset, in machine form, of what the handoff
file already carries in prose**. There is one artifact here — a durable file a successor reads —
split by reader, not two products. Two repositories would mean two definitions of `next_action`
drifting apart: the fork failure measured above, reproduced deliberately.

The counter-argument, weighed rather than skipped: P1 serves an interactive session and P2 an
unattended one, and their failure modes differ. It loses because the driver already treats them
identically — re-verifying `branch` against reality every firing is the interactive `resume` ritual
executed by a machine.

### What folding costs, and it is a real narrowing

Two things the seed listed as P2's value are **not** in the new repository and are not planned:

- **The scheduler** — 877 lines of Windows PowerShell (`arm-cycle.ps1` 243, `install-tasks.ps1` 138,
  `install-driver.ps1` 230, `run-iteration.ps1` 266) against ~1,010 lines of markdown playbook. All
  behaviour lives in the markdown; `Unregister-ScheduledTask` at `run-iteration.ps1:75,96,134` is
  the stop mechanism, called from inside the iteration body, and is structurally Windows-bound.
- **The operator-approval protocol** (`spec-queue/`: the five-row who-writes-what table, the status
  token that is the authority with deliberately no checkbox, `ORDER`/`NOTHING TONIGHT`). A good
  file contract and a *different* one — a person negotiating with a process, not a session handing
  to its successor. A candidate for its own project later.

This narrows what the operator asked for and it is theirs to overturn; it is in `decisions_for_user`.

### Rejected, each on a measurement

- **The checkpoint engine.** 2,596 lines across `hub/hub/checkpoint*.py`, 11 of the 44
  `__tablename__` declarations in `db/models.py` (44 confirmed by count), and the decisive point
  read in full at `checkpoint_generation.py:11-14`: the probe works *because* it can compare a
  checkpoint against `files_changed`, `tasks` and `open_questions` sitting in a table — *"Factory
  needed an LLM judge because they had nothing to compare against."* Strip the tables and it
  degenerates into the design its own docstring calls inferior.
- **`spec_lifecycle.py`** — 17 inbound importers.
- **The review-page checkers** — 199 lines confirmed (94 + 105), but they check *this* repo's
  conventions, one needs Playwright, and one has emitted a known false red since 2026-09-05. A
  script, not a product.

### Seed numbers that did not reproduce

Reported because the point of re-measuring is that citations move. Exact: 728 lines of continuity
markdown; 199 lines of review-page checkers; six of eighteen `STATE.json` keys. Off: 879 → **877**
PowerShell lines, 1,047 → **1,010** playbook lines, a "4,567-line checkpoint stack" → **2,596**
across the `checkpoint*`-prefixed files (upstream evidently counted unprefixed files too; the
qualitative point stands). One claim I corrected in my own draft after checking: the handoff
skill's Step 5 checklist is **14** items, not thirteen.

**Not measurable here:** the live handoff chain. `.claude/handoffs/` is untracked since 2026-09-04,
so the working copies exist only in the main checkout, which this run may not enter. Git history
shows **72 distinct numbered handoff files** ever tracked and 162 distinct paths ever added under
that directory. The seed's "111 handoffs" is therefore carried as a claim, not a measurement.

### What was created

`C:\Users\huida\Documents\projects\continuity-kit\` — `git init`, **no remote**, branch `master`,
commit `0eb373d`:

- `README.md` — what it is, what it was lifted from with commit and line counts, the scope decision,
  and a status table saying plainly that there are no specs, no code, no tests and no governance.
- `openspec/config.yaml` — project context and authoring rules, including the standing requirement
  that any proposal name which `handoff.md` is upstream.
- `openspec/explorations/2026-09-07-what-was-measured-before-this-repo-existed.md` — the full seed
  for R1: the measurements above, the five questions R1 must answer rather than inherit, and a
  section on what was not measured.
- `openspec/specs/`, `openspec/changes/archive/` — empty, from `openspec init --tools none`.

Question 4 for R1 was sharpened beyond the seed's version, because the fork finding gave it teeth,
and a fifth question was added that neither seed asked: **what in this contract is mechanically
checkable and what is irreducibly the model's judgement?** The kit's own recorded failure modes are
all in the checkable half — `## Corrections to the previous handoff` present in 5 handoffs out of
108, `Model:` filled 7 out of 108, and a chain tracked through `0073` and ignored from `0074` whose
clone silently resumed from month-old state. A checker with no model in it would have caught all
three, and that is the strongest available argument that this is a *product* and not just a
document.

### Verification

- `openspec init --tools none` in the new repo, then `openspec list` (clean) and a throwaway
  `tmp-probe` change carrying one `SHALL` requirement: **`openspec validate --strict tmp-probe`
  returned "Change 'tmp-probe' is valid", exit 0**, proving the hand-written `config.yaml` does not
  break validation before S-5 relies on it. Probe deleted; `git status` clean.
- `git remote -v` in the new repo returns nothing. Confirmed twice.
- Every line count, importer count and line citation above was run in this session against the
  worktree at `903ad6b`. Four claims carried from the seed were re-checked before being repeated
  (`checkpoint_generation`'s docstring, the 44 tables, `Unregister-ScheduledTask`'s three call
  sites, the Step 5 checklist length) and one of them was wrong.
- **No AgentWeave product code was touched.** `git status` in this worktree shows only
  `.claude/autonomous/` files, so no lint or test set applies.
- Nothing driven: no Hub, no agent turn, no web, per this run's limits.

### Next

`next_action` is `S-5` — spec loop R1 for the continuity kit, written **inside**
`C:\Users\huida\Documents\projects\continuity-kit`, not here. S-7 and S-8 are marked `skipped`
because P2 folded in.
