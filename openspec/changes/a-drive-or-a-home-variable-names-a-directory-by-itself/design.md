# Design — a drive or a home variable names a directory by itself

## Operator review, 2026-09-24

The operator sent this change back as **REVISING** after an Opus adversarial pre-approval review
(`spec-queue/tracks/reviews/B4-2026-09-24.md`, "Change 2").

The review found a **bypass**: `bash -c 'cp n $HOME'` is allowed today and stayed allowed under D2,
because a single-quoted `$` is `_LITERAL_DOLLAR`, which D2 excluded. The spec went further and made
that exclusion a requirement. The review also found:

- task 1.5's `$(dirname $PWD)` control could not pass;
- the PowerShell spellings `${env:N}`, `${HOME}`, `$variable:N` and `$global:N` were missing;
- a commit heredoc mentioning `$HOME` would be refused, a cost nobody had named.

The operator answered:

- **refuse a directory variable inside a quote handed to an inner shell**, accepting that
  `echo '$HOME'` and `grep '$HOME'` are refused;
- **extend the variable list** (`$HOMEPATH`, `$HOMEDRIVE`, `$PUBLIC`, `$OneDrive`, and the review's
  other candidates, each decided with a reason);
- add the PowerShell spellings;
- `$(dirname $PWD)` is now refused, which is accepted.

**R4 ran on 2026-09-24 (revise round).** It re-derived the change from `hub/hub/mcp_server.py` at
`b7d976a` (`_judge_word` rule 4, `_words`, `_lex`, `_expands`). It measured with `_decide`
in-process in `py -3.11`, in Git Bash 5.2.37 and in Windows PowerShell 5.1. The workspace held a
real junction `up` pointing outside. What changed:

- **D2:** the literal `$` now matches, and the list is extended, with a reason for each name. The
  PowerShell spellings are complete. A reference directly after a `:` in a value is matched too:
  `dd of=c:$HOMEPATH` is allowed today and lists home in Git Bash (measured).
- **D3:** a word that is `..` once its expansions are removed is refused. `$(true)..`, `$x..`,
  `.$x.` and an inner shell's `` `true`.. `` are all allowed today (measured), and each is `..`.
- **D10 (new):** a separator-less word naming a link is judged by where the link resolves.
  `cp n up`, `Copy-Item n up` and `cp -tup n` are all allowed today (measured), and each writes
  through the link. A separator-less glob is judged by its matches, using the sibling change's
  `_glob_links`: `cp n u*` is allowed today (measured).
- **Order:** this change now builds **after** `the-shell-judge-reads-a-word-whole`. It uses that
  change's `_glob_links`, its budget, its level-by-level escape reading (D7) and `_DRIVE_LETTERS`.

The record is in `spec-queue/tracks/B4.md`, under "R4".

**R5 ran on 2026-09-24 (independent verification)**, against the code at `8786289`, with `_decide`
in-process in `py -3.11` and real junctions `up` and `.l` pointing outside. It also approximated
the new rules over 42,860 Bash commands from this repository's own Claude Code transcripts. D2, D3
and D10 are sound as written: every "allowed today" row it re-measured is allowed today
(`bash -c 'cp n $HOME'`, `cp n $x..`, `cp -tup n`, `cp n u*`, `dd if=n of=c:$HOMEPATH`), and each
is caught by the step named for it.

**One cost was missing, and it is large.** It is D1 and D4's drive reading of a separator-less word
in bash on Windows. A single letter and a colon is common text: `except Exception as e:` and
`with open(p) as f:` in a Python heredoc or `py -c "…"`, `jq '{a: .x}'`, and `Plan A:` in a
message. Each is judged as a drive, and a drive that is not the workspace's is outside, **whether or
not it exists**: `_where("e:")` answers outside on a machine whose only drive is C (measured).
873 of the 42,860 commands (2.0%) hold such a word for a letter other than C. 510 of them hold a
heredoc. All are allowed today. See "Costs" and Open Question 3.

**Operator answers applied, 2026-09-24 afternoon** (`spec-queue/DECISIONS.md`, "the security
REVISING rounds"). Every open question is answered:

- **`B4-drive-exists`** (Open Question 3): on Windows, a one-letter word with a colon is judged as a
  drive **only when that drive exists**. D1 gains `_drive_exists`, and "Costs" is rewritten: the
  2.0% is gone.
- **`B4-dep-links`** (Open Question 2): build D10 as written. The residual is filed as **F444**
  (`scripts/drive/FINDINGS.md`), which must be fixed before a JavaScript project is registered.
- **`B4-residuals`**: this change builds after `the-shell-judge-reads-a-word-whole`, and both are
  built in one night window. That change's `case` arm and its four device names are accepted as
  recommended.

**R6 ran on 2026-09-24 (revise round, after the second pre-approval review,
`spec-queue/tracks/reviews/B4-2026-09-24-second.md`).** It re-derived D1, D2 and D10 from
`hub/hub/mcp_server.py` at `dd069ec`, and measured with `_lex`, `_words` and `_decide` in-process in
`py -3.11`, in Git Bash 5.2.37 and in Windows PowerShell 5.1, with real junctions in
`testbed/scratch/b4-r6/`. What changed:

- **D10 reaches a bracket glob.** Change 1's new D11 yields the bracket-kept word, so `cp n [u]p`
  and `cp n u[p]` reach D10 step 3 as globs (both wrote through `up` in Git Bash, measured). Without
  it, step 1 checked `lexists("u]p")`, which is False.
- **D2's PowerShell pattern needs `env:` for an environment name.** Only `HOME`, `PWD`, `PSHOME` and
  `PROFILE` are PowerShell variables of their own. Measured in PowerShell 5.1: `$TEMP`, `$TMP` and
  `$USERPROFILE` are empty, and `$tmp = New-TemporaryFile; Remove-Item $tmp` runs. R5's pattern
  refused that user variable, against the scenario "Any other bare expansion stands".
- **(R6, new) D2's bash pattern gains PowerShell's `env:` forms.** From the Bash tool,
  `powershell -c 'Copy-Item x $env:TEMP'` reaches rule 4 as `␀env:TEMP` (measured), which no bash
  spelling matched. It is the operator's inner-shell case one dialect over.
- **`Temp:` is read in the PowerShell dialect only** (the review's LOW; R6's choice, confirmed by
  the operator as `B4-temp-dialect`). Windows PowerShell 5.1 has no `Temp:` drive (measured), and in the bash
  reading `temp:` is ordinary text (a YAML key in a heredoc).
- **Named:** `$PWD.Path` and the other member accesses (Costs). `_DRIVE_LETTERS` is read at call
  time (change 1's D9).

The record is in `spec-queue/tracks/B4.md`, under "R6".

**R7 ran on 2026-09-24 (independent comparison of R6's fixes)**, against the code at `658332b`, with
`_lex`, `_words` and `_decide` in-process in `py -3.11` and real junctions in
`testbed/scratch/b4-r7/`. Each R6 fix is reached by the word it is for: `powershell -c 'Copy-Item x
$env:TEMP'` and `…${env:USERPROFILE}` from the Bash tool give `␀env:TEMP` and `␀{env:USERPROFILE`;
`$tmp = New-TemporaryFile; Remove-Item $tmp` gives `$tmp` twice; a heredoc's `temp: 5` gives `temp`;
`cp n [u]p` and `cp n u[p]` give `u]p` and `u[p`, so D10 needs change 1's D11. Each is allowed today
(measured). A glued or colon-joined bracket glob (`cp -t[u]p n`, `Copy-Item n -Destination:[u]p`)
keeps its brackets, because the bracket is not at the word's edge, and reaches D10 step 3 as the
option's value. No defect of this change's own. `B4-temp-dialect` is cited where R6 asked for it.

---

**Built on the recommended answer to D5** (*"How strict should the shell judge be about bare `$VAR` /
`$(…)`?"*): refuse a bare reference only where it names a directory by itself, the way rule 4
already refuses `~`, and leave every other bare expansion allowed. The operator took (d) on
2026-09-24 and widened it (see above). **Also built on D4's recommended answer** (the default posture
stays `workspace`), under which this judge decides every unattended run.

**R1, 2026-09-24**; functions are cited by name (line numbers drift).

## D5 — the options, with evidence

| Option | What it refuses | Cost | Verdict |
|---|---|---|---|
| (a) Accept the disclaimer; close F401 as documented | nothing new | `cp x $HOME` stays allowed while `cp x ~` is refused, the incoherence F375 removed for `..` | rejected: leaves the spec's own shorthand rule inconsistent |
| (b) Refuse every separator-less word with an expansion | `$HOME` and everything else | refuses `echo $x`, `for f in $files`, `test -n "$VAR"`, and **every commit** Claude Code makes: `git commit -m "$(cat <<'EOF' …)"` lexes to the single word `$(…)` (measured: `_words` yields `['git','commit','-m','$(…']`) | rejected: breaks the default posture |
| (c) Refuse a bare expansion only in a destination position of a known file tool | `cp x $DEST` | a command-aware layer in a judge that is deliberately word-based (`a-url-is-not-a-path` D1); defeated by `bash -c`, functions and aliases; large | rejected: cost out of proportion, and still incomplete |
| **(d) Refuse a bare reference to a directory variable, and a `..` that survives an expansion** | the list in D2; `..$x`, `$x..` | `echo $HOME`, `ls $PWD` and, after R4, `echo '$HOME'` are refused, as `echo ~` already is | **chosen** (operator, 2026-09-24) |

**Interaction with D4's card.** Under (d), `cp x $DEST` is still allowed, and today's allow reason
is *"inside your workspace"*. `an-ask-me-card-says-what-workspace-only-would-decide` makes that
reason say the command names values decided at run time; this change does not need it.

## Decisions

### D1 — A drive keeps its colon (F402)

`_words(arguments)` becomes `_words(arguments, dialect)`. In the PowerShell reading, and in the bash
reading on a host with drive letters (`_DRIVE_LETTERS`, the sibling change's D9, read at call time;
see D4 below), a piece is first trimmed of `_WORD_TRIM` less `:`. If that fullmatches
`_PS_DRIVE_RE = [A-Za-z]:[^:\\/]*`, or, **in the PowerShell reading only (R6)**,
`(?i)temp:[^:\\/]*`, it is the word, colon kept. Otherwise the existing trim applies. Rule 4 then checks, before its option handling:

- `[A-Za-z]:…` → `_judge_path(word, root, word, argument, continues)`, **on a drive-letter host
  only when `_drive_exists(letter)`** (below). `_where` gives Windows' answer. Measured:
  `_where("Z:")` → outside; `_where("C:")` and `_where("C:foo")` → inside for a workspace on C. On
  a POSIX host (pwsh on Linux) no probe is made: `Z:` goes to `_judge_path` as before and resolves
  as a file name inside, which is what pwsh does with it.
- `Temp:…` → `_judge_path(os.path.join(tempfile.gettempdir(), rest), …)`, quoting the word.
  `gettempdir` can raise when no temporary directory is usable, so it is wrapped and becomes
  `_UNRESOLVED`.
- **(R6) `Temp:` is the PowerShell dialect's only.** `Temp:` is a drive of PowerShell 7's
  FileSystem provider. Windows PowerShell 5.1 has none (measured: `Get-PSDrive Temp` fails), no
  native program reads `Temp:` as a directory, and msys does not. In the bash reading on a Windows
  host, R5's rule refused ordinary text: a heredoc line `temp: 5` gives the word `temp:` (measured:
  today `_words` yields `temp`), which would have been refused as the temporary directory. So the
  bash reading does not keep the colon of `temp:`. What this leaves is a named residual: from the
  Bash tool, `pwsh -c 'Copy-Item x Temp:'` is allowed, today and after. **(Operator,
  `B4-temp-dialect`)** Confirmed: `Temp:` is a drive in the PowerShell dialect only, and the
  residual is accepted. Rejected: both dialects.
- A colon-joined option value (`_COLON_OPTION_RE`) is read with its colon kept, so
  `-Destination:Z:` judges `Z:`. **(R2)** The trim rule alone does not do this. `_words` turns
  `-Destination:Z:` into `-Destination:Z`, so the trim must also keep the colon when the piece,
  trimmed of `_WORD_TRIM` less `:`, is `_COLON_OPTION_RE` followed by a `_PS_DRIVE_RE` fullmatch.
- **(R2)** With a separator after the drive (`Z:foo\bar`) the word is not rule 4's. The sibling
  change's D2 step 3 keeps it refused by not breaking at a drive colon on a drive-letter host. The
  two changes agree on one meaning of `Z:` per platform.

`s:a:b` (a second colon) and `HEAD:README.md` (more than one letter, not `Temp`) do not match and
stand.

**(R5) A drive word judged inside does not end rule 4.** The drive check returns only a refusal; on
the workspace's own drive it passes the word on to the checks below. On Windows, with the workspace
on C, `dd if=n of=c:$HOMEPATH` gives the word `c:$HOMEPATH`, which matches `_PS_DRIVE_RE` and
resolves inside as `c:` plus a name. Only D2's check after a colon refuses it. Task 1.4c's row
catches an early return on the Windows job. **(Operator)** The same holds for a drive word skipped
because its drive does not exist: the check yields no answer and the checks below still run.

#### (Operator, `B4-drive-exists`) A drive word is judged only when the drive exists

On a drive-letter host (`_DRIVE_LETTERS`), in both dialects, a separator-less word or option value
matching `_PS_DRIVE_RE` is judged as a drive only when `_drive_exists(letter)` answers True.
Otherwise the drive check yields nothing and rule 4 goes on (D2, D3, D4's `~` after a colon, D10).
D10's link check still skips such a word, because `os.path.join(root, "e:x")` discards the root and
a drive that does not exist has no entries.

R5 measured the unconditional rule refusing 873 of 42,860 Bash commands in this repository's
transcripts (2.0%): `except … as e:`, `with … as f:`, `jq '{a: .x}'`, `Plan A:`. A drive that does
not exist cannot be written to, so refusing its letter guards nothing.

**`_drive_exists(letter)`** is `os.path.exists(letter + ":\\")`, wrapped, with one deliberate
difference. Bare `os.path.exists` (`genericpath.exists` on 3.11) catches **every** `OSError` and
`ValueError` and answers False. Used bare, a drive that exists but cannot be read would count as
absent and its word would be allowed: a drive whose root denies access, a network drive whose
server is unreachable, or a card reader that is not ready. That is an allow of a word that may name
a real drive outside. So the wrapper calls `os.stat(letter + ":\\")` and reads the outcome as
follows:

| Outcome | Counts as | Why |
|---|---|---|
| returns | exists | the drive is there |
| `FileNotFoundError` | **absent** | measured: `os.stat("E:\\")`, `"A:\\"` and `"Z:\\"` on this machine (drive C only) each raise `FileNotFoundError` (errno 2, winerror 3) |
| any other `OSError` (`PermissionError`, a not-ready or network error), `ValueError`, or any other exception | **exists** | fail closed. The word goes on to `_judge_path`. On another drive `_where` answers outside, or `_UNRESOLVED` if `realpath` raises, and the call is refused |

**A raise counts as "exists".** The two errors are not symmetric. Counting a raise as absent can
allow a word naming a real, reachable drive outside the workspace. Counting it as existing costs a
false refusal of one word, on a machine with an unusual drive, and the reason names the word.

The answer is memoized once per letter per `_decide`, in the sibling change's per-`_decide` memo. It
is looked up only for a word that already matches `_PS_DRIVE_RE`. Cost (measured, `py -3.11`): 1.8
µs for a letter with no drive, 14.6 µs for `C:\`. A `stat` of an unreachable mapped network drive
can block for the system's network timeout. That is a latency cost, and the answer is still
"exists".

**What this leaves (named in "Costs"):** a word whose letter names a drive that exists but that no
command means, such as a removable card, a USB stick, a second disk or a mapped drive, is still
refused as that drive. A drive that appears between the judgement and the run, for example a stick
plugged in or a drive mapped by an earlier command in the same call, is not seen. A same-command
`subst e: ..` or `net use e: \\host\share` names its target as a path, and that path is judged.

**The `c:$HOMEPATH` family stays refused.** C exists wherever the workspace is on C, so `c:` is
judged and found inside, and D2's check after the colon refuses the word. If the workspace is on
another drive, the drive check refuses it as outside. `e:$HOMEPATH`, with drive E absent, is not
judged as a drive, and D2's check after the colon refuses it. D2 and D3 never consult the probe.

**Words with a separator are unchanged.** `Z:foo\bar` is not rule 4's. The sibling change's D2 judges
it as a path whether or not Z exists. R5 counted only separator-less words, and this change makes no
claim about the others.

### D2 — A directory variable, referenced by itself, is uncheckable (F401)

In rule 4, after the `~` check, on the **value** (the whole word, an option's colon-joined value,
or a glued short option's value), a directory-variable reference is looked for at two places:

- **the start of the value;**
- **(R4) directly after each `:` in it.** Git Bash expands `of=c:$HOMEPATH` to `of=c:\Users\huida`
  (measured), and `ls -d c:$HOMEPATH` lists the home directory (measured). `dd if=n of=c:$HOMEPATH`
  is allowed today (measured). This is the variable counterpart of D4's tilde after a colon.

The reference must **not be followed by a name character** (R2). So `$HOME.bak` and `$PWD..`,
siblings of home and of the workspace, are refused, while `$HOMEDIR` stands. A match is refused as
`_UNCHECKED`, the reason rule 3 already gives.

**Spellings (R4: complete).**

| Dialect | Pattern (NAME from the list below) | Case |
|---|---|---|
| bash | `[$␀]NAME` and `[$␀]\{NAME` followed by `}`, a non-name character, or the end (`${HOME-x}`, `${HOME:+y}`); `_words` trims the closing `}`, so `${HOME}` reaches the judge as `${HOME` | a POSIX name exactly (`HOME`); a Windows name in its Windows spelling or all capitals (`OneDrive`, `ONEDRIVE`), because msys keeps some names' case and capitalises others: Git Bash here shows `ProgramData`, `OneDrive` and `CommonProgramW6432` as spelled, and `PROGRAMFILES`, `SYSTEMROOT`, `WINDIR`, `SYSTEMDRIVE` in capitals (measured). A lowercase user variable such as `$tmp` is not matched |
| PowerShell | **(R6)** `[$␀]\{?env:NAME`, for every NAME; and `[$␀]\{?(?:(?:variable\|global\|local\|script\|private\|using):)?AUTO`, where AUTO is one of PowerShell's own `HOME`, `PWD`, `PSHOME`, `PROFILE` | any case |
| bash, also (R6) | `[$␀]\{?env:NAME`, PowerShell's environment spelling, handed to a nested PowerShell | any case |
| either | `%NAME%` (a nested `cmd`) | any case |

`␀` stands for `_LITERAL_DOLLAR`.

**(R6) Why PowerShell needs `env:` for an environment name.** R4's PowerShell pattern made the scope
prefix optional for every name. But in PowerShell a bare `$TEMP` is a variable of the script, not
the environment: measured in PowerShell 5.1, `$TEMP`, `$TMP` and `$USERPROFILE` are empty, and
`$env:TEMP` is the temporary directory. Only `HOME`, `PWD`, `PSHOME` and `PROFILE` are PowerShell's
own automatic variables. So R5 as written would refuse `$tmp = New-TemporaryFile; Remove-Item $tmp`
in the PowerShell tool (measured: that command runs, and is allowed today), a user variable the
scenario "Any other bare expansion stands" says SHALL stand.

**(R6) Why the bash reading also matches `env:`.** From the Bash tool,
`powershell -c 'Copy-Item x $env:TEMP'` lexes to the word `␀env:TEMP`, and
`powershell -c 'Copy-Item x ${env:USERPROFILE}'` to `␀{env:USERPROFILE` (measured). No bash spelling
matched either, and D2's check after a colon finds `TEMP`, not a reference. Both are allowed today,
and would have stayed allowed after R5, although the operator decided that a directory variable
handed to an inner shell is refused. In bash itself `$env:TEMP` is the variable `env` followed by
`:TEMP`, which no one writes for any other reason. The PowerShell automatic names need no bash
addition: `$HOME` and `$PWD` are already bash's own, and `$PSHOME` and `$PROFILE` match as the list
spells them (the Windows-spelling rule).

**(R4) A quoted or escaped `$` matches too.** R1 to R3 excluded `_LITERAL_DOLLAR`, on the argument
that a quoted reference is text. But a quoted reference is exactly what an inner shell expands:

- `bash -c 'cp n $HOME'` is allowed today, from both the Bash tool and the PowerShell tool (the
  review measured this);
- so is `sh -c "cp n \$HOME"` (measured);
- so is `powershell -c 'Copy-Item x $HOME'` sent from the Bash tool (measured).

The judge cannot tell text from a command handed on, and rule 3 already counts a literal `$` for a
word with a separator (`_expands`). So D2 matches both, as the operator decided. Deeper quoting is
covered by the sibling change's level-by-level escape reading (its D7), which judges each level as a
word through all rules:

- `bash -c 'bash -c "cp n \$HOME"'` gives the word `\$HOME` (with a literal `$`), and its level 1
  is `$HOME`. On POSIX this reaches rule 4 only through that reading, because `\` is not a separator
  there. On Windows rule 3 refuses it today, because `\` is a separator.
- `${env:TEMP}` inside quotes becomes `␀{env:TEMP`, and the `\{?` and `env:` in the pattern match
  it.

**The list (R4: extended; each with its reason).** The criterion: a variable that the shell, the
PowerShell host or the platform sets **for every process**, whose value is **one directory** (or
one file, for `$PROFILE`, or one drive for `HOMEDRIVE` and `SystemDrive`).

| Name | Kept, and why |
|---|---|
| `HOME`, `USERPROFILE`, `HOMEPATH` | the home directory. `HOMEPATH` is `\Users\huida`, a root-relative path on the current drive (measured) |
| `HOMEDRIVE`, `SystemDrive` | a drive by itself (`C:`, measured). A literal `C:` is judged by D1, but the variable's value is unknown, so it is uncheckable. `$HOMEDRIVE$HOMEPATH` begins with a reference and is refused by that |
| `PWD`, `OLDPWD`, and cmd's `%CD%` | the current and previous working directory: `~+` and `~-`, which F375 refuses |
| `TMPDIR`, `TMP`, `TEMP` | the temporary directory, shared by every process of the user |
| `APPDATA`, `LOCALAPPDATA` | per-user application data under home |
| `PUBLIC` | `C:\Users\Public`, writable by every user (measured present) |
| `OneDrive`, `OneDriveConsumer`, `OneDriveCommercial` | a synced folder under home: a write there leaves the machine (`OneDrive`, `OneDriveConsumer` measured present) |
| `ProgramData`, `ALLUSERSPROFILE` | `C:\ProgramData`, the machine-wide data directory. Ordinary users can create files there, and a write persists for every user (both measured present) |
| `SystemRoot`, `windir` | `C:\Windows`. Normally not writable without elevation, but it is one directory outside by itself, and no ordinary word collides (`$SYSTEMROOT`, `$WINDIR` measured) |
| `ProgramFiles`, `ProgramW6432`, `CommonProgramFiles`, `CommonProgramW6432` | install directories, one directory each (measured present). PowerShell's `${env:ProgramFiles(x86)}` begins with `${env:ProgramFiles` followed by `(`, so it matches |
| `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, `XDG_CACHE_HOME`, `XDG_STATE_HOME`, `XDG_RUNTIME_DIR` | on Linux, a directory under home, or the per-user runtime directory, when set |
| PowerShell `$HOME`, `$PWD`, `$PSHOME`, `$PROFILE` | automatic variables: home, the location, PowerShell's install directory, and the profile *file* under Documents (`Add-Content $PROFILE …` writes outside) |

**Left out, with reasons.** `XDG_DATA_DIRS` and `XDG_CONFIG_DIRS` are colon-separated lists, not a
directory, and a program given one opens a path that does not exist. Tool-specific variables
(`VIRTUAL_ENV`, `JAVA_HOME`, `GOPATH`, `CARGO_HOME`, `NVM_DIR`, Git Bash's `EXEPATH`) and user
variables are open-ended: they are the named residual, and the requirement says they are not judged.

**Measured words** (`_lex` + `_words`):

- `"$HOME"` → `$HOME`;
- `${HOME}` → `${HOME`;
- `--target-directory=$HOME` → `$HOME`;
- PowerShell `-Destination:$HOME` → one word `-Destination:$HOME` (the colon form);
- `$env:TEMP` → `$env:TEMP`;
- `'$HOME'` → `␀HOME`.

Today these are allowed (measured): `Copy-Item x ${env:TEMP}`, `${HOME}`, `$variable:HOME`,
`$global:HOME`, `$env:HOMEDRIVE$env:HOMEPATH`, `$PROFILE`, `$PSHOME`; bash `$HOMEPATH`,
`$HOMEDRIVE$HOMEPATH`, `$PUBLIC`, `$OneDrive`, `$XDG_CONFIG_HOME`.

### D3 — A `..` that survives an expansion is uncheckable

Two checks in rule 4, on the value:

- **R1:** the text before its first expansion is exactly `..` (`..$x`, `..${x}`, `..$(…)`).
- **(R4):** with every expansion removed, the text is exactly `..`. An unset variable and a
  substitution printing nothing leave the rest in place, so `$(true)..`, `$x..`, `.$x.` and an inner
  shell's `` `true`.. `` all name the parent. Git Bash prints `..` for each, with `x` unset
  (measured). PowerShell, with `$x = $null`, passes `..` for `$x..` (measured). The judge allows
  all of these today (measured).

"Expansion" means each of these:

- the `_SUBSTITUTION` marker (outer `$(…)` and backticks);
- `[$␀]NAME`;
- `[$␀]\{…\}`, with the closing `}` optional, since `_words` trims it;
- `[$␀]` followed by a digit or one of `@*#?$!-`;
- a backtick-delimited span left literal for an inner shell;
- `%NAME%`.

The text is cut at a NUL first. `..` before a separator is rule 3's. Cost: none measured. No
ordinary word is `..` around an expansion.

### D4 (R3) — the drive and the tilde, per platform; a glob beginning with `..`

- **The drive reading is keyed on the platform** (`_DRIVE_LETTERS`), not only the dialect, and
  (operator) on the drive existing (D1, `_drive_exists`). On a
  Windows host a Bash-tool word reaches native programs and nested PowerShell
  (`powershell -c 'Copy-Item x Z:'`, `python w.py Z:`; both allowed today, measured at `b66f6a6`).
  Git Bash's own `cp x Z:` writing a file named `Z:` becomes a harmless false refusal. On POSIX,
  bash is unchanged.
- **`~` after a colon.** Bash expands a tilde prefix after `:` in an assignment-shaped argument
  (measured: `echo of=c:~/y` prints `of=c:/c/Users/huida/y`). So the `~` check also applies to the
  text after each `:` in the value (`_TILDE_PREFIX_RE.fullmatch`), refused as `_UNCHECKED`. Cost:
  `git show HEAD:~`.
- **A separator-less glob beginning with `..`.** A value that begins with `..`, holds `*`, `?` or
  `[`, and satisfies `fnmatch.fnmatchcase("..", value)` is judged as `..`. This is the sibling
  change's D3 applied to rule 4. **`.*` and `.?` are not rewritten to `..`** when separator-less:
  they are as often a quoted regular expression (`grep '.*' f`). **(R4)** They are still judged by
  their matches (D10).

### D10 (R4) — a separator-less word that names a link, or a glob that matches one

Rule 4's premise is that "a word with no path separator usually names an entry of the directory the
shell runs in, so it cannot leave the workspace". **It is false for a link.** A junction `up` in the
workspace points outside, and these are all allowed today (measured):

- `cp n up`;
- `Copy-Item n up`;
- `cp -tup n`: Git Bash's `cp -t up n` copies into `up`;
- `cp n u*`;
- `cp n {up,x}`, once braces are expanded.

Each writes through the link. The main spec's "Traversal and links cannot escape" is false for them
today. The sibling change states the shell scope of that requirement. This change makes rule 4
honour it for a word with no separator.

After D1 to D4, and before rule 4 answers None, the value is checked, cut at a NUL:

1. **A name.** If the value holds no glob character (and no `:` on a drive-letter host, where D1
   owns the colon), and `os.path.lexists(os.path.join(root, value))`, it is judged by
   `_judge_path(value, root, word, argument, continues)`. `_where` resolves the link, and
   `_resolves_elsewhere` names where it lands. An entry that exists and is not a link resolves to
   itself, inside.
2. **A glued short option.** For a glued short option run (`-tup`, whose greedy reading leaves no
   value), each suffix of the run after its first letter (`up`, `p`) is checked as in step 1. Which
   letters take a value is the program's business (F375 D7), and a suffix that is not an entry costs
   one `lexists`.
3. **A glob.** A value holding a glob character goes through the sibling change's
   `_glob_links(value, root, budget)`. So `cp n u*` and `ls -d .*` are judged by the links they
   match. The latter is refused only where a dot-named link out of the workspace exists (a linked
   `.venv`).

**(R6) A bracket glob reaches step 3 through the sibling's bracket-kept word.** `_words` trims `[`
and `]` from a word's ends, so `cp n [u]p` and `cp n u[p]` give the words `u]p` and `u[p`
(measured). `u]p` holds no glob character, so step 1 checks `lexists("u]p")`, which is False. `u[p`
reaches step 3, but `fnmatch` reads a lone `[` literally and matches nothing. Both wrote `n` through
`up` in Git Bash (measured), and both would have stayed allowed, making this change's own SHALL
false. The sibling change's D11 also yields the bracket-kept words `[u]p` and `u[p]`, which reach
step 3 as globs. Their relaxed patterns `*p` and `u*` match `up`, which is judged outside.

**Cost.** One `lexists` per separator-less word: 10 µs when the entry does not exist, 18 µs when it
does (measured). Plus one `realpath` per word that names an entry, and the glob listings, which are
charged to the sibling change's per-`_decide` budget. **What it refuses:** a bare mention of a link
out of the workspace. In a worktree whose `node_modules`, `.venv` or `venv` is the Hub's shared link
to the project checkout (`worktrees.py`, `_symlink_shared_dependencies`), that is `ls node_modules`,
`rm -rf node_modules` and `grep -r foo --exclude-dir=node_modules .`. The last is allowed today
(measured) and would be refused there. Every path *through* such a link is refused today already. No
project worktree on this machine has such a link now (checked read-only), so nothing measured moves.
Open Question 2, answered (`B4-dep-links`): filed as F444.

### Totality

What rule 4 now does is all total, or wrapped:

- regex matches and slices;
- `tempfile.gettempdir`, wrapped;
- `_drive_exists`, which never raises: any failure other than `FileNotFoundError` answers True;
- `os.path.lexists`, which returns False on `OSError`/`ValueError`;
- `_judge_path`, which is total;
- the sibling change's `_glob_links`, which is total and bounded.

No route changes. `approve_tool_call` returns `_decide`'s answer, and after the sibling change's D6
a raising judge is a reported deny.

## Costs the operator accepts (R4)

Named in full, because they fall on ordinary work:

- `echo '$HOME'`, `grep '$HOME' f`, `git commit -m 'use $HOME'` and `printf '%s' "\$PWD"` are
  refused. The judge cannot tell a quoted reference that is text from one handed to an inner shell.
- **A commit or PR heredoc** whose body has a directory variable as a word (`$HOME`, `$PWD`,
  `$TEMP`…) is refused, because the heredoc body is lexed unquoted. This repository's own commit
  messages will hit it. The way round is to write the message to a file and use `git commit -F`.
  The commit heredoc itself, with no such word, stands.
- `echo $PWD`, `cd $OLDPWD`, `ls $TMPDIR` and `cp x $(dirname $PWD)` are refused. The last names
  the parent, and the operator accepted it. Its nested text `dirname $PWD` has the word `$PWD`.
- `git show a:README.md` in PowerShell, and in bash on Windows (a one-letter revision), is refused
  as drive A **where drive A exists** (operator, `B4-drive-exists`). Elsewhere it stands.
- **(Operator, `B4-drive-exists`) A one-letter word with a colon, on Windows, whose letter names a
  drive that exists and is not the workspace's.** R5's measured 2.0% (873 of 42,860 Bash commands:
  `as e:`, `as f:`, `jq '{a: .x, b: .y}' f`, `Plan A:`) is gone. It came from letters with no drive,
  which are now ordinary words. What remains is a letter naming a drive that exists but that the
  command does not mean: a removable card or USB stick, a second disk, a DVD drive, or a mapped
  network drive. There, `except … as d:` or a YAML key `d:` is refused as drive D. R5 counted 30
  `d:` words in the 42,860 commands. On this machine (drive C only) the measured cost is none. A
  drive whose probe fails other than by "not found" counts as existing (D1), so a not-ready card
  reader refuses its letter too. On the `hub-judge-windows` runner, drives C and D normally exist,
  so tests pin the probe (task 1.5c) rather than depend on the runner's drives.
- (R5, measured) 33 of the 42,860 commands name a directory variable as a word, most often
  `cd "$TMPDIR"` and `echo "… $TEMP"`. That is the cost the operator accepted, counted.
- (R4) In a worktree with a linked dependency directory, a bare mention of it is refused (D10).
  **(R5)** So is a bare `*` when the link's name has no leading dot (`node_modules`, `venv`):
  `ls *`, `grep foo *`, `du -sh *`. 595 of the 42,860 commands had a bare `*` word. No worktree on
  this machine holds such a link now. **(Operator, `B4-dep-links`)** Accepted and filed as **F444**
  (`scripts/drive/FINDINGS.md`), which must be fixed before a JavaScript project is registered.

- **(R6) A PowerShell member access on a directory variable.** In PowerShell a `.` after a
  reference is member access, and `.` is not a name character, so `$PWD.Path`, `$HOME.Length` and
  `$PROFILE.CurrentUserAllHosts` are refused. `$PWD.Path` is the idiomatic way to get the current
  directory (measured: it prints the location), so it names the same directory `$PWD` does, within
  the operator's accepted `$PWD` cost. `$HOME.Length` names no directory and is a false refusal.

## Residuals, named

- **A user or tool variable naming a directory** (`D=/tmp; cp x $D`, `$VIRTUAL_ENV`, `${!ref}`),
  and a computed one (`$(mktemp -d)`, `(Resolve-Path ~)`). Such a variable is not judged, and the
  requirement says so.
- **(R6) PowerShell 7's `Temp:` handed on from the Bash tool** (`pwsh -c 'Copy-Item x Temp:'`),
  allowed today and after (D1).
- **PowerShell drives that are not filesystem locations** (`Env:`, `Function:`, `HKLM:`…) and
  drives created by `New-PSDrive` in an earlier call.

## Open questions

All answered. The operator answered R4's and R5's list (`spec-queue/tracks/B4.md`, R5, "Left for the
operator", questions 1 to 5) on 2026-09-24 afternoon, in `spec-queue/DECISIONS.md`.

1. **Answered 2026-09-24:** D5 is (d), widened as above. `PWD` is included.
2. **Answered (`B4-dep-links`): the linked dependency directories (D10's cost). Build D10 as
   written.** The residual is filed as **F444** (`scripts/drive/FINDINGS.md`): the Hub's
   shared-dependency links (`node_modules`, `.venv`, `venv`) make every path, glob and bare name
   through them outside, including a bare `*` in a JavaScript worktree. **F444 must be fixed before a
   JavaScript project is registered.** Its fix belongs to the boundary, for example treating the
   Hub's own links as read-only inside, or provisioning without links. Exempting the bare names alone
   would refuse `ls node_modules/x` and allow `ls node_modules`, the incoherence F375 removed for
   `..`. Rejected: folding a read-through exemption into these changes now.
3. **Answered (`B4-drive-exists`): a one-letter word with a colon, on Windows (D1, D4).** It is
   judged as a drive only when that drive exists (D1, `_drive_exists`). Any probe failure other than
   `FileNotFoundError` counts as existing. Rejected: keeping the rule and accepting 2.0%, and dropping
   the bash reading on Windows, which reopens `python w.py Z:` and `c:$HOMEPATH`-style words.
4. **Answered (`B4-residuals`): build order.** This change builds after
   `the-shell-judge-reads-a-word-whole`, and both are built in one night window.
5. **Answered (`B4-residuals`), the sibling change's questions:** its `case`-arm residual stays, and
   its four device names stay exempt, accepting the inner-PowerShell `> /dev/null` residual. Neither
   bears on this change's rules.
6. **Answered (`B4-temp-dialect`), R6's `Temp:` choice.** `Temp:` is a drive in the PowerShell
   dialect only (D1). In bash, `temp:` is ordinary text. The residual, `pwsh -c '…Temp:'` sent from
   the Bash tool, is accepted. Rejected: both dialects.
