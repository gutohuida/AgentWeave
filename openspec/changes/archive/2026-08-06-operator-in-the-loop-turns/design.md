# Design — operator-in-the-loop turns

## What already exists

Worth stating precisely, because the gap is smaller than it looks in two places and larger in one.

| Piece | State |
|---|---|
| `Question` model, project-scoped, with `blocking` and `answered` | exists |
| `POST /agent-actions/questions`, `GET .../questions/{id}` | exists |
| SSE broadcast on question created / answered | exists |
| `QuestionsPanel`, `QuestionInterruptCard`, `AnswerForm` | exist |
| `ask_user` MCP tool | exists, **returns immediately** |
| Anything that makes an agent wait for an answer | **does not exist** |
| Questions rendered inside a conversation | **does not exist** |
| Escalating a Hub-refused action to the operator | **does not exist** |

So `blocking` is currently a stored boolean that describes an intent nothing implements.

## Decision 1 — blocking happens in the Hub, not in the provider

The obvious route is MCP elicitation: the AgentWeave MCP server calls `ctx.elicit(...)`, the client
prompts, the answer comes back as the tool result. It is what elicitation is for.

**It was measured and it does not work on Codex 0.146.0** — the elicitation is declined rather than
forwarded to the app-server client, with `mcpServerOpenaiFormElicitation` and `experimentalApi`
declared or not. Evidence in `2026-08-06-agent-messaging-delivery/implications-codex-appserver.md`
§9.

**Chosen: the Hub blocks inside the tool call.** `ask_user` does not return until the question is
answered, declined, or the wait expires. The agent is already blocked — it is waiting on a tool
result — so no provider cooperation is required at all.

This is better than the elicitation route in three ways beyond merely working: it is provider-
agnostic, it keeps the question in the Hub's own data model where it is already recorded and
broadcast, and it requires no new UI protocol — the existing answer path resolves the wait.

Its cost is a held connection per waiting question. Mitigations, to be decided at implementation:
the MCP request's own timeout must exceed the Hub's waiting period or the agent will see a transport
error instead of an expiry, and the Hub must not hold a database session for the duration of a wait.

## Decision 2 — escalation is a different mechanism from a question

A question originates with the *agent*, which chose to ask. An escalation originates with the
*provider*, telling the Hub an agent is attempting something; the Hub would refuse, and asks the
operator instead.

They are deliberately not unified:

- A question is durable, project-scoped, and outlives the turn. An escalation is bound to one
  in-flight approval request and is meaningless once that request is answered.
- A question's default on expiry is "unanswered, still visible". An escalation's default is
  **refuse** — the safe answer, and the one that already happens today.
- An escalation must never be answerable late. The provider is blocked on it; answering after the
  turn has moved on is not merely useless, it is wrong.

They share only their presentation: both are "the agent is waiting on you", both appear in the
conversation.

## Decision 3 — the default is always refusal

Every path where the operator does not act resolves to the refusal that would have happened without
this feature. Inaction cannot grant anything. This keeps the feature strictly additive to the
security posture established by `2026-08-06-agent-messaging-delivery`: it can only turn a refusal
into an allowance through a deliberate human act.

For the same reason, allowance is per-action. `_meta.persist: ["session", "always"]` in the Codex
protocol offers to remember a decision; this change does not use it. A standing grant is a different
feature with different risks and belongs to its own change.

## Decision 4 — waiting is a visible agent state

An agent waiting on a person and an agent working look identical today: both are `running`. That is
tolerable when nothing waits on a person and unacceptable once things do — an operator cannot be
expected to answer a question they have no indication exists.

Waiting must be distinguishable in the agent's status, not only inside the conversation, because the
rail is where an operator scanning several agents will notice it.

Whether this is a new status value or a flag alongside `running` is an implementation decision with
migration consequences for existing status consumers. It should be settled before the UI work, not
during it.

## Decision 5 — steering is offered only where it exists

`turn/steer` is Codex app-server. Claude's runner has no established equivalent, and this change does
not add one.

The interface therefore asks the runner whether redirection is supported and offers it only then.
This follows the existing launchability pattern — capability is reported, not assumed — rather than
offering a control that fails for half the roster.

## Risks

- **A blocking question that outlives its turn.** Bounded wait, and an expired question must not be
  deliverable into a turn that has continued.
- **Escalation used as a habit.** If every sandboxed action escalates, the operator clicks allow
  reflexively and the sandbox is theatre. Escalation should be uncommon by construction; if it is
  not, the sandbox is set wrong and that is the thing to fix.
- **Held connections under many waiting agents.** Untested at scale; worth a deliberate limit.
- **Two waiting mechanisms sharing one presentation.** The UI must not let an operator answer an
  escalation as though it were a durable question, or vice versa.
