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
- **H-2.1.269**, as measured below: the approver-named spawn starts and works until its first
  approval-needing call. At that call the harness process dies, exit 1, with no result line, after
  a model call the Hub records as usage *unavailable*. On this behaviour 1b turns a turn killed at
  its first write into one that survives the refusal, all-refused and recorded. That is why
  `proposal.md` opens with the operator question. *(Round 1 wrote "exits 1 at startup and costs
  nothing". See "What round 2 changed".)*

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
| **A_hub** | today's `build_command` for a `claude` run with the server injected, plus the policy | **exit 1 at the first approval-needing call, no result line**. Stream: `Warning: MCP server blocked by enterprise policy: agentweave`, `init` (no `agentweave` entry), **a model call with a `Write` tool_use**, then `Error: MCP tool mcp__agentweave__approve_tool_call (passed via --permission-prompt-tool) not found. Available MCP tools: none`, delivered as the `Write`'s error result. *(R1 read "no model call" here. R2 corrected it.)* | identical |
| **A_repro** | F299's reproduction flags: `manual` + approver, no `--mcp-config` | the same: a model call, a `Write` tool_use, the `not found` line, exit 1, no result line | identical |
| **B_1b** | A_hub with only `--permission-prompt-tool …` removed. **This is the shape 1b produces.** | exit 0, 2 turns, $0.0232, denied `['Write']`. The `Warning … blocked` line is still in the stream. Model: *"I need your permission to write the file. Please approve the request"* | exit 0, 2 turns, $0.0236, `['Write']`. *"You should see a permission dialog — please approve it"* |
| **B_q5** | the research's Q5: `manual` only, no `--mcp-config` | exit 0, `['Write']`, *"Please approve the permission prompt"* | exit 0, `['Write']` |
| **C_1b_none** | B_1b plus `--permission-prompts none` (shape (a)) | exit 0, 2 turns, `['Write']`, *"this session is non-interactive and doesn't have approval to write files"* | exit 0, **3 turns**, `['Write', 'PowerShell']`: **it retried**. *"non-interactive session without an approval surface"* |
| **C_q3** | the research's Q3: `manual` + `--permission-prompts none` | exit 0, `['Write']`, *"doesn't have an interactive approval surface"* | exit 0, `['Write']` |

What this settles:

1. **The research's failure rows reproduce through the Hub's own spawn**, P4 = A_repro and
   Q4b = A_hub: exit 1, no file, the two harness lines. **They are not startup failures.** Under the
   Hub's PTY the failure is at the first approval-needing call, after a model call (round 2). The
   research's pipe spawn was not re-checked.
2. **The inherited `CLAUDE*` environment is not the explanation** for F299's 2026-09-09 start.
   Both environments behave identically on every row. The most likely remaining cause is the
   harness build, and that is unmeasured.
3. **B_1b behaves as 1b's "condition C" said.** Same denial, and the model asks for approval rather
   than blaming the machine. **So the verdict's claim about the message holds on 2.1.269. Its
   picture of the state it replaces does not**: F299's run carried on after each refusal, and this
   build's run dies at the first one.
4. **Under the PTY, the `init` line is printed before the failure** in A_hub and A_repro. That is
   why `evidence/r1-harness-results.json` reads `"started": true` for them. The field means *init
   emitted*, and the script now calls it `init_emitted`. **R1 then wrote that a model call is the
   presence of `subtype`/`num_turns`. That is wrong.** Those fields are on the result line, which a
   process that dies mid-turn never writes. Every A row's transcript holds `assistant` lines and a
   `Write` tool_use (round 2, `evidence/r2-harness-results.json` §1). The
   `agentweave` entry is absent from `init.mcp_servers` whenever the policy applies, with or without
   the approver. Research candidate 3 builds on this. This change reads only that the line arrived
   (D3), not what it lists.
5. The denied `Write` was **inside** the run's workspace, so 1b's shape refuses in-workspace work.

## What round 2 changed (2026-09-13, `claude` 2.1.269, read at 10:25 and again at 10:38)

R2 re-ran R1's B_1b and A_hub (`plain`) through R1's script. Both outcomes reproduce: B_1b exit 0,
2 turns, `['Write']` denied, *"Please approve"*; A_hub exit 1 with both harness lines. It then made
five measurements of its own, all Haiku, all through `PtySession`. They are in
`evidence/r2-harness-results.json`, with the scripts `scripts/drive/t_d3_0913_f299_*.py`.

| # | measured | result | what it changed |
|---|---|---|---|
| 1 | R1's own A_hub/A_repro transcripts (10:08–10:09) and R2's A_hub rerun (10:25) | **every one has two `assistant` lines and a `Write` tool_use, and no result line** | A_hub's rows, the operator question's premise, D7 and D8. F299's configuration makes a model call and dies at its first approval-needing call, not at startup. |
| 2 | A_hub with a turn that needs no approval (*"Reply with just the word ok"*) | exit 0, `success`, 1 turn, `ok`; the `Warning … blocked` line is still there | The configuration works until an approval is needed. So an *untested* run in F299's configuration can complete, and still count as a test (D3). |
| 3 | early harness exits on a **permitted** harness, with the server as a stand-in that writes a marker when started | unknown option: exit 1, **no `init`, server never started**. `--resume` with an unseen session: exit 1, no `init`, server started 1.2 s before exit. Unknown model: exit 1, `init`, server `connected`. Invalid API key: 10 retries over 182 s, `init`, `connected`. | **D3 as R1 wrote it would count the first two as tests.** A typo in a runner's flags, on a machine where the approver works, would have taken away the next run's approver. D3 now also requires the `init` line. |
| 4 | the Hub's own read loop over a raw A_hub capture (`_flush_line`'s split, `strip_ansi_escapes`, `parse_claude_line`) | the `init` line arrives as JSON, second after the `Warning` text line. The Hub's escape regex is narrower than R1's script's, and it is enough here. | D3's new condition can fire in production, and not only in a test. |
| 5 | a stand-in `agentweave` server whose `approve_tool_call` refuses everything | the result line's `permission_denials` lists the approver's refusal, **under the same `tool_use_id` the approver was handed** | D6: dedupe is needed, and the join the codebase already uses for operator cards (`_operator_already_refused`, "the card is the join") does it exactly. |

Three more things R2 found by reading the code rather than the harness:

- **A shipped requirement R1 did not cite contradicts the new one on a blocking harness.** See
  D11.
- **The activity line does not show the path.** `EventRow` renders `summaryForEvent`
  (`EventRow.tsx:56`), and the `permission_denied` summary is `<agent> refused <tool_name>:
  <reason>` (`eventSummary.ts:114`). It never reads `detail`, so the path is visible only in the
  copied JSON. This is equally true of Codex's refusals today. D7, the spec scenario and the test
  guide now say what is on screen.
- **Nothing records the argv a run was spawned with.** `agent_trigger.py` neither logs nor stores
  `cmd`, so task 6.1's *"read from the run's recorded command or a debug log"* had no source. The
  live process's command line does, and 6.1 now reads that.

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

So the grounds stay exactly as they are, and the verdict's *"second run"* needs two more facts.
The Hub does not record whether it *gave* a run its server, and `resolve_access_path` depends on
`hub_client`, which can change between runs. Nor does it record whether the harness got as far as
its servers at all. An exit code does not say so (round 2, measurement 3). D3 records both.

### D3. What counts as a test of the harness

Two new nullable columns, both added by migration `0103` with no server default and no backfill.
That follows `0096`, `0101` and `0102`, and has the same guard for a missing `runs` table.

- **`Run.mcp_server_injected`** (Boolean) is written in the `Run(...)` construction
  (`agent_trigger.py:1190`) as `mcp_command is not None`. `mcp_command` is computed earlier in the
  same function (`:1084-1087`), from the access path resolved at `:1000`.
- **`Run.harness_init_at`** (timestamp) is written once, the first time the Claude read loop
  (`_flush_line`, `:2140`) parses a line whose `type` is `system` and whose `subtype` is `init`.
  `ParsedLine` gains a `harness_init: bool` for it. `parse_claude_line` today returns such a line
  with only its `session_id` (`runner_parsing.py:241`), and no other parser sets the flag, so the
  column is Claude-only by construction. `Run.session_id` cannot stand in for it, because the
  constructor seeds it from `resume_session_id` (`:1194`).

An earlier run **counts as a test** when all of the following hold:

- the same `project_id` and `agent`;
- `mcp_server_injected IS TRUE`. NULL means *not recorded*, from before `0103`. Counting it would
  move every upgraded agent into *refuted* on the strength of rows that never measured anything.
- `harness_init_at IS NOT NULL`, **so the harness got as far as its servers** (round 2). The
  harness writes `init` after it has dealt with its MCP servers: in A_hub the line lists the
  servers and leaves the blocked one out. And the adapter announces itself synchronously before it
  serves (`mcp_server.py:1825-1827`). So on a permitted harness, a server that `init` reports
  `connected` has already made its announce while the run's credential was live
  (`agent_auth.py:55` accepts only a `running` run). That leaves one way for a test on a permitted
  harness to show no report: a lost announce (D9). Measured cases this excludes: an unknown option
  in the runner's flags (no `init`, server never started), and `--resume` of an unseen session (no
  `init`, server started 1.2 s before exit, which races the announce). Both were on a harness where
  the approver works.
- `mcp_adapter_online_at IS NULL`;
- `exit_code IS NOT NULL`, so the harness process existed and exited. A spawn that raised
  (`agent_trigger.py:2050-2056`) and the unexpected-error handler (`:1907`) both set
  `status="failed"` and never set `exit_code`. Neither refutes anything. This condition is now
  mostly implied by the one above. It stays because it costs nothing, and because the error handler
  can fire after `init`.
- `status IN ('completed', 'failed')`. A *stopped* run may have been killed before the harness got
  to its servers, a *running* one has not finished, and an *interrupted* one is what crash recovery
  writes for a run the Hub lost track of (`run_reconciliation.py:65`). All three are excluded, so
  the conservative direction is today's behaviour.

**Codex is excluded by construction.** Its app-server path writes a synthetic `exit_code` of 0 or 1
(`agent_trigger.py:2897-2906`), which would otherwise have passed the exit-code condition. Its
parser never sets `harness_init`, so a Codex run is never a test. That matters only for an agent
re-bound from Codex to Claude, and the flag the test governs is Claude-only anyway.

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

### D6. Refusals the harness reports are recorded, once per tool call, for every Claude run

**Why this is in the change.** Today a Claude run's refusals reach the record through
`approve_tool_call` only (`agent_trigger.py:2759-2764`, `_on_refusal`'s docstring). A run in 1b's
shape starts on 2.1.269 and has its writes refused by the harness, and without this change nothing
records them. That is a new breach of the shipped *"A refusal is recorded wherever it is decided"*.
Its scenario *"A runtime refuses an action on its own"* is exactly this case, and the change would be
causing it.

**Round 1 keyed this on the argv, and round 2 replaced that with a join.** R1 recorded
`permission_denials` only when the spawned command named no approver, *"so a refusal `_decide` or
the operator already recorded is not recorded twice"*. The spec delta then said that an
approver-named run *"already has each refusal recorded where the approver decided it"*. That is
false in three measured or read cases:

- **F299's own first run on H-2026-09-09.** The approver was named, nothing answered it, and the
  harness refused every write. D7 says so itself: *"Refusals are **not** recorded."*
- **A lost report.** `_report_decision` swallows every failure (`mcp_server.py:1350-1369`), as
  *"A refused action is visible to the operator"* requires it to. The refusal happened, and nothing
  recorded it.
- **Any refusal the harness decides on its own while an approver is named.** These are in
  `permission_denials`, and the argv rule never reads them.

The join records all three, and still records each refusal once. Round 2 measured the fact it
rests on: **the harness lists the approver's own refusal in `permission_denials` under the same
`tool_use_id` it handed the approver** (measurement 5). Both existing writers of a Claude refusal
already store that id: the approver's report (`agent_actions.py:897-905`) and the operator's card
(`permissions.py:117`). The approver reports synchronously before it answers the harness
(`mcp_server.py:1470`), so its row exists before the harness writes the result line. The codebase
already dedupes this way for operator cards (`_operator_already_refused`, *"the card is the
join"*).

**Mechanism.** `ParsedLine` gains `refusals: List[dict]`. `parse_claude_line`'s `result` branch
(`runner_parsing.py:306`) fills it from `permission_denials`: each entry's `tool_name`,
`tool_use_id`, and a `detail`, which is `tool_input.file_path`, then `tool_input.command`, then
empty. `_flush_line` (`agent_trigger.py:2140`) reads the `tool_use_id`s this run has already
recorded as `permission_denied`: the `EventLog` rows for this project, agent and event type whose
`data.run_id` is this run. It records each remaining entry as a `permission_denied` event, in the
shape `_on_refusal` writes for Codex (`:2776-2788`), plus `tool_use_id`, with
`decided_by: "runtime"`. An entry with an empty `tool_use_id` cannot be joined, and is recorded. The
reason is a fixed sentence, because `permission_denials` carries none, capped as *"A refusal's
reason fits the record that carries it"* requires: *"Refused by Claude Code: no approver was
available to this run."* On an approver-named run that sentence would be false, so its reason is
*"Refused by Claude Code."* The choice reads whether the spawned `cmd` names the approver. That is
the only place the argv is still read, and it chooses words, not whether to record.

**Its limits, stated.**

- `permission_denials` arrives on the `result` line only. A run that dies before its result line
  records none of its harness's refusals. That includes F299's first run on H-2.1.269, which dies
  at its first approval-needing call. That is no worse than today, which records none at all.
- An approver report that timed out at the adapter but was committed by the Hub later could land
  after the result line, and be recorded twice. It is stated, not handled: the report's timeout is
  10 s (`mcp_server.py:184`), and a result line follows the last refused call by at least one more
  model response (B_1b: 2 turns).

### D7. What the operator sees (the F108 question)

| run | on H-2.1.269 (measured) | on H-2026-09-09 (F299's record) |
|---|---|---|
| **first** (*untested*, approver named, unchanged) | A turn needing no approval **completes**. A turn that reaches an approval-needing call gets `run_failed`, exit 1, and usage *unavailable*, because there is no result line (`usage_accounting.py:36-43`), although the model call was paid. The conversation shows, in order (round 2 replayed the Hub's own read loop): the `Warning … blocked by enterprise policy` line as text (`runner_parsing.py:234-238` turns a non-JSON line into a text event), the model's `Write` tool call, the `not found` error as text, and the same error as that call's failed result. No refusal is recorded: the approver never answered, and the process died before its result line. | completed, 5 turns. Refusals are **now** recorded from the result line, joined on `tool_use_id` (D6). Before this change they were not. The model blames the machine. |
| **second on** (*refuted*, new) | completed, about 2 turns, paid and recorded. The conversation shows the `Warning … blocked by enterprise policy` line and the model's *"please approve"*. **New:** an activity row per refused call, reading *"`<agent>` refused Write: Refused by Claude Code: no approver was available to this run."* The path is in the row's `detail`, which no activity line renders (`eventSummary.ts:114`). It is visible in the entry's copied JSON. | completed. The model says *"I need permission to write the file"*. **New:** the refusal rows. |
| **the turn-start notice** (unchanged) | The HTTP form, since there are no grounds. The request it tells the run to make is refused by the harness, and is now recorded. That is F301's ground (DIRECTION order item 3), not this change's. | same |

The activity summary's wording, *"`<agent>` refused Write"*, reads as if the agent did the refusing.
It is the shipped summary for every refusal, Codex's included, and this change does not touch
`hub/ui`.

**Nothing Hub-authored tells the operator why.** The only sentence naming the cause is the
harness's own stderr, and on *refuted* runs it arrives as a line of conversation text. Turning it
into a Hub notice naming `hub_client: "cli"` is research candidate 3, a new decision, and option
(b) of the operator question.

### D8. Why `agent-capability-plane` is not modified

*"A truer description does not silently widen permission"* forbids changing a run's containment
**as an undeclared consequence of attribution**. This change moves no containment. Measured on
2.1.269, the two shapes allow the same things. Both allow a turn that needs no approval, which
completes under A_hub too (round 2, measurement 2). Neither allows the `Write`: A_hub dies at it,
and B_1b refuses it and carries on. What differs is whether the turn survives the refusal, not what
it may do. *(R1 wrote "that A_hub's configuration would have refused, if it had started". A_hub
does start; see "What round 2 changed".)* Under H-2026-09-09, F299's condition A (flag named) and
condition C (no flag) each refused
every mutating call they attempted: A tried three tools and C tried one, which is the model retrying,
not a different answer. The flag
named an answerer that never answers, and removing it changes who is *named*, not what is
*allowed*. The trigger is also not the description. It is the Hub's own record of a completed
test (D3), and the requirement is stated in the new sandboxing requirement, so nothing about it is
undeclared.

R2 should attack this paragraph. If an H exists where an approver named but absent *allows*
something that `manual` without an approver refuses, D8 is wrong.

**R2 attacked it and found no such H on 2.1.269** (above). What R2 did find runs the other way. A
**false** refutation, on a harness where the approver works, takes away an answerer that would have
allowed in-workspace writes. That **narrows** a run, for one turn (D9). The capability-plane
requirement is about widening, so D8 stands. The narrowing is the default-posture requirement's
concern, and D11 covers it. R3 should check that D3's `init` condition leaves only the lost announce
able to cause it.

### D9. Risks, stated rather than fixed

- **A failed announce now costs one turn, not one description.** `mcp_server.py`'s
  `_announce_adapter_online` is best-effort and suppresses every error (`:1817-1822`). Before this
  change, a lost announce meant the next run read the HTTP form, which is the docstring's *"which
  works"*. After it, a lost announce on a permitted harness counts as a test (D3), so the next run
  gets no approver and its writes are refused. The server is still injected, so that run's own
  announce restores grounds, and the run after it is whole again. It corrects itself after one bad
  turn, and the operator is not told.
- **Grounds are permanent (research candidate 3).** An agent that ever had grounds keeps the
  approver after a policy arrives, and on 2.1.269 every later run dies at its first
  approval-needing call. This change
  inherits that unchanged. 1b says *"same signal"*, and a negative signal is a new decision. D-7 of
  today's window files it.
- **A test on a permitted harness that shows no report.** With D3's `init` condition, the only
  measured way to get one is D9's first bullet. R1's D3, without that condition, also admitted any
  harness exit before `init`, and round 2 measured two of those on a permitted harness (an unknown
  runner flag, and `--resume` of an unseen session).
- **The first run in F299's configuration is unchanged.** Every agent on a blocking machine still
  has one *untested* run. On H-2.1.269 it dies at its first approval-needing call. On
  H-2026-09-09 it misattributes, and its refusals are now at least recorded (D6).
- **The Hub still records no harness build**, so nothing in the product can tell which H it is on.

### D11. The default-posture requirement states the exception 1b decided (round 2)

*"The default posture lets an agent work inside its own workspace"* (`agent-run-sandboxing`, shipped)
says that the Hub **MUST NOT impose by default a posture whose decisions can only be resolved by an
operator prompt, unless a surface exists through which an operator can actually answer that
prompt**. Its scenario *"A newly created agent can edit files in its own workspace"* is
unconditional.

- On a harness that refuses the Hub's server, **today's code already breaches both.** Every run is
  default `manual` with an approver the harness will not start.
- Under this change, **the *refuted* run breaches them too, and now by requirement.** The ADDED
  requirement says it *"keeps the permission mode it would otherwise have had"* and *"is not moved
  to a mode that accepts requests without asking"*.
- Two requirements that demand opposite things of the same run are a spec that cannot be
  implemented. An implementer would satisfy whichever one their test checked.

**This is not an open question, because the verdict answered it.** 1b: *"It does **not** restore the
run's ability to work. On a harness that blocks MCP there may be no posture that gives both
containment and capability, and this verdict does not pretend otherwise."* And it rejected
`acceptEdits` on no grounds. So the change MODIFIES the default-posture requirement:

- one paragraph naming the exception, and naming the operator's way out, which is to state the
  access path;
- the *"newly created agent"* scenario, qualified to a harness that starts the Hub's server;
- one scenario for the exception.

The requirement's other text is kept word for word. The *untested* first run on a blocking harness
falls under the same exception. It breaches the clause today, and this change does not alter it.

**Related, cited rather than modified.** *"Introducing an enforced posture does not change existing
runs"* says the enforced posture's flags are emitted *"only where the mechanism answering them is
present"*. Today that clause is implemented as *"a server was configured"* (`runner_commands.py:250`).
The ADDED requirement narrows it to *"and has not been seen absent"*. That is a stricter reading of
the same clause, so it needs no delta.

### D10. Not in scope, and where it went

- **Research candidate 2**: `acceptEdits` is path-confined by the harness on 2.1.269. It
  contradicts the reason 1b's rejected alternative was rejected (`DECISIONS.md:772-773`). This
  change neither relies on it nor reintroduces the alternative. It goes to the operator as a finding
  (today's queue item D-7), not as a reversal written here.
- **`--permission-prompts none`**: operator question, option (a). It is an *unknown option* before
  2.1.259 (research candidate 1), and the Hub cannot tell which build it spawns.
