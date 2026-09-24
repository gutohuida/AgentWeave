# Proposal — the shell judge reads a word whole

**Round 1, 2026-09-24** (bundle B4, spec track S3). Findings: **F362 (B)**, **F403 (B)**.
**Nothing here is implemented.** R2 and R3 must re-derive it before any task starts, and the
operator must approve it (`spec-queue/APPROVALS.md`).

**R4, 2026-09-24 (revise round, after the operator's review).** The Opus review found that R3's
piece reading let a glob reach outside through a link (`cp n u*/`, measured writing outside in Git
Bash). The operator sent the change back. Steps 9 to 12 below are R4's, and steps 4, 6 and 8 are
revised. See `design.md`, "Operator review, 2026-09-24".

**R5, 2026-09-24 (independent verification).** The argument holds. Seven places could not fire or
could not end as written, and are fixed in the design, with tests:

- an absolute glob skipped D8 (`cp n C:/…/ws/u*/`, allowed today, measured);
- a glob after `@` or `:` was globbed from the wrong directory;
- PowerShell's `*` matches dot names, and R4 applied bash's dot rule to it;
- the escape levels could not end on a final backslash;
- `scp n user@example.com:` lost its colon to the trim;
- the bounds were not charged before the cost;
- a `**` walk through a link cycle could not end.

It also named two costs and one residual (design D4, D5, D7).

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
   than a fixed bound is refused as uncheckable. **(R2)** A brace the outer shell leaves literal
   (quoted, escaped, or any brace in PowerShell) is also judged as an inner shell would expand it,
   because `bash -c 'cp n .{,.}/x'` is refused today only by the tail reading step 2 removes.
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
   `/dev` path stay refused. **(R4)** On a Windows host, a piece only as a redirect target: see
   step 11.
5. **(R2) An approver whose judge raises denies with a reason** instead of failing the tool call
   silently (design D6).
6. **A schemeless address in the two forms a program reads as remote is refused as a network
   address**, not as a path: `user@host:path` (scp, git over ssh) and `host:port/…`. Today, with a
   separator, both are refused only by the backstop's false filesystem reason. Without one
   (`git clone git@github.com:repo`) they are allowed. **(R4)** The check runs on the whole word
   before rule 3, so the separator-less form is caught too. The host must be a domain name, an IP
   address or `localhost`, so that `alpine@sha256:…`, `x@npm:y` and `x@workspace:*` are not
   addresses. `host:x/y` stays a path (operator, 2026-09-24). The existing network requirement is
   **modified** to say which schemeless forms it covers.

7. **(R3) Two regressions R2's rules would have let through are closed in step 2:** on a Windows
   host a drive letter's colon is not a break in *either* reading (the Bash tool hands
   `'Z:foo\bar'` to native programs and nested PowerShell; refused today, allowed under R2's bash
   break), and a piece beginning with `~` after a colon is refused as uncheckable (`dd of=c:~/y`,
   which bash expands to the home directory; refused today, allowed under R2's pieces).
8. **(R3) Two escapes allowed today are closed** (design D7): a word holding a backslash is also
   judged with an inner shell's escapes removed (`bash -c 'cp n .\./x'` writes `../x`), and a
   PowerShell provider-qualified path (`…\FileSystem::C:\Windows\x`) is not read as a plain
   relative path. **(R4)** The escapes are removed **level by level, until none is left**, and each
   level is judged as a whole word. `bash -c 'bash -c "cp n .\\./x"'` writes `../x` (measured), is
   allowed today, and is still allowed after one level.

9. **(R4) A glob is also judged by the links it matches** (design D8). Each piece holding `*`, `?`,
   `[` or an extglob group is expanded against the filesystem one directory at a time. A matched
   entry that is a link (a junction included) is judged by where it resolves. This is bounded at
   8192 directory entries per call and refused past the bound. It closes the regression R3
   introduced: `cp n u*/`, `u?/x` and `[u]p/x`, with `up` a link pointing outside, are refused today
   only by the tail and were allowed under R3.
10. **(R4) An extglob group is one glob unit** (design D3). `@(..)/x` is judged as `../x`, not as the
    piece `..)/x`.
11. **(R4) On Windows, the device exemption covers only a whole word or a redirect target**
    (design D4). `python -c "open('/dev/null','w')"` opens `C:\dev\null` and stays refused.
12. **(R4) The bounds are per call, with a memo** (design, "The bounds"), and **the Windows rules run
    in a Windows CI job** (design D9).

## What does not change

- Rules 1, 2, 4 and 5, the lexer's quote and ANSI-C handling, `_where`, `_judge_path` and the
  refusal-length bound. **(R4)** One step is inserted between rules 2 and 3: the schemeless-address
  check (step 6).
- Every separator-less word (rule 4): `..` alone, `~` and option-joined values stay as F375 left
  them. `a-drive-or-a-home-variable-names-a-directory-by-itself` changes rule 4 separately and
  **(R4) builds after this change**, because it reuses step 9's `_glob_links`.
- A word with a separator and an expansion is still refused as uncheckable (rule 3).

## Residuals, kept on purpose

- (R3) A quoted JSON array of nine or more objects with commas (`curl -d '[{"a":1,"b":2},…]'`) is
  refused as too many brace alternatives, spaces or not.
- (R4) A glob over a directory of more than 8192 entries is refused as too many to check.
- (R3) An inner shell's ANSI-C string spelling `..` with no separator
  (`bash -c "cp n \$'\\x2e\\x2e'"`) is allowed, today and after: rule 4 reads the literal `$'…'`.
- (R4) An inner shell's `case` arm executing a path straight after `)`
  (`sh -c 'case 1 in 1)../../evil.sh;;esac'`) is refused today and allowed after, because `)` is
  not a break (regex back-references keep that allowed). It executes and cannot write. Design Open
  Question 1.
- (R4) `**` is matched as `*` unless the command names `globstar`, so a program's own recursive
  glob through a link two or more levels down is not seen.
- (R4) `host:x/y` and `user@alias:path` (a dotless host) are read as paths (operator, 2026-09-24).
- Pre-existing, as the review named them: a directory change the text does not name
  as a path; `CDPATH=.:..`; cmd's caret escape (`echo "copy n .^.\x" | cmd`); `cmd /v:on` with `!X!`;
  paths computed inside code (`python -c`, PowerShell `(Split-Path (pwd))`); and a hard link.
- `cp n '.{,.}'/x` (a file literally named `.{,.}` in a directory): refused, because an inner shell
  would expand the pattern (R2).
- (R5) On Windows, an inner PowerShell's or `cmd`'s `> /dev/null` (`powershell -c 'echo x > /dev/null'`)
  is allowed after and refused today. It writes `\dev\null` only if that directory exists. Design
  Open Question 2.
- (R5) `grep -rn '\.\./' src` on POSIX (the escape levels read `../`), and an scp-style address
  written as text in an `echo` or a commit message, are refused.
- `grep -c '</script>' a.html`: the trimmed word is `/script`, refused by rule 5. `<` before `/` is
  an input redirect to any inner shell, so it stays refused.
- `gcc -Iinclude/x`, `tar -xvf/tmp/a.tar`: which letters of a glued option take a value is the
  program's business. The option run is read greedily, as F375's D7 reads it, so `-Iinclude/x` is
  refused as `'/x'`; `-I include/x` and `-I./include/x` are allowed.
- `awk -F/`, `cut -d/`: the glued value `/` is the root directory, refused as it would be alone.
- `grep -rn "import .*/utils" src`: `.*` is judged as `..`; a regex spelled like a glob is refused.
- `awk '{print $1/2}'`: rule 3 (a separator and a `$`), unchanged.
- (R4, replacing R3's line) A glob that matches a link inside the workspace pointing outside is
  **refused** (step 9). In a worktree whose `node_modules`, `.venv` or `venv` is the Hub's shared
  link to the project checkout, every path through it is refused today already. Globs through it now
  are too. See design Risks and Open Question 3.

## Findings

- **F362**: fixed by steps 2 to 4, 6 and 9 to 11. Step 5 (R2) makes the judge fail closed visibly.
- **F403**: fixed by step 1.
- The change touches `hub/hub/mcp_server.py` and its tests, plus one CI job
  (`.github/workflows/ci.yml`). No migration, no UI bundle, no Hub restart. **An edit reaches the
  operator's `:8000` agents on their next run, committed or not** (`.claude/rules/mcp-server.md`),
  so the implementing session tells the operator first.

## Impact

- **Code:** `hub/hub/mcp_server.py`:
  - `_lex`, `_read_command`, `_decide` (the per-call budget and memo);
  - `_judge_word` (rule 6, and the address step before rule 3);
  - new `_expand_braces` and `_glob_links`;
  - patterns beside `_ABSOLUTE_PATH_RE`, and `_DRIVE_LETTERS`;
  - `approve_tool_call` (D6).
- **CI:** a `hub-judge-windows` job on `windows-latest` runs the judge's two test files (design D9).
- **Tests:** `hub/tests/test_permission_approver.py` (rows X4, X5 and X6 flip to allowed; N5, N6, G3,
  E11, Z1 and Z2 keep refused with a truer reason); a new
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, with a link fixture (`os.symlink` on
  POSIX, `_winapi.CreateJunction` on Windows).
- **Spec:** `agent-run-sandboxing`. **Modified:** the shell-path requirement; (R4) "A posture exists
  in which the workspace boundary is enforced per tool call" (globs are judged by their matches;
  the shell scope stated), and "A network address in a shell command is decided as a network
  address" (which schemeless forms are addresses, and that other colon forms are read as paths).
  **Added:** brace expansion. R3's added schemeless-address requirement is folded into the modified
  network one.
- **Order:** it must ship before, or with, any change that loosens rule 6 further. It also ships
  before `a-drive-or-a-home-variable-names-a-directory-by-itself`, which uses `_glob_links`.
