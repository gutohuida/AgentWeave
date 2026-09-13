# Tasks — an absent approver is not named

Implementation belongs to a night window. No task here is complete because this plan exists. Only
verified implementation closes one.

**Do not start until the operator question at the top of `proposal.md` is answered.** If the
answer is (a) or (b), this task list is wrong as written and goes back through the rounds.

**Python only.** No `hub/ui` change, so `hub/hub/static/ui` is **not** rebuilt. The CI lint set is
required (§7).

**Tests use the ordering and grain the real path writes** (CLAUDE.md, F190). A test of D3's read
seeds `Run` rows the way `trigger_agent_directly` and `_execute_run` write them: `exit_code` and
`status` set at finalize, `mcp_adapter_online_at` set by `POST /agent-actions/mcp-adapter-online`,
and `mcp_server_injected` set at construction. A fixture that sets `mcp_adapter_online_at` on a row
whose `mcp_server_injected` is NULL, or that sets `exit_code` on a spawn-failure row, is not a state
the path produces, and it is not evidence.

## 1. Record what the Hub gave the run

- [ ] 1.1 `hub/hub/db/models.py`: add `Run.mcp_server_injected: Mapped[Optional[bool]]`, nullable,
  no default. Its comment says NULL means *not recorded*, and why nothing reads NULL as either
  answer (`design.md` D3).
- [ ] 1.2 Migration `hub/hub/migrations/versions/0103_mcp_server_injected.py`, revising `0102`. It
  adds the column with no server default and no backfill, guarded for a missing `runs` table the
  way `0102` is.
- [ ] 1.3 `hub/tests/test_migrations.py`: bump `HEAD_REVISION` to `"0103"`. Add three tests, as for
  `0102`: the column exists after upgrade; existing rows read NULL (no backfill); and the upgrade
  is guarded when `runs` does not exist. Check `hub/tests/test_project_persistence.py` for a
  literal head assertion. At `00ba182` it has none, because it upgrades to `"head"`.
- [ ] 1.4 `hub/hub/api/v1/agent_trigger.py`, in the `Run(...)` construction (`:1190`): set
  `mcp_server_injected=mcp_command is not None`. Test through `trigger_agent_directly`, not by
  constructing a `Run`: a `claude` agent with `hub_client` unset gets `True`, and one with
  `hub_client: "cli"` gets `False`.

## 2. The third state

- [ ] 2.1 `hub/hub/launchability.py`: add `async def harness_refused_mcp(db, project_id, agent) ->
  bool`, one `EXISTS` query over D3's five conditions. Its docstring states what it is not: it is not
  a harness signal, it does not outrank grounds, and it is per agent like `harness_has_honoured_mcp`.
- [ ] 2.2 Tests in `hub/tests/` for 2.1, one row each, seeded as the path writes them:
  - no rows → `False`;
  - one injected, finalized, unreported row, `completed` → `True`;
  - the same with `failed` and `exit_code=1` → `True` (H-2.1.269's first run);
  - `stopped` → `False`;
  - `running` → `False`;
  - a spawn failure (`status="failed"`, `exit_code` NULL) → `False`;
  - `mcp_server_injected` NULL → `False`;
  - `mcp_server_injected` False → `False`;
  - another agent's refuting row → `False`;
  - another project's refuting row → `False`.
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
  - (ii) after that run finalizes `failed`, `exit_code=1`, never reported (H-2.1.269), the second
    run does not;
  - (iii) after an adapter report on any run, the approver is named again.

  Drive the report through `POST /api/v1/agent-actions/mcp-adapter-online` with that run's
  credential, not by setting the column.

## 4. Record the harness's refusals on an approver-less Claude run

- [ ] 4.1 `hub/hub/runner_parsing.py`: `ParsedLine.refusals: List[Dict[str, str]]`.
  `parse_claude_line`'s `result` branch fills it from `permission_denials` with `tool_name`, and a
  `detail` of `tool_input.file_path`, then `tool_input.command`, then empty. A malformed entry is
  skipped. Test it with the `result` line R1 captured **verbatim** from a 1b-shaped spawn on
  2.1.269, which is `evidence/b1b-plain-result-line.json` in this change. Copy it into
  `hub/tests/` as a fixture. Do not hand-write one.
- [ ] 4.2 `agent_trigger.py` `_flush_line` (`:2140`): when `parsed.refusals` is non-empty and the
  spawned `cmd` has no `--permission-prompt-tool`, persist one `permission_denied` event per entry
  and broadcast it, in the shape `_on_refusal` uses (`:2776-2793`), with `decided_by: "runtime"`
  and D6's fixed reason.
- [ ] 4.3 Tests for 4.2 through `_execute_run`, with a stub session replaying a recorded stream:
  - (a) no approver in `cmd` → one row per denial, naming `Write` and the path;
  - (b) approver in `cmd` → no row from the result line;
  - (c) a result with `permission_denials: []` → no row.
  - Mutation-check (b): remove the `cmd` guard, and confirm it goes red.

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
  - Expect run 1 `failed` with the two harness lines, on H-2.1.269.
  - Send a second turn. Expect its `cmd` (read from the run's recorded command or a debug log,
    **not** inferred) without `--permission-prompt-tool`, completed, and a `permission_denied` row
    naming `Write`.
  - Screenshot the conversation and the activity.
- [ ] 6.2 **Permitted harness, a fresh agent.** Its first run has the approver and writes a file in
  its workspace. That is the D2 regression, driven, not only tested. Its adapter reports in, and its
  second run also has the approver.
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
