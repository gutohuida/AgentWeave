# Design — an absent approver is not named

## Which harness behaviour this is designed for

**Stated first, because the argument depends on it and the Hub records no harness build.** This
design implements `DECISIONS.md` 1b, which was decided against F299's drive on 2026-09-09. That
drive did not record its `claude` build. This routine read `2.1.238` on the mornings of 2026-09-10
and 2026-09-11, and the shim was rewritten to `2.1.269` at 2026-09-11 23:00:04, so the build was
probably 2.1.238. **That is unverified.**

The mechanism (D1–D4) does not depend on the build. Its trigger is the Hub's own record, not a
harness message. **Its value does depend on the build**, and this design names two behaviours:

- **H-2026-09-09**, as F299 recorded it: the approver-named spawn *starts*, reads, is refused every
  write, and the model blames the machine. On this behaviour 1b does what it says, turning
  *"contact your system administrator"* into *"I need permission to write the file"*.
- **H-2.1.269**, as measured below: the approver-named spawn exits 1 at startup and costs nothing.
  On this behaviour 1b turns a free, truthful failure into a paid, all-refused turn. That is why
  `proposal.md` opens with the operator question.

## What the installed harness does (R1, 2026-09-13, `claude` 2.1.269)

`scripts/drive/t_d2_0913_f299_harness.py`. It builds argv with `runner_commands.build_command`
itself, where it can produce the condition. It spawns through `hub.pty_runner.PtySession`, as
`agent_trigger.py:2034` does for Claude. The day's research used `subprocess` pipes, and
`PipeSession` (`pty_runner.py:357`, `stderr=STDOUT`) is **Codex's** spawn, not Claude's. Each
condition ran once in each of two environments:

- **inherit**: this process's own environment, including `CLAUDECODE` and `CLAUDE_CODE_*`. This is
  what a Hub started inside a Claude Code session hands its children, because
  `launchability.resolve_agent_env` starts from the Hub's `os.environ`.
- **plain**: every `CLAUDE*` variable removed. This is a Hub started from an ordinary terminal.

Other conditions: Haiku (`claude-haiku-4-5-20251001`), a throwaway directory under `%TEMP%`, and
F299's own prompt. The "policy" is `deniedMcpServers` given through `--settings`, not a managed
settings file.

| cond | argv | inherit | plain |
|---|---|---|---|
| **A_hub** | today's `build_command` for a `claude` run with the server injected, plus the policy | **exit 1, no model call**. Stream: `init` (no `agentweave` entry), `Warning: MCP server blocked by enterprise policy: agentweave`, `Error: MCP tool mcp__agentweave__approve_tool_call (passed via --permission-prompt-tool) not found. Available MCP tools: none` | identical |
| **A_repro** | F299's reproduction flags: `manual` + approver, no `--mcp-config` | exit 1, no model call, the `not found` line only | identical |
| **B_1b** | A_hub with only `--permission-prompt-tool …` removed. **This is the shape 1b produces.** | exit 0, 2 turns, $0.0232, denied `['Write']`. The `Warning … blocked` line is still in the stream. Model: *"I need your permission to write the file. Please approve the request"* | exit 0, 2 turns, $0.0236, `['Write']`. *"You should see a permission dialog — please approve it"* |
| **B_q5** | the research's Q5: `manual` only, no `--mcp-config` | exit 0, `['Write']`, *"Please approve the permission prompt"* | exit 0, `['Write']` |
| **C_1b_none** | B_1b plus `--permission-prompts none` (shape (a)) | exit 0, 2 turns, `['Write']`, *"this session is non-interactive and doesn't have approval to write files"* | exit 0, **3 turns**, `['Write', 'PowerShell']`: **it retried**. *"non-interactive session without an approval surface"* |
| **C_q3** | the research's Q3: `manual` + `--permission-prompts none` | exit 0, `['Write']`, *"doesn't have an interactive approval surface"* | exit 0, `['Write']` |

What this settles:

1. **The research's startup-failure rows reproduce through the Hub's own spawn.** That covers
   P4 = A_repro and Q4b = A_hub.
2. **The inherited `CLAUDE*` environment is not the explanation** for F299's 2026-09-09 start.
   Both environments behave identically on every row. The most likely remaining cause is the
   harness build, and that is unmeasured.
3. **B_1b behaves as 1b's "condition C" said.** Same denial, and the model asks for approval rather
   than blaming the machine. **So the verdict's claim about the message holds on 2.1.269. Its claim
   about the state it replaces does not.**
4. **Under the PTY, the `init` line is printed before the failure** in A_hub and A_repro. That is
   why `evidence/r1-harness-results.json` reads `"started": true` for them. The field means *init
   emitted*, not *a model call*, and the script now calls it `init_emitted`. A model call is the
   presence of `subtype`/`num_turns`, which those rows lack. The
   `agentweave` entry is absent from `init.mcp_servers` whenever the policy applies, with or without
   the approver. Research candidate 3 builds on this. This change does not.
5. The denied `Write` was **inside** the run's workspace, so 1b's shape refuses in-workspace work.

## Decisions

### D1. Three states, not two

| state | condition | approver named? |
|---|---|---|
| *grounds* | operator `hub_client: "mcp"`, **or** `harness_has_honoured_mcp` is true | yes, as today |
| *untested* | no grounds, and no earlier run of this agent counts as a test (D3) | **yes, as today** |
| *refuted* | no grounds, and at least one earlier run counts as a test | **no** |

The verdict's words map onto it directly. *"From the second run of an agent whose adapter has never
come online"* is *refuted*, and the first run is *untested*.

### D2. Why the verdict's signal alone cannot carry it

1b says *"same signal, same grain"*. The signal, `Run.mcp_adapter_online_at` read through
`harness_has_honoured_mcp`, answers one question: has this agent's harness ever started the Hub's
server? A *no* covers two different agents. One has never run. The other ran and its harness did
not start the server. Only the second is F299.

A literal *"no grounds → no flag"* fires on the first. A fresh agent's first turn on a harness that
honours MCP would get the server, with the adapter coming online, and no approver. Its writes would
be refused for that turn, even though its approver was the one thing that would have worked. That
breaches `agent-run-sandboxing`'s *"A newly created agent can edit files in its own workspace"*
for every new agent on every permitted machine, which is the ordinary case.

So the grounds stay exactly as they are, and the verdict's *"second run"* needs one more fact. The
Hub does not record whether it *gave* a run its server, and `resolve_access_path` depends on
`hub_client`, which can change between runs. D3 records it.

### D3. What counts as a test of the harness

A new nullable column, `Run.mcp_server_injected` (Boolean). It is written in the `Run(...)`
construction (`agent_trigger.py:1190`) as `mcp_command is not None`. `mcp_command` is computed
earlier in the same function, where the access path is resolved. Migration `0103` adds it with no
server default and no backfill. That follows `0096`, `0101` and `0102`, and has the same guard for a
missing `runs` table.

An earlier run **counts as a test** when all of the following hold:

- the same `project_id` and `agent`;
- `mcp_server_injected IS TRUE`. NULL means *not recorded*, from before `0103`. Counting it would
  move every upgraded agent into *refuted* on the strength of rows that never measured anything.
- `mcp_adapter_online_at IS NULL`;
- `exit_code IS NOT NULL`, so the harness process existed and exited. A spawn that raised
  (`agent_trigger.py:2050-2056`) sets `status="failed"` and never sets `exit_code`, so a missing
  binary does not refute anything.
- `status IN ('completed', 'failed')`. A *stopped* run may have been killed before the harness got
  to its servers, and a *running* one has not finished starting. Both are excluded, so the
  conservative direction is today's behaviour.

The read is one `EXISTS` query beside `harness_has_honoured_mcp`, in `launchability.py`. It is made
at the same point in `trigger_agent_directly` (`agent_trigger.py:1000-1005`), before this run's own
row exists, so the run can never count as its own test.

**Grain: per agent, as the verdict states.** That inherits the verdict's known property. An agent
re-bound from one runner to another carries its evidence across. It is stated here, not fixed.

### D4. What the command carries on *refuted*

`build_command` and `_build_claude_command` take a new keyword, `approver_available: bool = True`.
When it is `False`:

- `--permission-prompt-tool` is **not** emitted, whether it was asked for by the default posture
  (`defaults_to_approver`) or by an operator's `permission_mode` of `workspace` or `manual`
  (`APPROVER_PERMISSION_MODES`, `runner_commands.py:250-253`). 1b is unqualified, and an approver
  flag the harness will not serve is equally absent whichever posture asked for it.
- `--permission-mode` is **unchanged**. The default still spells `manual`, and an operator's choice
  still arrives through `control_args`. **No other posture is substituted.** The verdict rejects
  `acceptEdits` on no grounds, and `DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER` is not used
  here: that constant is for a run with **no server configured**, and this one has a server that the
  harness refused.
- `--mcp-config` and `--allowedTools mcp__agentweave__*` are **unchanged**. Injection is
  `resolve_access_path`'s decision, which only the operator moves. Keeping the server on the command
  line is also how a lifted policy is noticed: the adapter reports in, grounds are earned, and the
  next run gets its approver back.

The default is `True`, so every existing caller and test builds exactly today's argv.

### D5. Codex is untouched

`--permission-prompt-tool` is Claude-only. Codex's app-server answers approvals itself
(`codex_appserver.decide_approval`), and `_build_codex_command` never names an approver.
`approver_available` is accepted by `build_command` and ignored on the Codex branch.

### D6. Refusals decided by the harness are recorded, for every approver-less Claude run

**Why this is in the change.** Today a Claude run's refusals reach the record through
`approve_tool_call` only (`agent_trigger.py:2759-2764`, `_on_refusal`'s docstring). A run in 1b's
shape starts on 2.1.269 and has its writes refused by the harness, and without this change nothing
records them. That is a new breach of the shipped *"A refusal is recorded wherever it is decided"*.
Its scenario *"A runtime refuses an action on its own"* is exactly this case, and the change would be
causing it.

**Why every approver-less Claude run, not only *refuted* ones.** A run under `acceptEdits` (the
`cli` path and the no-server fallback), an operator's *Edit files*, or *refuted* all have the same
property: the harness decides refusals, and the Hub never hears of them. The recording rule is *the
command named no approver*. That is known at spawn and needs no second rule. Runs **with** the
approver are excluded, so a refusal `_decide` or the operator already recorded is not recorded
twice. That is the requirement's *"A refusal SHALL be recorded once"*.

**Mechanism.** `ParsedLine` gains `refusals: List[dict]`. `parse_claude_line`'s `result` branch
(`runner_parsing.py:306`) fills it from `permission_denials`: each entry's `tool_name` and a
`detail`, which is `tool_input.file_path`, then `tool_input.command`, then empty. `_flush_line`
(`agent_trigger.py:2140`) records each one as a `permission_denied` event, in the same shape
`_on_refusal` writes for Codex (`:2776-2788`), with `decided_by: "runtime"`, **only when the argv
`_execute_run` actually spawned carries no `--permission-prompt-tool`**. It reads the command, not
a recomputation of the state, so the record and the spawn cannot disagree. The reason is a fixed sentence, because
`permission_denials` carries none, capped as *"A refusal's reason fits the record that carries it"*
requires: *"Refused by Claude Code: no approver was available to this run."*

**Its limit, stated.** `permission_denials` arrives on the `result` line only. A run killed before
its result line records none of its refusals. That is no worse than today, which records none at
all.

### D7. What the operator sees (the F108 question)

| run | on H-2.1.269 (measured) | on H-2026-09-09 (F299's record) |
|---|---|---|
| **first** (*untested*, approver named, unchanged) | `run_failed`, exit 1, zero tokens. The conversation shows two harness lines as the agent's text (`runner_parsing.py:234-238` turns a non-JSON line into a text event): the policy block and the `not found` error. | completed, 5 turns. Refusals are **not** recorded, because no approver answered. The model blames the machine. |
| **second on** (*refuted*, new) | completed, about 2 turns, paid. The conversation shows the `Warning … blocked by enterprise policy` line and the model's *"please approve"*. **New:** a `permission_denied` row per refused call, naming `Write` and the path. | completed. The model says *"I need permission to write the file"*. **New:** the refusal rows. |
| **the turn-start notice** (unchanged) | The HTTP form, since there are no grounds. The request it tells the run to make is refused by the harness, and is now recorded. That is F301's ground (DIRECTION order item 3), not this change's. | same |

**Nothing Hub-authored tells the operator why.** The only sentence naming the cause is the
harness's own stderr, and on *refuted* runs it arrives as a line of conversation text. Turning it
into a Hub notice naming `hub_client: "cli"` is research candidate 3, a new decision, and option
(b) of the operator question.

### D8. Why `agent-capability-plane` is not modified

*"A truer description does not silently widen permission"* forbids changing a run's containment
**as an undeclared consequence of attribution**. This change moves no containment. Measured on
2.1.269: B_1b refuses the same `Write` that A_hub's configuration would have refused, if it had
started. Under H-2026-09-09, F299's condition A (flag named) and condition C (no flag) each refused
every mutating call they attempted: A tried three tools and C tried one, which is the model retrying,
not a different answer. The flag
named an answerer that never answers, and removing it changes who is *named*, not what is
*allowed*. The trigger is also not the description. It is the Hub's own record of a completed
test (D3), and the requirement is stated in the new sandboxing requirement, so nothing about it is
undeclared.

R2 should attack this paragraph. If an H exists where an approver named but absent *allows*
something that `manual` without an approver refuses, D8 is wrong.

### D9. Risks, stated rather than fixed

- **A failed announce now costs one turn, not one description.** `mcp_server.py`'s
  `_announce_adapter_online` is best-effort and suppresses every error (`:1817-1822`). Before this
  change, a lost announce meant the next run read the HTTP form, which is the docstring's *"which
  works"*. After it, a lost announce on a permitted harness counts as a test (D3), so the next run
  gets no approver and its writes are refused. The server is still injected, so that run's own
  announce restores grounds, and the run after it is whole again. It corrects itself after one bad
  turn, and the operator is not told.
- **Grounds are permanent (research candidate 3).** An agent that ever had grounds keeps the
  approver after a policy arrives, and on 2.1.269 every later run fails at spawn. This change
  inherits that unchanged. 1b says *"same signal"*, and a negative signal is a new decision. D-7 of
  today's window files it.
- **The first run in F299's configuration is unchanged.** Every agent on a blocking machine still
  has one *untested* run that fails (on H-2.1.269) or misattributes (on H-2026-09-09).
- **The Hub still records no harness build**, so nothing in the product can tell which H it is on.

### D10. Not in scope, and where it went

- **Research candidate 2**: `acceptEdits` is path-confined by the harness on 2.1.269. It
  contradicts the reason 1b's rejected alternative was rejected (`DECISIONS.md:772-773`). This
  change neither relies on it nor reintroduces the alternative. It goes to the operator as a finding
  (today's queue item D-7), not as a reversal written here.
- **`--permission-prompts none`**: operator question, option (a). It is an *unknown option* before
  2.1.259 (research candidate 1), and the Hub cannot tell which build it spawns.
