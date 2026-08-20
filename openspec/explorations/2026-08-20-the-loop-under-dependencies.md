# Exploration — The loop under dependencies (2026-08-20)

**Status:** Explored with the operator 2026-08-20, immediately after
`2026-08-20-what-the-spec-may-say-about-who-does-the-work.md` and prompted by their question: *"How
does the loop fit into all of this? The current code for loop I already think it's kind of weird."*

Decisions the operator took are marked **DECIDED**. Every claim was checked against the code;
`file:line` is given so the next reader can re-check rather than trust.

**The short version.** The loop is not weird — it is a mature sequential executor with 24
requirements and three documented live-found bugs. What is true is that `task-dependencies` **breaks
it in two specific, nameable ways**, and one of those looks reachable today without any of this
shipping.

---

## 1. What the loop actually is

`Loop` is *"an `AIJob` wearing a purpose and an optional stop condition"* (`models.py:1219`). That
framing undersells it. What has accumulated around it:

| | where |
|---|---|
| A queue — the tasks naming it via `Task.loop_id` | `agent-loops` §36 |
| One loop per document, enforced | `models.py:1257-1259`, `unique=True` |
| A deterministic claim, never the agent's judgement | §206 |
| Continuity across firings by checkpoint, not resumed session | §231 |
| Stop conditions that can only prevent a firing already going to happen | §110 |
| A controller, defaulting to the operator, delegable | §322 |
| Archiving, `ending_state`, per-loop history | §466, §508, §429 |

That is a work executor, and rebuilding it would mean re-deriving twenty-four requirements including
three bugs found only by driving it live. **Rebuilding is not a candidate**; the question is what
changes.

## 2. The deadlock — structural, guaranteed, and predicted in a comment

Three facts in `scheduler.py`:

```python
_loop_queue_order()            (Task.status != "pending").desc()   # non-pending sorts FIRST
CLAIMABLE_LOOP_TASK_STATUSES   ("in_progress", "blocked", "assigned", "pending")
claim                          pending -> assigned                 # scheduler.py:815-816
```

Now add the dependency gate, which refuses `→ in_progress` while a prerequisite is unapproved:

```
   firing 1   claim oldest pending ──▶ assigned
              agent attempts → in_progress ──▶ REFUSED
              task remains `assigned`

   firing 2   `assigned` sorts above every `pending` task ──▶ re-claims THE SAME task
   firing 3   ⟳ forever. Startable work is never reached.
```

The code predicts this exactly, at `scheduler.py:243-245`:

> *"The accepted cost is the mirror image: a task the agent genuinely cannot start is now re-claimed
> every firing, so the loop repeats one item instead of spinning on none. That is the more visible
> and more fixable of the two failures, which is why it was chosen."*

That trade was taken on 2026-08-19 against an **occasional agent-behaviour** problem — an agent that
*"may simply not"* call `update_task` (`scheduler.py:236-237`). Dependencies convert it into a
**structural certainty**: every dependent task is unstartable by design until its prerequisite is
approved.

**An irony worth recording.** `task-dependencies` design D1 deliberately leaves `→ assigned`
ungated, so a whole wave can be assigned in advance. That exact decision is what allows the loop to
claim work it cannot start. Two locally-correct decisions, one bad interaction — and neither is
wrong on its own.

## 3. The spin — same shape, different clothes, and it looks live

`TERMINAL_FOR_BINDING` is `("approved", "rejected")` (`scheduler.py:239`). So `completed` counts as
**open** for the stop condition (`scheduler.py:88-92`), while `completed` is **not** in
`CLAIMABLE_LOOP_TASK_STATUSES`.

```
   every queued task reaches `completed`, none approved
        │
        ├── nothing claimable       completed ∉ CLAIMABLE
        └── queue not empty         completed ∉ TERMINAL_FOR_BINDING
                    │
              fires forever · claims nothing · never stops
```

This is the *"spinning on none"* failure the 2026-08-19 fix was written against, reached by a
different route — and that fix did not close this one, because it added `assigned` to the claimable
set, not `completed`.

**It appears reachable today, without dependencies**, whenever a loop's tasks all complete and
nothing reviews them. **Not verified.** It should be, before any of this is designed around: it
would be a live bug worth fixing on its own terms.

## 4. Why a solo loop cannot execute a chain at all

Combine §3 with `task-dependencies`' decision that a dependency is met at **approved**, and with
author/reviewer separation, which binds agent runs (`task_transition_service.py:119`, and *"the
operator may approve their own work"* — but an agent may not).

```
   loop agent completes layer 0
        │
        ├── cannot approve its own work        (author/reviewer separation)
        └── layer 1 needs layer 0 approved     (met-at-approved)
                    │
              nothing claimable, ever, without a second party
```

A single-agent loop does not merely do dependent work badly. **It cannot advance past the first
layer.** This is the finding that makes the loop question load-bearing rather than tidy-up.

## 5. The operator's answer — hand off, don't grow the loop

**DECIDED.** Not a second agent bound to the loop:

> *"We don't need to assign another agent I think. Once the agent finishes the work it needs to send
> a message to a tester to continue the work. Any tester available."*

This is better than growing `Loop` a second binding, and most of it already exists:

| Piece | State |
|---|---|
| `send_message(to_agent, subject, content, message_type, task_id, conversation_id)` | exists, `mcp_server.py:174` |
| `message_type` vocabulary | **already includes `"review"`** — the handoff was anticipated |
| Delivery | the recipient's durable inbound queue |
| Waking the recipient | `schedule_agent`, called from `messages.py:259` on send |
| Asking the operator when unsure | `ask_user`, 1–4 structured questions, blocks and returns |

So the mechanism is: agent completes → `send_message(tester, message_type="review", task_id=…)` →
inbound queue → `schedule_agent` starts the tester → tester reviews → `under_review` → `approved` →
the next layer unlocks.

**Nothing in that chain needs building.** What is missing is everything the agent needs to *choose*
the tester.

## 6. The four gaps, and one of them is total

### 6.1 An agent cannot tell what any other agent is *for*

`send_message`'s own description says the recipient is *"as listed in your context"*
(`mcp_server.py:185`), and there is a Team section (`api/v1/agents.py:1229-1243`). It carries:

```
### Team
- `bravo`: claude, opus
- `charlie`: codex, gpt-5      <- you

Address a peer by the exact name above when sending a message or assigning a task.
```

Name, runner, model. **Not the charter.** The charter is the *"editable markdown behavior contract"*
that says what an agent is for — and it is injected into that agent's own context, never into
anyone else's.

So an agent told to find a tester sees two names and two model strings. The operator's phrasing —
*"names and charter are not explanatory"* — is generous: the charter is not there at all.

### 6.2 An agent cannot tell who is busy

> *"if there are 2 testers and one is testing we don't want to pile all the test on the same one
> right?"*

Nothing exposes this. The Hub knows — `turn_scheduler.py:37-43` answers *"agent is already
running"* on every schedule attempt, and `agent_status.py` derives heartbeat status including a
`stalled` state. None of it reaches an agent.

**This is the argument for a tool rather than a richer context section**, and it is worth stating
because the cheaper fix looks tempting: context is assembled **once, at turn start**. Availability
changes *during* a turn — that is the whole nature of it. A roster snapshot claiming `bravo` is free
is wrong the moment `bravo` starts, and an agent acting on it piles work exactly as the operator
described.

```
   charter / purpose  ──▶ static, cheap, same all turn   ──▶ belongs in CONTEXT
   availability       ──▶ live, changes mid-turn         ──▶ must be a TOOL
```

### 6.3 There is no agent-listing tool at all

Twenty-one `@mcp.tool()` functions, twenty agent-callable. Reading the list: messaging, tasks,
questions, checkpoints, recall, `request_agent`, jobs and loops, spec documents, evidence.

**Nothing lists agents.** `request_agent` *creates* one. An agent can ask for a new colleague and
cannot see the colleagues it has.

### 6.4 A task cannot name its reviewer

> *"there should also be a way to bind a tester to a task."*

`Task.assignee` is the doer. There is no reviewer field. So *"this one goes to bravo"* has nowhere to
be recorded, and the choice is re-made from scratch on every handoff — including by an agent that
has no basis for making it (6.1).

## 7. Who guarantees the handoff happens — the real fork

The operator's design has the **agent** send the message. That is right on the merits: the agent
knows what it built and what needs checking, and a handoff carrying that is worth more than a
mechanical one.

But it makes the chain depend on an agent choosing to act, and this codebase has been bitten by
exactly that. `scheduler.py:236-237`, on why `assigned` had to join the claimable set:

> *"reaching `in_progress` needs the agent to call `update_task` itself, **which it may simply not
> do.**"*

An agent that completes and does not hand off leaves the task `completed`, unreviewed, and the loop
in §3's spin.

Against that stands an existing principle in the loop's own specification (§206):

> *"No firing SHALL leave the choice of which queued task to work to the firing agent's own
> judgement."*

The loop already refuses to let the agent choose *what to work on*. Letting the agent be the only
thing that decides *whether work moves forward* sits awkwardly beside it.

And a second standing principle cuts the other way. CLAUDE.md, on the retired question-detection
backstop: *"An agent that needs an answer calls `ask_user`; a turn that ends without calling it has
ended."* The product deliberately refuses to guess at agent intent.

The distinction that may reconcile them: **the backstop was retired because it *inferred* intent
from prose.** A loop noticing that its own claimed task sits `completed` and nothing is reviewing it
infers nothing — it is a fact about a row.

**Proposed, not decided:** the agent sends the handoff, and the loop guarantees it. If a firing finds
its claimed task `completed` with no review in flight, it routes it rather than claiming new work.
Belt and braces — which is the same choice `scheduler.py:243` already made, preferring *"the more
visible and more fixable of the two failures"*.

## 8. Is the time-based firing wrong?

Less than it looks. The clock is not scheduling work — it is **polling**. A poll over a DAG is
perfectly reasonable, provided it can distinguish three states. Today it distinguishes none of them:

```
   nothing ready YET      keep firing, and say what is being waited on
   nothing ready EVER     stop — gated on rejected work
   nothing LEFT           stop — complete
```

All three currently present as "claimed nothing", which is why §3 spins.

**Before replacing the clock with readiness events, §6 of the previous exploration applies
directly.** `redrain_queued_agents` is *"reachable only from project open, settings save and
relocate"*, and an entry was *measured* sitting queued until an unrelated settings save —
*"a limit protecting nobody"*. This codebase forgets to wire event wakers.

**So: events, with the clock retained as a backstop.** Never events instead of the clock. A loop that
fires on a schedule and finds nothing to do is cheap; a loop that waits for an event nobody emits is
the bug this project has already shipped once.

## 9. The structural mismatch that remains

`Loop.spec_document_id` is `unique=True` — *"one loop per document… so two loops cannot silently race
to claim the same decomposition"* — and `_claim_loop_task` returns exactly one task. **The loop is
serial by construction.** Dependencies exist precisely to expose parallelism it cannot use.

That is not necessarily wrong. §6 of the previous exploration decided parallelism is the operator's
to start, not the system's. So:

```
   LOOP                              BOARD
   unattended · serial · one doc     attended · parallel · operator-driven
   "grind through this decomposition" "here is the shape, start what you like"
```

Two coherent modes rather than one broken one. **Open:** whether a loop should ever claim more than
one item. It is the only way unattended work gets parallelism, and it collides with both the
uniqueness constraint and the §6 decision. Not needed for correctness — only for throughput.

## 10. What this becomes

| # | Change | Depends on | Why |
|---|---|---|---|
| **L0** | **Verify the §3 spin**, and fix it if live | nothing | A loop that fires forever claiming nothing is a bug today, independent of everything here. |
| **L1** | **Charter summary in the Team section** | nothing | One line per peer saying what it is for. Cheapest possible fix for 6.1, and useful with or without loops. |
| **L2** | **`list_agents` MCP tool** — roster, charter, current availability | nothing | 6.2 and 6.3. Must be a tool, not context (§6.2). |
| **L3** | **Dependency-aware claim** — skip unstartable tasks; distinguish the three stalled states | `task-dependencies` | Without it, dependencies deadlock every loop (§2). **This is not optional.** |
| **L4** | **A task names its reviewer** | L2 | 6.4. Bindable by the operator, choosable by an agent, and the natural home for "easy tasks get a weaker reviewer". |
| **L5** | **The review handoff, and who guarantees it** | L2, L3 | §7's fork. |

**L0 through L2 are worth doing regardless of dependencies.** L1 in particular: an agent that cannot
tell what its colleagues are for is a gap in a multi-agent product, not a gap in loops.

**L3 is a hard prerequisite.** Shipping `task-dependencies` without it deadlocks every loop pointed
at a document that declares an order.

## 11. Still open

- **Does the §3 spin actually happen?** Everything else here is reasoning; this is checkable. Do it
  first.
- **Who guarantees the handoff** (§7) — agent alone, loop alone, or both.
- **Should a loop ever claim more than one item** (§9).
- **How does a reviewer get chosen when several are free?** The same least-loaded-versus-round-robin
  question §5 of the previous exploration left open for implementers, now for reviewers.
- **"Easy tasks can be reviewed by weaker agents."** This is the complexity tier applied to *review*
  rather than implementation, which the tier design did not anticipate. Does a task carry two tiers,
  or is the review tier derived from the implementation tier? **It also strengthens the case for
  tiers generally** — a second, independent use of the same vocabulary.
- **What happens to the loop's `stop_when_queue_empties` when the queue is stalled rather than
  empty?** A loop waiting on a review that will never come should end, and today it cannot tell.
- **Does the agent hand off to a *tester*, or to whoever the task names?** The operator said both —
  *"any tester available"* and *"bind a tester to a task"*. They compose (the binding wins, otherwise
  pick one), but the precedence should be stated rather than assumed.
