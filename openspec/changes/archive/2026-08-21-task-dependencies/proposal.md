# Task dependencies, the start gate, and a board that shows the shape

## Why

A specification declares tasks. It cannot declare their order, so approval produces a flat set of
work all claiming to be ready at once. The operator asked for two things: that the specification say
which tasks can run in parallel, and that the board show it.

The gap is one field wide. `spec_payload.Task` (`hub/hub/spec_payload.py:98-108`) carries `key`,
`title`, `description` and `requirements` — and `key` is already *"a stable handle for this task,
unique within the document"*, so the identifiers a dependency graph needs already exist and are
already stable across rewordings. Nothing declares an edge between them; `depends_on` appears
nowhere in the Hub outside Alembic's own boilerplate.

**What makes this cheap is that the enforcement point already exists, twice.**
`hub/hub/task_transition_service.py:208-217` holds two guards in one place, with a comment stating
why that place is the right one:

```python
await _guard_author_is_not_reviewer(session, task, to_status, actor)   # guard, on the review edges

# "The gate, on this one edge. Inside the service and before the history row, so it cannot be
#  bypassed by a caller reaching the row a different way — which is also why every surface
#  (operator route, agent HTTP, the tool surface, jobs) gets it without knowing it exists."
if to_status == "approved":
    refusal, policy = await evaluate(session, task)                    # requirement_gate
```

A dependency gate is the third guard in that same position, on the `→ in_progress` edge. No new
status, no stored readiness, no per-surface enforcement.

**And the alternative was checked and refused.** An earlier design proposed materialising dependent
tasks as `blocked`. That is illegal three ways: `blocked` is not in `ENTRY_STATUSES`
(`hub/hub/task_transitions.py:94`) and the rule exists because *"a lifecycle that can be entered
anywhere is not a lifecycle"*; it is reachable only from `in_progress` because *"a task nobody has
started is not blocked, it is pending"* (`:120`); and it means *"work that started and then hit
something only a person can supply"* (`:118`), which a sibling task is not.

The operator's framing is what resolved it: *"A task won't be stopped by a dependency… it should
never start if a dependency is not met."* Stopped and never-started are different states, and the
transition machine already distinguishes them.

## What Changes

**In the specification**

- **New**: `depends_on` on `spec_payload.Task` — keys of sibling tasks that must finish first.
- **New**: an **imported task entry** — a task belonging to another document, declared in this one so
  that a local task may depend on it. `depends_on` stays a list of local keys.
- An import may name **only an approved document**. This freezes the reference (see below), and it
  also guarantees the foreign task exists: an approved document has already materialised.
- `spec_completeness` gains three checks: a `depends_on` key that resolves to nothing, a cycle within
  the document, and an import naming a document that is not approved. All **reported as blocking**,
  not refused at submission — *"incompleteness is reported, not refused… it is the transition to
  `proposed` that cares"* (`hub/hub/spec_service.py:98-101`).
- `materialise()` creates the declared edges, and **resolves an imported entry to the existing task
  rather than creating one**.

**In the lifecycle**

- **New**: a third guard in `task_transition_service`, on `→ in_progress`. A task whose dependencies
  are not all `approved` cannot start.
- `→ assigned` is **not** gated. Assigning work that cannot start yet is legitimate, and it is what
  lets a whole wave be assigned in advance.
- A dependency is met at **`approved`**, not at `completed`.

**In the corpus**

- `rename_document` refuses for a document that has **ever** been approved, not only one currently
  approved. Today the check is `phase == APPROVED` (`hub/hub/spec_service.py:638-641`) and `approved`
  has two exits — to `archived` and back to `exploring` — so an approved document's path can be
  changed by archiving it first. That contradicts the refusal's own stated reason, independently of
  this change.

**On screen**

- **New**: a dependency board — per document, chosen from a picker, laid out top to bottom as a
  layered DAG, with status on the card.
- Structure is **read-only**. The document is the only writer of edges.
- Imported entries render as off-board references naming their document.
- A layer whose tasks are all finished collapses to one expandable row.
- A task gated on rejected work, and a task running on a dependency that regressed, are each
  surfaced.

**Non-Goals** — stated explicitly, not by omission:

- **Not** `complexity`, tiers, routing or auto-assignment. Those serve a different question and need
  a tier vocabulary this change does not use.
- **Not** operator-editable edges. *"Only if the document is changed those edges are changed. This
  would break protocol and the documentation."* An edge that exists only on the board is a fact the
  specification does not contain.
- **Not** dependencies on hand-made tasks. A task belonging to no document has no document to declare
  its edges. The refusal should say so rather than silently doing nothing.
- **Not** replacing the seven-column status board. This is a second view.
- **Not** halting a running task whose dependency regressed. The gate is a precondition on an edge,
  not a continuous invariant; a running task is flagged, not stopped.
- **Not** cross-document cycle detection. Within-document cycles are checked; a cycle spanning
  documents needs the whole corpus, only part of which may be adopted on a given machine.
- **Not** starting work. Assignment and readiness fill in and reveal; nothing here enqueues a turn.

## Capabilities

### New Capabilities

- `task-dependencies`: how a document declares the order of its own work, how a dependency crosses a
  document boundary, when a dependency counts as met, and what an unmet one prevents.
- `task-dependency-board`: the per-document layered view — what it draws, what it refuses to let you
  edit, and what it must say when work is stalled.

### Modified Capabilities

- `task-lifecycle-governance`: gains a third guard, on the `→ in_progress` edge, and the rule that
  starting is gated while assigning is not.
- `spec-document-authority`: a document's path is frozen once it has ever been approved, rather than
  while it is approved.

## Impact

**Code**

- `hub/hub/spec_payload.py` — `depends_on`, the imported-entry shape, and their `Field(description=)`
  strings, which *are* the agent-facing instructions.
- `hub/hub/spec_completeness.py` — three new checks.
- `hub/hub/spec_tasks.py` — create edges; resolve imports without creating.
- `hub/hub/task_transition_service.py` — the third guard.
- `hub/hub/spec_service.py` — the rename refusal.
- `hub/hub/db/models.py` — a task-to-task edge, and the durable "has been approved" fact.
- `hub/hub/api/v1/tasks.py` — dependency state on the task read model.
- `hub/ui/src/components/tasks/` — the board, the picker, layer collapse.

**Data**

Migration `0083` (head is `0082`): the edge storage, and `SpecDocument.first_approved_at`.
`explore_closed_at` (`hub/hub/db/models.py:1649`) is the precedent for the second — with one
difference that must be commented where it is added: `explore_closed_at` is deliberately **reset** on
reopen (`hub/hub/spec_lifecycle.py:253-257`, *"reopening genuinely reopens"*), and this one never is.

**What this makes true without being asked**

Because the dependency gate and `requirement_gate` sit on the same edge, and a dependency is met at
`approved`, **a dependency chain cannot advance past unverified work** at `gate` rigor. That is worth
knowing before someone moves either gate.

**Risk**

The bottleneck moves to review. Every wave now passes through `completed → under_review → approved`,
and author/reviewer separation means a second agent. A five-deep decomposition needs five review
cycles; if review is not happening, the board stalls at layer 1 with everything downstream gated —
and a review backlog will be indistinguishable from the feature being broken unless the board says
which. That is a requirement, not a caveat.
