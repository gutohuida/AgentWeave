# Design — a URL is not a path

Everything below was measured on 2026-09-12 against `autonomous/2026-09-12-daily` at `e9b2bd0`,
unless it is labelled otherwise. "Prototype" means `testbed/scratch/r1f300/prototype.py`: a
standalone implementation of D1 that loads today's `_decide` beside it and prints both answers for
every row. **It is a design aid, not the implementation.** Its rows are the pinned test table in
tasks §1, and the implementation is held to that table, not to the prototype's code.

Re-run it: `cd hub && py -3.11 -B ../testbed/scratch/r1f300/prototype.py`.

**R2 (2026-09-12) replaced D1's word split, and the rest of the design stands on the new one.**
R1's reader split words at quote characters. The shell does not split there. It removes the
quotes and joins what stands on either side, so R1's reader judged strings the shell never
produces. R2 measured **sixteen commands** that today's `_decide` refuses and R1's prototype
allows, and ran five of them in Git Bash on this machine. Each of the five wrote a file **outside
the workspace**. They are D2's E rows. They fall into three classes: quotes the shell joins, an
own-Hub address used as a path, and a word the argument carries on. R2's corrected reading is
`testbed/scratch/r2f300/reader.py`, and `table.py` beside it prints today's answer and R2's answer
for every row in D2. It is a design aid on the same terms as R1's prototype. Re-run it:
`cd testbed/scratch/r2f300 && py -3.11 -B table.py`.

## D1 — `_decide` reads a shell command as the shell will, then judges each word by what it is at its start

**First, arguments, lexed in the dialect of the tool that carries the command.** A word is only
worth judging if it is a string the shell will actually produce. R1's reader split
`echo hi > '.'./stray1.txt` into `.` and `./stray1.txt`, and both are inside. Bash joins them into
`../stray1.txt`. Run in Git Bash on this machine, the file landed in the workspace's parent (E1).
So did `.""./stray2.txt` (E2) and `.\./stray9.txt` (E3). Today's regex refuses all three, because
it matches the `/stray…` in the middle. R1's own requirement text forbids exactly this: *"reading
words from their start must not let through a path that reading them from the middle refused"*.

So the reader lexes first. It removes what the shell removes, joins what the shell joins, and
marks what the shell expands:

- **`Bash`** (Git Bash on Windows, bash or zsh elsewhere). Single quotes are literal. Inside
  double quotes, `\` escapes only `$`, `` ` ``, `"`, `\` and a newline, and is kept before
  anything else. Outside quotes, `\c` is `c`.
- **`PowerShell`**. Single quotes are literal, `` ` `` escapes, and `\` is an ordinary character.
- **Any other tool whose input carries `command`** is read both ways, and refused if either
  reading refuses.

Unquoted whitespace and `| ; & < > ( )` end an argument. A command substitution, `$(…)` or
`` `…` ``, stays in its argument as an expansion, which makes that argument rule 3's. Its contents
are also read as a command of their own, so `echo "$(cat /etc/x)"` is refused for `/etc/x` (S2).
An unbalanced quote runs to the end of the text. Nothing raises, so the reader is total on any
string, which `shlex` is not (D8).

**The dialect is not a detail.** In Git Bash, `echo hi > ..\stray7.txt` wrote `..stray7.txt`
*inside* the workspace, because bash removed the backslash (X1a). `echo hi > "..\stray8.txt"`
wrote `stray8.txt` *outside* it, because a backslash inside double quotes survives and MSYS reads
it as a separator (X1b). **Today's `_decide` allows X1b.** It is an escape today, and this change
closes it. A single reading cannot serve both shells. Read PowerShell's way, the bash-escaped JSON
body `-d "{\"title\": \"x\"}"` leaves `\title\` as a word, which is rooted and outside, so F300's
request would be refused on Windows (J2). Read bash's way, PowerShell's `..\stray.txt` loses its
separator, and a traversal passes (X1c).

**Then words: split only at characters that stay in the string.** Each argument is split at the
whitespace, `=` and `,` that survived lexing. Each word then has any leading and trailing
`` " ' ` { } [ ] ( ) < > | ; & : `` trimmed. A quote in the *middle* of a word is **not** split
there. `sh -c "echo hi > '.'./x"` hands its inner shell the text `'.'./x`, and that shell would
join it into `../x`. Left whole, the word is not plain, so rule 6's backstop refuses `/x` (E11).

This is what lets F300's request through. `-H "Content-Type: application/json"` is one argument,
and `application/json` is a word of it, plain and inside (H1). It is also what lets the
bash-escaped JSON body through: `"{\"title\": \"fix sub/hello.py\"}"` lexes to
`{"title": "fix sub/hello.py"}`, and the word `"sub/hello.py"}` trims to `sub/hello.py` (J3). R1's
reader refused both J2 and J3 on Windows as `'\\'`. That was a lone backslash left between two
delimiters, rooted and so outside.

**A word that the argument carries on is judged as a name that continues.** Splitting at `=` or at
a space, or trimming a trailing quote, can end a word at the workspace's own name. Take
`cp notes.md ../ws=y/z`, where the workspace directory is `ws`. The word `../ws` resolves to the
workspace itself, and `y/z` is inside it. But the shell writes to `../ws=y/z`, a **sibling
directory** named `ws=y` (E15). `echo hi > "../ws y.txt"` wrote `ws y.txt` next to the workspace in
Git Bash (E16). Today's regex refuses both. R1's reader allows both.

So a word followed, inside its argument, by anything the split or the trim removed is judged with
its last name extended. The reader appends one ordinary character, so that `../ws` is judged as
`../ws_`. The refusal quotes the whole argument, `'../ws=y/z'`, because that is the path the shell
will use. A word that ends its argument is judged as it stands. So is a word with something only
*before* it. A prefix lands inside the word's first name, which makes that name neither `.` nor
`..`, so the prefix can only keep the path further in.

**Each word is classified by the first rule that matches, in this order:**

| # | the word | decision |
|---|---|---|
| 1 | begins with a URL scheme, `^[A-Za-z][A-Za-z0-9+.-]*://` | `file:` → its path is checked as a path (rule 5), and a non-local host is outside. Any other scheme → **network rule** (D4). An address D4 accepts as the run's own Hub is **also judged as the relative path it spells**, by rule 5. |
| 2 | begins with a reference to `HUB_URL`: `$HUB_URL`, `${HUB_URL}`, `$env:HUB_URL` | **the run's own Hub** when D4's conditions hold, and then **also judged as the path it spells** once the approver's own `HUB_URL` value is put in its place. Otherwise → rule 3's refusal. |
| 3 | contains an expansion **anywhere** (a `$`, a command substitution, a leading `~`, or `%NAME%`) **and** contains a separator | **refused**: where it points is decided by the shell at run time and cannot be checked |
| 4 | contains no separator | not a path; nothing to check (unchanged from today) |
| 5 | is absolute (`os.path.isabs`), or is **plain relative**: word characters, `.`, `+`, `-` and separators, not beginning with `-`, with `:` permitted only after the first separator | **resolved** against the workspace (a relative word joined to it), refused if outside; the reason names the word, or its whole argument when the word continues |
| 6 | anything else containing a separator | **the backstop**: `_ABSOLUTE_PATH_RE` applied to this word alone, each candidate checked as today, a candidate that ends the word inheriting the word's "continues". On Windows the backstop regex also opens a candidate at a bare `\` (R3), not only after a drive letter — see below |

**Why rule 3 looks anywhere in the word, not only at its start.** R1's rule 3 looked at the
first character. `$(echo .)./stray.txt` lexes to one argument with an expansion at its start, but
`sub/$X/../..` has its expansion in the middle. Today's regex refuses that one as `'/$X/../..'`.
Under R1's rule order it would reach rule 6 and be refused for the same false reason. Looking
anywhere gives the true reason, and it costs nothing: a word with a `$` and a separator was
refused under every earlier reading too.

**Why an own-Hub address is also a path.** The shell does not know that a word is a URL.
`echo hi > "$HUB_URL/../../../stray.txt"` writes to the relative path
`http:/127.0.0.1:8016/../../../stray.txt`. Two of those `..` climb back out of `http:/127.0.0.1:8016`,
and the third leaves the workspace. Git Bash did exactly that once the two directories existed,
and an agent can create them, since they are inside (E5). Judging the address as a path costs a
legitimate request nothing. curl 8.21.0 removes dot segments before it sends (measured: a request
for `/api/../../../x` arrived as `/x`, and only `--path-as-is` kept them). So no request to the Hub
needs a `..`, and a path that stays inside passes (E14). The rule also sends E4, E6 and E6b to
*outside*, which is where they write.

"Separator" is `/`, plus `\` where `os.sep` is `\`. On Windows `..\stray.txt` is a traversal. On
POSIX it is a file name with a backslash in it. The reader uses the platform's own answer, as
`os.path` already does.

**Why rule 6 exists.** A word-anchored reader loses every path that is glued to something:
`-o/tmp/x`, `@/etc/passwd` (curl reads that file), `file:/x`, `host:/x`, `-I../include`. Today's
regex refuses all of them, because it matches inside the word. Rule 6 hands any word the earlier
rules cannot account for back to today's reading, confined to that word. **A word therefore changes
answer only when rules 1, 2, 3 or 5 positively account for it.** That property is what lets D2's
table be complete: the only rows that can move are rows in those four classes.

**The backstop's regex must know `\` as a separator on Windows (R3).** `_ABSOLUTE_PATH_RE`
(`(?:[A-Za-z]:[\\/]|/)…`) opens a candidate at `/`, or at `\` only *after a drive letter*. A bare
`\stray.txt` opens no candidate. Rule 5 catches a *plain* relative `..\stray.txt`, but a backslash
traversal **glued to an option** is not plain — it begins with `-` — so it falls to rule 6, and R2's
backstop, being today's regex, let it through. Measured on this machine: `sort -o"..\stray.txt"
notes.md` in Git Bash wrote `stray.txt` in the workspace's parent, rc=0, and R2's reader **allows**
it (Z1). So does today's `_decide` (its whole-command regex finds no `/`). Worse,
`curl -o"..\out" http://127.0.0.1:8016/api` is **refused today** — the URL's `//` gives today's
regex a false candidate — and R2's reader **allows** it: a regression the reader introduces (Z2).
So on Windows the backstop opens a candidate at a bare `\` too. This is the exact mirror of rule 6's
POSIX behaviour, and it inherits the same known residual: `gcc -I"sub\include" x.c`, an inside path
glued to an option, is now refused as `'\include'` outside, the Windows twin of G3 (`-I../include`,
already a residual over-refusal today). No row in D2 outside the Windows-`\` class moves; POSIX is
untouched, because `\` is not `os.sep` there.

**Why `:` only after the first separator in rule 5.** `sub/test_x.py::test_a` (a pytest node id)
must be plain relative. `host:/x` (scp), `127.0.0.1:9/x` (a schemeless address) and
`HEAD:sub/x.py` (a git object path) must not be, because a colon in the first segment is where a
host or a revision goes. Those fall to rule 6 and keep today's answer.

## D2 — The decided table

Research 2026-09-12 §1 asked for this: rows 1–5 pinned as `_decide` tests **before** the reader
changes, each with a decided answer and a true reason. The rest of the table extends that to every
row whose answer could move, and to every residual worth recording. Measured by the prototype;
*today* is `_decide` at `e9b2bd0`. `AW_WORKSPACE_DIR` is a directory named `ws` holding
`sub/hello.py`, and `HUB_URL` is `http://127.0.0.1:8016`.

**R2 re-measured every *today* cell** with `testbed/scratch/r2f300/today.py`, which loads only
`_decide`, and every one agrees. Every *after* cell below is R2's lexing reading. It keeps every
answer R1 decided except X1–X3, which R2 splits by dialect.

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

**Glued paths, the backstop's rows.** G1–G4 keep today's answer and today's reason. G5 and G6
keep their answer and gain a true reason.

| row | command | today = after |
|---|---|---|
| G1 | `curl -o/tmp/x $HUB_URL/api` | deny `'/tmp/x'` |
| G2 | `curl -d @/etc/passwd $HUB_URL/api` | deny `'/etc/passwd'` |
| G3 | `gcc -I../include x.c` | deny `'/include'`: right answer, reason names a path not written (residual) |
| G4 | `tar -C/tmp -xf a.tar` | deny `'/tmp'` |
| G5 | `echo hi > $1/stray.txt` | deny: after, as cannot be checked (rule 3), where today reads `'/stray.txt'` |
| G6 | `echo hi > sub/$X/stray.txt` | deny: after, as cannot be checked (rule 3 looks anywhere, R2), where today reads `'/$X/stray.txt'` |

**Windows forms: which rows move depends on the shell (R2).** The tool column is the tool whose
`command` is read (D1).

| row | tool | command | today | after |
|---|---|---|---|---|
| X1a | Bash | `echo hi > ..\stray.txt` | allow | allow: bash removes the `\` and writes `..stray.txt` **inside**, measured |
| X1b | Bash | `echo hi > "..\stray.txt"` | **allow** | **deny**, `'..\\stray.txt' is outside…`. **An escape today**, measured in Git Bash and in a live Haiku turn through the approver (**F323**) |
| X1c | PowerShell | `echo hi > ..\stray.txt` | **allow** | **deny**, `'..\\stray.txt' is outside…` |
| X2b | Bash | `type %USERPROFILE%\x` | allow | allow: bash does not expand `%NAME%`, and the `\` is removed |
| X2p | PowerShell | `type %USERPROFILE%\x` | **allow** | **deny**, cannot be checked (conservative: PowerShell does not expand `%NAME%` either, but a nested `cmd /c` does) |
| X3b | Bash | `Get-Content $env:USERPROFILE\x` | allow | allow: no separator survives bash's lexing |
| X3p | PowerShell | `Get-Content $env:USERPROFILE\x` | **allow** | **deny**, cannot be checked |

X1b, X1c, X2p and X3p are escapes today's regex never saw, because it knows `\` only after a drive
letter. Refusing them is a tightening, and it is decided here rather than left as a side effect.
R1 decided X1–X3 as *deny* without a tool column. That was right for PowerShell. For Bash it
refused X1a, which writes inside. R1's prototype also refuses X1b, but D2 did not record that X1b
is an escape today. On POSIX, `\` is not a separator, so every X row keeps today's answer there.

**R3's rows: a backslash traversal glued to an option reaches the backstop, which R2's regex did
not catch.** X1b is a *bare* word, so rule 5 catches it. Glue the same traversal to an option and it
is no longer plain, so it falls to rule 6. R2's backstop (today's regex) missed the bare `\`. Both
rows run through the **Bash** tool on Windows; on POSIX both keep today's answer.

| row | tool | command | today | R2 | after (R3) |
|---|---|---|---|---|---|
| Z1 | Bash | `sort -o"..\stray.txt" notes.md` | **allow** | **allow** | **deny**, `'\stray.txt' is outside…`. **An escape today**, measured writing outside in Git Bash |
| Z2 | Bash | `curl -o"..\out" http://127.0.0.1:8016/api` | deny (false, the URL's `//`) | **allow** | **deny**, `'\out' is outside…`. R2 opened it: a regression the reader introduced |
| Z3 | Bash | `gcc -I"sub\include" x.c` | allow | allow | **deny**, `'\include' is outside…`. A residual over-refusal, the Windows twin of G3 |

**R2's rows: what R1's reader let through, and what it refused (R2, measured).** Every E row except
E7 is refused today, and R1's prototype **allows every one of them**. The R1 column was measured
by `testbed/scratch/r2f300/attack.py` and `r1col.py`, which run R1's prototype as the subject.
*Shell* marks the five that R2 ran in Git Bash and saw write outside the workspace. Rows not shown
(E10, E17, E19) are variants of E9, E15 and E1, with the same three answers.

| row | command | today | R1 | after | why |
|---|---|---|---|---|---|
| E1 | `echo hi > '.'./stray.txt` | deny | **allow** | deny, `'../stray.txt'` | quotes joined (D1). *Shell* |
| E2 | `echo hi > .""./stray.txt` | deny | **allow** | deny | quotes joined. *Shell* |
| E3 | `echo hi > .\./stray.txt` (Bash, Windows) | deny | **allow** | deny | `\.` is `.` in bash. *Shell* |
| E4 | `echo hi > $HUB_URL/../../../stray.txt` | deny | **allow** | deny, outside | own Hub, also a path (D1 rule 2) |
| E5 | `echo hi > "$HUB_URL/../../../stray.txt"` | deny | **allow** | deny, outside | the same, quoted. *Shell*, after `mkdir -p 'http:/127.0.0.1:8016'` |
| E6 | `echo hi > http://127.0.0.1:8016/../../../stray.txt` | deny | **allow** | deny, outside | own Hub literal, also a path (rule 1) |
| E6b | `cp a http://127.0.0.1:8016/x#/../../../../stray.txt` | deny | **allow** | deny, outside | a fragment is a file name to the shell |
| E7 | `curl "$HUB_URL"@evil.example` | **allow** | allow | **deny**, cannot be checked | the joined argument is `$HUB_URL@evil.example`, H8's shape. A tightening |
| E9 | `echo hi > $(echo .)./stray.txt` | deny | **allow** | deny, cannot be checked | a substitution in the argument |
| E11 | `sh -c "echo hi > '.'./stray.txt"` | deny | **allow** | deny, `'/stray.txt'` | a quote mid-word is not split; the backstop |
| E13 | `curl $HUB_URL/$X` | deny | **allow** | deny, cannot be checked | an expansion after the reference |
| E14 | `echo hi > $HUB_URL/../../x` | deny | **allow** | **allow** | it resolves inside, and writes inside |
| E15 | `cp notes.md ../ws=y/z` | deny | **allow** | deny, `'../ws=y/z'` | a continuing word (D1) |
| E16 | `echo hi > "../ws y.txt"` | deny | **allow** | deny, `'../ws y.txt'` | the same at a space. *Shell* |
| E18 | `curl -o<workspace>=x $HUB_URL/api` | deny | **allow** | deny | the backstop's candidate continues |
| S2 | `echo "$(cat /etc/x)"` | deny | deny | deny, `'/etc/x'` | the substitution's contents are a command |

**Bodies and messages that name a path (R2).** Each is refused today, and each is allowed after.
J2 and J3 are forms of F300's own request.

| row | command | today | R1 (Windows) | after |
|---|---|---|---|---|
| J1 | `curl -d '{"description": "update src/a.py"}' $HUB_URL/x` | deny `'/a.py'` | allow | **allow** |
| J2 | H1 with the body written `-d "{\"title\": \"x\"}"` | deny | **deny** `'\\'` | **allow** |
| J3 | the same body with `\"fix sub/hello.py\"` as the title | deny | **deny** `'\\'` | **allow** |
| J4 | `git commit -m 'fix: sub/hello.py'` | deny `'/hello.py'` | allow | **allow** |
| J7 | `git commit -m 'fix sub/hello.py, and sub/other.py'` | deny | allow | **allow** |
| J8 | `python sub/hello.py --out=sub/out.txt` | deny | allow | **allow** |
| H2p | H2 through the PowerShell tool, body `` "{`"title`": `"x`"}" `` | deny | allow | **allow** |

J4 is a commit message, refused today because it names a path. F52 (2026-08-26) recorded agents
losing turns to refused `git commit`s, with the root cause unconfirmed. **Whether J4's mechanism is
part of F52 is unverified.** F52 also records a refused bare `git --version`, which J4's mechanism
cannot explain.

**Residuals recorded, unchanged by this change.**

| row | command | today = after | why it stays |
|---|---|---|---|
| X4 | `cmd 2>/dev/null` | deny `'/dev/null'` | an absolute path outside the workspace. Whether the null device should pass is a containment question, open (D10) |
| X5 | `python src/*.py` | deny `'/*.py'` | glob characters are not in rule 5's class, because bash's `.*` can match `..` (D8) |
| X6 | `git show HEAD:sub/hello.py` | deny `'/hello.py'` | a colon in the first segment (D1) |
| X7 | `python $(pwd)/sub/hello.py` | deny | today as `'/sub/hello.py'`; after, as cannot be checked, because the substitution is part of the argument (D1, R2) |
| X8 | `cat sub/a<NUL>b` | deny | not a word character → backstop |
| X9 | `python /c/Users/…/ws/sub/hello.py` (the workspace, in MSYS form) | deny | `os.path` on Windows reads `/c/…` as `C:\c\…`. MSYS translation is not attempted |

**Count:** 56 labelled rows. The prototype's `ROWS` holds 49 commands. X7, X8, X9, H12–H16, the
`$HUB_URL.evil.example` case in D4, and the long URL in D5 were measured beside it by
`measure3.py`, `measure4.py` and `measure5.py` in the same directory, and N8 by a direct `_decide`
call. On the prototype's own run, **exactly 14 rows move**: W1–W5, H1–H4, R11, N3 and X1–X3.
H15 and H16 also move, which makes **16**. Both are the run's own Hub, written differently.

**R2's count.** `table.py` holds 91 commands: D2's rows with X1–X3 split by tool, plus the E, J,
S and L rows. On Windows, **26 move**.
- **21 go from refused to allowed.** Thirteen are R1's: R11, W1–W5, H1–H4, H15, H16 and N3. Eight
  are R2's: H2p, E14, and J1–J4, J7, J8.
- **5 go from allowed to refused.** X1b, X1c, X2p and X3p are Windows escapes. X1b goes through
  the Bash tool, and was measured writing outside in Git Bash. E7 is the joined `$HUB_URL@host`.
- On R1's own 56 rows, with X1–X3 read as PowerShell, the same 16 move as R1 counted. With X1–X3
  read as Bash, 13 move.

**R3's count.** R3 changes the backstop only, so its reader agrees with R2 on all of D2's earlier
rows (re-measured: `testbed/scratch/r3f300/table3.py`, 78 rows, no divergence). It adds two
allowed→refused moves on Windows, both backstop-`\` cases: Z1 (an escape today) and Z3 (a residual
over-refusal, G3's twin). Z2 is refused *today* — for a false reason — so it is not a move against
today, but it is a fix against R2, which allowed it. So after R3, **28 move on Windows**: 21 to
allowed, and 7 to refused (R2's five plus Z1 and Z3).

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

**R2 attacked it, and it stands.** Each of the three reasons was re-derived against today's
`_decide`. N4 is allowed, and so are `curl -d @notes.md example.com` and `curl example.com?q=x`.
So every byte N3 could send leaves today without the `/x`. R2 adds one reason. The shape that makes
N3 a relative path is the same shape J4 and J8 depend on: word characters, dots and `/`. Any rule
that refuses N3 by its shape refuses `sub/hello.py` in a commit message by the same shape, unless it
guesses which first segments are hosts.

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
form (rule 1) has no such gap. R2 checked this machine only: of `~/.bashrc`, `~/.bash_profile`,
`~/.profile` and `~/.zshrc`, only `~/.zshrc` exists, and it does not name `HUB_URL`. Whether the
harness sources a profile at all was not measured.

**What R2 added to D4.**
- **An address this section accepts is still judged as a path** (D1, rules 1 and 2). For a
  reference, the approver's own `HUB_URL` value is put in its place first. So
  `$HUB_URL/../../../x` is refused as outside (E4). Without this, *"the run's own Hub"* would have
  been a licence to write outside the workspace through a directory named `http:`.
- **What follows a reference may not contain an expansion.** `$HUB_URL/$X` names the Hub's host,
  but as a path `$X` can carry any number of `..` (E13). It is refused as cannot be checked.
- **`%HUB_URL%` is not a reference.** R1 listed it. Neither shell a Claude run uses expands
  `%NAME%`, and a nested `cmd /c` is not something a reference test should trust. It falls to
  rule 3.
- **Which spelling counts as a reference follows the shell.** `$HUB_URL` and `${HUB_URL}` are
  case-sensitive, because bash's variables are. `$env:HUB_URL` is not, because PowerShell's are
  not. The count condition stays case-insensitive, so `hub_url=…; curl $HUB_URL/x` still fails
  it.

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

**Cannot-be-checked refusal** (rules 2 and 3). R2 widened the wording, because rule 3 now looks
anywhere in the word:

> `'<word>' contains a variable, '~' or a command substitution that the shell expands when it
> runs, so where it points cannot be checked against your workspace; write a path relative to your
> workspace instead`

**Outside refusal** (rules 5 and 6): unchanged, `'<word>' is outside your workspace`. What changes
is that `<word>` is now the whole path the shell will use (rule 5), not a fragment of it. For an
unquoted path, that is exactly what the agent wrote. For a quoted or joined one, it is the path
after the shell has removed the quotes: `'.'./stray.txt` is refused as `'../stray.txt'`. For a word
that continues, it is the whole argument (D1).

**The bound applies to the quotation as rendered, not to the word (R2).** R1 bounded the word to
200 characters and then rendered it with `repr`. `repr` expands what it cannot print. Measured:
200 characters of NUL render as 802, 200 zero-width spaces as 1,202, and 200 characters from the
astral plane that are not printable as 2,002. So a word bounded to 200 characters could still
produce a reason over the cap, and the refusal would still go unrecorded. The quotation, as
rendered, is at most **200** characters, cut with `…`. The longest fixed wording, measured from
R2's strings, is the cannot-be-checked text at **197** characters. The network text is 168 and the
outside text is 26. So no reason exceeds 400.

**Why a bound at all.** Measured by R2: a URL of exactly 1,200 characters gives a
**1,224**-character reason *today*. R1 recorded 1,244, which is what a 1,220-character URL gives.
R1's network wording makes it longer still. `POST /agent-actions/permission-decisions` caps
`reason` at **1000** (`PermissionDecisionCreate`, `hub/hub/api/v1/agent_actions.py:840`). R2
measured the schema: a 1,000-character reason validates, and a 1,001-character one raises
`ValidationError`. That the route then answers 422 is FastAPI's handling of that error, **read, not
driven**. `_report_decision` swallows the 422, so the
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
`…os.environ['HUB_URL']+'/api/v1/agent-actions/tasks'…`. It is refused as outside, `'/api/v1/…'`,
**today and after**.

**R2 corrected the argument; the outcome is unchanged.** R1 wrote that the quote splits the
`'/api/…'` literal into a word that begins with `/`. Under R2's lexing the single quotes sit inside
a double-quoted argument, so they are literal, and nothing splits there. The word is
`urllib.request.Request(os.environ['HUB_URL']+'/api/v1/agent-actions/tasks'`. It has quotes in its
middle, so it is not plain, and rule 6's backstop finds `/api/v1/agent-actions/tasks` and refuses
it.

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
- **(f) R1's reader: split at quotes and judge the pieces (rejected by R2).** It judged strings the
  shell never produces, and let sixteen commands through that today's regex refuses. Five of them
  wrote outside the workspace in Git Bash (D2, E rows). It also refused F300's request on Windows
  whenever the JSON body was written with bash escapes (J2).
- **(g) Read every command both ways and refuse if either refuses (rejected by R2).** It needs no
  tool name, and it refuses X1c under any tool. But the PowerShell reading of bash's `\"` leaves
  `\title\` as a rooted word, so it refuses J2 and J3. That is F300 undelivered on Windows for the
  commonest way to write the body. So it is kept only for a tool whose dialect is unknown (D1).

## D9 — The escapes that never went through the regex stay as they are

R8, R9 and a `cd` in an earlier call are allowed today and after. Relative words are resolved
against the workspace root, which is the run's *starting* directory. The harness's shell keeps its
working directory between calls. `_decide` cannot see it, and the docstring already says *"a
boundary, not a sandbox"*. The change rewrites the `_decide` comment that claims relative paths
*"resolve against the run's cwd, which is the workspace"*, because that is the claim F321 and R1
both show is false. The rewrite states the resolution rule and this limit instead.

**PowerShell has its own members of this class, and they are named here so nobody infers the list
is Bash-only** (added 2026-09-12 by the pre-approval Opus review). A path *built at runtime* by a
cmdlet or .NET call never appears as a word the reader can judge: `Set-Content (Join-Path ..
stray.txt) "hi"` was **measured** in Windows PowerShell 5.1 writing `stray.txt` in the workspace's
parent, and the reader sees only the separator-less words `..` and `stray.txt` (rule 4). The same
holds for `Resolve-Path`, `Convert-Path` and `[IO.Path]::Combine('..', 'x')`. These are allowed today
and after, for the same reason `cd ..` is. They are residuals, not rows this change closes. Closing
them is a separate change with its own rounds.

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
   **R2: re-derived, and the bound moved to the rendered quotation** (D5). The longest fixed text
   is 197 characters.
5. **The tool names (R2).** The lexing dialect is chosen by the tool name: `Bash` and
   `PowerShell`. Both names are in the tool list of the Claude Code session R2 ran in, on this
   machine. **That a spawned run's approver receives `PowerShell` as `tool_name`, with its script
   in `command`, is unverified.** If the name differs, the reader falls back to reading both ways
   (D8(g)), which is safe and refuses J2. The night's drive (tasks §6) should record the
   `tool_name` of every approval it sees.
6. **Nested shells (R2).** The reader reads a `$(…)` substitution as a command of its own. It does
   **not** re-read the argument of `sh -c`, `bash -c` or `powershell -Command` as a command. A
   quote in the middle of such an argument keeps the word out of rule 5 (E11), so the backstop
   still sees what today's regex sees. That is the design's only defence there, and it is today's.
7. **A single-quoted literal `$` is over-refused (R3, decided: stays a residual).** Rule 3 refuses
   any word that holds a `$` and a separator. The lexer already knows a `$` inside single quotes is
   literal, not an expansion, so in principle rule 3 could ask "an *active* expansion", and let
   `curl -d '{"price":"$5/mo"}' $HUB_URL/api` through. R3 measured this: it is a false refusal
   (Z3-body class). **It is refused today too** — today's regex reads `/mo` as a path — so this
   change is no regression, and the shape has a one-line workaround (drop the `/`, or ask the
   operator). R3 leaves it as a residual rather than teaching the lexer to mark active-vs-literal
   `$` in a final verification round, which would add an unreviewed rule. Recorded here and in
   `decisions_for_user`; the clean fix (sentinel every active expansion at lex time, and make rule 3
   test the sentinel, not the character) is a small follow-up, not this change.

## D11 — What R3 re-derived, and the one thing it changed

R3 re-derived the argument against the code and the shells, not against R2's reasoning. It wrote its
own reader from the design's prose (`testbed/scratch/r3f300/reader3.py`, every R3 change behind a
switch), ran the shells directly (Git Bash 5.2.37 and Windows PowerShell 5.1), and compared all
three readers over 78 of D2's rows plus six attack rows (`table3.py`).

**What R3 confirmed against real shells.** Bash keeps a `\` before an ordinary character inside
double quotes (so X1b escapes) and removes it bare (so X1a stays inside). PowerShell's `''`→`'`,
`""`→`"`, and `$env:HUB_URL` is the environment variable while a bare `$HUB_URL` is a PowerShell
variable that expands to nothing (so a reference's dialect matters, D4). PowerShell 5.1 also splits
`"a"b` into *two* arguments where R2's lexer joins them — a curiosity that only ever refuses more,
never less (measured: Z6 denies under both readers), so it is not a defect.

**The one change: the backstop's `\` gap** (the paragraph under "Why rule 6 exists", the D2 Z rows,
and the count above). It is a real escape R2's reader passes and a real regression it introduces,
both Windows-only, both fixed by making rule 6's backstop open a candidate at a bare `\` on Windows.
R3 verified this is the *sole* divergence from R2: with every other switch off, only Z1–Z3 move.

**What R3 attacked and left standing.** The lexer's dialect rules (measured, correct). The
continuing-word rule and its "a prefix can only keep the path further in" argument (E15/E16 refuse
under both readers; a prefix lands inside a word's first name, which is then neither `.` nor `..`).
The trim set. D3's N3 widening (re-derived: every byte N3 sends leaves today without the `/x`).
D4's own-Hub test, D6's `python -c` refusal, and the rendered bound. The delta's requirement
scenarios were correct; the defect was in the design's rule 6, not in what the spec requires — and
R3 adds one scenario so a test pins the glued-backslash case.
