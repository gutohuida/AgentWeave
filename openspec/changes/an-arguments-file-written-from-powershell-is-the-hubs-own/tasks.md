## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: re-derive the proposal independently against `hub/hub/mcp_server.py` (`_hub_own_call`,
  `_hub_own_command`, `_plain_calls_path`, `_inside_hub_calls_root`, rule 6 of `_judge_word`) and
  `hub/hub/copilot_acp.py:515-540`. Re-run the proposal's table, and do not trust R1's numbers. Confirm or refute
  that F478 is rule 6 and not rule 1. Re-read `the-shell-judge-reads-a-word-whole` D2 and say again whether the
  two changes are independent. Check slice 3's drive logs for a bash write of an arguments file (Open
  question 1).
  - **Done 2026-10-02** (night iteration 5): see design.md's round log, R2. Table confirmed; rule 6 confirmed;
    9.10's exact bytes fit D2; independence re-derived; no bash write in any drive. Three corrections made.
- [x] 0.2 R3: a second independent re-derivation, measuring D2's grammar traps on PowerShell 5.1 again (smart
  quotes, here-strings, `-Value` arrays, parameter prefixes, `--%`). `openspec validate
  an-arguments-file-written-from-powershell-is-the-hubs-own --strict` passes.
  - **Done 2026-10-02** (night iteration 6): see design.md's round log, R3. A BMP-wide tokenizer sweep found the
    closer set complete. Every trap was run. One safety rule was made explicit (nothing joined to the literal),
    the NUL rule's reason was corrected, and 1.3's example was replaced by one that parses.
- [x] 0.3 The adversarial Opus review, recorded under `spec-queue/tracks/reviews/`.
  - **Done 2026-10-02** (night iteration 7): `spec-queue/tracks/reviews/F478-2026-10-02.md`, APPROVE WITH FIXES.
    All nine findings were applied (see design.md's round log), including the blocking one: "nothing joined"
    now covers every part, and the path's character set is labelled a safety rule. The notice now spells the
    form out (D5, task 2.4). The hard-link residual is filed as F480.
- [x] 0.4 The operator approves the change in `spec-queue/APPROVALS.md`, and answers Open questions 1 and 2.
  - **Done 2026-10-02 (operator, interactive):** APPROVED; Open question 1 left out, Open question 2 accepted.
- [x] 0.5 Before any code: tell the operator that `mcp_server.py` reaches `:8000`'s agents on their next run
  (`.claude/rules/mcp-server.md`).
  - **Done 2026-10-02:** said before the approval and again before the code.

## 1. Tests first — in `hub/tests/test_hub_own_call.py`; each must fail on today's code unless marked as a control

- [x] 1.1 `test_a_powershell_args_file_write_has_standing_in_every_posture`, parametrised over the 9.10 form
  (`-Path '.agentweave/calls/r.json' -Value '{"path":"spec/x.html"}' -Encoding utf8`), the same with
  `-LiteralPath`, a bare path, a backslash path (`'.agentweave\calls\r.json'`), the parameters in each of the six
  orders, and mixed case (`set-content -PATH … -encoding UTF8`). Assert `_hub_own_call` is the own reason, that
  `_decide` allows it, and that under the operator posture `approve_tool_call` allows it and `asked` is empty.
  Record that the `_decide` assertion FAILS today for the 9.10 form (`'/x.html' is outside your workspace`).
  - **Done 2026-10-02:** `test_a_powershell_args_file_write_has_standing_in_every_posture` (13 forms). Measured failing on the pre-change source (each form refused or carded); `test_the_9_10_form_is_refused_by_the_judge_alone` keeps the judge's `/x.html` refusal asserted.
- [x] 1.2 `test_the_literal_is_not_read`: values holding `../x`, `/etc/x`, `C:\x`, `https://example.com/x`,
  `a; rm x`, `$(Write-Output x)`, `$env:X`, a backtick, `it''s`, a newline, and `{"a":"b/c"}`. Each has standing.
  (Review) Also a value holding parameter-like text, `-Value ' -Path x -Encoding utf8 '`, which keeps standing:
  together with 1.4's last row, it catches a parser that splits on spaces.
  - **Done 2026-10-02:** `test_the_literal_is_not_read` (13 values, including the parameter-like and empty ones).
- [x] 1.3 `test_a_typographic_quote_is_not_one_literal`: for each of U+2018, U+2019, U+201A and U+201B,
  `-Value 'a<q>; Set-Content pwned.txt x; Write-Output <q>' -Encoding utf8` has no standing, and `_decide`'s
  answer equals today's answer for the same text. (R3: this is the form that ran its second command on 5.1. The
  earlier `'a<q>; Remove-Item x; <q>' -Encoding utf8` does not parse there.) Also a NUL in the value, and
  (review) an ESC (U+001B) and a DEL (U+007F). Controls: U+201C, U+201D and U+201E in the value keep standing,
  because they do not end a single-quoted literal; and a pretty-printed multi-line JSON value (LF, CRLF and a
  tab) keeps standing.
  - **Done 2026-10-02:** `test_a_typographic_quote_is_not_one_literal`, `test_a_control_character_in_the_literal_is_not_one_literal`, `test_content_a_literal_may_hold`. Mutation (exclusion removed): the 4 quote rows fail.
- [x] 1.4 `test_a_near_miss_of_the_write_falls_through`, parametrised: `-Val`, `-Enc`, `-Pa`; a positional value;
  `-Force`; `-NoNewline`; `-Stream x`; `-Value "…"`; `-Value 'a','b'`; `-Value @'…'@`; `-Value $x`;
  `-Value ('a')`; (R3) `-Value 'a'(Write-Output x)`, `-Value 'a'b` and `-Value 'a'$x` (text joined to the
  literal); `-Value 'a' ,'b'`; `-Value:'a'`; `-PSPath`; a `--%`; a parameter dash U+2013, U+2014 or U+2015; a
  tab or U+00A0 between the parts; `-Encoding utf8NoBOM`; `-Encoding Unicode`; a parameter given twice; `; aw-tool …` chained;
  a leading `&`; a path outside the calls root, with `..`, absolute, with `*`, not `.json`, or beginning with `-`;
  `Add-Content` and `Out-File`. (Review, text joined to any other part, each measured to run code on 5.1:)
  `-Path '<p>'(Write-Output x)`, `-Path '<p>'$x`, `-Encoding 'utf8'(Write-Output x)`,
  `-Encoding utf8(Write-Output x)`, `-Path .agentweave/calls/$(Write-Output x).json`,
  `-Path .agentweave/calls/a(b).json`, `-Path ".agentweave/calls/r.json"`, `-Path(…)`, `-Value$(…)` and
  `Set-Content(…) …`. (Review, further gaps:) `| Out-Null`, `> x.txt` and `# c` after a valid write; a valid write
  followed by `\nWrite-Output x`, and by `\r\nWrite-Output x`; `-Encoding:utf8`; both `-Path` and `-LiteralPath`;
  a path given as an array, `-Path '<p>','x.txt'`; and a literal holding parameter-like text whose real `-Encoding`
  is absent, `-Value 'a -Encoding utf8' -Path '<p>'`. Under the operator posture, each is asked (`asked` has one
  entry), and `_decide`'s answer equals the answer with `_hub_own_powershell_write` patched to return False.
  - **Done 2026-10-02:** `test_a_near_miss_of_the_write_falls_through`, 65 rows, each equal to `_decide` with the predicate patched off. Three rows added beyond the list (a quoted part joined straight to the next parameter, e.g. `-Value '…'-Encoding utf8`): without them, removing the space-or-end rule failed no test, because the next word is itself a valid parameter name. Mutations: boundary rule removed -> 3 fail; path allow-list replaced by a `*?[]` blacklist -> the `a(b).json` row fails.
- [x] 1.5 `test_the_write_has_standing_only_in_powershell`: the 9.10 text as a `Bash` request, and as a `Shell`
  request, falls through.
  - **Done 2026-10-02:** `test_the_write_has_standing_only_in_powershell` (`Bash`, `Shell`).
- [x] 1.6 `test_a_junctioned_calls_directory_gives_the_write_no_standing`: reuse the existing junction fixture
  (`test_a_junctioned_calls_directory_gives_no_standing`). The 9.10 form falls through.
  - **Done 2026-10-02:** `test_a_junctioned_calls_directory_gives_the_write_no_standing`.
- [x] 1.7 Controls (PASS today, must keep passing): the whole existing file; `hub/tests/test_permission_approver.py`;
  `hub/tests/test_copilot_acp_run_turn.py`; `hub/tests/test_copilot_acp_decide.py`.
  - **Done 2026-10-02:** the controls pass (`test_hub_own_call.py`, `test_permission_approver.py`, `test_copilot_acp_run_turn.py`, `test_copilot_acp_decide.py`).
- [x] 1.8 A Copilot-path test in `hub/tests/test_copilot_acp_decide.py`, beside slice 3's call-command tests (`:1140`,
  `:1146`, `:1193`): an `execute` request of the 9.10 form on a **spec turn** is answered ALLOW with "the Hub's own
  tools" before the judge, in each posture. (R2) Its `calls` map holds `CallFacts(tool_name="powershell", …)` for
  the call id, as the captured start event reports and as `:1140` does. Controls: the same request with no facts,
  and with `tool_name="write_powershell"`, is keyed `Shell` and falls through to the judge.
  - **Done 2026-10-02:** `test_a_powershell_args_file_write_has_standing_on_a_spec_turn` (3 postures; 3 failed on the pre-change source) and `test_the_write_from_a_shell_keyed_shell_goes_to_the_judge` (no facts; `write_powershell`).
- [x] 1.9 (Review) Add the 9.10 form, as a `PowerShell` request, to the existing `test_the_predicate_is_total`.
  Today it drives only `Bash` and `Write`, so a raise inside case 4 (from `realpath`, say) is untested.
  - **Done 2026-10-02:** `test_the_write_predicate_is_total` (a separate test beside `test_the_predicate_is_total`, same raising `realpath`).
- [x] 1.10 (Review, D5) A notice-text test for each of the three sites (`agents.py` preamble, `launchability.py`
  notice, the shim's decode error in `mcp_server.py`): each contains
  `Set-Content -Path '.agentweave/calls/<file>.json' -Value '<json>' -Encoding utf8`, and the text the 1.1 test
  gets by filling the placeholders has standing. Fails today.
  - **Done 2026-10-02:** `test_each_notice_spells_the_write_out_and_the_filled_form_has_standing` (3 sites; failed on the pre-change source). The notice also says to double any `'` in the JSON.

## 2. The fix

- [x] 2.1 `_hub_own_powershell_write(command, workspace) -> bool` in `hub/hub/mcp_server.py`, beside
  `_hub_own_command`, implementing design D2 over the raw text. Reuse `_plain_calls_path` for the path, and
  `_PLAIN_COMMAND_CHARS_POWERSHELL` for the path's characters. Stdlib only (`.claude/rules/mcp-server.md`).
  - **Done 2026-10-02:** `_hub_own_powershell_write` with `_ps_bare_word`/`_ps_single_quoted`, a scanner over the raw text; stdlib only.
- [x] 2.2 Call it from `_hub_own_call`'s shell branch when the tool's dialect is `powershell`, after
  `_hub_own_command`. Update `_hub_own_call`'s docstring ("exactly three cases" becomes four) and the module note
  above `_HUB_OWN_REASON`.
  - **Done 2026-10-02:** called from `_hub_own_call`'s shell branch for the `powershell` dialect, after `_hub_own_command`; docstring says four cases; module note added.
- [x] 2.3 Update slice 3's design D8 text? **No**: slice 3 is a separate change. Instead, add one line to this
  design's round log naming the D8 sentence this change amends.
  - **Done 2026-10-02:** round log line added (Implementation).
- [x] 2.4 (Review, D5) Spell the form out at the three notice sites (`hub/hub/api/v1/agents.py:1628-1632`,
  `hub/hub/launchability.py:445-449`, `hub/hub/mcp_server.py:2452-2455`), keeping the file tool as the preferred
  route. Update any existing notice-text assertions (`test_launchability.py:601` asserts `-Encoding utf8`, which
  still holds).
  - **Done 2026-10-02:** the three sites spell out `Set-Content -Path '.agentweave/calls/<file>.json' -Value '<json>' -Encoding utf8`; the file tool stays preferred.
- [ ] 2.5 `py -3.11 -m pytest hub/tests/test_hub_own_call.py hub/tests/test_permission_approver.py
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
  holds "The Hub's own call command is decided like the Hub's own tools". If not, stop here and log it. (Review)
  Also check that the synced requirement's text equals this delta's MODIFIED text with this change's additions
  removed: the SHALL clause's PowerShell item, the "The Hub tells a run…" paragraph, the `Set-Content` and
  literal sentences added to the residual paragraph, the rewritten "almost an invocation" paragraph, and the seven
  new scenarios. If they differ, re-base the delta on the synced text before archiving.
- [ ] 4.2 `openspec validate an-arguments-file-written-from-powershell-is-the-hubs-own --strict`, then the
  `openspec-archive-change` skill. Commit and push, staging paths explicitly.
