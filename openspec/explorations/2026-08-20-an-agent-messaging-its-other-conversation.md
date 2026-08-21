# Exploration — An agent messaging its other conversation (2026-08-20)

**Status:** **ANSWERED 2026-08-20 by execution.** It already works, and it is already bounded. What
remains is a discoverability problem, exactly as this stub predicted — see §"Verified" below.

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

## Verified — it is the third one

Run against the route agents actually use (`POST /api/v1/agent-actions/messages`), locked down in
`hub/tests/test_agent_message_routing.py`:

```
   agent `solo`, mid-turn in conv-thinking, sends to `solo` naming conv-building
        ──▶ 201
        ──▶ Message.sender == Message.recipient == "solo"
        ──▶ sent FROM conv-thinking, delivered INTO conv-building
        ──▶ queue entry hop_depth = 1
```

**Nothing was built for this.** There is no self-send guard on the path, and naming a conversation
routes on the conversation rather than on who is asking — so `recipient == sender` is not a special
case, it is the general rule applied to one agent. That is why it works, and also why nobody knew.

**Question 4 answered too: a self-loop cannot run away.** `hop_depth` comes from the sending run's
`turn_depth + 1` with no exemption for a self-send. With `hop_budget = 6`, a run at depth 6 sends
successfully, the entry is created at depth 7 and stays durable, and `schedule_agent` then refuses
with `"hop budget exhausted"`. Refusal happens at delivery rather than at send, so nothing is lost —
the entry is there if the budget is later raised.

**So this item needs no routing work at all.** What it needs is for an agent to be able to *find*
the capability and the conversation ids it requires — which is the same gap as L1/L2, and belongs
with them rather than here.

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
