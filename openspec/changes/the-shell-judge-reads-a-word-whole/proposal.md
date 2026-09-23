# Proposal — the shell judge reads a word whole

**Round 1, 2026-09-24** (bundle B4, spec track S3). Findings: **F362 (B)**, **F403 (B)**.
**Nothing here is implemented.** R2 and R3 must re-derive it before any task starts, and the
operator must approve it (`spec-queue/APPROVALS.md`).

## Why

Under the default posture every shell command an agent runs is read by `mcp_server._decide`, and
each word is judged by the first of six rules in `_judge_word` (`hub/hub/mcp_server.py:1226-1268`).
Rule 6, the backstop (`:1261-1267`), handles every word that has a separator but is not a *plain*
path. It runs `_ABSOLUTE_PATH_RE` (`:1023-1026`) over the word, and that regex opens a candidate at
**every** separator, including one in the middle of a relative name. So the tail of an ordinary
relative word is judged as a path at the root of the drive and refused as *outside your
workspace*. It does this on both platforms: the POSIX branch of the regex also opens at any `/`.

F362 measured **262 refusals** on one real project (LoopEngine, `:8000`, read-only), each costing a
retry and some pushing agents into worse workarounds. Measured again at HEAD `ce086b6`, with
`_decide` in-process and `AW_WORKSPACE_DIR` a scratch `b4ws`:

| Command | Today | What it names |
|---|---|---|
| `ls test/*.test.js`, `grep -r foo src/*.py` | deny `'/*.test.js'`, `'/*.py'` | files inside |
| `find . -path './src/*' -name x` | deny `'/src/*'` | a pattern |
| `npm install @types/node`, `ls node_modules/@babel/core` | deny `'/node'`, `'/@babel/core'` | a package; a path inside |
| `git show HEAD:src/a.py` | deny `'/a.py'` | a git object |
| `git log --format=%h/%s`, `printf '%s/%s' a b`, `echo 50%/60%` | deny `'/%s'`, `'/60%'` | not paths |
| `sed -E 's/(foo)/\1/' f` | deny `'/(foo'` | a regex |
| `python -c 'print(1/2)'` | deny `'/2'` | a division |
| `mkdir -p src/{a,b}` | deny `'/{a'` | two directories inside |
| `ls 2>/dev/null`, `cmd >/dev/null 2>&1` | deny `'/dev/null'` | the null device |
| `Get-ChildItem src\*.py` (PowerShell) | deny `'\\*.py'` | files inside |

Two of those are archived residuals the operator never decided: `a-url-is-not-a-path` left X4
(`/dev/null`) as an open question (its design D10.2), and X5 (`src/*.py`) refused because *bash's
`.*` can match `..`* (its D8).

The same backstop is also what refuses a brace pattern that leaves: `cp notes.md .{,.}/x` expands to
`./x ../x`, and today it is refused only because the backstop reads `/x` out of `.}/x`. The judge
does not model brace expansion at all (F403), so **the whole-word fix below, shipped alone, would
let `.{,.}/x` and `src/{a,..}/../y` through** (measured with a prototype: both flip to allow). The
two findings therefore ship as one change. F403's own shapes, `cp notes.md .{,.}` and
`{.,.}.`, which land in the parent today and are allowed, are closed by the same step.

## What changes

1. **A bash word's brace patterns are expanded before its words are judged (F403).** The bash
   lexer marks the braces and commas it would expand (not quoted, not escaped, not `${`), and each
   argument is judged as every word its brace patterns expand to. A pattern with more alternatives
   than a fixed bound is refused as uncheckable. PowerShell has no brace expansion and is unchanged.
2. **Rule 6 reads a non-plain word as the pieces a shell could take from it, never from the middle of
   a name (F362).** The word is divided at the characters where another path can begin: the shell's
   own metacharacters that survive lexing (`<`, `>`, `|`, `;`, `&`, `(`), a quote, and the prefixes a
   path can be glued to (`@`, `:`, and a leading short option such as `-o` or `-I`). Each piece is
   judged as the path it spells, resolved against the workspace, and so is the word with its inner
   quotes removed (what an inner `sh -c` would join). A separator that continues a name is not the
   start of a path.
3. **A glob component that could match the parent directory is judged as the parent.** A path
   component that begins with `.` and whose pattern matches `..` (`.*`, `..*`, `.?`, `.[.]`) is
   judged as `..`, so `ls .*/x` and `rm -rf ../*` stay refused and `ls src/*.py` is allowed.
4. **In bash, the null device and the standard streams may be named** (`/dev/null`, `/dev/stdin`,
   `/dev/stdout`, `/dev/stderr`), as whole words or as a piece. `/dev/tcp/…` and every other
   `/dev` path stay refused.
5. **A schemeless address in the two forms a program reads as remote is refused as a network
   address**, not as a path: `user@host:path` (scp, git over ssh) and `host:port/…`. Today both are
   refused only by the backstop's false filesystem reason (`a-url-is-not-a-path` D3 named this a
   residual). Without this step the whole-word reading would allow them.

## What does not change

- Rules 1 to 5, the lexer's quote and ANSI-C handling, `_where`, `_judge_path` and the
  refusal-length bound.
- Every separator-less word (rule 4); `..` alone, `~` and option-joined values stay as F375 left
  them. `a-drive-or-a-home-variable-names-a-directory-by-itself` changes rule 4 separately.
- A word with a separator and an expansion is still refused as uncheckable (rule 3).

## Residuals, kept on purpose

- `grep -c '</script>' a.html`: the trimmed word is `/script`, refused by rule 5. `<` before `/` is
  an input redirect to any inner shell, so it stays refused.
- `gcc -Iinclude/x`, `tar -xvf/tmp/a.tar`: which letters of a glued option take a value is the
  program's business. The option run is read greedily, as F375's D7 reads it, so `-Iinclude/x` is
  refused as `'/x'`; `-I include/x` and `-I./include/x` are allowed.
- `awk -F/`, `cut -d/`: the glued value `/` is the root directory, refused as it would be alone.
- `grep -rn "import .*/utils" src`: `.*` is judged as `..`; a regex spelled like a glob is refused.
- `awk '{print $1/2}'`: rule 3 (a separator and a `$`), unchanged.
- A glob that matches a symbolic link inside the workspace pointing outside is judged by its
  literal text, not by its matches. A named link is still resolved (`_where`).

## Findings

- **F362** — fixed by steps 2 to 5.
- **F403** — fixed by step 1.
- The changes are in one file, `hub/hub/mcp_server.py`, plus its tests. No migration, no UI bundle,
  no Hub restart. **An edit reaches the operator's `:8000` agents on their next run, committed or
  not** (`.claude/rules/mcp-server.md`), so the implementing session tells the operator first.

## Impact

- **Code:** `hub/hub/mcp_server.py` — `_lex`, `_read_command`, `_judge_word` rule 6, three new
  patterns beside `_ABSOLUTE_PATH_RE`.
- **Tests:** `hub/tests/test_permission_approver.py` (rows X4, X5 and X6 flip to allowed; N5, N6, G3,
  E11, Z1 and Z2 keep refused with a truer reason); a new
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`.
- **Spec:** `agent-run-sandboxing` — the shell-path requirement is modified; brace expansion and
  schemeless addresses are added.
- **Order:** independent of the other three B4 changes. It must ship before, or with, any change
  that loosens rule 6 further.
