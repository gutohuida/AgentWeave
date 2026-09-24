## 0. Before building

- [ ] 0.1 R2: an independent re-derivation of proposal and design against `hub/hub/mcp_server.py` (`_lex`, `_words`, `_read_command`, `_judge_word`, `_where`, `_judge_path`) and the `agent-run-sandboxing` spec; record it in the bundle record `spec-queue/tracks/B4.md`
- [ ] 0.2 R3: a second independent re-derivation, not starting from R2's notes
- [ ] 0.3 The operator approves the change in `spec-queue/APPROVALS.md` and answers design Open Questions 1 and 2; before `mcp_server.py` is edited, the operator is told that `:8000`'s next run is judged by the edited file, committed or not

## 1. Tests first — each must fail on today's code

- [ ] 1.1 New file `hub/tests/test_the_shell_judge_reads_a_word_whole.py`, using the `workspace` fixture shape of `test_permission_approver.py`: rows allowed after and refused today (each FAILS today): `ls test/*.test.js`, `grep -r foo src/*.py`, `find . -path './src/*' -name x`, `npm install @types/node`, `ls node_modules/@babel/core`, `git show HEAD:src/a.py`, `git log --format=%h/%s`, `printf '%s/%s' a b`, `python -c 'print(1/2)'`, `sed -E 's/(foo)/\1/' f`, `mkdir -p src/{a,b}`, `ls src/?.ts src/[ab].ts`, `gcc -I./include/x a.c`, `ls 2>/dev/null` (Bash), `echo x > /dev/stderr` (Bash), PowerShell `Get-ChildItem src\*.py`
- [ ] 1.2 Brace escapes refused as outside (F403), each FAILS today (allowed): `cp notes.md .{,.}`, `cp notes.md {.,.}.`; and brace escapes that are refused today only by the backstop and must stay refused — `cp notes.md .{,.}/x`, `cp notes.md {.,.}./x`, `cp x src/{a,..}/../y`. The last three PASS today; each FAILS against the rule-6 rewrite built without D1 (record the scratch run: the prototype measured all three allowed). That failure is what makes them evidence for D1
- [ ] 1.3 Braces an inner shell expands (R2): `bash -c 'cp n .{,.}/x'`, `sh -c 'cp n {,..}/x'`, `bash -c "cp x src/{a,..}/../y"` (Bash tool) and `bash -c 'cp n .{,.}/x'` (PowerShell tool) are refused; each PASSES today (backstop `'/x'`) and FAILS against rule 6 rewritten without the inner-shell brace reading. `bash -c 'cp n .{,.}'` is refused and FAILS today (allowed). Quoted braces with no escape in them stand: `awk '{print $1, $2}' f`, `jq '{a: .x, b: .y}' f`, `sed 's/a{2}/b/' f` allowed. `${HOME}` inside a word is not a brace pattern (`echo hi > ${X}/y` stays refused as uncheckable). The literal `cp notes.md '.{,.}'/x` is now refused (the accepted cost). Record today's answer for each
- [ ] 1.4 Glob parents (D3): `ls .*/x`, `ls ..*/x`, `cp x .[.]/y`, `ls ../*`, `rm -rf ../*.py`, PowerShell `Get-ChildItem ..\*` are refused, each quoting the whole piece (`'.*/x'`, `'../*'`); `ls sub/.*/x` and `cp x sub/..?/y` are allowed. The refused rows PASS today with a fragment reason and FAIL on the reason assertion (they must name the whole piece)
- [ ] 1.5 Network (D5): `git clone git@github.com:o/r.git` and `curl -s 127.0.0.1:9/x` are refused with the network reason naming the whole word; `docker run -p 8080:80 img` and `docker run -v data:/app img` keep today's answers (allow; deny `'/app'`). Record: the first two FAIL today on the reason
- [ ] 1.6 Totality: `_decide` answers (never raises) for `Bash` commands made of `{` × 5000, a single-quoted `{` × 5000 (the inner-shell reading), 20 arguments of 100 alternatives each (refused by the per-command bound), `{a,` × 2000, `a{1..99999999}`, `[[[[.*`, `.[`, and a 300-alternative brace pattern (refused with the new too-many reason). Letter ranges expand in full: on Windows `cp x {Z..a}..` is refused (its backslash alternative) and `ls {a..c}` allowed. `approve_tool_call` with `_decide` monkeypatched to raise returns a deny whose message names the failure, and reports it (design D6). Run on POSIX-path CI too (the NUL row X8 stays refused)
- [ ] 1.7 Negative controls that must stay refused, each PASSES today: `curl -o/tmp/x $HUB_URL/api`, `curl -F file=@/etc/passwd x`, `tar -xvf/tmp/a.tar`, `ls a(b/../../x`, `cp x @../y`, `sh -c 'cat</etc/passwd'`, `sh -c "echo hi>../x"`, `python -c "open('/etc/x','w')"`, `node -e "require('fs').writeFileSync('../x','')"`, `scp a host:/x`, `cat /dev/tcp/1.2.3.4/80`, PowerShell `echo hi > /dev/null`, and (Windows only, `<other>` a drive letter that is not the workspace's) PowerShell `Copy-Item x <other>:foo\bar` and `Copy-Item x -Destination:<other>:foo\bar` (R2: the `:` break without the drive exception allows both). Each names the implementation it catches in a comment (a break removed; the quote-removed reading dropped; D4 applied to PowerShell)
- [ ] 1.8 In `hub/tests/test_permission_approver.py`, move rows X4, X5 and X6 out of "Residuals" to allowed, and change the expected reasons of N5 and N6 to `_NETWORK`, G3 to `_outside("../include")`, E11 to `_outside("../stray.txt")`, Z1 and Z2 to the whole traversal; rewrite their comments to name this change; record that each FAILS today

## 2. The fix

- [ ] 2.1 D1 first: sentinels in `_lex` for bash, `_expand_braces`, `_TOO_MANY_BRACES`, and `_read_command` judging each alternative's words. Run 1.2 and 1.3
- [ ] 2.1b The inner-shell brace reading and the per-command bound (design D1, R2). Run 1.3 and 1.6
- [ ] 2.2 D2-D5: replace rule 6 of `_judge_word` (`hub/hub/mcp_server.py:1261-1267`) with the piece reading; add `_PIECE_BREAKS`, `_BASH_DEVICES`, `_SCP_ADDRESS_RE`, `_HOST_PORT_RE` beside `_ABSOLUTE_PATH_RE` with a comment naming this change; allow `_BASH_DEVICES` before rule 5 in bash. Keep `_ABSOLUTE_PATH_RE` for `_read_command`'s nesting-depth fallback (`:1514-1520`), and say so in its comment
- [ ] 2.2b D6: `approve_tool_call` catches an exception from `_decide`, denies with a reason and reports it; no return annotation
- [ ] 2.3 Run the eight files named in design D2 plus the new file; expected moves are exactly task 1.8's rows plus the new rows. Record counts
- [ ] 2.4 `py -3.11 -m pytest hub/tests/ -q` with `claude` stripped from PATH; record the count, or do not tick
- [ ] 2.5 `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`

## 3. Real shells

- [ ] 3.1 In a scratch directory, Git Bash: confirm `cp notes.md .{,.}/` and `cp notes.md {.,.}.` land in the parent (refusals justified) and `mkdir -p src/{a,b}` creates two directories inside; record `bash --version` and `shopt globskipdots`

## 4. Close

- [ ] 4.1 F362 and F403 Status lines in `scripts/drive/FINDINGS.md` → `fixed <sha>`; regenerate the backlog; `openspec validate the-shell-judge-reads-a-word-whole --strict`; archive
