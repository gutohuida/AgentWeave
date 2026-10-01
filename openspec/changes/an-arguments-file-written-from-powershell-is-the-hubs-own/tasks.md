## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: re-derive the proposal independently against `hub/hub/mcp_server.py` (`_hub_own_call`,
  `_hub_own_command`, `_plain_calls_path`, `_inside_hub_calls_root`, rule 6 of `_judge_word`) and
  `hub/hub/copilot_acp.py:515-540`. Re-run the proposal's table, and do not trust R1's numbers. Confirm or refute
  that F478 is rule 6 and not rule 1. Re-read `the-shell-judge-reads-a-word-whole` D2 and say again whether the
  two changes are independent. Check slice 3's drive logs for a bash write of an arguments file (Open
  question 1).
  - **Done 2026-10-02** (night iteration 5): see design.md's round log, R2. Table confirmed; rule 6 confirmed;
    9.10's exact bytes fit D2; independence re-derived; no bash write in any drive. Three corrections made.
- [ ] 0.2 R3: a second independent re-derivation, measuring D2's grammar traps on PowerShell 5.1 again (smart
  quotes, here-strings, `-Value` arrays, parameter prefixes, `--%`). `openspec validate
  an-arguments-file-written-from-powershell-is-the-hubs-own --strict` passes.
- [ ] 0.3 The adversarial Opus review, recorded under `spec-queue/tracks/reviews/`.
- [ ] 0.4 The operator approves the change in `spec-queue/APPROVALS.md`, and answers Open questions 1 and 2.
- [ ] 0.5 Before any code: tell the operator that `mcp_server.py` reaches `:8000`'s agents on their next run
  (`.claude/rules/mcp-server.md`).

## 1. Tests first — in `hub/tests/test_hub_own_call.py`; each must fail on today's code unless marked as a control

- [ ] 1.1 `test_a_powershell_args_file_write_has_standing_in_every_posture`, parametrised over the 9.10 form
  (`-Path '.agentweave/calls/r.json' -Value '{"path":"spec/x.html"}' -Encoding utf8`), the same with
  `-LiteralPath`, a bare path, a backslash path (`'.agentweave\calls\r.json'`), the parameters in each of the six
  orders, and mixed case (`set-content -PATH … -encoding UTF8`). Assert `_hub_own_call` is the own reason, that
  `_decide` allows it, and that under the operator posture `approve_tool_call` allows it and `asked` is empty.
  Record that the `_decide` assertion FAILS today for the 9.10 form (`'/x.html' is outside your workspace`).
- [ ] 1.2 `test_the_literal_is_not_read`: values holding `../x`, `/etc/x`, `C:\x`, `https://example.com/x`,
  `a; rm x`, `$(Write-Output x)`, `$env:X`, a backtick, `it''s`, a newline, and `{"a":"b/c"}`. Each has standing.
- [ ] 1.3 `test_a_typographic_quote_is_not_one_literal`: for each of U+2018, U+2019, U+201A and U+201B,
  `-Value 'a<q>; Remove-Item x; <q>'` has no standing, and `_decide`'s answer equals today's answer for the same
  text. Also a NUL in the value.
- [ ] 1.4 `test_a_near_miss_of_the_write_falls_through`, parametrised: `-Val`, `-Enc`, `-Pa`; a positional value;
  `-Force`; `-NoNewline`; `-Stream x`; `-Value "…"`; `-Value 'a','b'`; `-Value @'…'@`; `-Value $x`;
  `-Value ('a')`; `-Encoding utf8NoBOM`; `-Encoding Unicode`; a parameter given twice; `; aw-tool …` chained;
  a leading `&`; a path outside the calls root, with `..`, absolute, with `*`, not `.json`, or beginning with `-`;
  `Add-Content` and `Out-File`. Under the operator posture, each is asked (`asked` has one entry), and `_decide`'s
  answer equals the answer with `_hub_own_powershell_write` patched to return False.
- [ ] 1.5 `test_the_write_has_standing_only_in_powershell`: the 9.10 text as a `Bash` request, and as a `Shell`
  request, falls through.
- [ ] 1.6 `test_a_junctioned_calls_directory_gives_the_write_no_standing`: reuse the existing junction fixture
  (`test_a_junctioned_calls_directory_gives_no_standing`). The 9.10 form falls through.
- [ ] 1.7 Controls (PASS today, must keep passing): the whole existing file; `hub/tests/test_permission_approver.py`;
  `hub/tests/test_copilot_acp_run_turn.py`; `hub/tests/test_copilot_acp_decide.py`.
- [ ] 1.8 A Copilot-path test in `hub/tests/test_copilot_acp_decide.py`, beside slice 3's call-command tests (`:1140`,
  `:1146`, `:1201`): an `execute` request of the 9.10 form on a **spec turn** is answered ALLOW with "the Hub's own
  tools" before the judge, in each posture. (R2) Its `calls` map holds `CallFacts(tool_name="powershell", …)` for
  the call id, as the captured start event reports and as `:1140` does. Controls: the same request with no facts,
  and with `tool_name="write_powershell"`, is keyed `Shell` and falls through to the judge.

## 2. The fix

- [ ] 2.1 `_hub_own_powershell_write(command, workspace) -> bool` in `hub/hub/mcp_server.py`, beside
  `_hub_own_command`, implementing design D2 over the raw text. Reuse `_plain_calls_path` for the path, and
  `_PLAIN_COMMAND_CHARS_POWERSHELL` for the path's characters. Stdlib only (`.claude/rules/mcp-server.md`).
- [ ] 2.2 Call it from `_hub_own_call`'s shell branch when the tool's dialect is `powershell`, after
  `_hub_own_command`. Update `_hub_own_call`'s docstring ("exactly three cases" becomes four) and the module note
  above `_HUB_OWN_REASON`.
- [ ] 2.3 Update slice 3's design D8 text? **No**: slice 3 is a separate change. Instead, add one line to this
  design's round log naming the D8 sentence this change amends.
- [ ] 2.4 `py -3.11 -m pytest hub/tests/test_hub_own_call.py hub/tests/test_permission_approver.py
  hub/tests/test_copilot_acp_run_turn.py -q`; `ruff check`; `black --check --target-version py311`. Then the full
  `hub/tests/` suite, backgrounded per the night window's rule, with its tail read before the change is closed.

## 3. Drive

- [ ] 3.1 Measure the predicate against real PowerShell 5.1: for every row of 1.1 and 1.2, run the command in a
  scratch workspace and confirm that the file holds exactly the literal's content and that the shim
  (`aw-tool --list` is not enough: `aw-tool read_spec_document <file>` against a drive Hub) decodes it.
- [ ] 3.2 Re-drive slice 3's task 9.10 on a fresh drive profile and port (never `:8000`; Haiku is not a Copilot
  model, so use the drive's Copilot model as 9.10 did). Record Copilot's exact `rawInput.command` for the
  arguments-file write. If it matches the grammar, the write is allowed with "the Hub's own tools" and the
  submission is recorded. If it does not, record the form and stop: that is a new finding, not a grammar
  widening made in the drive.
- [ ] 3.3 Append the outcome to `scripts/drive/FINDINGS.md`. F478's status line names this change's commit for
  the arguments-file half, and `the-shell-judge-reads-a-word-whole` for the general half (`echo 'a:b/c'`), which
  stays open until that change archives.

## 4. Archive

- [ ] 4.1 **Gate:** `a-run-reaches-the-hub-without-mcp` is archived, so `openspec/specs/agent-run-sandboxing/spec.md`
  holds "The Hub's own call command is decided like the Hub's own tools". If not, stop here and log it.
- [ ] 4.2 `openspec validate an-arguments-file-written-from-powershell-is-the-hubs-own --strict`, then the
  `openspec-archive-change` skill. Commit and push, staging paths explicitly.
