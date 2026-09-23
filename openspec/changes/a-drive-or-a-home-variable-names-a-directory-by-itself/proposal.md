# Proposal — a drive or a home variable names a directory by itself

**Round 1, 2026-09-24** (bundle B4, spec track S3). Findings: **F402 (B)**, **F401 (B)**.
**Built on the recommended answer to operator decision D5** (see `design.md`). Nothing here is
implemented. R2 and R3 must re-derive it, and the operator must answer D5 and approve.

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
| `cp notes.md $(dirname $PWD)` | Bash | allow | the parent — **stays allowed** (D5) |

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
   drive) is judged as the temporary directory. Bash is unchanged: Git Bash writes a file named `C:`.
2. **Both dialects: a bare reference to a directory variable is refused as uncheckable (F401).** A
   word that is exactly one reference to a variable the shell or platform defines as a directory —
   `HOME`, `PWD`, `OLDPWD`, `USERPROFILE`, `TMPDIR`, `TMP`, `TEMP`, `APPDATA`, `LOCALAPPDATA` — as
   `$NAME` or `${NAME}` (bash), `$HOME`, `$PWD` or `$env:NAME` (PowerShell), or `%NAME%` (either,
   for a nested `cmd`), alone or as an option's joined value, is refused with the reason rule 3
   already gives. A single-quoted reference (`'$HOME'`) is literal and stands.
3. **A word whose literal text before its first expansion is `..`** (`..$x`, `..${x}`, `..$(…)`) is
   refused as uncheckable: whatever the expansion yields, the word starts in the parent.

Every other bare expansion stays allowed — `echo $x`, `for f in $files`, `test -n "$VAR"`, and the
heredoc Claude Code commits with (`git commit -m "$(cat <<'EOF' … EOF)"`), whose argument is one
bare substitution.

## Residuals, named

- A user variable that names a directory outside (`D=/tmp; cp x $D`): the assignment's own word
  `/tmp` is judged (row R6 is refused today), but a variable set in an earlier call, inherited, or
  computed (`$(mktemp -d)`) is not seen. `_decide`'s docstring already says a path built at run time
  never appears as a word (`:1546-1548`); the requirement now says so for a bare expansion too.
- `git show a:README.md` in PowerShell (a one-letter revision) is refused as drive A. Rare; the
  reason names the word.
- PowerShell drives that are not filesystem locations (`Env:`, `Function:`, `Variable:`, `Alias:`,
  `HKLM:`, `HKCU:`, `Cert:`) and drives created by `New-PSDrive` in an earlier call are not judged.

## Impact

- **Code:** `hub/hub/mcp_server.py` only — `_words` learns the dialect, rule 4 of `_judge_word`
  gains the drive, directory-variable and `..`-prefix checks. No migration, no UI, no restart;
  reaches `:8000`'s next run on edit.
- **Tests:** `hub/tests/test_permission_approver.py` rows for both findings; F375's negative controls
  (`echo $x`-style rows and the commit heredoc) must stay allowed.
- **Spec:** `agent-run-sandboxing`, the separator-less requirement is modified: its closing scope
  sentence stops disclaiming variables wholesale and names what is and is not judged.
- **Order:** independent of `the-shell-judge-reads-a-word-whole` (different rule, different
  requirement). `an-ask-me-card-says-what-workspace-only-would-decide` reads the allow reason this
  change leaves for a bare expansion.
