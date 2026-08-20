# Exploration — What a specification may say about who does the work (2026-08-20)

**Status:** Explored 2026-08-20, carrying forward decisions the operator took in
`2026-08-20-the-row-is-the-spine.md` §6–§7. This is carve-up item **#4** — the largest of the five,
and the one that was left open rather than proposed because six routing questions were unanswered
and the tiers themselves were undefined.

Every claim below was checked against the code; `file:line` is given so the next reader can re-check
rather than trust. **Three of the previous exploration's proposals do not survive that check** and
are withdrawn in §3, §4 and §6. That is the main value of this document.

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

**Recommendation: three named tiers, and resist a second axis until a real decomposition needs
one.** But this is the operator's, and it should be decided before anything writes a tier into a
document.

## 6. Max concurrent runs — the cap is trivial, the release is the whole problem

**DECIDED already** (previous exploration §7): parallelism is opt-in, a project setting, default 1.
*"He could be using a restricted token plan and need to do things one at a time."*

`Project` already carries four budget columns (`models.py:71-81`), so a fifth has an obvious home,
and `schedule_agent` is called from **fifteen call sites** — so a check placed inside it is enforced
everywhere at once. That part is a morning's work.

**The part that is not:** what wakes the next agent when a run finishes.

Today the scheduler's only concurrency rule is per-agent (`turn_scheduler.py:37-43`) — *"agent is
already running"*. Agent A running never blocks agent B, so nothing ever needs to notice A finishing
in order to release B. A **project-wide** cap creates exactly that cross-agent blocking, and there
is no waker for it.

`redrain_queued_agents` is the only project-wide drain, and `agent_trigger.py:1234-1238` records both
its reach and a measured failure:

> *"Nothing does on a timer: `redrain_queued_agents` is reachable only from project open, settings
> save and relocate. **Measured — an entry sat `queued` at one attempt until an unrelated settings
> save drove the second, which is a limit protecting nobody.**"*

That is this exact bug, already observed once in a narrower form. Shipping a project cap without a
release path reproduces it deliberately and at larger scale: with `max_concurrent_runs = 1`, every
agent but one waits until the operator happens to save a setting.

```
   run ends ──▶ schedule_agent(same agent)          ← exists today
            └─▶ redrain_queued_agents(project)      ← MISSING. the whole feature.
```

**The change is small and it is the load-bearing part**: every path where a run reaches a terminal
state must re-drain the project, not only its own agent. It should be built and tested *first*, not
last — a cap without it is worse than no cap, because work stops silently rather than visibly.

**Open:** re-draining the project on every run completion is O(agents) scheduling attempts per
completion. At `agent_budget = 8` that is fine. It is worth knowing it is not free.

## 7. What this becomes

The item is too large for one change. Split on the seams the code already has:

| # | Change | Depends on | Size |
|---|---|---|---|
| **4a** | **Max concurrent runs** — the project setting, the check in `schedule_agent`, and the project re-drain on run completion. | nothing | small, and useful alone |
| **4b** | **Complexity and dependencies in the payload** — two payload fields, `spec_completeness` checks, `materialise()` carrying them onto the task, readiness computed. No routing. | nothing | medium |
| **4c** | **The tier table** — project-scoped tier→runners mapping, operator-editable, one-to-many, pointing at `Runner` rows so deletion fails loudly. | 4b | medium |
| **4d** | **Auto-assignment** — `materialise()` fills `assignee` from the tier mapping. Legal without touching the transition machine, because `assigned` is already an entry status. | 4b, 4c | small |

**4a is worth doing on its own merits**, independent of the whole tier idea: it is the operator's
stated want, and the missing project re-drain is a latent defect the moment any project-wide limit
exists.

**4d is smaller than it sounds and that is the finding worth carrying:** `ENTRY_STATUSES` already
includes `assigned`, so materialising a task directly as assigned is legal under the machine as
written. Auto-assignment is filling in two `None`s at `spec_tasks.py:192-193` — not a subsystem.

## 8. Still open, and genuinely the operator's

- **What are the tiers?** (§5, Q6.) Decide before anything writes one into a document.
- **Does a tier name a model, or a (model, effort) pair?** The second is better and costs building
  `Runner.flags` support that nothing has yet.
- **Cross-document dependencies** (§4). Recommended out of scope, but the carve-up itself is a
  five-item dependency chain across five documents, so the limit will be felt immediately.
- **Least-loaded or round-robin** (§5, Q2).
- **Should assignment ever start work?** Recommended as a firm non-goal here, but it is the question
  behind "does approving a document make eight agents wake up", and leaving it unanswered means
  someone answers it by accident later.

## 9. Not covered

The model catalog (§8 of the previous exploration, carve-up item #5) stays where it is: independent
of all of this, and carrying its own governance question about an agent that can expand what it is
allowed to spend money on.
