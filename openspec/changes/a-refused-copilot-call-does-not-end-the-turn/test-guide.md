# Test guide — A refused Copilot call does not end the turn

## Agent-verifiable

1. **The stop reason is kept** (tasks 1.1, 1.11, 2.A). `pytest
   hub/tests/test_copilot_acp_refusal_continuation.py::test_the_stop_reason_is_on_the_outcome
   hub/tests/test_failure_reporting.py -q`. The outcome and the `run_completed` payload carry
   `stop_reason`, and a Codex-shaped outcome adds nothing.
2. **A judge refusal is continued once, with its reason** (1.2, 2.B, 2.C). The second
   `session/prompt` in the fake's `sent_requests` names the refused call and the judge's reason, and
   the continuation's text reaches the output.
3. **An operator Deny** (1.3), as `wpc1-b` decided.
4. **Controls stay green** (1.4, 1.5, 1.6): a subagent refusal, a refusal followed by text, and
   Stop or `cancelled` send no continuation.
5. **The bound and the visible fall-through** (1.7, 1.8, 2.D). Never a third prompt;
   `copilot.turn_ended_on_refusal` is emitted when nothing more is sent.
6. **Raise handling** (1.9, 1.10, 1.14, 1.15, design D7). A failed or timed-out continuation leaves
   `completed` and force-closes the session. A quota error or a root `session.error` still fails
   the turn. A Stop just before the result gives `interrupted` with no continuation. A cancelled
   task propagates `CancelledError`. `mapper.finish()` runs once on every returning path.
7. **Accounting** (1.13, a control). `pytest hub/tests/test_copilot_usage.py -q`. The later prompt
   result is kept, not added to the earlier one.
8. **Pinned tests** (1.12, 2.E.1). `pytest hub/tests/test_copilot_acp_run_turn.py
   hub/tests/test_copilot_acp_decide.py -q` is green. Each updated test scripts a real continuation
   response; none had an assertion removed.
9. **Whole suite and spec**: `pytest hub/tests/ -q`, `ruff check hub/`, `black --check hub/hub/
   hub/tests/`, and `npx openspec validate a-refused-copilot-call-does-not-end-the-turn --strict`.

## Human-only

1. **A real Copilot turn on the trial Hub `:8010`** (3.1), never `:8000`. A judge refusal of
   `Get-ChildItem 'C:\Python*'` is followed by a `copilot.refusal_continued` row and agent text that
   takes another route or asks. Check in the drive DB that the run's `run_completed` payload has
   `stop_reason`.
2. **An operator Deny on a manual card** (3.2). It reads as the operator expects under the
   `wpc1-b` answer. Judge whether the continuation's wording ("The operator did not approve …") is
      right in the timeline.
3. **Cost** (3.1). Compare the turn's premium requests in the Hub against Copilot's
   `session.usage_checkpoint`. A continuation should cost one more request times the multiplier,
      and appear once. Also compare the continuation's prompt-result `totalTokens` with the turn's
      per-call sum: they should agree, which confirms the prompt result is cumulative across two model
      prompts in one process (design D5, R3).
4. **A subagent refusal** (3.3). The parent continues on its own, with no Hub continuation.
5. **A task run** (3.4). Whether the agent continues or not, the operator can tell from the task's
   timeline why the turn ended.
