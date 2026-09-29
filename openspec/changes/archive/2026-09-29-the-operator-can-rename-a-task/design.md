# Design — the operator can rename a task

## Operator review, 2026-09-24

The Opus adversarial review (`spec-queue/tracks/reviews/B3-2026-09-24.md` §8) verdict was
**APPROVE WITH FIXES**; the operator approved with the fixes applied (F125: the operator may rename,
agents may not). Fixes, re-verified on HEAD `a50a49b`:

- **MEDIUM — renaming a blocked task would fail.** `useUpdateTask` (`hub/ui/src/api/tasks.ts:359-381`)
  takes `status` as required and always sends it. Renaming a `blocked` task through it would restate
  `blocked` without `blocked_reason`, which the route answers 422. The drawer uses a separate
  **`useRenameTask`** that sends only `{title}`, following the `useLandTask` precedent (`:391-405`,
  whose docstring gives the reason: a different act must not share the status mutation's pending
  state). D4; tasks 1.4a, 2.2.
- **LOW — `"title": null`.** Refused as blank (422, the same sentence), not read as "leave it alone":
  a `title` key present in the body (`model_fields_set`) with a null value is a request to clear it,
  and a task cannot have no title. D2; task 1.2a.
- **LOW — where the agent refusal sits.** In the pre-write check beside `loop_id`
  (`tasks.py:1286-1295`), where `an-agent-updates-a-task-with-what-its-tool-carries` also puts its
  field refusal — **not** "beside `description`" (`:1410`), which runs after the transition
  (`:1381`) and the assignee write (`:1317`). D2; task 2.1.
- **LOW — bundle skew.** A committed bundle reaches `:8000` on its next reload, before its Python does
  (on the operator's restart), so a rename sent from `:8000` answers 422 `extra_forbidden` until then.
  Per `spec-queue/DECISIONS.md` *2026-09-14-ui* (a UI fix's bundle is committed by day only if it
  needs nothing newer from Python than `:8000` runs), this bundle needs the new `title` field, so it
  is built with the backend in the night build and committed with it. D5; task 2.2.

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
- **`"title": null` is blank** (operator review): a `title` key present in the body with a null value
  answers the same 422 and sentence. `TaskUpdate` reads presence through `model_fields_set`, as
  `assignee` does (`tasks.py:1307`), so an omitted `title` still means "leave it"; only an explicit
  null is refused.
- **The agent refusal is a pre-write check** (operator review): `title` in `model_fields_set` for a
  run actor → 403, raised beside `loop_id`'s check (`tasks.py:1286-1295`) before any field is
  touched, in the same list as `an-agent-updates-a-task-with-what-its-tool-carries`'s operator-only
  fields if that change has landed. The operator's write of the title may sit beside `description`
  (`:1410`); the refusal may not, because that point is after the transition (`:1381`) and the
  assignee write (`:1317`), and would rely on the uncommitted session being discarded.
- No new raise path beyond validation and that refusal.
- The PATCH already broadcasts the updated task; the board and drawer re-render from it.

## D4 — The drawer's mutation (operator review)

`useRenameTask` in `hub/ui/src/api/tasks.ts`: `PATCH /api/v1/projects/{p}/tasks/{id}` with exactly
`{title}`, invalidating the tasks query as `useUpdateTask` does. Not `useUpdateTask`: that hook
requires and always sends `status`, so a rename would restate the status — refused 422 for a
`blocked` task without its reason — and would share the status change's pending state, the reason
`useLandTask` is separate. A failed rename shows the route's `detail` and restores the old title.

## D5 — Bundle skew (operator review)

The bundle calls a field only the new Python accepts. Under *2026-09-14-ui* it is therefore built
and committed with the backend in the night build, not by day. Between the commit and the
operator's restart of `:8000`, a rename from `:8000`'s reloaded UI answers 422 and D4's error path
shows it; nothing is written. Accepted: the window closes on the restart, and the alternative (a
feature flag) is more machinery than a rename is worth.

## D3 — Not recorded in history

Transitions record status moves (`task-lifecycle-governance`, *"Every accepted transition is recorded
append-only"*). A rename is not one. Recording renames would need a new record type; not proposed.

## Round log

- R1 (2026-09-24): written. Not yet compared by R2/R3.
- R2 (2026-09-24): `TaskUpdate` (`schemas/tasks.py:120-151`) has no `title`; `Task.title` is `String(256)` (`db/models.py:684`) matching `TaskCreate`; the drawer's `<h2>` is static (`TaskDetailDrawer.tsx:298-300`); no code reads a task title as an identity (no `title ==` comparisons in `hub/hub`). Holds. Shares `update_task_for_actor`'s run-actor refusal with `an-agent-updates-a-task-with-what-its-tool-carries`; whichever lands second extends the other's list.
- R3 (2026-09-24): re-read; holds. The agent route takes the same `TaskUpdate` (`agent_actions.py:279-292`), so without the run-actor refusal a `title` field would be writable by agents the moment it is added — task 2.1's refusal is load-bearing, not optional, whichever of the two changes lands first.
- Operator review (2026-09-24): `useRenameTask` (D4), `title: null` refused as blank, the agent refusal placed in the pre-write check, bundle skew (D5). Tasks 1.2a, 1.4, 1.4a, 2.1, 2.2 follow. See the section at the top.
