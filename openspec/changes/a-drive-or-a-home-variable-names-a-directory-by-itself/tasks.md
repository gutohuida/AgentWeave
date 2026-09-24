## 0. Before building

- [ ] 0.1 R2 and 0.2 R3: independent re-derivations against `hub/hub/mcp_server.py` (`_words`, `_judge_word` rule 4, `_lex`'s literal `$`) and the separator-less requirement; recorded in `spec-queue/tracks/B4.md`
- [ ] 0.2b R4 (revise round after the operator's 2026-09-24 review): re-derived from the code at `b7d976a`; recorded in `B4.md` under "R4"
- [ ] 0.2c R5: an independent verification round of the R4 design
- [ ] 0.3 The operator approves in `APPROVALS.md` and answers design Open Question 2 (D5 and `PWD` were answered on 2026-09-24); told first that `:8000`'s next run uses the edited file
- [ ] 0.4 (R4) `the-shell-judge-reads-a-word-whole` is built first. This change uses its `_glob_links`, budget, level-by-level escape reading, `_DRIVE_LETTERS` and `hub-judge-windows` job

## 1. Tests first (in `hub/tests/test_permission_approver.py`) — each must fail on today's code or on the R3 design as written (each row says which)

- [ ] 1.1 F402, PowerShell, on Windows only (`skipif os.name != "nt"`; runs in the `hub-judge-windows` job; the workspace fixture's drive is the tmp drive). Refused as outside, naming the word with its colon: `Copy-Item notes.md <other>:`, `Copy-Item x <other>:foo`, `Copy-Item x -Destination:<other>:`, where `<other>` is a letter that is not the workspace's drive. Each FAILS today (allow)
- [ ] 1.2 F402 controls that stand, both platforms. PowerShell: `Copy-Item x <own drive>:` and `<own>:foo` (Windows), `git show HEAD:README.md`, `sed s:a:b: f`. Bash: `cp notes.md C:`, with the workspace on C on Windows. Each PASSES today and catches a rule that ignores the dialect or the second colon
- [ ] 1.3 F402 `Temp:`: PowerShell `Copy-Item x Temp:` refused as outside, with `TMP`/`TEMP` monkeypatched to a directory outside the workspace; FAILS today
- [ ] 1.4 F401, refused as uncheckable (the reason contains "cannot be checked", not "outside"). Each FAILS today:
  - Bash: `cp notes.md $HOME`, `"$HOME"`, `${HOME}`, `$OLDPWD`, `$TMP`, `--target-directory=$HOME`, `cp x %USERPROFILE%`.
  - PowerShell: `Copy-Item x $HOME`, `$env:USERPROFILE`, `$ENV:temp`, `-Destination:$HOME`.
  - Bash: `cp notes.md ..$x` and `..$(echo)`.
  - (R2) Bash: `cp x $HOME.bak`, `cp x $PWD..`, `cp x ${HOME-y}`.
- [ ] 1.4b (R4, the extended list and spellings), refused as uncheckable. Each FAILS today (allowed; measured for most at `b7d976a`) and FAILS against the R3 design (not on its list, or its PowerShell regex does not match):
  - Bash: `cp n $HOMEPATH`, `cp n $HOMEDRIVE$HOMEPATH`, `cp n $PUBLIC`, `cp n $OneDrive`, `cp n $ONEDRIVE`, `cp n $ProgramData`, `cp n $ALLUSERSPROFILE`, `cp n $SYSTEMROOT`, `cp n $windir`, `cp n $PROGRAMFILES`, `cp n $XDG_CONFIG_HOME`, `cp n $XDG_RUNTIME_DIR`.
  - PowerShell: `Copy-Item x ${env:TEMP}`, `${HOME}`, `$variable:HOME`, `$global:HOME`, `$script:PWD`, `$PROFILE`, `$PSHOME`, `${env:ProgramFiles(x86)}`.
  - Either dialect: `cp x %CD%`.
- [ ] 1.4c (R4, after a colon) `dd if=n of=c:$HOMEPATH` and `echo PATH=a:$HOME` refused as uncheckable. Each FAILS today and against R3
- [ ] 1.4d (R4, **inner-shell `$HOME`**) Refused as uncheckable. Each FAILS today (allowed, measured) and FAILS against the R3 design, which excluded `_LITERAL_DOLLAR` on purpose:
  - Bash tool: `bash -c 'cp n $HOME'`, `sh -c "cp n \$HOME"`, `bash -c 'cp n ${HOME}'`, `bash -c 'cp n ..$x'`, `powershell -c 'Copy-Item x $HOME'`.
  - PowerShell tool: `bash -c 'cp n $HOME'`, `powershell -c 'Copy-Item x ${env:TEMP}'`.
  - POSIX CI: `bash -c 'bash -c "cp n \$HOME"'`, which needs the sibling change's level-by-level escape reading.
- [ ] 1.4e (R4, D3) Refused as uncheckable. Each FAILS today (allowed, measured) and FAILS against R3 (whose D3 read only the text before the first expansion):
  - Bash: `cp n $x..`, `cp n $(true)..`, `cp n .$x.`, `` cp n `true`.. ``;
  - Bash tool: `` bash -c 'cp n `true`..' ``;
  - PowerShell: `Copy-Item n $x..`.
- [ ] 1.4f (R4, D10) With the sibling change's link fixture (`up` → outside, made with `os.symlink` or `_winapi.CreateJunction`), refused as outside, naming where `up` resolves. Each FAILS today (allowed, measured) and against R3:
  - Bash: `cp n up`, `cp n u*`, `cp -tup n`, `cp n {up,x}`, `cp --target-directory=up n`, and `ls -d .*` with a link `.l` → outside;
  - PowerShell: `Copy-Item n up`, `Copy-Item n -Destination:up`.

  Controls allowed: `cp n sub`, `ls in` (an inside link), `cp -r n newdir`, `grep -r foo --exclude-dir=node_modules .` with no `node_modules` link. With `node_modules` a link to outside, that grep is **refused**: assert it, so the accepted cost stays visible.
- [ ] 1.5 F401 controls that must stay allowed. Each PASSES today and names the rule it catches:
  - `echo $x`, `for f in $files; do echo $f; done`, `test -n "$VAR"`;
  - `echo $HOMEDIR` (a prefix match), `echo '$HOMEDIR'`;
  - `tmp=$(mktemp); cp x $tmp` (a lowercase user variable), `cp x $(git rev-parse --show-toplevel)` (a substitution naming no directory variable);
  - the commit heredoc `git commit -m "$(cat <<'EOF'` / `fix the judge` / `EOF` / `)"`.
- [ ] 1.5a (R4, the accepted costs, asserted refused so that a change of mind is visible) `echo '$HOME'`, `grep '$HOME' f`, `cp x $(dirname $PWD)`, and the commit heredoc whose body line is `use $HOME for config`. Each PASSES today (allowed), so each FAILS today, and the first three also FAIL against R3
- [ ] 1.5b (R3, design D4). Each FAILS today (allowed):
  - Windows, Bash tool: `python w.py <other>:` and `powershell -c 'Copy-Item x <other>:'`, refused as outside;
  - both platforms: `dd if=x of=c:~` and `echo PATH=a:~`, refused as uncheckable;
  - `cp x ..*` and `cp x .{,.}*`, refused as outside.

  Controls that stand: `grep '.*' f`, `ls -d .*` (no dot-named link), and, on Windows, Bash `cp notes.md C:` with the workspace on C.
- [ ] 1.6 Update the `_decide` docstring assertion if any test pins its text; rows R5, R6 and X3b keep their answers

## 2. The fix

- [ ] 2.1 `_words(arguments, dialect)` and `_PS_DRIVE_RE`, keeping the colon for a bare drive and for a colon-joined option whose value is a drive (design D1, R2). Pass the dialect from `_read_command`
- [ ] 2.2 Rule 4, in this order:
  - the drive check (PowerShell on any host; bash where `_DRIVE_LETTERS`, design D4);
  - the `~` after a colon;
  - the `..`-glob;
  - `_DIRECTORY_VARIABLE_RE[dialect]` at the value's start and after each `:`, matching `$` and `_LITERAL_DOLLAR` (design D2, R4);
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

  Delete the scratch.

## 4. Close

- [ ] 4.1 F401 and F402 → `fixed <sha>`; the linked-dependency-directory finding filed if the operator chose it (design Open Question 2); backlog regenerated; `openspec validate a-drive-or-a-home-variable-names-a-directory-by-itself --strict`; archive
