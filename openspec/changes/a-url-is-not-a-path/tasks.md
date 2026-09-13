# Tasks — a URL is not a path

Implementation belongs to a night window. No task here is complete because this plan exists. Only
verified implementation closes one.

**This change is Python-only.** No `hub/ui` file changes, so the committed bundle in
`hub/hub/static/ui` is **not** rebuilt. The Python lint set **is** required (§8).

**Two constraints of `hub/hub/mcp_server.py` bind every task below.**
- It is spawned standalone and may import **only** the standard library and fastmcp. `urllib.parse`
  and `urllib.request` are standard library. The Hub's schema is not, so the reason cap is restated
  (§2.4).
- `approve_tool_call` has **no return annotation**. With one, FastMCP emits `structuredContent`, and
  a correct `allow` is silently not honoured. Nothing in this change touches that function, and
  `test_response_carries_no_structured_content` must still pass.

**The table is written first, and the tree stays green at every commit.** The night window commits
each checkpoint. So §1 pins D2's rows against the **unmodified** `_decide`, marking each row
expected to move `xfail(strict=True)`, and §2 removes those markers as the reader lands. A strict
xfail that starts passing early is a failure. That is the point: a row may not change answer before
its rule exists.

## 1. Pin the table before the reader moves

- [x] 1.1 In `hub/tests/test_permission_approver.py`, add D2's table as one parametrized test over
  `_decide(<tool>, {"command": …})`, where `<tool>` is D2's tool column (`Bash` unless it says
  `PowerShell`). Every row goes in: R, W, H, N, G, X, **and R2's E, J and S rows**. Use the existing
  `workspace` fixture, which already has `sub/`, and set `HUB_URL=http://127.0.0.1:8016` with
  `monkeypatch`. The fixture's workspace directory is named `work`, not `ws`, so E15, E16 and E18
  are written against its real name. For each row, assert `allow`, and where D2 names a reason,
  assert on a distinguishing substring of it:
  - network: `"network address"` present, `"workspace"` absent;
  - cannot be checked: `"cannot be checked"` present, `"outside your workspace"` absent;
  - outside: the whole path, e.g. `"'../stray.txt'"`. For E1, that is the joined path
    `'../stray.txt'`. For E15, it is the whole argument `'../work=y/z'`.

  Rows are platform-scoped where D2 says so. X1b, X1c, X2p, X3p, E3 and X9 run on Windows only.
  On POSIX, every X row is pinned at today's answer, because `\` is not a separator there. The
  `ids=` are D2's labels, so a failure names its row.

  **R3's backstop rows Z1, Z2, Z3 (Windows only).** Z1 `sort -o"..\stray.txt" notes.md` and Z3
  `gcc -I"sub\include" x.c` are `deny` after, `'\stray.txt'`/`'\include'` outside; Z2
  `curl -o"..\out" http://127.0.0.1:8016/api` is `deny` after, `'\out'` outside. On POSIX all three
  keep today's answer (`\` is not a separator). Z1's write-outside is the drive's §6 witness.
- [x] 1.2 Add N8 as its own test: `_decide("WebFetch", {"url": "https://example.com/x", "prompt":
  "p"})` is **allowed**. It pins D7's statement that the rule governs shell text only. A future
  change that brings fetch under the rule must flip this deliberately.
- [x] 1.3 Add H12: with `HUB_URL` deleted from the environment, H1–H4 are refused.
- [x] 1.4 Run §1's tests against the unmodified `_decide`. Mark `xfail(strict=True, reason="a-url-
  is-not-a-path §2")` on exactly the rows D2 says move: W1–W5, H1–H4, H15, H16, R11, N3, J1–J4, J7,
  J8, H2p, E14, E7, and (on Windows) X1b, X1c, X2p, X3p, **Z1 and Z3**. Also mark every row whose
  **reason** assertion is new: R1–R5, R10, N1, N2, N7, G5, G6, X7, H5–H10, H13–H14, E1, E2, E4–E6b,
  E9, E13, E15, E16, and (on Windows) **Z2** (refused today, but for the URL's path, not `'\out'`). **Any other failure means the table is wrong, not the code.** Stop, re-measure the row
  with `testbed/scratch/r2f300/table.py`, and record what differed here. **Every E row except E7
  and E14 must pass its answer today**: each is refused by the unmodified `_decide`, and the pin
  is what makes a reader that lets it through fail CI.

  **Measured at S1 (night 2026-09-12, `u1-pin`): D2's *today* column is Windows-only.** On POSIX,
  today's regex reads `https://…` as `s://…` and `file:///…` as `e:///…`, which are relative there,
  so the URL resolves inside and the command is allowed (F331). Four marks are therefore
  platform-scoped rather than as listed above:
  - H4, H15 and H16 are xfail on **Windows only**. On POSIX they are allowed today and after.
  - X8 is xfail on **POSIX only**, with `raises=ValueError`. `posixpath.realpath` raises on the NUL
    byte today (D5, *Totality*), and §2.5 is what turns that into a decision.
  - H12's H4 case is xfail on **POSIX only**, because it is allowed there today.
  - The added row `F331` (`curl -T notes.md file:///tmp/stray.txt`, refused) is xfail on **POSIX
    only**.
  R10, N1, N2, N7, H5–H7, H13 and H14 keep their marks. On POSIX they fail on the *answer*, not
  the reason. Every mark was checked on both platforms: `testbed/scratch/night0912/why_each_row.py`
  on Windows and under WSL Ubuntu; that file prints which assertion each row fails. Then pytest ran
  under WSL with `posix_stubs.py`. No row disagreed with its mark on either platform. Z2 on POSIX is
  allowed today, so *"keep today's answer"* there means `allow`. H2, H2p and W6 are read as the
  `PowerShell` tool, as both measurement scripts read them. D2's `$env:` forms are PowerShell's.
- [x] 1.5 Commit §1 alone, green. This is the pin: from this commit on, a regex change that flips
  R1–R5 fails CI.

## 2. The reader

- [x] 2.1 In `hub/hub/mcp_server.py`, beside `_decide`, add the reader of D1 in its two stages.
  - **The lexer**, a small state machine in the tool's dialect: `Bash`, `PowerShell`, or both for
    any other tool name. It handles the quote states, the escape character, the substitutions
    `$(…)` and `` `…` `` (recursed into, with depth bounded), and the argument-ending characters.
    It must not raise on any string.
  - **The words**: split at surviving whitespace, `=` and `,`; trim the D1 set from both ends; and
    record whether each word continues.

  Then add the six rules in their order. Keep `_ABSOLUTE_PATH_RE` as rule 6's backstop, applied to
  one word at a time, and rewrite its comment to say that is now its only use. **On Windows the
  backstop opens a candidate at a bare `\`, not only after a drive letter** (R3, D1): use a
  `\`-aware pattern where `os.sep == "\\"`, and today's exact regex on POSIX. Without this, Z1 (an
  escape today) and Z2 (a regression) pass. `_decide`'s `command` branch calls the reader with
  `tool_name`. The `_PATH_KEYS` branch for file tools is **unchanged**. `shlex` is not used (D8(c)).
- [x] 2.2 The run's-own-Hub test of D4. For a URL: `urllib.parse.urlsplit`, schemes compared
  ignoring case, `hostname` equal, effective ports equal (80 and 443 by default), `username` and
  `password` both `None`, and any `ValueError` treated as "not own". For a reference, all of these
  hold:
  - the remainder is empty, or starts with `/ ? #` and contains no `$`;
  - the approver has a non-empty `HUB_URL`;
  - the command's case-insensitive `HUB_URL` count equals its reference count;
  - `%HUB_URL%` is **not** a reference.

  **Then judge the accepted word as a path**. A literal URL is judged as it stands. A reference is
  judged with the approver's `HUB_URL` value in place of the reference. Refuse if it resolves
  outside (E4–E6b).
- [x] 2.3 The three refusal texts of D5, verbatim from `design.md`. An edit to their wording is an
  edit to the design, so record it there.
- [x] 2.4 The bound. A reason's **rendered** quotation (after `repr`, or whatever renders it) is at
  most 200 characters, with `…` where it cuts. Bounding the word before rendering is the defect D5
  records. Restate the Hub's cap as a module constant beside `MIN_WAITING_SECONDS`, with the same
  kind of comment. Add a test asserting that the longest possible reason is at or under
  `PermissionDecisionCreate.model_fields["reason"]`'s `max_length`, which the test reads from the
  Hub's schema. Pydantic 2 keeps it in that field's `.metadata` as `MaxLen(max_length=1000)`, not as
  an attribute of the field (measured by R2). The longest possible reason is the longest fixed text
  (197 characters) plus 200.
  **Also** pin two things: a 1,200-character URL now gives a reason within that cap (today it gives
  1,224), and so does a URL followed by 400 characters of `"\U000e0001"`. Today the second gives
  well over the cap, and under R1's bound it gave 2,000 or more (D5, table row L1).
- [x] 2.5 Totality. Catch `(OSError, ValueError)` around `realpath` and `commonpath`, and refuse.
  Add a test with a NUL byte in a path word that asserts a decision is **returned** (either
  answer), so that it runs meaningfully on CI's Linux, where it raises today (D5).
- [x] 2.6 Rewrite `_decide`'s docstring and the comment at its `command` branch (D9). It reads
  shell text as the tool's shell will, then word by word. Relative words are resolved against the workspace root, which is where
  the run started. A `cd` in an earlier call is not seen. It is a boundary, not a sandbox. It does
  not govern network access, only which address a shell command's text may name. **Delete** the
  sentence *"Relative paths are left alone: they resolve against the run's cwd, which is the
  workspace."*
- [x] 2.7 Remove every §1.4 `xfail` marker. The whole table is green, with no marker left, and
  `grep -n xfail hub/tests/test_permission_approver.py` shows none of this change's.

  **Done at S2 (night 2026-09-12, `u2-reader`), measured.**
  - `grep -c xfail hub/tests/test_permission_approver.py` is 0. `_MOVES`, `_MOVES_ON_WINDOWS` and
    `moves=` are gone.
  - The file on Windows: **176 passed, 1 skipped** (the symlink test). The baseline chunk: **285
    passed, 1 skipped**.
  - Under WSL Ubuntu with `posix_stubs.py`: 170 passed, 1 skipped, 2 failed. The skip is the
    §2.4 cap test, which cannot import the Hub's API there. The two failures are
    `test_generated_context_does_not_advertise_the_approver` and `test_codex_posture_mapping`.
    Both fail on the stub environment's missing `sse_starlette.event`, and neither reaches
    `_decide`.
  - `why_each_row.py`: 0 disagreements on both platforms (98 rows on Linux).
  - Every row that was xfail on Windows at S1 passed before its marker came off. That is 59 of
    59, printed by the same checker.
  - The fixed wordings measure 197 (cannot be checked), 168 (network) and 26 (outside)
    characters with the leading space. Those are D5's figures.

  **The implementation departs from R2's reader in four places.** D11a records each, with its
  measurement.
  - A `$` that the shell will not expand is not a reference. New rows **E20, E21 and E22**
    wrote outside the workspace in Git Bash, and R2's and R3's readers both allowed them.
  - References follow the tool's dialect. New row **H17**.
  - A continuing word's refusal quotes the whole argument only when the extension is what
    found it. So H11 keeps D2's *"unchanged"* reason.
  - Nesting past the bound falls back to the backstop over the whole text.

  New tests beside the table:
  - the §2.4 cap agreement, and the longest reason of every kind;
  - the 1,200-character URL;
  - the rendered-bound row L1;
  - four NUL-byte cases (§2.5);
  - an 18-case totality sweep;
  - a path nested past the bound.

## 3. The wire shape

- [x] 3.1 Beside `_call_tool_over_stdio`, add two cases through a **real spawn** of
  `mcp_server.py`, with `AW_WORKSPACE_DIR` and `HUB_URL` in the child's environment.
  - `curl -s https://example.com/x` answers `behavior: deny`, with a message that begins
    `Denied: 'https://example.com/x' is a network address`.
  - `curl -s "$HUB_URL/api/v1/agent-actions/tasks"` answers `behavior: allow`.

  Both results carry **no** `structuredContent`. This is the only test that sees the answer Claude
  actually receives.

  *Done (night 2026-09-12): `test_a_network_address_is_refused_on_the_wire` and
  `test_the_run_s_own_hub_is_allowed_on_the_wire`. Both fail against c12a7d3's server, measured:
  it answered `Denied: 's://example.com/x' is outside your workspace.` and
  `Denied: '/api/v1/agent-actions/tasks' is outside your workspace.`.*

## 4. Docs

- [x] 4.1 `docs/reference/permission-postures.md`, *"A shell command declares no path"*. Replace
  *"the approval tool does read absolute paths out of the command text"* with what D1 reads, in one
  or two sentences. Add one sentence saying that a shell command under **Workspace only** may name
  only the run's own Hub as a network address, and that this is a rule about the command's text,
  not a network boundary (`WebFetch` is not checked). Keep the page's per-posture framing. It states
  a requirement (`agent-run-sandboxing`, *"The product states which postures confine a run"*).

## 5. Mutation checks — every rule must be load-bearing

Nothing existing fails for the absence of most of these rules. So each is mutated once, and a
named row must fail. Record which row failed, then restore.

- [x] 5.1 Delete rule 6 (the backstop). G1–G4 must fail.
- [x] 5.2 Delete the `HUB_URL` count condition. H10 must fail.
- [x] 5.3 Delete the remainder condition (`/ ? #`). H8 must fail.
- [x] 5.4 Delete the userinfo condition. H13 must fail.
- [x] 5.5 Treat rule 3's words as plain relative. R4, R5 and G5 must fail.
- [x] 5.6 Resolve rule 5's relative words without joining them to the root. R1–R3 must fail.
- [x] 5.7 Make quotes delimit words instead of being removed and joined, which was R1's reader.
  **E1 and E2 must fail.** Then stop splitting arguments at surviving whitespace. **H1 must
  fail**: the quoted `Content-Type` header becomes one non-plain word, refused as `'/json'`. Also
  pin J5, `python -c "open('/etc/x','w')"`, as refused. It is refused under every split, and it
  guards the backstop rather than the split.
- [x] 5.8 Drop `\` from the Windows separators. X1b and X1c must fail (on Windows).
- [x] 5.9 Drop the bound. §2.4's long-URL test must fail. Then bound the word before rendering
  instead of after. §2.4's non-printable test must fail.
- [x] 5.10 Stop judging an accepted own-Hub word as a path. E4, E5 and E6 must fail.
- [x] 5.11 Drop the "continues" flag, judging every word as it stands. E15 and E16 must fail.
- [x] 5.12 Read the `PowerShell` tool's command in the bash dialect. X1c must fail (on Windows).
  Read the `Bash` tool's command in the PowerShell dialect. J2 must fail (on Windows).
- [x] 5.13 Look for rule 3's expansion only at a word's start. G6 must fail its reason assertion:
  it is still refused, but as `'/$X/stray.txt'` outside, through the backstop, and not as *cannot
  be checked*.
- [x] 5.14 Stop recursing into substitutions. S2 must fail.
- [x] 5.15 Allow an expansion after a reference. E13 must fail.
- [x] 5.16 On Windows, drop the bare `\` from rule 6's backstop (use today's drive-letter-only
  regex there). **Z1 and Z2 must fail.** This is the R3 gap: a backslash traversal glued to an
  option reaches the backstop, and the drive-letter-only regex lets it through.

- [x] 5.17 (added at S2, design D11a) Remove the `_LITERAL_DOLLAR` sentinel from `_lex`, at both
  places it is appended, so a quoted or escaped `$` becomes a plain one again. **E20, E21 and E22
  must fail.**

  **Done at S5 (night 2026-09-13, `u4-mutations`), measured on Windows.** Each mutation was applied
  alone by `testbed/scratch/night0912/u4/mutate.py` (UTF-8 in and out, every edit asserted to match
  exactly once). The whole of `hub/tests/test_permission_approver.py` then ran, and the file was
  restored by `git checkout` from the committed tree. `git status --short` was empty after every
  restore. Unmutated, the file gives 178 passed and 1 skipped. No named row survived its mutation,
  and no test was changed.

  | task | mutation | named rows: all failed | everything else that failed |
  |---|---|---|---|
  | 5.1 | rule 6 deleted | G1 G2 G3 G4 | H11 N5 N6 X5 X6 X8 E11 E18 J5 Z1 Z2 Z3 |
  | 5.2 | `HUB_URL` count condition deleted | H10 | none |
  | 5.3 | remainder condition (`/ ? #`) deleted | H8 | E7 E8 |
  | 5.4 | userinfo condition deleted | H13 | none |
  | 5.5 | rule 3's words judged as plain relative | R4 R5 G5 | H17 G6 X7 E9 E10 X2p X3p, the cap test |
  | 5.6 | relative words left unresolved (the pre-fix reading) | R1 R2 R3 | E1 E2 E12 E15 E16 E17 E19 X1b X1c E3, the cap test |
  | 5.6′ | relative words resolved against the process's own directory (`abspath`, no join) | none of R1–R3; see below | W1–W6 H1 N3 E15 E16 J1 J2 J3 J4 J7 J8 H2p, the cap test |
  | 5.7a | quotes delimit arguments (R1's reader) | E1 E2 | E7 E19 Z1 Z2 Z3 |
  | 5.7b | no split at surviving whitespace | H1, refused as `'/json'` | E16 J1 J2 J3 J4 J7 H2p |
  | 5.8 | `\` dropped from the Windows separators | X1b X1c | X2p X3p Z1 Z2 Z3 |
  | 5.9a | bound dropped | `test_a_long_url_is_refused_within_the_cap` | the cap test, the rendered-bound test |
  | 5.9b | word bounded before rendering | `test_the_bound_is_on_the_rendered_quotation_not_the_word` | the cap test |
  | 5.10 | accepted own-Hub word not judged as a path (rules 1 and 2) | E4 E5 E6 | E6b |
  | 5.11 | "continues" always false | E15 E16 | E17 E18, the cap test |
  | 5.12a | `PowerShell` tool read as bash | X1c | H2 H17 H2p X2p X3p |
  | 5.12b | `Bash` tool read as PowerShell | J2 | R11 H1 H3 X1a X2b X3b E4 E5 E7 E14 J1 J3 E3, the own-Hub wire test |
  | 5.13 | rule 3's expansion sought only at a word's start | G6, refused as `'/$X/stray.txt'` outside, not *cannot be checked* | none |
  | 5.14 | substitutions not recursed into | S2 | S3, the nested-past-the-bound test |
  | 5.15 | an expansion allowed after a reference | E13 | none |
  | 5.16 | Windows backstop without the bare `\` | Z1 Z2 | Z3 |
  | 5.17 | `_LITERAL_DOLLAR` sentinel removed at both sites | E20 E21 E22 | none |

  "The cap test" is `test_no_refusal_is_longer_than_the_hub_records`. J5 was still refused under
  both 5.7 mutations, as 5.7 requires.

  Two readings needed saying:
  - **5.6.** Read literally ("resolve against the process's own directory"), the mutation cannot
    fail R1–R3 under pytest. Its directory is `hub/`, which is itself outside the fixture's
    workspace, so `../stray.txt` is refused either way. It is killed by W1–W6 instead, whose inside
    paths land in `hub/` and are refused. When the process's directory is the workspace, that
    mutation gives the same answer as joining, so no row could separate them. R1–R3 fail under
    the reading 5.6 means: relative words not resolved at all.
  - **5.12b.** J2 fails, but on its first word: `$HUB_URL` is no reference in PowerShell. H1 fails
    the same way. The mutation is killed, but J2 does not show the body's `\"` being lexed
    differently. That is not a gap: the reference rule kills the mutation first.

## 6. Drive it — the table is an argument, and a drive is the product

Every real agent turn binds `claude-haiku-4-5`. No job is left enabled. The drive Hub runs on a
port chosen that night, with a fresh profile, started from `hub/` with uvicorn **from source**,
and no `.py` under `hub/hub` or `src` newer than the process. Never 8000 or 8010.

- [ ] 6.1 **Pre-fix, first.** `git worktree add ../aw-url-prefix <sha>` at the commit **before**
  §2's (not `git stash`). Start the drive Hub from that worktree, on a fresh git fixture project
  containing `sub/hello.py`, with one agent on the default posture (no override) and a Haiku runner.
  On its **first** turn it is told the HTTP form, because there are no grounds for MCP yet.
  1. Ask it to create a task through that form with `curl`.
  2. Ask it to run `python sub/hello.py`.
  3. Ask it to run `curl -s https://example.com/`.
  4. **On Windows only**, ask it to run `echo hi > "..\stray.txt"` with its Bash tool (X1b).

  Read `event_logs` for `permission_denied`, and the transcript's tool results. Asks 1–3 must be
  refused, for filesystem reasons: `'/api/…'`, `'/hello.py'` and `'s://example.com/'`. Ask 4 must
  be **allowed**, and `stray.txt` must appear in the fixture's parent directory: it is an escape
  today (D2). If any of these does not hold, this is not a reproduction. Say so and stop. Delete the
  stray file and remove the worktree afterwards.
- [ ] 6.2 **Fixed tree**, same fixture shape, on a fresh project and agent:
  - Ask 1 creates the task. Read `tasks`: it exists, created by the run, with no
    `permission_denied` for that call.
  - Ask 2 prints `hello from sub`.
  - Ask 3 is refused, and the tool result carries D5's network text verbatim.
  - Ask 4 (Windows) is refused as `'..\\stray.txt' is outside your workspace` (the reason renders
    the word with `repr`, so the backslash is doubled), and no
    `stray.txt` appears in the parent.
  - **Ask 5 (Windows, R3): the glued-option form.** Ask it to run `sort -o"..\out.txt" notes.md`
    (its Bash tool). Pre-fix (§6.1) this **must be allowed** and `out.txt` must appear in the
    parent — an escape today. Fixed, it is refused as `'\\out.txt' is outside your workspace`, and
    no `out.txt` appears in the parent. This is the R3 backstop finding, and a drive is what checks
    it rather than the table (D11).
  - Record the `tool_name` of every `permission_denied` row the drive produced. D1 chooses the
    lexing dialect by that name, and that the approver receives `Bash` and `PowerShell` as those
    names is unverified (D10 item 5).
  - `event_logs` holds that refusal as `permission_denied`, with the same reason. That is the
    record the operator reads, and the question that F108 established the rounds never ask.
- [ ] 6.3 **What the agent does next.** In 6.2's transcript, after ask 3's refusal, record what the
  agent did: called `ask_user`, stopped and reported, or tried another route (`python -c`, `wget`,
  `WebFetch`). This is one observation, not a rate. Record it verbatim and do not grade it here;
  §7.2 is the judgement.
- [ ] 6.4 Confirm every run in the drive profile joined to `claude-haiku-4-5-20251001`, that `GET
  /jobs` is empty or every job is disabled, and stop the Hub.

## 7. Verification only a human can do

- [ ] 7.1 **Is the refusal legible where the operator reads it?** Open the agent's activity in the
  served UI and read the network refusal from §6.2. Does it tell you what happened and who can
  change it, without sending you to look at the filesystem? An agent can check that the string is
  there. Only you can say whether it reads.
- [ ] 7.2 **Is the way out the one taken?** Read §6.3's observation. An agent that routes around
  the refusal with `python -c` is the failure the research's incident report describes, and the
  wording in D5 is this change's only lever on it. Decide whether the wording needs to change.
  That is a product judgement, not a test.
- [ ] 7.3 **Decide D10's open items:** N3 (the one widening), and `/dev/null` (X4). Decide them or
  leave them open, but in writing, in `spec-queue/DECISIONS.md`.

## 8. The gate

- [x] 8.1 `ruff check src/ hub/ tests/`, `black --check src/ hub/hub/ hub/tests/ tests/
  --target-version py311`, `mypy src/`. Use CI's path list, not a narrower one.
  *Measured at 3fba6b2 (night 2026-09-12, under `py -3.11 -m`): ruff "All checks passed!",
  black "565 files would be left unchanged", mypy "Success: no issues found in 22 source files".*
- [x] 8.2 `py -3.11 -m pytest tests/ -q` from `hub/` (the whole Hub suite), under `py -3.11`, never
  bare `python`.
  *Measured at 3fba6b2 (night 2026-09-13, Windows, `-p no:cacheprovider`): "4194 passed, 86
  skipped, 261 warnings in 2079.29s (0:34:39)", exit 0. The JUnit report agrees: 4280 tests, 0
  failures, 0 errors. Neither known intermittent fired (F292 `database is locked`, F314
  `test_a_wide_flows_state_is_still_one_call`), so nothing needed attributing. The 30
  `PytestUnhandledThreadExceptionWarning`s are aiosqlite's `Event loop is closed` in
  `test_migrations.py` round trips. They are warnings, not failures, and come from no file this
  change touches.*
- [x] 8.3 `openspec validate --strict a-url-is-not-a-path` after every delta edit.
  *Measured at S3/S4 (night 2026-09-12): "Change 'a-url-is-not-a-path' is valid". No delta was
  edited in S2–S4; 9.4 runs it again before archiving.*
- [x] 8.4 No migration, no API or schema change. `git diff <base>.. -- hub/hub/migrations
  hub/hub/api hub/ui` is empty.
  *Measured at 3fba6b2 with base c12a7d3 (arm(night)): 0 diff lines. The whole diff since the
  base is `hub/hub/mcp_server.py`, `hub/tests/test_permission_approver.py`,
  `docs/reference/permission-postures.md`, this change's design and tasks, `FINDINGS.md`,
  `DEAD-ENDS.md`, and the night window's own log and state files.*

## 9. Close it out

- [ ] 9.1 Set `F300`, `F312`, `F321` and `F323` to `fixed <sha>` in `scripts/drive/FINDINGS.md`, each
  naming the task that closed it and quoting §6.2's evidence. In `F312`, correct in place, in a
  dated block, the claim *"No agent on the default posture can make any network request from a
  shell command"*: `curl example.com` (no `/`) was always allowed (D2 N4). In `F300`, correct
  *"any URL in any shell command is denied"* the same way.
- [ ] 9.2 `F322` stays **open**, and so do `F299` and `F301`. Say so in the close-out commit, so
  that nobody reads this change as closing them.
- [ ] 9.3 Do **not** edit `spec-queue/DECISIONS.md`. D6's correction to 1c/1d is the operator's to
  record. If the review page for the night has not already carried it, put it in
  `decisions_for_user`.
- [ ] 9.4 `openspec validate --strict a-url-is-not-a-path`, then archive with the
  `openspec-archive-change` skill. Before syncing, compare the MODIFIED block with the main
  `agent-capability-plane` block. Every scenario must survive, and the F301 clause must be
  verbatim.

## 10. User test guide

- [ ] 10.1 `test-guide.md` in this change is the operator's walkthrough. Keep it true to what
  shipped, and correct it if D5's wording changes.
