# Exploration — The loop becomes a flow (2026-08-21)

**Status:** Explored with the operator 2026-08-21, following
`2026-08-21-a-review-is-a-task-not-a-message.md`, which ended on a fork the operator refused to pick
a side of. Decisions the operator took are marked **DECIDED**. Every claim was checked against the
code or the specification; `file:line` and requirement lines are given so the next reader can
re-check rather than trust.

**The short version.** The previous exploration asked whether the *finishing agent* or the
*reviewer's own schedule* should wake a reviewer. Both answers make waking somebody's private
responsibility. The operator's reframe —

> *"we need to transform the loop into a flow with more functionalities. Like now it detects that
> it's complete and fire another agent. This feels like the right idea, the deterministic scheduler
> of a flow of tasks."*

— makes it the system's. And the audit below says this is an **extension of the loop, not a
rebuild**: 20 of its 25 requirements survive untouched, and the two structural obstacles are both
narrower than they first look.

---

## 1. What a flow is, said plainly

| | Loop today | Flow |
|---|---|---|
| Bound to | one agent | one **decomposition** |
| Each firing | pokes that agent | fires **whichever agent the next step needs** |
| Decides | which task | which task **and who does it** |
| Review | outside the queue, by message | inside the queue, a claim like any other |
| The graph | walks a list | executes a DAG |

The one-sentence version: **a loop pokes an agent on a schedule; a flow executes a decomposition.**

## 2. Why this dissolves the push/pull fork

The previous exploration's §6 could not choose between:

```
   PUSH   the finishing agent picks a reviewer and wakes them
          └─▶ an act, and an act can be omitted

   PULL   the reviewer's own schedule notices claimable work
          └─▶ needs standing loops that fire and find nothing —
              the spin fixed on 2026-08-20, recreated per reviewer
```

Both make waking *somebody's private responsibility*. A flow makes it structural: the flow already
fires on a cadence and already reads the queue, so *"task 1 is complete and needs a reviewer"* is a
fact it is looking straight at.

**It also extends the loop's own governing principle rather than contradicting it.** `agent-loops`
§211:

> *"No firing SHALL leave the choice of which queued task to work to the firing agent's own
> judgement."*

A flow says the same about **who does it next**. Same sentence, one more noun. That the principle
already exists — and was written for exactly this reason — is the strongest single argument that a
flow is what the loop was becoming anyway.

## 3. The audit — what survives

`agent-loops` has **25 requirements**. Read against a multi-agent flow:

**Survive untouched (20).** The loop/purpose/stop-condition definition; the queue being the tasks
that name it; queue-write authorship; stop conditions only ever preventing a firing; one document as
the queue's source; who may add to the queue; the briefing bound; the empty-queue-with-a-request-in-
flight termination; the creator-only window before first fire; **the controller**; edits taking
effect at the next firing; refusal-and-successor for a stopped loop; per-loop history; in-progress
versus finished; archivable-never-deletable; no archiving while running; `ending_state`; listability;
conversations naming their loop; and the timestamp rule.

Note the controller (§322) in that list. *"A loop has a controller, defaulting to the operator, which
may be delegated"* — under a flow that becomes **more** load-bearing, not less: it is already the
answer to "who may extend what this thing executes".

**Change (5).**

| Requirement | What changes |
|---|---|
| §206 A firing claims its queue's current item | Also determines **who**. The claim becomes actor-aware. |
| §231 Continuity is by checkpoint | Survives; the *lineage* model beneath it changes — §5. |
| §525 A claimed task is still the loop's current item | "The current item" is singular. Only breaks under parallelism (§6). |
| §626 Consecutive firings occupy one row | Written for one agent firing repeatedly. Consecutive firings of *different* agents are not the same event. |
| §72 A firing is traceable to what it produced | Survives, but must now name which agent produced it. |

**Twenty out of twenty-five untouched is the answer to the "do not rebuild it" decision** recorded in
`2026-08-20-the-loop-under-dependencies.md` §1 — *"24 requirements and three bugs found only by
driving it live… rebuilding re-derives all of it."* This re-derives none of it.

## 4. The first structural obstacle — `AIJob.agent`

`AIJob.agent` is `String(64), nullable=False, index=True` (`hub/hub/db/models.py`). One agent, and
not optional.

That field is not decoration. Agent identity reaches the run credential, the briefing, the
conversation, the checkpoint and the inbound queue entry. A flow that fires different agents on
different firings cannot simply null it.

**The shape that avoids a rewrite:** `AIJob.agent` keeps meaning what it means — *the agent this job
pokes* — and a flow's firing supplies the agent **per firing** rather than reading it from the job.
The job's field becomes the default and the fallback: a flow with nothing to say about who should act
fires its declared agent, which is exactly today's behaviour and exactly what every existing test
asserts.

That is worth stating as a rule: **a flow with one agent and no declared reviewers must behave
identically to a loop today.** It is the migration story and the regression suite at once.

## 5. The second — the checkpoint lineage

**DECIDED: the checkpoint chain belongs to the flow. One chain, many authors, each checkpoint
recording which agent wrote it.**

The good news is that the *requirement* is already flow-shaped. §231:

> *"Each firing of a loop's job SHALL be briefed with the most recent checkpoint recorded by **any
> prior firing of that same loop, regardless of which conversation produced it**."*

Keyed on the loop, not the agent, and `latest_checkpoint_for_loop` retrieves that way today. What
disagrees is the model's own comment — *"Linear, single-agent chain. `lineage_id` is the first
checkpoint's id, carried forward"* — and `Checkpoint.agent` being `nullable=False`.

So this is not a conflict between the flow and the design. It is a **latent disagreement between a
requirement that already says "the loop's" and a model comment that says "one agent's"**, which
nothing has had to resolve because no loop has ever had two agents.

*Rejected:* **per-agent chains within the flow.** It preserves today's model exactly and defeats the
purpose — a reviewer would start blind to what the implementer was thinking, and carrying that across
is most of what a handoff is for. *Rejected:* **both a flow chain and per-agent chains** — two
mechanisms where there is one, plus a rule for what goes where, before anything has demonstrated
needing it.

**Consequence to hold:** a checkpoint becomes readable by an agent that did not write it. Nothing in
the checkpoint contract says it is private, but nothing says it is shared either, and the wording an
agent is given when it writes one should now say who will read it.

## 6. The question this forces — parallelism

`_claim_loop_task` returns **exactly one task**. `2026-08-20-the-loop-under-dependencies.md` §9 named
the consequence and left it open:

> *"The loop is serial by construction. Dependencies exist precisely to expose parallelism it cannot
> use."*

A flow that runs one task at a time walks the DAG in a valid order and never uses its width. The
graph becomes documentation.

**But the operator's standing decision is that parallelism is theirs to start, not the system's**
(§6 of `2026-08-20-what-the-spec-may-say-about-who-does-the-work.md`, where the max-concurrent-runs
setting was withdrawn: *"let the user control it. He can start the agents and tasks that he wants to
start as he wants to start."*).

**A flow genuinely reopens this**, and the argument for it is narrower than "the system should be
clever": a flow starting two tasks whose dependencies are both met is not the system exercising
judgement — **it is executing what the document declared.** The width came from the operator, at spec
time, through the decomposition they approved.

That is a real distinction and it may or may not persuade. **Not decided.** It is the main scope
question and the reason this exploration exists rather than a proposal.

Worth noting the serial reading survives contact with the review problem perfectly well: implementer
fires, then reviewer fires, one at a time, and every problem this week's explorations chased is
solved. Parallelism buys throughput, not correctness.

## 7. What this does to work already proposed

**`loop-notices-and-reacts`** — the accounting from the previous exploration holds and sharpens:

| Part | Fate |
|---|---|
| R5 busy guard, R6 tick recording, D9 status vocabulary | **Unaffected and still wanted.** A flow fires more often, not less, so a firing that costs nothing when there is nothing to do matters more. |
| R1 handoff detection, R2 re-brief | **Superseded.** There is no message to detect or to remind about. The flow fires the reviewer. |
| R3 surfacing exhaustion | **Reduced to something real:** a task that has been claimable for a long time and that the flow could not staff — because no eligible agent exists — is worth surfacing. That is a statement about the roster, not about an agent's diligence. |

**`task-dependencies`** — unaffected and strengthened. Its group 9 (the dependency-aware claim, added
2026-08-21) is exactly the claim logic a flow needs, and design D10's insistence that the claim
consult the same gate the transition uses is what makes a flow's selection trustworthy. It is being
implemented now and nothing here disturbs it.

**Shape B from the previous exploration** — `completed` becoming claimable by a non-author — is what
the flow *uses* to fire a reviewer. The two are one design: Shape B says the work is takeable, the
flow says who takes it and when.

## 8. Open questions

- **Parallelism** (§6). The scope question. Everything else works either way.
- **How does a flow know who should review?** Three layers already sketched in the previous
  exploration: the document names them; else whoever is free and holds no active task; else nobody
  and it surfaces. The flow performs the selection either way — this is only about where the answer
  comes from.
- **What if the eligible reviewer is busy?** A flow that fires nobody this tick and tries again is
  cheap once the busy guard lands. But *"busy"* and *"there is no eligible agent at all"* are
  different, and only the second is worth surfacing.
- **Does a flow fire an agent that has no runner bound?** Today `AIJob.agent` is validated at
  creation. A flow selecting an agent at firing time can select an unlaunchable one.
- **Does `Loop` keep its name?** *"Flow"* describes the thing better and the rename would touch a
  lot: table, API routes, UI, the `agent-loops` capability, MCP tools, and the operator's own
  vocabulary. Cosmetic against everything else here, and worth deciding once rather than drifting
  into both words.
- **`§626 consecutive firings occupy one row`** — written when consecutive firings meant one agent
  repeating. Two agents in sequence is the normal case for a flow and is not one event.
- **What does the operator see?** A flow's board is the dependency board of `task-dependencies`,
  which is being built. Whether a flow needs a view of its own, beyond the loop card and that board,
  is untouched.
