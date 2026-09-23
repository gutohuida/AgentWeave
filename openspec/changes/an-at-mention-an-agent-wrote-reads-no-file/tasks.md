## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [ ] 0.1 R2: an independent re-derivation of the proposal against `hub/hub/inbound_queue.py` (`format_turn_prompt`), `hub/hub/turn_scheduler.py:408-411`, `hub/hub/api/v1/agent_trigger.py:1074-1115` (notices and prompt assembly), `hub/hub/api/v1/questions.py` (`_batch_delivery_text`), `hub/hub/scheduler.py` (`_compose_loop_briefing` and both job firing sites), `hub/hub/run_divergence.py:262` and `hub/hub/checkpoint_cutover.py:136`, and the `agent-run-sandboxing` spec. R2 checks in particular: whether any Hub notice or divergence text interpolates agent-authored text (design Risks, third bullet); whether a spec document path an agent can choose can carry an at-sign; and whether the tokeniser table still holds (rerun `scripts/drive/d2_0923_at_mention_tokeniser.py`). Record the result in `design.md` `## Round log`
- [ ] 0.2 R3: a second independent re-derivation, which must not start from R2's notes; record it. `openspec validate an-at-mention-an-agent-wrote-reads-no-file --strict` passes
- [ ] 0.3 The operator answers design Open Questions Q1 (operator-authored job prompts lose expansion) and Q2 (email addresses reach agents with a backslash); record the answers in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 In `hub/tests/test_inbound_queue.py`, add a parametrised test over `origin_type` in `agent`, `job`, `checkpoint`, `divergence`, and one unknown origin: an entry whose content is `see @/etc/passwd and a@b.com` reaches `format_turn_prompt`'s output as `see \@/etc/passwd and a\@b.com`. Record that each FAILS today
- [ ] 1.2 Control: an `operator` entry with the same content reaches the output byte-identical, with no backslash and no D6 sentence. Record that it PASSES today
- [ ] 1.3 A mixed turn (an operator entry with `@src/app.py`, then an agent entry with `@../x`): the operator block keeps `@src/app.py` and the agent block reads `\@../x`. The D6 sentence appears once, on the line after the preamble. Record that it FAILS today
- [ ] 1.4 The D6 sentence contains no literal at-sign, and it is absent from a non-operator turn whose content has no at-sign (the existing exact-string test `test_scheduled_job_origin_is_typed_and_has_no_origin_agent` must keep passing unchanged). Record both
- [ ] 1.5 Escaping is idempotent in the only sense that matters: content that already contains `\@` becomes `\\@`. Assert it, and assert the character before every at-sign in the output is a backslash (the property D2 relies on). Include U+FEFF, U+3000 and a newline before the at-sign. Record that it FAILS today
- [ ] 1.6 In the questions tests, `_batch_delivery_text` for one question and for a batch of two: an at-sign in `question` is escaped and an at-sign in `answer` is not. Record that it FAILS today

## 2. The fix

- [ ] 2.1 Add `neutralise_file_mentions(text: str) -> str` to `hub/hub/inbound_queue.py` (`text.replace("@", "\\@")`), with a comment citing design D2 and the U+FEFF row
- [ ] 2.2 `format_turn_prompt`: neutralise `entry.content` unless `entry.origin_type == "operator"` (D3, default-deny), and add the D6 sentence after the preamble line when any backslash was inserted
- [ ] 2.3 `questions.py` `_batch_delivery_text`: neutralise `row.question` at both interpolations (D4)
- [ ] 2.4 Run group 1; every row passes. Record the counts inline
- [ ] 2.5 Run `py -3.11 -m pytest hub/tests/ -q` and record the full-suite count inline, or do not tick. Any existing assertion that moves is named and explained; any unexplained move is a defect
- [ ] 2.6 Run `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`; both are clean

## 3. The CLI — evidence that the rule matches what the harness does

- [ ] 3.1 Rerun `py -3.11 scripts/drive/d2_0923_at_mention_tokeniser.py` on the CLI version installed at build time; record the version and the `N/N match` line. If a row is marked `CHANGED`, stop and re-open D2 before building
- [ ] 3.2 Add a note to `scripts/drive/README.md` saying that a `claude` CLI upgrade reruns this probe, and naming the two rows D2 depends on (`escaped`, `escaped_twice`)

## 4. Drive — the product, end to end (every real turn binds `claude-haiku-4-5`)

- [ ] 4.1 On a scratch Hub (never `:8000`, never `:8010`'s real projects), with a fresh project in `testbed/scratch/` and two Claude agents A and B in the default "Workspace only" posture: plant a random marker in a file outside B's workspace. Have the operator ask A to `send_message` B a text containing `@<that absolute path>`, and ask B to report any line starting with MARKER. **Before the fix** (or with task 2.2 reverted), record whether B's CLI session transcript has an `"attachment":{"type":"file"` for the marker file. **After the fix**, confirm it has none and that the marker appears nowhere in B's run output
- [ ] 4.2 Positive control on the same Hub: the operator sends B `@<a file inside B's workspace>` from the composer. Confirm the attachment is still made (the picker's contract survives)
- [ ] 4.3 Record both in `scripts/drive/FINDINGS.md` under the drive's dated section; tear down the scratch Hub by exact PID and remove the scratch project

## 5. Close

- [ ] 5.1 Update F409's Status line to `fixed <sha>`; regenerate the backlog with `py -3.11 scripts/backlog_page.py`
- [ ] 5.2 `openspec validate an-at-mention-an-agent-wrote-reads-no-file --strict` passes; archive with `openspec-archive-change`
