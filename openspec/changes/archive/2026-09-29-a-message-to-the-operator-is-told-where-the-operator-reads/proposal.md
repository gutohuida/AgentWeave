# Proposal — a message to the operator is told where the operator reads

**Round 1, 2026-09-24** (bundle B3, decision D10, F77). Finding **F77 (C)**, re-verified on HEAD
`404c7d5`. **Nothing here is implemented yet.**

## Why

An agent that tries to tell the operator something through `send_message` is refused as if it had
mistyped a peer's name:

```
send_message {"to": "Operator", ...}
  -> 404 "Unknown recipient 'Operator': no agent by that name is registered in this project"
```

(`hub/hub/api/v1/messages.py:94-117`, unchanged since F77 was filed.) The refusal is true and
useless: it does not say whether the operator can be addressed at all, so the agent's next move is to
guess another name. `operator` and `user` are **reserved** — no agent can ever hold them
(`hub/hub/worktrees.py:73-80`, checked case-insensitively at `:148`; restated in
`src/agentweave/constants.py:79`) — so this request is always an attempt to address the person, never
a typo for a peer.

D10 asked whether the operator should be addressable *without a question*. CLAUDE.md fixes the
boundary: operator-in-the-loop has **no backstop**, and the retired trailing-question detector
(migration `0082`) must not return. So the answer cannot be a Hub that reads an agent's prose and
decides it was addressed to a person. It also need not be a new channel: the operator already reads
what an agent writes — its reply is the conversation they open — and a task carries its own record in
`notes`.

**While checking this, a spec drift was found.** `agent-capability-plane` still carries
*"A turn that ends on an unasked question is surfaced to the operator"* and *"The operator can convert
an unasked question into a real one"* (`openspec/specs/agent-capability-plane/spec.md:323-384`). The
code behind both was deleted by migration `0082` (2026-08-20); the table is gone and
`grep -rln unasked hub/hub` finds only that migration history and unrelated uses of the word. The main
spec states, as current behaviour, the backstop CLAUDE.md forbids reintroducing — a later round
reading the spec as authority could rebuild it.

## What Changes

- A message **an agent's run** sends to a recipient that is a reserved name is answered with a
  refusal that says what works (R3: the check sits in `create_message_for_actor`, which the agent and
  operator routes share; the operator's own sends, `by_operator` at `messages.py:62`, keep today's
  answer): *"The operator is not a message recipient. What you write in your reply is what they
  read in this conversation; record a result on a task with update_task's notes; if you need their
  answer before you can continue, call ask_user."* Status stays 404 (the recipient does not exist), and
  the `agent_action_rejected` event records `reason: "operator_not_a_recipient"`.
- `send_message`'s docstring and its `_operations()` row say the operator is not a recipient and name
  the two ways to reach them.
- The two retired requirements are **removed** from `agent-capability-plane`, and the third
  reference to the retired flag (`agent-conversation-workspace/spec.md:803`) is dropped by a
  MODIFIED delta (operator review 2026-09-24: the removal ships in this change).
- No new tool. Nothing detects anything in an agent's text.

## Capabilities

### Modified Capabilities

- `agent-capability-plane` — adds the reserved-recipient requirement; removes the two retired
  backstop requirements.
- `agent-conversation-workspace` — the attention-state requirement stops counting the retired
  unasked-question flag as a reason a conversation waits on the operator (operator review
  2026-09-24).

## Impact

Backend copy in `messages.py`, `mcp_server.py`, `agents.py` (`_operations`); a small public helper in
`worktrees.py` so `messages.py` does not import a private dict (the reserved-name rule itself is not
changed, so its three restatements stay in step). No migration, no UI.
