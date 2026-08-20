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

## 4. Where dependencies live, and the one thing that makes it cheap

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

**Open — and it matters more than it looks.** Dependencies are scoped *within one document*, because
`key` is only unique within a document. Real work crosses documents: "the landing page needs adoption
to land first" is exactly the dependency between two of the five carve-up items, and it cannot be
expressed. Cross-document dependencies need a task-level edge (`Task.depends_on_task_id` or a join
table), not a payload field. **Recommendation: ship within-document only, and say so explicitly as a
non-goal rather than leaving the reader to discover the limit.**

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

**The picker is worth designing, not just listing.** If it carries each document's open and total
counts, choosing a board and seeing what remains become one act:

```
  ▸ corpus-aware-documents      12 open / 55
  ▸ agent-created-documents      0 open / 35   ✓
  ▸ document-adoption           38 open / 38
  ▸ (no document)                4 open
```

### DECIDED — the spec declares edges and the operator may edit them

`depends_on` in the payload covers tasks materialised from a document. The operator also makes tasks
by hand, and those would otherwise all be roots. Both, then: declared dependencies arrive with the
task, and the operator can add or remove edges on the board.

This is the first place the payload and the board both write the same fact, and the rule needs
stating when it is designed: the document declares the decomposition's *intent*, the board holds what
is *true now*, and re-approving a document must not silently redraw edges the operator changed —
consistent with `spec_tasks.py:19-21`, *"a task that already exists is never touched."*

### The cost of per-document scoping, and one way to soften it

A dependency crossing two documents cannot be drawn on either board. That shape is immediate: this
project's own carve-up is five items depending on each other across five documents.

An edge leaving the board can be shown as an off-board reference rather than dropped:

```
        ┌──────────────────────────────┐
        │  ⇡ document-adoption          │  ← names the document and the
        │    task: "adopt a corpus"     │    task. not a card to act on.
        └───────────────┬───────────────┘
                        │
                       [A]   [B]
                        └──┬──┘
                          [C]
```

The blocker stays visible and reachable without the board becoming the whole project. **Open:**
whether that requires a task-level edge (`Task.depends_on_task_id` or a join table) in addition to
the within-document payload field. §4 recommended within-document only; the off-board stub is what
makes that recommendation survivable rather than merely cheap.

## 8. What this becomes

The item is too large for one change. Split on the seams the code already has. The original **4a**
was max concurrent runs and is gone — §6 — and what stood behind it became **4b′**.

| # | Change | Depends on | Size |
|---|---|---|---|
| **4b** | **Dependencies in the payload** — `depends_on` on `spec_payload.Task`, `spec_completeness` checking cycles and unknown keys, `materialise()` carrying them onto the task, readiness computed rather than stored. | nothing | medium |
| **4b′** | **The dependency board** — per-document, top-to-bottom layered DAG, status on the card, operator-editable edges, document picker with open counts, off-board stubs for edges that leave. | 4b | medium, and the visible half |
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
- **Cross-document dependencies** (§4, §7). Recommended out of scope, but per-document boards make
  the limit structural rather than merely present, and this project's own carve-up is exactly that
  shape. The off-board stub in §7 is the proposed softening, and it may still need a task-level edge.
- **Which fact wins when a re-approved document's declared edges disagree with the operator's** (§7).
  `spec_tasks.py:19-21` — *"a task that already exists is never touched"* — points at the answer but
  does not cover edges, which did not exist when it was written.
- **Least-loaded or round-robin** (§5, Q2).
- **Should assignment ever start work?** Recommended as a firm non-goal, but it is the question
  behind "does approving a document make eight agents wake up", and leaving it unanswered means
  someone answers it by accident later.
- **Does the dependency board need its own readiness rule for `blocked` tasks?** A task that is
  `blocked` (waiting on a person) and also has unmet dependencies is stopped for two unrelated
  reasons. The board shows one; the badge shows the other. Probably fine, unexamined.

## 10. Not covered

The model catalog (§8 of the previous exploration, carve-up item #5) stays where it is: independent
of all of this, and carrying its own governance question about an agent that can expand what it is
allowed to spend money on.
