# A materialised task carries its criteria

## Why

A specification document already holds binary, testable acceptance criteria — `AcceptanceCriterion`
is `key`, `requirement`, `given`, `when`, `then`, and `then` is documented as *"the observable
outcome. Binary — it either happened or it did not"* (`hub/hub/spec_payload.py:91-100`).

`spec_tasks.materialise()` never carries them to the task it creates. The `Task(...)` constructed at
`hub/hub/spec_tasks.py:205-217` sets title, description, status, priority, assignee, assigner,
`spec_document_id`, `spec_task_key` and `loop_id`, and never `acceptance_criteria`. The column
exists and is nullable (`hub/hub/db/models.py:684`). Requirements are linked
(`spec_tasks.py:221-222`); the criteria that demonstrate them are dropped.

The loop briefing then renders `criteria = claimed_task.acceptance_criteria or []`
(`hub/hub/scheduler.py:2456-2460`) for both the implementer and the reviewer. For a reviewer that
block is introduced by *"What the author was asked to build. This is the standard you check their
work against, not an instruction to you."* (`scheduler.py:2444-2447`) — and is then followed by
nothing. A reviewer gets no requirement identifiers either:
`_briefing_evidence_lines()` returns `[]` when `is_review` is true, by design
(`scheduler.py:2316-2318`).

So a reviewer of a spec-materialised task is told what standard to apply and handed the task's title
and description to apply it with. The standard has to be re-derived from the codebase.

**Measured, read-only against the live Hub's database, project `LoopEngine`
(`proj-03b9c6a6c37a`), 2026-09-12 to 2026-09-16:**

| task origin | tasks | with acceptance criteria |
|---|---|---|
| hand-made (`spec_task_key IS NULL`) | 18 | **18** |
| spec-materialised (`spec_task_key IS NOT NULL`) | 32 | **0** |

Not one spec-materialised task in that corpus carried a criterion. Over the same window the project
spent **470M of its 481M input tokens on cached re-reads** to produce 3.7M output tokens — 0.77% —
and the reviewing agent averaged **1,898,949 input tokens per turn** across the 42 turns that both
carried usage and could be classified by their tool calls. (That agent has 62 measured turns in
total; 47 of them could be classified this way, of which 42 executed something. The 42-of-47 figure
is a subset statistic and is stated as one here — the earlier phrasing implied 47 was its whole
measured population, which it is not.) The full measurement, its method and its blind spots are in
`openspec/explorations/2026-09-16-the-flow-costs-more-than-the-work.md`.

Why now: the explorations that follow this one (an iteration budget, a single end-of-task gate, and
moving orchestration out of the coordinating agent) all assume a task states its own standard. None
of them can be built on a task whose standard is empty.

## What Changes

- `spec_tasks.materialise()` assigns each task it creates the acceptance criteria belonging to the
  requirements that task resolves — the criteria whose `requirement` key is among the requirement
  keys already resolved for that entry at `spec_tasks.py:184-194`.
- Criteria are stored as **rendered strings**, one per criterion, so that every existing consumer
  keeps working unchanged (see Impact). No schema change, no migration.
- A criterion with no matching requirement on the task is not attached. A task that resolves no
  requirement gets no criteria, which is the status quo for that task.
- Tasks already materialised before this change are **not** backfilled. (Non-goal below; the
  existing-key skip at `spec_tasks.py:176` means a re-approval never revisits a created task.)

**Non-goals, stated rather than left to omission:**

- **Not** changing `Task.acceptance_criteria`'s type, the column, or any API schema.
- **Not** changing how a reviewer is briefed, beyond the content it already renders. No new briefing
  section, no new scheduler branch.
- **Not** making criteria executable, running them, or building a gate. This change makes the
  standard *present*; executing it is a later change and must not be smuggled in here.
- **Not** backfilling existing tasks, and **not** touching hand-made tasks, whose criteria already
  arrive through `create_task` (`hub/hub/mcp_server.py:256`).
- **Not** requiring a document to declare criteria. Whether a document may be approved with
  requirements that have no criteria is `spec_completeness`'s question
  (`hub/hub/spec_completeness.py:186`), and is deliberately untouched.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `spec-document-authority`: a declared task, when materialised, carries the acceptance criteria of
  the requirements it serves. This sits beside the existing requirement *"A declared task can state
  the name the board shows"* (`openspec/specs/spec-document-authority/spec.md:541`), which governs
  the same `materialise()` path and is the pattern to follow.

**Considered and deliberately not modified:** `agent-loops`' *"A firing's briefing is bounded"*
(`openspec/specs/agent-loops/spec.md:274`) bounds the **prior checkpoint** only, and this change adds
content outside that bound. Whether criteria need their own bound is a real question and is raised
in design.md rather than settled here — if the answer is yes, this proposal must gain a second
modified capability, and R2/R3 should check that rather than inherit this sentence.

## Impact

**Code**

- `hub/hub/spec_tasks.py` — `materialise()`, the only edit that changes behaviour.
- `hub/hub/spec_payload.py` — read-only; source of the `AcceptanceCriterion` shape.

**Consumers that constrain the shape** (why rendered strings, not objects):

- `hub/hub/scheduler.py:2459` renders `f"- {criterion}"`. A dict renders as a Python repr.
- `hub/ui/src/api/tasks.ts:18` types the field `acceptance_criteria?: string[]`, and
  `hub/ui/src/components/tasks/TaskDetailDrawer.tsx:612-616` maps each element straight into JSX. A
  non-string element throws at render.
- Storing objects would therefore require a UI change and a committed bundle. Per `CLAUDE.md`, the
  operator's live `:8000` Hub serves `hub/hub/static/ui` from this checkout, so a committed bundle
  reaches their running app on the next reload. **Strings avoid touching that surface at all.**

**Not affected:** no migration (`models.py:684` is already `JSON, nullable=True`), no API schema
(`hub/hub/schemas/tasks.py:64,299` are `Optional[List[Any]]` / `Optional[Any]`), no MCP tool surface,
no new dependency.

**Tests likely to need extending rather than changing:** `hub/tests/test_spec_declared_tasks.py`,
`hub/tests/test_spec_board_task_convergence.py`, `hub/tests/test_task_spec_document_context.py`.
