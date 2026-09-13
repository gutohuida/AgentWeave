> **OPERATOR QUESTION — answer before this is approved. The measurement changes what the verdict
> replaces.** `DECISIONS.md` 1b was decided against F299's 2026-09-09 drive. In that drive the Hub's
> configuration started a turn, read, was refused every write, carried on, and blamed the operator's
> machine. Re-driven today on the installed **`claude` 2.1.269**, with the argv `build_command`
> itself produces, spawned through the Hub's own `PtySession`, in both spawn environments:
>
> - **That configuration still starts a turn and works until its first approval-needing call.** A
>   turn that needs no approval completes normally.
> - **At the first approval-needing call, the harness process dies**, exit 1, with no result line.
>   The conversation shows the harness's own two lines, `Warning: MCP server blocked by enterprise
>   policy: agentweave` and `Error: MCP tool mcp__agentweave__approve_tool_call (passed via
>   --permission-prompt-tool) not found`. The model call before it was paid for, and the Hub records
>   that turn's usage as *unavailable*, because Claude's spend reaches the Hub only on the result
>   line.
>
> *(Round 1 wrote that this configuration "exits 1 before any model call, spending nothing". Round 2
> found a model call and a `Write` attempt in every one of Round 1's own transcripts. Round 1 had
> read the absence of a result line as the absence of a model call. `design.md`, "What round 2
> changed".)*
>
> **On this build, 1b as written swaps a turn killed at its first write for a turn that survives the
> refusal.** That turn is recorded, its spend and refusals included, and its model asks the operator
> to *"approve the request"*, which no surface can show. Answer in one line, with one of:
>
> - **(a)** 1b, plus `--permission-prompts none` on the approver-less spawn, gated on a known harness
>   build. The Hub records no build today, so this adds a version probe. Measured once per
>   environment: the model then says *"no approval surface"* (4 of 4), and it still retried through
>   another tool in 1 of those 4.
> - **(b)** Hand 1b back. On current builds the run already ends at its first write, with the
>   harness's own error naming the blocked server. What the operator lacks is a Hub-authored
>   sentence in place of two raw harness lines, which is the day's research candidate 3 and a new
>   decision, not 1b.
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
*"second run"* needs two facts the Hub does not record today: that an earlier run was given the
server, and that its harness got as far as reporting its own start. Round 2 measured why the second
fact is needed. On a harness that honours MCP perfectly well, an unknown option in the runner's
flags makes the harness exit 1 before it starts any server. Without the second fact, that one typo
would take away a working approver on the next run. This change records both facts. The first is
the Hub's own record of what it gave. The second is the harness's `init` line, which the Hub's read
loop already receives and does not keep.

**Round 1 also found that the verdict, as written, would newly breach a second shipped
requirement.** A Claude run's refusals reach the Hub's record only through `approve_tool_call`, the
approver itself (`agent_trigger.py:2759-2764`). On 2.1.269, a run spawned under 1b's shape starts,
has its writes refused by the harness, and leaves no `permission_denied` event, so the durable
record shows a clean run. *"A refusal is recorded wherever it is decided"* (`agent-run-sandboxing`)
requires otherwise. The harness already reports each refusal in its own result line
(`permission_denials`), and the Hub does not read it (`runner_parsing.py:306` onward). This change
reads it. Each refusal is recorded once, joined on the tool call's id. Round 2 measured that the
approver's own refusals appear there too, under the same `tool_use_id` the approver was handed and
already records.

**Round 2 found that the verdict meets a third shipped requirement, and that the verdict itself
decided that case.** *"The default posture lets an agent work inside its own workspace"* says the
Hub MUST NOT impose, by default, a posture that only an absent answerer can resolve. On a harness
that refuses the Hub's server, every run breaches that clause today, and every run still breaches
it under 1b. The verdict says so plainly: *"It does not restore the run's ability to work"*, and it
rejects the one posture that would. A spec that adds 1b's requirement beside that clause unchanged
contradicts itself. This change states the exception in that requirement instead.

## What changes

- **Three states per agent, read at spawn**, beside the existing grounds:
  - *grounds*: the operator said `hub_client: "mcp"`, or some run of this agent saw the adapter
    report in. This is today's signal, unchanged.
  - *untested*: no grounds, and no earlier run of this agent was a test of the harness. **The
    approver is named, exactly as today.** The first spawn is the test.
  - *refuted*: no grounds, and at least one earlier run was given the Hub's server, had its harness
    report its own start, and ended without the adapter reporting in. **The approver is not named.**
- **The Hub records two facts per run, in two new nullable columns (migration `0103`):**
  - whether it injected its server (`Run.mcp_server_injected`);
  - when the harness reported its own start (`Run.harness_init_at`), which is the first
    `system/init` line the read loop parses.

  Rows from before the migration are NULL, and NULL is never counted as a test, so an upgrade moves
  no agent into *refuted*.
- **`_build_claude_command` omits `--permission-prompt-tool` on *refuted*, and nothing else
  changes.** The permission mode stays what it would have been (`manual` for the default posture
  and for an operator's *Workspace only* or *Ask me*). `--mcp-config` and `--allowedTools` stay, so
  a lifted policy earns grounds back on the next spawn without anyone acting.
- **A Claude run's harness-reported refusals are recorded**, from the result line's
  `permission_denials`, as `permission_denied` events with `decided_by: "runtime"`. A refusal this
  run already recorded under the same `tool_use_id` is skipped, whether the approver or the
  operator recorded it. That covers every Claude run, with or without an approver. It includes the
  refusals an approver-named run could not record, because its approver never answered or its
  report was lost (`design.md` D6).
- **The default-posture requirement states its one exception**: a run whose harness has been seen
  not to start the Hub's server gets no posture that needs no answer, as 1b decided (`design.md`
  D11).
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
  exactly as today. On 2.1.269 it works until its first approval-needing call and dies there.

## Capabilities

### Modified capabilities

- `agent-run-sandboxing`
  - ADDED *"An approver the harness has been seen not to start is not named"*.
  - MODIFIED *"A refusal is recorded wherever it is decided"*, which gains the harness's own
    report as a source, recorded once per tool call.
  - MODIFIED *"The default posture lets an agent work inside its own workspace"*, which states the
    exception 1b decided, so the spec does not contradict itself (round 2).

`agent-capability-plane` is not modified. Its *"A truer description does not silently widen
permission"* holds, because the flag's removal changes no answer (`design.md` D8).

## Collision check (DIRECTION `## 2026-09-13`)

This change touches `hub/hub/runner_commands.py`, `hub/hub/launchability.py`,
`hub/hub/api/v1/agent_trigger.py` (the access-path block, the `Run(...)` construction and the
Claude read loop), `hub/hub/runner_parsing.py`, `hub/hub/db/models.py`, a new migration `0103`,
`hub/tests/test_migrations.py`, and `docs/reference/permission-postures.md`. Round 2 added no file.
`test_project_persistence.py` upgrades to `"head"` and has no literal to bump. **`agent_trigger.py` is also
F327's review-dispatch path** (`review_dispatch_refusal`, `:452`, called at `:1461`). The regions
differ, but the rule is *"shares no file"*, so the second loop does not run today.

## Impact

- Python only. No `hub/ui` change, so the committed bundle is not rebuilt.
- One migration (`0103`), two nullable columns, no backfill.
- **New operator-visible rows on runs that exist today.** Claude runs without an approver, which
  are the `hub_client: "cli"` path and the operator's *Edit files*, now record the refusals the
  harness decided, for example each headless `Bash` refusal under `acceptEdits`. Until now they
  recorded none. That is the shipped requirement being met, but an operator will notice it.
- No API or schema change on any route. `permission_denied` is an existing event kind with an
  existing `decided_by: "runtime"` shape (`agent_trigger.py:2776-2788`).
