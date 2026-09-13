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
- **An overrange `\U` does not crash the checker (row N3, R2 finding 2).**
  `echo hi > $'\Uffffffffx'` — a valid 8-hex escape above Unicode's max — is *allowed* (bash writes
  a file named `x` inside) and, above all, returns a decision rather than raising. Pinned as row
  N3; §4.7's mutation proves the totality guard is load-bearing.

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
