# Design — the shell judge reads a word whole

## Operator review, 2026-09-24

The operator sent this change back as **REVISING** after an Opus adversarial pre-approval review
(`spec-queue/tracks/reviews/B4-2026-09-24.md`, "Change 1"). The review found a **security
regression**: under R3's piece reading, a glob reached outside through a link inside the workspace
(`cp n u*/x`, with `up` a junction pointing outside). It also found an extglob `@(..)` escape, a
mismatch between the spec and the design on `user@host:`, a missing MODIFIED delta for the network
requirement, and no CI coverage for the Windows rules. The operator answered: **expand glob matches
against the filesystem and judge each one** (bounded, refused past the bound), and **allow**
`host:x/y`, with the network requirement modified to say so.

**R4 ran on 2026-09-24 (revise round).** It re-derived the change from `hub/hub/mcp_server.py` at
`b7d976a` rather than patching the review's bullets, and measured with `_decide` in-process in
`py -3.11`, in Git Bash 5.2.37 (`globskipdots on`, `extglob off`) and in Windows PowerShell 5.1.
The workspace was `testbed/scratch/b4-r4/ws`, with a real junction `up` pointing to a sibling `out`.
What changed, each with its measurement below:

- **D8 (new):** a glob is also judged by the links it matches, one directory listing at a time,
  bounded.
- **D3:** an extglob group is one glob unit.
- **D5:** moved in front of rule 3, so that a separator-less `git@github.com:repo` is judged too. It
  is narrowed to hosts that can only be hosts. The ADDED requirement is folded into a MODIFIED
  network requirement.
- **D7:** removes backslash escapes level by level. One level missed
  `bash -c 'bash -c "cp n .\\./x"'`, which is allowed today (measured) and which R3 as written also
  allows.
- **D4:** the device exemption on a Windows host is limited to whole words and redirect targets.
- **D9 (new):** the Windows rules run in a Windows CI job.
- **The bounds** are per `_decide`, with a memo.
- **A MODIFIED delta** is added on the posture requirement, whose scenario "Traversal and links
  cannot escape" R3 broke.

The record is in `spec-queue/tracks/B4.md`, under "R4".

**R5 ran on 2026-09-24 (independent verification).** It re-derived the design from
`hub/hub/mcp_server.py` at `8786289` (no product change since `b7d976a`). It measured with `_decide`
in-process in `py -3.11` (3.11.9), with a real junction `up` and a dot-named junction `.l` pointing
outside, and in Windows PowerShell 5.1. It also counted 42,860 Bash commands from this repository's
own Claude Code transcripts. The argument holds. Seven places could not fire as written, or could
not end, and were fixed:

- **D8 did not reach an absolute glob.** Rule 5 takes every absolute word first, so
  `cp n C:/…/ws/u*/` and `cp n C:/…/ws/.*/x` never reach rule 6. Both are allowed today (measured)
  and stayed allowed under R4. D8 and D3 now also run in rule 5.
- **D8 globbed a word's pieces only, never the whole word.** `@` and `:` are breaks, so
  `node_modules/@s/u*/` was globbed as `s/u*/` from the root. D8 now also globs the whole value.
- **D8's dot rule is bash's.** PowerShell's `*` matches `.l` (measured: `Resolve-Path *`), so in the
  PowerShell dialect a dot-named link, such as a linked `.venv`, would have been missed.
- **D7 could not end on a final backslash.** `src\` has no character after its `\`, so "until no
  backslash is left" never arrives. It now ends when a level changes nothing.
- **D5 missed a trailing colon.** `_words` trims `:`, so `scp n user@example.com:` reaches the
  judge as `user@example.com` (measured: allowed today, and under R4).
- **The bounds are now charged before the cost.** A brace pattern's count is computed before it is
  expanded (`{a,b}` × 40 is 2^40 words). Glob entries are charged as they are read, and each
  directory is listed once per `_decide`, not once per pattern: over this repository's own
  commands, a per-pattern memo spent up to 5,412 entries on one command's root listings.
- **A `**` walk through a link cycle could not end** once listings are memoized, since a memo hit
  charges nothing. A `**` walk now does not descend through a link, as bash's does not.

R5 also added two named residuals and two costs, which are not decisions: an inner PowerShell's
`> /dev/null` (D4), a POSIX `grep '\.\./'`, and a commit message naming `user@host:` (D5).

---

**Built on the recommended answer to D4** (the built-in default posture for a Claude run stays
`workspace`, so this judge decides every unattended shell command). If the operator answers D4
with `acceptEdits` instead, this change still holds — the judge still decides every run under
"Workspace only" and every card verdict (`an-ask-me-card-says-what-workspace-only-would-decide`) —
but its reach falls from "every run" to "runs that chose the posture". **The bundle's decision D5
does not bear on it.** The only separator-less words this change touches are schemeless network
addresses (this design's own D5, a different D5).

**R1, 2026-09-24.** "Measured" means `hub.mcp_server._decide` called in-process with
`AW_WORKSPACE_DIR` a scratch workspace (Windows, Python 3.11), or a real Git Bash 5.2.37 (msys,
`globskipdots on`). R1's prototype (an out-of-repo pytest plugin swapping `_judge_word`, not
committed) implemented D2-D5 but not D1, so its brace rows show the regression D1 exists to prevent.
Functions are cited by name; line numbers drift.

## Context

- `_words` splits each lexed argument at `[\s=,]+` and trims `_WORD_TRIM`
  (`"\"'`{}[]()<>|;&:"`) from both ends.
- `_judge_word`: rule 1 URL (`_URL_SCHEME_RE`), rule 2 `$HUB_URL` (`_HUB_REFERENCE_RE`), rule 3 a
  separator plus an expansion is uncheckable (`_expands`), rule 4 no separator, rule 5 absolute or
  `_PLAIN_RELATIVE_RE`, rule 6 the backstop over `_ABSOLUTE_PATH_RE`.
- `_PLAIN_RELATIVE_RE` excludes `"'`{}[]()<>|;&@*?%` and NUL everywhere
  (`_PLAIN_RELATIVE_EVERYWHERE`), and `:` in the first segment. So **every relative word holding a
  glob character (`*`, `?`, `[`) reaches rule 6**; none is plain. **(R5) An absolute one does not:**
  rule 5 takes it by `os.path.isabs(word)` and resolves the literal text (see D8, "Where it runs").
- `_ABSOLUTE_PATH_RE`: on Windows `(?:[A-Za-z]:[\\/]|[\\/])[^\s"'|;&><)]*`, on POSIX
  `(?:[A-Za-z]:[\\/]|/)…`. Both open at any separator anywhere in the word. **This is also the only
  reason a glob through a link is refused today:** `cp n u*/` is refused as `'/'` and `cp n u?/x` as
  `'/x'` (measured). Neither refusal has anything to do with the link.
- `_where` is total: `OSError`/`ValueError` become `_UNRESOLVED`, a drive mismatch becomes
  `_OUTSIDE`, and `os.path.realpath` resolves symlinks and junctions. `_judge_path` adds the
  `continues` extension.
- `approve_tool_call` calls `_decide` with no `try`, then `_report_decision`, then returns one
  `json.dumps` string.
- `_lex` never treats `{`, `,`, `}`, `*`, `?` or `[` specially. `(` and `)` end an argument in the
  outer shell (`_ARGUMENT_ENDS`).
- `_read_command` recurses into each nested substitution, up to `_MAX_NESTING` (8). Past that it
  falls back to `_ABSOLUTE_PATH_RE` over the whole text. `_decide` calls it once per dialect
  (Bash: one; an unknown tool: two) and once per reading (`c`, `utf8`), so up to four top-level
  reads per call.
- `hub/hub/worktrees.py` links `SHARED_DEPENDENCY_DIRS` (`node_modules`, `.venv`, `venv`) from the
  project checkout into every agent and task worktree (`_symlink_shared_dependencies`). The run's
  workspace is that worktree. So in a project that has them, **these links point outside the
  workspace by construction**. Every path through them is already refused today (rule 5 resolves
  it). D8 extends the same verdict to globs through them. See Risks.

## Decisions

### D1 — Brace expansion is modelled in the bash lexer (F403)

`_lex(bash=True)` marks an unquoted, unescaped `{`, `,` and `}` with three private-use sentinels, the
way it already marks a quoted `$` with `_LITERAL_DOLLAR`. A `{` directly after a real `$`
opens a parameter expansion, not a brace pattern, and its contents up to the matching `}` are
literal. A new `_expand_braces(argument, budget) -> Optional[List[str]]` applies bash's rule to a
marked argument: a `{…}` group expands when it holds a top-level sentinel comma (`{a,b}`), or is a
sequence `{x..y}` of two integers or two single letters; any other marked brace is restored as a
literal character. Groups nest, and a preamble and a postscript are distributed
(`a{b,c}d` → `abd acd`).

- **An integer sequence is replaced by one representative** (its first endpoint). Its elements
  (`{1..1000}`, `{01..10}`, `{-1..1}`, `{1..9..2}`) are an optional sign and digits, so none of them
  can be `..`, `~` or contain a separator, and each would be judged alike.
- **A letter sequence is expanded in full (R2).** Bash's letter range runs over the ASCII codes
  between its endpoints: measured in Git Bash 5.2.37, `echo {Z..a}` prints `Z [`, a backslash,
  `] ^ _`, a backtick and `a`. On Windows the backslash is a separator, so `{Z..a}..` has the
  alternative `\..`, which the judge refuses. At most 58 elements.
- **Bounded, per `_decide` (R4).** See "The bounds" below: 256 alternatives from one argument,
  1024 across the whole `_decide`. Past either, `_expand_braces` returns `None` and the argument is
  refused as `_TOO_MANY`.
- **Then the words.** `_read_command` calls `_words` on each alternative, as bash hands each
  alternative on as its own word. Unexpanded literal braces reach `_words` as today.

Measured in Git Bash 5.2.37: `echo .{,.}/x` → `./x ../x`; `{.,.}./x` → `../x ../x`;
`src/{a,..}/../y` → `src/a/../y src/../../y`; `'.{,.}'/x` and `.\{,.}/x` → literal `.{,.}/x`;
`${HOME:0:3}{a,b}` → `/c/a /c/b`; `{..}` → literal `{..}`; `{a,{b,c}}d` → `ad bd cd`;
`cp notes.md .{,.}/` put `notes.md` in the parent.

**Totality (R2).** The expander must not recurse on nesting depth: an argument of 5000 `{` would
pass Python's recursion limit. Build it iteratively (an explicit stack of groups), or cap nesting at
32 and return `None` past it. `fnmatch.fnmatchcase` was measured total on Python 3.11 for unbalanced
`[`, `.[`, `[[[[.*`, `.[!]`, `.[z-a]`, `.[]`, `.[\`, `.[a-` and for 5000-character components.

**R2: a brace an inner shell will expand is judged as expanded too.** A quoted brace pattern handed
to an inner shell (`bash -c 'cp n .{,.}/x'`) reaches `_words` literal, and under D2 its piece `.}/x`
would be a name inside. So `_read_command` also judges, for an argument holding a brace the outer
shell left literal (quoted, escaped, or any brace in the PowerShell dialect), the words that argument
expands to when **every** brace is treated as bash treats an unquoted one (a `{` after a `$` or a
`_LITERAL_DOLLAR` still opens a parameter expansion). Cost: `cp n '.{,.}'/x` (a file literally named
`.{,.}`) is refused, and inline JSON expands to many harmless words (see the bounds).

**PowerShell's own reading is unchanged** (`{…}` is a script block there and `,` an array
operator); only the inner-shell reading above is added to it.

### D2 — Rule 6 judges pieces, not tails (F362)

Rule 6 is replaced. For a word that reached it (a separator, no expansion, not plain, not absolute,
not a schemeless address — D5 now runs before rule 3):

1. If the word begins with `-` and `_GLUED_OPTION_RE` matches, drop that option run; what follows is
   the value.
2. **(R4)** Mark each extglob group in the value as one glob unit (D3): the characters inside it are
   not breaks.
3. Split the value at `_PIECE_BREAKS` = `[<>|;&(@:\s'"`]+` and judge each non-empty piece.
   **Drive exception (R2, R3):** on a host with drive letters (`_DRIVE_LETTERS`, D9), a `:`
   directly after a single ASCII letter that begins the value or a piece is not a break, in
   **either** dialect. So `Z:foo\bar` and `-Destination:Z:foo\bar` keep one piece `Z:foo\bar`,
   which `_where` resolves on drive Z (outside). A Bash-tool word reaches native Windows programs and
   nested PowerShell too (`python w.py 'Z:foo\bar'`), so the bash reading needs the exception as
   much as the PowerShell reading does. Git Bash's own `cp` writes a file named `Z:` there, so the
   refusal is a harmless false one. On a POSIX host the break stands. Cost: `git show a:src/x.py`
   (a one-letter revision) is refused as drive A on Windows.
4. Also remove the quote characters `'"`` from the value, split at the same breaks less the quotes,
   and judge each piece: this is what an inner shell joins.
5. Each piece:
   - A NUL anywhere refuses it as `_UNRESOLVED` (row X8).
   - A piece that begins with `~`, or a drive piece whose text after the colon does, is refused as
     `_UNCHECKED` (R3). Bash expands a tilde after `:` in an assignment-shaped argument (measured:
     `echo of=c:~/y` prints `of=c:/c/Users/huida/y`).
   - A bash device stands (D4).
   - Otherwise its `..`-capable glob components are rewritten (D3), and it goes through
     `_judge_path(rewritten, root, piece, argument, continues and <piece is last>)`.
   - **(R4)** Then, if it holds a glob character, it goes through the link expansion of D8.

Why each break is there:

- `< > | ; &` survive lexing only when quoted. They matter to an **inner shell**
  (`sh -c "echo hi>../x"`).
- `(` opens a subshell or a call (`print(1/2)`, `open('../x','w')`). **`)` is deliberately not a
  break**, except where it closes an extglob group (D3). Breaking at every `)` refuses every regex
  back-reference (`s/(foo)/\1/`, `rg 'foo(bar)/baz'`, `grep -E '^(a|b)/c'`: each would read
  `/\1/`, `/baz` or `/c` as a path at the root). Those were among F362's measured refusals. **What
  this costs (R4, from the review):** an inner shell's `case` arm can put a command word straight
  after `)`. `sh -c 'case 1 in 1)../../evil.sh;;esac'` is refused today by the tail
  `'/../evil.sh'` (measured) and is **allowed** after: the piece `1)../../evil.sh` is a name inside.
  It **executes** a file outside. It cannot write one: a redirect there meets the `>` break, and an
  argument meets whitespace. This is operator question 1.
- `'` `"` `` ` ``: a quoted literal inside a script is a path the script opens (row H11).
- `@` and `:` are where a path is glued to a host, a revision or a curl `name@file`
  (`-F file=@/etc/passwd`, `host:/x`). Split there, `HEAD:src/a.py` is `HEAD` and `src/a.py`, both
  inside, and `host:/x` yields `/x`, refused as it is today.

**R1's prototype measurement (D2-D5, no D1)**, over eight test files: 9 failed, 445 passed,
1 skipped. The nine were exactly the intended moves:

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

The 60-command sweep moved these to allowed and nothing else: `ls test/*.test.js`,
`grep -r foo src/*.py`, `find . -path './src/*'`, `npm install @types/node`,
`ls node_modules/@babel/core` (R4: only where `node_modules` is not a link; see Risks),
`git log --format=%h/%s`, `git show HEAD~2:src/a.py`, `printf '%s/%s'`, `python -c 'print(1/2)'`,
`echo 'a/b(c)/d'`, `sed -E 's/(foo)/\1/'`, `sed 's/\(a\)b/\1/'`, `grep -E '^(a|b)/c'`,
`rg 'foo(bar)/baz'`, `mkdir -p src/{a,b}`, `ls src/?.ts src/[ab].ts`, `gcc -I./include/x`,
`echo 50%/60%`, `scp a host:x/y`, `echo a:b/c`, `ls sub/.*/x`, PowerShell `Get-ChildItem src\*.py`
and `Select-String -Path src\*.ts`. **R4: the glob rows among them stay allowed only while no link
out of the workspace matches them (D8).**

**Without D1, three escapes regress** (prototype): `cp notes.md .{,.}/x`, `{.,.}./x` and
`cp x src/{a,..}/../y`. **Without D8, globs through links regress** (R4, below). Neither step may be
built after D2.

**Alternatives rejected:** a lookbehind on `_ABSOLUTE_PATH_RE` (regresses E11 and
`sh -c "echo hi>../x"`), and anchoring the regex to word starts (`a-url-is-not-a-path` D8(b); it lets
G1-G4 through).

### D3 — A glob component that could match `..` is judged as `..`; an extglob group is one unit

`a-url-is-not-a-path` kept `*`/`?` out of rule 5 because *bash's `.*` can match `..`*. In Git Bash
5.2.37 `globskipdots` is on, but it is off in bash before 5.2 (Ubuntu 22.04 ships 5.1). So a
component that begins with `.`, contains `*`, `?` or `[`, and for which
`fnmatch.fnmatchcase("..", component)` is true, is replaced by `..` before `_judge_path`. The
refusal still quotes the piece as written. `*` and `?*` never match a dot-leading name in bash, so
they are not rewritten. `..?` needs a third character (measured: `sub/..?/y` allowed; `.[.]/y`,
`.*/x`, `..*/x` refused).

**Extglob (R4, review MEDIUM).** With `extglob` on and `globskipdots` off, `@(..)/x` and
`?(..)/x` expand to `../x` (the review measured this in Git Bash). `bash -O extglob -c 'cp n @(..)/x'`
is refused today only by the tail `'/x'` (measured at `b7d976a`). Under R3's D2 the pieces are
`..)/x`, because `(` and `@` are breaks and `)` is not, and `..)` reads as a name inside, so it
would be **allowed**. So before the split (D2 step 2), each extglob group is found: one of
`@ ? * + !` directly followed by `(`, up to its matching `)`, with nesting counted. An unbalanced
`(` is not a group. Each group is one glob unit, and the `(`, `|`, `@` inside it are not breaks. A
component holding a group is `..`-capable, and rewritten to `..`, when:

- any `|`-separated alternative of any group in it begins with `.`, or
- the component, with each group replaced by `*`, passes the test above.

For D8's matching, each group counts as `*`. Cost: none measured. A regex such as `a*(b)` or `x+(y)`
becomes a harmless glob unit.

`fnmatch.fnmatchcase` translates to a regex and was measured total (D1, Totality).

### D4 — The null device and standard streams may be named, in bash only

`/dev/null`, `/dev/stdin`, `/dev/stdout`, `/dev/stderr`, in the bash dialect, as a whole word
(before rule 5) or as a D2 piece. `/dev/tcp/…`, `/dev/fd/N` and `/dev/sda` stay refused, and the
PowerShell reading still refuses them (PowerShell 5.1 would try `C:\dev\null`).

**R4 (review LOW): on a host with drive letters, only a whole word or a redirect target.** On
Windows only Git Bash maps these names. A native program given one inside a script's own text
opens `C:\dev\null`: `python -c "open('/dev/null','w')"` is refused today, as the tail
`'/dev/null'`, and R3's D4 would allow it as a piece. When the Bash tool hands a *whole* argument
to a native program, msys converts it: `python -c 'import sys;print(sys.argv)' /dev/null x=/dev/null`
prints `['nul', 'x=nul']` (measured). So on a host with drive letters (`_DRIVE_LETTERS`) the
exemption holds for:

- a whole word, which includes the value after `=`, since `_words` splits there;
- a piece that directly follows a `<` or `>` break, which is a redirect target for an inner shell.

A piece after a quote or a `(` is judged as a path. On POSIX `/dev/null` is the device for every
program, so there the exemption also covers every piece.

**What this leaves (R5, measured).** msys converts a whole *argument*, and the exemption is for a
whole *word*. `_words` splits a quoted script at whitespace and trims a leading `>`, so the inner
script's redirect target is a whole word. For `sh -c 'ls >/dev/null 2>&1'` that is right: the inner
shell is msys. For `powershell -c 'echo x > /dev/null'` the inner shell is not msys, and it writes
`\dev\null` on the current drive. That command is refused today (as `'/dev/null'`) and allowed
after. The judge cannot tell which program the quoted script is for. The write fails unless a `\dev`
directory already exists on that drive (`C:\dev` does not exist here). This is a named residual,
put to the operator with Open Question 2.

### D5 — `user@host:` and `host:port/…` are network addresses, decided before rule 3

**R4: where it runs.** R3 ran D5 as the first step of rule 6. Only a word with a separator reaches
rule 6, so `git clone git@github.com:repo` and `scp n user@example.com:file` were never seen. Both
are allowed today (measured) and would have stayed allowed, against a SHALL that said such a word
is refused. R4 runs D5 on the whole word **after rule 2 and before rule 3**, in both dialects. So a
separator-less address is caught, and so is one that also holds an expansion (`git@github.com:$R`).
Like rules 1 and 2, it reads the whole word. `_words` has already split an `=`-joined value
(`--remote=git@…`) into its own word.

**R4: which words.** A word is a network address without a scheme when it matches either pattern:

- `_SCP_ADDRESS_RE` =
  `^[A-Za-z0-9._-]+@(?:localhost|\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+):`. This is a
  user at a host that is a domain name, an IPv4 address, a bracketed IPv6 address or `localhost`,
  then a colon: scp, rsync and git over ssh (`git@github.com:o/r.git`). **The host must be
  unmistakably a host.** Written as `[^:]+`, it caught package-manager and digest forms, which are
  not addresses, and all of them have a dotless name before the colon:
  - `docker pull alpine@sha256:…`, allowed today (measured);
  - `npm i x@npm:y`;
  - `pnpm add x@workspace:*`;
  - `npm i x@file:../lib`, which is refused anyway as the piece `../lib`.

  A dotless ssh alias (`user@myserver:path`) is therefore read as a path. It is the same call the
  operator made for `host:x/y`.
- `_HOST_PORT_RE` = `^[A-Za-z0-9.-]{2,}:[0-9]+[/\\]`. This is a host of two or more characters, a
  port and a separator (`127.0.0.1:9/x`, `localhost:8016/x`). The separator is required, so
  `-p 8080:80`, `redis:6` and `127.0.0.1:8080` stay ordinary words: they have no path, and the
  requirement does not cover them. The two-character floor keeps a Windows drive-relative
  `C:1/x` from reading as a host `C` with port 1.

`host:x/y` (scp to a relative remote path, no user, no port) is **allowed**, as the operator decided
on 2026-09-24. It reads as the relative path `x/y`, which is the same call made for `example.com/x`.
The judge cannot tell a host from a revision (`HEAD:src/a.py`). **That contradicted the existing
network requirement** ("SHALL be allowed only when that address is the run's own Hub"). So that
requirement is MODIFIED here to say which schemeless forms it treats as addresses, and that other
schemeless forms are read as paths. R3's separate ADDED requirement is folded into it, so that one
requirement decides what an address is.

The reason is `_NETWORK` unchanged, naming the whole word. A schemeless address naming the run's own
Hub is refused too: `_is_own_hub` needs a scheme, and the instructed spelling (`$HUB_URL`) carries
one.

**R5: a trailing colon.** `_words` trims `:` from a word's ends, so `scp n user@example.com:` (a
copy to the remote home directory) reaches the judge as `user@example.com`. It is allowed today
(measured), and `_SCP_ADDRESS_RE` as written never sees its colon. So `_words` also yields whether
it trimmed a `:` directly after the word, and D5 matches the word with that colon restored. Over
42,860 Bash commands from this repository's own transcripts, the rule with the colon kept matched
only two words, both `git@github.com:o/r.git` in earlier probes.

**Cost (R5).** The judge cannot tell text from a command, so an `echo`, a `grep` or a commit message
naming an address in this form (`git@github.com:o/r.git`) is refused as a network address, as
`echo '$HOME'` is under the sibling change. Write the message to a file and use `git commit -F`.

### D6 (R2) — an approver that fails denies, with a reason

**Refuse or allow, if the judge raises?** Today: neither, cleanly. The exception propagates out of
`approve_tool_call`, and FastMCP returns it as a tool error. That is never the
`{"behavior": "allow"}` string, so the call is not allowed. But no reason reaches the model, and
`_report_decision` never runs. D1 and D8 add the first code in the judge that could plausibly raise.
Totality tests (1.6) are the first defence. The second is structural: `approve_tool_call` wraps the
`_decide` call in `try/except Exception` and answers
`{"allow": False, "reason": "the workspace check failed on this call (<exception class>); ask the operator with ask_user"}`.
It then reports that like any refusal. Fail closed, visibly.

**Checked against the annotation trap (R3; held by the review).** The `try` wraps only the `_decide`
call and yields the same `{"allow", "reason"}` dict. So the function still returns the one
`json.dumps` string from one exit path and needs no return annotation. `except Exception` covers
`RecursionError` and `MemoryError`. `test_response_carries_no_structured_content` spawns the server
and fails if `structuredContent` appears. The D6 test itself is in-process: it monkeypatches
`_decide` to raise, then asserts a `behavior: deny` naming the failure and that `_report_decision`
was called. D6 must not wrap the operator path: `an-ask-me-card-says-what-workspace-only-would-decide`
catches its own verdict failure.

### D7 (R3, R4) — escapes an inner shell removes, and a provider-qualified path

- **Backslash escapes, every level (R4).** R3 judged a word holding a backslash once more, with each
  `\c` replaced by `c`, because an inner bash removes one level: `bash -c 'cp n .\./x'` writes `../x`
  and is allowed today (measured). **One level is not enough.** A shell between the command and the
  one that writes removes a level of its own: `bash -c 'bash -c "cp n .\\./x"'` makes Git Bash print
  `../x` for `echo` (measured). The judge allows it today, because `.\\./x` is plain and inside on
  Windows. R3 as written also allows it: one level gives `.\./x`, which is still inside. So the
  word is judged at **each** level:
  - Level 1 replaces each `\c` by `c`, scanning left to right. Level 2 does the same to level 1's
    result, and so on **until a level changes nothing** (R5). A final backslash has no character
    after it and stays, so "until no backslash is left" would never end for `src\` or `x\\`,
    and the call would never be answered.
  - Every level at least halves each run of backslashes. So there are at most one more level than
    log2 of the longest run: 17 for a run of 65,536 characters.
  - Each level is judged **as a word, through all of `_judge_word`'s rules**, without a further
    escape-removed reading of its own. It is not judged only as a path. On a POSIX host `\` is not a
    separator, so `bash -c 'bash -c "cp n \$HOME"'` reaches rule 4 as `\$HOME` (on Windows rule 3
    refuses it, because `\` is a separator there). Only the level-1 word `$HOME` lets
    `a-drive-or-a-home-variable-names-a-directory-by-itself` see the directory variable.
  - Each level is an extra reading only. It can add a refusal and never remove one. On Windows
    every path spelled with `\` gains harmless readings (`src\a.py` → `srca.py`).
  - **Cost (R5), POSIX only.** A regular expression that escapes dots to spell a traversal is
    refused: `grep -rn '\.\./' src` reads `../` at level 1. It is allowed today on POSIX. On Windows
    it is refused today already (as `'\\.\\./'`, measured), because `\` opens a root path there.
- **A PowerShell provider-qualified path.** `Copy-Item x Microsoft.PowerShell.Core\FileSystem::C:\Windows\x`
  is allowed today (measured at `b66f6a6`). A word containing `::` is therefore not plain, in either
  dialect, and reaches the piece reading, where `::` is a break. Cost: `lib/Foo::Bar.pm` is read as
  pieces, both of them inside.

Found and handled in the sibling change, all separator-less and so rule 4's:

- `cp x ..*` and `cp x .{,.}*`;
- an expansion that leaves `..` behind, such as `cp n $(true)..` or `cp n $x..` (R4: allowed today,
  measured; Git Bash prints `..` for each);
- a link named by itself, such as `cp n up` (R4: allowed today, measured).

An inner shell's ANSI-C `..` with no separator (`bash -c "cp n \$'\\x2e\\x2e'"`) is a named
residual.

### D8 (R4) — a glob is also judged by the links it matches

**The regression (review HIGH, re-measured).** `up` was a junction in the workspace pointing to a
sibling `out`. In Git Bash, `cp n u*/` copied `n` into `out` (measured). The judge refuses
`cp n u*/`, `u?/x` and `[u]p/x` today only by the tails `'/'` and `'/x'`. Under R3's D2 the piece
`u*/` is judged as the literal name `u*`, which is inside, so all three would be **allowed**. The
spec scenario "Traversal and links cannot escape" (`agent-run-sandboxing`, "A posture exists in
which the workspace boundary is enforced per tool call") would then be false for globs. That is why
this change now carries a MODIFIED delta on that requirement.

**Rule.** Every piece that holds a glob character (`*`, `?`, `[`, or an extglob group) is still
judged by its literal text, as D2 and D3 say. It is **also** expanded against the filesystem by a
new `_glob_links(piece, root, budget)`. This covers every reading the piece is judged in: as
written, quote-removed and escape-removed. An inner shell globs a quoted pattern too
(`bash -c 'cp n u*/'`).

1. **Base.** The piece's leading components that hold no glob character, joined to the root (or
   absolute), resolved with `os.path.realpath`. If the base is outside, the literal judgement has
   already refused.
2. **One component at a time.** List the current directory with `os.scandir`. An entry matches the
   component's *relaxed* pattern under `fnmatch.fnmatchcase` after `os.path.normcase` of both sides.
   Relaxed means:
   - the text from the component's first `[` to its last `]` becomes `*`;
   - each extglob group becomes `*`;
   - `**` is `*`, except when the command's text names `globstar`, in which case `**` matches
     directories at any depth.

   In the bash dialect, a name beginning with `.` matches only when the relaxed component begins
   with `.`, as bash's default (`dotglob` off) does. The rule is dropped when the command's text
   names `dotglob`. **(R5) In the PowerShell dialect there is no such rule**: its wildcards match a
   dot-leading name (measured: `Resolve-Path *` lists `.l`), so a linked `.venv` matches `*` there.
   When D3 says the component can match `..`, `..` is also a candidate.

   Whether the command names `globstar` or `dotglob` is read once per `_decide`, from the whole
   `command` (R5), so that the memo below cannot hold a result from a nested text read under
   different flags.
3. **Links are judged.** A matched entry that is a link is judged by
   `_judge_path(entry.path, root, <piece as written>, argument, False)`. An outside match refuses,
   and `_resolves_elsewhere` names where it lands. An entry is a link when `DirEntry.is_symlink()`
   is true or, on Windows, when it is a reparse point:
   `DirEntry.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT`,
   which is served from the directory listing. **Python 3.11's `is_symlink()` is False for a
   junction** (measured on `up`), so it cannot be the test alone. (R5 re-measured on 3.11.9 with
   two junctions made by `_winapi.CreateJunction`: `is_symlink()` False, `is_dir()` True, the
   reparse-point attribute set, `st_reparse_tag` 0xA0000003, and `realpath` gives the target.) A
   cloud or deduplicated file is a reparse point too; it costs one `realpath`, which resolves to
   itself, inside.
4. **Descend** into a matched directory for the next component, following a link only once it has
   been judged inside. The last component's matches are not descended into. **(R5) A `**` walk
   under `globstar` does not descend through a link** (bash 4.3 and later do not either); it judges
   the link and stops there. Without this, the listing memo below would never end a link cycle
   (`loop` → the workspace): every level is a memo hit, which charges nothing. Each other
   component moves one level, so any other walk ends with its components.
5. **A directory that cannot be listed** (`OSError`, `ValueError`) contributes no matches. The shell
   cannot list it either, and the literal is judged regardless. A glob that matches nothing is passed
   on literally by bash, and the literal is already judged.

**Why only links are resolved.** A non-link entry of a directory that is itself inside is inside by
construction. Only a link, or `..` (D3), can carry a match out. So a glob costs one listing per
directory it enters (about 9 µs per entry on this machine) and one `realpath` per matched link
(about 85 µs), not one `realpath` per match.

**Over-approximation, on purpose.** Folding case, the relaxed brackets and extglob groups, and
matching PowerShell's `-LiteralPath`/`-Destination` values although PowerShell does not expand them
can all match more names than the shell would. For example, `fnmatch` does not match
`[[:alpha:]]p` to `up`, but bash does (measured: `bash -c 'echo [[:alpha:]]p'` prints `up`); the
relaxed `*p` matches it. Matching more names can only add a refusal, and only where a link out of the
workspace exists.

**Where it runs (R5: three places).**

- **In the piece reading (rule 6), on each piece.**
- **In rule 6, also on the whole value** (the word after its option run, and its quote-removed and
  escape-removed readings). `@` and `:` are breaks for the literal reading, but to the shell's
  globbing they are name characters. Globbed piece by piece, `ls node_modules/@s/u*/` is only
  `s/u*/` from the root, and a link at `node_modules/@s/up` is never listed. Matching more names
  can only add a refusal.
- **(R5) In rule 5, on an absolute word that holds a glob character or an extglob group.** Rule 5
  takes every absolute word before rule 6 (`os.path.isabs(word)`), and `_PLAIN_RELATIVE_RE` keeps
  only relative globs out of it. So R4's D8 never saw `cp n C:/…/ws/u*/`, whose base is the
  workspace itself. That command, and `cp n C:/…/ws/.*/x`, are allowed today (measured) and stayed
  allowed under R4. In rule 5 such a word is also rewritten by D3 and then passed through
  `_glob_links`. Step 1's "(or absolute)" base was already written for it.

`a-drive-or-a-home-variable-names-a-directory-by-itself` applies the same `_glob_links` to a
separator-less word (rule 4), where `cp n u*` is allowed today (measured). That change builds after
this one. Until it is built, a separator-less glob is judged as today, by its text alone.

### D9 (R4) — one platform key, and a Windows CI job

`_DRIVE_LETTERS = os.sep == "\\"` is the one constant read by:

- the drive exception in D2 step 3;
- the device limit in D4;
- the sibling change's drive rules.

`_SEPARATORS` and `_ABSOLUTE_PATH_RE` keep their own `os.sep` keys.

**The Windows rules are tested by a Windows CI job, not by monkeypatching the constant on Linux.**
The rows whose truth is Windows' answer depend on `ntpath` resolution:

- `_where` answering drive Z as outside (via `commonpath` raising on another drive);
- junctions resolving through `realpath`;
- `\` being a separator.

On Linux, `_where("Z:foo\\bar")` is a relative file inside. A monkeypatched `_DRIVE_LETTERS` could
only assert which string reached `_judge_path`, not that the call is refused. That is the "passes its
tests and cannot fire" failure `CLAUDE.md` names. So `.github/workflows/ci.yml` gains a job,
`hub-judge-windows`:

- `runs-on: windows-latest`, `working-directory: hub`;
- the same install steps as `hub-test`, through `-c ../constraints-dev.txt`, which
  `tests/test_dev_constraints.py` checks;
- `pytest tests/test_permission_approver.py tests/test_the_shell_judge_reads_a_word_whole.py -v --timeout=300 --timeout-method=thread`.

The `test` job already runs on `windows-latest` for the CLI, so the runner is known to work. The
link fixture uses `os.symlink` on POSIX and `_winapi.CreateJunction` on Windows (no privilege
needed), so the link rows run on both jobs. Production is Windows.

## The bounds (R4: per `_decide`)

One `_Budget` is created by `_decide` and passed through every `_read_command` it makes: both
dialects for an unknown tool, both readings (`c`, `utf8`), and every nested substitution down to
`_MAX_NESTING`. From there it reaches `_expand_braces` and `_glob_links`.

| Bound | Value | Counted |
|---|---|---|
| Brace alternatives from one argument | 256 | per argument expansion |
| Brace alternatives in total | 1024 | across the whole `_decide` |
| Directory entries examined by `_glob_links` | 8192 | across the whole `_decide` |
| Backslash levels (D7) | log2 of the longest run, +1 | per word; each level one judgement |
| Substitution nesting | 8 (`_MAX_NESTING`, unchanged) | per `_read_command` chain |

**A memo keeps the readings from multiplying the cost.** `_decide` keeps one dictionary of word
judgements, keyed by `(word, argument, continues, dialect, trusted)`. It also keeps one of
expansions: brace alternatives keyed by the marked argument text and dialect, and **(R5) directory
listings keyed by the resolved directory**. The budget is charged only on a miss. R4 keyed
`_glob_links` results by base and remaining components, which lists the root once per distinct
pattern. Over 42,860 Bash commands from this repository's own transcripts, one command (a Markdown
heredoc) held 123 distinct separator-less glob words. At 44 root entries, a per-pattern memo would
charge 5,412 of the 8,192, from one listing. A project with a larger root would pass the bound on
ordinary text.

**Each bound is checked before its cost is spent (R5).**

- `_expand_braces` computes an argument's alternative count (the product of each group's size,
  summed over nesting) before it builds any alternative, and returns `None` past either bound.
  Building first and counting after would not end on `{a,b}` repeated 40 times (2^40 words).
- `_glob_links` charges the budget as each directory entry is read from `os.scandir` and stops
  reading at the bound. It does not list a directory first and count it after. The `c` and
`utf8` readings differ only where a `$'…'` escape at or above 0x100 renders differently. So a
second reading of the same text costs lookups, not listings or `realpath` calls. Without the memo,
a per-`_decide` bound of 1024 would leave an unknown tool (four reads) 256 usable alternatives.

**Past any bound the call is denied**, with a new reason `_TOO_MANY`: *"expands to more words or
files than can be checked against your workspace; name the files you mean, or write the payload to a
file"*. It quotes the argument or piece. It is reported by `_report_decision` like any refusal, and
it never allows. Worst case on this machine: 1024 alternatives × two `realpath` (about 175 ms), plus
8192 entries (about 75 ms). The per-word work that exists today is unbounded by count, as it is now.

**What the bounds cost ordinary work** (named, accepted in the Final section's item 5):

- A quoted JSON array of about nine or more two-key objects is refused as too many brace
  alternatives. Spaces do not help: the inner-shell reading expands the whole quoted argument.
  Splitting at whitespace first would let `'{a," b",..}/x'` through.
- A glob over a directory of more than 8192 entries is refused. Every listed entry counts, not only
  the matches.

## What each changed route returns when something raises

No HTTP route changes. `approve_tool_call` is the only entry point, and after D6 it returns a deny
whenever `_decide` raises. The step-by-step:

- `_lex`, `_words`, the extglob scan and `_expand_braces` are string work. `_expand_braces` is
  iterative, so there is no recursion.
- `fnmatch.fnmatchcase` was measured total.
- `_where` and `_judge_path` are total.
- `_glob_links` catches `OSError` and `ValueError` around each `os.scandir` **and its iteration**
  (R5: the iterator can raise part-way through a listing), each `DirEntry.is_dir()` and each
  `DirEntry.stat()`, and treats them as "no match" for that entry or directory.
- The escape-removed readings (D7) end when a level changes nothing, so a final backslash cannot
  loop (R5). It is
  iterative, with an explicit stack, and bounded by the entry budget. (R5) A link cycle ends because a
  `**` walk does not descend through a link (D8 step 4), not at the budget: memo hits charge nothing.
- Budget exhaustion is a return value (`None`, then `_TOO_MANY`), not an exception.
- Anything else, `MemoryError` included, is caught by D6 and becomes a reported deny.

The tasks include a totality test over adversarial words (1.6) and an in-process D6 test.

## Risks

- **The change reaches `:8000` before any commit** (`agent_trigger.py` starts the run's MCP server
  from this checkout; `.claude/rules/mcp-server.md`). Task 0.3.
- **Order against B11's `an-agents-tool-server-is-the-one-its-hub-loaded`** (F354). Either order is
  safe (no Hub-side counterpart). If B11 lands first, task 0.3's warning becomes "on your next
  restart".
- **Linked dependency directories.** In a project with a `node_modules`, `.venv` or `venv`, every
  agent worktree holds a link to the project checkout's copy (`worktrees.py`,
  `_symlink_shared_dependencies`). A path through it already resolves outside and is refused today
  (`ls node_modules/x`, `.venv/bin/python`). D8 adds `ls node_modules/*` and **(R5) any glob whose
  component matches the link's name**: `ls */package.json` in a worktree with a linked
  `node_modules`, and in PowerShell `Get-ChildItem *\x` with a linked `.venv`. The sibling change
  adds the bare `ls node_modules` and a bare `*` (`ls *`, `grep foo *`, `du -sh *`). On this machine no project worktree holds such a link today: all four
  LoopEngine worktrees were checked read-only, and LoopEngine has no `node_modules`. So nothing
  measured moves. This is a candidate finding for the operator. The workspace boundary and the
  shared read-only dependency links disagree, and it is not this change's to settle.
- **Other bundles may edit `mcp_server.py`** in the same window (B12's F363 touches
  `read_spec_document`). No overlapping function; rebase at build time.
- **A regex written like a glob with a leading dot** (`.*/utils`) is refused as `..`. Accepted; the
  reason quotes it.

## Residuals, named

Escapes that exist today and stay, as the review listed them:

- **A directory change the text does not name as a path.** `cd` into a directory computed at run
  time, then a relative path. A link the command names (`cd up`) is now judged: this change judges
  it with a separator, and the sibling change judges it by itself.
- **`CDPATH=.:..`,** where a separator-less `..` follows a colon.
- **cmd's caret escape:** `echo "copy n .^.\x" | cmd`.
- **Delayed expansion:** `cmd /v:on` with `!X!` variables.
- **Paths computed inside code:** `python -c`, or PowerShell `(Split-Path (pwd))`.

New, or kept on purpose:

- **An inner shell's `case` arm executing a path straight after `)`**
  (`sh -c 'case 1 in 1)../../evil.sh;;esac'`). It is refused today and allowed after. It executes and
  cannot write. Operator question 1.
- **`**` is matched as `*`** unless the command names `globstar`. A program's own recursive glob
  (`prettier "src/**/*.ts"`) through a link two or more levels down is not seen. Walking every level
  would refuse such globs in any tree larger than the budget.
- **A hard link** is a name inside, and its content is shared. No path check can see it.
- **`host:x/y` and `user@alias:path`** are read as paths (D5; operator, 2026-09-24).
- **R3's:** a quoted JSON array past the bound (refused), and an inner shell's ANSI-C `..` with no
  separator (allowed).
- **(R5) An inner PowerShell's or `cmd`'s `> /dev/null` on Windows** (D4): allowed after, refused
  today.
- **(R5) Named costs:** `grep -rn '\.\./' src` on POSIX (D7), and an address written as text
  (`echo git@github.com:o/r.git`, a commit message naming one; D5).
- **(R5) A glob mentioned in a heredoc that also names `globstar`** is walked at every depth, and
  may pass the entry bound. The flag is read from the command's text.

## Open questions

1. **The `case` arm (D2).** Recommended: **accept the residual and keep `)` not a break.** Closing it
   by breaking at `)` refuses regex back-references again (`s/(foo)/\1/`, `rg 'foo(bar)/baz'`),
   which were among F362's measured refusals. It is an execution and cannot write. The narrower
   alternative is to break at a `)` directly followed by `.` or `~`. That closes the relative case
   but refuses regexes ending `(…).*` or `(…)..`, and it leaves `1)/abs/x`.
2. **D4's set.** Recommended: the four names (`/dev/null`, `/dev/stdin`, `/dev/stdout`,
   `/dev/stderr`), not `/dev/null` alone. Still unanswered from the Final section. (R5) The answer
   also accepts D4's residual on Windows: an inner PowerShell or `cmd` given `> /dev/null` writes
   `\dev\null`, if that directory exists. Recommended: accept. The alternative, exempting only a
   whole argument, refuses `sh -c 'cmd >/dev/null 2>&1'` on Windows.
3. **The linked dependency directories (Risks).** Recommended: file a finding and leave this change
   as written. The boundary is not this change's to redraw. (R5) The cost is larger than a bare
   mention: with the sibling change, a bare `*` in a worktree with a linked `node_modules` is
   refused. 595 of 42,860 Bash commands in this repository's own transcripts had a bare `*` word.
   No worktree on this machine holds such a link now, so the recommendation stands. If a
   JavaScript project is registered before the finding is fixed, the fix should come first.
4. **(R5) Build order.** Recommended: build this change and the sibling in one window. Between the
   two builds, a separator-less link or glob (`cp n up`, `cp n u*`) stays allowed, as it is today.
