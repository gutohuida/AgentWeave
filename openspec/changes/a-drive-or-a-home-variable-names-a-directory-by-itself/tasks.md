## 0. Before building

- [ ] 0.1 R2 and 0.2 R3: independent re-derivations against `hub/hub/mcp_server.py` (`_words`, `_judge_word` rule 4, `_lex`'s literal `$`) and the separator-less requirement; recorded in `spec-queue/tracks/B4.md`
- [ ] 0.3 The operator answers D5 (recommended (d)) and design Open Question 2, records them in `spec-queue/DECISIONS.md`, and approves in `APPROVALS.md`; told first that `:8000`'s next run uses the edited file

## 1. Tests first (in `hub/tests/test_permission_approver.py`) — each must fail on today's code

- [ ] 1.1 F402, PowerShell, refused as outside naming the word with its colon, on Windows only (`skipif os.name != "nt"`; the workspace fixture's drive is the tmp drive): `Copy-Item notes.md <other>:`, `Copy-Item x <other>:foo`, `Copy-Item x -Destination:<other>:` where `<other>` is a letter that is not the workspace's drive. Each FAILS today (allow)
- [ ] 1.2 F402 controls that stand, both platforms: PowerShell `Copy-Item x <own drive>:` and `<own>:foo` (Windows), `git show HEAD:README.md`, `sed s:a:b: f`; Bash `cp notes.md C:` (Git Bash writes a file named `C:`). Each PASSES today and catches a rule that ignores the dialect or the second colon
- [ ] 1.3 F402 `Temp:`: PowerShell `Copy-Item x Temp:` refused as outside, with `TMP`/`TEMP` monkeypatched to a directory outside the workspace; FAILS today
- [ ] 1.4 F401, refused as uncheckable (reason contains "cannot be checked", not "outside"), each FAILS today: Bash `cp notes.md $HOME`, `"$HOME"`, `${HOME}`, `$OLDPWD`, `$TMP`, `--target-directory=$HOME`, `cp x %USERPROFILE%`; PowerShell `Copy-Item x $HOME`, `$env:USERPROFILE`, `$ENV:temp`, `-Destination:$HOME`; Bash `cp notes.md ..$x` and `..$(echo)`; (R2) Bash `cp x $HOME.bak`, `cp x $PWD..`, `cp x ${HOME-y}`
- [ ] 1.5 F401 controls that must stay allowed, each PASSES today and names the rule it catches: `echo $x`, `for f in $files; do echo $f; done`, `test -n "$VAR"`, `echo $HOMEDIR` (a prefix match), `echo '$HOME'` (the literal `$`), `cp x $(dirname $PWD)` (D5 leaves substitutions), and the commit heredoc `git commit -m "$(cat <<'EOF'` / `fix` / `EOF` / `)"`
- [ ] 1.5b (R3, design D4), each FAILS today (allowed): Bash tool on Windows `python w.py <other>:` and `powershell -c 'Copy-Item x <other>:'` refused as outside; `dd if=x of=c:~` and `echo PATH=a:~` refused as uncheckable (both platforms); `cp x ..*` and `cp x .{,.}*` refused as outside (the second needs the sibling change's brace step; skip it if that has not landed). Controls that stand: `grep '.*' f`, `ls -d .*` (the `.*` residual), Bash `cp notes.md C:` with the workspace on C (Windows)
- [ ] 1.6 Update the `_decide` docstring assertion if any test pins its text; rows R5, R6 and X3b keep their answers

## 2. The fix

- [ ] 2.1 `_words(arguments, dialect)` and `_PS_DRIVE_RE`, keeping the colon for a bare drive and for a colon-joined option whose value is a drive (design D1, R2); pass the dialect from `_read_command` (`hub/hub/mcp_server.py:1521`)
- [ ] 2.2 Rule 4: the drive check (PowerShell on any host, bash on a Windows host — design D4), the `~` after a colon, the `..`-glob, then `_DIRECTORY_VARIABLE_RE[dialect]` and the `..`-prefix check on the whole word and on an option's joined value (design D2, D3); a comment naming F401, F402 and D5
- [ ] 2.3 Extend `_decide`'s docstring: a bare reference to any other variable, and a substitution, are not judged
- [ ] 2.4 Run the judge's test files and the full `hub/tests/` with `claude` off PATH; record counts. Expected moves: exactly group 1's new rows
- [ ] 2.5 ruff and black as in CLAUDE.md

## 3. Real shells

- [ ] 3.1 PowerShell 5.1 in a scratch directory on C with a second drive available (or `subst`): `Copy-Item notes.md Z:` lands outside; `Copy-Item notes.md C:` lands in the current location. Git Bash: `cp notes.md $HOME` lands in home; `cp notes.md C:` writes a file named `C:`

## 4. Close

- [ ] 4.1 F401 and F402 → `fixed <sha>`; backlog regenerated; `openspec validate a-drive-or-a-home-variable-names-a-directory-by-itself --strict`; archive
