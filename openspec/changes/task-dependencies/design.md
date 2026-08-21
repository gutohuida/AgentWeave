# Design — task dependencies

## Context

Four things are already true, and most of this design is a matter of composing them rather than
building.

1. **Task keys are stable identifiers.** *"A stable handle for this task, unique within the document…
   Keep it across rewordings"* (`spec_payload.py:99`). A dependency graph needs no new identifier
   scheme.
2. **There is one place every status write passes through**, and it already holds two guards, with a
   comment explaining why that placement is what makes them unbypassable
   (`task_transition_service.py:208-217`).
3. **`materialise()` is mature.** It resolves requirement keys through two maps, dedupes by
   `(document, key)`, respects an owning `Loop`, credits hand-made tasks, and preserves unresolvable
   names as free text rather than refusing (`spec_tasks.py:89-214`).
4. **Incompleteness is reported, not refused** (`spec_service.py:98-101`). A document under
   discussion is expected to be incomplete; the transition to `proposed` is what cares.

## Goals

- A document can say what order its own work goes in, and that statement travels with the repository.
- A task cannot start before its prerequisites are done.
- The operator can see the shape of a decomposition and choose what to start.

## Non-goals

- Deciding *who* does the work. That is `complexity` and the tier table, deliberately excluded.
- Any continuous invariant. Every rule here fires on an edge.

## Decisions

### D1 — A dependency is a precondition on an edge, not a property of a task

**Rejected: materialising dependent tasks as `blocked`.** Three independent refusals, each written
down in `task_transitions.py`:

| | |
|---|---|
| `ENTRY_STATUSES = {"pending", "assigned"}` (`:94`) | *"a lifecycle that can be entered anywhere is not a lifecycle"* |
| `blocked` reachable only from `in_progress` (`:120`) | *"a task nobody has started is not blocked, it is pending"* |
| `blocked` means (`:118`) | *"work that started and then hit something only a person can supply"* |

**Rejected: a stored `ready` column.** It would be a denormalisation of a join, correct only until
something forgot to recompute it, and it would need recomputing on every transition of every
prerequisite.

**Chosen: a third guard, in the place the other two live.**

```
   pending ──▶ in_progress     GATED — every dependency must be `approved`
           ──▶ assigned        not gated
           ──▶ rejected        not gated

   (blocked ──▶ in_progress is the resume edge and is gated the same way:
    a task that was blocked and is now unblocked must still satisfy its
    dependencies to resume.)
```

Leaving `→ assigned` open is load-bearing for auto-assignment later: a whole wave can be assigned
up front and each task starts when its own prerequisites clear. Gating assignment would make
assigning ahead impossible and force routing to run repeatedly as waves complete.

### D2 — Met at `approved`, not at `completed`

The stricter reading. Two consequences, one intended and one not.

**Intended: a dependency chain cannot advance with a single agent.** Author/reviewer separation is
structural — `ActorNotPermittedError`, guarded at `task_transition_service.py:119` — so
`completed → under_review → approved` needs a second agent.

```
   layer 0   agent A builds ──▶ completed ──▶ agent B reviews ──▶ approved
                                                                     │
   layer 1                                    agent A can now start ◀┘
```

**Unintended, and worth protecting: a chain cannot advance past unverified work.** The `→ approved`
edge already runs `requirement_gate.evaluate`, which at `gate` rigor refuses while any of the task's
requirements is unverified. Two gates on one edge means the second guards the first for free.

**The cost is real and is a requirement, not a caveat.** The bottleneck moves to review. If review is
not happening, the board stalls at layer 1 and every downstream card is gated — which looks exactly
like the feature failing. D8 is the mitigation.

### D3 — Edges are stored as rows, not as a JSON list on the task

A join table (`task_dependencies`: `task_id`, `depends_on_task_id`) rather than
`Task.depends_on: JSON`.

The gate asks *"are all my prerequisites approved"* — a join. The board asks both directions: what
blocks this, and what does this block. A JSON array answers the first badly and the second not at
all, and it cannot be indexed. `requirement_links` is the existing precedent for a link table between
a task and something else.

**Open — foreign key or not.** There is a precedent for deliberately *not* having one:
`Question.blocked_task_id` carries *"no ForeignKey… the block record must outlive a deleted task
rather than cascade or refuse"* (`models.py:901-903`). The reasoning does not obviously transfer: a
dependency on a deleted task is not a record worth keeping, it is a graph with a hole. **Leaning
towards a foreign key with cascade delete**, so a deleted task takes its edges with it — but the
precedent is close enough that it deserves an explicit decision rather than a default.

### D4 — A foreign dependency is an imported entry in this document

**Rejected: a qualified key** (`"adopt-corpus@spec/…/spec.html"`) in `depends_on`. It puts path
parsing into a field whose grammar is currently "a key", and it means an authoring agent must learn
two forms of the same thing.

**Rejected: deriving an off-board reference** from a task-level edge the operator drew. Superseded by
D5 — there is no operator-drawn edge.

**Chosen: the document declares the foreign task as an entry of its own, marked as imported. Local
tasks then depend on it by local key like any sibling.**

```
   document B's payload
   ┌──────────────────────────────────────────────────────┐
   │  tasks:                                               │
   │    - key: adopt-corpus            ← IMPORTED          │
   │      from: <approved document A>, key: adopt-corpus   │
   │                                                       │
   │    - key: render-map                                  │
   │      depends_on: [adopt-corpus]   ← an ordinary       │
   │                                     local key         │
   └──────────────────────────────────────────────────────┘
```

Three properties follow. `depends_on` stays a list of local keys, so nothing about the field's
grammar changes. The dependency is visible to a **reader of the document**, which is the point of
putting it in the specification rather than the UI. And — the property that makes this right rather
than merely workable — **the per-document board becomes closed**: everything it must draw is declared
in the one document it is scoped to, and it never queries another document at layout time.

`materialise()` gains exactly one rule: **an imported entry resolves to the existing task and never
creates one.**

**Implementation shape, decided at task 1.3: a discriminator field on `Task` (`from`), not a
separate list.** Built a real cross-document payload both ways before choosing. A discriminator
keeps the imported entry inside the same `tasks:` list a sibling's `depends_on` already indexes by
key — one collection, no second list to cross-reference when materialising, rendering a nav strip,
or checking for a duplicate key. The alternative, a separate `imported_tasks: List[dict]`, keeps an
ordinary `Task` structurally simpler (no field required for one kind of entry and forbidden for
another) but forces every consumer of `depends_on` — the gate, the board, `materialise()` — to look
in two lists to resolve one key. The discriminator also matches this section's own diagram above
literally: the imported entry is drawn *inside* `tasks:`, marked "← IMPORTED", not in a second
block. Landed as `hub/hub/spec_payload.py`'s `Task.from_` (aliased to the reserved word `from`,
`Optional[ImportedFrom]`, `ImportedFrom` a `{document, key}` submodel rather than a raw dict so a
malformed import is an ordinary field error, the same mechanism every other nested part uses).
`description` and `requirements` became optional on `Task` as a consequence — an imported entry
carries neither.

### D5 — The document is the only writer of edges

The operator, reversing an earlier decision in the same review: *"I can't edit existing edges. Only
if the document is changed those edges are changed. This would break protocol and the documentation."*

An edge that exists only on the board is a fact the specification does not contain, which quietly
demotes the artefact meant to be the record. This also removes rather than answers the question of
what happens when a re-approved document disagrees with an operator's edits: there is one writer.

**Consequence, to be surfaced rather than discovered: a hand-made task can never have a dependency.**
It belongs to no document, so nothing can declare its edges. An operator who tries should get a
refusal that says why.

### D6 — Imports name approved documents only, and that is a rename rule

An import is a `(document path, task key)` reference. Paths move — `rename_document` derives a new
path from a subject — so the reference needs the path to be stable.

It nearly is. `rename_document` refuses on `document.phase == APPROVED` because *"its path is part of
what was approved"*. But `approved` has two exits (`spec_lifecycle.py:45,50`):

```
                    ┌──▶ (APPROVED, ARCHIVED)     ← path unfreezes
   approved ────────┤
                    └──▶ (APPROVED, EXPLORING)    ← path unfreezes
```

**This is a latent hole independent of this change**: today an approved document's path can be
changed by archiving it first, which the refusal's own reason does not intend.

**Chosen: refuse rename for a document that has *ever* been approved.** Monotone, faithful to the
stated reason, and reopening for revision does not un-approve history.

The durable fact follows `explore_closed_at`'s shape (`models.py:1649`) — a nullable timestamp
recording a one-way event — **with one difference that must be commented where the column is added**:
`explore_closed_at` is deliberately reset on reopen (*"reopening genuinely reopens"*,
`spec_lifecycle.py:253-257`) and `first_approved_at` never is.

Restricting imports to approved documents buys a second thing, unasked: **the foreign task is
guaranteed to exist**, because an approved document has already materialised.

**Rejected: refusing rename only when a document has dependents.** It targets the problem exactly,
but needs a corpus-wide query at rename time and can only see documents this machine has adopted.

### D7 — Checks are reported at submission and enforced at proposal

An agent authoring document B will often write the import while A is still exploring. Refusing the
submission would make B unwritable until its prerequisite settled — which is the opposite of how the
product treats incomplete documents.

So all three new checks — unresolved `depends_on` key, within-document cycle, import naming a
non-approved document — are **reported in `blocking`** and refused at propose/approve. Same pattern,
same place, nothing new.

A **dangling import** at materialise time follows the existing precedent rather than inventing one:
unresolvable requirement names are *"preserved rather than dropped… the unrecognised name is the
evidence of what went wrong"* (`spec_tasks.py:204-206`).

**Addendum, decided at task 4.3: its own table, `task_dependency_references`, not
`task_requirement_references`.** The two are different facts — a dangling requirement reference is a
string that never named anything this project has; a dangling dependency reference is a `depends_on`
key that names a real entry in *this* document (so `spec_completeness` already accepted it) whose
import target could not be resolved to an existing task at materialise time. Sharing the table would
mean a reader can no longer tell a broken reference from a broken edge without also reading `reason`,
and the two tables' `reason` vocabularies do not overlap (`unknown`/`ambiguous`/`unparsed` vs.
`document_not_found`/`document_not_approved`/`key_not_found`/`malformed_import`). In practice this
case should be rare: `import_not_approved` already refuses `propose()` for exactly this condition,
so the only way `materialise()` (which runs at `approve()`, a later moment) meets it is the document
being reopened in the window between the importing document's `propose()` and its `approve()` — the
race this addendum exists to name. Rows are replaced wholesale per task on every `materialise()`
call, mirroring `absorb_free_text`'s `replace=True` default, so a reference that resolves on a later
approval is removed rather than left stale.

**Addendum, decided at task 4.4: a revision may add a new edge to a task an earlier approval already
materialised.** The existing rule in `spec_tasks.py`'s own module docstring — *"a task that already
exists is never touched"* — predates dependencies and is about the task **row**: status, assignee,
description. It says nothing about incoming edges, because none existed yet when it was written.
Read against D5 (*"the document is the only writer of edges"*), the two rules do not conflict, they
compose: the document is the only place an edge can ever be declared, so if a revision adds a new
`depends_on` naming an already-materialised task, re-approving is the only way that edge is ever
recorded at all — refusing it would make `depends_on` write-once for a task that gained a dependency
after its first approval, which nothing in D1–D7 asks for. What the rule still protects, and what
`_materialise_edges` deliberately preserves: nothing here ever *removes* an edge a prior approval
created, even if a revision's `depends_on` no longer names it — same one-directional caution
`existing_keys` already gives task creation itself.

### D8 — The board draws depth downward, and must distinguish stalled from gated

**Top to bottom, because the axes are not symmetric.** Width is bounded by `agent_budget` (8); depth
is unbounded. The unbounded axis belongs where scrolling is cheap. Left-to-right would also render as
columns of stacked cards — visually identical to the existing seven-column kanban with the columns
silently meaning something else.

It is a **layered DAG, not a tree**: edges converge as well as diverge, so there is no parent per
card.

**Status moves onto the card, and is already there.** `TaskCard.tsx:235` renders
`<StatusBadge status={task.status} />` today, where it is redundant with the column it sits in. In a
dependency layout the position is repurposed and the badge becomes the only status signal. Position
cannot encode two things.

**Three states the board must distinguish**, because they look identical as "a card that will not
start" and have completely different remedies:

| | what it means | remedy |
|---|---|---|
| gated | prerequisites not yet approved | wait, or review them |
| **stalled on review** | prerequisites `completed`, nothing reviewing | assign a reviewer |
| gated on rejected | a prerequisite was rejected and never will complete | reopen it, or edit the document |

The middle one is D2's risk made visible. *"Layer 2 is waiting on 3 reviews"* is the difference
between a working feature and one that looks broken.

**A running task whose dependency regressed is flagged, not stopped.** `approved → revision_needed`
is operator-only, so this is rare and always an explicit act. Enforcement is a guard; awareness is a
display; keeping them apart is what stops an agent losing its task mid-turn.

### D9 — One board per document, plus one for tasks that have none

`Task.spec_document_id` already exists (`spec_tasks.py:194`), so a per-document board is a filter on a
column. The operator's reason: *"As the project goes on and more things park in done it gets
overpopulated."*

Hand-made tasks have `spec_document_id = NULL` and get a standing "no document" board — a filter on
`NULL`, not a new concept. Per D5 it will never have edges; it is a flat set of cards.

**A finished layer collapses to one expandable row.** Scoping narrowed the overpopulation problem but
did not solve it: a finished document's board is still a screen of done cards. Collapsing by layer
keeps the DAG's shape legible. *Rejected: hiding terminal tasks* — edges into a hidden task have to
render as something or the remaining graph looks rootless.

**The picker carries counts**, so choosing a board and seeing what remains are one act.

### D10 — The loop's claim must consult the gate, or this change deadlocks every loop

**Added 2026-08-20, after the gap was found in review.** This design originally said nothing about
loops, which would have shipped a guaranteed deadlock. From
`openspec/explorations/2026-08-20-the-loop-under-dependencies.md` §2:

```
   firing 1   claim oldest pending ──▶ assigned       (D1 leaves → assigned UNGATED)
              agent attempts → in_progress ──▶ REFUSED by the gate
              task remains `assigned`
   firing 2   `assigned` sorts above every `pending`  ──▶ re-claims THE SAME task
   firing 3   ⟳ forever. Startable work is never reached.
```

Two locally-correct decisions produce it, and neither is wrong alone. D1 deliberately leaves
`→ assigned` ungated so a whole wave can be assigned in advance. `_loop_queue_order` deliberately
sorts non-pending above pending so an unfinished task is resumed rather than stranded — a fix made
2026-08-19 whose own comment predicts this exact cost: *"a task the agent genuinely cannot start is
now re-claimed every firing, so the loop repeats one item instead of spinning on none."* That trade
was taken against an occasional agent-behaviour problem. **Dependencies make it a structural
certainty**: every dependent task is unstartable by design until its prerequisite is approved.

**Chosen: the claim consults the same dependency determination the gate uses**, and skips unstartable
tasks in order rather than stopping at the first. Claimability and startability agreeing is the whole
fix.

*Rejected:* **gating `→ assigned` as well.** It would stop the loop claiming unstartable work, but it
discards D1's reason for leaving that edge open and breaks auto-assignment before it is built.

*Rejected:* **a separate readiness computation for the loop.** Two implementations of "are this
task's dependencies met" is the drift shape `_loop_queue_order`'s comment already records —
*"two consistent wrong answers read as a match, which is how it survived review."*

**A queue gated on a `rejected` prerequisite stalls; it does not stop.** Tempting to treat as
§8's *"nothing ready EVER"* and end the loop, but `rejected → pending` is operator-only and therefore
reversible, while stopping sets `job.enabled = False` and calls `remove_job` — so the operator
reversing the rejection afterwards could not revive the loop. Same reasoning that chose *skip* over
*stop* for the stall on 2026-08-20. The stall reason distinguishes the two kinds of gating, because
the remedies differ.

**Sequencing.** `loop-notices-and-reacts` introduces the one shared claim-decision function that both
`_do_fire_job` and `_batch_loop_summaries` call. This change adds a dependency branch to it. Landing
that change first makes this a branch; landing this first means building the shared function here and
rewriting it there.

## Risks

**Review becomes the bottleneck and nobody notices.** D8's middle state is the whole mitigation, and
it is a display rule protecting a lifecycle rule — a weaker kind of protection than a guard.

**A five-deep chain needs five review cycles.** Whether that is acceptable is a question only real
use answers, and it is worth metering rather than assuming.

**The board is a second view of the same tasks.** Two layouts diverge under maintenance. Sharing
`TaskCard` is what keeps them honest; a board that grows its own card component is the failure.

**Layout of a layered DAG is not trivial** once edges are long. Minimising crossings is a known hard
problem, and "good enough" needs defining before it is implemented rather than after.

## Migration plan

1. Payload fields and their descriptions — inert; nothing reads them.
2. `spec_completeness` checks — reported only, blocking nothing that was not already blocked.
3. Migration `0083`: edge table, `first_approved_at` backfilled from the `kind="phase"` event history.
4. `materialise()` creates edges and resolves imports.
5. The guard. **This is the first step that changes behaviour**, and every existing project gains it
   at once — which is safe only because a task with no declared dependencies has none to fail.
6. The rename refusal.
7. The board.

Steps 1–4 are observable-but-inert: edges exist and nothing enforces them, which is a good state to
sit in for a release if the guard needs more confidence.

## Open questions

- **Foreign key on the edge table, or not?** (D3.) `Question.blocked_task_id` is a close precedent for
  *not*, with reasoning that does not obviously transfer.
- **Cross-document cycles.** Out of scope, and the limit should be stated in the checks' own message
  rather than left silent — a reader who sees cycle detection will assume it is complete.
- **Does a task's own document being reopened affect its dependents?** `approved → exploring` is
  legal for a document. Its tasks are untouched — `materialise` never modifies an existing task — so
  presumably nothing happens. Unexamined.
- **Should the board show requirement coverage per card?** It is the other thing gating `→ approved`,
  and a card that cannot be approved for coverage reasons stalls a wave exactly as a dependency does.
