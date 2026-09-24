## 0. Rounds and decision

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): an independent re-derivation. `grep -rn visibility` over `hub/hub`, `hub/ui/src`,
      `hub/tests`, `src/`; rebuild design's table before reading it. Check that no route or MCP tool
      writes the column and that no UI component reads the field. Record in `spec-queue/tracks/B2.md`
- [x] 0.2 R3 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): a second independent
      re-derivation. `openspec validate the-checkpoint-grant-says-it-reaches-every-checkpoint --strict`
      passes. The rebuild now saves and restores every partial index (design D3); 1.4 is the check
- [ ] 0.3 The operator records D11/F235 in `spec-queue/DECISIONS.md` and answers design Open
      Question 1

## 1. Tests first — each must fail on today's code unless marked as a control

- [ ] 1.1 (UI) A test for `CheckpointGrantsSetting` (new, beside the agent settings tests): the read
      grant's hint contains `every conversation in this project` and does not contain `visibility`.
      Record that it FAILS today
- [ ] 1.2 (Hub) `GET` a checkpoint through its route: the response has no `visibility` key. Record
      that it FAILS today
- [ ] 1.3 (Hub) Controls, PASS today and must keep passing after `visibility=` is removed from the
      helper: every other test in `hub/tests/test_checkpoint_access.py`, and the F235 leg of
      `scripts/drive/t_sweep_row13_checkpoints.py` read as a unit expectation (a granted peer reads a
      checkpoint from a conversation it never joined)
- [ ] 1.4 (Hub, group 3) Migration: upgrade to head leaves `checkpoints` with no `visibility` column;
      downgrade one step restores it with every row `project`. A bare alembic run has no
      `checkpoints` table (`0044` creates it only beside `projects` and `conversations`), so stand the
      table up by hand at the prior revision, as `test_migrations.py:3058-3086` does for `0097`,
      **with a partial unique index on it** (B8's own DDL if B8 has landed, else
      `CREATE UNIQUE INDEX ix_test_partial ON checkpoints (conversation_id) WHERE status = 'ready'`).
      Assert that index's `sqlite_master.sql` is byte-identical after the upgrade and after the
      downgrade, and that `pk_checkpoints`, `uq_checkpoints_id`, `ck_checkpoints_trigger`,
      `ck_checkpoints_status` and `ck_checkpoints_ready_has_a_body` are still in the table's DDL
      (R3: the F329 parity test does not reach this rebuild, so it cannot be the check). Add the
      missing-table and column-already-gone guard cases beside it. Record that it FAILS today

## 2. Say it, and remove the concept from code

- [ ] 2.1 `AgentSettingsControls.tsx:417`: the hint (design D1)
- [ ] 2.2 `checkpoint_access.py`: drop the visibility half and rewrite the docstring (design D2)
- [ ] 2.3 `api/v1/checkpoints.py`: drop `CheckpointSummary.visibility`; `checkpoints.py` and
      `checkpoint_generation.py`: drop the parameter; `hub/ui/src/api/checkpoints.ts`: drop the field;
      fix the UI fixtures that set it
- [ ] 2.4 Delete `test_a_granted_peer_still_cannot_read_a_private_checkpoint`; remove `visibility=` from
      the helper and its callers
- [ ] 2.5 `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together
- [ ] 2.6 Run 1.1-1.3; full `py -3.11 -m pytest hub/tests/ -q` and `cd hub/ui && npm test -- --run`,
      counts inline

## 3. Drop the column (design D3; stopping before this group leaves a complete change)

- [ ] 3.1 Read `.claude/rules/db-migrations.md`. New migration: drop `ck_checkpoints_visibility` and
      `checkpoints.visibility` in `batch_alter_table`, guarded for a missing table and for a column
      already gone; save every partial index's DDL from `sqlite_master` before the batch, drop it,
      and re-execute it after (design D3); downgrade restores both with server default `'project'`,
      around the same save-and-restore
- [ ] 3.2 `db/models.py`: remove the column, `CHECKPOINT_VISIBILITIES`, the check and the DEAD comment;
      drop `visibility="private"` from `hub/tests/test_checkpoint_record.py:541` and `:732`. Whether or
      not B8's partial index exists by then, 1.4 is the check; the F329 parity test must still pass
      but does not exercise the rebuild
- [ ] 3.3 Bump the head assertions in `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`
- [ ] 3.4 Run 1.4 and the full suite again, counts inline
- [ ] 3.5 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, `cd hub/ui &&
      npm run lint`, clean

## 4. Drive it

- [ ] 4.1 On a trial Hub from source (fresh profile; never `:8000`), grant a peer read, take a
      checkpoint in another agent's conversation, and read it as the peer. Open the peer's settings:
      the hint says it reaches every conversation
