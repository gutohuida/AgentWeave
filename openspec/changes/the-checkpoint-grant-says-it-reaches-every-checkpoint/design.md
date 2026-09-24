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
`test_a_granted_peer_still_cannot_read_a_private_checkpoint` (`:96-104`). R2 found two more writers
R1's table missed: `hub/tests/test_checkpoint_record.py:541` and `:732` construct
`Checkpoint(..., visibility="private")`, which raise once the column leaves the model (group 3).
`hub/tests/test_migrations.py:2390` and `:3058-3086` write the column in raw SQL against older
revisions (the latter upgrades only to `0097`), and are unaffected.

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
`batch_alter_table`), guarded to return early when the table is missing (as `0097` is) **or the
column is already gone** (a database whose `checkpoints` table `create_all` built from the new
model before alembic ran, which is exactly the F329 parity test's reference build). Downgrade re-adds
the column with server default `'project'` and the check over the three values, which is the state
`0097` left.

**Why a rebuild, and how it keeps every index exactly (R3).** A plain `ALTER TABLE checkpoints DROP
COLUMN visibility` fails on SQLite while `ck_checkpoints_visibility` names the column (measured R3:
*"error in table checkpoints after drop column: no such column: visibility"*), so the table must be
rebuilt. A rebuild re-creates indexes from reflection. On the installed SQLAlchemy (2.0.50) the
reflection carries a partial index's `WHERE` and the rebuild kept it (measured R3 against a copy of
the table with a partial unique index; it also kept `pk_checkpoints`, `uq_checkpoints_id` and every
named `CHECK`, the names `0088`'s downgrade drops by). But `pyproject.toml` allows any
`sqlalchemy>=2.0`, so the migration does not depend on reflection for this. It is safe in either
build order with B8's `a-checkpoint-is-handed-over-once-and-says-where-it-went`:

1. Before the batch, read `SELECT name, sql FROM sqlite_master WHERE type='index' AND
   tbl_name='checkpoints' AND sql LIKE '%WHERE%'` (every partial index on the table, whoever made
   it) and drop each.
2. Run the batch (drop the check, drop the column).
3. Re-execute each saved `sql` verbatim, if an index of that name does not already exist.

Downgrade does the same around its own batch. **If B8 lands first**, its partial unique index
`ix_checkpoints_one_handover_per_conversation` is saved and restored byte for byte. **If this lands
first**, there is nothing to save, and B8's migration creates its index on the rebuilt table (it does
no rebuild of its own: B8 design D1 chose a nullable column without a foreign key precisely to avoid
one). Keyed on *every* partial index rather than on B8's name, so neither change needs to know the
other's number or name. Non-partial indexes are left to reflection, which has always carried them
(`0088` rebuilt this table the same way).

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

- **Recreating `checkpoints` under B8's index (R2, corrected R3).** R2 named the F329 parity test
  (`test_migrations.py:3669`) as the check that the rebuild keeps B8's `WHERE`. **It is not one:**
  neither of its builds reaches the rebuild. The reference build runs `create_all` first, so the
  table has no `visibility` and the guard returns; the alembic-only build has no `checkpoints` table
  at all (`0044` creates it only beside `projects` and `conversations`). The check is task 1.4's
  migration test, which stands the old table up by hand **with a partial unique index on it** and
  asserts the index's `sqlite_master.sql` is byte-identical after upgrade and after downgrade. D3
  gives the save-and-restore that makes it pass whatever the SQLAlchemy version.
- **Same function as B7.** `worker-spend-counts-against-the-budget` (B7) adds parameters to
  `generate_checkpoint`, whose `visibility` parameter this change removes; whichever lands second
  rebases. B7 and B8 each also name migration `0106`; numbers are assigned at IMPL in landing order,
  not here.

## Migration Plan

Group 3's migration. Head assertions bumped in `test_migrations.py` and `test_project_persistence.py`
(`.claude/rules/db-migrations.md`, step 3).

## Open Questions

1. **Drop the column now, or leave it inert?** *Recommended: drop* (D3).
