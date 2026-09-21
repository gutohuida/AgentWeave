# Proposal — a word without a separator can still leave

**Round 1, 2026-09-21** (interactive, operator-requested). Finding: **F375 (A)**. **Nothing here is
implemented yet.** R2 and R3 each still have to compare this proposal against the code independently
before any task is built (CLAUDE.md, "the round discipline").

## Why

The shell-command judge waves a bare `..` through as "not a path", so `cp notes.md ..` is answered
**allow, "inside your workspace"** and the file lands one directory above the workspace. That is the
plainest traversal there is, and it needs no quoting, escaping or locale trick. It works on every
platform, in both dialects, and for every tool that takes a directory argument.

The cause is one line. `_judge_word` (`hub/hub/mcp_server.py:1141-1168`) applies rule 4 at `:1158`:
a word containing no `/` (or, on Windows, `\`) returns `None` before `_where` is ever called. Rules 3,
5 and 6, the only ones that could catch a traversal or an expansion, are all gated behind
`has_separator` (`:1155`). The premise "no separator, so not a path" holds for an ordinary name,
because a name without a separator resolves to an entry of the shell's current directory. It fails
for the words that name *another directory by themselves*: `..` is the parent, and `~` (with `~user`,
`~+`, `~-`) is a home or remembered directory.

This session measured today's decisions by calling `_decide` directly, with the workspace a
subdirectory of a scratch directory:

| Command | Dialect | Today | Where it really lands |
|---|---|---|---|
| `cp notes.md ..` | Bash | allow | the parent (Git Bash 5.2.37: the file appears there) |
| `Copy-Item notes.md ..` | PowerShell | allow | the parent (PowerShell 5.1: the file appears there) |
| `cp notes.md '..'`, `cp notes.md .""."` | Bash | allow | the parent (the quotes join to `..`) |
| `cp --target-directory=.. notes.md` | Bash | allow | the parent (`_words` splits at `=`) |
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
  - Every other separator-less word is still exempt, unchanged: `.`, `...`, `notes.md`, `-la`,
    `HEAD~1`, `a..b`.
- Test row P7 flips from allow to deny, and new rows pin each case above on both dialects.
- **Behaviour change an operator will see:** `cd ..` and `ls ..` are now refused, exactly as `cd ../`
  and `ls ../` already are. `cp x ~` and `ls ~` are now refused, exactly as `ls ~/` already is.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-run-sandboxing`: adds one requirement. A word with no path separator is still judged when it
  names a directory by itself. The existing requirement "A path in a shell command is judged by where
  it resolves" is left unmodified: it constrains only words that contain a separator
  (`openspec/specs/agent-run-sandboxing/spec.md:595-708`), and nothing in it says a separator-less
  word is allowed.

## Non-Goals

Each of these is stated so that omission is not read as coverage.

- **A bare variable or command substitution** (`cp notes.md $HOME`,
  `cp notes.md $(dirname $PWD)`). Both measured as allowed today. It is the same shape of hole, but refusing
  every separator-less word that contains `$` would refuse `echo $x`, `for f in $list` and most
  ordinary shell, and `_decide`'s own docstring already states that "a path built at run time never
  appears as a word, so this is a boundary, not a sandbox" (`mcp_server.py:1448-1449`). Proposed as a
  separate finding (see design, Open Questions).
- **PowerShell drive-qualified words** (`Copy-Item notes.md Z:`, `Temp:` on PowerShell 7). Measured:
  allowed today. The judge never sees `Z:`, because `_WORD_TRIM` strips the colon and leaves `Z`
  (`mcp_server.py:981`, `_words` at `:1385-1399`). A fix touches word trimming and needs its own
  dialect and platform rows. Git Bash, measured, writes a file literally named `C:`, so the fix is
  PowerShell-only. Proposed as a separate finding.
- **A glob that could expand to `..`.** Measured: Git Bash 5.2.37 has `globskipdots` on, so `.?` and
  `.*` never match `..`. There is no hole on this machine. It is not generalised to older bash.
- **The shell's current directory.** A `cd` into a subdirectory followed by `..` inside the same
  command is still judged against the workspace root, as every relative word already is
  (`_decide`'s docstring). This change does not start tracking `cd`.
- **The Codex approval path** (`codex_appserver.decide_approval`). It judges a command by its `cwd`,
  not by its words, and Codex is undrivable on this machine (memory, 2026-08-29).
- **File tools** (`Write`, `Edit` and the rest, via `_PATH_KEYS`). They already call `_where`
  directly, so a `file_path` of `..` is judged today.

## Impact

- **Code:** `hub/hub/mcp_server.py`, rule 4 of `_judge_word` only. No change to `_lex`, `_words`,
  `_where` or `_judge_path`.
- **Tests:** `hub/tests/test_permission_approver.py`: P7 flips, and new parametrised rows are added.
- **Runtime:** the approver runs inside the agent's MCP server process. It needs no Hub restart and
  no migration. No UI bundle changes, so nothing reaches `:8000` on reload. A run picks up the change
  when its MCP server next starts.
- **Operator-visible:** more refusals for commands that already leave the workspace (`cd ..`,
  `ls ~`). Each refusal names the word and why.
