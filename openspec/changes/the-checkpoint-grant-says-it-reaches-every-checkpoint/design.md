# Design — the checkpoint grant says it reaches every checkpoint

**Built on the recommended answer to D11 for F235** (the grant is all-or-nothing; delete the claim and
the unreachable concept). If the operator answers otherwise:

- *build per-checkpoint visibility*: a route and a control to set it, a writer for `private` and
  `granted`, and a meaning for `granted` (which has none today: `checkpoint_access.py:48` treats it as
  `project`). A different, larger change; this one is withdrawn;
- *fix only the sentence*: tasks 2.1 and the spec delta alone; the dead column, check and response
  field stay, documented as dead by `db/models.py:1653-1665`.

**Round 1, 2026-09-24.** Nothing here is implemented yet.

## Context

Every place `visibility` appears in the Hub, at HEAD:

| Where | What |
|---|---|
| `db/models.py:1653-1665` | `CHECKPOINT_VISIBILITIES = ("private", "project", "granted")`, with the DEAD comment |
| `db/models.py:1709-1723` | the column, default `"project"`, and its history (F88) |
| `db/models.py:1792-1795` | `ck_checkpoints_visibility` |
| `checkpoint_access.py:4`, `:36-48` | *capability ∩ visibility*; the one read |
| `checkpoints.py:425`, `:454` | `create_checkpoint(…, visibility="project")`, no caller passes it |
| `checkpoint_generation.py:506`, `:590` | `generate_checkpoint(…, visibility="project")`, likewise |
| `api/v1/checkpoints.py:37`, `:58` | `CheckpointSummary.visibility`, response only |
| `migrations/versions/0044_add_checkpoints.py` | created it, default `private` |
| `migrations/versions/0097_checkpoint_visibility_default.py` | rewrote every `private` to `project` |

In the UI: the type `hub/ui/src/api/checkpoints.ts:14`, and test fixtures in
`hub/ui/src/__tests__/agentHandoff.test.tsx:129`, `:268`, `:295-296`. No component reads the field.

In the Hub tests: `hub/tests/test_checkpoint_access.py` seeds `visibility` in its `_checkpoint`
helper (`:49-56`), and one test exists only for the unreachable state:
`test_a_granted_peer_still_cannot_read_a_private_checkpoint` (`:96-104`).

## Decisions

### D1 — Say what the grant reaches

Hint: *"Summaries of where their conversations got to, from every conversation in this project."*
The spec replaces its MAY paragraph with a SHALL stating the reach, so the next reader of the
requirement does not rebuild the bound from the spec.

*Rejected:* **build it.** Nothing asks for per-checkpoint restriction: the operator's control is per
reader (the two grants), and the one drive that reached this (F235) found the reader-level control
sufficient for everything else it tested. A restriction nobody can set is the state F88 and F235 both
found.

### D2 — Remove the concept from code and API

`may_read_checkpoint` returns `reader.can_read_checkpoints` after the owner check. The response
field and the two parameters go. `test_a_granted_peer_still_cannot_read_a_private_checkpoint` is
deleted with a note in the commit message: it pinned a state no database past `0097` holds and no
code can write. The other tests in that file lose the `visibility=` argument and keep every
assertion.

### D3 — Drop the column, last

A new migration drops `checkpoints.visibility` and `ck_checkpoints_visibility` (SQLite:
`batch_alter_table`), guarded for a missing table as `0097` is. Downgrade re-adds the column with
server default `'project'` and the check over the three values, which is the state `0097` left.

Last, and separable: after groups 1-2 the column is inert (written by its default, read by nothing).
Stopping there is a complete change; group 3 removes the inert column. It is kept in this change
rather than deferred because the operator prefers the cleanest end state, and the DEAD comment
already lists exactly what the removal touches.

## Risks / Trade-offs

- **A migration on the operator's real data.** It removes a column whose every value is `project` and
  which nothing reads after group 2. Downgrade restores it exactly.
- **An external reader of `CheckpointSummary.visibility`.** None in the repo (`grep` above); MCP's
  `list_checkpoints`/`read_checkpoint` go through the same routes and an agent reading the field
  would have read `project` every time.

## Migration Plan

Group 3's migration. Head assertions bumped in `test_migrations.py` and `test_project_persistence.py`
(`.claude/rules/db-migrations.md`, step 3).

## Open Questions

1. **Drop the column now, or leave it inert?** *Recommended: drop* (D3).
