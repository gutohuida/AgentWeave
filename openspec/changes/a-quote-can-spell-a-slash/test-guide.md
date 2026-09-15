# User test guide — a quote can spell a slash

Task 9.1. What an operator does, what they should see, and what it looks like when it goes wrong.

The suite proves the table: every row in `design.md` D2 gets the answer and the reason written
there. The finding this closes — F332 — is a **POSIX-only** escape, and the machine you drive on is
Windows, so read the split below carefully: on Windows the command was already refused (for a
misleading reason), and what a Windows drive shows you is the reason improving and one over-refusal
corrected. The escape itself writing outside is a Linux fact, proven on CI, not something a Windows
drive can reproduce.

## Agent-verifiable (the suite and CI check these)

These need no operator; a test or CI settles each.

- **The escape is refused.** `echo hi > $'..\x2fstray.txt'` (bash ANSI-C quoting: `\x2f` decodes to
  `/`, so the shell writes `../stray.txt`) is refused as `'../stray.txt' is outside your workspace`.
  Pinned in `hub/tests/test_permission_approver.py` (row G1) and on the wire (§3).
- **Every spelling of the slash is refused.** Octal (`$'..\057x'`), the 4- and 8-hex unicode
  escapes, the fully-spelled `$'\x2e\x2e\x2fx'`, the split-quote and adjacent forms, and the same in
  `tee`/`cp` argument position (D2 rows G2–G10). All refused as the decoded path.
- **The literal-`$` spelling is refused.** `echo hi > $'\x24HUB_URL\x2f..\x2f..\x2fx'` decodes to a
  directory literally named `$HUB_URL` that `..` then climbs out of; it is refused as *cannot be
  checked* (row D1), not treated as the run's own Hub.
- **The POSIX flip is proven on CI, not on your machine.** On CI's Linux `hub-test` job, the rows
  above are strict-xfail against the tree before the fix and PASS after it. That is the only
  authoritative evidence that the escape, allowed on Linux before, is refused after (`design.md`
  D4). WSL runs of `testbed/scratch/r1f332/forms.sh` and `reader_forms.py` reproduce it locally.
- **Legitimate work and the own-Hub request are unchanged.** `python sub/hello.py` and
  `curl "$HUB_URL/api/v1/agent-actions/tasks"` are allowed (rows OK1, OK2).
- **A digitless `\x` is a Windows separator, not a dropped byte (row N2, R2 finding 1).**
  `echo hi > $'..\x'` — bash keeps the backslash (`..\x`), which is a traversal on Windows — is
  refused as outside on Windows. Pinned in `test_permission_approver.py` (row N2). If the decoder
  dropped the backslash it would allow this on Windows; §4.6's mutation guards that.
- **A `\u`/`\U` from 0x100 to 0x7FFFFFFF is judged under both readings a real bash shell
  might use, and refused if either would escape (row N4, D1's dual reading).** bash's decode of
  a codepoint in this range is locale-dependent: a UTF-8 locale emits multibyte UTF-8 (no
  backslash), and a *true C (non-UTF-8) locale* keeps the escape literal, backslash and all —
  and, measured, **both are genuinely reachable on this machine** depending on how the Bash
  tool's shell is invoked, not merely a hypothetical worst case. So `echo hi > $'..\u0100'` (a
  `\u` whose value 0x100 is above 0xFF) is refused as *outside* on Windows: the C-locale
  reading alone already finds a traversal (the kept backslash is a separator there), so the
  command refuses regardless of what the UTF-8 reading finds. Pinned as row N4; §4.7's mutation
  (decode the whole range above 0xFF via `chr()` unconditionally) flips it to allow.
- **A `\U` at or above 0x80000000 decodes to nothing, matching bash exactly, and is *allowed*
  on Windows (row N3) — this is not a deny, and not merely a reason improving.** bash itself
  renders nothing for this range in every locale, so `echo hi > $'\Uffffffffx'` writes a file
  literally named `x`, inside the workspace, on every platform — and the checker now matches
  that exactly rather than conservatively refusing it. (An earlier design kept this range's
  backslash literal and denied it, believing that a safe over-refusal; it was not — a kept
  backslash here can hide a real escape elsewhere in a longer path, design.md's "What round 4
  changed".) The checker also **returns a decision rather than raising** here — the value is
  never passed to `chr()` at all, so there is nothing to overflow. §4.7's mutation (decode this
  range via `chr()` unconditionally) makes `_decide` **raise** on N3 instead of returning,
  proving totality is load-bearing even though the row's own answer is allow.
- **A `\c` before the closing quote keeps its backslash (row N5, R3 finding 2).**
  `echo hi > $'..\c'` — bash keeps `\c` literal (`..\c`) when nothing follows it before the closing
  quote — is refused as *outside* on Windows. If the decoder consumed the closing quote as `\c`'s
  control target it would allow this on Windows; §4.8's mutation guards that.
- **A decoded character outside the checker's `\w`-only path pattern does not wrongly refuse an
  inside path (rows Q1–Q4, S1, design.md D6, corrected Round 7).** `cat $'sub\xd7\x2fhello.py'`,
  `cat $'sub\cA\x2fhello.py'` and `cat $'sub\u2000\x2fhello.py'` each decode to a path genuinely
  inside the workspace (a filename containing ×, a control byte, or a Unicode space character), and
  are **allowed** on both platforms — this is a pre-existing gap in the checker's own path-matching
  regex, not something this change's decoder gets wrong, but the decoder is what first makes these
  characters reachable through an escape. Without task 2.2c's fix, these rows would be wrongly
  **denied** (`'/hello.py' is outside your workspace'`) even though they never leave the workspace —
  §4.9's mutation guards that. `cat $'sub\xe9\x2fhello.py'` (Q4, é) decodes to a character the
  checker's pattern already accepted — but its permission answer still moves, from *cannot be
  checked* to *allowed*, once ANSI-C decoding exists at all, the same way every other over-refusal
  in this table does; it is not affected by task 2.2c's regex change specifically. **S1**
  (`cat $'\xd7sub\x2fhello.py'`) is the same class of path as Q1, but with the exotic byte as the
  word's *first* character rather than an interior one — a version of the fix that only widens
  interior character classes still wrongly denies this row; the shipped fix widens the leading
  position too.
- **A directly typed word with no escape at all is not caught by the same fallthrough this
  change corrects (rows T1, T2).** `cat x!/etc/passwd` (T1, punctuation mid-word) and
  `cat !/etc/passwd` (T2, punctuation as the word's first character) — nothing in either command
  is ANSI-C-quoted — flip from refused (`'/etc/passwd' is outside your workspace'`, an
  over-refusal: the checker used to mistake the tail for an absolute path glued onto the leading
  text) to **allowed** (correctly resolved as one relative path under the workspace root). This is
  a real, deliberate widening of the fix beyond ANSI-C decoding — see design.md D6's "wider effect"
  note — and `cat -o/tmp/x` (row S2) still correctly denies, confirming the checker still
  recognizes a genuinely glued form.
- **Quote-joining, glob characters and an embedded NUL stay protected, exactly as they do today
  (rows `E11`, `J5`, `X5`, `X8` — not new, already in `hub/tests/test_permission_approver.py`).**
  This fix widens what the checker treats as an ordinary path character, and an earlier draft of
  it widened too far — it let a shell-quote-joined traversal, a glob that can match `..`, and a
  path split around a NUL byte all resolve as literal, safe-looking relative paths instead of
  being caught the way they are today. None of these four commands should ever change behavior
  because of this fix; if any of them does, the fix has regressed past its own intended scope.
- **curl's own file-reading convention stays protected, even from an interior `@` (row S3).**
  `curl --data-urlencode name@/etc/passwd $HUB_URL/api/v1/agent-actions/tasks` is refused as
  outside, unchanged, before and after this change — curl reads the file named after an `@`
  anywhere in a `--data-urlencode` value, not only a leading one, so the checker excludes `@` from
  every position a word can carry it in, not just the first character. If this command ever gets
  through, that protection has regressed — see design.md D6's correction and S3's own row.

## Human-only (you judge these)

Drive the trial Hub on port **8010** (started from `hub/`, per `CLAUDE.md`), a project whose
workspace is a git repository with `sub/hello.py`, one agent with a Haiku `claude` runner and **no
permission override** (the default, "Workspace only").

### 1. The escape is refused, and the reason names the path

Send the agent, for its **Bash** tool:

> Run `echo hi > $'..\x2fstray.txt'`

**You should see** a refusal reading `Denied: '../stray.txt' is outside your workspace.` — the path
the shell would actually have written, not a fragment. On Windows this command was refused before
this change too, but as *cannot be checked* (a false reason). **Judge it:** does the new reason tell
you what happened? That judgement is task 8.1.

**Where a stray would land if it wrote.** A writing agent in a git project works in its own
worktree, `<project>\.agentweave\worktrees\<agent>`. So a `..` escape lands in
`<project>\.agentweave\worktrees\`, not beside the project. Look there; nothing should appear.

### 2. An ANSI-C spelling of an inside path is allowed

> Run `cat $'sub\x2fhello.py'`

**You should see** the contents of `sub/hello.py`. `$'sub\x2fhello.py'` decodes to `sub/hello.py`,
which is inside the workspace. Before this change this was **refused** on Windows (the literal
backslash tripped the checker) — an over-refusal the fix corrects. **Judge it (task 8.2):** confirm
it is the same file as `cat sub/hello.py`, i.e. the change made an inside path reachable, not an
escape.

### 3. A decoded character the checker's own pattern doesn't recognize still doesn't false-deny

> Run `cat $'sub\xd7\x2fhello.py'`

**You should see** a "file not found"-style error **from the tool itself**, not a permission
refusal — the approval decision is allow (the path `sub×/hello.py` is inside the workspace, even
though no such file exists), and the checker's own regex used to wrongly deny this because the `×`
character fell outside a character class only decoded paths ever exercise. **It has gone wrong if**
you instead see `Denied: '/hello.py' is outside your workspace` — that means task 2.2c's fix (D6)
did not land.

**It has gone wrong if** step 1 succeeds and a `stray.txt` appears in the worktrees directory, or
step 2 is refused as outside the workspace.

## What this does not show

- **The escape writing outside.** That is Linux-only. On Windows the command was already refused, so
  you cannot watch the file appear and then not appear. Trust CI's Linux job for the flip.
- **PowerShell.** `$'…'` is a bash quote form; PowerShell has no equivalent, and its reading is
  unchanged.
- **`cd ..` then write, or a path built at runtime** (`Set-Content (Join-Path .. x)`). Still allowed,
  as before — the approver does not track the shell's working directory or read runtime-built paths
  (`a-url-is-not-a-path` D9). Recorded, not closed here.
- **Codex.** "Workspace only" on Codex decides by working directory, not by reading the command
  (F322). Unchanged.
