# Exploration — A review is a task, not a message (2026-08-21)

**Status:** Explored with the operator 2026-08-21, prompted by their objection to the direction the
previous exploration was heading. Decisions the operator took are marked **DECIDED**. Every claim was
checked against the code; `file:line` is given so the next reader can re-check rather than trust.

**Supersedes part of** `2026-08-20-who-guarantees-the-review-handoff.md`. That document's answer —
the loop re-briefs its own agent to send a handoff message — solves a problem this one argues should
not exist.

**The short version.** The re-brief exists because a review handoff is a *message*, and a message can
be forgotten. Make the review a *task* and there is nothing to forget: it is on the board because the
work is done, and it is claimable by whoever is free. The operator got there from a different
direction — refusing to accept configuration as a precondition for starting work — and the two
concerns turn out to have one answer.

---

## 1. The objection that started it

The previous exploration's §6.1 said an agent cannot tell what its colleagues are *for*, and proposed
putting each peer's charter scope into the Team section (L1) plus a `list_agents` tool (L2). Grounding
that turned up something encouraging: **every seeded charter already carries a one-line purpose**, as
`> **Scope:** …` immediately below its H1, consistent across all nine
(`hub/hub/data/charters/*.md`).

The operator stopped it anyway:

> *"Now that I think about it I don't want to end up in a old problem where having a squad to develop
> is a price that you need to pay before even starting development... Needing to decide everything up
> front is not what I would like."*

**This is correct and the direction was wrong.** For charter-based selection to work an operator must
create charters, write good scope lines, and bind them to agents — all before the first handoff can
happen. That is a squad tax, and it is the same shape of friction this project already diagnosed once
in the init/roles default.

The evidence was in the seeds too. Three of nine ship an **unfilled placeholder** scope —
`developer`, `underwriter`, `underwriting_approver` all read *"_Set this for the agent you bind this
charter to…_"*. A design that depends on operators writing good scope lines starts from a corpus
where a third of them have not been written.

**DECIDED on the narrow question:** where a scope is unfilled, show **nothing** — no purpose line at
all, rather than a placeholder an agent would read as a peer's purpose.

## 2. The operator's three shapes are one answer in three layers

> *"At spec time define who is testing what. As soon as the agent finishes he picks one available
> agent that is not assigned to any task. A test should be a task on the board and be assigned to
> agents as well."*

Read as competing options these are three designs. Read as layers they compose, and the composition
has the property the objection asked for:

```
   WHAT        a review is a TASK on the board                       (c)
                    │
   WHO, said   the document names who reviews it                     (a)
                    │
   WHO, else   whoever is free and holds no active task              (b)
```

**With nothing configured — no charters, no scope lines, no bindings — (c)+(b) still works.** A
review appears on the board and whoever is free takes it. Configuration becomes optional refinement
rather than a precondition. That is the whole point.

L1 and L2 do not die; they demote. Charter purpose makes selection *better* — a security review going
to the security engineer rather than to whoever answered first — but nothing waits on it.

## 3. Why (c) is the load-bearing one

| | Review as a message (today) | Review as a task |
|---|---|---|
| Visible on the board | no | yes, a card |
| Can depend on the implementation task | no | yes, the machinery exists |
| Can be assigned | no | yes |
| Goes through the lifecycle | no | yes |
| **Claimable by a loop** | **no** | **yes** |

The last row is the whole argument. **The §7 problem exists because a message is not claimable.** A
loop stalls at `completed` precisely because the next step lives outside the queue it can see. Put
the review inside the queue and the loop's ordinary machinery moves it.

It also answers `task-dependencies` human-check 10.2 — *"the stall is diagnosable… the board says work
is waiting on review"* — structurally rather than by a display rule. That check exists because an
unattended review backlog and a broken dependency gate look identical from outside. If the review is a
card, they cannot.

## 4. Two shapes for "a review is a task", and one of them regresses

### Shape A — a second task row, `review T`, depending on `T`

The obvious reading. It breaks on two facts:

1. **`Task` has no `kind` column** (checked: `hub/hub/db/models.py`, the `Task` model carries
   `assignee`, `spec_document_id`, `loop_id` and no discriminator). A review task would need one, plus
   every consumer taught to treat it differently.
2. **Infinite regress.** If a review is a task, the review task's own completion needs reviewing. The
   only escapes are an exemption — *"review tasks are not reviewed"* — which is a special case
   contradicting the change's own premise, or an unbounded chain.

### Shape B — `completed` becomes claimable, but only by someone who is not the author

No new row, no new column, no regress. The task's existing lifecycle already contains the review:

```
   T:  pending → in_progress → completed → under_review → approved
                                ^author      ^reviewer     ^not the author
```

The only thing missing is that **nobody can pick the task up at `completed`.** It sits in the gap this
session already named — in neither `CLAIMABLE_LOOP_TASK_STATUSES` nor `TERMINAL_FOR_BINDING` — which
is exactly why the loop spins, and exactly why a message was needed to move it along.

**Shape B closes that gap properly instead of naming it.** `completed` becomes claimable *by an agent
that is not the one recorded as completing it* — and that determination already exists, computed by
`_agent_that_completed` (`hub/hub/task_transition_service.py:92-116`) for the guard on
`under_review → approved`.

**DECIDED: Shape B**, subject to §6's open question about what wakes the reviewer.

## 5. What this does to `loop-notices-and-reacts`

Honest accounting, because this challenges work proposed the same week.

| Part | Fate under Shape B |
|---|---|
| R5 — busy guard | **Unaffected.** A measured bug about firing during a live turn. |
| R6 — tick recording | **Unaffected.** About history legibility, not handoffs. |
| D9 — status vocabulary | **Unaffected, and more useful.** Shape B changes a status's classification, which is precisely what a single vocabulary makes safe. |
| R1 — handoff detection | **Probably unnecessary.** It answers *"did the agent send the message"*; under Shape B there is no message. |
| R2 — the re-brief | **Probably unnecessary.** Nothing to remind an agent to do. |
| R3 — surfacing exhaustion | **Reduced.** *"Nobody has reviewed this"* is still worth surfacing, but as an observation about a claimable task nobody claimed, not as a failed reminder chain. |

**The claim that killed it, stated plainly:** the re-brief exists because an agent might forget to
send a message. Under Shape B the agent does not send anything. The task becomes reviewable by virtue
of being `completed`, and there is no act to omit.

**Not yet certain**, because §6 is open: if something still has to *pick* a reviewer and *wake* them,
and that something is the finishing agent, then it can still be forgotten and R1–R3 come back in a
different costume. That is the one thing that decides whether they survive.

## 6. The open fork — pull or push

Making a task claimable does not make anyone claim it. Something must run a reviewer.

```
   PULL   reviewers' own loops claim reviewable tasks
          nothing is assigned, nothing is forgotten, no picking at all
          BUT: only works for agents that have a loop or are otherwise running
          AND: "one loop per document" is unique=True (models.py:1257-1259), so a
               reviewer's loop is a second loop over the same document — which the
               constraint forbids

   PUSH   the finishing agent assigns the review to a free agent, which wakes them
          matches the operator's words exactly — "he picks one available agent that
          is not assigned to any task"
          BUT: it is an act, and an act can be omitted — the re-brief's whole premise
          MITIGATED: an omitted assignment leaves a `completed` task visibly unassigned
                     on the board, where an omitted message left nothing at all
```

**PUSH is what the operator described.** Its weakness is real but much smaller than the message
version's: a forgotten assignment is a visible card, not an absence. Whether that visibility is enough
to retire R1–R3, or whether a reduced R3 should still surface a `completed` task nobody has claimed
after some time, is **the decision this exploration has not taken.**

There is also a third possibility neither the operator nor I have argued for: **the Hub assigns**,
which is carve-up item 4d (auto-assignment), unproposed and blocked behind 4c. Worth noting that
Shape B makes 4d a much smaller thing than it looked — assigning a reviewer is a narrower problem than
assigning implementation work.

## 7. What "free" means — DECIDED

> *"if there are 2 testers and one is testing we don't want to pile all the test on the same one"*

**DECIDED: not running, and holding no task in an active status.** Both facts already exist and
neither needs new state:

| Fact | Where |
|---|---|
| Is the agent mid-turn | a `Run` with `status == "running"`, the query `schedule_agent` already makes (`hub/hub/turn_scheduler.py:37-43`) |
| Does it hold active work | `Task.assignee` against `_ACTIVE_TASK_STATUSES` (`hub/hub/api/v1/agents.py:60`) |

*Rejected:* **not-running alone** — an agent can hold three assigned tasks and be idle between turns,
so it reads as free while genuinely loaded. That is the pile-up the operator named.
*Rejected:* **least-loaded** — never blocks, which sounds good and is not: it hands work to someone
already loaded and hides the fact that the project needs another agent.

**This must be a tool, not a context section**, and the reasoning from the previous exploration §6.2
is unchanged: context is assembled once at turn start, and availability changes *during* a turn. A
roster snapshot claiming `bravo` is free is wrong the moment `bravo` starts.

## 8. Still open

- **Pull or push** (§6), and consequently whether R1–R3 survive at all. Everything else here depends
  on it.
- **How a document declares a reviewer** (layer (a)) — a field on the task payload, and whether it
  names an agent, a charter, or neither.
- **`Loop.spec_document_id` is `unique=True`.** If reviewers pull, a reviewer working the same
  document needs a loop the constraint forbids. Does that constraint survive, or does pull need a
  different mechanism entirely?
- **What stops a loop claiming a review of its own agent's work?** Shape B's per-agent claimability
  answers it in principle — the loop's agent is the author and so cannot claim — but the loop's claim
  is currently a status query with no actor in it. Making claimability actor-dependent is a real
  change to `_claim_loop_task`'s shape, and it lands in the same shared decision function
  `loop-notices-and-reacts` D3 introduces.
- **Does `under_review` still get set by the author?** Today `completed → under_review` is `_BOTH` and
  unguarded, which is what lets an author self-submit with nobody on the other end. Under Shape B the
  reviewer's claim is what should move it, and the author moving it there itself becomes meaningless
  at best.
- **L1 and L2 are demoted, not cancelled.** Purpose improves matching once selection exists. Neither
  blocks anything now.
