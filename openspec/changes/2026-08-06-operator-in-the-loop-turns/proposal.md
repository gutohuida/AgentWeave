# The operator can answer a running agent from the conversation

**Approved:** _pending_

**Status: DEFERRED — do not implement.** Recorded 2026-08-06 by operator decision: not a priority,
and the current batch (`2026-08-06-agent-messaging-delivery` and
`2026-08-06-hub-composer-and-chrome-refinement`) is to be finished first. This document is kept
because the research behind it — in particular the measured elicitation limitation — is expensive to
re-derive and does not go stale quickly. Revisit deliberately; do not pick it up because it is here.

**Depends on:** `2026-08-06-agent-messaging-delivery`. The Codex app-server transport is what makes
most of this possible; without it there is no channel to ask the operator anything mid-turn.

## Why

An agent that cannot ask is an agent that guesses.

The Hub has the *parts* of operator interaction and none of the *interaction*. Today:

- **`ask_user` does not block.** `hub/hub/mcp_server.py`'s `ask_user` posts a question and
  immediately returns `{"success": True, "question_id": ...}`. The agent is expected to poll
  `get_answer` until `answered` flips. Nothing makes the agent wait, nothing makes it poll, and a
  turn that ends before the answer arrives has simply lost the question. The `blocking` field is
  stored and broadcast but nothing blocks on it.
- **Questions are not in the conversation.** `QuestionsPanel` and `QuestionInterruptCard` render on
  `AgentsPage` and `OverviewPage`. An operator reading an agent's conversation — the place they
  actually are when the agent is working — sees nothing.
- **The agent's own limits are invisible.** After `2026-08-06-agent-messaging-delivery`, a sandboxed
  agent that tries to write outside its workspace is silently denied by the Hub. The operator is
  never told it wanted to. The agent hits a wall, works around it or gives up, and the one person
  who could have said "yes, go ahead" never knew.
- **A running turn cannot be redirected.** An operator watching an agent go the wrong way can only
  wait for it to finish, or kill it and lose the context.

The plumbing for the first two is largely built — `Question` model, SSE broadcast, REST endpoints,
answer form, interrupt card. What has never existed is a transport that could carry a mid-turn
request, and a place in the UI where an answer belongs.

## What the app-server transport makes available

Verified against Codex CLI 0.146.0 while investigating
`2026-08-06-agent-messaging-delivery` (see its `implications-codex-appserver.md`):

- `item/commandExecution/requestApproval` — arrives with the command and a human-readable `reason`
  (observed: *"Do you want me to write the requested text to the file outside the sandboxed
  workspace?"*). Today the Hub answers this from policy. It could ask.
- `item/fileChange/requestApproval` and `item/permissions/requestApproval` — same shape, other
  actions.
- `item/tool/requestUserInput` — a tool asking the operator directly.
- `turn/steer` — redirect a turn *already running*, without killing it.
- `turn/interrupt` — stop one cleanly.

**One thing measured as unavailable:** an MCP server's own `ctx.elicit(...)` is declined rather than
forwarded to the client on this Codex version, with or without `mcpServerOpenaiFormElicitation`
declared. So `ask_user` cannot be made blocking *via MCP elicitation*. It can be made blocking by
the Hub simply not returning from the tool call until the answer arrives — which is a Hub-side
decision, works for any provider, and is the route taken here.

## What changes

- **`ask_user` can block.** A blocking question does not return until the operator answers, is
  declined, or the wait times out. Whether a given question blocks stays the agent's choice, as it
  is now.
- **Questions appear in the conversation they came from**, answerable in place, rather than only on
  a separate page.
- **A denied action can be escalated to the operator instead of silently refused.** When an agent
  attempts something its sandbox forbids, the operator can be asked, with the action and the
  agent's stated reason shown, and can allow it once.
- **An answer is attributable and recorded** — who was asked, what they said, when — on the same
  timeline as everything else the run did.
- **A running turn can be steered or interrupted from the conversation.**

## Impact

- **Affected specs:** `agent-tool-surface`, `agent-conversation-workspace`
- **Affected code:** `hub/hub/mcp_server.py`, `hub/hub/api/v1/questions.py`, the app-server client
  from the depended-on change, `hub/ui/src/components/agents/AgentTimeline.tsx`,
  `AgentOutputPanel.tsx`, `components/questions/*`
- **Reference:** t3code's `ComposerPendingApprovalPanel.tsx`,
  `ComposerPendingApprovalActions.tsx`, and `PendingUserInputCard.tsx` solve the same UI problem.

## Risks

- **A blocking question holds a turn open.** Without a bounded wait it holds one forever. The
  timeout is not a detail; it is what keeps a blocking question from being a hang.
- **Escalation weakens the sandbox by design.** That is its purpose, and it is why it must be
  per-action, operator-initiated, and never a standing grant.
- **Not every provider can escalate.** Claude's runner may have no equivalent channel. The feature
  must degrade to today's behaviour rather than appear broken.

## Out of scope

- Any standing "always allow" rule. One answer authorises one action. Persisted approval policy is
  a larger decision and is deliberately not started here.
- Replacing the existing questions pages. They stay; the conversation gains a second, better place.
