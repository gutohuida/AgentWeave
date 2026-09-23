# Design — the operator can rename a task

**Built on the recommended answer to D10/F125**: *titles are editable, by the operator only.* **If the
operator answers otherwise** ("a title is a permanent name"), this change is withdrawn and F125 closes
as decided; the one thing to keep is a named refusal instead of `422 extra_forbidden` — a `title` on
`TaskUpdate` that the service refuses with *"A task's title is fixed at creation"*, as `loop_id`
already is (`tasks.py:1286-1295`).

## Context — re-verified on HEAD `404c7d5`

- `TaskUpdate` (`schemas/tasks.py:120-151`): no `title`; `RequestModel` forbids extra fields, hence
  the 422 F125 measured (F116's strictness, working as designed).
- `TaskCreate.title: str = Field(max_length=256)` (`schemas/tasks.py:46`) — the bound a rename keeps.
- `TaskDetailDrawer.tsx:298-300`: static `<h2>`.
- `git log -S "title: Optional[str]" -- hub/hub/schemas/tasks.py`: never present on `TaskUpdate`.

## D1 — Options

1. **Operator may rename** (recommended). The title is the operator's handle on the work; a stale one
   is a cost they pay every time they scan the board.
2. **Nobody may rename** (the status quo, made explicit). Consistent, but the only remedy for a wrong
   title is to reject the task and create another, which loses its history and evidence links.
3. **Agents may rename too.** Conflicts with the field split in
   `an-agent-updates-a-task-with-what-its-tool-carries` (a title is the operator's statement, like the
   description).

## D2 — Validation and what the route returns

- Trimmed; empty after trimming → 422 *"A task's title cannot be blank."*; over 256 → 422 (field bound).
- Applied beside `description` in `update_task_for_actor`; no new raise path beyond validation.
- The PATCH already broadcasts the updated task; the board and drawer re-render from it.

## D3 — Not recorded in history

Transitions record status moves (`task-lifecycle-governance`, *"Every accepted transition is recorded
append-only"*). A rename is not one. Recording renames would need a new record type; not proposed.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
