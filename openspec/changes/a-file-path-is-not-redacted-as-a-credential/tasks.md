## 0. Rounds — no task below may start until R2 and R3 are recorded in design.md's round log

- [x] 0.1 R2 (2026-09-24, recorded in design.md's round log and `spec-queue/tracks/B12.md`): re-derive the proposal independently against `hub/hub/runner_events.py:28-81`, its
  three callers (`runner_events.py:177`, `:206`, `scheduler.py:94`), and
  `openspec/specs/agent-stream-events/spec.md:101-124`. Re-run D2's measurement, including the
  random-base64 residual, and do not trust R1's numbers. Grep `hub/hub` and `hub/ui/src` for
  anything that reads `<redacted>` back.
- [ ] 0.2 R3: a second independent re-derivation. `openspec validate
  a-file-path-is-not-redacted-as-a-credential --strict` passes.
- [ ] 0.3 The operator approves the change in `spec-queue/APPROVALS.md`.

## 1. Tests first — each must fail on today's code unless marked as a control

In `hub/tests/test_operator_is_told_the_truth.py`, beside the F31 and F118 cases:

- [ ] 1.1 `test_a_posix_path_is_not_a_credential`, parametrised over
  `/Users/operator/code/agentweave/hub/main.py`, `src/services/user/repository/handler.py`,
  `/workspace/proj/.agentweave/worktrees/beta/src/app.py` and
  `/home/runner/work/AgentWeave/AgentWeave/hub/hub/scheduler.py`. For each,
  `redact_secrets(p) == p` and `redact_secrets({"file_path": p}) == {"file_path": p}`. Record that
  every case FAILS today (measured output: `<redacted>.py` and `/workspace/proj/.<redacted>.py`).
- [ ] 1.2 `test_a_credential_used_as_a_path_segment_is_still_redacted`: for
  `https://api.example.com/v1/tokens/` + 40 hex characters, the output ends in
  `/v1/tokens/<redacted>` and contains no hex digit run longer than 8. Record that it FAILS today:
  the output is `https://api.example.<redacted>`, which drops the path.
- [ ] 1.3 `test_a_base64_credential_with_slashes_is_still_redacted`: for
  `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`, and for a value with `sk-` or `aw_live_` followed by
  `/`-separated lowercase words (the prefix alternatives must never go through the path
  exemption), the output is `<redacted>`. Control: PASSES today and must keep passing.
- [ ] 1.4 Controls: `test_a_credential_is_still_redacted`, `test_the_hubs_own_vocabulary_survives_redaction`,
  `test_a_task_id_is_not_a_credential`, `test_anchoring_the_prefix_does_not_cost_a_real_key` and
  the two loop-error-summary tests keep passing unchanged. Run them before group 2 and record the
  count.
- [ ] 1.5 **Rewrite the test that pins the defect.**
  `test_the_field_is_read_before_the_payload_is_redacted_and_truncated`
  (`hub/tests/test_write_paths_on_run_events.py:124`) uses
  `/workspace/project/src/services/handler.py` to show that redaction destroys the path. After this
  change that path survives, and `:147-148` would fail. Keep the test's purpose, which is to prove
  that `write_paths` is read before redaction, by using a path that redaction still destroys: a path
  with a 32-character hex segment (`/workspace/project/<32 hex>/app.py`). Assert
  `write_paths == (that path,)` and that the hex segment is absent from `payload["input"]`. Update
  the docstring's F278 bullet to say the path case is fixed and the credential-segment case is
  what remains. The truncation half (`:150-159`) stays as it is.

## 2. The fix

- [ ] 2.1 In `hub/hub/runner_events.py`, name `_SECRET_VALUE_RE`'s catch-all alternative
  `entropy` and drop the outer group, as D1 item 1 describes. Add `_PATH_SEGMENT_RE` and a replacement function
  `_redaction_for(match)` that implements D1. Call `_SECRET_VALUE_RE.sub(_redaction_for, value)` in
  `redact_secrets`. Extend the comment block above the pattern with an F278 paragraph, in the style
  of the F31 and F118 ones, that cites the measurements in D2.
- [ ] 2.2 Update the F278 comment at `runner_events.py:164-167`. The path case is fixed, and
  reading `write_paths` first is still needed for the credential-segment case and for truncation.
- [ ] 2.3 Run the files from group 1 and `hub/tests/test_write_paths_on_run_events.py` with `claude`
  stripped from PATH, then the lint block from CLAUDE.md.

## 3. Verify

- [ ] 3.1 A live run cannot produce a POSIX path on this Windows machine, so a drive on `:8010`
  proves nothing here. Instead, call `tool_use_event` directly with the D2 inputs and paste the
  stored `payload["input"]` into design.md's round log.
- [ ] 3.2 Close F278 in `scripts/drive/FINDINGS.md` with the commit and test names, and regenerate
  the backlog.
