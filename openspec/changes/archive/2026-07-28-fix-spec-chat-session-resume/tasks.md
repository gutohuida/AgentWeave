## 1. Fix the trigger call

- [x] 1.1 In `hub/ui/src/components/spec/SpecPage.tsx`, change the `/api/v1/agent/trigger`
  body to send `session_mode: 'resume'` and no `session_id`.
- [x] 1.2 Confirm no other call site in the Spec tab sends `session_mode`.

## 2. Deliberate new session

- [x] 2.1 Add a "new session" control to the Spec tab's agent header, next to the
  agent selector. Keep it compact — the pane is already width-constrained.
- [x] 2.2 Hold a one-shot `startNewSession` flag in component state. When set, the
  next message sends `session_mode: 'new'`.
- [x] 2.3 Clear the flag once the message has been sent, so the following message
  resumes the session that was just created.
- [x] 2.4 Clear the flag when the selected agent changes.

## 3. Session continuity indicator

- [x] 3.1 Indicate in the Spec tab whether the next message continues an existing
  session or starts a new one.
- [x] 3.2 Reflect the pending "new session" state in that indicator.

## 4. Tests

- [x] 4.1 Test: sending a message posts `session_mode: 'resume'` with no `session_id`.
- [x] 4.2 Test: with the new-session flag set, the message posts `session_mode: 'new'`.
- [x] 4.3 Test: the flag is cleared after one message, and the next message posts
  `session_mode: 'resume'`.
- [x] 4.4 Test: changing the selected agent clears the flag.

All in `hub/ui/src/__tests__/specChatSession.test.tsx` (7 tests — 4 above plus three
covering the continuity indicator). Full UI suite: 68 passed. `tsc --noEmit`: clean.

## 5. Manual verification

Run against a live Hub + host watchdog in a separate project (`Specalicious`) with a
kimi agent holding the `spec` role.

Note: the first attempt failed, but not because of this change. Kimi session ids were
never persisted on Windows — `_extract_kimi_code_session` compared a forward-slash
`workDir` from kimi's index against a backslash `str(Path)`, so the fallback had nothing
to resume. Fixed separately in commit `eb06019`; these checks passed afterwards.

- [x] 5.1 Send two messages in the Spec tab; confirm the second reply shows the agent
  retained context from the first.
  Verified: agent was told to remember a nonsense word, recalled it on a later message.
- [x] 5.2 Confirm `.agentweave/agents/<agent>-session.json` is not replaced between
  the two messages.
  Verified: `kimi-session.json` persists a single id, and `~/.kimi-code/session_index.jsonl`
  gained one session across the whole conversation (6 → 7). Before the fix it gained one
  per message.
- [ ] 5.3 Start a new session; confirm the agent has no prior context, and that the
  message after it resumes the new session.
  NOT VERIFIED — the new-session control is covered by unit tests only.
- [ ] 5.4 Repeat 5.1 with a second runner (e.g. codex or opencode) to confirm the
  behaviour is runner-independent.
  NOT VERIFIED — only kimi was exercised. The resolution path is runner-agnostic by
  construction (no runner-specific handling in the UI or the trigger endpoint), but
  that has not been demonstrated on a second runner.
