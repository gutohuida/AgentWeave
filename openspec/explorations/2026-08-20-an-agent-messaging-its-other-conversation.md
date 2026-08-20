# Exploration — An agent messaging its other conversation (2026-08-20)

**Status:** Stub. One of eight explore pages opened 2026-08-20 covering the open backlog. Nothing
decided.

**Origin:** item 10 of the operator's twelve:

> *"An agent should be able to send a message to itself in another conversation."*

---

## This may be mostly built already

`send_message` (`hub/hub/mcp_server.py:174`) already takes both parameters this needs:

```
to_agent: str
conversation_id: Optional[str] = None
```

and documents `conversation_id` as *"Which of the recipient's conversations to send into. Leave
unset to use their most recent one, or to start a new one if they have none."*

**No self-send guard was found** in `mcp_server.py`, `api/v1/messages.py` or `messages.py` — a grep
for the obvious shapes returned nothing. So `to_agent = <my own name>` with an explicit
`conversation_id` may already do what the operator asked, or may fail somewhere further down.

**First job of this exploration: try it.** One live call decides whether this item is a feature, a
bug, or already done and undiscoverable.

## If it works, the real problem is discoverability

`send_message`'s docstring says *"Exact name of a registered agent in this project, as listed in your
context."* An agent reading that has no reason to think its own name qualifies, and no way to learn
its other conversations' ids — the canonical turn context would have to carry them.

That makes the likely deliverable **documentation plus context**, not a new endpoint.

## Open questions

1. **Does it work today?** Try it before anything else.
2. **How does an agent learn its own conversation ids?** Without them, `conversation_id` is
   unusable for this case. Does the canonical context carry them, and should it?
3. **What is this actually *for*?** Worth asking the operator. Plausible uses — leaving a note for a
   long-running thread, handing findings from an exploration conversation to an implementation one,
   waking a conversation on a schedule — pull in different directions.
4. **Does a self-message trigger a run?** `send_message` delivers into a *durable inbound queue*. An
   agent messaging itself could spawn a turn that messages itself again. `hop_budget` (6) and
   `turn_delivery_cap` (10) exist on the project and may already bound this — worth confirming that
   they apply to a self-loop and not just to agent-to-agent hops.
5. **Should it be visibly attributed differently?** A message from yourself reading like a message
   from a peer is confusing in the transcript.
6. **Overlap with `submit_checkpoint_notes` and `recall`** — both already exist for an agent leaving
   information for its later self. Does this item duplicate them, or is the point specifically
   *another conversation*?

## Size

Possibly zero code. Most likely a documentation change plus surfacing conversation ids in context.
Only large if question 4 turns up an unbounded self-trigger loop, which would be worth knowing about
regardless of this feature.
