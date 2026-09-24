# Proposal — a drive or a home variable names a directory by itself

**Round 1, 2026-09-24** (bundle B4, spec track S3). Findings: **F402 (B)**, **F401 (B)**.
**Built on the recommended answer to operator decision D5** (see `design.md`). Nothing here is
implemented. R2 and R3 must re-derive it, and the operator must answer D5 and approve.

**R4, 2026-09-24 (revise round, after the operator's review).** The Opus review found that
`bash -c 'cp n $HOME'` bypassed D2 one quote level down. The operator sent the change back with
three answers: refuse the quoted form, extend the list, and complete the PowerShell spellings. R4
also found separator-less escapes of the same kind, allowed today (measured): `$x..`, `$(true)..`,
`dd of=c:$HOMEPATH`, and a link named by itself (`cp n up`, `cp n u*`, `cp -tup n`). Steps 2 and 3
are revised and step 5 is new. See `design.md`, "Operator review, 2026-09-24". An independent R5
comes next.

## Why

F375's change (`a-word-without-a-separator-can-still-leave`, archived 2026-09-22) made rule 4 of the
shell judge refuse the two separator-less spellings that name a directory by themselves: `..` and
the home shorthand `~`, `~+`, `~-`, `~name`. It filed three near-misses as findings by operator
decision (`DECISIONS.md` f375-findings). Two are separator-less and belong to the same rule; the
third (F403, braces) is in `the-shell-judge-reads-a-word-whole`.

Measured at `ce086b6` (`_decide` in-process, workspace `…/Temp/b4ws` on drive C):

| Command | Dialect | Today | Where it lands |
|---|---|---|---|
| `Copy-Item notes.md Z:` | PowerShell | allow — the word judged is `Z`; `_WORD_TRIM` strips the colon (`hub/hub/mcp_server.py:1054`, `_words` `:1495`) | drive Z's current location (F402) |
| `Copy-Item x Z:foo` | PowerShell | allow (rule 4: no separator) | `foo` in drive Z's current location |
| `Copy-Item x -Destination:Z:` | PowerShell | allow (the value is trimmed to `Z`) | drive Z |
| `cp notes.md $HOME`, `cp notes.md "$HOME"`, `cp notes.md ${HOME}` | Bash | allow (rule 3 needs a separator, `:1241`) | the home directory (F401) |
| `cp x --target-directory=$HOME` | Bash | allow | home |
| `Copy-Item x $env:TEMP`, `Copy-Item x -Destination:$HOME` | PowerShell | allow | temp; home |
| `cp notes.md ..$x`, `x` unset | Bash | allow | the parent (F403's note, F401's shape) |
| `cp notes.md $(dirname $PWD)` | Bash | allow | the parent — **refused after R4** (its nested `$PWD`; the operator accepts it) |
| (R4) `bash -c 'cp n $HOME'`, `sh -c "cp n \$HOME"` | Bash | allow | home, one quote level down |
| (R4) `cp n $HOMEPATH`, `$PUBLIC`, `$OneDrive`, `$XDG_CONFIG_HOME`; `dd if=n of=c:$HOMEPATH` | Bash | allow | home; `C:\Users\Public`; synced home; `~/.config`; home |
| (R4) `Copy-Item x ${env:TEMP}`, `${HOME}`, `$variable:HOME`, `$global:HOME`, `$PROFILE`, `$PSHOME` | PowerShell | allow | temp; home; the profile file; PowerShell's install directory |
| (R4) `cp n $x..`, `cp n $(true)..`, and an inner shell's backtick form | Bash | allow | the parent |
| (R4) `cp n up`, `cp n u*`, `cp -tup n` (`up` a junction to outside) | Bash | allow | through the link, outside |

The spec already refuses `~` as uncheckable because it is the home directory by itself. `$HOME` is
the same directory under another spelling, `$PWD` is `~+`, and `$OLDPWD` is `~-`. A boundary that
refuses `~` and allows `$HOME` has the incoherence F375 fixed for `..` and `../`.

## What changes

1. **PowerShell: a drive-qualified word is judged as a path (F402).** In the PowerShell reading, a
   word that is a single drive letter and a colon, optionally followed by a name with no separator
   and no further colon (`Z:`, `Z:foo`), keeps its colon and is judged by where it resolves:
   another drive is outside; the workspace's own drive is the shell's current location, which the
   judge takes to be the workspace root, as it does for every relative word. The same holds for such
   a value joined to a parameter by a colon (`-Destination:Z:`). `Temp:` (PowerShell 7's temporary
   drive) is judged as the temporary directory. Bash is unchanged on a POSIX host; on Windows see step 4 (R3).
2. **Both dialects: a bare reference to a directory variable is refused as uncheckable (F401).** A
   reference to a variable the shell, PowerShell or the platform sets for every process to one
   directory is refused with the reason rule 3 already gives. It is caught at the start of the word
   or of an option's value, or after a colon within it (R4), when no name character follows. The
   list and the reason for each name are in design D2. R4 extends it with `HOMEPATH`, `HOMEDRIVE`,
   `SystemDrive`, `PUBLIC`, the `OneDrive*` names, `ProgramData`, `ALLUSERSPROFILE`, `SystemRoot`,
   `windir`, the program directories, the `XDG_*_HOME` names, `XDG_RUNTIME_DIR`, and PowerShell's
   `$PSHOME` and `$PROFILE`. Every spelling is covered: bash `$N`/`${N…}`; PowerShell
   `$N`/`${N}`/`$env:N`/`${env:N}`/`$variable:N`/`$global:N` and the other scope prefixes; `%N%` for
   a nested `cmd`. **(R4)** A single-quoted or escaped reference (`'$HOME'`) is **refused too**,
   because an inner shell expands it (operator, 2026-09-24).
3. **A word whose literal text before its first expansion is `..`** (`..$x`, `..${x}`, `..$(…)`),
   **or (R4) whose text with every expansion removed is `..`** (`$x..`, `$(true)..`, `.$x.`), is
   refused as uncheckable: the word starts in the parent.

4. **(R3)** On a Windows host the drive reading applies to Bash commands too (they reach native
   programs and nested PowerShell); a `~` after a colon (`of=c:~`) is refused as uncheckable; and a
   separator-less glob beginning with `..` (`..*`) is judged as `..`. A separator-less `.*` stays
   allowed (often a quoted regex). Design D4.
5. **(R4) A separator-less word naming a link is judged by where the link resolves**, and so is a
   short option glued to one (`-tup`). A separator-less glob is judged by the links it matches,
   using the sibling change's `_glob_links`. Design D10.

Every other bare expansion stays allowed: `echo $x`, `for f in $files`, `test -n "$VAR"`, a
lowercase `$tmp`, and the heredoc Claude Code commits with
(`git commit -m "$(cat <<'EOF' … EOF)"`), unless its body names a directory variable as a word (R4,
an accepted cost).

## Residuals, named

- A user variable that names a directory outside (`D=/tmp; cp x $D`): the assignment's own word
  `/tmp` is judged (row R6 is refused today), but a variable set in an earlier call, inherited, or
  computed (`$(mktemp -d)`) is not seen. `_decide`'s docstring already says a path built at run time
  never appears as a word (`:1546-1548`); the requirement now says so for a bare expansion too.
- `git show a:README.md` in PowerShell (a one-letter revision) is refused as drive A. Rare; the
  reason names the word.
- (R4) Accepted costs, named in design "Costs the operator accepts": `echo '$HOME'`, `grep '$HOME' f`
  and a commit heredoc mentioning `$HOME` are refused (write the message to a file and use
  `git commit -F`). In a worktree whose `node_modules`, `.venv` or `venv` is the Hub's shared link,
  a bare mention of it is refused (design Open Question 2).
- PowerShell drives that are not filesystem locations (`Env:`, `Function:`, `Variable:`, `Alias:`,
  `HKLM:`, `HKCU:`, `Cert:`) and drives created by `New-PSDrive` in an earlier call are not judged.

## Impact

- **Code:** `hub/hub/mcp_server.py` only. `_words` learns the dialect. Rule 4 of `_judge_word`
  gains the drive, directory-variable, `..`-expansion and (R4) link and glob checks. No migration,
  no UI, no restart. It reaches `:8000`'s next run on edit.
- **Tests:** `hub/tests/test_permission_approver.py` rows for both findings; F375's negative controls
  (`echo $x`-style rows and the commit heredoc) must stay allowed.
- **Spec:** `agent-run-sandboxing`, the separator-less requirement is modified: its closing scope
  sentence stops disclaiming variables wholesale and names what is and is not judged.
- **Order (R4):** builds **after** `the-shell-judge-reads-a-word-whole`. It reuses that change's
  `_glob_links`, per-call budget, level-by-level escape reading (its D7, which makes
  `bash -c 'bash -c "cp n \$HOME"'` visible on POSIX) and `_DRIVE_LETTERS`. The Windows rows run in
  that change's `hub-judge-windows` CI job. Different requirement. `an-ask-me-card-says-what-workspace-only-would-decide` reads the allow reason this
  change leaves for a bare expansion.
