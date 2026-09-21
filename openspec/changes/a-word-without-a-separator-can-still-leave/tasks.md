## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: an independent re-derivation of the proposal against `hub/hub/mcp_server.py` (`_words`, `_judge_word`, `_where`, `_judge_path`, `_lex`'s NUL decode) and the `agent-run-sandboxing` spec; record in `design.md` `## Round log`
- [ ] 0.2 R3: a second independent re-derivation, which must not start from R2's notes; record it
- [ ] 0.3 The operator answers design Open Question 1 (file D5 and D6 as findings); record the answer in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code

- [ ] 1.1 In `hub/tests/test_permission_approver.py`, add parametrised rows over both dialects that are refused as outside, each naming the word: `cp notes.md ..`, `Copy-Item notes.md ..`, `cp notes.md '..'`, `cp notes.md .""."`, `cp --target-directory=.. notes.md`, `ls ..`, `cd .. && cat notes.md`; run them on today's code and record that each FAILS (allow)
- [ ] 1.2 Add a "judged alike" test: for each dialect, `_decide` on `cp notes.md ..` and on `cp notes.md ../` return the same `allow`; record that it FAILS today
- [ ] 1.3 Add rows refused as uncheckable, where the reason contains `_UNCHECKED` and does not contain `_OUTSIDE`: `cp notes.md ~`, `cp notes.md ~root`, `cp notes.md ~-`, `Copy-Item notes.md ~`; record that each FAILS today
- [ ] 1.4 Flip `_ANSI_C` row P7 (`cp notes.md $'..\x00x'`) to refused as outside, and rewrite its comment to say this change closes it; record that it FAILS today
- [ ] 1.5 Add negative controls that must stay allowed, and record that each PASSES today: `cp notes.md .`, `cp notes.md ...`, `git diff a..b`, `git log HEAD~1`, `ls -la`, `echo a,b`

## 2. The fix

- [ ] 2.1 Change rule 4 of `_judge_word` (`hub/hub/mcp_server.py:1158`) as in design D1: a leading `~` → `_refuse(word, _UNCHECKED)`; a word whose text before its first NUL is `..` → `_judge_path("..", root, word, argument, continues)`; any other separator-less word → `None`. Update the rule-4 comment and the block comment above `_SEPARATORS` if it restates the rule
- [ ] 2.2 Run group 1's rows; every row passes. Record the count inline
- [ ] 2.3 Run the whole of `hub/tests/test_permission_approver.py` plus `hub/tests/test_workspace_writes.py` and `hub/tests/test_codex_posture_ordering.py`; record the counts inline
- [ ] 2.4 Run `py -3.11 -m pytest hub/tests/ -q` (F392 rule 1); record the full-suite count inline, or do not tick
- [ ] 2.5 Run `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`; both clean

## 3. Real shells — the evidence that the rule matches what the shell does

- [ ] 3.1 In a scratch directory (not the repo root, not `testbed/` leftovers), repeat the design's real-landing rows in Git Bash and PowerShell: `cp notes.md ..`, `$'..\x00x'`, `~`; confirm each lands outside, which justifies its refusal. Record the shell versions
- [ ] 3.2 Confirm the negative controls `...`, `'.. '` and `C:` do not land outside in Git Bash; record the result

## 4. Close

- [ ] 4.1 Update F375's Status line in `scripts/drive/FINDINGS.md` to `fixed <sha>`, and regenerate the backlog with `py -3.11 scripts/backlog_page.py`
- [ ] 4.2 `openspec validate a-word-without-a-separator-can-still-leave --strict` passes; then archive with `openspec-archive-change`
