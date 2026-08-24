# User test guide — the hop budget is a real bound

Task 6.1. What an operator does, what they should see, and what it looks like when it goes wrong.

The suite proves the mechanism: an over-budget entry is not delivered, the depth counter does not
run backwards, Continue re-bases and delivers. What it cannot prove is task 5.1 — whether the held
entry's explanation tells you *what to do* rather than merely what happened. That judgement is
yours, and it is the reason this guide exists.

## Before you start

- The trial Hub on port **8010**, started **from `hub/`** so the source package is what runs:

  ```bash
  cd hub
  DATABASE_URL="sqlite+aiosqlite:///$HOME/.agentweave/hub/profiles/beta/agentweave.db" \
    py -3.11 -m uvicorn hub.main:app --port 8010 --host 127.0.0.1
  ```

  **Not `agentweave --port 8010`.** The console script is the *installed* `agentweave-hub`, whose
  migrations stop short of this branch's head.

- Two agents on the roster that can message each other — the walkthrough below uses `builder` and
  `relay`.
- The project's **hop budget set to 1**, in the queue settings. At the default of 6 you would need
  a seven-deep chain to see any of this.

  ```bash
  curl -X PATCH http://127.0.0.1:8010/api/v1/projects/<project>/queue/settings \
    -H "Authorization: Bearer $AW_KEY" -H "Content-Type: application/json" \
    -d '{"hop_budget": 1, "turn_delivery_cap": 10, "agent_budget": 8, "allow_agent_jobs": true}'
  ```

  **Put it back afterwards.** A budget of 1 stops every two-hop conversation in the project.

## Building a held entry

Ask one agent to message the other and get a reply. That is a two-hop chain, and the reply is the
hop the budget refuses.

```bash
curl -X POST http://127.0.0.1:8010/api/v1/projects/<project>/agent/trigger \
  -H "Authorization: Bearer $AW_KEY" -H "Content-Type: application/json" \
  -d '{"agent": "builder",
       "message": "Send exactly one message to the agent named relay using send_message, with subject \"ping\" and body \"Please reply to me with the single word ACK.\" Then stop."}'
```

Watch it happen:

```bash
AW_HUB=http://127.0.0.1:8010 AW_PROJECT=<project> python scripts/drive/t_hop.py 20
```

You are waiting for `builder` to reach `age@2/queued` and every agent to go idle. That is the held
entry: hop 2, over a budget of 1, and nothing is going to move it.

## What you should see

**In the conversation, an amber panel.** It names who the held entries are from, and what you can
do:

> **Autonomous continuation paused** — 1 entry from relay reached the hop budget. Continue to
> deliver them and restart the count from here, or discard them individually below.

**This is task 5.1.** Read that sentence as an operator who has not read the design. Does it tell
you what to do? It used to say *"They'll be delivered with your next message"* — which was true of
the bug and is false now. If the replacement leaves you guessing, say so; the wording is the
deliverable here, not the mechanism.

**On the entry itself, two named buttons** — **Continue** and **Discard**. Discard is spelled out
rather than an ✕ because on a held entry the choice is between two dispositions and one of them
throws the message away permanently.

**Continue is offered only on held entries.** An ordinary queued entry — one waiting because the
agent is busy — keeps the plain ✕ and no Continue. If you see Continue on an entry the budget is
not holding, that is a bug: the endpoint would refuse it.

## The three ways forward

| | What it does | What changes about the chain |
|---|---|---|
| **Continue** | Re-bases the entry to depth 0 and delivers it on the next turn | The count restarts from you. The agent's reply is at depth 1, and the chain gets a full budget again from here. |
| **Discard** | Withdraws the entry | It is never delivered. The sender is not told. |
| **Raise the budget** | Queue settings | Everything held below the new budget is delivered **at the depth it already has** — nothing is re-based, and nothing is recorded as your decision. |

The difference between the first and the third is worth seeing at least once. Continue says *the
operator restarted this chain here*; raising the budget says *the bound was set too low*. Only the
first is recorded, as a `queue_entry_released` event carrying the depth it was released from:

```
queue_entry_released  {"entry_id": "entry-…", "agent": "builder", "released_from_depth": 2}
```

That event is the only place the original depth survives — after the re-base the entry itself
reads 0.

## Task 5.2 — does the released message still make sense?

This is the part only a person can judge. Continue a held entry, then read the conversation from
the top.

The released message was written in reply to something the agent said a turn or two ago, and it now
arrives after whatever you said in between. Does the thread still read coherently, or does the
reply land somewhere it no longer fits? If it reads as a non-sequitur, that is a finding about
*when* the product should offer Continue, not about whether the mechanism works.

## What it looks like when it goes wrong

**An operator message drains the held entry.** Send an ordinary message into the same conversation
and watch the hop-2 entry go `delivered` alongside it. That is F5, the bug this change fixes — if
you see it, the delivery filter is not running. Check that the Hub serving 8010 is the one built
from this branch, not the installed package.

**The turn's depth is lower than the entry that admitted it.** Read the run:

```bash
sqlite3 "file:$HOME/.agentweave/hub/profiles/beta/agentweave.db?mode=ro" \
  "select id, agent, turn_depth from runs order by rowid desc limit 3"
```

A turn admitted by a hop-2 entry must read `turn_depth = 2`. If it reads 0 because an operator
message rode along in the same batch, the counter is still running backwards and the budget will
never actually bite.

**Continue returns 409.** Two different refusals, and they mean different things:

- *"Queue entry is absent or has already been delivered/withdrawn"* — someone else acted on it, or
  the id is wrong.
- *"Queue entry is at hop N, within the project's hop budget of M…"* — the budget is not what is
  holding this entry. It is waiting for something else, and the agent's queue status says what.
  Releasing it would not have helped.

**A held entry with no way out.** If you find an entry the budget is holding and the panel offers
neither Continue nor Discard, that is the wedge this change exists to prevent — a bound with no
exit is worse than the leak it replaced, because the agent starts a fresh chain around the held
message and nobody ever reads it.

## Afterwards

Put the hop budget back to whatever the project had before — 6 is the default. Anything still held
at that point is released at its own depth, without being re-based.
