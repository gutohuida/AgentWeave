## 0. Before building

- [x] 0.1 R2 and 0.2 R3: independent re-derivations against `hub/hub/mcp_server.py` (`_words`, `_judge_word` rule 4, `_lex`'s literal `$`) and the separator-less requirement; recorded in `spec-queue/tracks/B4.md`
- [x] 0.2b R4 (revise round after the operator's 2026-09-24 review): re-derived from the code at `b7d976a`; recorded in `B4.md` under "R4"
- [x] 0.2c R5: an independent verification round of the R4 design
- [x] 0.2d R6 (revise round after the second Opus pre-approval review, `spec-queue/tracks/reviews/B4-2026-09-24-second.md`): the PowerShell `env:` pattern, bash's `env:` forms, `Temp:` in PowerShell only, the bracket glob through the sibling's D11; recorded in `B4.md` under "R6"
- [x] 0.2e R7: one independent comparison round of R6's fixes against the code, before approval; recorded in `B4.md` under "R7" (no defect of this change's own; `B4-temp-dialect` cited)
- [x] 0.2f R8 (the third Opus pre-approval review's fixes, `spec-queue/tracks/reviews/B4-2026-09-24-third.md`; the operator approves after this round): the review's LOW taken the cleaner way, in the sibling's D8 step 2: a bracket expression is matched exactly unless `fnmatch` cannot read it, and then as `?`; D10's R6 paragraph, Costs and task 1.4f's rows. Measured with real junctions in `testbed/scratch/b4-r8/`; recorded in `B4.md` under "R8"
- [x] 0.3a The operator answers design Open Questions 2 and 3: answered 2026-09-24 afternoon in `spec-queue/DECISIONS.md` (`B4-dep-links`: build D10 as written, residual filed as F444; `B4-drive-exists`: a drive word is judged only when the drive exists). D5 and `PWD` were answered earlier the same day
- [x] 0.3 The operator approves in `APPROVALS.md` (after the Opus pre-approval review); told first that `:8000`'s next run uses the edited file -- `DECISIONS.md` `B4-approve` (DECIDED): both B4 changes approved as R8 left them
- [x] 0.4 (R4; order decided in `B4-residuals`: both in one night window) `the-shell-judge-reads-a-word-whole` is built first. This change uses its `_glob_links`, budget, level-by-level escape reading, `_DRIVE_LETTERS` and `hub-judge-windows` job

  **Re-derived fresh against the sibling's current code** (not assuming iter 32's or any later note
  still holds): `grep -n` for each of this task's five named symbols in `hub/hub/mcp_server.py`
  confirms all five are present and wired into production code -- `_glob_links` (defined, called
  from `_judge_path`/`_judge_piece`), `_Budget` (the per-`_decide` memo class, `budget.list_directory`/
  `budget.expand_braces`), `_escape_removed_levels` (defined and called from `_memo_judge_word`'s
  level loop), and `_DRIVE_LETTERS` (defined, documented as "D9: the one platform key ... and the
  sibling change's drive rules"); `.github/workflows/ci.yml` has a `hub-judge-windows` job. The
  sibling's own tasks 2.2a, 1.7c, 2.3 and 4.1 stay unticked (two parked on operator decisions,
  `shell-judge-escape-scope-1-7c` and `shell-judge-2-3-eight-files`, both OPEN in
  `spec-queue/DECISIONS.md`), but this task names code dependencies by symbol, not the sibling's
  own closure -- all five exist and are exercised by the sibling's passing test suite, so this
  change's own section 1 and 2 tasks are unblocked to build against them.

## 1. Tests first (in `hub/tests/test_permission_approver.py`) — each must fail on today's code or on the R3 design as written (each row says which)

- [ ] 1.1 F402, PowerShell, on Windows only (`skipif os.name != "nt"`; runs in the `hub-judge-windows` job; the workspace fixture's drive is the tmp drive). Refused as outside, naming the word with its colon: `Copy-Item notes.md <other>:`, `Copy-Item x <other>:foo`, `Copy-Item x -Destination:<other>:`, where `<other>` is an **existing** drive that is not the workspace's (operator, `B4-drive-exists`; taken or made with `subst` as in 1.5c). Each FAILS today (allow)

  **Measured, not ticked.** Made a real second drive with `subst Z: C:\Windows\Temp` on this machine (only `C:` otherwise real) and ran all three cases directly against `_decide`, workspace on `C:`: `Copy-Item notes.md Z:`, `Copy-Item x Z:foo`, and `Copy-Item x -Destination:Z:` are each `allow=True`, reason "inside your workspace" -- confirming the task's own "FAILS today (allow)" claim rather than assuming it. Did not add these rows to `_TABLE`: ticking this task means asserting `allow=False`, and getting there needs `_PS_DRIVE_RE`, the colon-joined option reading, and `_drive_exists` (this change's own D1/task 2.0-2.1) gated behind `_DRIVE_LETTERS` (the sibling change's D9) -- a one-line constant, but task 0.4 above, still unticked, names the sibling as "built first" for exactly this reason, and the sibling's own remaining work that would deliver D9 in sequence (task 2.2a) is itself parked on D7/D8/D11/D12 (see `the-shell-judge-reads-a-word-whole` tasks.md). Removed the `subst` mapping (`subst Z: /d`) after measuring. Queued next: task 1.2, which needs no drive machinery (the workspace's own drive already resolves inside without an existence check).
- [x] 1.2 F402 controls that stand, both platforms. PowerShell: `Copy-Item x <own drive>:` and `<own>:foo` (Windows), `git show HEAD:README.md`, `sed s:a:b: f`. Bash: `cp notes.md C:`, with the workspace on C on Windows. Each PASSES today and catches a rule that ignores the dialect or the second colon

  Measured directly against `_decide` (workspace on `C:`, this machine): `Copy-Item x C:`, `Copy-Item x C:foo`, `git show HEAD:README.md`, `sed s:a:b: f` (PowerShell), and `cp notes.md C:` (Bash) are each `allow=True` today. Added as rows `1.2a`-`1.2e` to `_TABLE` in `hub/tests/test_permission_approver.py`, using a new `<owndrive>` placeholder (`test_the_decided_table` substitutes the workspace's actual drive) so the row is not pinned to `C:` specifically; `1.2a`, `1.2b` and `1.2e` (the ones that use a drive letter) are `skipif sys.platform != "win32"`, since a bare drive letter is not a POSIX concept. No production code changed -- these are forward-looking regression guards for the fix task 1.1 is blocked on. `py -3.11 -m pytest hub/tests/test_permission_approver.py -q`: 305 passed, 1 skipped (up from 300). `ruff check`: clean. `black --check --target-version py311`: required one reformat (wrapped the new `skipif` calls), reapplied and reconfirmed clean and still 305 passed.
- [ ] 1.3 F402 `Temp:`: PowerShell `Copy-Item x Temp:` refused as outside, with `TMP`/`TEMP` monkeypatched to a directory outside the workspace; FAILS today. (R6, design D1) In the bash reading `temp:` stays an ordinary word, with `_DRIVE_LETTERS` monkeypatched True and the same `TMP`/`TEMP`: Bash `cat <<'EOF'` / `temp: 5` / `EOF` is allowed (FAILS against R5, which kept the colon in bash on a drive-letter host), and Bash `pwsh -c 'Copy-Item x Temp:'` is allowed (the named residual, asserted so a change of mind is visible)

  **Not attempted, flagged only (inferred from the design text, not measured).** The row's own wording monkeypatches `_DRIVE_LETTERS`, a symbol that does not exist in `hub/hub/mcp_server.py` today (confirmed by `grep`, same gap as task 1.1). Same block as 1.1; leave for whoever builds D9.
- [x] 1.4 F401, refused as uncheckable (the reason contains "cannot be checked", not "outside"). Each FAILS today:
  - Bash: `cp notes.md $HOME`, `"$HOME"`, `${HOME}`, `$OLDPWD`, `$TMP`, `--target-directory=$HOME`, `cp x %USERPROFILE%`.
  - PowerShell: `Copy-Item x $HOME`, `$env:USERPROFILE`, `$ENV:temp`, `-Destination:$HOME`.
  - Bash: `cp notes.md ..$x` and `..$(echo)`.
  - (R2) Bash: `cp x $HOME.bak`, `cp x $PWD..`, `cp x ${HOME-y}`.

  **Built.** Measured each row directly against `_decide` before touching production code (all 16
  were `allow=True` today, matching the claim). Added rows `1.4a`, `1.4g`-`1.4u` to `_TABLE` in
  `hub/tests/test_permission_approver.py` (letters `b`-`f` skipped: tasks.md reserves them for
  1.4b-1.4f, the extended-spellings/colon-after/inner-shell/`..`-survives/link families, each its
  own later task). Added the minimal D2 and D3 checks to rule 4 in `hub/hub/mcp_server.py`
  (`_directory_variable_reference`, `_first_expansion_start`, and the `_DIRECTORY_VARIABLE_RE`/
  `_CMD_DIRECTORY_VARIABLE_NAMES` tables), with only the names task 1.4's own rows exercise (bash
  `HOME`/`OLDPWD`/`TMP`/`PWD`, PowerShell `HOME` bare and `USERPROFILE`/`TEMP` via `env:`, and
  `%USERPROFILE%` either dialect) -- the rest of D2's spelling table is 1.4b's own measurement, not
  assumed here.

  **A side effect, not in the task's own list:** the fix also changes two pre-existing rows,
  `X2p`/`X3p`, on the non-Windows branch of `_BACKSLASH_ROWS` (`type %USERPROFILE%\x` and
  `Get-Content $env:USERPROFILE\x`, PowerShell tool). On POSIX `\` is not a separator, so these
  reach rule 4 rather than rule 3, and now correctly refuse by D2 -- the same verdict the Windows
  branch already reached by a different rule (rule 3, where `\` is a separator). Verified by
  monkeypatching `mcp_server._SEPARATORS` to `"/"` on this Windows machine to simulate the POSIX
  reading directly against `_decide`, since the real POSIX branch cannot run here; updated both
  rows from `True` to `False`/`_UNCHECKED`.

  **Mutation check:** `git stash`-ed `hub/hub/mcp_server.py` only; all 16 new rows failed (allowed)
  without the fix, confirming each measures real behaviour; restored and reconfirmed green.
  `py -3.11 -m pytest hub/tests/test_permission_approver.py -q`: 321 passed, 1 skipped (up from
  305; +16 rows). `ruff check`: clean. `black --check --target-version py311`: required one
  reformat of the test file (the new rows' line wrapping); reapplied and reconfirmed clean, still
  321 passed.
- [ ] 1.4b (R4, the extended list and spellings), refused as uncheckable. Each FAILS today (allowed; measured for most at `b7d976a`) and FAILS against the R3 design (not on its list, or its PowerShell regex does not match):
  - Bash: `cp n $HOMEPATH`, `cp n $HOMEDRIVE$HOMEPATH`, `cp n $PUBLIC`, `cp n $OneDrive`, `cp n $ONEDRIVE`, `cp n $ProgramData`, `cp n $ALLUSERSPROFILE`, `cp n $SYSTEMROOT`, `cp n $windir`, `cp n $PROGRAMFILES`, `cp n $XDG_CONFIG_HOME`, `cp n $XDG_RUNTIME_DIR`.
  - PowerShell: `Copy-Item x ${env:TEMP}`, `${HOME}`, `$variable:HOME`, `$global:HOME`, `$script:PWD`, `$PROFILE`, `$PSHOME`, `${env:ProgramFiles(x86)}`.
  - Either dialect: `cp x %CD%`.
- [ ] 1.4c (R4, after a colon) `dd if=n of=c:$HOMEPATH` and `echo PATH=a:$HOME` refused as uncheckable. Each FAILS today and against R3
- [ ] 1.4d (R4, **inner-shell `$HOME`**) Refused as uncheckable. Each FAILS today (allowed, measured) and FAILS against the R3 design, which excluded `_LITERAL_DOLLAR` on purpose:
  - Bash tool: `bash -c 'cp n $HOME'`, `sh -c "cp n \$HOME"`, `bash -c 'cp n ${HOME}'`, `bash -c 'cp n ..$x'`, `powershell -c 'Copy-Item x $HOME'`.
  - PowerShell tool: `bash -c 'cp n $HOME'`, `powershell -c 'Copy-Item x ${env:TEMP}'`.
  - POSIX CI: `bash -c 'bash -c "cp n \$HOME"'`, which needs the sibling change's level-by-level escape reading.
  - (R6) Bash tool: `powershell -c 'Copy-Item x $env:TEMP'` and `powershell -c 'Copy-Item x ${env:USERPROFILE}'`. Each FAILS today (allowed, measured: the words are `␀env:TEMP` and `␀{env:USERPROFILE`) and FAILS against R5, whose bash pattern had no `env:` form.
- [ ] 1.4e (R4, D3) Refused as uncheckable. Each FAILS today (allowed, measured) and FAILS against R3 (whose D3 read only the text before the first expansion):
  - Bash: `cp n $x..`, `cp n $(true)..`, `cp n .$x.`, `` cp n `true`.. ``;
  - Bash tool: `` bash -c 'cp n `true`..' ``;
  - PowerShell: `Copy-Item n $x..`.
- [ ] 1.4f (R4, D10) With the sibling change's link fixture (`up` → outside, made with `os.symlink` or `_winapi.CreateJunction`), refused as outside, naming where `up` resolves. Each FAILS today (allowed, measured) and against R3:
  - Bash: `cp n up`, `cp n u*`, `cp -tup n`, `cp n {up,x}`, `cp --target-directory=up n`, and `ls -d .*` with a link `.l` → outside;
  - PowerShell: `Copy-Item n up`, `Copy-Item n -Destination:up`;
  - (R6) Bash: `cp n [u]p` and `cp n u[p]`. Each FAILS today (allowed, measured; both wrote through `up` in Git Bash) and FAILS against R5 (the words are `u]p` and `u[p`; needs the sibling's D11 bracket-kept word).

  Controls allowed: `cp n sub`, `ls in` (an inside link), `cp -r n newdir`, `grep -r foo --exclude-dir=node_modules .` with no `node_modules` link. With `node_modules` a link to outside, that grep is **refused**: assert it, so the accepted cost stays visible.

  (R8, the third review's LOW; the sibling's D8 step 2) With `node_modules`, `venv` and `.venv` each a link to outside at the workspace root, a bare bracket expression is matched as the shell matches it, not as `*`. Allowed: Bash `grep '[0-9]' f`, `tr '[:upper:]' '[:lower:]'` and `grep '[[:digit:]]' f` (the bracket-kept words `[0-9]`, `[:upper:]`, `[:lower:]` and `[[:digit:]]` reach step 3), and PowerShell `Select-String '[0-9]' f` (no dot rule there, so `.venv` would match a `*`). Each PASSES today (allowed, measured) and FAILS against the sibling's D8 as R7 wrote it (every bracket expression relaxed to `*`, which matches the links). In the same fixture `cp n [u]p` and `cp n u[p]` stay refused, naming where `up` resolves: the second review's HIGH 1 is not reopened (`fnmatch` matches both to `up`, measured).
- [x] 1.5 F401 controls that must stay allowed. Each PASSES today and names the rule it catches:
  - `echo $x`, `for f in $files; do echo $f; done`, `test -n "$VAR"`;
  - `echo $HOMEDIR` (a prefix match), `echo '$HOMEDIR'`;
  - `tmp=$(mktemp); cp x $tmp` (a lowercase user variable), `cp x $(git rev-parse --show-toplevel)` (a substitution naming no directory variable);
  - the commit heredoc `git commit -m "$(cat <<'EOF'` / `fix the judge` / `EOF` / `)"`;
  - (R6) PowerShell: `$tmp = New-TemporaryFile; Remove-Item $tmp` and `Copy-Item x $TEMP` (a script variable, not the environment's). Each PASSES today and FAILS against R5, whose PowerShell pattern made the `env:` prefix optional for every name.

  **Measured, then built.** Ran all 10 rows directly against `_decide` before touching the test
  file: each is `allow=True` today, matching the claim. Added rows `1.5d`-`1.5m` to `_TABLE` in
  `hub/tests/test_permission_approver.py` (letters `a`-`c` skipped: `tasks.md` reserves them for
  tasks 1.5a-1.5c, each its own later task, matching the convention task 1.4's table already uses
  for `1.4b`-`1.4f`). No production code changed -- these are forward-looking regression guards for
  D2's fix, same category as task 1.2's precedent. `py -3.11 -m pytest
  hub/tests/test_permission_approver.py -q`: 331 passed, 1 skipped (up from 321; +10 rows). The
  broader regression set (adds `test_the_shell_judge_reads_a_word_whole.py`,
  `test_hub_own_call.py`, `test_copilot_acp_decide.py`,
  `test_a_write_outside_the_workspace_is_recorded.py`): 685 passed, 2 skipped, nothing broken.
  `ruff check` and `black --check --target-version py311`: both clean, no reformat needed.
  `git diff --stat` confirms only the test file changed.
- [x] 1.5a (R4, the accepted costs, asserted refused so that a change of mind is visible) `echo '$HOME'`, `grep '$HOME' f`, `cp x $(dirname $PWD)`, and the commit heredoc whose body line is `use $HOME for config`. Each PASSES today (allowed), so each FAILS today, and the first three also FAIL against R3. (R6) Also PowerShell `Copy-Item x $PWD.Path` and `Write-Output $HOME.Length`, refused (member access; design Costs). Each FAILS today (allowed)

  **Measured, then built.** Ran all six rows directly against `_decide` before touching production
  code: five already refuse today for free (`echo '$HOME'`, `grep '$HOME' f`,
  `cp x $(dirname $PWD)`, the heredoc, and `Write-Output $HOME.Length` -- task 1.4's D2 fix already
  reads the lexed word's text regardless of quoting or the `.Length` member-access tail, the same
  way it reads `$HOME.bak` in row 1.4s). One did not: PowerShell `Copy-Item x $PWD.Path` was
  `allow=True` -- `_DIRECTORY_VARIABLE_NAMES["powershell_auto"]` only carried `HOME`, never bare
  `PWD`, even though design.md line 80-81 names `PWD` as one of PowerShell's own four directory
  variables (`HOME`/`PWD`/`PSHOME`/`PROFILE`). Confirmed `PSHOME`/`PROFILE` are 1.4b's own rows
  (its own list has `$PROFILE`/`$PSHOME` bare), not this task's -- 1.4b never claims bare `PWD`
  (only the scoped `$script:PWD`), so adding it here does not collide with that later task.

  **Fix, `hub/hub/mcp_server.py`:** added `"PWD"` to `_DIRECTORY_VARIABLE_NAMES["powershell_auto"]`
  (now `("HOME", "PWD")`) -- a one-tuple-element change; the existing `(?![A-Za-z0-9_])` lookahead
  already does the member-access reading, so `$PWD.Path` and `$PWD` both match while `$PWDX` would
  not.

  Added rows `1.5a1`-`1.5a6` to `_TABLE` in `hub/tests/test_permission_approver.py`. **Mutation
  check:** `git stash -- hub/hub/mcp_server.py`, reran the six rows: exactly `1.5a5`
  (`Copy-Item x $PWD.Path`) failed (wrongly allowed); the other five passed unchanged against the
  unmodified code, confirming the "five already pass" claim rather than assuming it. Popped the
  stash; all six pass. **Suites run green.** `py -3.11 -m pytest
  hub/tests/test_permission_approver.py -q`: 337 passed, 1 skipped (up from 331; +6 rows). The
  broader regression set (adds `test_the_shell_judge_reads_a_word_whole.py`,
  `test_hub_own_call.py`, `test_copilot_acp_decide.py`,
  `test_a_write_outside_the_workspace_is_recorded.py`): 691 passed, 2 skipped, nothing broken.
  `ruff check` and `black --check --target-version py311`: both clean, no reformat needed. `mypy
  hub/hub/mcp_server.py`: one error, the same pre-existing `approve_tool_call`
  no-return-annotation gap `.claude/rules/mcp-server.md` names as deliberate (shifted line only).
  `git diff --stat`: only the two expected files changed, production diff is the single tuple
  element.
- [ ] 1.5b (R3, design D4). Each FAILS today (allowed):
  - Windows, Bash tool: `python w.py <other>:` and `powershell -c 'Copy-Item x <other>:'`, with `<other>` an existing drive as in 1.1, refused as outside;
  - both platforms: `dd if=x of=c:~` and `echo PATH=a:~`, refused as uncheckable;
  - `cp x ..*` and `cp x .{,.}*`, refused as outside.

  Controls that stand: `grep '.*' f`, `ls -d .*` (no dot-named link), and, on Windows, Bash `cp notes.md C:` with the workspace on C.

  **Partially built, iteration 14.** Re-measured all three bullets directly against `_decide` before
  touching anything (not trusting a prior note): the first bullet's drive refusal still needs
  `_DRIVE_LETTERS`/`_drive_exists` (task 2.0, the sibling change's D9) -- confirmed still absent
  (`grep -n "_DRIVE_LETTERS" hub/hub/mcp_server.py` returns nothing) -- so it stays unbuilt and this
  task stays unticked. The other two bullets needed no drive machinery at all, so they were built:
  **`hub/hub/mcp_server.py`**, in `_judge_word`'s rule 4 (no-separator) branch -- (a) the tilde check
  now also reads the text after a word's *last* `:` (`value.rfind(":")`, `_TILDE_PREFIX_RE.fullmatch`
  on the suffix), both dialects, not just PowerShell's colon-option case already there (confirmed
  `_words` already splits `dd of=c:~` into the standalone word `c:~` at the lexer's own `=` split, so
  no assignment-prefix handling was needed); (b) a separator-less value cut at a NUL that starts with
  `..` (two dots, not one -- `.*`/`.?` stay a quoted regex per D10), holds a glob character, and
  `fnmatch.fnmatchcase("..", cut)` proves it can expand to `..`, is judged as `..` the same way an
  exact `..` already was. Added rows `1.5b1`-`1.5b7` to `_TABLE` in
  `hub/tests/test_permission_approver.py` (the two controls as `1.5b6`/`1.5b7`, regression guards).
  **Mutation check:** `git stash -- hub/hub/mcp_server.py`, reran the new rows: exactly `1.5b1`-`1.5b5`
  failed (the two controls, `1.5b6`/`1.5b7`, passed unchanged); popped the stash, all seven pass.
  `py -3.11 -m pytest hub/tests/test_permission_approver.py -q`: 344 passed, 1 skipped (+7 rows). The
  broader regression set (adds `test_the_shell_judge_reads_a_word_whole.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): 698 passed, 2
  skipped, nothing broken. `ruff check` and `black --check --target-version py311` on both changed
  files: clean. `mypy hub/hub/mcp_server.py`: the same pre-existing `approve_tool_call`
  no-return-annotation gap (line shifted only). `git diff --stat`: only the two expected files
  changed. The `cp notes.md C:` control (bullet 1's own) was not added as a row here -- it belongs
  with the drive machinery it is a control *for*, same as 1.5c's own controls.
- [ ] 1.5c (operator, `B4-drive-exists`; design D1, `_drive_exists`) A drive word is judged only when the drive exists:
  - **Both platforms (Linux CI included), with `_DRIVE_LETTERS` monkeypatched True and `_drive_exists` monkeypatched**, and a spy on `_judge_path`:
    - probe answers False for E and A: `py - <<'PY'` / `try:` / `    pass` / `except Exception as e:` / `    print(e)` / `PY`, and `jq '{a: .x, b: .y}' f`, are allowed, and `_judge_path` never receives `e:`, `a:` or `b:`. Each FAILS against R4 as written (judged as a drive regardless);
    - probe answers True for E: the word `e:` reaches `_judge_path` (on Linux `_where("e:")` is inside, so the spy, not the verdict, is the assertion). FAILS today (the colon is trimmed);
    - `e:$HOMEPATH` with the probe answering False is refused as uncheckable (D2 after a colon never consults the probe);
    - the probe is called once per letter per `_decide` (memo): a command naming `e:` three times calls it once.
  - **`_drive_exists` itself, both platforms**, with `os.stat` monkeypatched for drive-root arguments only (delegating every other path): `FileNotFoundError` → False; a return → True; `PermissionError`, `OSError(22, "not ready", None, 21)`, `ValueError` and a bare `RuntimeError` → True (a raise counts as existing), and none propagates.
  - **Windows job, real probe:** with no drive E and no drive A present (`skipif` either exists), the heredoc and the `jq` row above are allowed. `Copy-Item x <other>:` and Bash `python w.py <other>:`, with `<other>` an existing drive other than the workspace's, are refused as outside, naming the word with its colon: the test takes an existing letter if the runner has one (`windows-latest` normally has D), otherwise it makes one with `subst` pointing at the fixture's `outside/` and removes it in `finally`; skip if `subst` fails. Each FAILS today (allowed). `dd if=n of=<own>:$HOMEPATH`, with `<own>` the workspace's drive, is refused as uncheckable: catches a drive check that ends rule 4 on an inside answer
- [ ] 1.6 Update the `_decide` docstring assertion if any test pins its text; rows R5, R6 and X3b keep their answers

## 2. The fix

- [x] 2.0 `_drive_exists(letter)`: `os.stat(letter + ":\\")`, `FileNotFoundError` → False, a return → True, any other exception → True; memoized per letter in the sibling change's per-`_decide` memo (design D1)

  **Built.** Added `_drive_exists(letter)` to `hub/hub/mcp_server.py` (module level, just before
  `_Budget`) and a memoized wrapper `_Budget.drive_exists(letter)` with its own `self._drive_exists:
  Dict[str, bool] = {}`, matching the existing `list_directory`/`expand_braces` memo pattern on the
  same class. Task 1.5c's second bullet built alongside it (not the whole task -- the real-probe
  Windows-job bullet and the `_judge_path`-level monkeypatch bullet both need `_PS_DRIVE_RE`/rule 4
  wiring, tasks 2.1/2.2, still unbuilt): two new tests in `hub/tests/test_permission_approver.py`,
  `test_drive_exists_reads_stat_outcomes` (all five outcomes from design D1's table, `os.stat`
  monkeypatched for drive-root arguments only, every other path delegated to the real call) and
  `test_drive_exists_is_memoized_per_budget` (a second call for the same letter makes no second
  `os.stat`). **Mutation check:** `git stash -- hub/hub/mcp_server.py`, reran both new tests:
  both failed (`AttributeError: '_Budget' object has no attribute 'drive_exists'`, since
  `_drive_exists` does not exist without the fix); popped the stash, both pass. `py -3.11 -m pytest
  hub/tests/test_permission_approver.py -q`: 346 passed, 1 skipped (up from 344; +2 tests, not
  `_TABLE` rows -- `_drive_exists` is tested directly, not through `_decide`). The broader
  regression set (adds `test_the_shell_judge_reads_a_word_whole.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): 769 passed, 6
  skipped, nothing broken. `ruff check` and `black --check --target-version py311` on both changed
  files: clean (one `N806` rename, a local sentinel `object()` from `_RAISE` to `raise_sentinel`,
  before either check passed). `mypy hub/hub/mcp_server.py`: the same pre-existing
  `approve_tool_call` no-return-annotation gap `.claude/rules/mcp-server.md` names as deliberate
  (line number unchanged by this task's own addition, which sits earlier in the file). `git diff
  --stat`: only the two expected files changed.
- [ ] 2.1 `_words(arguments, dialect)` and `_PS_DRIVE_RE`, keeping the colon for a bare drive and for a colon-joined option whose value is a drive (design D1, R2); (R6) `Temp:` keeps its colon in the PowerShell reading only. Pass the dialect from `_read_command`. `_DRIVE_LETTERS` is read at call time (the sibling's D9): no regex or default argument built from it at import, or task 1.5c's monkeypatch passes without reaching the code
- [ ] 2.2 Rule 4, in this order:
  - the drive check (PowerShell on any host; bash where `_DRIVE_LETTERS`, design D4), made on a drive-letter host only when `_drive_exists(letter)` (design D1, `B4-drive-exists`), and returning only a refusal, never ending the rule on an inside or skipped answer;
  - the `~` after a colon;
  - the `..`-glob;
  - `_DIRECTORY_VARIABLE_RE[dialect]` at the value's start and after each `:`, matching `$` and `_LITERAL_DOLLAR` (design D2, R4); (R6) the PowerShell pattern requires `env:` for an environment name, and matches `HOME`, `PWD`, `PSHOME` and `PROFILE` with or without a scope prefix; the bash pattern also matches `env:` forms;
  - the `..` prefix and the `..` remainder (design D3);
  - (R4) the link check with glued-option suffixes, and `_glob_links` on a separator-less glob (design D10).

  Add a comment naming F401, F402 and D5.
- [ ] 2.3 Extend `_decide`'s docstring: a bare reference to any other variable, and a substitution, are not judged
- [ ] 2.4 Run the judge's test files and the full `hub/tests/` with `claude` off PATH, and record the counts. Expected moves: exactly group 1's new rows. Confirm that the `hub-judge-windows` job ran the Windows rows and passed, or do not tick
- [ ] 2.5 ruff and black as in CLAUDE.md

## 3. Real shells

- [ ] 3.1 In `testbed/scratch/`:
  - PowerShell 5.1, with a second drive available (or `subst`): `Copy-Item notes.md Z:` lands outside, and `Copy-Item notes.md C:` lands in the current location.
  - Git Bash: `cp notes.md $HOME` lands in home, and `cp notes.md C:` writes a file named `C:`.
  - (R4) Git Bash, with `x` unset: `echo $x.. $(true)..` prints `.. ..`; `ls -d c:$HOMEPATH` lists home; with a junction `up` pointing outside, `cp n up` lands outside.
  - (R6) Git Bash: `cp n [u]p` and `cp n u[p]` land outside through `up`. PowerShell 5.1: `$TEMP` is empty and `$tmp = New-TemporaryFile; Remove-Item $tmp` runs.

  Delete the scratch.

## 4. Close

- [ ] 4.1 F401 and F402 → `fixed <sha>`; F444 (the linked-dependency-directory finding, filed 2026-09-24 under `B4-dep-links`) left open and noted as a prerequisite for registering a JavaScript project; backlog regenerated; `openspec validate a-drive-or-a-home-variable-names-a-directory-by-itself --strict`; archive
