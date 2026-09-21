## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation of the proposal against `hub/hub/mcp_server.py` (`_words`, `_judge_word`, `_where`, `_judge_path`, `_lex`'s NUL decode) and the `agent-run-sandboxing` spec; record in `design.md` `## Round log` — done 2026-09-21: APPROVE WITH FIXES, R2-1 to R2-11 applied in place (the rule widened to option-joined values, D7; three more existing rows flip)
- [ ] 0.2 R3: a second independent re-derivation, which must not start from R2's notes; record it. R3 checks D7 (option-joined values) and D3's quoted-`~` over-refusal in particular
- [ ] 0.3 The operator answers design Open Questions 1, 3 and 4 (file D5, D6 and brace expansion as findings; D7 in scope; superseding archived D9 for rows R8 and R9); record the answers in `spec-queue/DECISIONS.md`
- [ ] 0.4 Before editing `hub/hub/mcp_server.py`, tell the operator: the Hub starts each run's MCP server from this checkout's file, so `:8000`'s next run is judged by the edited rule, committed or not (design R2-7)

## 1. Tests first — each must fail on today's code

- [ ] 1.1 In `hub/tests/test_permission_approver.py`, add parametrised rows over both dialects that are refused as outside, each naming the word: `cp notes.md ..`, `Copy-Item notes.md ..`, `cp notes.md '..'`, `cp notes.md ."".`, `cp notes.md \.\.` (Bash), `cp --target-directory=.. notes.md`, `ls ..`, `cd .. && cat notes.md`; run them on today's code and record that each FAILS (allow). Do not use `.""."`: it is an unbalanced quote bash refuses to parse, and the lexer's run-to-end reading would pass it for a reason unrelated to quote joining (R2-3)
- [ ] 1.2 Add a "judged alike" test: for each dialect, `_decide` on `cp notes.md ..` and on `cp notes.md ../` return the same `allow`; record that it FAILS today. Add a second case with `AW_WORKSPACE_DIR` set to `os.path.abspath(os.sep)` (a filesystem root; `_decide` reads no file, so nothing is created): both commands are allowed. Record that it PASSES today, and that it FAILS against a scratch implementation of rule 4 that returns `_refuse(word, _OUTSIDE)` for `..` instead of calling `_judge_path` (design D2, R2-6); that failure is what makes it evidence
- [ ] 1.3 Add rows refused as uncheckable, where the reason contains "cannot be checked" and not "outside your workspace": `cp notes.md ~`, `cp notes.md ~root`, `cp notes.md ~-`, `cp notes.md ~+`, `Copy-Item notes.md ~`, and PowerShell `Copy-Item notes.md -Destination:~`; record that each FAILS today
- [ ] 1.4 Flip `_ANSI_C` row P7 (`cp notes.md $'..\x00x'`) to refused as outside, and rewrite its comment to say this change closes it; record that it FAILS today
- [ ] 1.5 Add rows for option-joined values refused as outside, each naming the whole word (design D7): Bash `cp -t.. notes.md` (`'-t..'`), Bash and PowerShell `tar -C.. -xf a.tar` (`'-C..'`), PowerShell `Copy-Item notes.md -Destination:..` (`'-Destination:..'`), Bash `cp -t$'..\x00x' notes.md`; record that each FAILS today
- [ ] 1.6 Flip rows R8 (`cd .. && echo hi > stray.txt`) and R9 (`git -C .. status`) of `_TABLE` to `False, _outside("..")`, and add a comment above them saying this change supersedes the archived `a-url-is-not-a-path` D9 for these two rows; record that each FAILS today (R2-1)
- [ ] 1.7 Change H10's expected reason from `_UNCHECKED` to `_outside("..")`, and add a row H10b, `HUB_URL=sub ; cat $HUB_URL/x`, `False, _UNCHECKED`, which carries H10's old job of pinning `_read_command`'s `trusted` guard. Record that H10 FAILS today (wrong reason), that H10b PASSES today, and that H10b FAILS when `trusted` is forced to `True` in a scratch run (R2-1)
- [ ] 1.8 Add negative controls that must stay allowed, and record that each PASSES today. Each one names the wrong implementation it catches: `cp notes.md .` and `cp notes.md ...` (a prefix match on `..`), `git diff a..b` and `git log main..HEAD` (a substring match on `..`), `git log HEAD~1` (a substring match on `~`), `ls -la`, `git log -1` and `cp -t... notes.md` (a glued-option rule that judges more than an exact `..`), Bash `cp -t~ notes.md` (the `~` check applied to a glued short option), PowerShell `Copy-Item notes.md -Destination:sub`, `Get-ChildItem -Filter:*.md` and `Get-ChildItem -Recurse:$true` (a parameter rule that refuses every value), `echo a,b`

## 2. The fix

- [ ] 2.1 Change rule 4 of `_judge_word` (`hub/hub/mcp_server.py:1158`) as in design D1: extract a PowerShell `-Name:` value (PowerShell dialect only) and a glued short-option value (both dialects, `..` only); a value beginning with `~` → `_refuse(word, _UNCHECKED)`; a value whose text before its first NUL is `..` → `_judge_path("..", root, word, argument, continues)`; anything else → `None`. Add `_POWERSHELL_PARAMETER_RE` and `_GLUED_OPTION_RE` beside the other patterns (`:955-981`) with a comment citing D7. Update the rule-4 comment and the block comment above `_SEPARATORS` if it restates the rule
- [ ] 2.2 Run group 1's rows; every row passes. Record the count inline
- [ ] 2.3 Run the whole of `hub/tests/test_permission_approver.py` plus `hub/tests/test_workspace_writes.py` and `hub/tests/test_codex_posture_ordering.py`; record the counts inline. Expected changes against today are exactly P7, R8, R9 and H10 (R2 measured this with the rule patched in: 4 failed, 380 passed across the eight test files that reach the judge); any other change is a defect
- [ ] 2.4 Run `py -3.11 -m pytest hub/tests/ -q` (F392 rule 1); record the full-suite count inline, or do not tick
- [ ] 2.5 Run `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`; both clean

## 3. Real shells — the evidence that the rule matches what the shell does

- [ ] 3.1 In a scratch directory (not the repo root, not `testbed/` leftovers), repeat the design's real-landing rows in Git Bash and PowerShell: `cp notes.md ..`, `$'..\x00x'`, `~`, `cp -t.. notes.md`, `Copy-Item notes.md -Destination:..`; confirm each lands outside, which justifies its refusal. Record the shell versions
- [ ] 3.2 Confirm the negative controls `...`, `'.. '`, `C:` and `cp -t~ notes.md` do not land outside in Git Bash; record the result

## 4. Close

- [ ] 4.1 Update F375's Status line in `scripts/drive/FINDINGS.md` to `fixed <sha>`, and regenerate the backlog with `py -3.11 scripts/backlog_page.py`
- [ ] 4.2 `openspec validate a-word-without-a-separator-can-still-leave --strict` passes; then archive with `openspec-archive-change`
