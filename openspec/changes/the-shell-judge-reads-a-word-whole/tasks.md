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
- [ ] 1.4b (R4, D3 extglob) `bash -O extglob -c 'cp n @(..)/x'` and `bash -O extglob -c 'cp n ?(..)/x'` refused, the reason quoting `'@(..)/x'` / `'?(..)/x'`. Each PASSES today (tail `'/x'`) and FAILS against the R3 design (piece `..)/x`, inside); assert the reason, which FAILS today too. Controls allowed: `grep -E 'a*(b|c)' f`, `grep -E 'x+(y)' f`
- [ ] 1.4c (R4, D8, link fixture) **globs through a link**, refused as outside, the reason naming where the match resolves:
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
- [ ] 1.4e (R6, D11, link fixture) **a bracket at a word's edge**, refused as outside, the reason naming where `up` resolves:
  - `cp n [u]p/` and `cp n ./u[p]` (a trailing `]` the trim removes). Each PASSES today only by the tail (`'/'`, `'/u[p'`), so assert the resolved target, which FAILS today; each FAILS against R5 (allowed).
  - `cp n [.]./x` refused as outside, quoting `'[.]./x'`. PASSES today by the tail `'/x'`, FAILS on the reason assertion and against R5 (the word `.]./x` is inside).
  - PowerShell `Copy-Item n [u]p\x` (Windows) or `[u]p/x` (POSIX): same as the first row.

  Controls: `ls [../x]` stays **refused** as `'../x'` (PASSES today; FAILS if the bracket-kept word replaced the ordinary one instead of adding to it); `echo arr[0] x[1:]`, `python -c '["a","b"]'` and `ls sub/[ab].py` allowed. The separator-less `cp n [u]p` and `cp n u[p]` stay allowed under this change alone; the sibling change's 1.4f refuses them.
- [ ] 1.4f (R6, D12, operator `B4-link-dotdot`, link fixture with `sub/l` → `work`) **a `..` after a link**, refused as outside, the reason naming the workspace's parent:
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
- [ ] 1.4g (R8, design D2 step 6, the third review's HIGH; the shared fixture's `sub/@s/p`, `a'b/up` and `a@b/l`) **the whole value is judged as the path it spells**. Refused, each naming where it resolves:
  - `cp n sub/@s/p/x` (Bash) and PowerShell `Copy-Item n -Destination:sub/@s/p/x`: through a link behind a package scope's `@`, and behind a colon-joined option;
  - `cp n "a'b/up/x"`: through a link behind a quote;
  - `cp n sub/@s/p/*`: the glob's base is the link, and the literal whole value is what refuses (design D8 step 1);
  - `cp n "a@b/l/../y"`: a physical `..` (D12) after a link behind `@`, naming the workspace's parent.

  Each PASSES today only by the tail (`'/@s/p/x'`, `'/up/x'`, `'/@s/p/*'`, `'/l/../y'`), so assert the resolved target, which FAILS today. Each FAILS against R7 as written (allowed: the pieces `sub/`, `s/p/x`, `a`, `b/up/x`, `b/l/../y` are inside, and D8 listed `outside` from an outside base). Measured in Git Bash, the first three wrote into `outside` and the last beside the workspace.

  Also refused, the run-on at a dividing character, quoting the whole value: `cp n "../work(a"` and `mkdir '../work@'` (the fixture's workspace directory is `work`; in the R8 scratch, whose workspace is `ws`, Git Bash's `cp n "../ws(a"` wrote the sibling file `ws(a` and `mkdir '../ws@'` made the sibling directory `ws@`, measured). Each PASSES today by the tail (`'/work(a'`, `'/work@'`), so assert the quoted `'../work(a'` and `'../work@'`, which FAILS today; each FAILS against R7 (the piece `../work` is the workspace).

  POSIX only: a directory `work/t:d` holding a link `up` → `outside`; `cp n t:d/up/x` refused, naming where it resolves (the whole value with its colon). PASSES today by the tail, FAILS against R7. On Windows no name can hold a colon (design D2 step 6; the msys residual is named in design Residuals).

  Controls allowed (the review's measured-nil costs; each must stay allowed with step 6 in place): `git show HEAD:src/a.py`, `git show HEAD~2:src/a.py`, `ls node_modules/@babel/core` (no link), `npm install @types/node`, `python -c 'print(1/2)'`, `sed -E 's/(foo)/\1/' f`, `git log --format=%h/%s`, `grep -E '^(a|b)/c' f`, `rg 'foo(bar)/baz'`, `sh -c 'ls 2>&1/x'` (each refused today by its tail, measured), and `ls lib/Foo::Bar.pm` (allowed today as a plain word; after D7 it reaches rule 6, whose whole value must not refuse it). On the Windows job also `grep 'ORM\|:2580' f` and `sed -E 's/(:700)/(:697)/g' f` (both from this repository's transcripts), which a whole-value reading that kept the colons on Windows would refuse (measured: `ntpath.realpath` reads `|:2580` and `(:700)` as drives; design D2 step 6). Controls refused by their pieces, as under R7: `npm i x@file:../lib` (`'../lib'`), `sh -c "echo hi>../x"` (`'../x'`), `sh -c 'cat</etc/passwd'`.
- [ ] 1.4d (R4, bounds) A directory `big/` of 8193 empty files: `ls big/*` is refused with the too-many reason (FAILS against R3, which allows it). `ls sub/*` is allowed. With `globstar` named (`bash -O globstar -c 'ls sub/**/x'`) a link two levels down (`sub/deep/l` → outside) is refused, and without it the same `ls sub/**/x` is allowed (the named residual; assert it, so a change of mind is visible). R5: the pattern starts at `sub/`, because a top-level `**` matches the fixture's `up` link and would be refused either way
- [x] 1.5 Network (D5), each with the network reason naming the whole word:
  - `git clone git@github.com:o/r.git` and `curl -s 127.0.0.1:9/x` refused. Both FAIL today on the reason.
  - (R4) `git clone git@github.com:repo`, `scp n user@example.com:file` and `scp n root@10.0.0.5:f` refused. Each FAILS today (allowed) and FAILS against R3 (D5 in rule 6 never sees a separator-less word).
  - (R4) Allowed: `docker pull alpine@sha256:abc`, `npm i x@npm:y`, `pnpm add x@workspace:y`, `scp a host:x/y`, `scp n user@myserver:file`. `docker run -p 8080:80 img` stays allowed, and `docker run -v data:/app img` stays refused as `'/app'`.
  - (R4) `npm i x@file:../lib` refused as `'../lib'`, outside.
  - (R5) `scp n user@example.com:` refused with the network reason. FAILS today (allowed, measured) and FAILS against R4 (`_words` trims the colon).
- [ ] 1.6 Totality. `_decide` answers, and never raises, for these `Bash` commands:
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
- [ ] 1.7 Negative controls that must stay refused, each PASSES today:
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
  own "each PASSES today" framing claims for the whole group). This needs D9's `_DRIVE_LETTERS` and
  D2 step 3's platform-keyed drive exception (task 2.2a, not built) before it can be refused. Task
  left unticked; its fourth bullet's rows are not added to `_TABLE` until 2.2a lands.

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
- [ ] 1.7d (R4, D4 on Windows, Windows job) `python -c "open('/dev/null','w')"` refused as a path. PASSES today (tail), and FAILS against R3's D4. `sh -c "ls 2>/dev/null"` and `python w.py /dev/null` are allowed.
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
- [ ] 2.1c (R4) D8 `_glob_links`, built **before** 2.2, because rule 6 without it regresses; (R6) with the base resolved by `_physical`, each branch carrying its real directory, literal components moved into rather than listed, and `..` moving to the real parent and judged (design D8 step 4); (R7) each branch also carries its listed path, so a `..` refusal names where it lands (`_resolves_elsewhere`), a literal component's link test is `os.lstat` (not `os.path.islink`), and `_physical`, `realpath` and `lstat` inside `_glob_links` are wrapped as design "What each changed route returns" says. Run 1.4c, 1.4d and 1.4f
- [ ] 2.1d (R6, D11) The bracket-kept word in `_words`, and D3's and D8's reading of a component that opens with a bracket expression. Built before 2.2, for the same reason as 2.1c. Run 1.4c and 1.4e

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
- [ ] 2.2 D2-D5 (R5: D3 and `_glob_links` also run in rule 5 on an absolute glob word, and in rule 6 on the whole value as well as each piece; `_words` reports a trimmed trailing `:` for D5; (R8) D2 step 6, the whole value's literal judgement, after the pieces, with a colon-joined option dropped, divided at its colons where `_DRIVE_LETTERS` is true (read at call time), and on POSIX judged whole as well, each through step 5. Run 1.4g):
  - replace rule 6 of `_judge_word` with the piece reading, including D3's extglob units;
  - add `_PIECE_BREAKS`, `_BASH_DEVICES`, `_SCP_ADDRESS_RE` and `_HOST_PORT_RE` beside `_ABSOLUTE_PATH_RE`, with a comment naming this change;
  - (R4) run the address check after rule 2 and before rule 3;
  - allow `_BASH_DEVICES` before rule 5 in bash (on a drive-letter host, only a whole word or a redirect-target piece);
  - keep `_ABSOLUTE_PATH_RE` for `_read_command`'s nesting-depth fallback, and say so in its comment.
- [ ] 2.2a (R3, R4) The platform-keyed drive exception and the tilde-piece refusal in the piece reading; the level-by-level escape-removed readings, each judged by `_judge_word`, and the `::` not-plain rule before rule 5 (design D2 steps 3 and 5, D7). Run 1.7b, 1.7c and 1.7d
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
