# Proposal — a word without a separator can still leave

**Round 1, 2026-09-21** (interactive, operator-requested); **corrected by R2, 2026-09-21** (design
round log, R2-1 to R2-11). Finding: **F375 (A)**. **Nothing here is implemented yet.** R3 still has
to compare this proposal against the code independently before any task is built (CLAUDE.md, "the
round discipline").

## Why

The shell-command judge waves a bare `..` through as "not a path", so `cp notes.md ..` is answered
**allow, "inside your workspace"** and the file lands one directory above the workspace. That is the
plainest traversal there is, and it needs no quoting, escaping or locale trick. It works on every
platform, in both dialects, and for every tool that takes a directory argument.

The cause is one line. `_judge_word` (`hub/hub/mcp_server.py:1141-1167`) applies rule 4 at `:1158`:
a word containing no `/` (or, on Windows, `\`) returns `None` before `_where` is ever called. Rules 3,
5 and 6, the only ones that could catch a traversal or an expansion, are all gated behind
`has_separator` (`:1155`). The premise "no separator, so not a path" holds for an ordinary name,
because a name without a separator resolves to an entry of the shell's current directory. It fails
for the words that name *another directory by themselves*: `..` is the parent, and `~` (with `~user`,
`~+`, `~-`) is a home or remembered directory. It also fails for a word that carries one of those
as an option's value in the same word: `cp -t..`, `tar -C..`, and PowerShell's
`-Destination:..` and `-Destination:~` (R2-2).

This session measured today's decisions by calling `_decide` directly, with the workspace a
subdirectory of a scratch directory:

| Command | Dialect | Today | Where it really lands |
|---|---|---|---|
| `cp notes.md ..` | Bash | allow | the parent (Git Bash 5.2.37: the file appears there) |
| `Copy-Item notes.md ..` | PowerShell | allow | the parent (PowerShell 5.1: the file appears there) |
| `cp notes.md '..'`, `cp notes.md ."".` | Bash | allow | the parent (the quotes join to `..`; R2 measured `."".` in Git Bash) |
| `cp --target-directory=.. notes.md` | Bash | allow | the parent (`_words` splits at `=`) |
| `cp -t.. notes.md` | Bash | allow | the parent (R2, Git Bash 5.2.37: the file appears there) |
| `Copy-Item notes.md -Destination:..` | PowerShell | allow | the parent (R2, PowerShell 5.1.26100: the file appears there) |
| `Copy-Item notes.md -Destination:~\x.md` | PowerShell | **deny**, `'\x.md'` outside (rule 6) | the home directory (R2: the file appeared in `$HOME`); `-Destination:~` alone is allowed |
| `cp notes.md $'..\x00x'` | Bash | allow | the parent (bash ends the argument at the NUL; measured this session: the copy appears in the parent) |
| `ls ..`, `cd .. && cat notes.md` | Bash | allow | the parent |
| `cp notes.md ~` | Bash | allow | the home directory |
| `Copy-Item notes.md ~` | PowerShell | allow | the home directory (PowerShell 5.1: the file appears in `$HOME`) |
| `cp notes.md ../` | Bash | **deny**, "'../' is outside your workspace" | the parent |

The last row is the one that makes the first rows a defect rather than a design choice. `..` and
`../` name the same directory, and the judge refuses one and allows the other.

The archived change `a-quote-can-spell-a-slash` pinned its row P7 as **allow**, with a comment naming
F375 as the owner of the underlying hole (`hub/tests/test_permission_approver.py:518-521`, archived
`design.md:221`). It explicitly left the real repair to this change.

## What Changes

- Rule 4 of `_judge_word` stops exempting a separator-less word that names another directory by
  itself:
  - A word that is exactly `..`, compared by what precedes its first NUL, is judged as a path, the way
    rule 5 already judges `../`. It is refused as outside the workspace, with the word quoted.
  - A word that begins with `~` is refused as uncheckable, with the same reason rule 3 already gives
    `~/x`. It is not refused as "outside": `~` can in principle name the workspace.
  - The same two checks apply to the value an option carries in the same word (R2-2). In
    PowerShell, the value of `-Name:value` is checked for both (`-Destination:..`,
    `-Destination:~`). In both dialects, the value glued to a short option (`-t..`, `-C..`) is
    checked for `..` only: bash does not expand a `~` there (measured: `cp -t~ notes.md` looked for
    a file literally named `~`), and PowerShell passes it to a native program unchanged. The
    existing requirement already demands this once `..` alone is refused: a word that joins a path
    to an option "SHALL be judged at least as strictly as the path within it would be if it stood
    alone" (`openspec/specs/agent-run-sandboxing/spec.md:630-632`).
  - Every other separator-less word is still exempt, unchanged: `.`, `...`, `notes.md`, `-la`,
    `git log -1`, `HEAD~1`, `a..b`, `-Destination:sub`.
- Test rows flip, and new rows pin each case above on both dialects. **Four existing rows change,
  not one** (R2-1, measured by running the judge's eight test files with the proposed rule 4
  patched in: 4 failed, 380 passed):
  - `P7` (`cp notes.md $'..\x00x'`) flips from allow to deny, as R1 said.
  - `R8` (`cd .. && echo hi > stray.txt`) and `R9` (`git -C .. status`) flip from allow to deny.
    Both were pinned as allow on purpose, as "residual, unchanged" by the archived
    `a-url-is-not-a-path` (its `design.md:173-174` and D9, `:552-569`). This change supersedes that
    decision for these two rows.
  - `H10` (`HUB_URL=.. ; cat $HUB_URL/x`) stays refused, but for a different reason: `_words`
    splits the assignment at `=`, so the `..` word is refused as outside before the untrusted
    `$HUB_URL/x` is reached. H10 is the only row that pins the `trusted` guard of `_read_command`,
    so a companion row with a value that is not `..` takes over that job.
- **Behaviour change an operator will see:** `cd ..`, `ls ..`, `git -C .. status` and `pushd ..`
  are now refused, exactly as `cd ../` and `ls ../` already are. `cp x ~` and `ls ~` are now
  refused, exactly as `ls ~/` already is. A quoted `~` used as a pattern (`grep '~' notes.md`,
  `find . -name '~*'`) is also refused (design D3).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-run-sandboxing`: adds one requirement. A word with no path separator is still judged when it
  names a directory by itself, or carries one as an option's value. The existing requirement "A
  path in a shell command is judged by where it resolves"
  (`openspec/specs/agent-run-sandboxing/spec.md:595-708`) is left unmodified. Nothing in it says a
  separator-less word is allowed, and its uncheckable clause is scoped to words "that also contain
  a path separator", which the new requirement extends rather than contradicts. Its joined-word
  clause (`:630-632`) is what makes the option-joined forms part of this change: once `..` alone
  is refused, `-t..` must be judged at least as strictly (R2-2).

## Non-Goals

Each of these is stated so that omission is not read as coverage.

- **A bare variable or command substitution** (`cp notes.md $HOME`,
  `cp notes.md $(dirname $PWD)`). Both measured as allowed today. It is the same shape of hole, but refusing
  every separator-less word that contains `$` would refuse `echo $x`, `for f in $list` and most
  ordinary shell, and `_decide`'s own docstring already states that "a path built at run time never
  appears as a word, so this is a boundary, not a sandbox" (`mcp_server.py:1448-1449`). The same
  holds for `..` glued to a variable: R2 measured `cp notes.md ..$x`, with `x` unset, landing in
  the parent, and it stays allowed. Proposed as a separate finding (see design, Open Questions).
- **Bash brace expansion** (`cp notes.md .{,.}`, `cp notes.md {.,.}.`). R2 measured both landing in
  the parent in Git Bash 5.2.37, because the shell expands them to `. ..` and `.. ..`. They are
  still allowed after this change: `_lex` does not model brace expansion at all, and `_words`
  splits the word at the comma into `.` pieces. The fix belongs in the lexer, for every rule, not in
  rule 4. Proposed as a separate finding.
- **PowerShell drive-qualified words** (`Copy-Item notes.md Z:`, `Temp:` on PowerShell 7). Measured:
  allowed today. The judge never sees `Z:`, because `_WORD_TRIM` strips the colon and leaves `Z`
  (`mcp_server.py:981`, `_words` at `:1385-1400`). A fix touches word trimming and needs its own
  dialect and platform rows. Git Bash, measured, writes a file literally named `C:`, so the fix is
  PowerShell-only. Proposed as a separate finding.
- **A glob that could expand to `..`.** Measured: Git Bash 5.2.37 has `globskipdots` on, so `.?` and
  `.*` never match `..`. There is no hole on this machine. It is not generalised to older bash.
- **The shell's current directory.** A `cd` into a subdirectory followed by `..` inside the same
  command is still judged against the workspace root, as every relative word already is
  (`_decide`'s docstring). This change does not start tracking `cd`. So a command that moves the
  shell out of the workspace without naming a directory still passes: `cd` with no argument goes
  home (R2 measured `cd; pwd` printing `/c/Users/huida`), and `cd -` and `popd` go back to a
  remembered directory. The change refuses `cd ..`; it does not close `cd`.
- **The Codex approval path** (`codex_appserver.decide_approval`). It judges a command by its `cwd`,
  not by its words, and Codex is undrivable on this machine (memory, 2026-08-29).
- **File tools** (`Write`, `Edit` and the rest, via `_PATH_KEYS`). They already call `_where`
  directly, so a `file_path` of `..` is judged today.

## Impact

- **Code:** `hub/hub/mcp_server.py`, rule 4 of `_judge_word` and one compiled pattern beside it. No
  change to `_lex`, `_words`, `_where` or `_judge_path`.
- **Tests:** `hub/tests/test_permission_approver.py`: P7, R8 and R9 flip; H10's expected reason
  changes and a companion row H10b is added; new parametrised rows are added.
- **Runtime:** the approver runs inside the agent's MCP server process. It needs no Hub restart, no
  migration and no UI bundle. **It does reach the operator's live `:8000` instance, and sooner than
  a commit** (R2-7): the Hub starts each run's MCP server as `[sys.executable, <checkout>/hub/hub/
  mcp_server.py]` (`hub/hub/api/v1/agent_trigger.py:1094-1095`), and `:8000` runs this checkout. So
  the new rule governs every `:8000` run whose MCP server starts after the file changes on disk,
  committed or not.
- **Operator-visible:** more refusals for commands that already leave the workspace (`cd ..`,
  `git -C .. status`, `ls ~`, `Copy-Item x -Destination:..`), and for a quoted `~` pattern. Each
  refusal names the word and why. A `cd ..` an agent used to get away with on `:8000` is refused
  from the first run that starts after implementation.
