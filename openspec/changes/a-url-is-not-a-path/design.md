# Design — a URL is not a path

Everything below was measured on 2026-09-12 against `autonomous/2026-09-12-daily` at `e9b2bd0`,
unless it is labelled otherwise. "Prototype" means `testbed/scratch/r1f300/prototype.py`: a
standalone implementation of D1 that loads today's `_decide` beside it and prints both answers for
every row. **It is a design aid, not the implementation.** Its rows are the pinned test table in
tasks §1, and the implementation is held to that table, not to the prototype's code.

Re-run it: `cd hub && py -3.11 -B ../testbed/scratch/r1f300/prototype.py`.

## D1 — `_decide` reads a shell command word by word, and judges each word by what it is at its start

**Words.** The command is split on whitespace and on `" ' `` ` `` = < > | ; & ( ) ,`. Quotes are
delimiters, not grouping. That is deliberate, and the reason is **not** the obvious one. R1 first
wrote that grouping would let a path hidden in a quoted program through. Measured
(`measure6.py`), it does not: `python -c "open('/etc/x','w')"` and `sh -c "echo hi > /etc/x"`
are still refused under grouping, because the grouped word is not plain and rule 6's backstop finds
`/etc/x` inside it. What grouping breaks is **H1**. `"Content-Type: application/json"` becomes one
word containing a space, so it is not plain relative, and the backstop refuses it as `'/json'`.
That is F321 again, on the very request F300 is about. Splitting never raises: an unbalanced quote
is just one more delimiter. So the reader is total on any string, which `shlex` is not (D8).

**Each word is classified by the first rule that matches, in this order:**

| # | the word | decision |
|---|---|---|
| 1 | begins with a URL scheme, `^[A-Za-z][A-Za-z0-9+.-]*://` | `file:` → its path is checked as a path (rule 4), and a non-local host is outside. Any other scheme → **network rule** (D4). |
| 2 | begins with a reference to `HUB_URL`: `$HUB_URL`, `${HUB_URL}`, `$env:HUB_URL`, `%HUB_URL%` | **the run's own Hub** when D4's conditions hold. Otherwise → rule 3's refusal. |
| 3 | begins with any other variable (`$NAME`, `${…}`, `$1`, `$env:NAME`, `%NAME%`) or `~`, **and contains a separator** | **refused**: where it points is decided by the shell at run time and cannot be checked |
| 4 | contains no separator | not a path; nothing to check (unchanged from today) |
| 5 | is absolute (`os.path.isabs`), or is **plain relative**: word characters, `.`, `+`, `-` and separators, not beginning with `-`, with `:` permitted only after the first separator | **resolved** against the workspace (a relative word joined to it), refused if outside; the reason names the word as written |
| 6 | anything else containing a separator | **the backstop**: today's `_ABSOLUTE_PATH_RE` applied to this word alone, each candidate checked as today |

"Separator" is `/`, plus `\` where `os.sep` is `\`. On Windows `..\stray.txt` is a traversal. On
POSIX it is a file name with a backslash in it. The reader uses the platform's own answer, as
`os.path` already does.

**Why rule 6 exists.** A word-anchored reader loses every path that is glued to something:
`-o/tmp/x`, `@/etc/passwd` (curl reads that file), `file:/x`, `host:/x`, `-I../include`. Today's
regex refuses all of them, because it matches inside the word. Rule 6 hands any word the earlier
rules cannot account for back to today's reading, confined to that word. **A word therefore changes
answer only when rules 1, 2, 3 or 5 positively account for it.** That property is what lets D2's
table be complete: the only rows that can move are rows in those four classes.

**Why `:` only after the first separator in rule 5.** `sub/test_x.py::test_a` (a pytest node id)
must be plain relative. `host:/x` (scp), `127.0.0.1:9/x` (a schemeless address) and
`HEAD:sub/x.py` (a git object path) must not be, because a colon in the first segment is where a
host or a revision goes. Those fall to rule 6 and keep today's answer.

## D2 — The decided table

Research 2026-09-12 §1 asked for this: rows 1–5 pinned as `_decide` tests **before** the reader
changes, each with a decided answer and a true reason. The rest of the table extends that to every
row whose answer could move, and to every residual worth recording. Measured by the prototype;
*today* is `_decide` at `e9b2bd0`. `AW_WORKSPACE_DIR` is a directory holding `sub/hello.py`, and
`HUB_URL` is `http://127.0.0.1:8016`.

**The research's rows, re-measured.** Every answer and every reason in the *today* column was
reproduced exactly as §1 reports it.

| row | command | today | after | the reason after |
|---|---|---|---|---|
| R1 | `echo hi > ../stray.txt` | deny `'/stray.txt'` | **deny** | `'../stray.txt' is outside your workspace` |
| R2 | `echo hi \| tee ../stray.txt` | deny `'/stray.txt'` | **deny** | `'../stray.txt' is outside…` |
| R3 | `cp notes.md ../../stray.md` | deny `'/../stray.md'` | **deny** | `'../../stray.md' is outside…` |
| R4 | `echo hi > ~/stray.txt` | deny `'/stray.txt'` | **deny** | `'~/stray.txt'` starts with a variable or `~`… cannot be checked |
| R5 | `echo hi > "$HOME/stray.txt"` | deny `'/stray.txt'` | **deny** | `'$HOME/stray.txt'` … cannot be checked |
| R6 | `D=/tmp; echo hi > $D/stray.txt` | deny `'/tmp'` | deny | `'/tmp' is outside…` (the assignment's word comes first) |
| R7 | `echo hi > /tmp/stray.txt` | deny | deny | unchanged |
| R8 | `cd .. && echo hi > stray.txt` | allow | allow | **residual, unchanged** (D9) |
| R9 | `git -C .. status` | allow | allow | **residual, unchanged** (D9) |
| R10 | `curl -s https://example.com/x` | deny `'s://example.com/x'` | **deny** | network address (D5) |
| R11 | `curl "$HUB_URL/api/v1/agent-actions/tasks"` | deny `'/api/v1/…'` | **allow** | the run's own Hub |

**R4 and R5 are refused as uncheckable, not as outside.** Resolving `~` or `$HOME` would mean the
approver reading its own environment and assuming the shell's is the same. Under Git Bash, `$HOME`
is `/c/Users/…`, an MSYS path that `os.path` on Windows resolves incorrectly (row X9). The true
statement is that the approver does not know where the word points. An agent that means a path
inside its workspace can write it relative.

**F321: paths inside the workspace.**

| row | command | today | after |
|---|---|---|---|
| W1 | `python sub/hello.py` | deny `'/hello.py'` | **allow** |
| W2 | `git add sub/hello.py` | deny `'/hello.py'` | **allow** |
| W3 | `pytest sub/test_x.py::test_a` | deny `'/test_x.py::test_a'` | **allow** |
| W4 | `git diff origin/main...HEAD` | deny `'/main...HEAD'` | **allow** |
| W5 | `python sub/../hello.py` | deny `'/../hello.py'` | **allow** (it resolves inside) |
| W6 | `Get-Content .\sub\hello.py` | allow | allow |
| W7 | `ls`, `printf hi > a.txt`, `npm run test:unit` | allow | allow |

**The run's own Hub, and addresses that only look like it (D4).**

| row | command | today | after |
|---|---|---|---|
| H1 | `curl -s -X POST "$HUB_URL/api/v1/agent-actions/tasks" -H "Authorization: Bearer $AW_RUN_TOKEN" -H "Content-Type: application/json" -d "{…}"` | deny `'/api/…'` | **allow** |
| H2 | `curl.exe -s -X POST "$env:HUB_URL/api/v1/agent-actions/tasks" -H "Authorization: Bearer $env:AW_RUN_TOKEN"` | deny | **allow** |
| H3 | `curl -s ${HUB_URL}/api/v1/agent-actions/tasks` | deny | **allow** |
| H4 | `curl -s http://127.0.0.1:8016/api/v1/agent-actions/tasks` | deny `'p://…'` | **allow** |
| H5 | `curl -s http://127.0.0.1:9/api/v1/agent-actions/tasks` | deny `'p://…'` | deny, network |
| H6 | `curl -s http://localhost:8016/api/v1/agent-actions/tasks` | deny | deny, network (D4: not the same host string) |
| H7 | `curl -s http://127.0.0.1:8016@evil.example/x` | deny | deny, network (the host is `evil.example`) |
| H8 | `curl -s $HUB_URL@evil.example/x` | deny `'/x'` | deny, cannot be checked (what follows the reference is not `/ ? #`) |
| H9 | `HUB_URL=https://evil.example; curl -s $HUB_URL/x` | deny | deny, network (the assignment's URL) |
| H10 | `HUB_URL=.. ; cat $HUB_URL/x` | deny `'/x'` | deny, cannot be checked (`HUB_URL` is named outside a reference) |
| H11 | F301's `S1_python_c`, verbatim | deny `'/api/v1/…'` | **deny, unchanged** (D6) |
| H12 | any H1–H4 with `HUB_URL` **unset** in the approver | deny | deny |
| H13 | `curl -s http://u:p@127.0.0.1:8016/x` | deny | deny, network (userinfo, even on the Hub's own host) |
| H14 | `curl -s http://127.0.0.1:8016.evil.example/x` | deny | deny, network (the port does not parse, so not own) |
| H15 | `curl -s "http://127.0.0.1:8016#@evil.example/"` | deny | **allow**: the `@` is in the fragment, and host and port are the Hub's. curl sends no fragment |
| H16 | `curl -s HTTP://127.0.0.1:8016/x` | deny | **allow**: scheme compared ignoring case |

**Other network shapes.**

| row | command | today | after |
|---|---|---|---|
| N1 | `pip install https://example.com/pkg.tar.gz` | deny `'s://…'` | deny, network |
| N2 | `git clone https://github.com/o/r.git` | deny `'s://…'` | deny, network |
| N3 | `curl -s example.com/x` | deny `'/x'` | **allow**: the one widening, D3 |
| N4 | `curl -s example.com` | allow | allow |
| N5 | `curl -s 127.0.0.1:9/x` | deny `'/x'` | deny, unchanged reason (rule 6; D3) |
| N6 | `git clone git@github.com:o/r.git` | deny `'/r.git'` | deny, unchanged reason (rule 6; D3) |
| N7 | `curl file:///etc/passwd` | deny `'e:///etc/passwd'` | deny, `'file:///etc/passwd' is outside your workspace` |
| N8 | `WebFetch {"url": "https://example.com/x"}` | **allow** | allow, not governed (D7) |

**Glued paths, the backstop's rows.** G1–G4 keep today's answer and today's reason. G5 keeps its
answer and gains a true reason.

| row | command | today = after |
|---|---|---|
| G1 | `curl -o/tmp/x $HUB_URL/api` | deny `'/tmp/x'` |
| G2 | `curl -d @/etc/passwd $HUB_URL/api` | deny `'/etc/passwd'` |
| G3 | `gcc -I../include x.c` | deny `'/include'`: right answer, reason names a path not written (residual) |
| G4 | `tar -C/tmp -xf a.tar` | deny `'/tmp'` |
| G5 | `echo hi > $1/stray.txt` | deny: after, as cannot be checked (rule 3), where today reads `'/stray.txt'` |

**Windows forms: three rows move from allowed to refused.**

| row | command | today | after |
|---|---|---|---|
| X1 | `echo hi > ..\stray.txt` | **allow** | **deny**, `'..\\stray.txt' is outside…` |
| X2 | `type %USERPROFILE%\x` | **allow** | **deny**, cannot be checked |
| X3 | `Get-Content $env:USERPROFILE\x` | **allow** | **deny**, cannot be checked |

All three are escapes that today's regex never saw, because it knows `\` only after a drive letter.
Refusing them is a tightening, and it is decided here rather than left as a side effect. On POSIX,
X1–X3 contain no separator and keep today's answer.

**Residuals recorded, unchanged by this change.**

| row | command | today = after | why it stays |
|---|---|---|---|
| X4 | `cmd 2>/dev/null` | deny `'/dev/null'` | an absolute path outside the workspace. Whether the null device should pass is a containment question, open (D10) |
| X5 | `python src/*.py` | deny `'/*.py'` | glob characters are not in rule 5's class, because bash's `.*` can match `..` (D8) |
| X6 | `git show HEAD:sub/hello.py` | deny `'/hello.py'` | a colon in the first segment (D1) |
| X7 | `python $(pwd)/sub/hello.py` | deny `'/sub/hello.py'` | `)` splits the word, so `/sub/hello.py` reads as absolute |
| X8 | `cat sub/a<NUL>b` | deny | not a word character → backstop |
| X9 | `python /c/Users/…/ws/sub/hello.py` (the workspace, in MSYS form) | deny | `os.path` on Windows reads `/c/…` as `C:\c\…`. MSYS translation is not attempted |

**Count:** 56 labelled rows. The prototype's `ROWS` holds 49 commands. X7, X8, X9, H12–H16, the
`$HUB_URL.evil.example` case in D4, and the long URL in D5 were measured beside it by
`measure3.py`, `measure4.py` and `measure5.py` in the same directory, and N8 by a direct `_decide`
call. On the prototype's own run, **exactly 14 rows move**: W1–W5, H1–H4, R11, N3 and X1–X3.
H15 and H16 also move, which makes **16**. Both are the run's own Hub, written differently.

## D3 — A network address written without a scheme is a relative path, and N3 is the one widening that follows

`curl example.com/x` is, by syntax, the relative path `example.com/x`. So is a directory called
`example.com`. Nothing in the word distinguishes the two, and rule 5 resolves it inside the
workspace, so it is allowed. **This widens beyond the verdict.** It is decided here, knowingly, for
three reasons:

- It adds nothing the posture does not already give away: `curl example.com`, without the `/x`, is
  allowed today (N4). What the regex refused was the `/x`, not the host.
- The alternative is a host heuristic: treat `word.word/…` as a network address. That would refuse
  `cp v1.2/notes.md .` or `python src.old/x.py` *with a network reason*. That is F312's defect,
  a refusal for a false reason, rebuilt facing the other way.
- The verdict's own terms: this posture *"is not containment"* and *"actually containing network
  access needs a different layer entirely"*. Refusing N3 would not make it one.

Where a schemeless address has a colon in its first segment (N5 `127.0.0.1:9/x`, N6
`git@github.com:o/r.git`), rule 6 keeps today's answer, and today's false filesystem reason with
it. **That is a residual, not a decision about scp.** Recognising `user@host:` and `host:port` as
network addresses is small. It would need its own table, because `-p 8080:80` and `redis:6` look
the same, and nobody asked for it.

**R2/R3 should attack this section first.** It is the one place this change widens anything not in
the verdict. If the operator wants N3 refused, the cost is D8(d)'s heuristic, and the review page
will say so.

## D4 — What counts as the run's own Hub

**A URL** (rule 1) is the run's own Hub when all of these hold. The approver has a non-empty
`HUB_URL`. Both URLs parse (`urllib.parse.urlsplit`; a `ValueError` from a bad port means "not
own"). The schemes are equal, ignoring case. The hostnames are equal (`urlsplit` lowercases them).
The effective ports are equal, with `http` defaulting to 80 and `https` to 443. And the word carries
**no userinfo**. The userinfo condition is what refuses H7, whose host is `evil.example`. Any path,
query or fragment is permitted. The Hub authenticates every request by the run's token, and the
token authorises only the agent-action surface (`agent_trigger.py:1165-1179` strips the operator's
credentials from the run's environment). So "the run's own Hub" does not need to mean one route
prefix. `localhost` and `127.0.0.1` are **not** equated (H6). The notice names `$HUB_URL`, and
equating them would be a DNS claim the approver cannot check.

**A reference** (rule 2) is the run's own Hub when three conditions hold:

- the approver has a non-empty `HUB_URL`;
- what follows the reference is empty, or begins with `/`, `?` or `#`. So `$HUB_URL@evil.example`
  (H8) and `$HUB_URL.evil.example` are not;
- **the command names `HUB_URL` nowhere except in such references.** The count of case-insensitive
  `HUB_URL` occurrences equals the count of references. This refuses H10 and every way of
  reassigning the variable before using it (`HUB_URL=`, `export`, `read`, `set`, `$env:HUB_URL =`)
  without listing them. It also refuses a command that reads `os.environ['HUB_URL']` and uses
  `$HUB_URL` in the same breath. That is conservative, and rare.

**Why a reference is trusted at all.** The shell expands `$HUB_URL` to the value in *its*
environment, and the approver compares against the value in *its own*. Both processes inherit the
`claude` process's environment, which `agent_trigger.py:1140-1164` wrote. F300's drive observed the
approver's side (`mcp_server.py`, spawned by the harness, reached the Hub through `HUB_URL`), and
F301's S1–S3 executions observed the shell's side. What is **not** established is the case where the
operator's own shell profile, sourced by the harness's shell, sets `HUB_URL` to something else.
**Unverified.** If it can, the reference names an address the approver did not check. The literal
form (rule 1) has no such gap.

## D5 — What a refusal says, and how long it may be

**Network refusal** (rule 1):

> `'<word>' is a network address. Under this posture a shell command may name only this run's own
> Hub ($HUB_URL); if the task needs another address, ask the operator with ask_user`

`approve_tool_call` wraps it as `Denied: <reason>.`. The wording follows the verdict:
- it names network, and **not** the workspace or the filesystem;
- it claims only what the rule does. *"May name only"* is true. *"Network access is not permitted"*
  would be false (N3, N4, N8).
- it names who can change it and how. The research's point (2026-09-12 §2) is that a denial the
  agent can do nothing with, plus a task it must still finish, is when probing rises. So the way
  out it names is `ask_user`, and it does **not** suggest "try another way". The other way is a
  one-line `python -c`.

**Cannot-be-checked refusal** (rules 2 and 3):

> `'<word>' starts with a variable or '~' that the shell expands when it runs, so where it points
> cannot be checked against your workspace; write a path relative to your workspace instead`

**Outside refusal** (rules 5 and 6): unchanged, `'<word>' is outside your workspace`. What changes
is that `<word>` is now the word the agent wrote (rule 5), not a fragment of it.

**The bound.** Every reason quotes at most **200** characters of the word, cut with `…`. Measured:
a 1,200-character URL gives a **1,244**-character reason *today*, and 1,389 with the network
wording. `POST /agent-actions/permission-decisions` caps `reason` at **1000**
(`PermissionDecisionCreate`, `hub/hub/api/v1/agent_actions.py:840`). An over-long report is answered
422 by construction. **That was read, not driven.** `_report_decision` swallows the 422, so the
refusal is never recorded, which breaches *"A refusal is recorded wherever it is decided"*. This is
**already true today** for any long candidate. The bound fixes the existing defect as well as
keeping the new wording from making it worse. `mcp_server.py` may not import the Hub, so the cap is
restated there, with a test asserting the restated value is no larger than the schema's
`max_length`. That is the module's established pattern: `OPERATOR_POSTURE` and
`MIN_WAITING_SECONDS` do the same.

**Totality.** `_decide` catches `OSError` around `os.path.realpath`. On POSIX, a NUL byte in a path
raises **`ValueError`** instead. Measured on this machine: `posixpath.realpath('/a\x00b')` raises
`ValueError: lstat: embedded null character in path`, and CPython 3.11's `_joinrealpath` catches
only `OSError` at `posixpath.py:452`. So on Linux, CI's platform, `_decide` **raises** today for such
a command, where its docstring promises *"pure and total"*. Whether the harness then treats the
error as a denial or as a broken approval system is **unverified**. The reader catches
`(OSError, ValueError)` and refuses. On Windows, `ntpath.realpath` did not raise for the same input
(X8).

## D6 — F301's `python -c` shape stays refused, and that bears on the notice change

H11 is F301's `S1_python_c`, character for character from `testbed/scratch/f301shapes/shapes.py`:
`…os.environ['HUB_URL']+'/api/v1/agent-actions/tasks'…`. The quote splits the `'/api/…'` literal
into a word that begins with `/`. That is an absolute path by rule 5, and it is refused as outside,
**today and after**.

Rule 5 cannot tell that literal from `open('/etc/x','w')`. Reading Python to find out which strings
become URLs is not something a shell reader can do. The refusal's reason, *outside your workspace*,
is true of the word as written.

**Consequence, recorded for the operator and not acted on.** `DECISIONS.md` 1c's table records
`_decide → allow` for this shape, and 1d's *"notice first"* remedy instructs it. Measured, `_decide`
refuses it. After this change, the shape the notice **already** instructs (`curl "$HUB_URL/…"`, H1)
is the one `_decide` allows. Position 4 in `DIRECTION.md` 2026-09-11, F301's notice change, should
be re-derived against H1 and H11 before it is proposed.

## D7 — What is not governed, stated so nobody reads a boundary into it

- **`WebFetch` and `WebSearch`.** `_decide` reads `file_path`, `path`, `notebook_path` and
  `command`, and nothing else. A `WebFetch` to any address is allowed today (N8), measured, and is
  unchanged. The new requirement is worded as a rule about **shell command text**, and its prose
  says so.
- **Codex.** `decide_approval` under "Workspace only" accepts a command approval whose working
  directory is inside the workspace (`codex_appserver.py:280-283`), whatever the command does. The
  research's schema read says a Codex 0.146.0 approval can carry `networkApprovalContext {host,
  protocol}`, and nothing in the Hub reads it. **Unverified, because Codex is undrivable.** Filed as
  **F322**. The requirement's prose says it governs the posture where the Hub reads a shell
  command's text, and that a runner whose command approvals the Hub decides by working directory is
  not brought under it.

## D8 — Alternatives rejected

- **(a) Mask URLs and `$HUB_URL/…` out of the text, and keep the regex for the rest.** This was the
  smallest diff, and nothing else would have changed answer. **It cannot deliver F300's verdict.**
  H1's `Content-Type: application/json` header still yields `/json`, refused as outside (F321).
  That is the fix-that-cannot-fire shape this repository keeps finding.
- **(b) Anchor the regex to word starts, and stop there.** This is research §1's column. R1–R5 flip
  to allowed, and so do G1–G4. Rejected, as the research predicted.
- **(c) `shlex.split`.** It raises `ValueError` on an unbalanced quote, which breaks totality. Its
  POSIX escaping also consumes the `\` in Windows paths, and its non-POSIX mode keeps quotes on the
  words. It also groups quoted text into one word, which breaks H1 (D1).
- **(d) A host heuristic for schemeless addresses.** See D3. It refuses dotted directory names for a
  network reason.
- **(e) Deny every URL, the run's own Hub included.** This is the verdict's rejected option B. It
  leaves F300 standing.

## D9 — The escapes that never went through the regex stay as they are

R8, R9 and a `cd` in an earlier call are allowed today and after. Relative words are resolved
against the workspace root, which is the run's *starting* directory. The harness's shell keeps its
working directory between calls. `_decide` cannot see it, and the docstring already says *"a
boundary, not a sandbox"*. The change rewrites the `_decide` comment that claims relative paths
*"resolve against the run's cwd, which is the workspace"*, because that is the claim F321 and R1
both show is false. The rewrite states the resolution rule and this limit instead.

## D10 — Open, for R2, R3 and the operator

1. **N3.** Accept the one widening, or pay for D8(d)? (D3.)
2. **X4, `/dev/null`.** It is refused today and after. It is the most common absolute path in shell
   commands and harmless to write to. Permitting it would be a containment decision, and this change
   does not make it.
3. **D4's shell-profile gap.** Can a sourced profile override `HUB_URL` in the harness's shell? If it
   can, rule 2 should require the literal form, or `HUB_URL` should be re-read from somewhere the
   profile cannot reach.
4. **The 200-character bound.** Chosen so the longest fixed wording (about 190 characters) plus the
   word stays well under 1000. R2 should re-derive the wording lengths from the final strings.
