# Design — the shell judge reads a word whole

**Built on the recommended answer to D4** (the built-in default posture for a Claude run stays
`workspace`, so this judge decides every unattended shell command). If the operator answers D4
with `acceptEdits` instead, this change still holds — the judge still decides every run under
"Workspace only" and every card verdict (`an-ask-me-card-says-what-workspace-only-would-decide`) —
but its reach falls from "every run" to "runs that chose the posture". **D5 does not bear on it:**
nothing here touches a separator-less word.

**R1, 2026-09-24.** Every file:line was read at `ce086b6`. "Measured" means `hub.mcp_server._decide`
called in-process with `AW_WORKSPACE_DIR` a scratch `…/Temp/b4ws` (Windows, Python 3.11), or a real
Git Bash 5.2.37 (msys, `globskipdots on`). The prototype is an out-of-repo pytest plugin that swaps
`_judge_word` after collection (`/tmp/b4proto/b4plugin.py`, session scratch; not committed). It
implements D2-D5 below but **not** D1 (brace expansion), so its brace rows show the regression D1
exists to prevent.

## Context

- `_words` (`mcp_server.py:1484-1499`) splits each lexed argument at `[\s=,]+` and trims
  `_WORD_TRIM` (`"\"'`{}[]()<>|;&:"`, `:1054`) from both ends.
- `_judge_word` (`:1226-1268`): rule 1 URL (`:1230`), rule 2 `$HUB_URL` (`:1233`), rule 3 a separator
  plus an expansion is uncheckable (`:1241`), rule 4 no separator (`:1243-1258`), rule 5 absolute or
  `_PLAIN_RELATIVE_RE` (`:1259`), rule 6 the backstop (`:1261-1267`).
- `_PLAIN_RELATIVE_RE` (`:1038-1042`) excludes `"'`{}[]()<>|;&@*?%` and NUL everywhere, and `:` in
  the first segment (`_PLAIN_RELATIVE_EVERYWHERE`, `:1037`).
- `_ABSOLUTE_PATH_RE` (`:1023-1026`): on Windows `(?:[A-Za-z]:[\\/]|[\\/])[^\s"'|;&><)]*`, on POSIX
  `(?:[A-Za-z]:[\\/]|/)…`. Both open at any separator anywhere in the word.
- `_where` (`:1107-1127`) is total: `OSError`/`ValueError` become `_UNRESOLVED`, a drive mismatch
  becomes `_OUTSIDE`. `_judge_path` (`:1142-1158`) adds the `continues` extension.
- `approve_tool_call` (`:1692-1716`) calls `_decide` at `:1708` with no `try`. Anything new here must
  be total, or the approval surfaces to Claude as a failed MCP call.
- `_lex` (`:1397-1481`) never treats `{`, `,` or `}` specially.

## Decisions

### D1 — Brace expansion is modelled in the bash lexer (F403)

`_lex(bash=True)` marks an unquoted, unescaped `{`, `,` and `}` with three private-use sentinels, the
way it already marks a quoted `$` with `_LITERAL_DOLLAR` (`:1075`). A `{` directly after a real `$`
opens a parameter expansion, not a brace pattern, and its contents up to the matching `}` are
literal. A new `_expand_braces(argument) -> Optional[List[str]]` applies bash's rule to a marked
argument: a `{…}` group expands when it holds a top-level sentinel comma (`{a,b}`), or is a sequence
`{x..y}` of two integers or two single letters; any other marked brace is restored as a literal
character. Groups nest, and a preamble and a postscript are distributed (`a{b,c}d` → `abd acd`).

- **A sequence is replaced by one representative** (its first endpoint). Its elements are integers
  or single letters, so none of them can be `..`, `~` or contain a separator, and each would be
  judged alike. This keeps `{1..1000}` from costing a thousand judgements.
- **Bounded.** Past 256 alternatives for one argument, `_expand_braces` returns `None` and
  `_read_command` refuses the word as uncheckable with a new reason, `_TOO_MANY_BRACES` ("expands to
  more words than can be checked…"). Refusing is the only total answer that cannot allow an unseen
  word.
- **Then the words.** `_read_command` (`:1502-1534`) calls `_words` on each alternative, as bash
  hands each alternative on as its own word. Unexpanded literal braces reach `_words` as today.

Measured in Git Bash 5.2.37: `echo .{,.}/x` → `./x ../x`; `{.,.}./x` → `../x ../x`;
`src/{a,..}/../y` → `src/a/../y src/../../y`; `'.{,.}'/x` and `.\{,.}/x` → literal `.{,.}/x`;
`${HOME:0:3}{a,b}` → `/c/a /c/b`; `{..}` → literal `{..}`; `{a,{b,c}}d` → `ad bd cd`;
`cp notes.md .{,.}/` put `notes.md` in the parent.

**Totality:** string operations on a `str`, bounded recursion (nesting is bounded by the argument's
length and by the 256 cap). R2 must confirm that the expander cannot recurse past Python's limit on
a pathological `{{{{…` (it should iterate or bail to `None`).

**PowerShell is untouched.** `{…}` is a script block there and `,` an array operator.

### D2 — Rule 6 judges pieces, not tails (F362)

Rule 6 is replaced. For a word that reached it (a separator, no expansion, not plain, not absolute):

1. If a schemeless address matches (D5), refuse as a network address.
2. If the word begins with `-` and `_GLUED_OPTION_RE` (`:1048`) matches, drop that option run; what
   follows is the value.
3. Split the value at `_PIECE_BREAKS` = `[<>|;&(@:\s'"`]+` and judge each non-empty piece.
4. Also remove the quote characters `'"`` from the value, split at the same breaks less the quotes,
   and judge each piece.
5. Each piece: a NUL anywhere refuses it as `_UNRESOLVED` (keeps row X8); a bash device (D4)
   stands; otherwise its `..`-capable glob components are rewritten (D3) and it goes through
   `_judge_path(rewritten, root, piece, argument, continues and <piece is last>)`.

Why each break is there:

- `< > | ; &` survive lexing only when quoted. They matter to an **inner shell**
  (`sh -c "echo hi>../x"`, measured refused today by the tail `/x` and still refused by the piece
  `../x`).
- `(` opens a subshell or a call (`print(1/2)`, `open('../x','w')`). `)` is deliberately **not** a
  break: in bash nothing but a `case` pattern can start a word right after `)`, and breaking there
  refuses every regex back-reference (`s/(foo)/\1/` was one of F362's measured refusals).
- `'` `"` `` ` ``: a quoted literal inside a script is a path the script opens. Row H11 (F301's
  `python -c` with `'/api/v1/…'`) depends on this: without the quote break the prototype allowed
  it. With it, H11 stays refused with its current reason.
- The quote-removed reading (step 4) is what an inner shell joins: `sh -c "echo hi > '.'./x"` (row
  E11) is `../x`. Without it the prototype allowed E11.
- `@` and `:` are where a path is glued to a host, a revision or a curl `name@file`
  (`-F file=@/etc/passwd`, `host:/x`). Split there, `HEAD:src/a.py` is `HEAD` and `src/a.py`, both
  inside; `host:/x` yields `/x`, refused as today.

**Measured with the prototype** (D2-D5, no D1), eight test files that reach the judge
(`test_permission_approver`, `test_workspace_writes`, `test_codex_posture_ordering`,
`test_mcp_server`, `test_a_write_outside_the_workspace_is_recorded`, `test_agent_evidence_grant`,
`test_flow_width`, `test_a_held_agent_is_busy`): **9 failed, 445 passed, 1 skipped**. The nine are
exactly the intended moves:

| Row | Today | After |
|---|---|---|
| X4 `cmd 2>/dev/null` | deny `'/dev/null'` | allow (D4) |
| X5 `python src/*.py` | deny `'/*.py'` | allow |
| X6 `git show HEAD:sub/hello.py` | deny `'/hello.py'` | allow |
| N5 `curl -s 127.0.0.1:9/x` | deny `'/x'` | deny, network (D5) |
| N6 `git clone git@github.com:o/r.git` | deny `'/r.git'` | deny, network (D5) |
| G3 `gcc -I../include x.c` | deny `'/include'` | deny `'../include'` |
| E11 `sh -c "echo hi > '.'./stray.txt"` | deny `'/stray.txt'` | deny `'../stray.txt'` |
| Z1 `sort -o"..\stray.txt"` (Windows) | deny `'\\stray.txt'` | deny `'..\\stray.txt'` |
| Z2 `curl -o"..\out" …` (Windows) | deny `'\\out'` | deny `'..\\out'` |

A 60-command sweep (session scratch) moved these to allowed and nothing else:
`ls test/*.test.js`, `grep -r foo src/*.py`, `find . -path './src/*'`, `npm install @types/node`,
`ls node_modules/@babel/core`, `git log --format=%h/%s`, `git show HEAD~2:src/a.py`,
`printf '%s/%s'`, `python -c 'print(1/2)'`, `echo 'a/b(c)/d'`, `sed -E 's/(foo)/\1/'`,
`sed 's/\(a\)b/\1/'`, `grep -E '^(a|b)/c'`, `rg 'foo(bar)/baz'`, `mkdir -p src/{a,b}`,
`ls src/?.ts src/[ab].ts`, `gcc -I./include/x`, `echo 50%/60%`, `scp a host:x/y`, `echo a:b/c`,
`ls sub/.*/x`, PowerShell `Get-ChildItem src\*.py` and `Select-String -Path src\*.ts`. Every escape
in the sweep stayed refused: `ls ../*`, `rm -rf ../*.py`, `ls .*/x`, `ls ..*/x`, `ls a(b/../../x`,
`cp x @../y`, `cp x -t../y`, `curl -o/tmp/x`, `curl -F file=@/etc/passwd`, `tar -xvf/tmp/a.tar`,
`sh -c 'cat</etc/passwd'`, `python -c "open('/etc/x','w')"`, `node -e "…('../x',…)"`,
`scp a host:/x`, `docker run -v data:/app`, `cat /dev/tcp/1.2.3.4/80`, PowerShell `Get-ChildItem ..\*`.

**Without D1, three escapes regress** (prototype): `cp notes.md .{,.}/x`, `{.,.}./x` and
`cp x src/{a,..}/../y` move from deny to allow. D1 turns each into words rule 4/5 already refuse.
Task 2.1 builds D1 first for that reason.

**Alternative rejected: a lookbehind on `_ABSOLUTE_PATH_RE`** (open a candidate only after glue).
It is smaller, but it regresses E11 and `sh -c "echo hi>../x"` (a relative traversal after `>`),
and still needs the whole-word judgement for `a(b/../../x`. **Alternative rejected: anchoring the
regex to word starts** — `a-url-is-not-a-path` D8(b); it lets G1-G4 through. D2 keeps G1-G4 refused
through the glued-option and `@` breaks.

### D3 — A glob component that could match `..` is judged as `..`

`a-url-is-not-a-path` kept `*`/`?` out of rule 5 because *bash's `.*` can match `..`*. In Git Bash
5.2.37 `globskipdots` is on (F375 design measured `echo .*` printing no `..`), but it is off in
bash before 5.2 (Ubuntu 22.04 ships 5.1). So a component that begins with `.`, contains `*`, `?` or
`[`, and for which `fnmatch.fnmatchcase("..", component)` is true, is replaced by `..` before
`_judge_path`; the refusal still quotes the piece as written. `*` and `?*` never match a dot-leading
name in bash, so they are not rewritten. `..?` needs a third character and is not rewritten either
(measured: `sub/..?/y` allowed; `.[.]/y`, `.*/x`, `..*/x` refused).

`fnmatch.fnmatchcase` translates to a regex and escapes what it cannot parse; R2 must confirm it
cannot raise for an unbalanced `[` (totality).

### D4 — The null device and standard streams may be named, in bash only

`X4` was left open in `a-url-is-not-a-path` D10.2 as *"a containment decision"*. It is decided here:
writing to `/dev/null` or a standard stream lands nowhere in the filesystem, and F362 counted 15
refusals of `2>/dev/null`. The allowed set is exactly `/dev/null`, `/dev/stdin`, `/dev/stdout`,
`/dev/stderr`, as a whole word (before rule 5) or as a D2 piece, and only in the bash dialect. Git
Bash maps them; Windows PowerShell 5.1 would try `C:\dev\null`, so the PowerShell reading still
refuses (and an unknown tool, read both ways, is refused by that reading). `/dev/tcp/host/port`,
`/dev/fd/N` and `/dev/sda` stay refused.

### D5 — `user@host:path` and `host:port/…` are network addresses

Without D2's backstop reading, N5 and N6 would be allowed as relative paths, which the network
requirement forbids ("SHALL be allowed only when that address is the run's own Hub").
`a-url-is-not-a-path` D3 noted that recognising these was small and left them as residuals refused
for a false reason. Two anchored patterns on the whole word:

- `^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+:` — scp and git over ssh (`git@github.com:o/r.git`).
- `^[A-Za-z0-9.-]+:[0-9]+(?:[/\\]|$)` — a host and port (`127.0.0.1:9/x`, `localhost:8016/x`).

A port with no separator after it (`-p 8080:80`, `redis:6`) never reaches rule 6 (no separator), so
D3's worry about those does not arise. `docker run -v data:/app` still reaches the `:` break and is
refused as `'/app'`, as today. `host:x/y` (scp to a relative remote path) is allowed after this
change: it has no user and no port, and it reads as a relative path, the same call D3 made for N3
(`example.com/x`). R2 should weigh refusing any `name:path` whose first segment looks like a host.

The reason is `_NETWORK` unchanged, naming the whole word. Addresses naming the run's own Hub
without a scheme are refused too; `_is_own_hub` needs a scheme and the instructed spelling
(`$HUB_URL`) carries one.

## What each changed route returns when something raises

No HTTP route changes. `approve_tool_call` returns whatever `_decide` returns and has no `try`
(`:1708`); every added step is string work, `fnmatch`, and `_judge_path` (total). An exception here
would reach Claude as a failed tool call, which the model reports as a broken approval system — so
the tasks include a totality test over adversarial words (task 1.6).

## Risks

- **The change reaches `:8000` before any commit** (`agent_trigger.py` starts the run's MCP server
  from this checkout; `.claude/rules/mcp-server.md`). Task 0.3.
- **Other bundles may edit `mcp_server.py`** in the same window (B12's F363 touches
  `read_spec_document`). No overlapping function; rebase at build time.
- **A regex written like a glob with a leading dot** (`.*/utils`) is refused as `..`. Accepted; the
  reason quotes it.

## Open questions

1. D5's `host:x/y`: accept the widening (recommended, consistent with N3) or refuse
   `name:relative/path` as a network address?
2. D4's set: the four names, or `/dev/null` alone (the only one measured in F362)?
