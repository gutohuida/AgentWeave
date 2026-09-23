## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2: an independent re-derivation of the proposal against `hub/hub/inbound_queue.py` (`format_turn_prompt`), `hub/hub/turn_scheduler.py:408-411`, `hub/hub/api/v1/agent_trigger.py:1074-1115` (notices and prompt assembly), `hub/hub/api/v1/questions.py` (`_batch_delivery_text`), `hub/hub/scheduler.py` (`_compose_loop_briefing` and both job firing sites), `hub/hub/run_divergence.py:262` and `hub/hub/checkpoint_cutover.py:136`, and the `agent-run-sandboxing` spec. R2 checks in particular: whether any Hub notice or divergence text interpolates agent-authored text (design Risks, third bullet); whether a spec document path an agent can choose can carry an at-sign; and whether the tokeniser table still holds (rerun `scripts/drive/d2_0923_at_mention_tokeniser.py`). Record the result in `design.md` `## Round log`. **Done 2026-09-23 (R2-1 to R2-9 in the Round log). The tokeniser rerun gave **41/41 rows match** (exit 0, fresh marker). Scope widened to the one-shot workers (D7), and the D6 trigger moved.**
- [ ] 0.2 R3: a second independent re-derivation, which must not start from R2's notes; record it. `openspec validate an-at-mention-an-agent-wrote-reads-no-file --strict` passes
- [ ] 0.3 The operator answers design Open Questions Q1 (operator-authored job prompts lose expansion) and Q2 (email addresses reach agents with a backslash); record the answers in `spec-queue/DECISIONS.md`

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 In `hub/tests/test_inbound_queue.py`, add a parametrised test over `origin_type` in `agent`, `job`, `checkpoint`, `divergence`, and one unknown origin: an entry whose content is `see @/etc/passwd and a@b.com` reaches `format_turn_prompt`'s output as `see \@/etc/passwd and a\@b.com`. Record that each FAILS today
- [ ] 1.2 Control: an `operator` entry with the same content reaches the output byte-identical, with no backslash and no D6 sentence. Record that it PASSES today
- [ ] 1.3 A mixed turn (an operator entry with `@src/app.py`, then an agent entry with `@../x`): the operator block keeps `@src/app.py` and the agent block reads `\@../x`. The D6 sentence appears once, on the line after the preamble. Record that it FAILS today
- [ ] 1.3a The question echo (D4, D6 as revised in R2): a turn holding only an `operator` entry whose content is `_batch_delivery_text` of a question containing an at-sign gets the D6 sentence once. The same turn built from a question with no at-sign is byte-identical to today. Record that the first FAILS today and the second PASSES
- [ ] 1.4 The D6 sentence contains no literal at-sign. It is absent from a non-operator turn whose content has no at-sign, and from an operator turn whose content has no `\@` (the existing exact-string test `test_scheduled_job_origin_is_typed_and_has_no_origin_agent` must keep passing unchanged). Record both
- [ ] 1.5 Escaping is idempotent in the only sense that matters: content that already contains `\@` becomes `\\@`. Assert it, and assert the character before every at-sign in the output is a backslash (the property D2 relies on). Include U+FEFF, U+3000 and a newline before the at-sign. Record that it FAILS today
- [ ] 1.6 In the questions tests, `_batch_delivery_text` for one question and for a batch of two: an at-sign in `question` is escaped and an at-sign in `answer` is not. Record that it FAILS today
- [ ] 1.7 (D7) `build_worker_command` and `build_title_command`, for `cli` in `claude` and `codex`: a prompt containing `see @/etc/passwd` reaches argv as `see \@/etc/passwd`. Record that each FAILS today
- [ ] 1.8 (D7) Control, which PASSES today and must keep passing: `_GENERATION_PROMPT`, `_PROBE_PROMPT` and `conversation_titles._PROMPT` contain no at-sign, so neutralising a whole worker prompt never alters Hub text
- [ ] 1.9 (D7) `grade_probe`: when the envelope's `files_changed` is `['packages/@scope/x.ts']` and the answer is `['packages/\@scope/x.ts']` (the rendered form after neutralisation), the result is `passed` with no findings. Record that it FAILS today (today it reports one missing and one invented)
- [ ] 1.10 (D7) `build_generation_prompt` contains the rule about writing at-signs without the backslash, and `CHECKPOINT_PROMPT_VERSION == "checkpoint/2"`. Record that it FAILS today

## 2. The fix

- [ ] 2.1 Add `hub/hub/file_mentions.py` with `neutralise_file_mentions(text: str) -> str` (`text.replace("@", "\\@")`) and the D6 sentence as a constant. Add a comment citing design D2 and the U+FEFF row
- [ ] 2.2 `format_turn_prompt`: neutralise `entry.content` unless `entry.origin_type == "operator"` (D3, default-deny). Add the D6 sentence after the preamble line when the composed blocks contain `\@` (D6 as revised in R2)
- [ ] 2.3 `questions.py` `_batch_delivery_text`: neutralise `row.question` at both interpolations (D4)
- [ ] 2.3a (D7) `build_worker_command` and `build_title_command` neutralise the whole `prompt` in both CLI branches. Add the at-sign rule to `_GENERATION_PROMPT` and bump `CHECKPOINT_PROMPT_VERSION` to `checkpoint/2`. In `grade_probe`, map `\@` to `@` in the answers' `files_changed` before `_normalise`
- [ ] 2.4 Run group 1; every row passes. Record the counts inline
- [ ] 2.5 Run `py -3.11 -m pytest hub/tests/ -q` and record the full-suite count inline, or do not tick. Any existing assertion that moves is named and explained; any unexplained move is a defect
- [ ] 2.6 Run `ruff check src/ hub/ tests/` and `black --check --target-version py311 src/ hub/hub/ hub/tests/ tests/`; both are clean

## 3. The CLI — evidence that the rule matches what the harness does

- [ ] 3.1 Rerun `py -3.11 scripts/drive/d2_0923_at_mention_tokeniser.py` on the CLI version installed at build time; record the version and the `N/N match` line. If a row is marked `CHANGED`, stop and re-open D2 before building. Also rerun `py -3.11 scripts/drive/d3_0923_worker_at_mention.py` **before** group 2 lands: both workers `expanded=True` and the system-prompt-file control `expanded=False`, as R2 measured. That probe calls the builders directly, so after group 2 it shows the fix (both workers `False`); record both runs
- [ ] 3.2 Add a note to `scripts/drive/README.md` saying that a `claude` CLI upgrade reruns both probes. Name the two rows D2 depends on (`escaped`, `escaped_twice`) and the system-prompt-file control, which is why the context file is left alone

## 4. Drive — the product, end to end (every real turn binds `claude-haiku-4-5`)

- [ ] 4.1 On a scratch Hub (never `:8000`, never `:8010`'s real projects), with a fresh project in `testbed/scratch/` and two Claude agents A and B in the default "Workspace only" posture: plant a random marker in a file outside B's workspace. Have the operator ask A to `send_message` B a text containing `@<that absolute path>`, and ask B to report any line starting with MARKER. **Before the fix** (or with task 2.2 reverted), record whether B's CLI session transcript has an `"attachment":{"type":"file"` for the marker file. **After the fix**, confirm it has none and that the marker appears nowhere in B's run output
- [ ] 4.2 Positive control on the same Hub: the operator sends B `@<a file inside B's workspace>` from the composer. Confirm the attachment is still made (the picker's contract survives)
- [ ] 4.2a (D7) On the same Hub, have B write an `@<outside path>` into its reply in a conversation, then create a checkpoint for that conversation. Confirm that the checkpoint worker's CLI transcript (under `~/.claude/projects/`, the slug of the worker's temp directory) has no `"attachment":{"type":"file"`, that the stored checkpoint body does not contain the marker, and that the probe status is not `failed` for a reason naming that path
- [ ] 4.3 Record all three in `scripts/drive/FINDINGS.md` under the drive's dated section; tear down the scratch Hub by exact PID and remove the scratch project

## 5. Close

- [ ] 5.1 Update F409's Status line to `fixed <sha>`; regenerate the backlog with `py -3.11 scripts/backlog_page.py`
- [ ] 5.2 `openspec validate an-at-mention-an-agent-wrote-reads-no-file --strict` passes; archive with `openspec-archive-change`
