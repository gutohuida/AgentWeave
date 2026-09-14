# Peer threads that only acknowledge

**2026-09-14, day window, I-1 brief 9 of 11.** This is an improvement brief, not a proposal: there
is no change directory and no tasks. Source: `spec-queue/observations/2026-09-14-LoopEngine.md`,
`## Improvements` item 9, `### What happened` (the build), and `### Architect`'s shape and items 3
and 6.

## What we saw

**Every message wakes its recipient, including one that asks for nothing.**
- **Seven turns that only acknowledged.** Nine of the Architect's 96 turns made no tool call. Two were
  the quota wall. The other seven only acknowledged a peer, in text, and sent nothing back
  (`32be7c52` 18:50, 19:01 and 19:15, `0682583f` 19:59, `8b72ca10` 20:43, `d6e79412` 21:18,
  `4712e387` 04:00).
- **What woke them asked for nothing either.** *Measured for this brief* (`mode=ro`, the queue entry
  each of those runs delivered): two plain acknowledgements from `dev` and `dev_2`, one correction
  of a status `tester` had misreported, and four reports of work done, decided or waiting. They were
  246 to 1,375 characters, at hops 2 to 6. Five asked the Architect for nothing. The correction
  (04:00) asked it to hold an approval, which needs no action. Only `tester`'s 19:01 report ended
  with a suggestion, to link two tasks' prerequisites, and that turn did not act on it.
- **The money is small; the hops are not.** The seven turns cost about $0.35 at API-equivalent
  prices (`turn_usage`, 40–77 k tokens each, nearly all cache reads). But each waking message spent
  a hop in its thread. The 19:15 one arrived at hop 6, so any real message in that thread after it
  would have been at hop 7, past the budget.
- **The budget did cut threads.** From 19:20, 21 peer chains hit the budget at depth 7 and were
  suspended. One was released at 06:10, and the other 20 are still `queued` with an empty
  `waiting_reason` (F361). Eight of those 20 were sent by the Architect. The Architect↔`tester`
  threads were long partly because every evidence decision was routed through `tester` after F357's
  refused approvals.
- **Not measured:** whether any of the 21 suspensions would have been avoided without the
  informational messages ahead of them in the same thread.

## What would change

An agent is told what a message costs, and can send one that informs without waking anyone.
1. **The briefing says it.** A message wakes its recipient and spends one hop of the project's
   budget. A reply that only acknowledges costs the thread a hop and buys nothing. A turn woken by a
   message that asks for nothing may end without replying. A peer turn's prompt already shows each
   entry's hop (`hop N`), and it would also show the budget, so the agent can see how close the
   thread is to the wall.
2. **A message can be sent as a notice.** It is queued like any other and delivered inline at the
   recipient's next turn, but it does not start one. "Merged at 2f13395", "got it", "correction:
   the task is not at revision_needed": all seven waking messages above would have been notices.

## Why it matters

It keeps the hop budget for work. The budget is the product's guard against agents talking in
circles (F5), and it cannot tell a relay of a verdict from a courtesy. Every multi-agent project
with a coordinator will produce these messages, because being polite and reporting status are what
the models do by default. Part 1 costs nothing and would have told the agents that. Part 2 lets
them report without spending anything.

## Rough cost — a code-read estimate

- **Part 1:** the tools section of the canonical context (`hub/hub/api/v1/agents.py:1450-1455`) and
  the delivered prompt's entry header (`hub/hub/inbound_queue.py:98-122`, which renders
  `(hop N)` today). No migration, no API change.
- **Part 2:** the message route always calls `schedule_agent` for the recipient
  (`hub/hub/api/v1/messages.py:305-307`). A notice would skip that call and be picked up by the
  next turn's drain. It needs a value on `Message.type`
  (`MessageType`, `hub/hub/mcp_server.py:36`: `message`, `delegation`, `review`, `discussion`,
  `direct_trigger`), so the tool's argument changes, in `mcp_server.py`, **which F354 keeps out
  today**. `Message.type` is `String(32)` with no CHECK constraint
  (`hub/hub/db/models.py:525`, and `:8000`'s schema read `mode=ro` agrees), so no migration. The
  request schema's allowed values may still need a change.
- **Capabilities:** `agent-conversation-workspace` (the hop budget, `:1610` and `:1641`),
  `agent-tool-surface` (*"Outbound intent remains available"*, `:47`), `agent-capability-plane`.
- **UI:** a notice should look different in the chat timeline. That is small, but it is a bundle.

## Risks and open questions

- **A notice nobody reads.** If the recipient has no other reason to run, a notice waits
  indefinitely. It must be visible on the queue, and perhaps carry an age limit after which it wakes
  anyway.
- **Does a notice spend a hop?** If it does not, two agents could trade notices without limit, but
  since notices wake nobody, no turn would start. It probably keeps its depth, so a reply to it is
  still counted.
- **The operator's messages.** An operator message always wakes. Whether the operator wants a notice
  kind too is a UI question.
- **Part 1 is guidance.** Models acknowledge out of habit, and a sentence may not stop them. Part 2
  is the enforceable half. That is also why Part 1 alone is worth a spec loop: it is free.
- **Order.** After F361, which makes the suspension visible. Otherwise this changes what reaches the
  wall without anyone seeing the wall.

## The decision, in one line

Approve a spec loop for part 1, *the briefing states what a message costs and shows the hop
budget*, buildable without `mcp_server.py`. Hold part 2, *a notice that does not wake*, for a day
after F354.
