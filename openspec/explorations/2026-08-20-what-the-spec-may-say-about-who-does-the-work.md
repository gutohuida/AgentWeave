# Exploration — What a specification may say about who does the work (2026-08-20)

**Status:** Explored with the operator 2026-08-20, in two passes. The first carried forward decisions
from `2026-08-20-the-row-is-the-spine.md` §6–§7 and checked them against the code. The second was a
live review in which the operator withdrew the parallelism cap they had previously asked for and
replaced it with something better. This is carve-up item **#4** — the largest of the five.

Decisions the operator took are marked **DECIDED**. Every claim was checked against the code;
`file:line` is given so the next reader can re-check rather than trust.

**Four proposals do not survive this document**, and that is its main value:

| Withdrawn | Where | Whose |
|---|---|---|
| Materialise dependent tasks as `blocked` | §3 | the previous exploration's |
| `Runner.flags` can carry effort today | §2 | the previous exploration's |
| Tiers name a model | §5 | superseded — `high`/`medium`/`low`, **DECIDED** |
| **A max-concurrent-runs project setting** | §6 | the operator's own, withdrawn on review |

The last one is the significant one, and §7 is what replaced it.

One decision was taken and **reversed within the review itself** — that the operator could edit
dependency edges on the board. It is recorded in §7 rather than quietly deleted, because the reason
for the reversal is the more useful half: an edge that exists only on the board is a fact the
specification does not contain.

---

## 1. The principle this item collides with

Before designing anything, there is a rule already written into the code that item 11 appears to
break. `spec_tasks.py:39-41`, on why materialised tasks are created unassigned:

> *"Where a declared task enters the lifecycle. The entry status, unassigned: the document says the
> work exists, and **who performs it is a roster decision a specification has no business making.**"*

The operator's original ask — a field in the spec naming the implementing agent — is precisely what
that comment refuses. It is not an oversight to be corrected; it is a stated position about what a
specification is for.

**The operator's own revision resolves the collision, and it is worth naming why.** They replaced
"name the agent" with "state the complexity":

```
   IN THE DOCUMENT                        IN THE PROJECT
   (travels, outlives the roster)         (machine-local, changes freely)
   ──────────────────────────────         ──────────────────────────────
   task: "migrate the index"              high   ─┬─▶ runner "Deep work"
   complexity: high                               ├─▶ runner "Deep work (codex)"
                                                  └─▶ …
                                          medium ──▶ …
                                          low    ──▶ …
```

Complexity is a property **of the work**. It is true on a machine with no roster at all, and it
stays true when the roster changes. The roster decision — *which* agent — stays in the project,
where `spec_tasks.py:39-41` says it belongs. The document never names a performer.

So the tier design is not a workaround for the rule. It is the shape the rule implies. Recording
that here because the next reader will otherwise meet the comment and think the feature contradicts
it.

The same reasoning is why writing `claude-opus-5` into a document is wrong: Opus 6 ships and 34
documents are quietly false. The tier keeps the document true; the mapping absorbs the churn in one
place.

## 2. What exists, and what does not

Checked rather than assumed. `depends_on`, `complexity` and `tier` appear **nowhere** in the Hub
outside Alembic's own `depends_on = None` boilerplate.

| Piece | State |
|---|---|
| `spec_payload.Task` (`:98-108`) | `key`, `title`, `description`, `requirements`. **No complexity, no dependencies.** |
| `materialise()` (`spec_tasks.py:89`) | Resolves requirements, links them, dedupes against hand-made tasks, respects an owning `Loop`, preserves unresolvable names as free text. Mature. |
| `assignee` / `assigner` (`spec_tasks.py:192-193`) | Literal `None`. **Auto-assignment is a value with no source, not a subsystem to build.** |
| `Agent.runner_id` (`models.py:215`) | Exists, **nullable**. |
| `Runner` (`models.py:302-330`) | `cli`, `model`, `flags`. |
| `Runner.flags` | *"freeform, optional escape hatch for future per-runner CLI-flag overrides; **nothing populates it yet**."* |
| `Runner.cli` | `CheckConstraint("cli IN ('claude', 'codex')")`. |
| `Project` budgets (`models.py:71-81`) | `hop_budget`, `turn_delivery_cap`, `agent_budget`, `token_budget`. A fifth setting has an obvious home. |
| Task→task dependency | **Does not exist in any form.** |

**One correction to §6 of the previous exploration.** It said `Runner.flags` *"can carry effort,
which is often the cheaper way to buy 'harder' than a bigger model is"*. True as a design
opportunity, but stated there as though the capacity were live. Nothing populates `flags`, and
nothing reads it. Buying effort through a runner is a thing to build, not a thing to use.

## 3. `blocked` cannot be the dependency status — withdrawn

The previous exploration proposed (§7): *"`materialise()` can enter dependent tasks as `blocked`
rather than `pending`, so the board shows the wave structure instead of twenty tasks all claiming to
be ready."*

**This is illegal three times over**, and each refusal is deliberate and documented.

**One — a task cannot be created blocked.** `task_transitions.py:94`:

```python
ENTRY_STATUSES: FrozenSet[str] = frozenset({"pending", "assigned"})
```

and the module docstring says why (`:16-18`):

> *"**A lifecycle that can be entered anywhere is not a lifecycle.** `ENTRY_STATUSES` exists because
> governing transitions alone left the machine walkable around: a caller could create a task already
> `approved` and never transition at all."*

Materialising into `blocked` is exactly the move that rule was written to stop.

**Two — `blocked` is reachable only from `in_progress`** (`task_transitions.py:120`):

> *"Reachable only from `in_progress`: **a task nobody has started is not blocked, it is pending.**"*

That single sentence answers the question the proposal was trying to solve, in the opposite
direction from the proposal.

**Three — `blocked` means something else.** `task_transitions.py:118`: *"Work that started and then
hit something only a person can supply."* `Task.blocked_reason` (`models.py:680-688`) is *"what a
`blocked` task is waiting for, **in words the operator can act on**"* — the difference between a card
saying "blocked" and one saying "blocked on the API key". A task waiting on a sibling task is not
waiting on a person, and nothing the operator can do releases it.

**Also worth correcting:** `blocked_task_id` (`models.py:903`) is on **`Question`**, not on `Task`.
It records *"the task this question parked… answering it releases this task"*. It is not a
dependency edge and cannot be reused as one.

### What replaces it

**Readiness is a computed property, not a status.** A task with unmet dependencies is `pending` —
which already means "nobody has started it" — and is additionally *not yet startable*. That is a
scheduling fact, not a lifecycle fact, and the transition machine stays untouched.

```
  status        : where the work is in its life      (the machine owns this)
  depends_on    : which sibling tasks must finish first  (new, on the task)
  ready         : derived — no unmet dependency      (nothing stores this)
```

The board can show unready tasks differently — dimmed, grouped into waves, sorted last — without any
of that being a status. And routing simply does not offer an unready task to an agent.

**One thing this does lose**, and it should be admitted: `blocked` was attractive because the board
*already* renders it. Readiness needs new UI. That is a real cost and it is the price of not
overloading a status whose narrowness is load-bearing.

**§7 is where that cost is paid, and it turned out to be worth paying.** A status carries one bit per
card — stuck or not. A dependency layout carries the whole wave structure, which is strictly more
than `blocked` could ever have shown.

## 4. Where dependencies live, what an unmet one does, and how one crosses a document

`key` is already *"a stable handle for this task, unique within the document"* (`spec_payload.py:99`).
So a dependency is a list of sibling keys, and the DAG needs no new identifier scheme:

```python
class Task(_Part):
    key: str                  # exists
    title: str                # exists
    description: str          # exists
    requirements: List[str]   # exists
    depends_on: List[str]     # keys of sibling tasks in this document
    complexity: str           # the tier from §1
```

Two things ride along, and both are nearly free:

**The `Field(description=...)` strings *are* the agent-facing instructions.** *"One concrete unit of
work, not 'build the whole thing'"* is how the product teaches decomposition today. Dependencies get
taught the same way, in the same place, with no new mechanism.

**`spec_completeness` already reads the decomposition** (`:106`, `:130`) to judge whether tasks cover
the requirements. It gains the ability to say a decomposition declares a cycle, or names a
dependency key that does not exist — the same class of check it already performs against requirement
keys.

### DECIDED — an unmet dependency prevents starting; it does not stop anything

The operator's rule, and it is a sharper claim than "readiness":

> *"A task won't be stopped by a dependency… it should never start if a dependency is not met."*

This matters because *stopped* and *never started* are different states, and the transition machine
already distinguishes them. A dependency is a **precondition on an edge**, not a property of a task.

And the shape already exists — twice, in the same function. `task_transition_service.py:208-217`:

```python
await _guard_author_is_not_reviewer(session, task, to_status, actor)   # guard, on the review edges

# "The gate, on this one edge. Inside the service and before the history row, so it cannot be
#  bypassed by a caller reaching the row a different way — which is also why every surface
#  (operator route, agent HTTP, the tool surface, jobs) gets it without knowing it exists."
if to_status == "approved":
    refusal, policy = await evaluate(session, task)                    # requirement_gate
    if refusal.refuses:
        raise GateUnsatisfiedError(refusal)
```

A dependency gate is a **third guard in the same place**, on a different edge:

```
   pending ──▶ in_progress     ← GATED. every named dependency must be complete.
           ──▶ assigned        ← NOT gated. assigning future work is legitimate.
           ──▶ rejected        ← NOT gated. work never started can still be rejected.
```

No new status. No stored readiness column. No new enforcement surface — the comment above says why
every caller inherits it for free.

**Leaving `assigned` ungated is load-bearing for §8's 4d.** Routing can assign an entire wave up
front, and each agent starts when its own dependencies clear. The gate is what makes assigning ahead
safe rather than misleading.

**This dissolves an open question the earlier draft raised.** It asked what happens to a task that is
both `blocked` and dependency-unmet. Nothing does: `blocked` is reachable only from `in_progress`
(§3), and an unmet dependency prevents reaching `in_progress` at all. The two are mutually exclusive
by construction.

### DECIDED — a dependency is met at `approved`, and two things fall out of that

Not at `completed`. The wave advances only after the prerequisite has been reviewed and signed off.

**Consequence one: a dependency chain cannot advance with a single agent.** Author/reviewer
separation is structural (§6), so review needs a second agent:

```
   layer 0   agent A builds ──▶ completed ──▶ agent B reviews ──▶ approved
                                                                     │
   layer 1                                    agent A can now start ◀┘
```

This retroactively strengthens §6. Withdrawing the concurrency cap was not merely correct — it was
**necessary**. `max_concurrent_runs = 1` would have deadlocked every dependency chain of depth
greater than one, permanently, rather than merely making review awkward.

**Consequence two, unplanned: a dependency chain cannot advance past unverified work.** The gate on
the `→ approved` edge is already `requirement_gate.evaluate`, which at `gate` rigor refuses approval
while any of the task's requirements is unverified. Putting the dependency gate and the requirement
gate on the same edge means the second one guards the first for free. Nobody designed this; it is
worth stating so it is not removed by accident.

**The cost, stated: the bottleneck moves to review.** A five-deep decomposition needs five review
cycles, and if review is not happening the board stalls at layer 1 with everything downstream gated.
The board must say *"layer 2 is waiting on 3 reviews"* rather than only drawing gated cards —
otherwise a review backlog is indistinguishable from the dependency feature being broken.

**One thing this makes better:** regression becomes rare. `approved → revision_needed` is
operator-only, so a met dependency can now only come unmet by an explicit operator act, and the rule
below is a rare safety net rather than a common state.

**DECIDED — a rejected dependency is surfaced, not resolved.** A rejected task never reaches
`approved`, so its dependents are gated permanently, and `rejected → pending` is operator-only so
nothing self-heals. The board shows the dependent as gated on rejected work and names it; the
operator either reopens the dependency or edits the document to drop the edge.

*Rejected:* propagating rejection downstream — one rejection could cascade through a whole
decomposition unseen. *Rejected:* treating a rejected dependency as met — a dependent would start
because its prerequisite was abandoned, which is almost never the intent.

**DECIDED — a dependency that regresses after a dependent started flags, it does not halt.** `A` can
go `completed → under_review → revision_needed → in_progress` while `C`, which depends on it, is
already running. A precondition checked on an edge says nothing about this, so `C` continues — and
the board marks it as running on a regressed dependency so the operator can decide.

Enforcement is a guard; awareness is a display. Keeping them apart is what stops an agent having its
task pulled out from under it mid-turn, which is what a continuous invariant would do.

### DECIDED — a dependency crosses documents by importing the foreign task

The earlier draft called this out of scope and proposed a derived off-board stub. The operator's
answer is better because it is **declared**:

> *"We can put in the document tasks from another document just linking that task there saying it's a
> dependence."*

```
   document B's payload
   ┌──────────────────────────────────────────────────────┐
   │  tasks:                                               │
   │    - key: adopt-corpus            ← IMPORTED entry    │
   │      from: <approved document A>, key: adopt-corpus   │
   │                                                       │
   │    - key: render-map                                  │
   │      depends_on: [adopt-corpus]   ← an ordinary       │
   │                                     local key         │
   └──────────────────────────────────────────────────────┘
```

Three properties follow, and the second is why this is the right answer rather than merely a workable
one:

**`depends_on` stays a list of local keys.** No qualified-reference grammar, no second field, no new
resolution rule for an authoring agent to learn.

**The per-document board becomes closed.** Everything it must draw is declared in the single document
it is scoped to; it never queries another document at layout time. §7's per-document scoping stops
being a limitation that needed softening and becomes a property that holds.

**The dependency is visible to a reader of the document**, not only to the board — which is the whole
point of putting it in the specification rather than in the UI.

`materialise()` needs exactly one new rule: **an imported entry resolves to the existing task and
never creates one.** That is a small addition to a function that already dedupes by
`(document, key)`.

**DECIDED — only an approved document may be imported from.** This turns the rename problem into a
rule instead of a failure mode: `rename_document` refuses on an approved document — *"this document
is approved; its path is part of what was approved"* (`spec_service.py:638-641`) — so a
`(path, key)` reference to one is permanently stable, and it travels with the repository.

The cost is stated rather than hidden: **a dependency cannot be declared on work still being
explored.** Two things make that survivable, and the second is a design detail that must not be got
wrong.

*Order.* Imports resolve at approval, when `materialise()` runs. `B` depends on `A` because `A` is
the prerequisite, so `A` is approved first in the ordinary course of events. The restriction mostly
describes what would happen anyway.

*Timing of the check.* An agent authoring `B` may well write the import while `A` is still
exploring — and refusing the *submission* would make the document unwritable until its prerequisite
was settled. The existing rule covers this exactly (`spec_service.py:98-101`):

> *"Incompleteness is reported, not refused: a document under discussion is incomplete by definition,
> and it is the transition to `proposed` that cares."*

So: an import naming a non-approved document is **reported in `blocking`**, and refused at propose or
approval. Same pattern, same place, nothing new.

### DECIDED — once approved, a path is frozen forever

The archived question was checked and **did not close cleanly**, which turned out to matter more than
the question itself. `rename_document` refuses on exactly one phase (`spec_service.py:638-641`):

```python
if document.phase == spec_lifecycle.APPROVED:      # equality — not "approved or later"
```

and `approved` has two exits, both in `spec_lifecycle.TRANSITIONS` (`:45`, `:50`):

```
                    ┌──▶ (APPROVED, ARCHIVED)    ← path unfreezes
   approved ────────┤
                    └──▶ (APPROVED, EXPLORING)   ← path unfreezes
```

So the path is frozen *while the document sits in approved*, not permanently. Approve → import →
archive or reopen → rename → the import dangles. **This is a latent hole independent of imports:
today an approved document's path can be changed by archiving it first**, which the refusal's own
stated reason — *"its path is part of what was approved"* — plainly does not intend.

**DECIDED — change the refusal from "is approved" to "has ever been approved".** Monotone, faithful
to the stated reason, and reopening a document for revision does not un-approve history.

It needs a durable fact, and `explore_closed_at` (`models.py:1649`) is the precedent for exactly that
shape — a nullable timestamp recording a one-way event. The distinction is that `explore_closed_at`
is deliberately **reset** on reopen (`spec_lifecycle.py:253-257`, *"reopening genuinely reopens"*),
and this one never is. That difference is the whole point and should be commented where the column is
added.

It is also derivable without a column: phase transitions are recorded as `kind="phase"` events
carrying `{"from", "to"}` (`spec_lifecycle.py:259-265`). A column is cheaper to read and matches the
existing precedent; the event history is the check that it is correct.

**Open:** cross-document cycles. `spec_completeness` checks within one document (`:106`, `:130`);
`A ↔ B` needs the corpus, and only part of it may be adopted on this machine. A dangling import has a
precedent to follow rather than invent — unresolvable requirement names are *"preserved rather than
dropped… the unrecognised name is the evidence of what went wrong"* (`spec_tasks.py:204-206`).

## 5. Routing — the six open questions, answered where the code answers them

§6 of the previous exploration left six open. Four have factual answers in the code; two are the
operator's.

**Q5 first, because it changes the others: does assignment start work?**

**No, and nothing is close to it.** Nothing in `hub/hub/api/v1/tasks.py`,
`task_transition_service.py` or `task_integration.py` reaches `schedule_agent` or the inbound queue —
verified by grep, no hits. A run starts when something enqueues a turn: a message
(`messages.py:259`), an operator trigger, a job, an answered question. Assigning a task writes a name
onto a row.

So the alarming version of this feature — approve a document, eight agents wake up — **is not
reachable by accident.** It would require building a new path from assignment to the queue. That
should be a separate, explicitly-decided change, and this one should state it as a non-goal.

**Q1 — no roster agent holds the mapped tier. Refuse approval, or assign nothing?**

Assign nothing, and say why on the task. Refusing approval is disproportionate: approval is the
operator agreeing to the *specification*, and `materialise_quietly` already embodies exactly this
judgement (`spec_tasks.py:224-228`):

> *"Approval is the operator's decision about the specification. Failing that decision because the
> board could not be populated would make an unrelated problem look like a refusal to approve — and
> the document would stay unapproved, which is the one outcome nobody wanted."*

An unroutable task is the same class of problem. **Recommendation: create it unassigned, with the
reason recorded.**

**Q2 — several agents hold the tier. Round-robin, least-loaded, or ask?**

Least-loaded, counting *unfinished assigned tasks*, not runs. Round-robin ignores that one agent may
hold nine tasks. Asking, at materialise time, turns approval into an interview. **Open, but this is
the cheap default and it is reversible.**

**Q3 — `Agent.runner_id` is nullable. Is an unbound agent invisible to routing?**

Yes, necessarily. Routing matches on the runner, so an agent with no runner matches no tier. This
needs no rule — it falls out — but it needs *saying*, because an operator whose agent is silently
never assigned anything will read it as a bug.

**Q4 — `agent_budget` (8) caps the roster and therefore caps parallelism.**

True and already enforced (`api/v1/agents.py:1377`). No change proposed; recorded so the next reader
does not re-derive it.

**Q6 — what are the tiers?**

Genuinely open, and the one place a wrong answer is expensive: tiers are written into documents that
outlive the roster, so renaming a tier later means editing every document that used it.

`high` / `medium` / `low` is the obvious three. Two things argue for care:

- A tier could map to **(model, effort)** rather than a model alone, since effort is often the
  cheaper way to buy "harder". But `Runner.flags` is empty today (§2), so this is a build, not a
  configure.
- Three tiers assume complexity is one-dimensional. "Long but simple" and "short but subtle" want
  different runners, and both are `medium` under a single axis.

**DECIDED — `high` / `medium` / `low`.** Three names, one axis. A second axis is resisted until a
real decomposition needs one: adding an axis later is easy, renaming one is not, because a tier that
has been written into approved documents cannot be renamed without editing every document that used
it.

## 6. Max concurrent runs — proposed, then withdrawn by the operator

**WITHDRAWN.** The previous exploration recorded this as decided: parallelism opt-in, a project
setting, default 1, from *"He could be using a restricted token plan and need to do things one at a
time."* On review the operator withdrew it:

> *"I'm thinking of dropping this as a config and let the user control it. He can start the agents
> and tasks that he wants to start as he wants to start."*

Three things in the code support that, and any one of them would be enough.

**One — a cap cannot tell the operator's own work from an agent's, and the product already can.**
`turn_scheduler.py:68-71`:

```python
initiator = "operator" if controlling_operator is not None else "autonomous"
budget = await project_budget_state(db, project_id)
if initiator == "autonomous" and budget["exhausted"]:
    return ScheduleResult(waiting_reason="token budget exhausted")
```

`token_budget` pauses **autonomous** turns and lets **operator-initiated** ones through, so the
operator's own work is never starved by their agents' spending. That is exactly the distinction the
operator reached for — *"I want to explore something else while it builds"* — already built, and a
raw concurrency cap would ignore it. The cap would be a **regression against an existing mechanism**,
not an addition to it.

**Two — a cap of 1 makes the product's own review flow unreachable.** The operator's question was
*"what about testers? Will they enter in this math as well?"* They would, and it is fatal.
Author/reviewer separation is enforced rather than advised — `ActorNotPermittedError`, *"the move is
a legal edge, but not for this actor"* (`task_transition_service.py:52`), guarded at `:119`:

```
   completed ──▶ under_review ──▶ approved
                                     ▲
                        a different agent than the author.
                        structural, not a convention.
```

So the task lifecycle **requires** concurrency ≥ 2 to complete a single task. A project cap of 1
means no work can ever be reviewed while any work is in progress.

**Three — concurrency is a poor proxy for the quantity actually named.** The stated worry was a
restricted token plan. Two cheap runs cost less than one expensive one, and `token_budget` already
bounds the real quantity — with the operator carve-out above, which a count of runs cannot express.

**What the status quo already is.** There is no project-wide limit today; the only rule is per-agent
(`turn_scheduler.py:37-43`). So *"let the user control it"* is what ships now, and this item's
correct outcome is to build nothing.

### The finding that outlives the withdrawal

The reason the cap looked cheap and was not is worth keeping, because it applies to **any** future
project-wide limit.

Today, agent A running never blocks agent B, so nothing ever needs to notice A finishing in order to
release B. Any project-wide limit creates that cross-agent blocking — and there is no waker for it:

```
   run ends ──▶ schedule_agent(same agent)          ← exists, 15 call sites
            └─▶ redrain_queued_agents(project)      ← does not exist
```

`agent_trigger.py:1234-1238` records both the reach of the only project-wide drain and the same bug
already measured in narrower form:

> *"Nothing does on a timer: `redrain_queued_agents` is reachable only from project open, settings
> save and relocate. **Measured — an entry sat `queued` at one attempt until an unrelated settings
> save drove the second, which is a limit protecting nobody.**"*

**Rule for the next person who proposes a project-wide limit of any kind: build the release path
first.** A limit without it stops work silently rather than visibly, which is worse than no limit.

## 7. What replaced it — the dependency board

**DECIDED.** Instead of a number that throttles, a picture that informs.

```
   A CAP                          A BOARD
   ─────                          ───────
   a number that throttles        a picture that informs
   the system decides when        the operator decides when
   "you may run 2 at a time"      "here is the shape — start what you like"
```

This lands back on §1's principle from the other side. `spec_tasks.py:39-41` says a specification has
no business deciding who performs work; a concurrency cap says the *system* decides **when** work
happens. Showing the structure and leaving the choice to the operator refuses both.

And it subsumes what §3 wanted `blocked` for. Rather than one bit per card — stuck or not stuck —
the layout carries the whole wave structure:

```
   layer 0  ── ready now ──   [A]      [B]      [C]
                               │        │
                       ┌───────┘        └───┐
   layer 1                    [D]          [E]
                               │            │
   layer 2                     └─────┬──────┘
                                    [F]

   position  = dependency depth
   badge     = status
```

**DECIDED — status moves onto the card, and it is already there.** `TaskCard.tsx:235` renders
`<StatusBadge status={task.status} />` today, where it is redundant with the column it sits in. In a
dependency layout the column is repurposed and the badge becomes the only status signal. The card is
already ready; nothing needs adding to it.

The trade is explicit: **position cannot encode two things.** A dependency layout gives up
status-as-position, which is exactly why the operator said the status must be in the card.

### DECIDED — top to bottom, not left to right

The axes are not symmetric:

| | bounded by | |
|---|---|---|
| **width** — tasks that can run at once | `agent_budget` (8) | small |
| **depth** — length of a dependency chain | nothing | unbounded |

The unbounded axis belongs where scrolling is cheap, and vertical scrolling is free while horizontal
scrolling is avoided. A twelve-task decomposition eight layers deep and two wide is a comfortable
vertical scroll and a miserable horizontal one.

There is a second reason. Left-to-right produces columns of stacked cards — **visually identical to
the existing seven-column kanban**, with the columns silently meaning something else. Two views that
look the same and mean different things is a confusion paid for daily. Top-to-bottom also gives cards
room: the current board is `minmax(160px, 1fr)` across seven columns, and rows fit a title, a status
badge, an assignee and a complexity chip without cramping.

**It is a DAG, not a tree.** A task may depend on several, so edges converge as well as diverge and
there is no parent-per-card. "Tree" is the operator's word for the shape; layered DAG is what it is.

### DECIDED — a second view, toggled

Kanban answers *"what is in flight"*; the dependency board answers *"what can start"*. Neither
subsumes the other, so the seven-column board stays and this is a layout you switch to.

### DECIDED — one board per document, chosen from a picker

The operator's reason: *"As the project goes on and more things park in done it gets overpopulated.
One board for each document I feel is the best approach."*

`Task.spec_document_id` already carries this (`spec_tasks.py:194`), so a per-document board is a
filter on a column that exists.

**DECIDED — hand-made tasks get a standing "no document" board.** A task created by hand has
`spec_document_id = NULL` and would otherwise appear on no board at all — which would make it
unreachable for edge-drawing, contradicting the decision below. The picker lists the real documents
plus one board for the loose tasks. It is a filter on `NULL`, not a new concept.

**DECIDED — a layer whose tasks are all finished collapses to one expandable row.** Scoping to a
document narrowed the overpopulation problem the operator raised but did not solve it: a finished
document's board is still a screen of done cards. Collapsing by layer keeps the DAG's shape intact —
what depended on what is still legible — without the finished half taking the screen.

*Rejected:* hiding terminal tasks behind a toggle. Edges into a hidden task have to render as
something, or the remaining graph looks rootless.

**The picker is worth designing, not just listing.** If it carries each document's open and total
counts, choosing a board and seeing what remains become one act:

```
  ▸ corpus-aware-documents      12 open / 55
  ▸ agent-created-documents      0 open / 35   ✓
  ▸ document-adoption           38 open / 38
  ▸ (no document)                4 open
```

### DECIDED — the document is the only writer of edges. The board draws; it never authors.

**This reverses a decision taken earlier in the same review**, and the operator's reason for
reversing it is the stronger one:

> *"I can't edit existing edges. Only if the document is changed those edges are changed. This would
> break protocol and the documentation."*

An edge that exists only on the board is a fact the specification does not contain — so the
specification is no longer true, and the artefact that is supposed to be the record has been quietly
demoted to a suggestion. Changing a dependency means editing the document.

This removes rather than answers the question the earlier draft left open. There is no *"which fact
wins when a re-approved document disagrees with the operator's edges"*, because there is one writer.

**The cost, named rather than discovered: a hand-made task can never have a dependency.** It belongs
to no document, so nothing can declare its edges, and the "no document" board is a flat set of cards
with no lines. That is consistent rather than broken — a dependency is a property of a declared
decomposition, and a hand-made task is by definition not part of one — but an operator who tries to
draw a line and cannot should find the refusal says so.

### Edges that leave the document

Superseded by §4's imported-task decision, and the per-document board is better for it. A foreign
dependency is **declared in this document** as an imported entry, so:

```
        ┌──────────────────────────────────────┐
        │  ⇡ adopt-corpus                       │  ← an IMPORTED entry in this
        │    from: document-adoption (approved) │    document's own payload.
        └──────────────────┬────────────────────┘    resolves to the real task;
                           │                          never creates one.
                          [A]   [B]
                           └──┬──┘
                             [C]
```

The board never has to query another document to lay itself out. What looked like the price of
per-document scoping turned out to be a property it gains.

## 8. What this becomes

The item is too large for one change. Split on the seams the code already has. The original **4a**
was max concurrent runs and is gone — §6 — and what stood behind it became **4b′**.

| # | Change | Depends on | Size |
|---|---|---|---|
| **4b** | **Dependencies in the payload and the start gate** — `depends_on` on `spec_payload.Task`, imported entries for foreign tasks, `spec_completeness` checking cycles and unknown keys, `materialise()` carrying edges and resolving imports, and the third guard in `task_transition_service` on the `→ in_progress` edge. | nothing | medium |
| **4b′** | **The dependency board** — per-document, top-to-bottom layered DAG, status on the card, read-only structure, document picker with open counts, imported entries drawn as off-board references, regressed-dependency flag. | 4b | medium, and the visible half |
| **4c** | **Complexity and the tier table** — `complexity` on the payload; project-scoped tier→runners mapping, operator-editable, one-to-many, pointing at `Runner` rows so deletion fails loudly. | nothing (payload) / — | medium |
| **4d** | **Auto-assignment** — `materialise()` fills `assignee` from the tier mapping. | 4c | small |

**`complexity` was split out of 4b.** It serves routing; `depends_on` serves the board. They share
nothing but the payload object, so binding them into one change would make the board wait on a tier
vocabulary it does not use.

**4b + 4b′ is the slice worth shipping first.** It is the operator's actual want after §6, it needs
no tier decided, and it is the half with something to look at.

**4d is smaller than it sounds and that is the finding worth carrying:** `ENTRY_STATUSES` already
includes `assigned`, so materialising a task directly as assigned is legal under the machine as
written. Auto-assignment is filling in two `None`s at `spec_tasks.py:192-193` — not a subsystem.

## 9. Still open, and genuinely the operator's

- **Does a tier name a model, or a (model, effort) pair?** The second is better and costs building
  `Runner.flags` support that nothing has yet. (The tier *names* are decided — §5.)
- **Cross-document cycles** (§4). Within-document cycle detection is a small addition to
  `spec_completeness`; across documents it needs the corpus, and only part of it may be adopted here.
- **Whether an agent may declare a task's complexity** (§5). The exploration notes that *"an agent
  writing 'this needs Opus 5' is an agent committing the operator's money"*, and complexity is one
  indirection from a model choice. `decide_evidence` already refuses an agent deciding evidence it
  produced (`mcp_server.py:1127`) — the same shape, unresolved here. **This is what blocks 4c.**
- **Does review become the bottleneck in practice?** (§4.) Metering a dependency chain against review
  latency is the kind of thing only real use answers.
- **Least-loaded or round-robin** (§5, Q2).
- **Should assignment ever start work?** Recommended as a firm non-goal, but it is the question
  behind "does approving a document make eight agents wake up", and leaving it unanswered means
  someone answers it by accident later. §4's gate makes the accidental version harmless — an
  assigned task with unmet dependencies still cannot start — which lowers the stakes without
  answering it.

**Two questions the earlier draft carried are now closed rather than open**, and are recorded here so
they are not reopened by someone reading only the section they lived in:

- *Which fact wins when a re-approved document's edges disagree with the operator's?* — no longer
  reachable. The document is the only writer (§7).
- *What happens to a task that is both `blocked` and dependency-unmet?* — no longer reachable. An
  unmet dependency prevents reaching `in_progress`, and `blocked` is only reachable from it (§4).

## 10. Not covered

The model catalog (§8 of the previous exploration, carve-up item #5) stays where it is: independent
of all of this, and carrying its own governance question about an agent that can expand what it is
allowed to spend money on.
