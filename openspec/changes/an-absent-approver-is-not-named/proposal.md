> **OPERATOR QUESTION — answer before this is approved. The measurement contradicts the verdict's
> premise.** `DECISIONS.md` 1b was decided against F299's 2026-09-09 drive, in which the Hub's
> configuration *started* a turn, read, was refused every write, and blamed the operator's machine.
> Re-driven today on the installed **`claude` 2.1.269**, with the argv `build_command` itself
> produces, spawned through the Hub's own `PtySession`, in both spawn environments (a Hub started
> inside Claude Code and one started from a plain terminal): **that configuration no longer starts a
> turn.** It exits 1 before any model call, spending nothing. The harness's own two lines reach the
> conversation: `Warning: MCP server blocked by enterprise policy: agentweave` and
> `Error: MCP tool mcp__agentweave__approve_tool_call (passed via --permission-prompt-tool) not
> found`. **On this build, 1b as written swaps that free and truthful failure for a paid turn.** Its
> writes are all refused, and its model asks the operator to *"approve the request"*, which no
> surface can show. Answer in one line, with one of:
>
> - **(a)** 1b, plus `--permission-prompts none` on the approver-less spawn, gated on a known harness
>   build. The Hub records no build today, so this adds a version probe. Measured once per
>   environment: the model then says *"no approval surface"* (4 of 4), and it still retried through
>   another tool in 1 of those 4.
> - **(b)** Hand 1b back. On current builds the first run already fails truthfully. What the
>   operator lacks is a Hub-authored sentence in place of two raw harness lines, which is the day's
>   research candidate 3 and a new decision, not 1b.
> - **1b as written**, which is what this proposal specifies.
>
> This proposal is written for **1b as decided**, and the window does not choose between them.
> Measurement: `design.md` *"What the installed harness does"*. Research: `spec-queue/research/
> 2026-09-13.md` candidate 1.

## Why

**F299 (A).** A `claude` run on a harness whose policy blocks MCP servers cannot write, and until
2.1.269 at least it said the operator's machine was broken. The Hub injects its tool server with
`--mcp-config`, and because a server was configured it also names that server's
`approve_tool_call` as the run's approver with `--permission-prompt-tool`
(`hub/hub/runner_commands.py:250-254`). The harness ignores the server, so nothing answers. The
repository predicted the failure in the comment directly above that line (`:245-248`) and did not
drive it.

**The verdict is binding and this proposal implements it.** `DECISIONS.md` 1b (2026-09-10): *"when
there are no grounds that the harness honours MCP, do not emit `--permission-prompt-tool`."* It
connects the measurement that already decides what a run is **told**
(`launchability.harness_has_honoured_mcp`, `:232-259`) to the function that decides what a run is
**given** (`_build_claude_command`). It narrows nothing further and widens nothing.

**Round 1 found that the verdict cannot be implemented on the signal it names, at the grain it
states.** 1b says *"from the second run of an agent whose adapter has never come online"*.
`harness_has_honoured_mcp` is false both for that agent and for **every agent's first run**,
because no run of a fresh agent has an `mcp_adapter_online_at` yet. Implemented literally, *"no
grounds, no flag"* would drop the approver from the first turn of every new agent. That includes
agents on harnesses that honour MCP perfectly well. Those turns would run under Claude's `manual`
with no answerer, and every write would be refused, which breaches the shipped scenario *"A newly
created agent can edit files in its own workspace"* (`agent-run-sandboxing`). The verdict's
*"second run"* needs something the Hub does not record today, which is that a first run was given
the server and the harness got as far as starting. This change records that fact. It is the Hub's
own record of what it gave, not a new harness signal.

**Round 1 also found that the verdict, as written, would newly breach a second shipped
requirement.** A Claude run's refusals reach the Hub's record only through `approve_tool_call`, the
approver itself (`agent_trigger.py:2759-2764`). On 2.1.269, a run spawned under 1b's shape starts,
has its writes refused by the harness, and leaves no `permission_denied` event, so the durable
record shows a clean run. *"A refusal is recorded wherever it is decided"* (`agent-run-sandboxing`)
requires otherwise. The harness already reports each refusal in its own result line
(`permission_denials`), and the Hub does not read it (`runner_parsing.py:306` onward). This change
reads it for runs that carry no approver.

## What changes

- **Three states per agent, read at spawn**, beside the existing grounds:
  - *grounds*: the operator said `hub_client: "mcp"`, or some run of this agent saw the adapter
    report in. This is today's signal, unchanged.
  - *untested*: no grounds, and no earlier run of this agent was a test of the harness. **The
    approver is named, exactly as today.** The first spawn is the test.
  - *refuted*: no grounds, and at least one earlier run was given the Hub's server, reached the
    harness, and ended without the adapter reporting in. **The approver is not named.**
- **The Hub records, per run, whether it injected its server** (`Run.mcp_server_injected`, a new
  nullable column, migration `0103`). Rows from before it are NULL and are never counted as a test,
  so an upgrade moves no agent into *refuted*.
- **`_build_claude_command` omits `--permission-prompt-tool` on *refuted*, and nothing else
  changes.** The permission mode stays what it would have been (`manual` for the default posture
  and for an operator's *Workspace only* or *Ask me*). `--mcp-config` and `--allowedTools` stay, so
  a lifted policy earns grounds back on the next spawn without anyone acting.
- **A Claude run spawned without the approver has its harness refusals recorded**, from the
  result line's `permission_denials`, as `permission_denied` events with `decided_by: "runtime"`.
  This covers every approver-less Claude run, not only *refuted* ones. The mechanism cannot tell
  them apart, and the shipped requirement is breached identically on each (`design.md` D6).
- **The operator page states the new case**: a *Workspace only* run on a harness that has been seen
  not to start the Hub's server gets no approver, has every approval-needing call refused, and has
  those refusals recorded.

## What does not change

- **What the run is told.** `described_access_path` is untouched. A run with no grounds is still
  told the HTTP form.
- **Injection.** `resolve_access_path` is still moved only by the operator's `hub_client`.
- **Containment.** No posture is substituted. The verdict's rejected alternative, dropping to
  `acceptEdits` on no grounds, is not reintroduced (`DECISIONS.md` 1b, *"Rejected"*).
- **Codex.** Its app-server answers approvals itself, and `--permission-prompt-tool` is Claude-only.
- **The first run in F299's configuration.** It is *untested*, gets the approver, and behaves
  exactly as today: on 2.1.269 it fails at spawn.

## Capabilities

### Modified capabilities

- `agent-run-sandboxing`
  - ADDED *"An approver the harness has been seen not to start is not named"*.
  - MODIFIED *"A refusal is recorded wherever it is decided"*, which gains a scenario for an
    approver-less Claude run.

`agent-capability-plane` is not modified. Its *"A truer description does not silently widen
permission"* holds, because the flag's removal changes no answer (`design.md` D8).

## Collision check (DIRECTION `## 2026-09-13`)

This change touches `hub/hub/runner_commands.py`, `hub/hub/launchability.py`,
`hub/hub/api/v1/agent_trigger.py` (the access-path block, the `Run(...)` construction and the
Claude read loop), `hub/hub/runner_parsing.py`, `hub/hub/db/models.py`, a new migration `0103`, the
two migration-head tests, and `docs/reference/permission-postures.md`. **`agent_trigger.py` is also
F327's review-dispatch path** (`review_dispatch_refusal`, `:452`, called at `:1461`). The regions
differ, but the rule is *"shares no file"*, so the second loop does not run today.

## Impact

- Python only. No `hub/ui` change, so the committed bundle is not rebuilt.
- One migration (`0103`), one nullable column, no backfill.
- No API or schema change on any route. `permission_denied` is an existing event kind with an
  existing `decided_by: "runtime"` shape (`agent_trigger.py:2776-2788`).
