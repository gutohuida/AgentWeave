# Test guide — `request_agent` models the new agent on one the operator made

## Agent-verifiable

1. **The capability works at all.** Task 1.1 fails today (every call 400s — F378) and passes after.
2. **No authority is minted.** Task 1.2: the negative assertion on the grant is the one that matters.
   Tasks 1.2a and 1.2c: neither `yolo` nor `hub_client` reaches the new agent, so its first run's
   command has neither `--dangerously-skip-permissions` nor the `acceptEdits` fallback. Task 1.2d:
   a waiting override in `env_vars` is not inherited.
3. **Refusals name a way forward.** Tasks 1.3–1.5.
4. **A queued turn is not reported as a failure.** Task 1.7.
5. **No test depends on `project_sessions`.** `grep -n ProjectSession hub/tests/test_agent_actions_governed.py hub/tests/test_request_agent_models_an_existing_agent.py` is empty.

## Human-only

1. On a trial Hub, the roster shows the requested agent with the template's runner and charter, and
   its settings show every grant off. Decide whether that is the behaviour you want for
   `default_permission_mode` (design D2).
