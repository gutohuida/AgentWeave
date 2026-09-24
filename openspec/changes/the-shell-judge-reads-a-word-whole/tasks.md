## 0. Before building

- [x] 0.1 R2: an independent re-derivation of proposal and design against `hub/hub/mcp_server.py` (`_lex`, `_words`, `_read_command`, `_judge_word`, `_where`, `_judge_path`) and the `agent-run-sandboxing` spec; recorded in `spec-queue/tracks/B4.md`
- [x] 0.2 R3: a second independent re-derivation, not starting from R2's notes
- [x] 0.2b R4 (revise round after the operator's 2026-09-24 review): re-derived from the code at `b7d976a`; recorded in `B4.md` under "R4"
- [x] 0.2c R5: an independent verification round of the R4 design, not starting from R4's notes
- [x] 0.2d R6 (revise round after the second Opus pre-approval review, `spec-queue/tracks/reviews/B4-2026-09-24-second.md`, and the operator's `B4-link-dotdot`): D11, D12, the memo key's colon flag; recorded in `B4.md` under "R6"
- [x] 0.2e R7: one independent comparison round of R6's fixes against the code, as the second review asks before APPROVE WITH FIXES; recorded in `B4.md` under "R7" (D8 step 4: the `..` refusal names where it lands, the literal component's link test is `os.lstat`, raises inside `_glob_links` stated, one named cost)
- [x] 0.2f R8 (the third Opus pre-approval review's fixes, `spec-queue/tracks/reviews/B4-2026-09-24-third.md`; the operator approves after this round): D2 step 6, the whole value judged as the path it spells (between its colons on a drive-letter host); D8 step 1's claim restated; D8 step 2 relaxes only a bracket expression `fnmatch` cannot read; D8 step 4's listed path; D12's cost widened to the shared `node_modules` link; the `workspace_writes.py` docstring task. Measured with real junctions in `testbed/scratch/b4-r8/`; recorded in `B4.md` under "R8"
- [x] 0.3a The operator answers design Open Questions 1 to 4: answered 2026-09-24 afternoon in `spec-queue/DECISIONS.md` (`B4-residuals`: the `case` arm stays, the four device names, this change first and the sibling in the same window; `B4-dep-links`: build as written, residual filed as F444)
- [ ] 0.3 The operator approves the change in `spec-queue/APPROVALS.md` (after the Opus pre-approval review); before `mcp_server.py` is edited, the operator is told that `:8000`'s next run is judged by the edited file, committed or not

## 1. Tests first — each must fail on today's code or on the R3 design as written (each row says which)

Shared fixture, new in `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, shaped like `test_permission_approver.py`'s `workspace`:

- a sibling `outside/` holding `x`;
- a link `work/up` → `outside`, made with `os.symlink` on POSIX and `_winapi.CreateJunction` on Windows (no privilege needed);
- `work/sub/` with `a.py`, `b.py`;
- an inside link `work/in` → `work/sub`;
- (R6) an inside link `work/sub/l` → `work` itself (a link whose target is shallower than the link; D12). It is inside, so every existing control stays allowed: `ls sub/*` matches it and judges it inside, and a `**` walk does not descend through it.
- (R8) a link `work/sub/@s/p` → `outside` (the shape `npm link` makes under a scope), a directory `work/a'b` holding a link `up` → `outside`, and a directory `work/a@b` holding a link `l` → `work`. `@s`, `a'b` and `a@b` are directories inside, not links, so `ls sub/*` and the root globs above are unchanged; `ls sub/**/x` without `globstar` stays allowed (the walk descends the directory `@s`, which holds no `x`, and does not list below it).

- [ ] 1.1 Rows allowed after, refused today (each FAILS today): `ls test/*.test.js`, `grep -r foo src/*.py`, `find . -path './src/*' -name x`, `npm install @types/node`, `ls node_modules/@babel/core` (no link), `git show HEAD:src/a.py`, `git log --format=%h/%s`, `printf '%s/%s' a b`, `python -c 'print(1/2)'`, `sed -E 's/(foo)/\1/' f`, `mkdir -p src/{a,b}`, `ls src/?.ts src/[ab].ts`, `gcc -I./include/x a.c`, `ls 2>/dev/null` (Bash), `echo x > /dev/stderr` (Bash), PowerShell `Get-ChildItem src\*.py`
- [ ] 1.2 Brace escapes refused as outside (F403), each FAILS today (allowed): `cp notes.md .{,.}`, `cp notes.md {.,.}.`. Brace escapes refused today only by the backstop, which must stay refused: `cp notes.md .{,.}/x`, `cp notes.md {.,.}./x`, `cp x src/{a,..}/../y`. The last three PASS today and FAIL against rule 6 rewritten without D1 (R1's prototype measured all three allowed)
- [ ] 1.3 Braces an inner shell expands (R2):
  - Refused: `bash -c 'cp n .{,.}/x'`, `sh -c 'cp n {,..}/x'`, `bash -c "cp x src/{a,..}/../y"` (Bash tool), and `bash -c 'cp n .{,.}/x'` (PowerShell tool). Each PASSES today (backstop `'/x'`) and FAILS against rule 6 without the inner-shell brace reading.
  - `bash -c 'cp n .{,.}'` refused. FAILS today (allowed).
  - Allowed: `awk '{print $1, $2}' f`, `jq '{a: .x, b: .y}' f`, `sed 's/a{2}/b/' f`. (R5, `B4-drive-exists`) Once the sibling change is built, the `jq` row stays allowed on the `hub-judge-windows` job only because drives A and B do not exist there. The sibling's task 1.5c pins that with the drive probe patched; if this row ever fails on Windows, check the runner's drives first.
  - `echo hi > ${X}/y` stays refused as uncheckable.
  - `cp notes.md '.{,.}'/x` is now refused (the accepted cost).
- [ ] 1.4 Glob parents (D3): `ls .*/x`, `ls ..*/x`, `cp x .[.]/y`, `ls ../*`, `rm -rf ../*.py`, PowerShell `Get-ChildItem ..\*` refused, each quoting the whole piece. `ls sub/.*/x`, `cp x sub/..?/y` allowed. The refused rows PASS today with a fragment reason and FAIL on the reason assertion
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
- [ ] 1.5 Network (D5), each with the network reason naming the whole word:
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
- [ ] 1.7 Negative controls that must stay refused, each PASSES today:
  - `curl -o/tmp/x $HUB_URL/api`, `curl -F file=@/etc/passwd x`, `tar -xvf/tmp/a.tar`, `ls a(b/../../x`, `cp x @../y`;
  - `sh -c 'cat</etc/passwd'`, `sh -c "echo hi>../x"`, `python -c "open('/etc/x','w')"`, `node -e "require('fs').writeFileSync('../x','')"`;
  - `scp a host:/x`, `cat /dev/tcp/1.2.3.4/80`, PowerShell `echo hi > /dev/null`;
  - Windows only, with `<other>` a drive letter that is not the workspace's: PowerShell `Copy-Item x <other>:foo\bar` and `Copy-Item x -Destination:<other>:foo\bar`.

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
- [ ] 1.8 In `hub/tests/test_permission_approver.py`, move rows X4, X5 and X6 out of "Residuals" to allowed, and change the expected reasons: N5 and N6 to `_NETWORK`, G3 to `_outside("../include")`, E11 to `_outside("../stray.txt")`, Z1 and Z2 to the whole traversal. Rewrite their comments to name this change, and record that each FAILS today

## 2. The fix

- [ ] 2.0 (R4) `_Budget` and the per-`_decide` memo (design, "The bounds"), created in `_decide` and passed through `_read_command` (both dialects, both readings, nested); (R6) the memo key includes the trimmed-colon flag. `_TOO_MANY`. `_DRIVE_LETTERS` (D9), read at call time by every rule that consults it: no regex, default argument or module constant is built from it at import (the sibling's task 1.5c monkeypatches it)
- [ ] 2.0b (R6, D12) `_physical` and the second reading in `_where`, on a drive-letter host, with the 64-step bound, inside `_where`'s existing `try`. Run 1.4f's literal rows on Windows. This fixes a pre-existing escape and may be built first. (R8, third review) Also correct the `hub/hub/workspace_writes.py` docstring, whose module text (lines 8-10) and `classify` text (lines 172-174) say its `realpath` is "the reason the two agree about a symlink" with `_decide`: after D12, `_decide` also reads a `..` after a link physically on a drive-letter host (a second reading, D12), and `classify` does not, so the two agree about a link named directly and may differ about a `..` after one (`node_modules/../src/x`: `_decide` refuses, on Windows `classify` records `ws/src/x`, inside, which is where Node writes). Comment only; no behaviour of `classify` changes
- [ ] 2.1 D1 first: sentinels in `_lex` for bash, `_expand_braces` (iterative), and `_read_command` judging each alternative's words. Run 1.2 and 1.3
- [ ] 2.1b The inner-shell brace reading (design D1, R2). Run 1.3 and 1.6
- [ ] 2.1c (R4) D8 `_glob_links`, built **before** 2.2, because rule 6 without it regresses; (R6) with the base resolved by `_physical`, each branch carrying its real directory, literal components moved into rather than listed, and `..` moving to the real parent and judged (design D8 step 4); (R7) each branch also carries its listed path, so a `..` refusal names where it lands (`_resolves_elsewhere`), a literal component's link test is `os.lstat` (not `os.path.islink`), and `_physical`, `realpath` and `lstat` inside `_glob_links` are wrapped as design "What each changed route returns" says. Run 1.4c, 1.4d and 1.4f
- [ ] 2.1d (R6, D11) The bracket-kept word in `_words`, and D3's and D8's reading of a component that opens with a bracket expression. Built before 2.2, for the same reason as 2.1c. Run 1.4c and 1.4e
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
