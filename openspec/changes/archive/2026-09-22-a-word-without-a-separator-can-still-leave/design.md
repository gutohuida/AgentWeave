# Design — a word without a separator can still leave

**R1, 2026-09-21.** Every file:line below was read in this round, and every "measured" row was run
this session. Decisions were measured in two ways: by calling `hub.mcp_server._decide` in-process
with `AW_WORKSPACE_DIR` set to a scratch `ws/` directory, and by running the real command in Git Bash
5.2.37 (msys) and Windows PowerShell 5.1 inside that directory.

**R2, 2026-09-21.** Re-derived independently; corrections are marked R2-n in place and listed in the
round log. R2 measured with the same two methods, plus a third: the judge's eight test files run
with the proposed rule 4 swapped in (a pytest plugin in the session scratchpad that replaces
`hub.mcp_server._judge_word` after collection; no repo file was edited).

**R3, 2026-09-21.** Re-derived independently; corrections are marked R3-n in place and listed in the
round log. R3 measured the same ways, except that the proposed rule 4 was patched into a scratch copy
of the whole `hub` package and `hub/tests`, so the tests that spawn `mcp_server.py` as a process
also ran it (a plugin that swaps `_judge_word` in-process cannot reach those).

## Context

The shell-command judge reads a command in the tool's dialect and judges each word by the first of
six rules that matches it:

- `_read_command` (`hub/hub/mcp_server.py:1403-1435`) splits the command into words with `_words`
  (`:1385-1400`).
- `_judge_word` (`:1141-1167`) applies the rules.
- Rule 4 (`:1158`) returns `None`, meaning "may stand", for any word without a separator.
- `_SEPARATORS` is platform-based, not dialect-based (`:953`): `/` on POSIX, `/\` on Windows.
- Rule 3 (uncheckable: `$`, a leading `~`, `%VAR%`) is gated on `has_separator` (`:1156`).
- Rule 5 (a resolved path) and rule 6 (the backstop) are reached only after rule 4, so they are
  gated too.

`_where` (`:1034-1054`) joins a relative word to the root, takes `realpath`, and compares the result
with `commonpath`. It is already total: `OSError` and `ValueError` become `_UNRESOLVED` or
`_OUTSIDE`. `_judge_path` (`:1057-1073`) wraps it with the `continues` extension check.

Measured today, with the workspace `…/f375/ws` and its parent `…/f375`:

| Word or command | `_decide` today | Real landing |
|---|---|---|
| `cp notes.md ..` (Bash / PowerShell) | allow | parent (both shells) |
| `cp notes.md '..'`, `."".` | allow | parent (R2-3: R1 wrote `.""."`, an unbalanced quote bash refuses to parse) |
| `--target-directory=..` | allow | parent |
| `$'..\x00x'` | allow | parent (Git Bash: the copy appeared in `f375/`) |
| `cp notes.md ~`, `~root`, `~-` (Bash); `Copy-Item notes.md ~` | allow | `~`: home (PowerShell: appeared in `$HOME`). R2-4: `~root` stays literal in this Git Bash, which has no user `root` (`echo ~root` printed `~root`); it names `/root` on Linux. `~-` is `OLDPWD`, which the shell inherits (it printed the repo directory) |
| `cp notes.md ../` | **deny, outside** | parent |
| `cp notes.md $HOME`, `cp notes.md $(dirname $PWD)` | allow | home / parent (non-goal, D5) |
| `Copy-Item notes.md Z:` | allow (judged word is `Z`, the colon is trimmed) | drive Z's current directory (non-goal, D6) |
| `cp notes.md ...` / `'.. '` / `C:` (Git Bash) | allow | a **file** with that name inside `ws/` |
| `Copy-Item notes.md ...` / `'.. '` (PowerShell) | allow | error: "Could not find a part of the path" |
| `git log HEAD~1`, `echo a,..` | allow | not a path (after this change `echo a,..` is refused: `_words` splits at the comma; see Risks) |
| `cp -t.. notes.md` (R2) | allow | parent (Git Bash: the copy appeared in the parent) |
| `tar -C.. -xf a.tar` (R2) | allow | not run; `-C` takes its directory glued on, as `-t` does |
| `Copy-Item notes.md -Destination:..` (R2) | allow | parent (PowerShell 5.1.26100: appeared in the parent) |
| `Copy-Item notes.md -Destination:~\x.md` (R2) | **deny**, `'\x.md'` outside, by rule 6's backstop | home (appeared in `$HOME`); `-Destination:~` with no separator is allowed |
| `cp -t~ notes.md` (R2) | allow | nowhere: bash does not expand `~` after `-t`; cp failed on a file literally named `~` |
| `cp notes.md ..,x` (R2) | allow | a **file** named `..,x` inside `ws/` |
| `cp notes.md .{,.}`, `cp notes.md {.,.}.` (R2) | allow, before and after | parent: brace expansion gives `. ..` and `.. ..` (non-goal) |
| `cp notes.md ..$x`, `x` unset (R2) | allow, before and after | parent (non-goal, D5) |
| `cd; pwd` (R2) | allow | `/c/Users/huida`: `cd` alone goes home (non-goal) |

In Git Bash, `globskipdots` is `on`: `echo .?` and `echo .*` printed only `.x`, never `..`.

## Goals / Non-Goals

**Goals:**

- A separator-less word that is the parent directory is judged exactly as `../` is. A word that is
  the home-directory shorthand, in a shape the shell substitutes (`~`, `~+`, `~-`, `~name`), is
  refused as uncheckable, exactly as `~/` is (R3-1 narrowed this from "a leading `~`").
- A separator-less word that carries one of those two spellings as an option's value in the same
  word is judged the same way (D7, R2-2).
- No other separator-less word changes decision.
- Rows P7, R8 and R9 of `test_permission_approver.py` flip to deny, and H10's reason changes
  (R2-1). R1 said P7 was the only pinned evidence of the hole. It is not: R8 (`cd .. && echo hi >
  stray.txt`) and R9 (`git -C .. status`) pin it as allow on purpose, as residuals of the archived
  `a-url-is-not-a-path` (its D9). This change supersedes that decision for those two rows, and for
  D9's two PowerShell residuals, which no row pins (R3-6).

**Non-Goals:** as listed in `proposal.md`. The two that are near-misses of this one are argued here
(D5, D6), so a later round can overturn them with evidence rather than rediscover them. R2 added
two more to the proposal's list, both measured: bash brace expansion and a bare `cd`.

## Decisions

### D1 — Route the two spellings; do not judge every separator-less word

Rule 4 keeps its exemption, and names the two spellings it no longer covers. R2 extended R1's
version to read the value an option carries in the same word (D7). R3 made two further changes
(R3-1, R3-2): the `~` check matches only the shapes a shell substitutes, and the colon-joined form
is read in both dialects for `..`:

```python
# A value an option carries in its own word (D7): joined by a colon, `-Destination:..`,
# `-o:..`, `--output:..` (checked for `..` in both dialects, and for `~` in PowerShell, whose
# provider cmdlets resolve it there), or a short option with its value glued on, `cp -t..`,
# `tar -xvC..` (checked for `..` only: bash does not expand a `~` there).
_COLON_OPTION_RE = re.compile(r"--?[A-Za-z_][A-Za-z0-9_-]*:")
_GLUED_OPTION_RE = re.compile(r"-[A-Za-z0-9]+")
# The home-directory shorthand in the shapes a shell substitutes for a word with no separator
# (D3): alone, with a sign, or with a user name. `~30%` and `~2x` are left alone.
_TILDE_PREFIX_RE = re.compile(r"~(?:[+-]|[A-Za-z_][A-Za-z0-9._-]*)?")

if not has_separator:  # 4: a name in the directory the shell runs in -- unless it names another
    value = word
    joined = _COLON_OPTION_RE.match(word)
    if joined:
        value = word[joined.end() :]
        if dialect == "powershell" and _TILDE_PREFIX_RE.fullmatch(value):
            return _refuse(word, _UNCHECKED)
    else:
        if _TILDE_PREFIX_RE.fullmatch(word):
            return _refuse(word, _UNCHECKED)
        glued = _GLUED_OPTION_RE.match(word)
        if glued:
            value = word[glued.end() :]
    if value.partition("\x00")[0] == "..":
        return _judge_path("..", root, word, argument, continues)
    return None
```

R2 measured its version of this logic through `_decide`. R3 measured the version above from a
patched scratch copy of the whole `hub` package (so the tests that spawn `mcp_server.py` as a
process ran it too). `-t..`, `-xt..`, `-C..` and `-xvC..` in both dialects, `-Destination:..`,
`-Dest:'..'`, `-o:..` and `--output:..` in both dialects, `-Destination:~` and `-t$'..\x00x'` are
refused, each quoting the whole word. `-la`, `git log -1`, `-t...`, `-t~`, bash `-x:~`,
`-Destination:sub`, `-Destination:~5`, `-Filter:*.md`, `-Recurse:$true`, `~30%`, `~2x` and `~13`
stay allowed.

**Totality is load-bearing here.** `approve_tool_call` calls `_decide` with no `try` around it
(`mcp_server.py:1609`), so an exception in rule 4 would reach Claude as a failed MCP tool call, not
as a decision. The added code is `re.match` and `re.fullmatch` calls on a `str`, a slice and
`partition`, none of which raises, plus `_judge_path`, which is total because `_where` catches
`OSError` and `ValueError` (`:1041-1051`). `_judge_path` is handed the literal `".."`, never the
word, so a NUL in the word never reaches `os.path` (R3 checked this; the word itself only reaches
`_quote`, which renders it with `repr`).

**Alternative rejected: judge every separator-less word with `_where`.** It catches `..`, but
measurement shows it is wrong in three ways:

- **It does not catch `~`.** `os.path.join(root, "~")` resolved to `ws\~`, which is inside, because
  Python does not expand the shorthand. That is correct Python and a wrong answer for the shell.
- **It refuses harmless words on Windows.** `ntpath` reads any `X:` prefix as a drive, so
  `sed s:a:b: file` would resolve `s:a:b` on drive S and be refused as outside. On this
  machine, where the Hub runs, that is a false refusal of ordinary shell.
- **It costs a `realpath` system call for every word of every shell command,** to answer a question
  whose answer is already known for every word except two.

**Alternative rejected: drop the `has_separator` gate from rule 3 as well.** That would refuse every
`echo $x` (D5).

### D2 — `..` is judged, not refused outright

`..` goes through `_judge_path`, not straight to `_refuse(word, _OUTSIDE)`. The one case where the two
differ is a workspace whose parent is itself (a workspace at a filesystem root). There `..` really is
inside, and `commonpath` says so. That keeps the rule identical to what rule 5 does for `../`, which
is what the spec's "judged alike" scenario asserts. **R2-6:** this case is testable here, contrary to
R1's Risks entry: `_decide` reads no file, so the workspace need not be created. With
`AW_WORKSPACE_DIR=C:/`, R2 measured `cp notes.md ..`, `cp notes.md ../` and `cp notes.md ../x` all
allowed under the proposed rule. A row with the workspace at `os.path.abspath(os.sep)` passes on
both platforms and fails if D2 is implemented as `_refuse(word, _OUTSIDE)`, which makes it the test
that pins this decision. The refusal quotes the whole word (`shown=word`),
so a NUL-ended word is quoted as typed, with its `\x00` rendered by `repr` (`_quote`, `:1024`).

`continues` is passed through unchanged. For a `..` that its argument carries on past (the `..` in
`..,x`, split by `_WORD_SPLIT_RE`), `_judge_path` also tries `.._`. **R2-5:** R1 called `.._` "a
child of the parent. That is outside too". It is not: `".." + "_"` is the name `.._`, which is inside
the workspace. The extension check therefore never refuses anything for `..`; the refusal comes from
the first `_where("..")`. The conclusion (the added check cannot turn a refusal into an allow) still
holds, because `_judge_path` returns the first refusal before it tries the extension.

### D3 — A leading `~` is uncheckable, not outside

`~`, `~user`, `~+` and `~-` are each substituted by the shell from state the judge cannot see: `HOME`,
the password database, `PWD` and `OLDPWD`. `~+` is the current directory and can be inside. So the
honest reason is `_UNCHECKED`, the same constant rule 3 uses, and not `_OUTSIDE`. This matches the
existing requirement's SHALL NOT for separator-bearing words (`spec.md:624-628`).

The shorthand is matched on the lexed word, so a quoted `'~'` (which bash would not expand) is also
refused. Rule 3 already does exactly this for `'~/x'`, because `_expands` reads the lexed word
(`:1076-1085`). The over-refusal is accepted there, and it is accepted here for the same reason.
R2 names what it costs, since a separator-less `~` is commoner as a pattern than `~/x` is:
`grep '~' notes.md` and `find . -name '~*'` are refused. So is `Write-Output ~` in PowerShell, where
`~` is expanded only by a provider cmdlet (R2 measured it printing `~`). Each refusal names the word
and tells the agent to write a workspace-relative path. Accepted, but it is the change's widest
over-refusal, and R3 should weigh it against refusing only an unquoted `~`, which needs the lexer
to mark a quoted `~` the way it marks a quoted `$` (`_LITERAL_DOLLAR`, `:1002`).

**R3-1: the over-refusal was wider than that, and the rule is narrowed to the shapes a shell
substitutes.** A leading `~` is ordinary prose for an approximate figure, and prose reaches the
judge: a commit message or PR body is lexed like any other argument, and the body of the heredoc
Claude Code uses for commits (`git commit -m "$(cat <<'EOF' … EOF)"`) is lexed as a nested command,
unquoted. R3 measured `git commit -m "cuts time by ~30%"`, `gh pr create --body 'about ~5 files'`
and that heredoc form carrying `~30%`: all allowed today, all refused by R2's rule. In this
repository's last 3,000 commit messages, 106 carry a separator-less word that begins with `~`
(`~13`, `~30`, `~19s`, `~22%`, `~3.5`), against 2 that carry a lone `..` (a regex count that
approximates `_words`; under the shapes below, 3 of the 106 would still be refused).

A word with no separator is, to the shell, one whole tilde-prefix. Bash substitutes it only in
these shapes (measured in Git Bash 5.2.37): `~` (home), `~+` and `~-` (`PWD`, `OLDPWD`), `~N`,
`~+N` and `~-N` (directory-stack entries), and `~name` for a user that exists (`~huida` expanded,
`~nosuchuser` stayed literal). `~30%`, `~2x` and `~5` with no stack stayed literal. PowerShell's
provider resolves only `~` (`Resolve-Path ~huida` and `~5` failed as literal paths; R3 also measured
`Copy-Item notes.md -Destination:~5` writing a file named `~5` inside the workspace). So the check
is `_TILDE_PREFIX_RE.fullmatch`: `~`, `~+`, `~-`, or `~` followed by a name that begins with a
letter or `_` and continues with letters, digits, `.`, `_` or `-`. Two shapes are left out on
purpose:

- **`~N`, `~+N`, `~-N`.** A directory-stack entry is a directory some `pushd` put there, and
  `pushd` names it as a word the judge reads. So the entry was judged when it was pushed, unless it
  came from a variable, which is D5's hole, not a new one. The digit forms are also exactly the
  shape of prose figures (`~13`, `~30`).
- **A user name that begins with a digit** (`~2x`). Linux's default `useradd` refuses such names;
  Windows accounts may have them. The residual is a real account whose name begins with a digit,
  on a machine where an agent would guess it.

`~root`, `~huida` and `~approximately` are still refused, and so is a lone `~` in prose
(`approx ~ 5`) and as a quoted pattern (`grep '~' notes.md`).

**R3 on the quoted-`~` alternative: not in this change.** Marking a quoted `~` in the lexer the way
`_LITERAL_DOLLAR` marks a quoted `$` is right for bash only. In PowerShell quoting does not protect
a `~`: `Resolve-Path '~'` and `Resolve-Path "~"` both printed `C:\Users\huida`, and an MSYS program
started from PowerShell expands a leading `~` and `~user` itself (Git's `echo.exe ~ ~huida '~' "~"`
printed the home directory four times; `-t~` and `~+` stayed literal). It would also leave the
commonest carrier, the unquoted heredoc body, exactly as refused as before, and it changes what
rule 3 sees for a quoted `'~/x'`, which is existing behaviour this change does not own. It can be
filed as a finding if a quoted `~` pattern turns out to block real work.

### D4 — The NUL comparison lives in rule 4, not in the lexer

An argument the shell passes on is a C string: it ends at the first NUL. Measured: in Git Bash,
`cp notes.md $'..\x00x'` copied into the parent. The archived `a-quote-can-spell-a-slash` D5
deliberately decodes `\x00` into a real NUL in the word. Truncating there would change what every
other rule sees, and that change's ANSI-C rows were validated against the untruncated word over
eight rounds. So only rule 4's comparison truncates.

This is not a general NUL rule. A separator-bearing word containing a NUL is left exactly as today:
`_PLAIN_RELATIVE_RE` excludes NUL (`:973`), so such a word falls to rule 6's backstop. Whether every
such word is refused there is not re-derived in R1; this change does not alter that path. R2
measured one: `cp notes.md $'..\x00/x'` is refused today, as `'/x'` outside, by the backstop. The
shell's argument is `..`, so the refusal is right and its reason names a path nobody wrote.

### D5 — A bare variable or substitution stays exempt (non-goal)

`cp notes.md $HOME` is an escape, and it is measured as allowed. Refusing separator-less words that
contain `$` would refuse `echo $x`, `for f in $files` and `test -n "$VAR"`, which is most real shell.
`_decide`'s docstring already disclaims paths built at run time (`:1448-1449`; R3-8). This is proposed as
a separate finding, where the trade-off can be decided on its own evidence.

### D6 — PowerShell drive-qualified words stay out (non-goal)

`Copy-Item notes.md Z:` reaches the judge as the word `Z`, because `_WORD_TRIM` includes `:`
(`:981`) and `_words` strips it from both ends (`:1396`). A fix has to see the colon, so it
belongs in `_words` or in a dialect-aware pre-check, and it must be PowerShell-only: Git Bash wrote a
file named `C:`. It also has to handle multi-letter PSDrives (`Temp:` in PowerShell 7) without
refusing `git show HEAD:README.md`. That is a design of its own, and it is proposed as a separate
finding.

### D7 — The value an option carries in its own word is judged too (R2-2)

R1's rule refuses `..` and allows `-t..`. R2 measured both landing in the parent: `cp -t.. notes.md`
in Git Bash, and `Copy-Item notes.md -Destination:..` in PowerShell 5.1. The existing requirement
already rules on this pair: a word that joins a path to an option "SHALL be judged at least as
strictly as the path within it would be if it stood alone" (`spec.md:630-632`). Before this change
`..` alone stood, so `-t..` standing was consistent. After it, leaving `-t..` alone violates a
requirement this change does not modify, and R1's delta ("Every other word with no path separator
SHALL continue to stand") contradicted that requirement outright. It is also the asymmetry the
proposal calls a defect: `cp -t../ notes.md` is refused today (rule 6 finds `/`), and
`cp -t.. notes.md` is allowed.

Two joins put a value in the option's own word with no separator for `_words` to split at:

- **An option joined to its value by a colon**, `-Name:value`. PowerShell binds the text after
  the colon as the parameter's value and resolves it as a provider path, so `~` there is the home
  directory (R2 measured `-Destination:~\x.md` landing in `$HOME`). Both checks apply in
  PowerShell. **R3-2:** R2 made the pattern PowerShell-only, because in bash `-x:..` is one literal
  argument. That is the same argument the glued form below rejects: the shell passes the word on,
  and the program splits it. .NET's `System.CommandLine` (the `dotnet` CLI) documents `:` as an
  option delimiter alongside `=` and a space, so `dotnet publish -o:..` and `--output:..` name the
  parent from either shell (documented, not measured: this machine has no .NET SDK). So the `..`
  check reads a colon-joined value in both dialects, for `-name:` and `--name:`. The `~` check stays
  PowerShell-only: bash left `-x:~` literal (measured: `echo -x:~` printed `-x:~`), and a program
  that splits `-o:~` itself does not expand `~`. No ordinary word is `-name:..` or `--name:..`.
- **A short option with its value glued on**, `cp -t..`, `tar -C..`, `make -C..`, and combined
  flags `cp -xt..`, `tar -xvC..` (R3 measured both landing in the parent in Git Bash, with GNU tar
  1.35). The program parses this from its own argv, so it holds in both dialects: PowerShell passes
  `-C..` to a native `tar` unchanged. Only `..` is checked. Bash does not expand a `~` after `-t`
  (R2 measured `cp -t~ notes.md` looking for a file literally named `~`). PowerShell does not
  expand one in an argument to a native program; an MSYS program expands a *leading* `~` from its
  own command line (R3, D3), but `-t~` does not lead with it, and Git's `echo.exe -t~` printed
  `-t~`.

`--name=value` needs nothing new: `_words` already splits at `=`, which is why
`--target-directory=..` reaches rule 4 as `..`.

**Which option letters take a value is the program's business, and the judge does not know it.**
`_GLUED_OPTION_RE` therefore treats any run of letters and digits after one `-` as options, and
judges what follows. The words that match and end in exactly `..` are `-X..` spellings ordinary
commands almost never use, so the cost is small. R3 found two that are not paths, both refused:
`awk -F.. '{print $1}'` (a field separator of two dots) and a Ruby endless range,
`ruby -e 'p (-1..)'`, whose `(-1..)` trims to `-1..`. `-t...` and `-la` are not touched.
`--long..` does not match (the second `-` is not a letter or digit), and needs no rule: a GNU long
option takes its value after `=` or as the next word.

**Alternative rejected: leave the joined forms as a non-goal.** That keeps the rule smaller, but it
leaves the main spec contradicting itself (the joined-word clause against the new requirement), and
`-Destination:..` is an ordinary PowerShell spelling of a parameter value. The operator may still
prefer it; it is Open Question 3.

## Risks / Trade-offs

- **`cd ..` inside a compound command is newly refused**, for example
  `cd sub && make && cd .. && ls`. → This is consistent: `cd ../` is refused today, and so is
  `cd ../other` (the judge resolves every relative word against the root, per the docstring). The
  refusal names `'..'` and says it is outside, so an agent can rewrite it as `(cd sub && make)` or
  `make -C sub`. Accepted. **R3-9:** the commonest legitimate form is an out-of-source build,
  `mkdir build && cd build && cmake ..`, where `..` is the workspace itself. It is refused (measured),
  as `cmake ../` already is; the rewrite is `cmake -S . -B build`.
- **`ls ~` or `echo ~` is newly refused**, and so is a quoted `~` pattern (D3). → The refusal says
  why. Accepted; D3 records R3's weighing of the quoted-`~` alternative.
- **Prose in a commit message or PR body is judged** (R3-1). A lone `..` in a message
  (`git commit -m 'go up with cd .. first'`, measured refused) and a `~` word in one of the shapes
  D3 keeps (`~`, `~root`, `~approx`) are refused, as `../` and `~/.bashrc` in a message already are.
  → Accepted. R3 narrowed the `~` check so the common approximate figures (`~30%`, `~13`, `~2x`)
  stand: 106 of this repository's last 3,000 commit messages carry a `~` word, and 3 of them would
  still be refused; a lone `..` is in 2.
- **A `..` that is only a piece of an argument is refused** (R2). `_words` splits at `,` and `=`, so
  `echo a,..` and `cp notes.md ..,x` are refused, although the second writes a file named `..,x`
  inside the workspace (measured). → The same splitting already refuses `../work,y` (row E17), and a
  program that splits a comma list of directories would read `..` there. Accepted.
- **A workspace at a filesystem root.** → D2 keeps `..` inside there, via `commonpath`. R1 said this
  could not be tested here. R2-6: it can, and task 1.2 now pins it.
- **The change reaches the operator's live instance before it is committed** (R2-7). The Hub starts
  each run's MCP server from this checkout's file (`hub/hub/api/v1/agent_trigger.py:1094-1095`,
  `[sys.executable, <checkout>/hub/hub/mcp_server.py]`), and `:8000` runs this checkout. → The
  implementing session tells the operator before editing `mcp_server.py`, since their agents'
  `cd ..` is refused from the next run that starts.
- **Archived D9's PowerShell residuals are closed too** (R3-6). `a-url-is-not-a-path` D9 named
  `Set-Content (Join-Path .. stray.txt) "hi"` and `[IO.Path]::Combine('..', 'x')` as allowed
  residuals, measured writing into the parent. Both carry `..` as a word of its own, so both are now
  refused (measured). No test row pins them, so no test changes; the supersession of D9 covers them
  as well as R8 and R9. `Resolve-Path`/`Convert-Path` over a variable remain D5's.
- **Rows P7, R8 and R9's comments, and the archived designs, describe the old allow.** → The test
  comments are rewritten in the tasks that flip the rows, naming this change. Archived design
  documents are not edited.

## Migration Plan

None. The judge runs in each run's MCP server process (`_decide`). It needs no schema change, no Hub
restart and no UI bundle. A run picks up the change the next time its MCP server starts, on any Hub
that runs this checkout, `:8000` included, and whether or not the change is committed (R2-7).
Rollback is a revert of one commit.

## Open Questions

1. **File D5 and D6 as findings now?** R1 recommends yes: two findings, sized **B**, since each is an
   escape but needs a spelling an agent is less likely to produce by accident than `..`. They were
   not filed in R1, so that the operator decides the numbering and severity. R2 adds a third
   candidate of the same size: bash brace expansion (`cp notes.md .{,.}`), which `_lex` does not
   model for any rule.
2. **Should R2 measure on Linux?** Every real-shell row here is Windows (Git Bash, PowerShell 5.1).
   The POSIX branch of `_SEPARATORS` changes nothing for `..` or `~`, but CI runs Linux, so the new
   test rows will run there, which is where they must pass. R2 did not measure on Linux. It checked
   instead that nothing new depends on the platform: the value extraction and both checks read the
   word's text, and only `_where` touches `os.path`, as rule 5 already does. One platform fact
   matters for the evidence, not the decision: `~root` is literal in this Git Bash and expands on
   Linux, so no real-landing row on this machine may cite `~root` as landing in a home directory.
3. **Option-joined values in scope (D7)?** R2 brought `-t..` and `-Destination:..` into this change,
   because the existing joined-word requirement obliges it once `..` alone is refused. The
   alternative is to name them a non-goal and amend that requirement in this change's delta, which
   R2 does not recommend. Operator's call. R3 widened the colon form to both dialects and to
   `--name:` (R3-2); it recommends keeping D7 in scope with that widening.
4. **Superseding archived D9 for R8 and R9.** `a-url-is-not-a-path` pinned `cd .. && …` and
   `git -C .. status` as allowed residuals on purpose. This change refuses them. The operator should
   know that a decision from an archived change is being reversed, and that the reversal reaches
   `:8000` runs as soon as the file changes. R3-6: D9's two PowerShell residuals
   (`Join-Path ..`, `[IO.Path]::Combine('..', …)`) are reversed with them.
5. **The narrowed `~` check (R3-1).** R3 refuses a separator-less `~` word only in the shapes a
   shell substitutes, and leaves `~N` (directory stack) and `~` plus a digit-led name (`~2x`)
   standing, so that approximate figures in commit messages are not refused. The alternative is
   R2's rule: refuse every word that begins with `~`, and accept refusing about one commit message
   in 28 (106 of the last 3,000, against 3 under R3's check). R3 recommends the narrowed check. Operator's call.

## Round log

- **R1, 2026-09-21** (interactive, Opus 5). Explored `_judge_word`, `_words`, `_where`,
  `_judge_path` and `_expands`, plus the `agent-run-sandboxing` shell requirement (`spec.md:595-708`)
  and archived P7. Measured 19 commands through `_decide`, and 8 real landings across two shells.
  Proposed routing exactly two spellings (D1-D4). Recorded two related holes as non-goals with
  their reasons (D5, D6).
- **R2, 2026-09-21** (interactive subagent, Opus 5). **Verdict: APPROVE WITH FIXES** (all applied
  in place; R2-2 widens the rule, so R3 must re-derive D7 from the code, not from this entry).
  **Re-derived:** read `_lex`, `_words`, `_judge_word`, `_where`, `_judge_path`, `_expands`,
  `_read_command`, `_decide` and `approve_tool_call` (`mcp_server.py:1592-1613`), the existing
  shell requirement (`spec.md:595-708`), every test file that reaches the judge, and the archived
  `a-url-is-not-a-path` D9. **Measured:** (a) `_decide` in-process, `AW_WORKSPACE_DIR` a scratch
  `f375/ws`, on 48 commands today and with R1's rule 4 swapped in, printing each command's words and
  `continues` flags; (b) the eight judge test files (`test_permission_approver`,
  `test_workspace_writes`, `test_codex_posture_ordering`, `test_mcp_server`,
  `test_a_write_outside_the_workspace_is_recorded`, `test_agent_evidence_grant`, `test_flow_width`,
  `test_a_held_agent_is_busy`) run under a scratchpad pytest plugin that replaces `_judge_word`
  after collection: R1's rule gives 4 failed, 380 passed; R2's D1 gives the same 4 and no others;
  unpatched `test_permission_approver.py` is 217 passed, 1 skipped; (c) real landings in Git Bash
  5.2.37 and Windows PowerShell 5.1.26100. Every spelling R1 names reaches rule 4 as the word R1
  says (`'..'`, `\.\.`, `$'\x2e\x2e'`, `$'\056\056'`, `(..)`, `{..}`, `..,`, `..=x`, `:..:` all lex
  to a `..` word; `$'..\x00x'` to `..` + NUL + `x`), and rules 1 and 2 cannot take a `..` or `~`
  word first: neither starts with a letter or `$`.
  - **R2-1 (major): four existing rows change, not one.** R8 `cd .. && echo hi > stray.txt` and R9
    `git -C .. status` are pinned **allow** on purpose, as archived D9 residuals; they flip. H10
    `HUB_URL=.. ; cat $HUB_URL/x` stays refused, but `_words` splits the assignment at `=` and the
    `..` word is refused first, as outside, so H10's `_UNCHECKED` reason assertion fails, and H10
    stops exercising the `trusted` guard it alone pins. Fix: tasks 1.6 and 1.7 (H10 re-pinned, new
    H10b `HUB_URL=sub ; cat $HUB_URL/x`: refused as uncheckable today, allowed when `trusted` is
    forced true, measured); Goals, proposal and Open Question 4 corrected.
  - **R2-2 (major): the option-joined value escapes.** `cp -t.. notes.md` (Git Bash) and
    `Copy-Item notes.md -Destination:..` (PowerShell) both landed in the parent; R1's rule allowed
    both, and `-Destination:~` too. Once `..` alone is refused, the existing joined-word SHALL
    (`spec.md:630-632`) requires these be refused, and R1's delta ("every other word SHALL continue
    to stand") contradicted it. Fix: D1 extended and D7 added (PowerShell `-Name:` value checked for
    `~` and `..`; a glued short option's value for `..` only, in both dialects); tasks 1.3, 1.5, 1.8
    and 3.1; spec delta rewritten. Open Question 3 lets the operator send it back to a non-goal.
  - **R2-3: `.""."` is not a command.** It is an unbalanced quote; Git Bash refused it ("unexpected
    EOF while looking for matching `\"'"). The lexer runs it to the end and yields `..`, so a test
    row would pass for a reason unrelated to quote joining. Fix: `."".` (measured: lands in the
    parent) in the proposal, design and task 1.1.
  - **R2-4: `~root` does not land in a home here.** In this Git Bash `echo ~root` printed `~root`
    (no such user); `~-` printed the inherited `OLDPWD`. The decision is unaffected. Fix: the
    design table.
  - **R2-5: D2's `.._` argument was wrong.** `.._` is a name inside the workspace, not "a child of
    the parent". The conclusion survives because `_judge_path` returns the first refusal first. Fix:
    D2 text.
  - **R2-6: the filesystem-root case is testable.** `_decide` reads no file; with
    `AW_WORKSPACE_DIR=C:/`, `cp notes.md ..` and `../` are both allowed today and under the proposed
    rule. Fix: task 1.2's second case, which fails against a `_refuse(word, _OUTSIDE)` rule 4 and so
    is the test that pins D2.
  - **R2-7: the change reaches `:8000` before any commit.** `agent_trigger.py:1094-1095` starts each
    run's MCP server from this checkout's `mcp_server.py`. R1's Runtime line implied nothing reached
    `:8000`. Fix: proposal Impact, Risks, Migration Plan, task 0.4, test guide.
  - **R2-8: non-goals missed.** Brace expansion (`.{,.}`, `{.,.}.`: both landed in the parent,
    allowed before and after), a bare `cd` (went home), and `..$x` with `x` unset (landed in the
    parent). Fix: proposal Non-Goals, design table and Open Question 1.
  - **R2-9: the spec delta.** Its "every other word SHALL continue to stand" was a MUST-allow that
    guaranteed the R2-8 holes and contradicted the joined-word clause; replaced by a SHALL that
    ordinary names stay allowed, with an explicit scope limit. Scenarios 3 to 5 lacked "and that
    directory is outside the workspace", so they were false for a workspace at a root; added. The
    judged-alike scenario now covers the root case, and two scenarios cover option-joined values.
    ADDED (not MODIFIED) is kept: nothing in the existing requirement is contradicted by the new one,
    and the joined-word clause is satisfied rather than changed.
  - **R2-10: citations.** `_judge_word` ends at `:1167`; `_read_command` is `:1403-1435`; `_words`
    is `:1385-1400`; `_quote` is `:1024`; archived D9 is `:552-569`. The rest were verified as
    written, including P7 at `test_permission_approver.py:518-521`, archived `design.md:221`, and
    the `_decide` docstring at `:1448-1449`.
  - **R2-11: the approver's answer when something raises.** `approve_tool_call` has no `try`
    around `_decide` (`:1609`). The added code cannot raise (D1, totality paragraph), and every
    refusal it produces goes through `_judge_path` or `_refuse`, which are total. Recorded in D1;
    no fix to the design needed. D4's open question was measured: `cp notes.md $'..\x00/x'` is
    already refused, naming `'/x'`.
  **Test rows that could not fail:** task 1.5 of R1 (negative controls) can only pass today, by
  design; R2 kept them and named the wrong implementation each one catches (task 1.8). Every other
  group-1 row was checked to fail today by measurement (a) or (b).
- **R3, 2026-09-21** (interactive subagent, Opus 5). **Verdict: APPROVE WITH FIXES** (all applied
  in place). R3 formed its conclusions from the proposal, the delta, the tasks and the code before
  reading R1's and R2's entries above.
  **Re-derived:** `_lex`, `_words`, `_judge_word`, `_where`, `_judge_path`, `_expands`,
  `_read_command`, `_decide` and `approve_tool_call` (`mcp_server.py:1593-1613`), and the existing
  requirement (`spec.md:595-708`). Every spelling in tasks 1.1-1.8 reaches rule 4 as the proposal
  says: rules 1 and 2 cannot take a word that starts with `.`, `~` or `-`, rule 3 needs a separator,
  and `_words` splits `--target-directory=..` and `HUB_URL=..` at `=`. `_judge_path` is handed the
  literal `".."`, so a NUL in the word never reaches `os.path`, and the added code is `re.match`,
  `re.fullmatch`, a slice and `partition`: total, so `approve_tool_call`, which has no `try` around
  `_decide` (`:1609`), still always answers.
  **Measured:** (a) `_decide` in-process with `AW_WORKSPACE_DIR` a `C:/…/scratchpad/r3/land/ws`,
  from three scratch copies of the `hub` package (today, D1 as R2 wrote it, and R3's D1), selected
  by `PYTHONPATH`: every row of tasks 1.1-1.8 fails or passes today exactly as each task says, and
  passes under both rules; the root case (`AW_WORKSPACE_DIR=C:/`) allows `..` and `../` today and
  under both rules, and refuses `..` alone under a `_refuse(word, _OUTSIDE)` variant; H10b is
  refused as uncheckable today and allowed with `trusted = True` patched in. (b) A sweep of 100
  ordinary agent commands (git, npm, pip, pytest, ruff, docker, tar, find, grep, sed, awk, cut,
  make, `python -c`, `ruby -e`, PowerShell cmdlets with `-Param:value`, ranges `1..10`, `$a[0..2]`)
  and 54 escapes. (c) Ten test files that reach the judge, 453 tests, each copy run with its own
  `hub/tests` (so the tests that spawn `mcp_server.py` as a process ran the patched file, which R2's
  in-process plugin could not reach): D1 as R2 wrote it and R3's D1 each fail exactly P7, R8, R9
  and H10, confirming task 2.3. Two `test_workspace_writes` tests fail in every scratch copy,
  today's included, because they read the repository's layout; both pass in the repository
  (29 passed). (d) Real shells, Git Bash 5.2.37 and Windows PowerShell 5.1.26100: `cp -xt..` and
  `tar -xvC..` (GNU tar 1.35) landed in the parent; `Copy-Item notes.md -Dest:'..'` landed in the
  parent; `-Destination:~5` wrote a file named `~5` inside; bash printed `~30% ~2x ~5` literally,
  expanded `~0`, `~huida` and (after two `pushd`) `~1`, left `-x:~` and `--a=~` literal, and
  expanded `a=~` and `a=b:~`; `Resolve-Path '~'` and `"~"` gave `C:\Users\huida`; Git's `echo.exe`
  run from PowerShell printed `~ ~huida '~' "~"` as the home directory four times, and `-t~` and
  `~+` literally.
  - **R3-1 (major): the `~` check refused commit messages.** R2's rule refuses every separator-less
    word that begins with `~`. Prose reaches the judge, including the body of the heredoc Claude
    Code commits with, which is lexed as a nested command. `git commit -m "cuts time by ~30%"`,
    `gh pr create --body 'about ~5 files'` and the heredoc form with `~30%` were all allowed today
    and refused by R2's rule; 106 of this repository's last 3,000 commit messages carry such a word,
    and 3 of them would still be refused under R3's check.
    D3 named only `grep '~'`. Fix: `_TILDE_PREFIX_RE`, the shapes a shell substitutes (`~`, `~+`,
    `~-`, `~` plus a letter-led name); `~N` forms and digit-led names stand, with the reasons in D3.
    Proposal, D1, D3, Goals, Risks, delta (the refused-shorthand paragraph and scenario, a new
    "before a figure" scenario, the ordinary SHALL-allow list), tasks 1.8, 2.1 and 3.2, and Open
    Question 5, which puts R2's wider rule back to the operator.
  - **R3-2: the colon form escaped in bash.** R2 read `-Name:value` in PowerShell only, reasoning
    that bash passes `-x:..` literally; D7 rejects that same reasoning for glued options, since the
    program splits the word. `dotnet publish -o:..` (bash) and `--output:..` (either dialect) were
    allowed by R2's rule. .NET's `System.CommandLine` documents `:` as an option delimiter
    (documented, not measured: no .NET SDK here). Fix: `_COLON_OPTION_RE` (`-name:` and `--name:`),
    checked for `..` in both dialects and for `~` in PowerShell only (bash left `-x:~` literal);
    task 1.5 rows; D7, D1, proposal, delta scenario.
  - **R3-3: the delta's option scenario said the reason names the word "as the command wrote it".**
    It names the word as the shell passes it on: `Copy-Item notes.md -Dest:'..'` is refused naming
    `'-Dest:..'`. Fix: the scenario, and a task 1.5 row that pins the quoted case.
  - **R3-4: two scenario gaps.** Task 1.8's `cp -t~ notes.md` had no scenario, and the ordinary
    scenario's WHEN excluded it ("carry neither as an option's value"). The parameter scenario said
    a value that "begins with" `~` is refused, which would oblige refusing `-Destination:~5`, a file
    PowerShell writes inside the workspace. Fix: a scenario for the shorthand joined to an option
    in bash, the parameter scenario narrowed to the shorthand alone, and the ordinary SHALL-allow
    list extended so both "stands" scenarios rest on a SHALL.
  - **R3-5: D7 said PowerShell does not expand `~` for a native program.** True of PowerShell, but
    an MSYS program expands a leading `~` and `~user` from its own command line, quoted or not
    (measured above). Decisions unchanged: `-t~` is not leading, and a bare `~` is refused. Fix: D7
    text; the fact also rules out a PowerShell quoted-`~` sentinel (D3).
  - **R3-6: archived D9 is reversed wider than R8 and R9.** Its PowerShell residuals,
    `Set-Content (Join-Path .. stray.txt) "hi"` and `[IO.Path]::Combine('..', 'x')`, carry `..` as a
    word and are refused under both rules (measured). No row pins them. Fix: proposal, Goals, Risks,
    Open Question 4, task 0.3.
  - **R3-7: over-refusals R2 did not list.** Measured refused under both rules: `awk -F..` (a
    two-dot field separator), `ruby -e 'p (-1..)'` (an endless range trimmed to `-1..`),
    `grep -F '..'`, and a lone `..` in a commit message. Fix: D7 and Risks name them; accepted.
    No ordinary command in the sweep was refused by the colon or glued patterns otherwise
    (`-Recurse:$true`, `-First:5`, `-Format:'yyyy-MM-dd'`, `-c:Release`, `1..10`, `$a[-3..-1]`,
    `{-5..5}`, `HEAD~3`, `stash@{0}` all stand).
  - **R3-8: citations.** D5 cited the docstring at `:1447-1449`; it is `:1448-1449`. Task 2.1 cited
    the patterns at `:955-981`; they begin at `_SEPARATORS`, `:953`. Every other file:line in the
    proposal, design and tasks was checked and holds (`_judge_word` `:1141-1167`, rule 4 `:1158`,
    `has_separator` `:1155`, rule 3 `:1156`, `_where` `:1034-1054` with its catches at `:1043` and
    `:1050`, `_judge_path` `:1057-1073`, `_expands` `:1076-1085`, `_words` `:1385-1400` and `:1396`,
    `_read_command` `:1403-1435`, `_WORD_TRIM` `:981`, `_PLAIN_RELATIVE_EVERYWHERE` `:973`,
    `_LITERAL_DOLLAR` `:1002`, `_quote` `:1024`, `:1609`, `agent_trigger.py:1094-1095`, P7 at
    `test_permission_approver.py:518-521`, R8/R9/H10 at `:177-178` and `:206`, `spec.md:624-628`
    and `:630-632`, archived `design.md:221`, `:173-174` and D9 `:552-569`).
  - **R3-9: `cmake ..` was not in Risks.** The out-of-source build `cd build && cmake ..` is the
    commonest legitimate `..`, and it is refused (measured). Fix: Risks, proposal, test guide, with
    the rewrite `cmake -S . -B build`.
  **D3's quoted-`~` question, answered:** not in this change. A lexer mark for a quoted `~` would be
  correct in bash only, would not reach the unquoted heredoc body that carries most prose, and would
  change what rule 3 sees for `'~/x'`. R3-1's shape check removes most of the cost instead.
  **Consistency:** the delta stays ADDED; the existing requirement's uncheckable clause is scoped to
  separator-bearing words and its joined-word clause is satisfied, not changed. Each requirement's
  SHALL is on its first physical line, and every scenario is exercised by a task 1.x row: parent
  alone (1.1, 1.6), judged alike (1.2), quotes (1.1), option value (1.1, 1.5), NUL (1.4, 1.5),
  shorthand alone (1.3), parameter value (1.3), ordinary (1.8), before a figure (1.8), joined in
  bash (1.8). `openspec validate --strict` passes.
