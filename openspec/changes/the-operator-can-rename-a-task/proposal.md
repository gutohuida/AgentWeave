# Proposal — the operator can rename a task

**Round 1, 2026-09-24** (bundle B3, decision D10, F125). Finding **F125 (C)**, re-verified on HEAD
`404c7d5`. **Nothing here is implemented yet.**

## Why

A task's title is written once, at creation, and nobody can change it afterwards:

```
PATCH /projects/{p}/tasks/{id}  {"title": "Write loop_r11_c.txt (orphaned)"}
  422 extra_forbidden  loc: ["body", "title"]
```

`TaskUpdate` (`hub/hub/schemas/tasks.py:120-151`) has no `title`, and `TaskDetailDrawer.tsx:298-300`
renders the title into an `<h2>` with no editor. The title is the line the board and the drawer show,
and it goes stale exactly when work moves — including titles an agent chose. `description` is
already writable through the same PATCH. No code assigns `task.title` after creation
(`grep -rn "\.title = " hub/hub` finds no task write), so nothing depends on it being fixed.

## What Changes

- `TaskUpdate` gains `title` (1-256 characters after trimming; blank refused 422). The operator's
  `PATCH /projects/{p}/tasks/{id}` writes it.
- **Agents do not rename tasks.** If `an-agent-updates-a-task-with-what-its-tool-carries` has landed,
  `title` joins its operator-only list; if not, this change adds the same 403 for `title` alone.
- `title: null` is refused as blank; an omitted `title` leaves it alone (operator review 2026-09-24).
- The task drawer's title becomes editable in place (click or an edit affordance; Enter saves, Escape
  cancels), through a separate `useRenameTask` that sends only `{title}` — not `useUpdateTask`, which
  always sends `status` and would fail a rename of a `blocked` task (operator review).
- A rename is not a transition and is not added to the transition history. Conversations and job
  threads already named after the old title keep their names.

## Capabilities

### Modified Capabilities

- `task-lifecycle-governance` — adds a requirement that the operator may rename a task.

## Impact

Schema + service (`tasks.py`), one UI hook, one UI component and their tests, one bundle refresh,
committed with the Python in the night build (`DECISIONS.md` *2026-09-14-ui*). No migration.
Until the operator restarts `:8000`, a rename sent from its reloaded page answers 422 and changes
nothing (design D5).
