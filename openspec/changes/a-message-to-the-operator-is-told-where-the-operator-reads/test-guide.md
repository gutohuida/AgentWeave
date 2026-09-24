# Test guide — a message to the operator is told where the operator reads

## Agent-verifiable

1. **The refusal names what works.** Task 1.1 fails today and passes after, for three spellings.
2. **Peers are unaffected.** Control 1.2.
3. **No backstop returns.** No code added by this change reads an agent's final text; `grep -rn
   "unasked" hub/hub` finds nothing new.
4. **The spec matches the code.** After 3.1, `grep -n "unasked" openspec/specs/agent-capability-plane/spec.md openspec/specs/agent-conversation-workspace/spec.md` is empty (the second file added by the operator review, 2026-09-24).

## Human-only

1. In task 4.2's transcript, judge whether the agent, told the operator is not a recipient, did the
   sensible thing (wrote the result in its reply or on the task) rather than guessing another name.
