# Tasks — an absent approver is not named

Implementation belongs to a night window. No task here is complete because this plan exists. Only
verified implementation closes one.

**Do not start until the operator question at the top of `proposal.md` is answered.** If the
answer is (a) or (b), this task list is wrong as written and goes back through the rounds.

**Python only.** No `hub/ui` change, so `hub/hub/static/ui` is **not** rebuilt. The CI lint set is
required (§7).

**Tests use the ordering and grain the real path writes** (CLAUDE.md, F190). A test of D3's read
seeds `Run` rows the way `trigger_agent_directly` and `_execute_run` write them:

- `mcp_server_injected` is set at construction;
- `harness_mcp_status` is set by the read loop, from an `init` line;
- `mcp_adapter_online_at` is set by `POST /agent-actions/mcp-adapter-online`, which comes *before*
  that `init` line on a permitted harness (`design.md` D3);
- `exit_code` and `status` are set at finalize.

Some fixtures describe states the path never produces, and they are not evidence. Four examples: a
row with `mcp_adapter_online_at` set and `mcp_server_injected` NULL; a spawn-failure row carrying
`exit_code`; a Codex row carrying `harness_mcp_status`; and a row with `mcp_adapter_online_at` set
and `harness_mcp_status` `absent`. A server that announced was started, and a started server is not
left out of `init`.

## 1. Record what the Hub gave the run, and whether its harness started

- [ ] 1.1 `hub/hub/db/models.py`: add two nullable columns, with no defaults, beside
  `mcp_adapter_online_at`:
  - `Run.mcp_server_injected: Mapped[Optional[bool]]`;
  - `Run.harness_mcp_status: Mapped[Optional[str]]` (`String(32)`). This is what the harness's
    `init` line said of the Hub's server: its `status` verbatim, or `"absent"`.

  Each comment says NULL means *not recorded*, and why nothing reads NULL as either answer
  (`design.md` D3).
- [ ] 1.2 Migration `hub/hub/migrations/versions/0103_harness_test_record.py`, revising `0102`. It
  adds both columns with no server default and no backfill, guarded for a missing `runs` table the
  way `0102` is.
- [ ] 1.3 `hub/tests/test_migrations.py`: bump `HEAD_REVISION` to `"0103"`. Add three tests, as for
  `0102`: both columns exist after upgrade; existing rows read NULL in both (no backfill); and the
  upgrade is guarded when `runs` does not exist. `hub/tests/test_project_persistence.py` upgrades to
  `"head"` and has no literal to bump (checked at `54c47b3`).
- [ ] 1.4 `hub/hub/api/v1/agent_trigger.py`, in the `Run(...)` construction (`:1190`): set
  `mcp_server_injected=mcp_command is not None`. Test through `trigger_agent_directly`, not by
  constructing a `Run`: a `claude` agent with `hub_client` unset gets `True`, and one with
  `hub_client: "cli"` gets `False`.
- [ ] 1.5 `hub/hub/runner_commands.py`: one constant for the server's name (`"agentweave"`), used
  by `_build_claude_command`'s `--mcp-config`. `hub/hub/runner_parsing.py` imports it; neither
  module imports the other today. `ParsedLine.harness_mcp_status: Optional[str] = None`, set by
  `parse_claude_line` for a line whose `type` is `system`, whose `subtype` is `init`, and which
  carries an `mcp_servers` list. The value is the Hub server's entry's `status` verbatim, or
  `"absent"` when the list has no such entry. An `init` line without the list leaves it `None`.
  Nothing else about that line's handling changes: it still yields no event, and still carries its
  `session_id`. `agent_trigger.py` `_flush_line` (`:2140`) sets `Run.harness_mcp_status` the first
  time `parsed.harness_mcp_status` is not `None`, and never overwrites it.

  Test the parser with three captured `init` lines, one per value:
  - `absent`: from `evidence/a-hub-plain-raw-pty.txt`. That is R2's raw PTY capture of A_hub on
    2.1.269, escape sequences included, and it can be re-captured with
    `scripts/drive/t_d3_0913_f299_init_line.py`.
  - `connected` and `failed`: R3's S_0 and S_45 lines, verbatim JSON, in
    `evidence/r3-harness-results.json` §5.

  Copy them into `hub/tests/` as fixtures. Do not hand-write one. The raw capture's line endings may
  carry an extra `\r` from a Windows text-mode write, which `_flush_line`'s `rstrip("\r")`
  tolerates. The escapes are what matter.

  Test `_flush_line` through `_execute_run`, with a stub session replaying the raw capture
  **unstripped**. A test fed pre-stripped JSON cannot fail on the thing that could break this in
  production, which is `strip_ansi_escapes`.

## 2. The third state

- [ ] 2.1 `hub/hub/launchability.py`: add `async def harness_refused_mcp(db, project_id, agent) ->
  bool`, one `EXISTS` query over D3's six conditions. Its docstring states what it is not: it
  reads the `init` line's report only to decide what counts as a test, never to take grounds away
  (research candidate 3); it does not outrank grounds; and it is per agent like
  `harness_has_honoured_mcp`.
- [ ] 2.2 Tests in `hub/tests/` for 2.1, one row each, seeded as the path writes them:
  - no rows → `False`;
  - one injected, `harness_mcp_status="absent"`, finalized, unreported row, `completed` → `True`
    (a turn needing no approval, round 2 measurement 2);
  - the same with `failed` and `exit_code=1` → `True` (H-2.1.269's first run, dead at its first
    write);
  - `harness_mcp_status="failed"`, `completed`, `exit_code=0` → `True` (round 3's S_45 and S_crash);
  - **`harness_mcp_status="connected"`, `completed`, `exit_code=0`, unreported → `False`** (a lost
    announce; this is the row R2's D3 got wrong);
  - **injected, `failed`, `exit_code=1`, `harness_mcp_status` NULL → `False`** (an unknown runner
    flag, round 2 measurement 3; this is the row R1's D3 got wrong);
  - `stopped` → `False`;
  - `interrupted` → `False` (crash recovery, `run_reconciliation.py:65`);
  - `running` → `False`;
  - a spawn failure (`status="failed"`, `exit_code` NULL, `harness_mcp_status` NULL) → `False`;
  - `mcp_server_injected` NULL → `False`;
  - `mcp_server_injected` False → `False`;
  - another agent's refuting row → `False`;
  - another project's refuting row → `False`.
  - Mutation-check both bold rows. Drop the `IS NOT NULL` half of the status condition and confirm
    the NULL row goes red. Drop the `<> 'connected'` half and confirm the `connected` row goes red.
- [ ] 2.3 `agent_trigger.py:1000-1005`: compute `approver_available`. It is `True` when
  `access_path != "mcp"` (no server, so the flag is never emitted anyway), when `hub_client ==
  "mcp"`, or when `harness_has_honoured_mcp` is true. Otherwise it is `not await
  harness_refused_mcp(...)`. Pass it to `build_command`.

## 3. The command

- [ ] 3.1 `hub/hub/runner_commands.py`: `build_command` and `_build_claude_command` take
  `approver_available: bool = True`. When it is `False`, `--permission-prompt-tool` is not emitted,
  for both the `defaults_to_approver` branch and the operator's `APPROVER_PERMISSION_MODES` branch.
  Nothing else in the argv changes. Update the comment at `:244-249` so it says the flag is now also
  withheld on evidence, and cite D4. The Codex branch accepts the keyword and ignores it.
- [ ] 3.2 Tests in `hub/tests/test_runner_commands.py` (or its existing home for the approver flag;
  grep `CLAUDE_PERMISSION_PROMPT_TOOL`). With `mcp_command` set and `approver_available=False`:
  - (a) the default posture carries `--permission-mode manual`, `--mcp-config` and
    `--allowedTools mcp__agentweave__*`, and no `--permission-prompt-tool`;
  - (b) an operator `permission_mode` of `workspace` and one of `manual` each carry their mode and
    no approver;
  - (c) `acceptEdits`, `bypassPermissions` and yolo are byte-identical to `approver_available=True`;
  - (d) **no argv contains `acceptEdits` that did not contain it with `True`**. That is D4's *"no
    other posture is substituted"* and the spec's *"Nothing is widened"*.
  - Mutation-check (a) and (d): flip the guard, and confirm each goes red.
- [ ] 3.3 The first-run guard, end to end through `trigger_agent_directly` with the spawn stubbed at
  `PtySession.spawn`, capturing `cmd`. This is the test that fails if D2 is got wrong:
  - (i) a fresh `claude` agent's first run names the approver;
  - (ii) after that run's stub session replays the raw A_hub capture (`init` included) and
    finalizes `failed`, `exit_code=1`, never reported (H-2.1.269), the second run does not;
  - (ii-b) after a first run whose stub session emits only `error: unknown option '…'` and exits
    1, the second run **does** name the approver (round 2);
  - (ii-c) after a first run whose stub session replays R3's S_0 `init` line (`connected`) and a
    `success` result, exits 0, and whose adapter never reports, the second run **does** name the
    approver (round 3, a lost announce);
  - (iii) after an adapter report on any run, the approver is named again.

  Drive the report through `POST /api/v1/agent-actions/mcp-adapter-online` with that run's
  credential while the run is still `running` (`agent_auth.py:55` refuses a finished run), not by
  setting the column.

## 4. Record the harness's refusals, once per tool call

- [ ] 4.1 `hub/hub/runner_parsing.py`: `ParsedLine.refusals: List[Dict[str, str]]`.
  `parse_claude_line`'s `result` branch fills it from `permission_denials` with `tool_name`,
  `tool_use_id`, and a `detail` of `tool_input.file_path`, then `tool_input.command`, then empty. A
  malformed entry is skipped. Test it with the `result` line R1 captured **verbatim** from a
  1b-shaped spawn on 2.1.269, which is `evidence/b1b-plain-result-line.json` in this change. Copy it
  into `hub/tests/` as a fixture. Do not hand-write one.
- [ ] 4.2 `agent_trigger.py` `_flush_line` (`:2140`): when `parsed.refusals` is non-empty, read the
  `tool_use_id`s this run has already recorded. Those are the `EventLog` rows with this
  `project_id`, `agent` and `event_type="permission_denied"` whose `data["run_id"]` is this run
  (`EventLog.data["run_id"].as_string()`; there is no `run_id` column). Persist one
  `permission_denied` event per remaining entry, and broadcast it. Use the shape `_on_refusal`
  uses (`:2776-2793`) plus `tool_use_id`, with `decided_by: "runtime"`. The reason is D6's
  approver-less sentence when the spawned `cmd` has no `--permission-prompt-tool`, and
  *"Refused by Claude Code."* when it has one. An entry with an empty `tool_use_id` is recorded.
- [ ] 4.3 Tests for 4.2 through `_execute_run`, with a stub session replaying a recorded stream:
  - (a) no approver in `cmd` → one row per denial, naming `Write`, the path in `detail`, and D6's
    approver-less reason;
  - (b) approver in `cmd`, **and the approver's refusal already recorded** through
    `POST /api/v1/agent-actions/permission-decisions` with the run's credential and the same
    `tool_use_id`, before the result line is replayed (the order `mcp_server.py:1470` produces) →
    exactly one row for that tool call;
  - (c) approver in `cmd`, nothing recorded for that `tool_use_id` (the approver never answered, or
    its report was lost) → one row, with the reason *"Refused by Claude Code."*;
  - (d) an operator's refusal recorded through
    `POST /api/v1/projects/{project_id}/permission-requests/{request_id}/decide` for the same
    `tool_use_id` → no second row;
  - (e) a result with `permission_denials: []` → no row.
  - Mutation-check (b): remove the join, and confirm it goes red. Mutation-check (c): restore R1's
    argv guard (skip every approver-named run), and confirm it goes red.

## 5. The operator page

- [ ] 5.1 `docs/reference/permission-postures.md`: after the paragraph on the no-server fallback
  (`:36-39`), add the new case. A *Workspace only* or *Ask me* run of an agent whose harness has
  been seen not to start the Hub's server gets no approver. Its approval-needing calls, including
  writes inside its workspace, are refused by Claude Code, and each refusal is recorded. Setting
  `hub_client: "cli"` is the operator's move if they want the run to work, and it chooses **Edit
  files**. **Do not** edit the `acceptEdits` row's *"Not checked"* here. That is research
  candidate 2, which goes to the operator (today's D-7). This page must not restate it in new
  words either.

## 6. Drive (agent-verifiable)

Against a drive Hub from source on its own port and profile, never 8000 or 8010's database. Use
Haiku, and one `claude` agent with `hub_client` unset. Record `claude --version` beside every
result.

- [ ] 6.1 **Blocking harness.** Add `{"deniedMcpServers":[{"serverName":"agentweave"}]}` to the
  agent's runner flags as `--settings …`. That is the R1 method. A managed-settings file would need
  an administrator path on this machine, so say so if it is used instead. Send a turn:
  - Expect run 1, on H-2.1.269, to make a model call, attempt `Write`, and end `failed` with the
    two harness lines, usage *unavailable*, and `harness_mcp_status` = `absent`.
  - Send a second turn. Read its argv from the **live process**, while the run is in flight:
    `Get-CimInstance Win32_Process -Filter "Name='claude.exe'" | Select-Object CommandLine`. The
    Hub neither logs nor stores `cmd`, so there is no other source, and inferring it from behaviour
    is not reading it. Expect no `--permission-prompt-tool`, the `--mcp-config` still present, the
    run completed, and one `permission_denied` row naming `Write`, with the path in its `detail`.
  - Screenshot the conversation and the activity. Record what the activity line shows, and say
    that it does not show the path (`design.md` D7), rather than implying it does.
- [ ] 6.2 **Permitted harness, a fresh agent.** Its first run has the approver and writes a file in
  its workspace. That is the D2 regression, driven, not only tested. Its `harness_mcp_status` is
  `connected`, its adapter reports in, and its second run also has the approver.
- [ ] 6.2b **A typo is not a refutation.** A fresh agent on a permitted harness, with
  `--no-such-flag` in its runner's flags. Run 1 fails with `error: unknown option`, and its
  `harness_mcp_status` is NULL. Remove the flag. Run 2's live argv **names** the approver, and its write
  succeeds.
- [ ] 6.3 **Lifting the policy.** Remove the `--settings` flag from 6.1's agent. The next run
  (*refuted*, so no approver) still has the server injected, the adapter reports in, and the run
  after it has the approver again.

## 7. Close

- [ ] 7.1 `ruff check src/ hub/ tests/`; `black --check --target-version py311 src/ hub/hub/
  hub/tests/ tests/`; `mypy src/`.
- [ ] 7.2 `py -3.11 -m pytest hub/tests/ -q`, whole suite, **with `claude` stripped from `PATH`**
  as well as with it present (memory: local suite green because claude is on PATH).
- [ ] 7.3 Set F299's **Status:** line in `scripts/drive/FINDINGS.md` to the fixing commit, and
  state which H the drive ran on.

## Human-only verification

These need a person, because they are judgements about what an operator understands.

- [ ] H.1 Read 6.1's second-run conversation and activity side by side. Does the operator learn that
  the run could not write, and that it is not their machine's fault? The Hub adds no sentence of its
  own (`design.md` D7), so the answer may be *"only from the refusal rows"*. If it is, record that
  as a finding, not a failure of this change.
- [ ] H.2 Read the new paragraph in `docs/reference/permission-postures.md`. Could an operator whose
  runs are all refused find `hub_client: "cli"` from it, and know what that trades?

See `test-guide.md` for the walk-through.
