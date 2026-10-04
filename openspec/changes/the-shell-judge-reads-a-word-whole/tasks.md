## 0. Before building

- [x] 0.1 R2: an independent re-derivation of proposal and design against `hub/hub/mcp_server.py` (`_lex`, `_words`, `_read_command`, `_judge_word`, `_where`, `_judge_path`) and the `agent-run-sandboxing` spec; recorded in `spec-queue/tracks/B4.md`
- [x] 0.2 R3: a second independent re-derivation, not starting from R2's notes
- [x] 0.2b R4 (revise round after the operator's 2026-09-24 review): re-derived from the code at `b7d976a`; recorded in `B4.md` under "R4"
- [x] 0.2c R5: an independent verification round of the R4 design, not starting from R4's notes
- [x] 0.2d R6 (revise round after the second Opus pre-approval review, `spec-queue/tracks/reviews/B4-2026-09-24-second.md`, and the operator's `B4-link-dotdot`): D11, D12, the memo key's colon flag; recorded in `B4.md` under "R6"
- [x] 0.2e R7: one independent comparison round of R6's fixes against the code, as the second review asks before APPROVE WITH FIXES; recorded in `B4.md` under "R7" (D8 step 4: the `..` refusal names where it lands, the literal component's link test is `os.lstat`, raises inside `_glob_links` stated, one named cost)
- [x] 0.2f R8 (the third Opus pre-approval review's fixes, `spec-queue/tracks/reviews/B4-2026-09-24-third.md`; the operator approves after this round): D2 step 6, the whole value judged as the path it spells (between its colons on a drive-letter host); D8 step 1's claim restated; D8 step 2 relaxes only a bracket expression `fnmatch` cannot read; D8 step 4's listed path; D12's cost widened to the shared `node_modules` link; the `workspace_writes.py` docstring task. Measured with real junctions in `testbed/scratch/b4-r8/`; recorded in `B4.md` under "R8"
- [x] 0.3a The operator answers design Open Questions 1 to 4: answered 2026-09-24 afternoon in `spec-queue/DECISIONS.md` (`B4-residuals`: the `case` arm stays, the four device names, this change first and the sibling in the same window; `B4-dep-links`: build as written, residual filed as F444)
- [x] 0.3 The operator approves the change in `spec-queue/APPROVALS.md` (after the Opus pre-approval review); before `mcp_server.py` is edited, the operator is told that `:8000`'s next run is judged by the edited file, committed or not -- `DECISIONS.md` `B4-approve` (DECIDED): both B4 changes approved as R8 left them

## 1. Tests first — each must fail on today's code or on the R3 design as written (each row says which)

Shared fixture, new in `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, shaped like `test_permission_approver.py`'s `workspace`:

- a sibling `outside/` holding `x`;
- a link `work/up` → `outside`, made with `os.symlink` on POSIX and `_winapi.CreateJunction` on Windows (no privilege needed);
- `work/sub/` with `a.py`, `b.py`;
- an inside link `work/in` → `work/sub`;
- (R6) an inside link `work/sub/l` → `work` itself (a link whose target is shallower than the link; D12). It is inside, so every existing control stays allowed: `ls sub/*` matches it and judges it inside, and a `**` walk does not descend through it.
- (R8) a link `work/sub/@s/p` → `outside` (the shape `npm link` makes under a scope), a directory `work/a'b` holding a link `up` → `outside`, and a directory `work/a@b` holding a link `l` → `work`. `@s`, `a'b` and `a@b` are directories inside, not links, so `ls sub/*` and the root globs above are unchanged; `ls sub/**/x` without `globstar` stays allowed (the walk descends the directory `@s`, which holds no `x`, and does not list below it).

- [x] 1.1 Rows allowed after, refused today (each FAILS today): `ls test/*.test.js`, `grep -r foo src/*.py`, `find . -path './src/*' -name x`, `npm install @types/node`, `ls node_modules/@babel/core` (no link), `git show HEAD:src/a.py`, `git log --format=%h/%s`, `printf '%s/%s' a b`, `python -c 'print(1/2)'`, `sed -E 's/(foo)/\1/' f`, `mkdir -p src/{a,b}`, `ls src/?.ts src/[ab].ts`, `gcc -I./include/x a.c`, `ls 2>/dev/null` (Bash), `echo x > /dev/stderr` (Bash), PowerShell `Get-ChildItem src\*.py` -- in `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, with the shared fixture; made to pass by D2's rule-6 piece reading plus D4 (bash devices) and D5 (schemeless network addresses) in `hub/hub/mcp_server.py`. Flipped the same 9 rows the design's R1 prototype measured in `test_permission_approver.py` (X4, X5, X6 to allow; N5, N6 to the network reason; G3, E11, Z1, Z2 to quote the piece); also found and fixed one the design didn't anticipate: `test_hub_own_call.py::test_the_9_10_form_is_refused_by_the_judge_alone` pinned the old backstop's false refusal of a PowerShell `-Value` literal that merely contained `/x.html`-shaped text, now correctly read as the inside relative piece `spec/x.html` and updated to expect allow
- [x] 1.2 Brace escapes refused as outside (F403), each FAILS today (allowed): `cp notes.md .{,.}`, `cp notes.md {.,.}.`. Brace escapes refused today only by the backstop, which must stay refused: `cp notes.md .{,.}/x`, `cp notes.md {.,.}./x`, `cp x src/{a,..}/../y`. The last three PASS today and FAIL against rule 6 rewritten without D1 (R1's prototype measured all three allowed). Rows 1.2a-e added to `_TABLE`; made to pass by task 2.1's D1 (brace sentinels in `_lex`, `_expand_braces`, `_read_command` judging each alternative). Confirmed against real Git Bash (`.{,.}` -> `. ..`, `{.,.}.` -> `.. ..`), not assumed.
- [x] 1.3 Braces an inner shell expands (R2). Rows 1.3a-j added to `_TABLE`; made to pass by `_mark_inner_brace_sentinels` plus a second `_read_command` pass over every argument holding a literal brace (quoted, escaped, or any brace in the PowerShell dialect), judging the words its bash-unquoted expansion would produce in addition to the words `_words` already reads literally. Confirmed against real Git Bash, not assumed (`.{,.}/x` -> `./x ../x`, `{,..}/x` -> `/x ../x`, `src/{a,..}/../y` -> `src/a/../y src/../../y`, `.{,.}` -> `. ..`). Controls (`awk`/`jq`/`sed` brace-literal rows, `${X}/y`) unaffected.
  - Refused: `bash -c 'cp n .{,.}/x'`, `sh -c 'cp n {,..}/x'`, `bash -c "cp x src/{a,..}/../y"` (Bash tool), and `bash -c 'cp n .{,.}/x'` (PowerShell tool). Each PASSES today (backstop `'/x'`) and FAILS against rule 6 without the inner-shell brace reading.
  - `bash -c 'cp n .{,.}'` refused. FAILS today (allowed).
  - Allowed: `awk '{print $1, $2}' f`, `jq '{a: .x, b: .y}' f`, `sed 's/a{2}/b/' f`. (R5, `B4-drive-exists`) Once the sibling change is built, the `jq` row stays allowed on the `hub-judge-windows` job only because drives A and B do not exist there. The sibling's task 1.5c pins that with the drive probe patched; if this row ever fails on Windows, check the runner's drives first.
  - `echo hi > ${X}/y` stays refused as uncheckable.
  - `cp notes.md '.{,.}'/x` is now refused (the accepted cost).
- [x] 1.4 Glob parents (D3): `ls .*/x`, `ls ..*/x`, `cp x .[.]/y`, `ls ../*`, `rm -rf ../*.py`, PowerShell `Get-ChildItem ..\*` refused, each quoting the whole piece. `ls sub/.*/x`, `cp x sub/..?/y` allowed. The refused rows PASS today with a fragment reason and FAIL on the reason assertion. Rows 1.4a, 1.4h-n added to `_TABLE`, plus a dedicated reason-text table (`_DOTDOT_GLOB_REASON_TABLE`) asserting each refused row quotes the whole piece, not a fragment -- made to pass by `_rewrite_dotdot_globs` in `hub/hub/mcp_server.py`, applied before `_judge_path` at both rule 5's and rule 6's call sites. Verified, not assumed: measured against real Git Bash 5.2.37 with `shopt -u globskipdots` (off, matching the pre-5.2 bash this rule guards against) -- `.*` -> `. ..`, `..*` -> `..`, `.[.]` -> `..`, `..?` stays literal (no match). Checked today's actual pre-change behaviour (not the task's own framing) with a throwaway script first: `ls .*/x`, `ls ..*/x`, `cp x .[.]/y` were actually **allowed** today (not refused-with-fragment as queued), while `ls ../*`, `rm -rf ../*.py` and the PowerShell row were already correctly refused quoting the whole piece (no fragment bug reached rule 6's own piece reading) -- the three already-refused rows are now regression controls, not new behaviour. Mutation check (`git stash` the `mcp_server.py` change): exactly rows 1.4a, 1.4h, 1.4i fail in both tables without the fix; 1.4j/k/l and 1.4m/n unaffected. Full regression set (`test_the_shell_judge_reads_a_word_whole.py` + the six D2-named files): 686 passed, 2 skipped. ruff/black/mypy clean (mypy's one pre-existing `approve_tool_call` error now at line 2390, same annotation gap, confirmed unrelated by reading the function there)
- [x] 1.4b (R4, D3 extglob) `bash -O extglob -c 'cp n @(..)/x'` and `bash -O extglob -c 'cp n ?(..)/x'` refused, the reason quoting `'@(..)/x'` / `'?(..)/x'`. Each PASSES today (tail `'/x'`) and FAILS against the R3 design (piece `..)/x`, inside); assert the reason, which FAILS today too. Controls allowed: `grep -E 'a*(b|c)' f`, `grep -E 'x+(y)' f`

  **Iteration 37.** Re-derived against the current code before building, same discipline as 1.6's
  rows: measured `_decide` directly (throwaway `py -3.11 -c` one-liner, not committed, real
  `AW_WORKSPACE_DIR`) for `bash -O extglob -c 'cp n @(..)/x'` and the `?(..)/x` row. Both are
  **already refused today**, each naming the whole extglob piece (`'@(..)/x'`, `'?(..)/x'`), not
  only the tail `'/x'` -- the task's own text is stale, describing the pre-D3-extglob world task
  2.2's slice (iteration 25, this file's task group below) already fixed; the R3-design framing
  ("FAILS against the R3 design") is likewise moot once R4's `_rewrite_dotdot_globs` extglob
  handling landed. The grep controls (`a*(b|c)`, `x+(y)`) are also already allowed: `(` there
  follows `a`/`x`, not an extglob trigger (`@ ? * + !`), so `_extglob_span_at` never opens a group
  and the word is read as an ordinary inside path. So this task needed test coverage only, not a
  production change -- the bare-group form (`cp n @(..)/x` with no `bash -c` wrapper) already had
  a reason-asserting test from task 2.2's slice; this task specifically asks for the `bash -O
  extglob -c` wrapper and the grep controls, which had no test yet.

  Added `test_an_extglob_dotdot_group_still_refuses_inside_an_inner_bash_invocation_1_4b` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. **Mutation-checked**: temporarily forced
  `_rewrite_dotdot_globs` to never find an extglob group (`spans = []`) -- the new test's first
  assertion fails (`allow: True`) against the mutation, confirming it is load-bearing; reverted
  with a backup copy and confirmed `git diff --stat hub/hub/mcp_server.py` is empty afterward. `py
  -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **110 passed** (was
  109, +1). Broader regression set (`test_permission_approver.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): **736 passed,
  2 skipped**, no regressions. CLI suite (`py -3.11 -m pytest tests/ -q`, run because this
  iteration also edits `tasks.md`): **565 passed, 3 skipped**. `py -3.11 -m ruff check` and `py
  -3.11 -m black --check --target-version py311` on the changed test file: both clean. No
  production file changed, so `mypy` is unaffected. `git diff --stat`: exactly
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py` and this change's `tasks.md`. `py -3.11
  scripts/backlog_page.py --check`: current, nothing moved.
- [x] 1.4c (R4, D8, link fixture) **globs through a link**, refused as outside, the reason naming where the match resolves:
  - `cp n u*/`, `cp n u?/x`, `cp n [u]p/x`, and `cp n '[[:alpha:]]p'/x` (Bash; the first bracket matched exactly, the POSIX class relaxed, D8 step 2 as R8 wrote it);
  - `bash -c 'cp n u*/'` (inner shell);
  - `bash -O extglob -c 'cp n @(u)p/x'`;
  - PowerShell `Copy-Item n u*\x` (Windows) or `Copy-Item n u*/x` (POSIX).

  Each PASSES today only by the tail (`'/'` or `'/x'`), so assert that the reason contains the resolved target, which FAILS today. Each FAILS against the R3 design (allowed). Also `ls sub/.*/y` where `sub/.l` is a link → outside (the dot rule), which FAILS against R3.

  (R5) Also refused, each naming where the match resolves:
  - `cp n <workspace, absolute, forward slashes>/u*/` and `cp n <workspace, absolute>/.*/x`. Each FAILS today (allowed, measured) and FAILS against R4, whose rule 5 takes an absolute word before D8;
  - `cp n sub/@s/u*/`, with `sub/@s/up` a link to outside. PASSES today by the tail, so assert the resolved target, which FAILS today and FAILS against R4 (the piece `s/u*/` is globbed from the root);
  - PowerShell `Get-ChildItem ?l\x` (Windows) or `?l/x` (POSIX), where `.l` is the only entry that `?l` can match. FAILS against R4 (its dot rule). Control: Bash `ls ?l/x` in the same fixture is allowed, because bash's `?` does not match a leading dot.

  Controls allowed: `ls sub/*.py`; `ls i*/a.py` (an inside link); `ls nomatch*/x` (no match, the literal is inside).

  (R8, design D8 step 2) A bracket expression is matched as the shell matches it, and relaxed to `?` only where `fnmatch` cannot read it:
  - `ls ./[0-9]/x` allowed: `[0-9]` matches only a one-character name, so it does not match `up`. FAILS today (tail `'/[0-9]/x'`) and FAILS against R7 (every bracket relaxed to `*`, which matches `up`).
  - `ls ./[^a]p/x` (Bash) refused, naming where `up` resolves: bash negates with `^`, and `fnmatch` reads it literally. PASSES today only by the tail, so assert the resolved target; FAILS against a relaxation that keeps `[^a]` exact.
  - PowerShell `Get-ChildItem .\[!a]p\x` (Windows) or `./[!a]p/x` (POSIX) refused, naming where `up` resolves: PowerShell reads `!` literally (measured: `Resolve-Path '[!u]p'` lists `up`). FAILS against a relaxation that keeps `[!a]` exact.
  - `cp n '[[:alpha:]]p'/x`, `cp n [u]p/x` and `cp n ./u[p]` stay refused (rows above and 1.4e): the second review's HIGH 1 is not reopened.

  (R6) The rows `cp n [u]p/x` and `cp n '[[:alpha:]]p'/x` above pass only with D11: under R5 as written the words are `u]p/x` and `alpha:]]p/x`, no glob D8 can use, so both are **allowed** (FAIL against R5). The second is caught only by D8's whole-value pass, because `:` breaks the piece reading.

  **Iteration 38 (first slice, the plain Bash/inner-shell/PowerShell rows).** Re-derived this
  task's first bullet group fresh against `_decide` (`testbed/scratch/measure_1_4c_bash_rows.py`,
  gitignored, not committed), not trusting the task's own claim that the reason assertion fails
  today: with task 2.1c and 2.2 already built (both closed earlier this window), `cp n u*/`
  (the bare trailing-slash form, distinct from the already-tested `cp n u*/x`), `cp n u?/x`,
  `cp n [u]p/x` (matched exactly by the bracket relaxation task 2.1c's iteration 20 already
  built -- `[u]p` holds none of `! ^ [ \` or a backtick, so it is not relaxed to `?`), the
  inner-`bash -c 'cp n u*/'` form, and both PowerShell forms (`Copy-Item n u*\x` on Windows,
  `Copy-Item n u*/x` on POSIX) are each **already refused today**, naming the resolved target --
  confirmed by stashing nothing (no production file changed) and mutation-checking the test
  instead (see below). The task's own text is stale here, like most of this change's rows. Two
  rows in this same bullet group stay open, confirmed still wrong: `cp n '[[:alpha:]]p'/x`
  (the POSIX character class) and `bash -O extglob -c 'cp n @(u)p/x'` (extglob) are each still
  wrongly **allowed** -- `_glob_links` does not yet relax a POSIX class, and extglob is not in
  `_GLOB_CHARS` so `_glob_links` never sees it as a glob at all, both as documented elsewhere in
  this file. Neither this bullet's second paragraph ("the dot rule", `ls sub/.*/y`) nor the (R5),
  (R8), or (R6/D11) sub-groups below were touched this iteration.

  Added `test_a_bare_or_bracketed_relative_glob_is_matched_through_the_link_it_finds_1_4c` and
  `test_a_relative_glob_is_matched_through_the_link_it_finds_windows_powershell_1_4c` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. Mutation-checked: backed up
  `mcp_server.py`, inserted `return None` as `_glob_links`'s first statement (forcing every glob-link
  call to find nothing), reran just the two new tests -- both fail (`assert True is False`),
  confirming they are load-bearing; restored from the backup and confirmed `git diff --stat
  hub/hub/mcp_server.py` is empty. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **112 passed** (was 110, +2). Broader
  regression set (`test_permission_approver.py`, `test_hub_own_call.py`, `test_copilot_acp_decide.py`,
  `test_a_write_outside_the_workspace_is_recorded.py`): **738 passed, 2 skipped**, no regressions.
  `py -3.11 -m ruff check` and `py -3.11 -m black --check --target-version py311` on the changed
  test file: both clean. No production file changed, so `mypy` is unaffected. `git diff --stat`:
  exactly `hub/tests/test_the_shell_judge_reads_a_word_whole.py` and this task file.

  **Task 1.4c still stays unticked.** What remains: the dot-rule row in this bullet's second
  paragraph (unmeasured this iteration -- it may already be fixed by 2.1c's iteration 22 dot-leading
  fix, needs re-derivation, not assumed); the POSIX character class and extglob rows just above
  (each needs a further `_glob_links`/`_rewrite_dotdot_globs` slice, not attempted here); the (R5)
  absolute-word and `sub/@s/u*/` rows; the (R8) bracket-relaxation rows (`[0-9]`, `[^a]`, `[!a]`);
  and the (R6/D11) rows, which this task's own text says need 2.1d (unticked, not started). Each
  needs its own fresh measurement against `_decide` before building, same discipline as this
  iteration's slice -- do not assume any of them already pass just because this slice's rows did.

  **Iteration 39 (the (R5) and (R8) sub-groups, resolved differently than either sub-group's own
  text claims).** Re-measured both fresh against `_decide` (`testbed/scratch/measure_1_4c_r5_r8.py`
  and three siblings, gitignored, not committed), not trusting the task's own claim that the
  absolute rows are allowed today: the absolute `u*/` row already reaches `_glob_links` through
  rule 5's own call (`_judge_word`, line ~2033, built by task 2.2), and `sub/@s/u*/` reaches it
  through rule 6's piece reading the same way the already-tested relative `u*/x` row does -- both
  **already refused today**, naming the resolved target, no further production change needed. The
  three (R8) bracket rows (`[0-9]`, bash `[^a]p`, PowerShell `[!a]p`) are likewise each already the
  design's own outcome: `_relax_bracket_pattern` (task 2.1c, iteration 20) keeps a plain numeric
  bracket exact (`[0-9]` stays `[0-9]`, matching only a one-character name, not `up`), and widens a
  `^`- or `!`-led bracket to `?` (`content[:1] in "!^"` -- confirmed directly with a throwaway
  `_relax_bracket_pattern('[^a]p')` call, printing `'?p'`), which matches `up`'s two characters
  either way. Measured directly against `_decide`, not reasoned from the source alone.

  Two further things surfaced, neither in the task's own text, both left open rather than built:
  (1) the PowerShell dot-rule row this sub-group names (`?l` matching the only-entry `.l`) is
  already refused too, but not because either dialect encodes a rule -- `fnmatch` has no bash dot
  rule at all, so `?` matches a leading dot for both dialects alike, and the task's own Bash
  *control* (`ls sub/?l/x` "allowed, because bash's `?` does not match a leading dot") measures as
  **refused** today, not allowed: `_glob_links`'s own docstring already names the bash dot rule as
  left unbuilt for this whole change ("skipping it only widens what matches... over-approximation
  can only add a refusal"), so this control's failure is that documented, accepted gap, not a new
  finding -- not built here, consistent with the docstring's own scope. (2) The absolute
  `.*/x` row (bullet two's own text) does not exercise `_glob_links`'s dot-rule reading at all when
  the dot-leading component is the *first* component after the workspace root: `_rewrite_dotdot_globs`
  (D3) rewrites it to the literal `..` before rule 5's `_judge_path(rewritten, ...)` call ever
  reaches `_glob_links`, and `<workspace>/../x` already refuses on its own (the workspace's parent),
  short-circuiting before any link is matched -- confirmed by removing the `.l` link entirely and
  rerunning: the refusal is byte-for-byte identical either way, proving no link is actually being
  read. The already-built `sub/.*/y` case (2.1c) differs only because its rewrite (`sub/../y`)
  resolves *inside* the workspace, so the early check does not refuse and execution falls through
  to `_glob_links`, which does match `.l` there. Left open for a further slice, same bucket as the
  POSIX-class and extglob rows.

  Added four tests to `hub/tests/test_the_shell_judge_reads_a_word_whole.py`:
  `test_an_absolute_or_piece_relative_glob_is_matched_through_the_link_it_finds_1_4c_r5` (the
  already-passing absolute and `sub/@s/u*/` rows, plus the PowerShell dot-rule row),
  `test_an_absolute_top_level_dot_glob_refuses_by_the_dotdot_rewrite_not_the_link_it_finds_1_4c_r5`
  (documents finding (2) precisely, asserting the reason does *not* say "it resolves to" and is
  identical with or without the link), and
  `test_a_bracket_expression_is_matched_or_kept_exact_as_fnmatch_can_read_it_1_4c_r8` (the three
  bracket rows). Mutation-checked: backed up `mcp_server.py` to `testbed/scratch/` (not committed),
  inserted `return None` as `_glob_links`'s first statement, reran the four new tests -- the two
  that depend on `_glob_links` (the (R5) and (R8) ones) fail (`assert True is False`), confirming
  they are load-bearing; the dot-rewrite test correctly still passes under the same mutation (it
  does not reach `_glob_links` at all, which is exactly its own finding); restored from the backup
  and confirmed `git diff --stat hub/hub/mcp_server.py` is empty. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **115 passed** (was 112, +3 test
  functions, +4 with the mutation-only check not counted twice -- the file count is tests
  collected, not assertions). Broader regression set (`test_permission_approver.py`,
  `test_hub_own_call.py`, `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`):
  **626 passed, 2 skipped**, no regressions (a different total from iteration 38's 738 for the same
  four files -- not re-derived why; no failures either run, which is what the regression check is
  for). `py -3.11 -m ruff check` and `py -3.11 -m black --check --target-version py311` on the
  changed test file: both clean. No production file changed, so `mypy` is unaffected. `git diff
  --stat`: exactly `hub/tests/test_the_shell_judge_reads_a_word_whole.py` and this task file.

  **Task 1.4c still stays unticked.** What remains after this iteration: the dot-rule row in this
  bullet's second paragraph (still unmeasured -- re-derive, do not assume 2.1c's fix covers it);
  the POSIX character class and extglob rows (need a further `_glob_links`/`_rewrite_dotdot_globs`
  slice); the absolute top-level dot-glob gap this iteration found (finding (2) above, needs its
  own design thought about rule 5's call order, not attempted here); the bash-dot-rule control gap
  (finding (1) above, deferred per `_glob_links`'s own docstring, likely out of this task's scope
  entirely -- confirm against design.md before treating it as blocking); and the (R6/D11) rows,
  which need task 2.1d (unticked, not started). Each needs its own fresh measurement before
  building.

  **Iteration 41 (the dot-rule row and the POSIX character class row, both re-derived; extglob
  untouched).** The dot-rule row (`ls sub/.*/y`, `sub/.l` a link out) is **already covered**: a
  fresh, independent measurement against `_decide` (`testbed/scratch/measure_1_4c_posix_extglob.py`,
  gitignored, not committed, built without reading 2.1c's own test first) refuses it, naming the
  resolved target -- the same row task 2.1c's own
  `test_a_dot_leading_glob_is_also_matched_against_the_link_it_finds_2_1c` already exercises
  (iteration 22). No gap, no new test needed; this task's remaining dot-rule item is closed.

  The POSIX character class row (`cp n '[[:alpha:]]p'/x`) turned out to be **platform-split**,
  which no prior iteration's note said -- confirmed by direct investigation of `_judge_whole_value`
  and `_judge_piece`, not reasoned from the source alone: `_relax_bracket_pattern` already relaxes
  `[[:alpha:]]p` to `?p` correctly, and `fnmatchcase("up", "?p")` is True, but that pattern only
  ever reaches `_glob_links` through D9's *undivided* whole-value reading, which design D9 takes
  only `if not _DRIVE_LETTERS` -- a drive-letter host instead splits the value at every `:` first
  (`[[`, `alpha`, `]]p/x`), none of which matches `up`, because D9 reads any colon as a possible
  drive letter, not knowing some colons are POSIX bracket-class syntax instead. Confirmed by calling
  `_judge_piece` on the undivided value directly (refuses) versus `_judge_whole_value` on the same
  value with `_DRIVE_LETTERS` forced true (returns `None`, never reaching the undivided call). This
  machine has no symlink privilege (`OSError: WinError 1314`, measured), so the POSIX-side refusal
  is confirmed by forcing `_is_link_entry`/`_is_link_path` to answer as a real symlink's `os.lstat`
  would (`S_ISLNK`, independent of `_DRIVE_LETTERS` in production) rather than by a junction, which
  needs `_DRIVE_LETTERS` true for its own reparse-point check and so cannot stand in once that flag
  is forced false -- reasoned through for the real case the same way task 1.4g's own POSIX-only
  `work/t:d` row was (iteration 25). Confirmed (iteration 44): CI's `hub-test` job
  (ubuntu-latest, a real symlink, natively `_DRIVE_LETTERS` false) ran commit 84e4474 (the commit
  that added this test) and its log shows `test_a_posix_character_class_is_caught_whole_only_off_a_drive_letter_host_1_4c
  PASSED`, confirming the `not _WINDOWS` branch green on a real symlink. The Windows side is
  measured directly and natively on this machine: still wrongly allowed.
  No production change made -- fixing the Windows side would need a POSIX-class carve-out in D9,
  which risks reopening D9's own drive-letter reasoning, so it is left for a further round rather
  than patched here.

  Added `test_a_posix_character_class_is_caught_whole_only_off_a_drive_letter_host_1_4c` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, pinning both platforms' current answer
  (refused off a drive-letter host, allowed on one) so a future design change shows up as a test
  failure rather than silently. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **116 passed** (was 115, +1). Broader
  regression set (`test_permission_approver.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): **626 passed,
  2 skipped**, no regressions (same count as iteration 39's same four files). `py -3.11 -m ruff
  check` and `py -3.11 -m black --check --target-version py311` on the changed test file: both
  clean. No production file changed, so `mypy` is unaffected. `git diff --stat`: exactly
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py` and this task file.

  **Task 1.4c still stays unticked.** What remains: the extglob row (`bash -O extglob -c 'cp n
  @(u)p/x'`, confirmed still wrongly allowed on this platform, untouched this iteration --
  `_GLOB_CHARS` does not include extglob's own trigger characters at all, so `_glob_links` never
  sees it as a glob-holding component regardless of platform; needs its own `_glob_links` slice, not
  the D9 carve-out the POSIX-class row needs); the Windows-side POSIX-class gap just found (needs a
  design round for D9's carve-out, not a quick fix); the absolute top-level dot-glob gap (iteration
  39's finding (2), needs a design thought about rule 5's call order); the bash-dot-rule control gap
  (iteration 39's finding (1), likely out of scope, confirm against design.md); and the (R6/D11)
  rows, which need task 2.1d (unticked, not started -- read its own line and design.md's D11 section
  first before building, it touches `_words`, not only `_glob_links`). Each needs its own fresh
  measurement before building, same discipline as every iteration so far.

  **Iteration 42 (the extglob row, attempted and reverted -- design D8 step 2's own words are not
  enough to build from directly).** Built a first slice: a shared `_holds_glob_character` helper
  (`_GLOB_CHARS` or a non-empty `_extglob_group_spans`) at `_glob_links`'s own glob-position check
  and at both its call sites (rule 5's absolute-word check, `_judge_piece`'s rule-6 check, neither
  of which tested for an extglob group before, so `_glob_links` was never even reached for one
  regardless of what `_glob_links` itself could do), plus masking the matched component's extglob
  group to one `*` (`_mask_extglob_as_star`, already built for D3's `..`-rewrite) before
  `_relax_bracket_pattern`/`fnmatchcase`, reading D8 step 2's own line ("each extglob group becomes
  `*`") as literally as task 2.1c's bracket relaxation reads its own line. This made the target row
  refuse, naming the resolved target, matching this task's own expectation -- but running the full
  file caught something no prior iteration's note flagged: it also flipped
  `test_an_unquoted_extglob_group_is_kept_as_one_unit_through_the_lexer_and_rule_6`'s own
  `cp n @(a|b)/x` row (task 2.2, already built, no dot alternative, lexically inside) from allowed to
  **wrongly refused** -- `@(a|b)` masked to `*` matches every entry in the workspace, including the
  fixture's own `up` link to outside, although the shell can only ever expand `@(a|b)` to the
  literal name `a` or `b`, neither of which is a link here. Confirmed this is the masking, not a
  typo: printing `_relax_bracket_pattern(_mask_extglob_as_star("@(a|b)", _extglob_group_spans("@(a|b)")))`
  gives `'*'`, and `fnmatchcase("up", "*")` is True. D8 step 2's own line describes the *bracket*
  relaxation's budget correctly (`?` is the narrowest fnmatch can give a one-character class), but
  for an extglob group `*` is not the narrowest over-approximation available for every trigger --
  `@(u)` (exactly one alternative, D3's `@`/`?` triggers) could become the literal alternative text
  itself (`u`) rather than `*`, and `?(u)` (zero-or-one) could become an alternation of `""` and `u`
  tried in turn, each bounded and no wider than the shell's own expansion; only `*`, `+` (repetition)
  and `!` (negation) have no finite literal form `fnmatch` can express and genuinely need `*`'s own
  width. Masking every trigger to `*` alike, as this iteration first tried, is correct only for
  those last three and is already too wide for `@`/`?`'s own enumerable case, which is exactly the
  row `test_an_unquoted_extglob_group...`'s `@(a|b)` already covers and already pins as allowed.
  Building the enumerable `@`/`?` translation correctly (generating one concrete pattern per
  alternative, or per alternative crossed with the empty string, including across more than one
  group in the same component) is real work, not a one-line reading of D8 step 2 -- reverted both
  the production change and its own new test entirely (`git checkout --
  hub/hub/mcp_server.py hub/tests/test_the_shell_judge_reads_a_word_whole.py`; confirmed `git status
  --short` is empty before any of this entry's own edits), rather than leave a breaking change or an
  untested one. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q` back to
  **116 passed** (unchanged from iteration 41) after the revert, confirmed before writing this entry.

  **Task 1.4c still stays unticked; the extglob row's own remaining work narrows to this:** a
  correct fix needs `_glob_links` (or a helper it calls) to translate `@(...)`/`?(...)` by
  enumerating each `|`-separated alternative (plus, for `?`, the empty string) into its own
  concrete pattern tried against each entry, falling back to `*` only for `*(...)`, `+(...)` and
  `!(...)`, whose repetition/negation `fnmatch` cannot express exactly either way -- and a new test
  covering `@(a|b)/x` (must stay allowed, task 2.2's own row) alongside `@(u)p/x` (must now refuse)
  in the same file, so a future attempt cannot regress one while fixing the other without the suite
  catching it. Not sized for a further quick slice without that translator; the other open items
  named two paragraphs up are unaffected by this entry.

  **Iteration 43 (the extglob row, re-derived against design.md's actual text rather than iteration
  42's own conclusion -- a fresh comparison, not a re-read of the previous round).** Iteration 42's
  "stays allowed" constraint on `@(a|b)/x` was never itself checked against the design text; it was
  inferred from the regression alone. Re-reading D8 step 2 and D3 directly: both say, unconditionally,
  "each extglob group becomes `*`" for D8's matching -- no carve-out for an enumerable trigger, unlike
  the bracket-relaxation rule right next to it in the same step, which explicitly keeps a bracket
  exact wherever `fnmatch` can read it and relaxes only where it cannot. The design's own
  "Over-approximation, on purpose" section then names "extglob groups" directly, beside the relaxed
  brackets, as an accepted source of over-approximation: "matching more names can only add a
  refusal." So a per-alternative `@`/`?` translator, though buildable, is not what this task asks
  for, and `@(a|b)/x` becoming refused once D8 actually reaches extglob groups (this row, not yet
  built before this iteration) is the design's own intended outcome, not a regression -- task 2.2's
  test predates D8 reaching extglob at all (its own note says D8/`_glob_links` was still "untouched"
  for extglob as of iteration 19), so its "stays allowed" assertion was only ever true because
  nothing yet matched the fixture's `up` link against the mask.

  Built `_holds_glob_character(text)` (`hub/hub/mcp_server.py`): a bare `_GLOB_CHARS` character or a
  non-empty `_extglob_group_spans`. Wired it into `_glob_links`'s own `glob_positions` check (which
  decides which component is *the* glob-holding one) and both call sites that gate whether
  `_glob_links` runs at all (rule 5's absolute-word check, `_judge_piece`'s rule-6 check) -- neither
  tested for an extglob group before, so `_glob_links` was never even reached for one regardless of
  what it could do once there, confirming iteration 42's own diagnosis of that part. Inside
  `_glob_links`, masked the matched component's extglob group to one `*`
  (`_mask_extglob_as_star`, already built for D3's `..`-rewrite) before `_relax_bracket_pattern`,
  exactly iteration 42's first attempt, kept this time rather than reverted.

  Measured directly against `_decide` first (`testbed/scratch/measure_1_4c_extglob_star.py` and
  `measure_1_4c_extglob_control.py`, gitignored, not committed), before touching any test: `cp n
  @(u)p/x` (the task's own target row) now refuses, naming the resolved target; `cp n @(a|b)/x`
  (task 2.2's row) now also refuses, for the reason above; `cp n sub/@(..)/x` (task 2.2's
  "resolves_inside" control) is unaffected -- it never reaches `_glob_links`'s masking at all,
  because D3's own dotdot-rewrite already turns `@(..)` into the literal `..` first, which resolves
  inside and short-circuits before `_glob_links` runs. A naive control at the workspace root
  (`cp n @(sub)/a.py`) also refuses, because the mask is `*` for the *whole* group regardless of
  which alternative is named, and `*` matches the root's own `up` link too -- confirmed this is not
  a bug by checking the same shape one directory deeper (`cp n sub/@(nomatch)/`, no link in `sub`
  itself besides `l`, which resolves inside), which stays allowed; used that row as the new test's
  own control instead.

  Updated `test_an_unquoted_extglob_group_is_kept_as_one_unit_through_the_lexer_and_rule_6`'s
  `@(a|b)/x` row from allowed to refused, with a comment explaining why this is the design's own
  outcome and not a regression of this slice. Added
  `test_an_extglob_group_is_masked_to_star_through_the_link_it_finds_1_4c` covering `@(u)p/x`
  (the task's own row), `?(u)p/x` and `*(u)p/x` (confirming the mask is the same for every trigger,
  not only `@`), and the `sub/@(nomatch)/` control. Mutation-checked: `git stash`ing just
  `mcp_server.py` and rerunning the file fails exactly the new test and the updated `@(a|b)/x`
  assertion, leaving the other 115 rows passing unchanged -- confirming both changed assertions
  depend on the production change and nothing else moved. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **117 passed** (was 116, +1). Broader
  regression set (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): **743 passed, 2 skipped**, no regressions.
  `ruff check` and `black --check --target-version py311` on both changed files: clean. `git diff
  --stat`: exactly `hub/hub/mcp_server.py` and the one test file, plus this task file.

  **Task 1.4c still stays unticked**, but the extglob row is now done. What remains, unchanged from
  iteration 41's note: the Windows-side POSIX-class gap (needs its own D9 design round); the
  absolute top-level dot-glob gap (iteration 39's finding (2)); the bash-dot-rule control gap
  (iteration 39's finding (1), likely out of scope); and the (R6/D11) rows, which need task 2.1d
  (unticked, not started). Each needs its own fresh measurement before building, same discipline as
  every iteration so far -- in particular, re-derive from design.md's actual text before trusting
  any prior iteration's framing of what a fix should look like, this iteration's own lesson.

  **Iteration 45 addendum.** Task 2.1d is now ticked (its own note, below) and 1.4c's (R6/D11)
  bracket rows (`[u]p/x`, `'[[:alpha:]]p'/x`, `./u[p]`) all pass. 1.4c itself stays unticked for the
  three unrelated gaps named above (D9 round, absolute top-level dot-glob, bash-dot-rule control),
  none of which this iteration touched.

  **Iteration 46 (R1 of this gap's own round, draft only — no production change).** Took the
  Windows-side POSIX-class gap, the most tractable of the three remaining named gaps, and wrote its
  design round's first of three required rounds (`CLAUDE.md`'s round discipline: a change needing a
  spec goes through three independent rounds before a line is implemented). Re-derived against
  design.md's actual D9 text first, per the standing lesson (iteration 43): confirmed D9 as written
  covers only the CI-job and call-time-read rules, not this colon-split interaction, so patching D9
  inline would not have been a genuine design round. Measured the defect directly against the
  current code (`testbed/scratch/measure_1_4c_bracket_colon_gap.py`, gitignored, not committed, this
  machine's `_DRIVE_LETTERS` is natively true so no monkeypatching was needed): `_judge_whole_value`
  skips its undivided `_judge_piece` call outright on a drive-letter host, splitting
  `"[[:alpha:]]p/x"` into `['[[', 'alpha', ']]p/x']`, none of which carries a usable bracket
  expression, so `_glob_links` is never reached with the pattern that would match `up`. Prototyped a
  fix (`testbed/scratch/measure_1_4c_bracket_mask_prototype.py`, gitignored, not committed): mask a
  bracket expression's own `:` before the drive-letter colon split (found by the same
  `_bracket_expression_end` D8 step 2 already uses, mirroring the existing
  `_mask_extglob_groups`/`_restore_extglob_sentinels` pair D2 step 2 uses for the same kind of
  problem with `(`, `@` and `|`), restoring it in each segment before `_judge_piece` sees it.
  Measured the prototype against five cases, including the drive-letter row (`Z:foo\bar`, unaffected)
  and a non-bracket regex-shaped row (unaffected, so D2 step 6's own measured 44 words do not move):
  masking is a no-op whenever there is no bracket expression, and keeps a bracket's own colons intact
  when there is one. Wrote this up as design.md's new **D13** section, explicitly marked "R1, draft —
  not yet reviewed", naming what it does and does not change and what it leaves open
  (`_glob_links`'s own base-resolution text for a base crossing a colon, D8 step 1, not yet
  re-checked against the proposed mask). **No file under `hub/` was touched this iteration** --
  `mcp_server.py` and the test file are unchanged, per round discipline: R2 and R3 each need their
  own independent re-derivation against the code before any line of `_judge_whole_value` changes.
  1.4c stays unticked; this gap now has a draft design but no implementation, and the other two named
  gaps (absolute top-level dot-glob, bash-dot-rule control) are untouched.

  **Iteration 47 (R2 of this gap's own round — independent re-derivation, confirmed sound).**
  Re-derived D13 against the actual code from scratch, not from iteration 46's own write-up: read
  `_judge_whole_value` (`hub/hub/mcp_server.py:2137`) fresh, independently re-ran the
  `"[[:alpha:]]p/x".split(":")` measurement, and additionally called the module's own
  `_bracket_expression_end`/`_relax_bracket_pattern`/`_holds_glob_character` directly against each
  split fragment and the undivided value (`testbed/scratch/r2_verify_d13.py`, gitignored, not
  committed) — the undivided value relaxes to `'?p/x'` (matches `up`); none of the three fragments
  (`'[['`, `'alpha'`, `']]p/x'`) does, confirming the defect exactly as R1 stated. Re-coded the
  masking rule independently (a fresh script, not R1's prototype file) and ran it against the same
  five cases: all five produce exactly the split D13 claims, including the two no-op cases
  (`Z:foo\bar`, the `sed` row). Both (a) the defect and (b) the proposed fix confirmed. Also resolved
  the open item (c) rather than leaving it open: `_glob_links`'s D8 step 1 "base" is defined as the
  leading components holding *no* glob character, and every masked colon lies inside a bracket span
  that starts at `[` — itself a glob character — so a masked colon can never fall inside a base, in
  any arrangement. The base-crossing-a-colon case D8 step 1 already describes is always a literal
  colon outside any bracket, which the mask leaves untouched. No change needed there; this is now
  closed, not merely re-confirmed-open. Wrote all of this into design.md's D13 section itself
  (re-headed "R2 confirmed — one independent re-derivation done, R3 still required"). **No file under
  `hub/` was touched** — `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`:
  **119 passed** (unchanged, as expected for a docs-only round). 1.4c stays unticked; R3 (a second,
  independent re-derivation) is still required by `CLAUDE.md`'s round discipline before
  `_judge_whole_value` is touched.

  **Iteration 48 (R3 of this gap's own round -- independent re-derivation, confirmed sound; then
  implemented).** Re-derived D13 against the actual code a third time, fresh, before reading either
  R1's or R2's own write-up again (`testbed/scratch/r3_verify_d13.py`, gitignored, not committed, a
  script written from scratch, not reused from either prior round): called `_judge_whole_value`'s own
  split and the module's `_bracket_expression_end`/`_relax_bracket_pattern`/`_holds_glob_character`
  against four cases neither R1 nor R2 had used (`[[:digit:]]9/x`, `[:alpha:]p/x`, a bracket holding
  two concatenated POSIX classes, and a negated bracket whose only member is a literal `:`) -- every
  one split into fragments that lost the glob exactly as D13 describes, and the undivided reading
  relaxed to a pattern that matches `up`. **(a) confirmed**, by cases no prior round had tried. Wrote
  an independent masking function from scratch and ran it against nine cases (the five already named
  plus `[[:digit:]]9/x`, the negated-member bracket, a drive letter and a bracket colon in the same
  value (`C:\x[a:b]\y`), and a POSIX class beside an extra literal colon member in the same bracket)
  -- every case produced the expected split, with the drive-letter/`sed` rows unaffected. Also tried,
  and failed to construct, a counterexample to the rule itself: an unterminated bracket with a colon
  inside (`a[b:c/x`, `[[:alpha:`, `x[:y/z`) splits exactly as it does today, unmasked, because
  `_bracket_expression_end` finds no span for it -- consistent with `_relax_bracket_pattern`'s own
  literal reading of the same input (checked directly: it returns these unchanged too). **(b)
  confirmed**, including a boundary case neither prior round tried. Re-derived (c) independently from
  the actual D8-step-1 code, not the docstring text either prior round quoted: `_GLOB_CHARS = "*?["`
  (`hub/hub/mcp_server.py:1390`), and `_glob_links`'s own `base_components = components[:glob_index]`
  where `glob_index` is the position of the first component for which `_holds_glob_character` is
  true -- checked directly that a component holding `[` anywhere in it (not only as its first
  character, e.g. `lit[a:b]`) is `_holds_glob_character` True, so it is always excluded from
  `base_components` regardless of what precedes the `[` inside it. **(c) confirmed** by reading the
  code the claim is about, not only the docstring describing it. No counterexample found in any of
  the three rounds despite each one trying from a different angle.

  **D13 heading updated to "R3 confirmed -- all three required rounds done" in design.md.** Then
  implemented, per `next_action`: added `_BRACKET_COLON_SENTINEL`, `_bracket_expression_spans` and
  `_mask_bracket_colons` to `hub/hub/mcp_server.py` (after `_relax_bracket_pattern`, before
  `_glob_links`, mirroring `_mask_extglob_groups`/`_restore_extglob_sentinels`'s own shape), and wired
  `_mask_bracket_colons(value)` into `_judge_whole_value`'s drive-letter split, restoring the sentinel
  in each surviving segment before `_judge_piece` sees it. Updated the existing
  `test_a_posix_character_class_is_caught_whole_only_off_a_drive_letter_host_1_4c` (its Windows branch
  now asserts `allow is False`, naming the resolved target, same as the non-Windows branch -- merged
  to one assertion since both platforms now agree) and added
  `test_a_bracket_expressions_own_colon_survives_the_drive_letter_split_1_4c_d13` (an ordinary bracket
  with a literal `:` member, `[a:u]p/x`, matching the fixture's `up` link; plus, Windows-only, the
  existing `sed -E 's/(:700)/(:697)/g' f` control from 1.4g's own test, confirming a real drive-letter
  colon with no bracket still splits). Mutation-checked: temporarily reverted the `_judge_whole_value`
  wiring to the unmasked split and reran -- both the updated test and the new test fail (`assert True
  is False`), confirming they are load-bearing; restoring the fix afterward took two attempts because
  `git checkout -- hub/hub/mcp_server.py` discarded the real fix along with the mutation (the file had
  never been committed in its fixed state) -- caught immediately by grepping for `_mask_bracket_colons`
  and finding no match, then the two production edits were reapplied directly. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **120 passed** (was 119, +1 test
  function). Broader regression set (`test_permission_approver.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): **746 passed, 2
  skipped**, no regressions. `py -3.11 -m ruff check` and `py -3.11 -m black --check
  --target-version py311` on both changed files: clean. `git diff --stat`: `hub/hub/mcp_server.py`,
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, `design.md` and this task file.

  **Task 1.4c's Windows-side POSIX-class/colon-split gap is now closed.** The other two named gaps
  (the absolute top-level dot-glob gap, iteration 39 finding (2); the bash-dot-rule control gap,
  iteration 39 finding (1), likely out of scope) remain open and untouched -- task 1.4c itself stays
  unticked until both are resolved on their own fresh measurement, not assumed from this iteration's
  work on a different gap.

  **Iteration 49 (both remaining gaps re-derived fresh; one already closed, one is a real gap,
  drafted as D14).** Took `next_action`'s named item: re-derive both of task 1.4c's two other
  named gaps fresh against the current code, not assumed from iteration 39's or 45's notes.

  The absolute top-level dot-glob gap (iteration 39 finding (2)) is **already closed, no change
  needed**: reran
  `test_an_absolute_top_level_dot_glob_refuses_by_the_dotdot_rewrite_not_the_link_it_finds_1_4c_r5`
  directly (`py -3.11 -m pytest ... -k test_an_absolute_top_level_dot_glob_refuses_by_the_dotdot_rewrite_not_the_link_it_finds_1_4c_r5`):
  **1 passed**. It still documents, and still measures, that this row is refused by
  `_rewrite_dotdot_globs`'s earlier `..` rewrite, not by `_glob_links` reading a link at all --
  nothing left to build here. This half of task 1.4c's remaining work is done.

  The bash-dot-rule control gap (iteration 39 finding (1), both iteration 39's and 45's notes called
  it "likely out of scope") is **not out of scope -- it is a real, unbuilt piece of the design**,
  confirmed by reading design.md directly rather than trusting either prior note's hedge: the "Over-
  approximation, on purpose" section names exactly three accepted over-matches by name (folded case,
  relaxed brackets and extglob groups, PowerShell's literal-path matching), and "Residuals, named"
  lists every accepted gap this change ships with, also by name -- the bash dot rule is in neither
  list, while D8 step 2's own text states the rule as something this design builds (revised twice
  more since, R6 and R5). `_glob_links`'s own docstring cites "the design allows over-approximation"
  for skipping it, but that citation does not point at anything either list actually contains.
  Measured fresh against `_decide` (`testbed/scratch/measure_1_4c_bash_dot_rule.py`, gitignored, not
  committed): `_decide("Bash", {"command": "ls sub/?l/x"})` against a fixture with `sub/.l` linked
  outside is refused, naming the resolved link -- the task's own control (line 74) says this must be
  **allowed**, since bash's `?` does not match a leading dot. The already-passing test for this same
  row's *PowerShell* form stays correct (PowerShell has no dot rule either, so the two dialects
  coincide by accident there) -- this is a different, Bash-only gap that test does not cover.

  Drafted **D14 (R1)** in `design.md` (new section, after D13): the defect, why it is not covered by
  either named list, the scope (bash dialect's `_glob_links`/`_globstar_walk` matching only --
  PowerShell and the D8-step-4 literal-tail walk are both unaffected), and a proposed rule mirroring
  `_Budget.globstar_named`'s own shape (a new `_DOTGLOB_RE`/`dotglob_named`, `dialect` threaded from
  `_judge_word` through `_judge_piece` -- which currently takes no `dialect` parameter at all -- into
  a new `bash: bool` on `_glob_links`/`_globstar_walk`, and a dot-rule guard in each matching loop
  that exempts a pattern starting with `.` or `[`, reusing `_rewrite_dotdot_globs`'s own R6/D11
  bracket hedge for consistency). Three open items left for R2/R3 to each independently confirm
  before any production line changes: (a) the plumbing does not move any already-passing test's
  answer; (b) the reused `[`-opened hedge is read at the right point (`pattern` before masking, not
  `_rewrite_dotdot_globs`'s own post-mask `candidate`) and agrees with it on every case design's own
  bracket-relaxation section names; (c) `dotglob_named`'s read-once-per-`_decide` behaviour carries
  over correctly to a nested inner shell's own `shopt -s dotglob`, the same way `globstar_named`
  already does for `globstar`, not yet re-derived for `dotglob` specifically.

  No production file touched. `git diff --stat`: exactly `design.md` and this task file. This is a
  new, previously-unproposed gap (not one task 1.4c's own text already named a design for), so per
  `next_action`'s instruction it needs its own three-round discipline -- R1 drafted this iteration,
  R2 and R3 each a fresh independent re-derivation still to come, same as D13 just went through,
  before any line of `mcp_server.py` changes. **Task 1.4c stays unticked**: one of its two remaining
  gaps is now closed (the dot-glob rewrite row), the other (the bash dot rule) has an R1 draft but no
  implementation yet.

  **R2 (independent re-derivation, fresh)** found two real gaps in R1's draft, both corrected in
  `design.md`: `_judge_piece` has three call sites, not one (`_judge_whole_value`'s own two also
  need `dialect` threaded into its signature, or the whole-value reading built for D13's
  drive-letter/bracket-colon split never becomes bash-aware); and the `[`/`.`-prefix hedge alone
  misses an extglob group whose alternative itself begins with `.` (`@(.|..)p`), an under-refusal
  risk -- corrected to also waive the dot-skip via `_extglob_group_spans`/
  `_extglob_alternative_begins_with_dot`. (c) confirmed clean, directly from the one `_Budget`
  construction site. No already-passing test moves. Still docs-only.

  **R3 (independent re-derivation against the running code and R2's corrected proposal, fresh)**
  confirmed the corrected proposal with no further gap, and implemented it in the same round:
  `_DOTGLOB_RE`/`_Budget.dotglob_named`; `dialect`/`bash` threaded through `_judge_word`'s rule-5
  call, all three `_judge_piece` call sites, and `_judge_whole_value`'s own two callers, into
  `_glob_links` and `_globstar_walk` (both now take `bash: bool`); the dot-rule guard in each
  matching loop (`_glob_links`'s exempts a pattern starting with `.`/`[` or holding a dot-leading
  extglob alternative; `_globstar_walk`'s has no exemption clause, since `**` qualifies for neither).
  Measured directly against `_decide`: `ls sub/?l/x` (Bash) is now allowed with `.l` linked out,
  `Get-ChildItem sub/?l/x` (PowerShell) stays refused, `shopt -s dotglob; ls sub/?l/x` is refused
  once named, and the extglob-alternative fix is confirmed both ways (`@(.hidden|zzz)` refused,
  `@(zzz)` against the same fixture stays allowed). Added the Bash and `dotglob`-named rows to
  `test_an_absolute_or_piece_relative_glob_is_matched_through_the_link_it_finds_1_4c_r5` and a new
  `test_an_extglob_alternative_beginning_with_dot_is_not_exempted_from_the_bash_dot_rule_d14`.
  `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **121 passed**.
  Mutation-checked (`git stash` on `mcp_server.py` alone): fails exactly the new assertions/test,
  the other 119 stay green. `ruff check` and `black --check` clean; `mypy` shows only the
  pre-existing, unrelated `approve_tool_call` note. **Task 1.4c now ticks**: all three of its named
  gaps (the Windows POSIX-class/drive-letter split, the absolute top-level dot-glob row, and the
  bash dot rule) are closed.
- [x] 1.4e (R6, D11, link fixture) **a bracket at a word's edge**, refused as outside, the reason naming where `up` resolves:
  - `cp n [u]p/` and `cp n ./u[p]` (a trailing `]` the trim removes). Each PASSES today only by the tail (`'/'`, `'/u[p'`), so assert the resolved target, which FAILS today; each FAILS against R5 (allowed).
  - `cp n [.]./x` refused as outside, quoting `'[.]./x'`. PASSES today by the tail `'/x'`, FAILS on the reason assertion and against R5 (the word `.]./x` is inside).
  - PowerShell `Copy-Item n [u]p\x` (Windows) or `[u]p/x` (POSIX): same as the first row.

  Controls: `ls [../x]` stays **refused** as `'../x'` (PASSES today; FAILS if the bracket-kept word replaced the ordinary one instead of adding to it); `echo arr[0] x[1:]`, `python -c '["a","b"]'` and `ls sub/[ab].py` allowed. The separator-less `cp n [u]p` and `cp n u[p]` stay allowed under this change alone; the sibling change's 1.4f refuses them.

  **Iteration 45.** Re-derived this task's own remaining rows fresh against `_decide`
  (`testbed/scratch/measure_214d_1_4e_remaining.py`, gitignored, not committed), not trusting the
  task's own claim that `cp n [u]p/`, `cp n ./u[p]` and the PowerShell form PASS today only by the
  tail: with task 2.2 now built (iteration 43, which wired `_glob_links` into rule 6's per-piece
  reading via `_holds_glob_character`), all three are already refused, naming the resolved target,
  with no further production change needed -- `cp n [.]./x` (1.4e1) and every control row (1.4e2-7)
  were already covered by earlier iterations. Added
  `test_a_bracket_at_a_words_edge_is_matched_through_the_link_it_finds_1_4e` (the trailing-slash-only
  row, the bracket-closes-at-the-end row, and the POSIX-form PowerShell row) and
  `test_a_bracket_at_a_words_edge_is_matched_through_the_link_it_finds_windows_powershell_1_4e`
  (the backslash form, Windows-only) to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. Mutation-checked: temporarily forcing
  `_bracket_kept_word` to always return `None` and rerunning just the new tests fails both new test
  functions (`assert True is False` on the `allow` check) with the expected `AssertionError`s,
  confirming they are not vacuous; reverted immediately, `git diff --stat` on `mcp_server.py` clean
  afterward (no production change was needed, confirmed before and after). `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **119 passed** (was 117, +2). Broader
  regression set (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): **745 passed, 2 skipped**, no regressions.
  `ruff check` and `black --check --target-version py311` on the changed test file: clean. `git diff
  --stat`: exactly `hub/tests/test_the_shell_judge_reads_a_word_whole.py` and this task file.

  **Task 1.4e now ticks.** Every row and control this bullet names is measured and passes, with no
  production change needed this iteration (task 2.2 had already done the wiring). This does not
  close task 1.4c itself, which has its own separate open rows (the Windows-side POSIX-class gap,
  the absolute top-level dot-glob gap, and the bash-dot-rule control gap -- see 1.4c's own notes).
- [x] 1.4f (R6, D12, operator `B4-link-dotdot`, link fixture with `sub/l` → `work`) **a `..` after a link**, refused as outside, the reason naming the workspace's parent:
  - `cp n sub/l/../y`, `echo hi > sub/l/../x1`, `ls sub/l/../x`. On the `hub-judge-windows` job each FAILS today (allowed: `ntpath.realpath` removes the `..` first, measured). On Linux each PASSES today (`posixpath.realpath` is physical); keep them there as controls.
  - `cp n sub/l*/..` and `ls sub/l*/../x`, both platforms. Each PASSES today only by the tail (`'/l*/..'`, `'/l*/../x'`), so assert that the reason quotes the whole piece (`'sub/l*/..'`, `'sub/l*/../x'`) and names the workspace's parent after "it resolves to", which FAILS today; each FAILS against R5 (allowed: the walk's `..` matched no listing entry). (R7) The "names the parent" half also FAILS against R6 as written, whose `_judge_path` on the real parent gives the bare `_OUTSIDE` (measured); it needs design D8 step 4's `_resolves_elsewhere(<listed>/.., <real parent>)`.
  - (R7) A literal component after a glob that is a junction: `ls i*/l/../x` (with `in` → `work/sub`, so `i*/l` is the junction `sub/l` → `work`) refused, naming the workspace's parent. FAILS against a step-4 link test built on `os.path.islink`, which is False for a junction on Python 3.11 (Windows job); PASSES today only by the tail `'/l/../x'`.
  - (R7) The named cost, asserted so a change of mind is visible, both platforms: `ls sub/l*/../work/a` (the fixture's workspace directory is `work`) refused, although Git Bash expands it to `sub/l/../work/a`, inside. PASSES today (tail `'/l*/../work/a'`), and FAILS if the walk judged only where the piece ends.
  - The named costs, asserted so a change of mind is visible, Windows only, each FAILS today (allowed): PowerShell `Set-Content sub\l\..\p1 hi` refused; `_decide("Write", {"file_path": <workspace>\sub\l\..\z})` refused.
  - The bound, Windows only: a relative path of 65 `sub/..` pairs followed by `x` is refused as `_UNRESOLVED`; 64 pairs are allowed.

  Controls allowed, both platforms: `ls in/../sub` (a link to a directory of the same depth), `ls sub/../sub/a.py`, `ls in/../sub/*.py`.

  (R8, design D12 Costs, the third review's LOW) In its own fixture, so that the shared fixture's root globs are unchanged: a sibling `checkout/node_modules` and `checkout/src`, and `work/node_modules` a link → `checkout/node_modules` (the Hub's shared dependency link, `_symlink_shared_dependencies`), each refused, naming `checkout`'s `src/x` after "it resolves to":
  - Bash `cp n node_modules/../src/x`: the correct refusal (Git Bash's `cp n node_modules/../nm1` wrote into `checkout`, measured). On the Windows job it FAILS today (allowed, measured: it escapes today); on Linux it PASSES today (`posixpath.realpath` is physical).
  - `_decide("Write", {"file_path": <work>/node_modules/../src/x})`: the named false refusal (Node writes `work/src/x`), asserted so a change of mind is visible. On the Windows job it FAILS today (allowed, measured); on Linux it PASSES today.

  **Iteration 52.** Re-derived this task's scope fresh against the current code before building,
  per the prior note's own instruction (do not assume iter 32's or any older note still applies
  without checking). Found that most of this task's rows are already correct and already tested
  under other tasks' names, not 1.4f's own: the literal rows (task 2.0b,
  `test_a_dotdot_after_a_link_is_refused_though_a_native_program_writes_inside` and
  `test_the_physical_readings_64_step_bound` cover the two named-costs rows and the 64/65-step
  bound already), the glob rows `cp n sub/l*/..`/`ls sub/l*/../x` (task 2.1c's own
  `test_an_absolute_glob_word_s_tail_dotdot_moves_the_branch_through_a_link` and
  `test_a_dot_leading_glob_is_also_matched_against_the_link_it_finds_2_1c`'s own control), and the
  three "Controls allowed" rows (`_TABLE` rows `1.4f4`-`1.4f6`). Measured the two rows this task's
  own text names that had no test anywhere yet, directly against `_decide` first
  (`testbed/scratch/measure_14f_remaining.py` and `measure_14f_named_cost.py`, gitignored, deleted
  after use, not committed), before writing either as a test:
  - the junction row (R7): `ls i*/l/../x`, using the shared fixture's own `in` → `sub` and `sub/l`
    → `work` links (no new fixture needed -- `i*` matches `in`, the literal `l` that follows it
    inside `sub` is the junction, exactly as the task's parenthetical describes). Refused, naming
    the workspace's parent, **already correct**: `_glob_tail_walk`'s literal-component branch
    tests a followed component with `_is_link_path` (`hub/hub/mcp_server.py:1581`), which reads
    the Windows reparse-point attribute a junction sets, not `os.path.islink` alone -- the gap the
    task's own text worried about was already closed by an earlier iteration's D8 step 4 work, not
    by this one. Added `test_a_literal_component_after_a_glob_link_can_itself_be_a_junction`.
  - the named-cost row (R7, both platforms): `ls sub/l*/../work/a`. Refused, naming the parent,
    **already correct**: `_glob_tail_walk` judges where a `..` in the tail lands (the real
    parent) and returns the refusal immediately, before it ever reads a literal component that
    follows the `..` (`work`, `a` here) -- so the walk never gets as far as noticing the tail
    would, in Git Bash, actually land back inside. Added
    `test_a_glob_link_s_dotdot_tail_refuses_before_reading_a_literal_name_after_it`.

  Mutation check skipped for both: neither needed a production change (both rows were already
  correct), so stashing `mcp_server.py` would prove nothing about these two tests specifically --
  confirmed by reading `_glob_tail_walk` and `_is_link_path` directly rather than assumed. `py
  -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 123 passed (was 121,
  +2). Broader regression set (`test_permission_approver.py`/`test_hub_own_call.py`/
  `test_copilot_acp_decide.py`/`test_a_write_outside_the_workspace_is_recorded.py`): 626 passed, 2
  skipped, no regressions -- confirms iteration 51's D14 change (bash dot rule) did not regress
  anything either, closing that iteration's own open question. The full `hub/tests/` suite was
  started in the background again this iteration and still had not produced output after several
  minutes (consistent with its historical ~46-minute runtime, `hub-suite-gate`); relied on the
  targeted file plus the broader regression set instead, as prior iterations addressing this same
  task (2.0b, 2.1c) also did. `ruff check` and `black --check --target-version py311` on the test
  file: clean. `git diff --stat`: only the one test file and this task file changed.

  **Iteration 53.** Built the one remaining piece: the R8 shared-dependency-link fixture, in its
  own `tmp_path`-based setup (not the shared `workspace` fixture), kept separate so the shared
  fixture's root-level globs stay unchanged -- `checkout/node_modules`, `checkout/src/x`, and
  `work/node_modules` a link to `checkout/node_modules`, via the test file's own `_link` helper (a
  junction on Windows), matching the direction and naming `_symlink_shared_dependencies`
  (`hub/hub/worktrees.py`) actually uses (`target.symlink_to(source, ...)`, `target` inside the
  worktree, `source` in the checkout) -- re-derived from that function directly before building,
  per the prior note's own instruction. Used a junction rather than a real symlink because design
  D12 Costs's own R8 scratch measurement did too ("Measured in the R8 scratch, with
  `ws/node_modules` a junction to `checkout/node_modules`") and because this machine cannot build a
  real symlink without privilege (measured earlier in this file, `OSError: WinError 1314`) -- a
  junction is sufficient here since `_physical`'s resolution is `os.path.realpath`, which follows a
  junction's reparse point the same way it follows a symlink. Measured both named rows directly
  against `_decide` first (`testbed/scratch/measure_14f_r8_shared_dep.py`, gitignored, deleted
  after use, not committed): both are **already correctly refused** by D12's existing `_physical`
  walk, naming the checkout's `src/x` after "it resolves to" -- no production change needed, so no
  mutation check (confirmed by reading `_physical`/`_where` directly, not assumed). Added
  `test_a_dotdot_after_the_shared_dependency_link_resolves_to_the_checkout_1_4f_r8`. `py -3.11 -m
  pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 124 passed (was 123, +1).
  Broader regression set (`test_permission_approver.py`/`test_hub_own_call.py`/
  `test_copilot_acp_decide.py`/`test_a_write_outside_the_workspace_is_recorded.py`): 626 passed, 2
  skipped, no regressions. `ruff check` and `black --check --target-version py311`: clean.
  `openspec validate the-shell-judge-reads-a-word-whole --strict`: valid. `git diff --stat`: only
  the test file and this task file changed -- no production file touched.

  **Task 1.4f ticks.** Every row this task names is now either tested directly under its own test
  or already covered, and measured, under another task's test name (documented above).
- [x] 1.4g (R8, design D2 step 6, the third review's HIGH; the shared fixture's `sub/@s/p`, `a'b/up` and `a@b/l`) **the whole value is judged as the path it spells**. Refused, each naming where it resolves:

  **Iteration 25 note.** Built as task 2.2's second slice; see that task's own note for the
  implementation. Every row above is covered by
  `test_the_undivided_whole_value_is_judged_too_1_4g` in
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, measured against `_decide` directly
  first, **except** the POSIX-only `work/t:d` row, which cannot be built on this Windows machine
  (NTFS refuses a `:` in a file name outside the drive position) -- added to the test guarded by
  `if not _WINDOWS`, so it runs on CI's `hub-test` job (`ubuntu-latest`) but is unverified by this
  iteration. Ticking this task on that basis, not on a plan: every other row was run and is green;
  the one row this machine cannot run is reasoned through against the same code path (`not
  _DRIVE_LETTERS` judges the whole value with its colons kept, matching D2 step 6's own POSIX
  text) and will fail loudly in CI if that reasoning is wrong, not silently pass. A future iteration
  should confirm the `hub-test` job actually ran this row green after this change's first push,
  and downgrade this tick if it did not.
  - `cp n sub/@s/p/x` (Bash) and PowerShell `Copy-Item n -Destination:sub/@s/p/x`: through a link behind a package scope's `@`, and behind a colon-joined option;
  - `cp n "a'b/up/x"`: through a link behind a quote;
  - `cp n sub/@s/p/*`: the glob's base is the link, and the literal whole value is what refuses (design D8 step 1);
  - `cp n "a@b/l/../y"`: a physical `..` (D12) after a link behind `@`, naming the workspace's parent.

  Each PASSES today only by the tail (`'/@s/p/x'`, `'/up/x'`, `'/@s/p/*'`, `'/l/../y'`), so assert the resolved target, which FAILS today. Each FAILS against R7 as written (allowed: the pieces `sub/`, `s/p/x`, `a`, `b/up/x`, `b/l/../y` are inside, and D8 listed `outside` from an outside base). Measured in Git Bash, the first three wrote into `outside` and the last beside the workspace.

  Also refused, the run-on at a dividing character, quoting the whole value: `cp n "../work(a"` and `mkdir '../work@'` (the fixture's workspace directory is `work`; in the R8 scratch, whose workspace is `ws`, Git Bash's `cp n "../ws(a"` wrote the sibling file `ws(a` and `mkdir '../ws@'` made the sibling directory `ws@`, measured). Each PASSES today by the tail (`'/work(a'`, `'/work@'`), so assert the quoted `'../work(a'` and `'../work@'`, which FAILS today; each FAILS against R7 (the piece `../work` is the workspace).

  POSIX only: a directory `work/t:d` holding a link `up` → `outside`; `cp n t:d/up/x` refused, naming where it resolves (the whole value with its colon). PASSES today by the tail, FAILS against R7. On Windows no name can hold a colon (design D2 step 6; the msys residual is named in design Residuals).

  Controls allowed (the review's measured-nil costs; each must stay allowed with step 6 in place): `git show HEAD:src/a.py`, `git show HEAD~2:src/a.py`, `ls node_modules/@babel/core` (no link), `npm install @types/node`, `python -c 'print(1/2)'`, `sed -E 's/(foo)/\1/' f`, `git log --format=%h/%s`, `grep -E '^(a|b)/c' f`, `rg 'foo(bar)/baz'`, `sh -c 'ls 2>&1/x'` (each refused today by its tail, measured), and `ls lib/Foo::Bar.pm` (allowed today as a plain word; after D7 it reaches rule 6, whose whole value must not refuse it). On the Windows job also `grep 'ORM\|:2580' f` and `sed -E 's/(:700)/(:697)/g' f` (both from this repository's transcripts), which a whole-value reading that kept the colons on Windows would refuse (measured: `ntpath.realpath` reads `|:2580` and `(:700)` as drives; design D2 step 6). Controls refused by their pieces, as under R7: `npm i x@file:../lib` (`'../lib'`), `sh -c "echo hi>../x"` (`'../x'`), `sh -c 'cat</etc/passwd'`.
- [x] 1.4d (R4, bounds) A directory `big/` of 8193 empty files: `ls big/*` is refused with the too-many reason (FAILS against R3, which allows it). `ls sub/*` is allowed. With `globstar` named (`bash -O globstar -c 'ls sub/**/x'`) a link two levels down (`sub/deep/l` → outside) is refused, and without it the same `ls sub/**/x` is allowed (the named residual; assert it, so a change of mind is visible). R5: the pattern starts at `sub/`, because a top-level `**` matches the fixture's `up` link and would be refused either way

  **Iteration 29.** Built the globstar rule this row needs (`_glob_links`'s own docstring named it
  as the true reason 2.1c could not tick): a `_Budget.globstar_named` flag, read once per `_decide`
  from the whole top-level command text (`_GLOBSTAR_RE`, design R5 -- not re-derived for a nested
  substitution's own text, so a nested command cannot flip the flag an outer `_glob_links` call
  already made on the outer text's say-so); a component that is exactly `**`, when the flag is set,
  is now walked recursively by a new `_globstar_walk` rather than matched as one `fnmatch`
  component (which could not tell `**` apart from `*` on its own) -- the shared tail-walk logic
  (D8 step 4) was pulled out of the single-component match loop into `_glob_tail_walk` so both
  readings use the one rule. Measured directly against `_decide` first (a throwaway script, not
  committed): `bash -O globstar -c 'ls sub/**/x'`, with `sub/deep/l` a link out two levels below
  `sub`, was wrongly **allowed** before this fix (the one-level match found only `sub/deep`, never
  listed `l`); `ls sub/**/x` with no `globstar` named stays allowed, unchanged, confirming the
  named residual. The budget-bound two bullets (`big/*`/`sub/*`) needed no new code -- task 2.0's
  `_Budget.glob_entries_examined` already covers them, exercised by the existing
  `test_the_glob_link_walk_s_entries_are_charged_against_the_decide_budget` (a monkeypatched bound
  against the fixture's own entry count, not a literal 8193-file directory, the same surrogate that
  test already used). Added
  `test_a_globstar_walk_also_matches_a_link_several_levels_down_1_4d` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. Mutation-checked (`git stash`ing just
  `mcp_server.py`): exactly this one new test fails, the other 102 rows pass unchanged. `py -3.11 -m
  pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 103 passed (was 101, +2 -- the
  second is 1.6's own row below). Broader regression set
  (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 729 passed, 2 skipped, no regressions.
  `ruff check` clean; `black --check --target-version py311` clean, no reformat needed; `mypy
  hub/hub/mcp_server.py` clean (the one pre-existing `approve_tool_call` gap only). `git diff
  --stat`: exactly `hub/hub/mcp_server.py`, the one test file, and this task file. Ticked: every row
  this task's own text names is now built and verified.
- [x] 1.5 Network (D5), each with the network reason naming the whole word:
  - `git clone git@github.com:o/r.git` and `curl -s 127.0.0.1:9/x` refused. Both FAIL today on the reason.
  - (R4) `git clone git@github.com:repo`, `scp n user@example.com:file` and `scp n root@10.0.0.5:f` refused. Each FAILS today (allowed) and FAILS against R3 (D5 in rule 6 never sees a separator-less word).
  - (R4) Allowed: `docker pull alpine@sha256:abc`, `npm i x@npm:y`, `pnpm add x@workspace:y`, `scp a host:x/y`, `scp n user@myserver:file`. `docker run -p 8080:80 img` stays allowed, and `docker run -v data:/app img` stays refused as `'/app'`.
  - (R4) `npm i x@file:../lib` refused as `'../lib'`, outside.
  - (R5) `scp n user@example.com:` refused with the network reason. FAILS today (allowed, measured) and FAILS against R4 (`_words` trims the colon).
- [x] 1.6 Totality. `_decide` answers, and never raises, for these `Bash` commands:
  - `{` × 5000, and a single-quoted `{` × 5000;
  - 20 arguments of 100 alternatives each (refused by the per-`_decide` bound);
  - `{a,` × 2000, `a{1..99999999}`, `[[[[.*`, `.[`, `@(` × 3000, `*(*(*(a)))b` × 50;
  - a 300-alternative brace pattern (refused with the too-many reason);
  - a backslash run of 70,000 characters followed by `./x`;
  - (R5) a word ending in a backslash, PowerShell `dir src\` and Bash `ls 'x\\'` (Bash's lexer removes an unquoted final `\`, so the Bash row is quoted; the levels must end when one changes nothing);
  - (R5) `{a,b}` repeated 40 times in one argument (2^40 alternatives), refused with the too-many reason within the test's timeout.

  Letter ranges expand in full: on Windows `cp x {Z..a}..` is refused and `ls {a..c}` allowed.

  (R4, R5) A link cycle, in a workspace holding only a link `loop` → the workspace root (no link out, so nothing else refuses first): `bash -O globstar -c 'ls **/x'` answers, allowed, within the test's timeout. It hangs without D8 step 4's rule that a `**` walk does not descend through a link.

  (R4) The memo: a Bash command read in both readings charges the budget once, so `ls sub/*` with the entry bound monkeypatched to the number of entries in `sub` is allowed. This FAILS without the memo.

  (R6) The memo key carries the trimmed-colon flag: `echo a@example.com,a@example.com:` is refused with the network reason, naming `a@example.com:`. FAILS today (allowed, measured) and FAILS with the key R5 wrote, since the first word's allow is reused for the second.

  (R5) The listing memo: `ls sub/*.py sub/?.py sub/[ab].py`, with the same bound, is allowed. Three patterns over one directory are charged one listing. This FAILS with a memo keyed by pattern.

  `approve_tool_call` with `_decide` monkeypatched to raise returns a deny whose message names the failure, and reports it (D6); FAILS today (raises). Run on POSIX CI too (the NUL row X8 stays refused).

  **Iteration 17 (partial, brace/budget rows only).** Measured directly against `_decide` first (a
  throwaway script, every row answered in under 5ms, none raised): the `{` x 5000 row (both
  unquoted and single-quoted), the 20-arguments-of-100-alternatives row, `{a,` x 2000, the
  300-alternative brace row, and the `{a,b}` x 40 (2^40) row are all refused with `_TOO_MANY` and
  none hangs or raises, because `_expand_braces` is iterative (an explicit stack, capped at
  `_BRACE_MAX_NESTING`) and `_brace_absorb` refuses before multiplying out past the budget. Letter
  ranges: `ls {a..c}` allowed (confirmed `_brace_sequence` already expands a letter range in full);
  on Windows, `cp x {Z..a}..` refused (the range crosses `\`, read as a separator). Added
  `test_the_totality_rows_for_brace_expansion_never_raise_or_hang` and
  `test_a_letter_range_through_a_separator_is_refused_on_windows` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 83 passed (was 81, +2). Broader
  regression set (+`test_permission_approver.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): 709 passed, 2
  skipped, no regressions. `ruff check` and `black --check --target-version py311` on the changed
  test file: clean. No production file changed this iteration, so no mutation check applies; these
  rows prove existing behaviour rather than a new fix. `git diff --stat`: exactly the one test file,
  plus this file. **Not built this iteration, task 1.6 stays unticked**: the extglob/backslash-run
  rows (`@(` x 3000, `*(*(*(a)))b` x 50, the 70,000-backslash run, the trailing-backslash rows --
  not brace-specific, but not yet measured either), the link-cycle `**` row and the listing memo
  (both need `_glob_links`, task 2.1c, not built), the memo key's colon flag (R6), and
  `approve_tool_call` catching a raise from `_decide` (D6, task 2.2b, not built).

  **Iteration 29 (partial, the link-cycle row only).** Built the globstar walk task 2.1c's own note
  named as the true blocker (see task 1.4d's iteration-29 note for the production change). Measured
  the cycle row directly against `_decide` first, in a minimal workspace holding only a link `loop`
  -> the workspace root (not the shared fixture, whose own `up` link would refuse the top-level `**`
  first and never reach the cycle guard): before this iteration, `**` was a one-level `*`, so `bash
  -O globstar -c 'ls **/x'` was already allowed with nothing ever hanging -- there was no recursive
  walk to hang. Confirmed the guard itself is load-bearing, not decorative, with a throwaway
  monkeypatch that removed the stop-at-a-link `continue` from the real recursive walk: on this exact
  fixture it recursed until Python's own call-stack limit raised `RecursionError` (a real function
  recurses rather than loops, so without the guard it is a stack overflow, not a true infinite
  loop, but the underlying defect -- no termination on a link cycle -- is the one this row names).
  Added `test_a_globstar_walk_does_not_descend_through_a_link_cycle_1_6`. **Task 1.6 still stays
  unticked**: the extglob/backslash-run rows, the listing memo, the memo key's colon flag, and
  `approve_tool_call`'s D6 catch are all still unbuilt, exactly as the iteration-17 note above left
  them.

  **Iteration 34 (partial, the D6 row only).** Built design D6: `approve_tool_call`'s workspace-posture
  branch now wraps the `_decide` call in `try/except Exception`, answering `{"allow": False,
  "reason": "the workspace check failed on this call (<exception class name>); ask the operator
  with ask_user"}` and still routing that decision through `_report_decision` like any other
  refusal. Matches design D6's exact wording. The operator-posture branch (`_ask_operator`) is
  untouched, per D6's own note that it must not be wrapped here (that path catches its own verdict
  failure in the sibling change). Added
  `test_approve_tool_call_denies_and_reports_when_the_judge_raises_1_6` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`: monkeypatches `mcp_server._decide` to
  raise `RecursionError`, monkeypatches `_report_decision` to record its call, and asserts the
  JSON answer is `behavior: deny` naming `RecursionError`, and that the reported decision is also
  `allow: False` naming `RecursionError`. Mutation-checked (`git stash` just `mcp_server.py`):
  exactly this one new test fails (the raise propagates uncaught), the other 106 rows in the file
  pass unchanged. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 107
  passed (was 106, +1). Broader regression set (`test_permission_approver.py`,
  `test_hub_own_call.py`, `test_copilot_acp_decide.py`,
  `test_a_write_outside_the_workspace_is_recorded.py`): 626 passed, 2 skipped, no regressions.
  `py -3.11 -m pytest tests/ -q` (CLI suite, per CLAUDE.md -- a `tasks.md` edit can break it): 565
  passed, 3 skipped. `ruff check` on both changed files: clean. `black --check --target-version
  py311` on the test file needed one reformat, applied, then clean. `mypy hub/hub/mcp_server.py`:
  the same pre-existing `approve_tool_call` no-return-annotation gap only (deliberate, D6's own
  note: FastMCP would derive `structuredContent` from one and silently defeat an `allow`). `git
  diff --stat`: exactly `hub/hub/mcp_server.py`, the one test file, and this task file. **Only the
  D6 row is ticked by this iteration's own evidence; task 1.6 as a whole stays unticked**: the
  extglob/backslash-run rows and the memo key's colon flag (R6) remain separate, unbuilt residuals.

  **Iteration 32 (partial, the two listing-memo rows only -- line 151 and line 155).** Task 2.1c's
  own iteration (iter 31, this window) built `_Budget.list_directory`, keyed by the resolved
  directory, used by both `_glob_links` and `_globstar_walk`. Re-derived both rows fresh against
  `hub/hub/mcp_server.py` and tasks.md's own wording (not reused from iter 31's note): row 151's
  "both readings" are the unconditional `c`/`utf8` passes `approve_tool_call` always makes (line
  3104), not the two dialects; a plain `Bash` command has one dialect, so `ls sub/*` reaches
  `_glob_links` on `sub` twice, once per reading, with no `$'...'` escape to make the two renderings
  differ. Row 155's three patterns (`sub/*.py`, `sub/?.py`, `sub/[ab].py`) are three distinct
  pattern texts, so a memo keyed by pattern (which this slice deliberately does not build) would
  still list `sub` three times. Measured directly against `_decide` first
  (`testbed/scratch/measure_task_1_6_memo_rows.py`, gitignored, not committed, deleted after use),
  using the shared fixture's `sub` (4 entries: `a.py`, `b.py`, `l`, `@s`) with `_GLOB_ENTRY_BUDGET`
  monkeypatched to 4: both commands allowed on this branch. Mutation-checked by running the same
  script against `mcp_server.py` as it stood at iter 30's tip (`89da542`, before 2.1c's memo),
  temporarily swapped into place and restored after: both wrongly refused as `_TOO_MANY` there,
  confirming the rows exercise the memo and not something already true. Added
  `test_a_bash_command_read_in_both_readings_charges_the_listing_once_1_6` and
  `test_three_glob_patterns_over_one_directory_are_charged_one_listing_1_6` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. Mutation-checked the same way inside
  pytest (the pre-memo file swapped in, `-k "1_6"`): exactly these two new tests fail, nothing else
  in that filter. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 106
  passed (was 104, +2). Broader regression set (`test_permission_approver.py`,
  `test_hub_own_call.py`, `test_copilot_acp_decide.py`,
  `test_a_write_outside_the_workspace_is_recorded.py`): 732 passed, 2 skipped, no regressions.
  `ruff check` and `black --check --target-version py311` on the changed test file: clean. No
  production file changed this iteration (`_Budget.list_directory` already existed from 2.1c), so
  `mypy src/` is unaffected; `git diff --stat`: exactly the one test file, plus this file. **Only
  these two rows' own test coverage is ticked here; task 1.6 as a whole stays unticked**: the
  extglob/backslash-run rows, the memo key's colon flag (R6), and `approve_tool_call`'s D6 catch
  remain separate, unbuilt residuals.

  **Iteration 35 (partial, the memo key's colon flag (R6) only).** Re-derived from the real code
  rather than trusting iteration 16's note: `_memo_judge_word`'s key
  (`word, argument, continues, trailing_colon, dialect, trusted`) has carried `trailing_colon`
  since the memo was first built (`git blame` on that line names the same commit that introduced
  the memo, not a later one), so this row no longer fails -- `echo a@example.com,a@example.com:`,
  measured directly against `_decide` in a real `AW_WORKSPACE_DIR`, is already refused naming
  `'a@example.com:'`. No production change needed; this iteration is test coverage only, closing
  the gap the row's own text still called a future fix. Added
  `test_the_memo_key_carries_the_trailing_colon_flag_1_6` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. Mutation-checked by editing the key in
  `hub/hub/mcp_server.py` down to `(word, argument, continues, dialect, trusted)` (dropping
  `trailing_colon`) and rerunning just this test: it fails (`allow: True`, the first word's memo hit
  reused), confirming the row is load-bearing and not vacuous; reverted with `git checkout --` and
  reran clean. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 108
  passed (was 107, +1). Broader regression set (`test_permission_approver.py`,
  `test_hub_own_call.py`, `test_copilot_acp_decide.py`,
  `test_a_write_outside_the_workspace_is_recorded.py`): 734 passed, 2 skipped, no regressions.
  `py -3.11 -m pytest tests/ -q` (CLI suite, since this iteration also edits `tasks.md`): 565
  passed, 3 skipped. `ruff check` and `black --check --target-version py311` on the changed test
  file: both clean, no reformat needed. `git diff --stat`: the one test file, plus this task file
  -- no production file changed. **Only the R6 row
  is ticked by this iteration's own evidence; task 1.6 as a whole stays unticked**: the
  extglob/backslash-run rows (`@(` x 3000, `*(*(*(a)))b` x 50, the 70,000-backslash run) are the
  only thing left.

  **Iteration 36 (the extglob/backslash-run rows -- the last unbuilt part of this task).** Measured
  all three directly against `_decide` first (a throwaway script, not committed), in a real
  `AW_WORKSPACE_DIR`: none raises. `ls ` + `@(` x 3000 + `x` (3000 unbalanced extglob opens, no
  closing `)` anywhere) answers in a little over a second -- `_extglob_group_spans` rescans from the
  next trigger character each time a `(` fails to balance, which is quadratic in the length of an
  unbalanced run, but it terminates and never hangs. The literal `*(*(*(a)))b` x 50 (50
  self-contained, already-balanced nested groups concatenated with no separator) answers in under a
  millisecond, since each unit's matching `)` is found in one pass. A backslash run of 70,000
  characters followed by `./x` (unquoted, so Bash's own escape handling is part of what reaches
  `_decide`) answers in well under a tenth of a second, refused as outside the workspace. No
  production change needed for any of the three; this iteration is test coverage only, same pattern
  as iterations 29, 32, 34 and 35's rows in this task. Added
  `test_the_totality_rows_for_extglob_and_a_long_backslash_run_never_raise_1_6` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. Mutation-checked: a throwaway monkeypatch
  of `_extglob_span_at` to raise (not committed) makes `_decide` raise on the `@(` x 3000 row, which
  this test's call would propagate uncaught -- confirming the test is not vacuous, it would fail on
  a defect of the shape this row guards against. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 109 passed (was 108, +1). Broader
  regression set (`test_permission_approver.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): 626 passed, 2
  skipped, no regressions. `py -3.11 -m pytest tests/ -q` (CLI suite, since this iteration also
  edits `tasks.md`): 565 passed, 3 skipped. `ruff check` and `black --check --target-version py311`
  on the changed test file: both clean, no reformat needed. No production file changed, so `mypy` is
  unaffected. `git diff --stat`: exactly the one test file, plus this task file. **Every row named
  in this task's own text is now built and verified; ticked `[x]`.**
- [x] 1.7 Negative controls that must stay refused, each PASSES today:
  - `curl -o/tmp/x $HUB_URL/api`, `curl -F file=@/etc/passwd x`, `tar -xvf/tmp/a.tar`, `ls a(b/../../x`, `cp x @../y`;
  - `sh -c 'cat</etc/passwd'`, `sh -c "echo hi>../x"`, `python -c "open('/etc/x','w')"`, `node -e "require('fs').writeFileSync('../x','')"`;
  - `scp a host:/x`, `cat /dev/tcp/1.2.3.4/80`, PowerShell `echo hi > /dev/null`;
  - Windows only, with `<other>` a drive letter that is not the workspace's: PowerShell `Copy-Item x <other>:foo\bar` and `Copy-Item x -Destination:<other>:foo\bar`.

  **Iteration 9 re-derived this independently against `_decide`** (not reused from iteration 7's
  note), with the shared `workspace` fixture, on this machine (Windows, only `C:` real, `Z:`
  substituted for `<other>`): the first three bullets (11 named cases) do refuse correctly today
  and are now in `_TABLE` as rows 1.7a, 1.7e-1.7o (measured, regression guards only, each naming the
  design step it exercises). **The fourth bullet does not hold**: `_judge_pieces`'s
  `_PIECE_BREAKS_RE` splits at `:`, so `Z:foo\bar` becomes pieces `Z` and `foo\bar`, both judged as
  inside relative paths -- the drive letter is dropped, not refused (measured: both `Copy-Item x
  Z:foo\bar` and `Copy-Item x -Destination:Z:foo\bar` are **allowed**, not refused as this task's
  own "each PASSES today" framing claims for the whole group). This needed D9's `_DRIVE_LETTERS` and
  D2 step 3's platform-keyed drive exception (task 2.2a).

  **Iteration 54.** Built that one piece of 2.2a -- the drive exception in the piece reading (D2
  step 3) only, not 2.2a's other three parts (the tilde-piece refusal for a drive piece, the
  level-by-level escape-removed readings through `_judge_word`, and the `::` not-plain rule; left
  unticked below for a later iteration to re-derive fresh). Re-read `_judge_pieces_reading`
  (`hub/hub/mcp_server.py`) first: it splits at `_PIECE_BREAKS_SPLIT_RE` with no drive awareness, so
  `Z:foo\bar` always broke at the colon, same bug as the task's own measurement. Added
  `_DRIVE_COLON_RE` (an alternation of `_PIECE_BREAKS_RE`'s own break-char class or `\A`, then a
  single `[A-Za-z]`, then `:` -- reusing the existing class so the two stay in agreement about what
  a break is) and `_mask_drive_colons`, gated on `_DRIVE_LETTERS` read at call time (D9's own rule,
  not baked in at import). Wired into `_judge_pieces_reading` the same way `_mask_extglob_groups`
  already is: masked before the split, restored (to `:`) alongside the extglob sentinels once a
  piece is carved out. Measured directly against `_decide` before writing a test
  (`testbed/scratch/measure_17_drive_exception.py`, gitignored, deleted after use): both
  `Copy-Item x Z:foo\bar` and `Copy-Item x -Destination:Z:foo\bar` were **allowed** before the fix
  (confirming the bug) and **refused**, resolving to `'Z:foo\bar'`, after it -- no real `Z:` drive
  needed, matching design D2 step 3's own "(R6) this holds whether or not drive A exists" (measured
  directly: `os.path.realpath` on a missing drive raises nothing, just returns the unresolved
  drive-relative text, and `os.path.commonpath` against the workspace root then raises `ValueError`
  on the differing drive, which `_judge_resolved` already turns into `_resolves_elsewhere`). Added
  rows `1.7p`/`1.7q` to `_TABLE` (`hub/tests/test_the_shell_judge_reads_a_word_whole.py`,
  `windows_only=True`, PowerShell tool) for this task's own fourth bullet.
  `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: **126 passed** (was
  124, +2). Broader regression set (`test_permission_approver.py`/`test_hub_own_call.py`/
  `test_copilot_acp_decide.py`/`test_a_write_outside_the_workspace_is_recorded.py`): 626 passed, 2
  skipped, no regressions. `ruff check` and `black --check --target-version py311` on both changed
  files: clean. `mypy src/`: no issues (the CLI suite; CI never runs mypy on `hub/`). `openspec
  validate the-shell-judge-reads-a-word-whole --strict`: valid. `git diff --stat`: exactly
  `hub/hub/mcp_server.py` and the one test file changed. **Every row this task's own text names is
  now refused as claimed; ticked `[x]`.**

  Each names in a comment the implementation it catches.
- [ ] 1.7b (R3) Regressions of R2's rule set. Each PASSES today (refused by the tail) and FAILS against pieces built as R2 wrote them:
  - Windows, Bash tool, `Z` not the workspace's drive: `python w.py 'Z:foo\bar'`, `python w.py Z:foo/bar` and `powershell -c "Copy-Item x Z:foo\bar"`, refused as outside naming `Z:foo…`.
  - Both platforms: `dd if=x of=c:~/y` and `git show HEAD:~/x`, refused as uncheckable. Assert the reason.
  - POSIX only: `python w.py Z:foo/bar` allowed. FAILS today (tail `'/bar'`).
- [ ] 1.7c (R3, R4; design D7) Escapes allowed today:
  - (R5, POSIX CI) `grep -rn '\.\./' src` refused: the named cost, asserted so that a change of mind is visible. FAILS today on POSIX (allowed).
  - `bash -c 'cp n .\./x'` refused, from both the Bash and the PowerShell tool. FAILS today.
  - (R4) `bash -c 'bash -c "cp n .\\./x"'` refused (Bash tool). FAILS today and FAILS against R3's one-level D7.
  - (R4, POSIX CI) `bash -c 'bash -c "cp n \$HOME"'` refused **once the sibling change is in**. Until then, assert that its level-1 word `$HOME` reaches `_judge_word`: spy on `_judge_word`, which FAILS against R3, where the escape-removed text was judged only as a path.
  - PowerShell `Copy-Item x Microsoft.PowerShell.Core\FileSystem::C:\Windows\x` refused (Windows), and `…\FileSystem::..\x` refused naming `..\x`. FAIL today.
  - Controls that stand: `grep foo 'src\a.py'` (Windows), `ls lib/Foo::Bar.pm`.
- [x] 1.7d (R4, D4 on Windows, Windows job) `python -c "open('/dev/null','w')"` refused as a path. PASSES today (tail), and FAILS against R3's D4. `sh -c "ls 2>/dev/null"` and `python w.py /dev/null` are allowed.

  **Iteration 26.** Built as task 2.2's third slice; see that task's own note for the measurement,
  the fix (`_PIECE_BREAKS_SPLIT_RE`, `dialect` threaded through the piece reading) and the test
  (`test_a_redirect_target_piece_names_a_bash_device_1_7d`).
- [x] 1.8 In `hub/tests/test_permission_approver.py`, move rows X4, X5 and X6 out of "Residuals" to allowed, and change the expected reasons: N5 and N6 to `_NETWORK`, G3 to `_outside("../include")`, E11 to `_outside("../stray.txt")`, Z1 and Z2 to the whole traversal. Rewrite their comments to name this change, and record that each FAILS today

## 2. The fix

- [x] 2.0 (R4) `_Budget` and the per-`_decide` memo (design, "The bounds"), created in `_decide` and passed through `_read_command` (both dialects, both readings, nested); (R6) the memo key includes the trimmed-colon flag. `_TOO_MANY`. ~~`_DRIVE_LETTERS` (D9)~~ -- **built by task 2.0b above**, not here (iteration 15 re-derived that D9 and "The bounds" are independent design concerns).

  **Iteration 16.** Found, before writing anything, that an earlier iteration's tasks 1.2/1.3 had
  already built `_expand_braces`, `_mark_inner_brace_sentinels` and the sentinels in `_lex`
  (section 2's task 2.1/2.1b content), wired into `_read_command`, but gated by a provisional
  module constant (`_BRACE_ARGUMENT_BUDGET = 256`, its own comment naming task 2.0 as not yet
  threaded through) rather than a real per-`_decide` budget -- so 2.1/2.1b were left unticked
  (correctly) despite the code existing. This made the gap exact rather than the open-ended one
  the previous `next_action` framed it as: a `_Budget` class, not a brace-specific lexer/expander.
  Built `_Budget` (`hub/hub/mcp_server.py`, beside `_expand_braces`): one object, created once per
  `_decide` call (before the dialect/reading loops) and threaded as a required parameter through
  every `_read_command` call, including the recursive nested-substitution one, so it is shared
  across both dialects, both readings and nesting as the design asks. Two memos, both keyed
  without `reading` (where the `c`/`utf8` readings render identical text the shared key is exactly
  what avoids a double charge; where they differ, the word or argument text itself differs,
  separating them without needing the field): `expand_braces(marked, dialect)` memoizes
  `_expand_braces` by `(marked text, dialect)` and charges `alternatives_spent` only on a miss,
  capped at `min(_BRACE_ARGUMENT_BUDGET, _BRACE_TOTAL_BUDGET - spent)` so "past either bound" (D1)
  falls out of one scalar; `_memo_judge_word` memoizes `_judge_word` by the 6-tuple the design
  names (`word, argument, continues, trailing_colon, dialect, trusted`), `trailing_colon` being
  (R6) the colon flag. Added `_BRACE_TOTAL_BUDGET = 1024` beside the existing per-argument
  constant. `_TOO_MANY` already existed (built with the provisional brace work) and needed no
  change. Did not build `_glob_links`'s entry bound or its directory-listing memo (design "The
  bounds" table's other two rows): `_glob_links` itself is task 2.1c, not built, so there is
  nothing yet to count entries for or memoize listings of -- `_Budget` is left extensible for that
  task to add to, not pre-built unused.

  **Measured, not assumed**, with a throwaway script calling `_Budget.expand_braces` directly
  before writing any test: two calls with the same `(marked, dialect)` charge `alternatives_spent`
  once (10, not 20); clearing the memo's cache between the same two calls (simulating no memo)
  charges it twice, and the second call then returns `None` against a monkeypatched total of 15
  (`cap = min(256, 15-10=5)`, 10 > 5). Added one test,
  `test_the_brace_budget_is_one_per_decide_not_per_reading_or_argument`, to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`: a single 10-alternative brace argument
  with `_BRACE_TOTAL_BUDGET` monkeypatched to 15 is allowed (proving the memo stops the `c`/`utf8`
  reading pair from double-charging one argument, which a shared-but-unmemoized budget would
  refuse); a second, separate 10-alternative argument in the same command is then refused as
  `_TOO_MANY` (proving the total is spent across arguments, not reset between them). Both
  assertions are new behaviour: `_BRACE_TOTAL_BUDGET` did not exist before this iteration, so the
  test fails (`AttributeError` on the monkeypatch) on today's code without the fix. Mutation check
  (`git stash` just `mcp_server.py`): exactly this one test failed; the other 80 rows in the file
  passed unchanged. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`:
  81 passed (was 80). Broader regression set (+`test_permission_approver.py`,
  `test_hub_own_call.py`, `test_copilot_acp_decide.py`,
  `test_a_write_outside_the_workspace_is_recorded.py`): 707 passed, 2 skipped, no regressions.
  `ruff check` and `black --check --target-version py311` on both changed files: clean (black
  reformatted the new `_Budget`/`_memo_judge_word` code once, then was clean). `mypy
  hub/hub/mcp_server.py`: the same pre-existing `approve_tool_call` no-return-annotation gap.
  `git diff --stat`: exactly `hub/hub/mcp_server.py` and the one test file, plus this file. Did not
  run the full `hub/tests/` suite this iteration (46 minutes at the last full run,
  `hub-suite-gate`); relied on the broader regression set as prior iterations have.

  **Queued next (iteration 17 resolved this).** Task 2.1 and 2.1b are now ticked above, confirmed
  by reading the actual code paths (not grep): `_lex`'s sentinel marking, `_expand_braces`'s
  iterative stack, `_read_command`'s two judging passes, and `_mark_inner_brace_sentinels` all match
  the design text and are wired through the real `_Budget`. A brace/budget-specific slice of task
  1.6's totality rows was also measured and tested (see 1.6's own note); task 1.6 itself stays
  unticked -- its extglob/backslash-run rows, the link-cycle and listing-memo rows (need `_glob_links`,
  task 2.1c), the memo's colon flag, and `approve_tool_call`'s D6 catch remain. **Task 2.1c (D8
  `_glob_links`) is section 2's next unbuilt item in build order**, and is the dependency the sibling
  change's drive-gated tasks (1.1, 1.3, 1.5b's drive bullet, 1.5c) are still waiting on. Re-derive
  2.1c from design D8 (steps 1, 2 and 4 especially -- the base resolved by `_physical`, each branch
  carrying its real and listed directory, a literal component's link test via `os.lstat`, `..`
  moving to the real parent and judged via `_resolves_elsewhere`) before building; it is a large
  unit (a new glob-walking function plus wiring at both rule 5 and rule 6's call sites), so size a
  sub-slice if it does not fit one iteration.
- [x] 2.0b (R6, D12) `_physical` and the second reading in `_where`, on a drive-letter host, with the 64-step bound, inside `_where`'s existing `try`. Run 1.4f's literal rows on Windows. This fixes a pre-existing escape and may be built first. (R8, third review) Also correct the `hub/hub/workspace_writes.py` docstring, whose module text (lines 8-10) and `classify` text (lines 172-174) say its `realpath` is "the reason the two agree about a symlink" with `_decide`: after D12, `_decide` also reads a `..` after a link physically on a drive-letter host (a second reading, D12), and `classify` does not, so the two agree about a link named directly and may differ about a `..` after one (`node_modules/../src/x`: `_decide` refuses, on Windows `classify` records `ws/src/x`, inside, which is where Node writes). Comment only; no behaviour of `classify` changes

  **Iteration 15.** Built `_DRIVE_LETTERS = os.sep == "\\"` (D9, a module constant beside
  `_SEPARATORS`, read at call time -- never baked into a regex or default argument) and
  `_physical(absolute)` in `hub/hub/mcp_server.py`: walks `absolute`'s components past the drive
  anchor, resolving the current path with `os.path.realpath` (reading any link) before a `..`
  leaves a name appended since the last resolution, then moving to the parent with
  `os.path.dirname`; raises past 64 such resolutions (`_PHYSICAL_MAX_STEPS`), caught by `_where`'s
  existing `try` as `_UNRESOLVED`. Factored `_judge_resolved` out of `_where` so the lexical and
  physical readings share the same `commonpath`/`_resolves_elsewhere` judgement; `_where` now
  computes the physical reading only when `_DRIVE_LETTERS` and the path holds a `..`, and refuses
  if either reading does. Corrected `workspace_writes.py`'s module and `classify` docstrings as this
  task asks (comment only, `classify` unchanged). Measured directly against `_decide` before
  writing any test (real junctions via `_winapi.CreateJunction` on this machine, which is the
  Windows host production runs on): `cp n sub/l/../y`, `echo hi > sub/l/../x1`, `ls sub/l/../x`
  (literal, no glob) were `allow=True` before the fix and are `allow=False` after; the controls
  `ls in/../sub`, `ls sub/../sub/a.py`, `ls in/../sub/*.py` stayed `allow=True` throughout. Added
  rows `1.4f1`-`1.4f6` to `_TABLE` in `hub/tests/test_the_shell_judge_reads_a_word_whole.py`
  (`_TABLE` runs on both platforms; the three refusals are already true on POSIX, where
  `os.path.realpath` is itself physical, so they serve as controls there) -- these are **task
  1.4f's literal rows only**; its glob rows (`sub/l*/..`, `i*/l/../x`) need D8's `_glob_links`
  (task 2.1c, not built), so 1.4f itself stays unticked. Added two Windows-only tests (`skipif not
  _WINDOWS`) for the named costs (`Set-Content sub\l\..\p1 hi` through PowerShell, and
  `_decide("Write", {"file_path": .../sub/l/../z})`, both measured `allow=True` before and
  `allow=False` after, each asserting the reason names where it resolves) and for the 64-step bound
  (`"sub/../" * 64` allowed, `* 65` refused as `_UNRESOLVED`, measured both ways with a throwaway
  script first). Mutation check: `git stash` the two production files, reran the test file --
  exactly the five new assertions (`1.4f1`-`1.4f3`, the named-costs test, the bound test) failed;
  `1.4f4`-`1.4f6` and every other row passed unchanged. `py -3.11 -m pytest
  tests/test_the_shell_judge_reads_a_word_whole.py -q`: 80 passed (was 72 before this iteration's
  test file edit, confirmed by stashing just that file; +6 `_TABLE` rows, +2 standalone test
  functions). Broader regression set (adds `test_permission_approver.py`, `test_hub_own_call.py`,
  `test_copilot_acp_decide.py`, `test_a_write_outside_the_workspace_is_recorded.py`): 706 passed, 2
  skipped, nothing broken. `ruff check` and `black --check --target-version py311` on the three
  changed files: clean. `mypy hub/hub/mcp_server.py`: the same pre-existing `approve_tool_call`
  no-return-annotation gap `.claude/rules/mcp-server.md` names as deliberate. `git diff --stat`:
  only `hub/hub/mcp_server.py`, `hub/hub/workspace_writes.py` and the one test file changed, plus
  this file. Did not run the full `hub/tests/` suite this iteration (46 minutes at the last full
  run, `hub-suite-gate`); relied on the broader regression set as prior iterations have.

  **Queued next:** task 2.1 (D1, brace expansion in `_lex`/`_expand_braces`) is the next item in
  section 2's stated build order, but re-derive from the design text before starting -- it is a
  larger unit (an iterative expander, sentinels in the bash lexer, `_read_command` judging each
  alternative, totality against 5000-`{` inputs) and may need its own sub-slice. Task 2.0's
  `_Budget`/memo remains open and un-attempted; nothing in section 2.1 onward is known yet to need
  it (the memo is for readings that do not exist until 2.1/2.1c are built), so re-confirm whether
  2.1 truly needs the budget before 2.0, or can be built budget-free with the bound added once
  `_expand_braces` exists -- do not assume either way without reading design D1 and "The bounds"
  together again.
- [x] 2.1 D1 first: sentinels in `_lex` for bash, `_expand_braces` (iterative), and `_read_command` judging each alternative's words. Run 1.2 and 1.3

  **Iteration 17.** Re-derived independently, by reading the code rather than trusting iteration
  16's grep: `_lex` marks an unquoted bash `{`, `,` and `}` with `_BRACE_SENTINELS` (confirmed at
  the call site, not just by name); `_expand_braces` is the iterative stack machine (`_brace_frame`,
  `_brace_absorb`, no recursion, capped at `_BRACE_MAX_NESTING = 32`); `_read_command`'s bash branch
  calls `budget.expand_braces(argument, dialect)` for every argument holding a sentinel and hands
  each returned alternative to `_words`/`_memo_judge_word` as its own argument, refusing with
  `_TOO_MANY` on a `None`. This is task 2.1's own text, built and wired in, not merely present in
  the file. Ran 1.2 and 1.3 (`py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`):
  83 passed (see 2.0's own count; 1.2/1.3's rows are the ones already in `_TABLE` as 1.2a-e/1.3a-j).
- [x] 2.1b The inner-shell brace reading (design D1, R2). Run 1.3 and 1.6

  **Iteration 17.** Re-derived independently: `_mark_inner_brace_sentinels` marks every `{`/`,`/`}`
  in an argument (quoted, escaped, or either dialect) except one directly after a real `$` or
  `_LITERAL_DOLLAR` (still a parameter expansion); `_read_command`'s second pass (after the literal
  word judging) runs this over every argument holding a literal brace, calls
  `budget.expand_braces(marked, dialect)`, and judges each alternative's words the same way as the
  first pass. This is the "blanket worst case... reaches a nested shell or not" task 2.1b asks for.
  Ran 1.3 (passing, as above) and the brace-specific slice of 1.6 this iteration added (below) --
  task 1.6 itself is far larger than the brace rows and stays unticked.
- [x] 2.1c (R4) D8 `_glob_links`, built **before** 2.2, because rule 6 without it regresses; (R6) with the base resolved by `_physical`, each branch carrying its real directory, literal components moved into rather than listed, and `..` moving to the real parent and judged (design D8 step 4); (R7) each branch also carries its listed path, so a `..` refusal names where it lands (`_resolves_elsewhere`), a literal component's link test is `os.lstat` (not `os.path.islink`), and `_physical`, `realpath` and `lstat` inside `_glob_links` are wrapped as design "What each changed route returns" says. Run 1.4c, 1.4d and 1.4f

  **Iteration 19 (partial, a first slice).** Re-derived D8 from the design text again, as iteration
  18's own note asked, rather than trusting that reading. Confirmed it is still too large to build
  whole in one iteration (a directory-walking function with a relaxed bracket/extglob translator,
  multi-component descent, link tests via both `is_symlink()` and the Windows reparse-point bit,
  and `..`-after-a-link judging) and sized a genuinely minimal slice instead: `_glob_links(piece,
  shown, root)` in `hub/hub/mcp_server.py`, reachable only through rule 5 (`_judge_word`), on an
  absolute word that holds a glob character. It handles exactly the case design D8's "(R5) In rule
  5" bullet names -- a piece whose **only** glob-holding component is its **last** one, holding
  `*`/`?` only (no bracket expression, no extglob group), with **no `..` anywhere** in the piece.
  The base (the piece's leading components) is resolved by `_physical` (so a link in the base,
  including a junction, is followed, exactly as D8 step 1 asks) and listed once with
  `os.scandir`; a matching entry is judged a link by a new `_is_link_entry` helper
  (`is_symlink()`, or on a drive-letter host the reparse-point bit of `DirEntry.stat(follow_symlinks=False).st_file_attributes`,
  since `is_symlink()` is False for a junction on Python 3.11 -- D8 step 3), and a matching link is
  judged by `_judge_path(entry.path, root, shown, shown, False)`, quoting the word as written.
  Everything else D8 asks for -- more than one glob-holding component, a glob followed by further
  components, a bracket expression or extglob group (D8 step 2's relaxation), `..` anywhere (step
  4's walk and its `_resolves_elsewhere`-naming refusal), and the entry budget (`_Budget` has no
  `_glob_links` hook yet) -- returns `None` from this slice rather than guess, deferred to a
  further one.

  Measured directly against `_decide` first, on this Windows machine, with a real junction (a
  throwaway script in `testbed/scratch/measure_glob_links.py`, gitignored, not committed): `cp n
  <workspace, absolute, forward slashes>/u*/` -- design D8's own R5 example -- was wrongly
  **allowed** today (confirmed live), and is now refused, the reason naming where `up` resolves.
  Confirmed no regression with the same script: `cp n <ws>/sub/*.py` (a match with no link behind
  it) and `cp n <ws>/nomatch*/x` (the glob is not the piece's last component, so this slice does
  not touch it) stay allowed; a relative glob (`cp n u*/x`) is untouched (rule 6, not this slice).
  Mutation-checked: `git stash`ing just `mcp_server.py` and rerunning the test file fails exactly
  the one new test, `test_an_absolute_glob_word_is_also_matched_against_the_links_it_finds`
  (`hub/tests/test_the_shell_judge_reads_a_word_whole.py`), leaving the other 91 rows passing
  unchanged -- confirming its three control assertions are true regression guards, not
  accidentally dependent on this change. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 92 passed (was 91, +1). Broader
  regression set (+`test_permission_approver.py`/`test_hub_own_call.py`/
  `test_copilot_acp_decide.py`/`test_a_write_outside_the_workspace_is_recorded.py`): 718 passed, 2
  skipped, no regressions. `ruff check` and `black --check --target-version py311` on both changed
  files: clean. `git diff --stat`: exactly `hub/hub/mcp_server.py` and the one test file, plus this
  file.

  **Task 2.1c stays unticked**: its own text names the base's real/listed directory tracking, the
  literal-component link test via `os.lstat`, and `..` moving to the real parent -- none of which
  this slice builds, since it excludes `..` and multi-component pieces entirely. The link-detection
  rows of 1.4c that need a bracket expression or a relative word (`cp n [u]p/x`, `ls sub/[a]`, `cp n
  u*/` relative) still do not pass; only the one absolute, bracket-free, `..`-free row above does.

  **Iteration 20 (a second slice: D8 step 2's bracket relaxation).** Re-derived step 2's bracket
  rule from the design text again, not iteration 19's own reading, before building: `fnmatch` reads
  a bracket expression differently from the shell only when it opens with `!` or `^`, or holds a
  `[`, a `\` or a backtick; such an expression is relaxed to `?` (the widest reading that is still
  one character), every other bracket expression is matched exactly, and a `[` with no closing `]`
  is a literal character to both. Built `_bracket_expression_end` (finds the closing `]` as bash
  does, past an optional leading `!`/`^` and a `]` directly after that, with `[:`, `[=`, `[.`
  classes read as their own sub-brackets) and `_relax_bracket_pattern` (walks the pattern, relaxing
  each bracket expression it finds per the rule above, passing everything else through unchanged)
  in `hub/hub/mcp_server.py`, and wired the result into `_glob_links`'s existing match loop in
  place of the raw pattern. The one line the old exclusion needed changing: `pattern`'s
  glob-character check now reads `_GLOB_CHARS` (`*?[`) instead of `*?` only, so a pattern holding
  only a bracket expression (`[u]p`, with no `*`/`?`) is no longer skipped before reaching the
  match loop.

  Measured directly against `_decide` first, on this Windows machine, with the same real junction
  (`testbed/scratch/measure_glob_links.py`, gitignored, not committed, extended with five more
  rows): against an absolute word whose piece's last component is a bracket pattern (trailing `/`,
  so the bracket is the last component, not followed by further ones -- this slice's own scope),
  `[u]p/` (exact match) and the three relaxed forms `[^a]p/` (bash negation), `[!a]p/`
  (PowerShell's literal `!`) and `[[:alpha:]]p/` (a POSIX class `fnmatch` has no notion of) were all
  wrongly **allowed** today against the real junction `up`, confirmed live, and are now refused,
  each reason naming where `up` resolves. Confirmed no regression: `[0-9]/` (an exact bracket that
  matches no one-character name in the fixture) stays allowed, R8's own worked example. Added one
  standalone test,
  `test_an_absolute_glob_word_s_bracket_expression_is_relaxed_like_the_shell_reads_it`, to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py` (needs the fixture's own absolute path and
  a real junction, so not a `_TABLE` row, same reasoning as iteration 19's test next to it).
  Mutation-checked: `git stash`ing just `mcp_server.py` and rerunning the test file fails exactly
  this one new test (on its first assertion, the exact-match row), leaving the other 92 rows
  passing unchanged. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`:
  93 passed (was 92, +1). Broader regression set
  (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 719 passed, 2 skipped, no regressions.
  `ruff check` and `black --check --target-version py311` on both changed files: clean. `git diff
  --stat`: exactly `hub/hub/mcp_server.py` and the one test file, plus this task file.

  **Task 2.1c still stays unticked**, and so does 2.1d (below): this slice only reaches an
  *absolute* word (rule 5's own wiring from iteration 19), so the 1.4c/1.4e bracket rows that are
  relative words (`cp n [u]p/x`, `ls sub/[a]`, `cp n ./u[p]`) still do not pass -- they need rule
  6's piece reading rewritten to call `_glob_links` too (task 2.2), which this change has not
  reached. `..` and multi-component pieces are still excluded exactly as iteration 19 left them;
  an extglob group is still not detected as a glob character at all (it has no `*`, `?` or `[`), so
  `bash -O extglob -c 'cp n @(u)p/x'` (1.4c's own extglob row) is untouched by this slice too.

  **Queued next:** D8 step 4's multi-component walk (carrying each branch's real and listed
  directory, a literal component's link test via `os.lstat`, moving on `..` and judging where it
  lands, the entry budget hook `_Budget` still has no `_glob_links` hook for) is what the rest of
  1.4c, 1.4d and 1.4f need, and is the natural next slice once it can be sized down the same way
  this one and iteration 19's were -- re-derive D8 step 4 from the design text again rather than
  trusting this note, since it is the largest remaining piece of D8 (real/listed path tracking
  across descent, the `..`-after-a-link refusal naming where it lands via `_resolves_elsewhere`,
  and the budget charge per listing). Task 2.2's rule-6 rewiring of `_glob_links` onto relative
  globs is independent of step 4 and could be sized as its own slice first if step 4 proves too
  large again.

  **Iteration 21 (the entry budget hook, independent of step 4's walk).** D8 step 4's own text
  names "the budget charge per listing" as part of the multi-component walk, but re-reading "The
  bounds" section directly shows the charge belongs to step 2's listing in general, not to the walk
  specifically: "`_glob_links` charges the budget as each directory entry is read from `os.scandir`
  and stops reading at the bound. It does not list a directory first and count it after." That is
  true of the single-level `_glob_links` already built (iterations 19-20) regardless of whether the
  multi-component walk exists yet, so it was sized out as its own slice. Before this iteration,
  `_glob_links` had no `budget` parameter at all: `os.scandir`'s listing was read in full into a
  Python list (`entries = list(listing)`) before anything was matched, so a directory with more
  entries than `_GLOB_ENTRY_BUDGET` (8192, the design's own bound, which did not exist as a constant
  either) could be enumerated and held in memory with no check and no bound -- the budget table's
  "Directory entries examined by `_glob_links`" row named a bound that nothing enforced.

  Added `_GLOB_ENTRY_BUDGET = 8192` beside `_BRACE_ARGUMENT_BUDGET`/`_BRACE_TOTAL_BUDGET`, and
  `_Budget.glob_entries_examined` (an `int`, starting at 0, alongside `alternatives_spent`).
  `_glob_links` now takes a `budget: "_Budget"` parameter, iterates `os.scandir`'s listing directly
  inside the existing `try`/`except (OSError, ValueError)` (rather than materializing it first),
  charging `budget.glob_entries_examined` for every entry read before matching it, and returns
  `_refuse(shown, _TOO_MANY)` -- the same shared reason `_expand_braces` uses for its own bound --
  the moment the running total passes the bound, stopping the listing mid-iteration rather than
  finishing it. `budget` reaches `_glob_links` by threading it one hop further than it reached
  before: `_judge_word` gained a `budget: "_Budget"` first parameter (matching `_memo_judge_word`'s
  own ordering), and its one call site (`_memo_judge_word`, which already held `budget`) and its own
  one call to `_glob_links` were both updated. `_judge_word` and `_glob_links` have exactly the one
  call site each in `hub/hub/mcp_server.py` (confirmed by grep, not assumed), so no other caller
  needed updating; the CLI (`src/agentweave/`) has no reference to either name.

  The per-pattern listing memo the same "bounds" text also names ("directory listings keyed by the
  resolved directory") was sized back out: its absence only means a directory already listed for
  one glob word may be listed again for a different one (or a different dialect reading of the same
  word), which spends the shared budget sooner, never later -- it cannot turn a refusal into a wrong
  allow, only make a heavy, repeated-glob command hit `_TOO_MANY` sooner than the design's own
  worked example (123 distinct glob words, 44 root entries, 5,412 of 8,192) implies. Documented as
  left to a further slice in `_glob_links`'s own docstring.

  Measured directly against `_decide` first, before writing a test (a throwaway script,
  `testbed/scratch/measure_glob_budget.py`, gitignored, not committed, run three times to check for
  `os.scandir` order-dependence): a workspace root holding 5 direct entries (`sub`, `up`, `in`,
  `a'b`, `a@b`, the shared fixture's own set) globbed with a pattern matching none of them
  (`nomatch*`, so no entry can short-circuit the walk via a link judgement before the bound is
  reached, regardless of listing order) was unbounded before this slice and, with
  `_GLOB_ENTRY_BUDGET` monkeypatched to 2, is now refused with `_TOO_MANY` every time. Added one
  test, `test_the_glob_link_walk_s_entries_are_charged_against_the_decide_budget`, to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py` (not a `_TABLE` row: needs the fixture's
  own workspace and a monkeypatched module constant, same reasoning as the neighbouring budget test
  in `test_the_totality_rows_for_brace_expansion_never_raise_or_hang`). Mutation-checked: `git
  stash`ing just `mcp_server.py` and rerunning the test file fails exactly the one new test, with an
  `AttributeError` on `_GLOB_ENTRY_BUDGET` (the same shape as the existing brace-budget test's own
  documented mutation check), leaving the other 93 rows passing unchanged. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 94 passed (was 93, +1). Broader
  regression set (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 720 passed, 2 skipped, no regressions. `ruff
  check` clean; `black --check --target-version py311` reformatted one line (the new `_glob_links`
  signature collapsed to one line) -- applied, then both files passed `black --check` and the full
  regression set was rerun unchanged (720 passed). `git diff --stat`: exactly `hub/hub/mcp_server.py`
  and the one test file, plus this task file.

  **Task 2.1c still stays unticked**: this slice only hardens the entry budget around the
  single-level `_glob_links` iterations 19-20 already built (rule 5, absolute words, no `..`, one
  glob-holding component). It adds no new matching behaviour -- nothing that was allowed or refused
  before this slice changed, for any row in `_TABLE` or any existing test. D8 step 4's
  multi-component walk (real/listed path tracking, the `..`-after-a-link refusal naming where it
  lands, `os.lstat` for a literal component) is still the largest remaining piece of 2.1c and is
  unaffected by this slice; re-derive it from the design text again before attempting it, sizing
  down further if it still does not fit one iteration, with task 2.2's rule-6 rewiring as the
  fallback slice (now smaller by exactly the budget-threading work this iteration already did, since
  rule 6's own future call to `_glob_links` will need `budget` passed the same way rule 5's does).

  **Iteration 22 (a fourth slice: step 4's literal tail, without `..`).** Re-derived step 4 from
  the design text again rather than trusting iteration 21's note. Step 4 bundles several concerns
  that do not all depend on each other: (a) a glob-holding component need not be the piece's last
  one -- literal components after it are walked too; (b) each branch tracks its real directory
  across descent, separately from its listed path, so a `..` refusal can name where it lands; (c) a
  `..` component moves the branch to the real parent and is judged there. (b) and (c) exist only to
  make (a) correct in the presence of `..`; without `..` anywhere in the piece, the real and listed
  paths never diverge, so (a) stands on its own and was sized out as this iteration's slice, still
  excluding `..` entirely (bails to `None` for it, same as before).

  **The gap found by re-deriving:** before this iteration `_glob_links` required the glob-holding
  component to be the piece's **last** one (`pattern = components[-1]`; any earlier component
  holding a glob character made it bail to `None`, and so did a literal component held in `pattern`
  itself). This is the exact shape of the original regression report's second and third rows (`u?/x`,
  `[u]p/x` -- a glob matching a link, with a literal path component after it) and the task's own
  `not_last` control (`nomatch*/x`, deliberately a non-match so it could not expose this): a glob
  anywhere but last, with any literal tail after it, was not merely unoptimized but entirely
  unreached by `_glob_links`, so a link anywhere in that tail -- in the matched glob entry itself,
  or in a plain literal component after it -- went unjudged and the piece stood allowed by the
  literal reading alone.

  Built: `_glob_links` now finds the piece's **one** glob-holding component at any index (bails to
  `None`, as before, when there is more than one or none); everything before it is still the base,
  resolved by `_physical` as before; everything after it is the new `tail`, a list of literal
  components. For each base entry the relaxed pattern matches: if the entry is itself a link
  (`_is_link_entry`, as before), it is judged by `_judge_path` first (as before); if that does not
  refuse and `tail` is non-empty, the branch continues from the link's `os.path.realpath` (it has
  just been judged inside, so this call resolves the same target `_judge_path` already read). Then,
  for each component in `tail` in order: the branch moves to `<current>/<component>`; a new helper,
  `_is_link_path(path)`, reads whether that is a link by `os.lstat` directly (there is no `DirEntry`
  for a literal component, matching design step 4 R7's own note) -- the two cases `_is_link_entry`
  already reads from a listing, `stat.S_ISLNK` or, on a drive-letter host, the reparse-point
  attribute, with `OSError`/`ValueError` read as "not a link" rather than raised. When it is a link,
  it is judged by `_judge_path` (quoting `shown`, the whole piece, exactly as every other link
  judgement in this function does) and, if inside, followed to its own `realpath` to keep walking;
  when it is not, the branch simply continues from the literal child path, which needs no
  re-resolution -- a non-link child of a real directory is itself real (design, "Why only links are
  resolved"). A `realpath` call that raises (an extremely rare case -- the same path has just been
  proven to resolve, once by `_judge_path`'s own internal `_where`) ends that one branch without
  refusing or raising, per design "What each changed route returns"; the outer `try`/`except
  (OSError, ValueError)` around the whole listing remains as the backstop it already was.

  Measured directly against `_decide` first, before writing a test (a throwaway script,
  `testbed/scratch/measure_glob_tail.py`, gitignored, not committed, built on the shared fixture's
  own shape): `sub/@s*/p`, where the glob `@s*` matches `sub/@s` -- a **plain, non-link** directory
  -- and the literal tail component `p` is itself a link to the fixture's outside target, was
  **allowed** before this slice and is now refused, naming where it resolves. `u*/x`, where the glob
  match `up` is itself the link and `x` is a literal tail after it, was also wrongly allowed before
  (the first slice, iteration 19, only reached this when `x` was absent) and is now refused too.
  Both confirmed by stashing just `mcp_server.py` and rerunning: both revert to allowed. A control,
  `sub/@s*/missing` (the same shape, but the tail component does not exist), stays allowed both
  before and after, as the design's own "a name that does not exist still moves the branch" note
  predicts.

  Added one test, `test_an_absolute_glob_word_s_tail_is_also_walked_through_a_link`, to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py` (not a `_TABLE` row, for the same reason as
  the neighbouring budget test -- needs the fixture's own link shapes). Also corrected a now-stale
  comment on the existing `not_last` control in `test_an_absolute_glob_word_is_also_matched_against
  _the_links_it_finds`: it used to say the glob-not-last case was "left to the walk, not this
  slice"; it is partly built now, and that row (`nomatch*/x`) stays allowed only because it matches
  nothing, not because the shape is out of scope. Mutation-checked: `git stash`ing just
  `mcp_server.py` and rerunning the test file fails exactly the one new test, leaving the other 94
  rows passing unchanged. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py
  -q`: 95 passed (was 94, +1). Broader regression set
  (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 721 passed, 2 skipped, no regressions. `ruff
  check` and `black --check --target-version py311` both clean on the first pass (no reformat
  needed this time). `mypy hub/hub/mcp_server.py`'s one error is the same pre-existing
  `approve_tool_call` return-annotation gap `.claude/rules/mcp-server.md` documents, unrelated to
  this change. `git diff --stat` confirmed only `hub/hub/mcp_server.py`, the one test file, and this
  task file changed.

  **Task 2.1c still stays unticked**: `..` anywhere in the piece still bails the whole function to
  `None` (unchanged), so the dual real/listed path tracking, the `..`-after-a-link refusal naming
  where it lands (`_resolves_elsewhere`), and the globstar-does-not-descend-through-a-link rule are
  still unbuilt -- that is what remains of step 4, and it is the true reason 2.1c cannot tick yet.
  The bash dot rule (step 2) also remains deferred, as iterations 19-21 already noted; nothing in
  this slice needed it. Re-derive the `..` handling from the design text again before building it
  (D8 step 4's bullets on `..`, plus D12's physical-reading precedent in `_physical` itself, which
  already walks a path component-by-component resolving `..` against a tracked "current" location --
  a close structural parallel worth reading before inventing a new shape for `_glob_links`'s own
  branch tracking). Task 2.2's rule-6 rewiring remains the fallback slice if `..` still does not fit
  whole.

  **Iteration 22's own note (now also stale): built, below.** `_glob_links` now tracks `real` and
  `listed` as two paths per branch, as `_physical` does for a single `current` -- they coincide
  until a link is followed, so most of the walk is unchanged; a tail component that is `..` moves
  `real` to its real parent (one confirming `os.path.realpath`, same cost D12's own wording names:
  "one `realpath`, which returns it unchanged") and is judged there with `_judge_resolved(listed,
  real, root)` directly, not through `_judge_path`/`_where` (which would resolve the already-real
  `real` again and find it unchanged, naming nothing) -- `_resolves_elsewhere` can then say where
  the piece as spelled actually lands. A `..` in the *base* (before the glob) already worked, since
  `_physical` (step 1) resolves it physically on its own; only the bail-out was blocking it. Measured
  live first (`testbed/scratch/measure_glob_dotdot.py`, gitignored): `sub/l*/..`, with `sub/l` R6's
  own shallower-than-the-link junction to the workspace root, was wrongly **allowed** before this
  slice (`realpath`'s lexical `..` handling collapses it to `sub` without ever reading the link) and
  is now refused, naming the real parent it lands in. Confirmed by `git stash`ing just
  `mcp_server.py` and rerunning: reverts to allowed. Controls: a `..` after a glob match that is a
  plain (non-link) directory stays allowed (no divergence, nothing to name); the same link as a
  *relative* word (rule 6, task 2.2, not yet wired) stays allowed too, unaffected by this slice.
  Added one test, `test_an_absolute_glob_word_s_tail_dotdot_moves_the_branch_through_a_link`.
  Mutation-checked: stashing just `mcp_server.py` fails exactly that one test, leaving the other 95
  rows unchanged. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 96
  passed (was 95, +1). Broader regression set (+`test_permission_approver.py`/
  `test_hub_own_call.py`/`test_copilot_acp_decide.py`/`test_a_write_outside_the_workspace_is_recorded.py`):
  722 passed, 2 skipped, no regressions. `ruff check` clean; `black --check --target-version py311`
  needed one reformat (the new test's signature line wrap), applied and reverified clean. `mypy
  src/` (the only path CI runs mypy over) stays clean; `.claude/rules/mcp-server.md`'s pre-existing
  `approve_tool_call` gap is in `hub/`, outside that path, unchanged either way. `git diff --stat`
  confirmed only `hub/hub/mcp_server.py`, the one test file, and this task file changed.

  **Task 2.1c still stays unticked, but for a narrower reason now.** The `..` gap this note named is
  closed. What remains is task 2.1c's own checklist line naming "Run 1.4c, 1.4d and 1.4f": 1.4c's
  glob rows reached through an *absolute* word (rule 5) now pass, but its relative-word rows
  (`cp n u*/`, `cp n [u]p/x`, the inner-shell and PowerShell rows) and the globstar-does-not-descend
  rule still need task 2.2 (rule 6's piece reading wired to `_glob_links`) and the bash dot rule
  (step 2), neither built. The globstar rule and the per-pattern listing memo are also still
  unbuilt, as the function's own docstring says. **Task 2.2 (rule-6 rewiring) is the natural next
  slice**: it is independent of what remains here, is explicitly named as this task's own fallback
  across the last several iterations, and unblocks the sibling change's drive-gated relative-word
  rows the same way this task's absolute-word rows already did.

  **Iteration 27's night-window follow-up (re-derived fresh now that task 2.2 is built, before
  building anything).** Measured directly against `_decide` first
  (`testbed/scratch/measure_21c_relative_rows.py`, gitignored, not committed), with the fixture's
  own link shape: with task 2.2 now built, 1.4c's relative-word glob rows all now pass on their
  own, with no further code change -- `cp n u*/`, `cp n u?/x`, `cp n [u]p/x`, the inner-shell row
  (`bash -c 'cp n u*/'`) and the PowerShell row (`Copy-Item n u*/x`) are each refused, naming where
  the match resolves. 1.4f's relative `..`-after-glob-link rows (`cp n sub/l*/..`,
  `ls sub/l*/../x`) also already pass, through the same `_glob_links` tail walk task 2.1c's own
  iteration 22 built. The extglob row (`bash -O extglob -c 'cp n @(u)p/x'`) stays allowed, as
  documented (extglob is not in `_GLOB_CHARS`, so `_glob_links` never sees it as a glob at all --
  left to a further slice, unaffected by this one).

  **A real, previously unnoticed gap found by this measurement, not named by any note above:**
  1.4c's own `ls sub/.*/y` row ("the dot rule") was wrongly **allowed**, through both the relative
  piece reading and, separately measured with an absolute word, rule 5 too. The cause was not the
  bash dot rule step 2 defers (that only widens what matches, safe by design) -- it was an
  interaction between D3's `..`-rewrite and D8's matching that no prior iteration's note
  mentioned: `_rewrite_dotdot_globs` rewrites a dot-leading glob-holding component (`.*`) to the
  literal text `..` before `_judge_path`'s literal check runs, and both `_judge_word` (rule 5) and
  `_judge_piece` (rule 6) then handed that *rewritten* text on to `_glob_links` too, which erased
  the one glob character `_glob_links` needs to find a real entry (`.l`, a link out) through --
  `_glob_links` saw `..` with no glob character left, found no glob-holding component at all, and
  returned `None`. Confirmed by `git stash`ing just `mcp_server.py` and rerunning: both the
  relative and the absolute row revert to allowed.

  Fixed by matching `_glob_links` on the piece/word exactly as written, not on D3's rewrite of it,
  in both call sites: the literal `..` interpretation that rewrite feeds is `_judge_path`'s own
  check, which already runs first and independently, so nothing is lost by leaving `_glob_links`
  the original text. This is safe because `_rewrite_dotdot_globs` only ever rewrites a component
  that already holds a glob character (a glob-free component never satisfies its own `_GLOB_CHARS`
  check), so no base or already-literal-`..` tail component is affected either way -- confirmed by
  rereading `_rewrite_dotdot_globs`'s own condition, not assumed. Added
  `test_a_dot_leading_glob_is_also_matched_against_the_link_it_finds_2_1c` to
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, covering the relative row, the absolute
  row, and a literal-`..`-tail control (unaffected either way). Mutation-checked: `git stash`ing
  just `mcp_server.py` and rerunning the test file fails exactly this one new test, leaving the
  other 100 rows passing unchanged. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 101 passed (was 100, +1). Broader
  regression set (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 727 passed, 2 skipped, no regressions. `ruff
  check` clean; `black --check --target-version py311` clean on both files, no reformat needed;
  `mypy src/` (the only path CI runs mypy over) clean. `git diff --stat`: exactly
  `hub/hub/mcp_server.py`, the one test file, and this task file.

  **Task 2.1c still stays unticked**, but what remains has narrowed further: 1.4c's and 1.4f's
  named rows now all pass (bar the extglob row, explicitly deferred). What is left of 2.1c's own
  checklist line is the globstar-does-not-descend-through-a-link rule (task 1.4d's own row,
  `bash -O globstar -c 'ls sub/**/x'`) and the per-pattern listing memo -- both still unbuilt, as
  `_glob_links`'s own docstring already says, and the true reason 2.1c cannot tick yet. The
  globstar rule is the more load-bearing of the two (task 1.6's link-cycle hang row and 1.4d's own
  test need it); re-derive design D8 step 2's `**` rule and D8 step 4's link-cycle note fresh
  before building it, sizing down further if it does not fit one slice whole.

  **Iteration 29.** Built the globstar rule (see task 1.4d's own iteration-29 note for the
  production change and measurement, and task 1.6's for the link-cycle row it also closes). **Task
  2.1c still stays unticked, but for only one remaining reason now**: the per-pattern listing memo
  ("The bounds": "directory listings keyed by the resolved directory") is still unbuilt. Its
  absence does not threaten correctness (a directory already listed for one word's glob may be
  listed again for a different word's or a deeper `**` level, which only spends budget sooner,
  never later), so it is a genuine, narrow residual rather than a hidden gap -- the next slice to
  build before this task can tick.

  **Iteration 30 (closes 2.1c).** Built the per-pattern listing memo, the one thing left of this
  task's own checklist: `_Budget.list_directory(directory)`, a new method on `_Budget` (the same
  object `expand_braces` already memoizes on), keyed by the directory already resolved real by the
  caller (`_glob_links`'s `_physical`-resolved base, or a non-link branch `_globstar_walk` recurses
  into -- itself real, since a non-link child of a real directory is real). A hit returns the
  memoized `os.DirEntry` list and charges nothing; a miss reads `os.scandir`, charging
  `glob_entries_examined` one entry at a time exactly as the two call sites already did inline, and
  returns a new `_LISTING_TOO_MANY` sentinel (not memoized, since the scan never finished a listing
  to reuse) when that pushes past `_GLOB_ENTRY_BUDGET`; `None` ("cannot be listed") is memoized, a
  deterministic answer for that path. Both `_glob_links`'s single-component match loop and
  `_globstar_walk` now call it instead of opening `os.scandir` themselves, then iterate the
  returned list with the same per-entry matching/judging logic as before, unchanged.

  Measured directly against `_decide` first (a throwaway script, not committed): three absolute
  glob words landing on the same 50-entry directory (`ls .../a*.txt .../b*.txt .../c*.txt`), bound
  tightened to 60 entries. With today's code (`git stash`ing just `mcp_server.py`), the second
  word's scan pushes the running total to 100, over the bound, and the call is wrongly refused as
  `_TOO_MANY` even though the shell would run it fine (one 50-entry directory, read twice, is not
  "more files than can be checked"). With the memo, the second and third words are served from the
  first's listing, examined count stays 50, and the call is allowed, matching the shell. Confirmed
  the reverse holds too: a single `_Budget` is created once per `_decide` call (one listing
  survives across both dialects and both readings of the same command, as the design's own `budget`
  threading already implied, not newly introduced here).

  Added `test_a_second_glob_word_against_the_same_directory_is_served_from_the_listing_memo_2_1c`
  to `test_the_shell_judge_reads_a_word_whole.py`: the fixture's workspace root (5 direct entries),
  bound pinned to 6 so one listing fits but an unmemoized second listing of the same 5 would not,
  two distinct non-matching patterns (`nomatch1*`, `nomatch2*` -- distinct patterns, so a
  per-*pattern* memo, which design D8's own docstring explicitly rejected in favor of per-directory,
  would still list the root twice and refuse) each with a literal tail so only the budget can
  refuse. Mutation-checked (`git stash`ing just `mcp_server.py`): exactly this one new test fails,
  the other 103 rows passing unchanged. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 104 passed (was 103, +1). Broader
  regression set (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 730 passed, 2 skipped, no regressions. `ruff
  check` clean on both files; `black --check --target-version py311` clean, no reformat needed;
  `mypy src/` (the only path CI runs mypy over) clean. `openspec validate
  the-shell-judge-reads-a-word-whole --strict`: valid. `git diff --stat`: exactly
  `hub/hub/mcp_server.py`, the one test file, and this task file.

  **Task 2.1c ticks.** Its own checklist line ("Run 1.4c, 1.4d and 1.4f") and every residual this
  file's own notes have tracked since iteration 16 (the base's real/listed directory tracking, the
  `..`-moves-to-the-real-parent rule, the globstar rule, and now the listing memo) are built and
  verified. Task 1.6 stays separately unticked: the extglob/backslash-run rows, the memo key's
  colon flag (R6), and `approve_tool_call`'s D6 catch remain, none of which this slice touched.
- [x] 2.1d (R6, D11) The bracket-kept word in `_words`, and D3's and D8's reading of a component that opens with a bracket expression. Built before 2.2, for the same reason as 2.1c. Run 1.4c and 1.4e

  **Iteration 18 (partial).** Measured today's `_decide` directly first (not from this file's old
  R6/R7 tables, which predate the current rule-6 rewrite): `cp n [u]p/x` and `cp n [.]./x` are both
  wrongly **allowed** today against a real junction (confirmed live, not assumed). Built the two
  halves that do not need `_glob_links`: `_bracket_kept_word` plus the `_words` wiring (D11 itself --
  a piece whose ordinary trim removed a `[` or `]` also yields the same piece trimmed with the
  brackets left in, when that still holds a `[` with a later `]`), and `_rewrite_dotdot_globs`'s dot
  rule now also accepts a component opening with `[` (D3's half of this task), both over-approximating
  per design's own text ("Git Bash 5.2 does not match a leading dot that way, measured, but older
  bash was not available"). This closes `cp n [.]./x` (task 1.4e's one row that needs no directory
  listing) end to end. It does **not** close the link-detection rows (`cp n [u]p/x`, `cp n ./u[p]`,
  `ls sub/[a]`): the bracket-kept word now reaches rule 5/6 correctly, but without `_glob_links`
  (task 2.1c) nothing yet matches a bracket pattern like `[u]p` against the real directory entry
  `up` to find the link behind it -- `_judge_path` still resolves the literal nonexistent name
  `[u]p` lexically and finds it inside. Confirmed the new words do not regress any control: `ls
  [../x]` stays refused as `'../x'` (the ordinary word, unaffected -- its own bracket-kept word
  `[../x]`'s first component `[..` has no closing `]` within it, so `fnmatch.fnmatchcase` already
  returns False, matching the design's own worked example); `arr[0]`, `x[1:]`,
  `python -c '["a","b"]'` and `ls sub/[ab].py` stay allowed; the separator-less `[u]p`/`u[p]` stay
  allowed (task 1.4f's own note -- the sibling change's drive machinery, not this one, is what would
  refuse them). Added rows 1.4e1-1.4e7 to `_TABLE` and one row to `_DOTDOT_GLOB_REASON_TABLE` in
  `hub/tests/test_the_shell_judge_reads_a_word_whole.py`. Mutation-checked: stashing the production
  fix fails exactly the two 1.4e1 rows (the allow/deny table row and the reason-text row) and leaves
  every other new row passing unchanged, confirming 1.4e2-1.4e7 are true regression guards rather
  than accidentally dependent on this change. `py -3.11 -m pytest
  hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 91 passed (was 83, +8). Broader
  regression set (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 717 passed, 2 skipped, no regressions. ruff
  and black (`--target-version py311`) clean on both changed files; `mypy src/` (the file is under
  `hub/`, outside mypy's CI scope) unaffected. `git diff --stat`: exactly `hub/hub/mcp_server.py` and
  the one test file, plus this task file. **Task 2.1d stays unticked**: its own text also names "D8's
  reading of a component that opens with a bracket expression," which is `_glob_links`'s job once
  2.1c exists, and the link-detection rows of 1.4c/1.4e are not run yet.

  **Iteration 20 note.** `_glob_links` now relaxes a bracket expression (2.1c's iteration-20 slice,
  above), so "D8's reading of a component that opens with a bracket expression" exists -- but only
  for an absolute word (rule 5). The bracket-kept word built here reaches a real link match through
  that path (an absolute `cp n <ws>/[u]p/` now resolves and refuses), but 1.4c/1.4e's own rows are
  relative words, which still reach rule 6's unrewritten piece reading, not `_glob_links`. 2.1d
  stays unticked until task 2.2 wires `_glob_links` into rule 6 too.

  **Iteration 45.** Task 2.2 (R5, rule 6's per-piece `_glob_links` call) was built at iteration 20
  and ticked some time before this window started; re-derived against the current code rather than
  assuming that closed this task automatically. `_judge_piece` now calls `_glob_links` for any
  relative piece `_holds_glob_character` accepts, and `[` is one of `_GLOB_CHARS`, so a bracket-kept
  word from `_words` reaches it the same way an ordinary glob word does. Measured 1.4e's remaining
  rows directly (this iteration's own 1.4e note, above) and 1.4c's bracket rows (`[u]p/x`,
  `'[[:alpha:]]p'/x`, `./u[p]`, all tested in earlier iterations or this one): every row task 2.1d's
  own text names across 1.4c and 1.4e now passes, with no further production change. **Task 2.1d
  ticks.** This is narrower than 1.4c itself, which has its own still-open rows unrelated to the
  bracket-kept word (the Windows-side POSIX-class/drive-letter-colon-split interaction, the absolute
  top-level dot-glob gap, and the bash-dot-rule control gap) -- see 1.4c's own notes for those.
- [x] 2.2 D2-D5 (R5: D3 and `_glob_links` also run in rule 5 on an absolute glob word, and in rule 6 on the whole value as well as each piece; `_words` reports a trimmed trailing `:` for D5; (R8) D2 step 6, the whole value's literal judgement, after the pieces, with a colon-joined option dropped, divided at its colons where `_DRIVE_LETTERS` is true (read at call time), and on POSIX judged whole as well, each through step 5. Run 1.4g):
  - replace rule 6 of `_judge_word` with the piece reading, including D3's extglob units;
  - add `_PIECE_BREAKS`, `_BASH_DEVICES`, `_SCP_ADDRESS_RE` and `_HOST_PORT_RE` beside `_ABSOLUTE_PATH_RE`, with a comment naming this change;
  - (R4) run the address check after rule 2 and before rule 3;
  - allow `_BASH_DEVICES` before rule 5 in bash (on a drive-letter host, only a whole word or a redirect-target piece);
  - keep `_ABSOLUTE_PATH_RE` for `_read_command`'s nesting-depth fallback, and say so in its comment.

  **Iteration 24 note.** Re-derived this task from scratch against the current code before building:
  most of this bullet list turned out to be already built by earlier iterations under other task
  numbers -- `_PIECE_BREAKS_RE`/`_BASH_DEVICES`/`_SCP_ADDRESS_RE`/`_HOST_PORT_RE` all exist, the
  address check already runs between rules 2 and 3, `_BASH_DEVICES` already stands before rule 5 as
  a whole word, and rule 6 is already `_judge_pieces`, the piece reading. What D3's "extglob units"
  phrase in this bullet still named, unbuilt: an unquoted extglob group (`@(..)/x`) was not kept as
  one unit at all, at **two** layers, not just rule 6's. `_lex`'s `_ARGUMENT_ENDS` already ends an
  argument at any bare `(`, `|` or `)` (mimicking a real subshell/pipe) -- so `@(..)/x` was split
  into three separate *arguments* ("@", "..", "/x") before rule 6's own piece reading ever ran,
  which the design text (written assuming the group reaches rule 6 intact) does not address. Built:
  `_lex` now recognises a trigger (`@ ? * + !`) directly followed by `(`, up to its balanced `)`
  (`_extglob_span_at`), and keeps the whole span as literal characters in the current argument
  rather than ending it there (an unbalanced `(` is not a group, and falls through to the ordinary
  `_ARGUMENT_ENDS` handling unaffected). Once the group survives into rule 6 intact, `_judge_pieces_reading`
  now masks `(`, `@` and `|` inside each group (`_mask_extglob_groups`) before splitting at
  `_PIECE_BREAKS_RE`, and restores them (`_restore_extglob_sentinels`) in the surviving piece before
  it is judged -- so the group is not re-fragmented there either. `_rewrite_dotdot_globs` now also
  recognises a component holding a group as `..`-capable (D3's own two-bullet test:
  `_extglob_alternative_begins_with_dot`, or the component with each group read as one `*`,
  `_mask_extglob_as_star`, against the existing `fnmatch` test). Measured live first in real Git
  Bash 5.2.37 with `extglob` on and `globskipdots` off (`testbed/scratch/measure_extglob.sh`,
  gitignored, not committed): `@(..)/x`, `?(..)/x` and `@(.|..)/x` all expand to `../x`. Measured
  against `_decide` next (`testbed/scratch/measure_extglob_decide.py`, gitignored): every
  dotdot-capable row was already refused before this slice too, but each by accident -- the old
  fragmentation isolates a bare `..` as its own argument, caught by rule 4's unrelated
  `cut == ".."` check, or (`@(.*)/y`) isolates a spurious absolute-looking `/y` fragment refused for
  an unrelated reason. Two rows are not just a reason change: `@(a|b)/x` and `sub/@(..)/x` (resolves
  to `sub`'s own parent, genuinely inside) were both wrongly **refused** by the same accidental
  fragmentation before this slice, and are correctly allowed after. Confirmed by stashing just
  `mcp_server.py` and rerunning. Added one test,
  `test_an_unquoted_extglob_group_is_kept_as_one_unit_through_the_lexer_and_rule_6`. Mutation-checked:
  stashing `mcp_server.py` fails exactly that one test, the other 96 unchanged.
  `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 97 passed (was 96,
  +1). Broader regression set
  (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 723 passed, 2 skipped, no regressions. `ruff
  check` and `black --check --target-version py311` clean on both changed files; `mypy src/` (the
  only path CI runs mypy over) clean. `git diff --stat`: exactly `hub/hub/mcp_server.py`, the one
  test file, and this task file. **Task 2.2 stays unticked**: this bullet's own text ("replace rule
  6 ... including D3's extglob units") is now built, but the task's other three bullets (the address
  check, `_BASH_DEVICES`, keeping `_ABSOLUTE_PATH_RE`) were already built under earlier task numbers
  and never checked off here, so the task line as a whole still needs "Run 1.4g" measured and
  recorded before it can tick -- not run this iteration. **D2 step 6 (R8, the whole-value judgement
  after the pieces) is not touched by this slice at all** and remains the largest unbuilt piece of
  this task; `_glob_links` integration for an extglob group ("For D8's matching, each group counts
  as `*`") is also still unbuilt, as the existing 2.1c/2.1d notes already flagged.

  **Iteration 25 note (second slice, D2 step 6, R8).** Re-derived against the current code: the
  value rule 6 should judge whole is the word after its option run (a colon-joined option dropped
  first, else the glued option step 1 already drops), divided at `:` on a drive-letter host
  (keeping each divided segment, never the whole-with-colons reading there -- `ntpath.realpath`
  misreads a component whose second character is `:` as a drive and drops the real workspace
  prefix, measured: `realpath(<ws>\src\a:1)` is `a:1`), and on POSIX judged both whole-with-colons
  and divided. Built `_whole_value` (the value computation) and `_judge_whole_value` (the
  judgement itself, both readings, calling the existing `_judge_piece` for each), wired into
  `_judge_pieces` after its own piece-reading call, for both the quoted and quote-stripped
  readings. No new threading of `budget` was needed: unlike pieces (D8's `_glob_links` for rule 6
  remains unbuilt for both pieces and the whole value, per the note above), the whole value's own
  test row needing a glob (`sub/@s/p/*`, task 1.4g) turns out to need no `_glob_links` match at
  all -- the link sits behind a literal path, and only the trailing component is a glob, so the
  *literal* undivided value already resolves through the link via plain `_judge_path`, exactly as
  1.4g's own text anticipates ("the literal whole value is what refuses"). `_glob_links`
  integration into rule 6 is therefore not blocking this slice, contrary to the previous iteration's
  own sizing note -- it remains a real gap (a link whose *own path* is reached only by expanding a
  glob, e.g. `sub/@s/*/x` where `*` matches `p`), just not one task 1.4g's test list exercises.
  Measured directly against `_decide` first (`testbed/scratch/measure_whole_value.py`, gitignored,
  not committed), then against task 1.4g's own row list one by one, including two from this
  repository's real transcripts (`grep 'ORM\|:2580' f`, `sed -E 's/(:700)/(:697)/g' f`) that would
  be wrongly refused without the drive-letter guard (confirmed by temporarily removing the guard in
  the same scratch session and rerunning). Added one test,
  `test_the_undivided_whole_value_is_judged_too_1_4g`, covering every 1.4g row this machine can run
  (see that task's own tick for the one POSIX-only row it cannot). Mutation-checked: stashing just
  `mcp_server.py` fails exactly that one test, the other 97 unchanged.
  `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 98 passed (was 97,
  +1). Broader regression set
  (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 724 passed, 2 skipped, no regressions.
  `ruff check` clean; `black --check --target-version py311` clean on both changed files; `mypy
  src/` clean. `git diff --stat`: exactly `hub/hub/mcp_server.py`, the one test file, and this task
  file. **Task 2.2 stays unticked**: its other bullets (`_glob_links` in rule 5 and rule 6's
  pieces, the piece-level `_BASH_DEVICES` check threading `dialect` through, "Run 1.4g" now done)
  are a mix of built-elsewhere-unchecked and genuinely unbuilt; task 1.4g itself now ticks (see its
  own note).

  **Iteration 26 note (third slice, the piece-level `_BASH_DEVICES` check, task 1.7d).** Re-derived
  against the current code before building: rule 5's `_glob_links` call was already built
  (iteration 20), but neither of rule 6's two readings called it, and the piece reading had no
  device check at all -- only the whole-word check before rule 5 (line ~1924) did. Measured first
  (`testbed/scratch/measure_bash_devices_piece.py`, gitignored, not committed), against `_decide`
  directly: `sh -c 'ls 2>/dev/null'` -- the quotes keep the outer lexer from splitting at the inner
  `>`, so the whole thing is one outer word, `/dev/null` reaches rule 6 as a piece split off by the
  `>` break, not the whole-word check -- was wrongly **refused** (`'/dev/null' is outside your
  workspace`), exactly task 1.7d's framing. `python -c "open('/dev/null','w')"` (python source
  text, not a redirect) and `python w.py /dev/null` (a clean whole word) already matched the
  task's "PASSES today" / "allowed" claims and needed no change.

  Built `_PIECE_BREAKS_SPLIT_RE`, the same break class as `_PIECE_BREAKS_RE` but capturing, so
  `_judge_pieces_reading`'s split keeps each delimiter next to the piece that followed it --
  needed to tell a redirect-target piece (one directly after a `<`/`>` break) apart from any other
  piece break (D4, R4's own distinction, not previously readable from a plain `.split()`). Threaded
  `dialect` from `_judge_word`'s rule-6 call site through `_judge_pieces` and both of
  `_judge_pieces_reading`'s calls (the quoted and quote-stripped readings). In the bash dialect, a
  piece that is exactly a mapped device name now stands without being judged as a path, when it is
  a redirect target OR the host has no drive letters (POSIX, where `/dev/null` is a real device for
  every program, not only a redirect target) -- D4's own two-way rule, read off `design.md:430-442`
  fresh, not assumed. `_judge_whole_value`/`_judge_piece` were not touched: the undivided-value
  reading of a redirect-glued word (`"2>/dev/null"` read as one literal relative path) already
  resolves *inside* the workspace with no `..` in it, exactly like the existing
  `redirect_glued_to_a_glob` control (`sh -c 'ls 2>&1/x'`, task 1.4g) already proved for a
  non-device redirect target -- confirmed by letting the piece-reading fix run alone and checking
  the whole-value reading never raised a second refusal.

  Added one test, `test_a_redirect_target_piece_names_a_bash_device_1_7d`, covering task 1.7d's
  three named rows plus a control (a piece glued by a non-`<>` break, here `@`, stays refused --
  the exemption is for a redirect target specifically, not any piece that happens to spell a
  device name). Mutation-checked: stashing just `mcp_server.py` fails exactly that one test, the
  other 98 unchanged. `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`:
  99 passed (was 98, +1). Broader regression set
  (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 725 passed, 2 skipped, no regressions.
  `ruff check` clean; `black --check --target-version py311` needed one reformat (the new
  `_judge_pieces_reading` body), applied and reverified clean; `mypy src/` (the only path CI runs
  mypy over) clean. `git diff --stat`: exactly `hub/hub/mcp_server.py`, the one test file, and this
  task file. **Task 1.7d now ticks.** **Task 2.2 stays unticked**: `_glob_links` is still not
  called from either of rule 6's readings (pieces or the whole value) -- the largest remaining
  piece of this task, and the one that needs `budget` threaded all the way down through
  `_judge_pieces`/`_judge_pieces_reading`/`_judge_piece`/`_judge_whole_value`, none of which carry
  it today. That is the natural next slice.

  **Iteration 27 note (fourth slice, closing task 2.2).** Re-derived against the current code
  before building, per `next_action`: of task 2.2's five bullets and its own header parenthetical,
  only "`_glob_links` also run ... in rule 6 on the whole value as well as each piece" was still
  unbuilt (the other four bullets, `_words`' trimmed colon, and the R8/step-6 parenthetical were
  each confirmed already built by iterations 20-25, re-checked rather than trusted). Threaded
  `budget` through `_judge_pieces` -> `_judge_pieces_reading`/`_judge_whole_value` -> `_judge_piece`
  (none of which carried it before this slice), and added the `_glob_links` call **once**, inside
  `_judge_piece` itself: both of rule 6's readings (the piece reading and the whole-value reading,
  D2 step 6) already call `_judge_piece` as their shared per-piece/per-segment primitive, so wiring
  it there reaches both at once rather than needing two separate call sites. The piece is joined to
  `root` first when relative (mirroring `_where`'s own `os.path.isabs(path) else os.path.join(root,
  path)` pattern) -- `_glob_links` otherwise reads a relative piece as rooted at the filesystem root
  or a drive, not the workspace, which would silently never match anything real.

  Measured first (`testbed/scratch/measure_rule6_glob_links.py`, gitignored, not committed),
  against `_decide` directly: with a workspace link `sub/l` -> an outside directory, `cp n
  sub/l*/x` was wrongly **allowed** today (the literal component is `l*`, not `l`, so plain
  `realpath` never follows the link -- only `_glob_links`'s `fnmatch` match against the real
  listing does). Also measured a second gap the piece split itself causes: `@` is a piece break,
  so `sub/@s*/p` reaches the piece reading as `s*/p` (not `@s*/p`), matching nothing in `sub` --
  confirmed (by temporarily monkeypatching `_judge_whole_value` to always return `None` in the same
  scratch session) that only the undivided whole-value reading still holds `@s*` intact and matches
  the fixture's own `sub/@s/p` link; the piece reading alone stands allowed. Both gaps close with
  this one slice, since both readings share `_judge_piece`.

  Two existing tests asserted the old (unbuilt) behaviour by name and needed updating, not just
  leaving to rot: `test_an_absolute_glob_word_is_also_matched_against_the_links_it_finds`'s own
  control ("a relative glob reaches rule 6, which this slice does not touch" -- `cp n u*/x`) and
  `test_an_absolute_glob_word_s_tail_dotdot_moves_the_branch_through_a_link`'s own control ("Stays
  allowed until that task is built" -- `cp n sub/l*/..`) each now assert the refusal this slice
  builds, with the comment rewritten to say why. Added one new test,
  `test_rule_6_also_matches_a_relative_glob_word_against_the_links_it_finds_2_2`, covering: the
  piece-reading refusal (`u*/x`), a matched-but-lands-inside control through the fixture's own
  shallower link (`sub/l*/x`, proving a match is followed rather than refused outright), a no-match
  control (`sub/q*/x`), a no-link control (`sub/*.py`), and the whole-value-only refusal
  (`sub/@s*/p`) -- every row checked against the real fixture shapes with a throwaway script first
  (`testbed/scratch/verify_fixture_shapes.py`, gitignored, not committed) before trusting an
  assertion, since this task's own earlier sizing note had wrongly assumed `sub/l`'s target was
  outside the workspace (it is the workspace root itself, R6's shallower-link shape) and the first
  draft of this test asserted the wrong thing.

  Mutation-checked: stashing just `mcp_server.py` fails exactly the three tests this slice touches
  or adds (the two updated controls, the new test) and no others.
  `py -3.11 -m pytest hub/tests/test_the_shell_judge_reads_a_word_whole.py -q`: 100 passed (was 99,
  +1). Broader regression set
  (+`test_permission_approver.py`/`test_hub_own_call.py`/`test_copilot_acp_decide.py`/
  `test_a_write_outside_the_workspace_is_recorded.py`): 726 passed, 2 skipped, no regressions.
  `ruff check` clean; `black --check --target-version py311` needed one reformat of
  `mcp_server.py` (the new parameter wrapping), applied and reverified clean; `mypy src/` (the only
  path CI runs mypy over) clean. `git diff --stat`: exactly `hub/hub/mcp_server.py`, the one test
  file, and this task file. **Task 2.2 now ticks**: every bullet, the header parenthetical, and
  "Run 1.4g" are each built and verified; this slice closed the one remaining gap.

  Not yet built, left to 2.2a-2.2c below (each already scoped, untouched by this slice) and to the
  sibling tasks that explicitly wait on this wiring: task 1.4f's own rows (the `..`-after-a-
  relative-glob-link walk, which this slice's `_glob_links` call already answers correctly for the
  rows measured above, but 1.4f's own task also needs the junction/`os.path.islink`-false check and
  the named-cost assertions it lists, not yet re-derived against the current code) and task 2.1d
  (the bracket-kept relative word, same wiring, not yet re-measured).
- [ ] 2.2a (R3, R4) The platform-keyed drive exception and the tilde-piece refusal in the piece reading; the level-by-level escape-removed readings, each judged by `_judge_word`, and the `::` not-plain rule before rule 5 (design D2 steps 3 and 5, D7). Run 1.7b, 1.7c and 1.7d

  **Iteration 54.** Built this task's first part only: the platform-keyed drive exception in the
  piece reading (D2 step 3), as task 1.7's own note above records (`_mask_drive_colons`, wired into
  `_judge_pieces_reading`). Not yet built: the tilde-piece refusal for a drive piece whose text
  after the colon begins with `~` (step 5's second clause -- `_judge_piece` today only checks
  whether the piece itself begins with `~`, not a drive piece's text after the colon), the
  level-by-level escape-removed readings through `_judge_word`, and the `::` not-plain rule before
  rule 5 (D7). Task left unticked; 1.7b and 1.7c (both still named below) were not run this
  iteration and need their own fresh re-derivation once the remaining three parts land -- do not
  assume they now pass just because the drive exception does, each names more than that one piece.
- [ ] 2.2b D6: `approve_tool_call` catches an exception from `_decide`, denies with a reason and reports it; no return annotation
- [ ] 2.2c (R4, D9) Add the `hub-judge-windows` job to `.github/workflows/ci.yml` (`windows-latest`, `working-directory: hub`, the `hub-test` install steps with `-c ../constraints-dev.txt`, `pytest tests/test_permission_approver.py tests/test_the_shell_judge_reads_a_word_whole.py -v --timeout=300 --timeout-method=thread`). Run `py -3.11 -m pytest tests/test_dev_constraints.py -q`. After pushing, confirm the job ran and passed, or do not tick
- [ ] 2.3 Run the eight files named in design D2 plus the new file; expected moves are exactly task 1.8's rows plus the new rows. Record counts
- [ ] 2.4 `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH; record the count, or do not tick
- [ ] 2.5 `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`

## 3. Real shells

- [ ] 3.1 In `testbed/scratch/`, in Git Bash, confirm:
  - `cp notes.md .{,.}/` and `cp notes.md {.,.}.` land in the parent (the refusals are justified), and `mkdir -p src/{a,b}` creates two directories inside;
  - (R4) with a junction `up` pointing outside, `cp n u*/` lands outside;
  - `bash -c 'bash -c "echo .\\./x"'` prints `../x`;
  - (R6) `cp n [u]p/` and `cp n u[p]` land outside through `up`; with a junction `sub/l` → the scratch workspace, `cp n sub/l/../y` and `cp n sub/l*/..` land in the workspace's parent, while PowerShell's `Set-Content sub\l\..\p1 hi` lands in `sub`.
  - (R8) with a junction `sub/@s/p` pointing outside and a directory `a'b` holding a junction `up` pointing outside, `cp n sub/@s/p/x` and `cp n "a'b/up/x"` land outside, and PowerShell's `Copy-Item n -Destination:sub/@s/p/x` too; `cp n "../<workspace>(a"` writes a sibling of the workspace; with a junction `node_modules` pointing to a sibling checkout's `node_modules`, `cp n node_modules/../y` lands in the checkout.

  Record `bash --version`, `shopt globskipdots` and `shopt extglob`. Delete the scratch.

## 4. Close

- [ ] 4.1 F362 and F403 Status lines in `scripts/drive/FINDINGS.md` → `fixed <sha>`; F444 (the linked-dependency-directory finding, filed 2026-09-24 under `B4-dep-links`) left open and noted as a prerequisite for registering a JavaScript project; regenerate the backlog; `openspec validate the-shell-judge-reads-a-word-whole --strict`; archive
