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
