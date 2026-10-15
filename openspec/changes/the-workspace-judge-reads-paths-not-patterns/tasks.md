# Tasks — the workspace judge reads paths, not patterns

## 0. Rounds and decision

- [x] 0.1 **R2.** Derive the argument again from the code, not from this proposal.
      *(done 2026-10-12 on the work PC, HEAD `6208e9a5`; see design Round log R2. Results summary at
      the end of this block.)*
      - Trace `_lex`'s PowerShell branch (`hub/hub/mcp_server.py:2958-3070`), `_words` (`:3112`),
        `_read_command` (`:3153`) and `_judge_word` (`:2294`). Confirm independently that refusal 1
        comes from rule 5 and refusal 2 from rule 3 via `_LITERAL_DOLLAR`.
      - Try to break D1: find a command-mode element that D1's first-token test would read as
        expression mode. Candidates:
        - `&('Copy-Item') x -match 'C:\o'`
        - a dot-sourced script
        - `.\tool.exe $x -match 'C:\o'`
        - a number-looking command name
        - a line continuation (backtick + newline)
        - `--%` (stop-parsing)
        - a splat `@args`
        - `$x.Method('C:\o')`
      - Try to break D2 and D3:
        - an operator that follows `,`;
        - `-replace` with no comma;
        - `-split 'C:\o', 2`;
        - `-csplit` after `(`.
      - Confirm whether `_lex` re-reads an inner `powershell -Command "…"` string, and with which
        dialect.
      - Confirm that **subagent** tool calls reach `track_call` with `toolName: "powershell"`
        before their `session/request_permission`, from `copilot_acp.py:347-402` and a captured
        subagent trace if one exists. If they do not, the change cannot fire for the drive's
        evidence, and that must be said.
      - Re-run the measurements in design Context.

      **R2 result (2026-10-12, work PC).**
      - Refusals confirmed: refusal 1 = rule 5 (`\\.git\\` is a UNC root); refusal 2 = rule 3 via
        `_LITERAL_DOLLAR` (single-quoted `$`), **not** `$_`/`$PSItem` (both measured allowed).
      - D1 bypass sweep — all **refused today**, fail safe: `(Copy-Item $x -match 'C:\o')`,
        `Write-Output $x -match 'C:\out'`, `Invoke-Expression 'Remove-Item C:\o'`, a here-string
        `@'…C:\outside…'@`, a newline separator, and `powershell -Command 'Remove-Item
        C:\outside'`. Added to the controls below (rows 1.4/1.6 extensions).
      - Nested `-Command` text is **not** re-lexed as a command (only `$(...)` recurses); `_words`
        still judges its words, so the outside path is caught. Design updated.
      - D3 cost confirmed: `$s -replace 'a','/'` is refused today on `'/'` (row 1.2 control holds).
      - Subagent tracking **confirmed from code**: `track_call(self.calls, …)` runs on every armed
        raw event (`copilot_acp.py:1292`), no subagent filter, shared `self.calls` (`:2193`,
        `:2221`, `judge()` `:2362`). The two recorded refusals were a subagent's (`task`/`explore`,
        rows `out-3788f09bbae6`, `out-4f7c7cf6d660`). R1's doubt refuted. Empirical gap: raw
        `toolName` not stored in the DB (`agent_outputs` keeps kind-label `"shell"`), so the live
        key cannot be read back — folded into `wpc2-e` and task 3.3.
      - Proposal correction: `evt-12c4`'s quote dropped a spurious `-Force` (DB row has none).
      - **Limitation:** a pattern operand containing a comma (`-replace 'a,C:\out','x'`) is split by
        `_WORD_SPLIT_RE`; only the first word is the pattern, the rest stay judged — a false
        refusal, never a bypass. See row 1.2-note below.
- [x] 0.2 **R3.** Compare the result against the spec and the existing tests, fresh.
      *(done 2026-10-12 on the work PC, HEAD `6208e9a5`; see design Round log R3. Result summary at
      the end of this block.)*
      - Read the whole of the requirement *"A path in a shell command is judged by where it
        resolves"* in `openspec/specs/agent-run-sandboxing/spec.md` and its 1.7c rows in
        `hub/tests/test_the_shell_judge_reads_a_word_whole.py`.
      - Check that the ADDED requirement contradicts no existing scenario.
      - Check that each task 1 row asserts the real producer's shape: Copilot's `rawInput.command`
        as `normalise_request` reads it (`copilot_acp.py:509-528`), and Claude's
        `{"command": …}`.
      - Check whether the inner-brace pass (`:3209-3236`) re-judges an exempt word through
        `_mark_inner_brace_sentinels`. A pattern holding `{1,2}` must not be refused by that pass
        once D6 skips it in the first pass, and must still be judged if it is not exempt.

      **R3 result (2026-10-12, work PC).** Independent re-lex/re-judge; R1 and R2 not trusted.
      - Existing requirement read in full: its scenario *"A pattern or a name with a separator in it
        is judged whole"* covers only inside-resolving words, so the ADDED requirement contradicts
        no scenario. Task 1 rows match the real producers (`rawInput.command` / `{"command": …}`).
      - **HIGH — inner-brace pass defeats the exemption for `{n,m}` patterns.** The pass
        (`:3209-3236`) iterates `arguments` and re-judges every expanded word with no exemption, and
        D6 (as R1/R2 wrote it) left it unchanged. Measured today: `$ip -match '\d{1,3}'` REFUSE on
        `'\d1'`; `$x -match 'C:\x{1,2}'`, `$x -match '\.git\\{1,2}'` REFUSE; only brace-less or
        separator-less patterns (`$a -match 'a{1,2}'`) ALLOW. So the as-designed change leaves a
        common pattern class refused, breaking the requirement's unconditional wording. **Fixed:**
        D6 and task 2.3 now skip the exempt operand in the brace pass; added failing row 1.2g and
        control 1.6f.
      - **Adversarial sweep (written before reading the controls), all refused today, none a
        bypass:** `-f` format operator (`Remove-Item ('{0}' -f 'C:\outside\f')`), redirection target
        (`$x -match 'y' > C:\outside\f`), binary-split outside **left** operand (`'C:\outside\f'
        -split '\\'`), `[IO.File]::Delete('C:\outside\f')`, `cmd /c`, `Start-Process … -ArgumentList
        '/c del'`, dot-sourcing, `&{ Remove-Item … }`, backtick continuation, pipe into
        `Set-Content`. The first three are expression-mode shapes **not** on D2's list that produce
        or carry a path — added as controls 1.5f, 1.6r, 1.5s so no implementer widens the list to
        reach them.
      - **Spec wording is exactly the exemption:** the fixed operator list, "right-hand operand",
        and the "SHALL still judge" scenarios license no broader reading. One tightening raised as
        `wpc2-g` (Unicode quote characters must disqualify a "quoted literal").
      - **`track_call` claim confirmed from code:** `on_raw_event` (`copilot_acp.py:1287`) calls
        `track_call(self.calls, …)` at `:1292` unconditionally, before any `_is_subagent` gate; the
        judge therefore sees a subagent's PowerShell calls keyed `"PowerShell"`.
- [ ] 0.3 The operator answers `wpc2-a` to `wpc2-f`, recorded in `spec-queue/DECISIONS.md`. Then
      revise the design to match.

## 1. Tests first — each must fail on today's code unless marked as a control

The new file is `hub/tests/test_the_workspace_judge_reads_paths_not_patterns.py`.

- **Fixture:** as in `test_the_shell_judge_reads_a_word_whole.py:30-55`. A `tmp_path` workspace
  containing a real `.git` directory and a few files; `monkeypatch.setenv("AW_WORKSPACE_DIR", ws)`;
  `monkeypatch.delenv("AW_RUN_TOKEN", raising=False)`.
- **Rows:** each row is a `pytest.param(..., id="1.n…")` passed to
  `mcp_server._decide(key, {"command": cmd}, workspace=ws)`. It asserts `allow` and, for a refusal,
  that the expected word is in `reason`.
- **Platform:** rows that need a backslash to be a separator are marked `windows_only`, as the
  existing file does.

The tasks:

- [ ] 1.1 **The two recorded commands, verbatim** from `evt-9d816809f8a2` and `evt-12c4094a5bdb`
      (trial DB `workpc-drive`, `event_logs.data.detail`), with the worktree path replaced by `ws`.
      Key `"PowerShell"`, `allow is True`. **Fails today.**
- [ ] 1.2 **Variants, key `"PowerShell"`, all allowed.** **Each fails today.**
      - `-cnotmatch '\\.git\\'`
      - `-imatch`
      - `-notlike '\\*\.git\*'` (a pattern that starts with `\\`. `-notlike '*\\.git\\*'` is
        already allowed today, so it is not a failing row)
      - the glued opener `{$_.FullName -notmatch '\\.git\\'}`
      - `$PSItem.FullName -match '\.git$'`
      - `'a' -split '\\'` (binary)
      - `$s -replace '\\','-'` (the pattern is exempt, and the replacement `-` is no path)
      - **1.2g (R3, fails today).** `$ip -match '\d{1,3}'` is allowed. The pattern holds a regex
        brace quantifier `{1,3}` beside a `\` separator, so the inner-brace pass (`:3209-3236`)
        refuses it today on `'\d1'`; it must ALLOW only once D6 skips the exempt operand in that pass
        too. `windows_only`. A separator-free `$a -match 'a{1,2}'` is already allowed today, so it is
        not this failing row.
      - Control, documenting D3's cost: `$s -replace '\\','/'` stays refused, now on `'/'` (the
        replacement, a root-relative path on a drive-letter host). Assert that `reason` names
        `'/'`. See `wpc2-f`.
      - **1.2-note (R2 limitation, control).** A pattern operand that itself contains a comma is
        split by `_WORD_SPLIT_RE`, so only the first word is the pattern: `$x -match 'a,C:\out'`
        stays refused on `C:\out`. This is a false refusal, not a bypass; pin it as a control so the
        limitation is not mistaken for a regression.
- [ ] 1.3 **Double-quoted literal**, if `wpc2-b` says yes: `-notmatch "\\.git\\"` is allowed.
      **Fails today.**
- [ ] 1.4 **Command-mode controls, key `"PowerShell"`, all refused (control).** Each is refused on
      today's code and must stay refused.
      - `Write-Output $x -match 'C:\outside'`
      - `Copy-Item $x -match 'C:\outside'`
      - `& $cmd -match 'C:\outside'`
      - `robocopy $x -match 'C:\outside'` (a native program. Do not use `cmd /c …` here: today it
        is refused on `/c`, which is read as a root-relative path, so it proves nothing about the
        operand)
      - `Get-ChildItem | Where-Object FullName -notmatch 'C:\outside'`
      - `Select-String -Pattern 'x' -Path C:\outside\f`
      - `(Copy-Item $x -match 'C:\outside')` (R2: command mode inside `(`; first token is a command
        name, so D1 gives no exemption)
      - `Invoke-Expression 'Remove-Item C:\outside'` (R2: `iex`'s literal argument is split by
        `_words`; `C:\outside` is judged)
      - `powershell -Command 'Remove-Item C:\outside'` (R2: the inner `-Command` text is not
        re-lexed, but its words are still judged)

      Each refusal's `reason` must name `C:\outside` (or `C:\outside\f`), not some other word.
- [ ] 1.5 **Operand controls (control).** All refused.
      - `Set-Content -Path ('x' -replace 'x','C:\outside\f') -Value y` (the replacement)
      - `Set-Content -Path (-split 'C:\outside\f')[0] -Value y` (unary split)
      - `$x = -split 'C:\outside\f'`
      - `Set-Content -Path ('C:\outside\x' -replace 'q','')` (the left operand)
      - `$x -notmatch $env:TEMP` (unquoted)
      - `$x -match "C:\o\$y"` (interpolating)
      - **1.5f (R3).** `Remove-Item ('{0}' -f 'C:\outside\f')` — the `-f` format operator is
        expression-mode and binary but is **not** on D2's list, and it *produces* its right operand
        as the value handed to `Remove-Item`. It must stay judged; assert `reason` names
        `C:\outside\f`. Guards against an implementer treating any expression-mode binary operator
        as exempt.
      - **1.5s (R3).** `'C:\outside\f' -split '\\'` — binary `-split` returns pieces of its **left**
        operand, which is not exempt (D3 exempts the pattern only). Refused on the left operand;
        assert `reason` names `C:\outside\f`.
- [ ] 1.6 **Other-statement controls (control).** All refused.
      - `Where-Object { $_ -notmatch 'x' } ; Remove-Item C:\x`
      - `Where-Object { Remove-Item C:\x }`
      - `Where-Object { $_.FullName -notmatch '\\.git\\' } | Copy-Item -Destination C:\outside`
      - `Get-ChildItem -Path C:\x | Where-Object { $_ -match 'x' }`
      - `| Remove-Item -Path $env:TEMP`
      - `Remove-Item $env:TEMP\x`
      - `Remove-Item $HOME\x`
      - `Remove-Item ~\x`
      - `Remove-Item $(Get-Location)\x`
      - `Copy-Item a.txt -Destination '\\server\share'`
      - `Where-Object { $_ -match 'a' }` + a newline + `Remove-Item C:\outside` (R2: a newline is a
        statement boundary under D1; the second statement is judged and names `C:\outside`)
      - `@'` newline `C:\outside` newline `'@` (R2: a here-string is not a recognised quoted
        literal; `_words` judges `C:\outside`)
      - **1.6r (R3).** `$x -match 'y' > C:\outside\f` — the redirection target is a separate word,
        not the operand that directly follows the operator, so it stays judged. Assert `reason`
        names `C:\outside\f`. Confirms the classifier exempts only the operand, not a later word.
      - **1.6f (R3, non-exempt brace pattern).** `Copy-Item $x -notmatch '\d{1,3}'` — command mode
        (first token a cmdlet), so the `'\d{1,3}'` argument is **not** exempt and the inner-brace
        pass must still refuse it. Pairs with 1.2g to pin that the D6 brace-pass skip applies to
        exempt operands only. `windows_only`.

      The third row is refused today because of its **pattern**. After the change it must be
      refused because of `C:\outside`, so assert that `reason` names `C:\outside`.
- [ ] 1.7 **Bash and `"Shell"` stay strict (control).** All refused.
      - Under `"Bash"`: `$x -match '/outside/f'`.
      - Under `"Shell"`: both commands from 1.1.
      - The existing row `1.7c1` (`grep -rn '\.\./' src`) is not edited and stays refused.
- [ ] 1.8 **Through the ACP route.** In the style of `hub/tests/test_copilot_acp_decide.py`
      (`_params`, `_decide` wrapper at `:139-183`):
      - Seed `calls` with `track_call(calls, "tool.execution_start", {"toolCallId": "call_1",
        "toolName": "powershell"})`. This is the shape of `turn_write_shell_mcp.jsonl` line 46.
      - Then call `decide_permission` with `kind="execute"` and `raw_input={"command": <1.1>,
        "commands": [<1.1>]}`, the captured rawInput shape (fixture line 55), under
        `WORKSPACE_PERMISSION_MODE`. Assert ALLOW. **Fails today.**
      - The same call **without** the tracked start (key `"Shell"`) is answered REJECT (control).
- [ ] 1.9 **Failing closed.** Monkeypatch the new statement classifier to raise. Assert:
      - `approve_tool_call("PowerShell", {"command": <1.1>})` answers `deny`, with *"the workspace
        check failed"*;
      - the ACP route answers `reject_once`, via `_respond_to_permission` or its test seam, as in
        `test_copilot_acp_run_turn.py`.

      Control, unless the classifier is a new function (then it fails to import today).
- [ ] 1.10 Run the file on today's code. Record inline which rows fail and which pass. Every
      non-control row must fail.

## 2. Implementation

- [ ] 2.1 `hub/hub/mcp_server.py` `_lex`, PowerShell branch: per argument, record whether it starts
      a statement (design D1's boundaries) and whether it is one fully quoted literal (D4). Return
      them alongside `arguments`, without changing what bash callers receive.
- [ ] 2.2 A classifier, `_powershell_pattern_operands(...)`. It returns the indexes of the arguments
      that are exempt under D1–D4, in expression-mode statements only, after a binary operator from
      D2's list, and only the first element for `-replace` (D3).
- [ ] 2.3 `_read_command`: in the PowerShell dialect only, skip `_memo_judge_word` for the words of
      an exempt argument (D5, D6) in **both** passes that judge it — the main word loop
      (`:3200-3206`) and the inner-brace pass (`:3209-3236`), by the argument index
      `_powershell_pattern_operands` returns. The nested pass is unchanged (a `$`-free quoted literal
      has no substitution to recurse into). Without the brace-pass skip, row 1.2g stays refused; with
      it, non-exempt brace arguments (row 1.6f) must still be judged.
- [ ] 2.4 Run group 1 until it passes. Then run all of `hub/tests/` with `py -3.11 -m pytest
      hub/tests/ -q` (on the work PC, `$py -m pytest`) and record the count inline. Name and explain
      any assertion that moved.
- [ ] 2.5 `ruff check hub/` and `black --check --target-version py311 hub/hub/ hub/tests/` are
      clean.
- [ ] 2.6 Update the docstrings of `_words` and `_read_command` to name the exemption. Do not
      reword `_OUTSIDE` or `_UNCHECKED` unless `wpc2-d` says to.

## 3. Live verification

- [ ] 3.1 On the work PC: a trial Hub from source, on a fresh profile and port (never `:8000`). Use
      a Copilot agent on the GHCP licence, under the Workspace posture, in a worktree project.
      - Prompt: *"List every file in your worktree except those under .git, using Get-ChildItem and
        a Where-Object -notmatch filter, and print the relative paths."*
      - Afterwards, in the trial DB (`mode=ro`), confirm:
        - `event_logs` has **no** `permission_denied` for that run;
        - `agent_outputs` for the run shows the tool call and the listing in the agent's reply;
        - the run finished `completed`, not cut short (WPC-1 makes a refusal visible this way).
      - Record the command Copilot actually sent, verbatim.
- [ ] 3.2 Same Hub, same agent. Ask it to *"copy README.md to C:\Windows\Temp using a single
      PowerShell line that also uses -match"*. Confirm that a `permission_denied` event is recorded
      with the outside path in `reason`, so the boundary still holds live.
- [ ] 3.3 If the drive's agent used a subagent: confirm from `agent_outputs` and the Hub log that
      the subagent call was keyed `"PowerShell"`. That is, the call was allowed, not refused by the
      `"Shell"` key's bash reading. If it was keyed `"Shell"`, record a finding (R2, task 0.1).
