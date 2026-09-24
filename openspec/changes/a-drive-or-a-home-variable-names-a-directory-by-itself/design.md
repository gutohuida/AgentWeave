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
reading on a host with drive letters (`_DRIVE_LETTERS`, the sibling change's D9; see D4 below), a
piece is first trimmed of `_WORD_TRIM` less `:`. If that fullmatches
`_PS_DRIVE_RE = [A-Za-z]:[^:\\/]*` or `(?i)temp:[^:\\/]*`, it is the word, colon kept. Otherwise the
existing trim applies. Rule 4 then checks, before its option handling:

- `[A-Za-z]:…` → `_judge_path(word, root, word, argument, continues)`. `_where` gives Windows'
  answer. Measured: `_where("Z:")` → outside; `_where("C:")` and `_where("C:foo")` → inside for a
  workspace on C. On a POSIX host (pwsh on Linux) `Z:` resolves as a file name inside, which is
  what pwsh does with it.
- `Temp:…` → `_judge_path(os.path.join(tempfile.gettempdir(), rest), …)`, quoting the word.
  `gettempdir` can raise when no temporary directory is usable, so it is wrapped and becomes
  `_UNRESOLVED`.
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
catches an early return on the Windows job.

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
| PowerShell | `[$␀]\{?(?:(?:env\|variable\|global\|local\|script\|private\|using):)?NAME` | any case |
| either | `%NAME%` (a nested `cmd`) | any case |

`␀` stands for `_LITERAL_DOLLAR`.

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

- **The drive reading is keyed on the platform** (`_DRIVE_LETTERS`), not only the dialect. On a
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

**Cost.** One `lexists` per separator-less word: 10 µs when the entry does not exist, 18 µs when it
does (measured). Plus one `realpath` per word that names an entry, and the glob listings, which are
charged to the sibling change's per-`_decide` budget. **What it refuses:** a bare mention of a link
out of the workspace. In a worktree whose `node_modules`, `.venv` or `venv` is the Hub's shared link
to the project checkout (`worktrees.py`, `_symlink_shared_dependencies`), that is `ls node_modules`,
`rm -rf node_modules` and `grep -r foo --exclude-dir=node_modules .`. The last is allowed today
(measured) and would be refused there. Every path *through* such a link is refused today already. No
project worktree on this machine has such a link now (checked read-only), so nothing measured moves.
Open Question 2.

### Totality

What rule 4 now does is all total, or wrapped:

- regex matches and slices;
- `tempfile.gettempdir`, wrapped;
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
  as drive A.
- **(R5, measured) Any word that is one letter and a colon, on Windows, in either dialect**, unless
  the letter is the workspace's drive. That is Python in a heredoc or a `-c` string
  (`except Exception as e:`, `with open(p) as f:`, `for k in d:`, `lambda x:`), a one-letter JSON,
  jq or YAML key (`jq '{a: .x, b: .y}' f`, `cat > c.yml <<EOF` with `x: 1`), and prose
  (`Plan A:`). **873 of 42,860 Bash commands (2.0%)** in this repository's own transcripts hold such
  a word (the most frequent words: `e:` 153 times, `f:` 134, `A:` 83, `t:` 75, `s:` 73). 510 of them hold a
  heredoc. All are allowed today. **The sibling change's own control `jq '{a: .x, b: .y}' f` (its
  task 1.3) would fail on the `hub-judge-windows` job** once this change is built as written. The
  PowerShell dialect has the same cost for a PowerShell-tool command carrying such a script. Open
  Question 3.
- (R5, measured) 33 of the 42,860 commands name a directory variable as a word, most often
  `cd "$TMPDIR"` and `echo "… $TEMP"`. That is the cost the operator accepted, counted.
- (R4) In a worktree with a linked dependency directory, a bare mention of it is refused (D10).
  **(R5)** So is a bare `*` when the link's name has no leading dot (`node_modules`, `venv`):
  `ls *`, `grep foo *`, `du -sh *`. 595 of the 42,860 commands had a bare `*` word. No worktree on
  this machine holds such a link now.

## Residuals, named

- **A user or tool variable naming a directory** (`D=/tmp; cp x $D`, `$VIRTUAL_ENV`, `${!ref}`),
  and a computed one (`$(mktemp -d)`, `(Resolve-Path ~)`). Such a variable is not judged, and the
  requirement says so.
- **PowerShell drives that are not filesystem locations** (`Env:`, `Function:`, `HKLM:`…) and
  drives created by `New-PSDrive` in an earlier call.

## Open questions

1. **Resolved by the operator on 2026-09-24:** D5 is (d), widened as above. `PWD` is included.
2. **The linked dependency directories (D10's cost).** Recommended: **build D10 as written, and file
   a finding** that the Hub's shared-dependency links make every path through them outside. Its fix
   belongs to the boundary: for example, treating the Hub's own links as read-only inside, or
   provisioning without links. Exempting the bare names alone would refuse `ls node_modules/x` and
   allow `ls node_modules`, which is the incoherence F375 removed for `..`. (R5) The cost includes
   a bare `*` in a JavaScript worktree (see "Costs"). The recommendation stands while no worktree
   holds such a link. If a JavaScript project is registered before the finding is fixed, the fix
   should come first.
3. **(R5) A one-letter word with a colon, on Windows (D1, D4).** As written, 2.0% of this
   repository's own Bash commands are refused, mostly Python's `as e:` and `as f:` (see "Costs").
   **Recommended: judge a separator-less drive word only when that drive exists**
   (`os.path.exists("Z:\\")`, wrapped, looked up once per letter per `_decide`), in both dialects.
   A drive that does not exist cannot be written to, so refusing it guards nothing. On this machine
   (drive C only) the measured cost falls to none, because `c:` is the workspace's own drive and
   inside. `Z:` stays refused wherever Z is a real or mapped drive. What remains: on a machine with
   a second drive D, a `d:` word (30 occurrences in the 42,860 commands). A drive mapped by `subst` or
   `net use` in an earlier call is seen, because it exists by then. One mapped in the same command
   names its target as a path, which is judged. The spec sentence would read "…names that drive's
   current location, and, where that drive exists, SHALL be judged by where it resolves".
   The alternatives:
   - **Keep the rule as written**, and accept the 2.0%.
   - **Drop the bash reading on Windows**, and keep R2's PowerShell-only rule. Then
     `python w.py Z:` and `powershell -c 'Copy-Item x Z:'` from the Bash tool stay allowed, as they
     are today. The PowerShell tool keeps the cost for scripts it carries.
