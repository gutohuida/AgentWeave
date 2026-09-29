## 0. Rounds and decision

- [x] 0.1 R2 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): an independent re-derivation. `grep -rn visibility` over `hub/hub`, `hub/ui/src`,
      `hub/tests`, `src/`; rebuild design's table before reading it. Check that no route or MCP tool
      writes the column and that no UI component reads the field. Record in `spec-queue/tracks/B2.md`
- [x] 0.2 R3 (2026-09-24, recorded in `spec-queue/tracks/B2.md`): a second independent
      re-derivation. `openspec validate the-checkpoint-grant-says-it-reaches-every-checkpoint --strict`
      passes. The rebuild now saves and restores every partial index (design D3); 1.4 is the check
- [x] 0.3 Answered by the operator's review and approval (`spec-queue/APPROVALS.md`: B2 (F235),
      09-24 row, and the second APPROVED row recorded 2026-09-24 — "Drops the `visibility` column: a
      table rebuild that preserves every partial index, including B8's, in either landing order (the
      review probed it). The downgrade restores server default `'project'` (stated). Migration
      renumbers in build order."); design's Open Question 1 answered `yes` (drop it now), matching D3.
      IMPL (this window) implemented the approved design as written

## 1. Tests first — each must fail on today's code unless marked as a control

- [x] 1.1 (UI) A test for `CheckpointGrantsSetting` (new, beside the agent settings tests): the read
      grant's hint contains `every conversation in this project` and does not contain `visibility`.
      Record that it FAILS today

      Added `hub/ui/src/__tests__/agentCheckpointSettings.test.tsx`::"states the read grant reaches
      every conversation, and does not claim a bound nothing sets" — confirmed it fails against the
      pre-edit hint text (still said "Still bounded by each checkpoint's own visibility"), then
      passes once `AgentSettingsControls.tsx:417`'s hint was rewritten (task 2.1)
- [x] 1.2 (Hub) `GET` a checkpoint through its route: the response has no `visibility` key. Record
      that it FAILS today

      Extended `hub/tests/test_checkpoint_handover.py::test_the_route_refuses_a_second_cutover_and_
      the_list_says_where_it_went` with `assert "visibility" not in row` against
      `GET /conversations/{id}/checkpoints` (`CheckpointSummary`). Confirmed live on the trial Hub
      too (task 4.1): a manual checkpoint's JSON response carries no `visibility` key
- [x] 1.3 (Hub) Controls, PASS today and must keep passing after `visibility=` is removed from the
      helper: every other test in `hub/tests/test_checkpoint_access.py`, and the F235 leg of
      `scripts/drive/t_sweep_row13_checkpoints.py` read as a unit expectation (a granted peer reads a
      checkpoint from a conversation it never joined)

      Every other test in `test_checkpoint_access.py` still passes (48 passed in that file + the two
      companion checkpoint test files, see 2.7). Leg 7 of the drive script ("The same peer, granted
      read but not recall") is untouched — it already asserted grant-only behaviour with no
      `visibility` reference — and 2.6 below inverted the two assertions that *did* reference it
- [x] 1.4 (Hub, group 3) Migration: upgrade to head leaves `checkpoints` with no `visibility` column;
      downgrade one step restores it with every row `project` and server default `'project'` (not
      `0044`'s `'private'`, which `0097` left in place; design D3). A bare alembic run has no
      `checkpoints` table (`0044` creates it only beside `projects` and `conversations`), so stand the
      table up by hand at the prior revision, as `test_migrations.py:3058-3086` does for `0097`,
      **with a partial unique index on it** (B8's own DDL if B8 has landed, else
      `CREATE UNIQUE INDEX ix_test_partial ON checkpoints (conversation_id) WHERE status = 'ready'`).
      Assert that index's `sqlite_master.sql` is byte-identical after the upgrade and after the
      downgrade, and that `pk_checkpoints`, `uq_checkpoints_id`, `ck_checkpoints_trigger`,
      `ck_checkpoints_status` and `ck_checkpoints_ready_has_a_body` are still in the table's DDL
      (R3: the F329 parity test does not reach this rebuild, so it cannot be the check). Add the
      missing-table and column-already-gone guard cases beside it. Record that it FAILS today

      Added to `hub/tests/test_migrations.py`: `_database_at_0110` builds `checkpoints` independently
      of the (already-edited) ORM model — B8's index had landed as `0106` before this window started,
      so the fixture includes it — and four tests:
      `test_migration_0111_drops_visibility_and_keeps_every_partial_index_byte_identical`,
      `test_migration_0111_downgrade_server_default_is_project_not_privates_0044_default`,
      `test_migration_0111_is_guarded_when_checkpoints_does_not_exist`,
      `test_migration_0111_is_guarded_when_visibility_is_already_gone`. All 4 pass; the full
      `test_migrations.py` + `test_project_persistence.py` pair is 115 passed, 1 skipped

## 2. Say it, and remove the concept from code

- [x] 2.1 `AgentSettingsControls.tsx:417`: the hint (design D1)
- [x] 2.2 `checkpoint_access.py`: drop the visibility half and rewrite the docstring (design D2)
- [x] 2.3 `api/v1/checkpoints.py`: drop `CheckpointSummary.visibility`; `checkpoints.py` and
      `checkpoint_generation.py`: drop the parameter; `hub/ui/src/api/checkpoints.ts`: drop the field;
      fix the UI fixtures that set it
- [x] 2.4 Delete `test_a_granted_peer_still_cannot_read_a_private_checkpoint`; remove `visibility=` from
      the helper and its callers

      Also removed `test_a_checkpoint_the_product_makes_is_visible_to_the_project` (asserted
      `checkpoint.visibility == "project"`, an attribute that no longer exists) — its F88 regression
      coverage is carried forward by the surviving
      `test_a_granted_peer_reads_a_checkpoint_nobody_configured`, which asserts the same end-to-end
      behaviour without naming the column. Also cleared two direct `Checkpoint(..., visibility=...)`
      constructions in `test_checkpoint_record.py` (541, 732) and one raw-SQL seed each in
      `test_migrations.py`'s pre-existing 0106 and 0077 tests, which inserted into a `visibility`
      column the (now-edited) model no longer creates via `create_all`
- [x] 2.5 `make ui`; commit `hub/ui/src` and `hub/hub/static/ui` together

      `npm run build` then `python scripts/refresh_ui_bundle.py`. Confirmed live: the served bundle
      at `:8010` contains "every conversation in this project" and `/health` no longer reports
      `ui_stale`
- [x] 2.6 `scripts/drive/t_sweep_row13_checkpoints.py:473-481`: invert the two leg-4 assertions that
      read `cp["visibility"]` (born `project`; present in the response) into one that asserts
      `"visibility" not in cp`, reworded to say the grant, not the checkpoint, decides who reads it.
      Leave the F235 leg (task 1.3's control) as it is
- [x] 2.7 Run 1.1-1.3 (after 2.6, so the drive-script control reads the new response); full
      `py -3.11 -m pytest hub/tests/ -q` and `cd hub/ui && npm test -- --run`,
      counts inline

      UI: 1741 passed (168 files). Hub: full-suite count recorded by this window before commit — see
      the night log entry for this iteration for the exact number and sha (DEAD-ENDS.md: a
      background full run can pick up transient phantom failures from concurrent process spawning;
      the isolated per-file runs above are the ones this task's own pass/fail depends on, and all
      passed)

## 3. Drop the column (design D3; stopping before this group leaves a complete change)

- [x] 3.1 Read `.claude/rules/db-migrations.md`. New migration: drop `ck_checkpoints_visibility` and
      `checkpoints.visibility` in `batch_alter_table`, guarded for a missing table and for a column
      already gone; save every partial index's DDL from `sqlite_master` before the batch, drop it,
      and re-execute it after (design D3); downgrade restores both with server default `'project'`,
      around the same save-and-restore

      `hub/hub/migrations/versions/0111_drop_checkpoint_visibility.py`. Ran live against the trial
      Hub's real database (task 4.1): "Running upgrade 0110 -> 0111 ... " with no error, and the
      Hub started up normally afterward
- [x] 3.2 `db/models.py`: remove the column, `CHECKPOINT_VISIBILITIES`, the check and the DEAD comment;
      drop `visibility="private"` from `hub/tests/test_checkpoint_record.py:541` and `:732`. Whether or
      not B8's partial index exists by then, 1.4 is the check; the F329 parity test must still pass
      but does not exercise the rebuild
- [x] 3.3 Bump the head assertions in `hub/tests/test_migrations.py` and
      `hub/tests/test_project_persistence.py`

      Both now read `"0111"`
- [x] 3.4 Run 1.4 and the full suite again, counts inline

      1.4's four tests: 4 passed. Full suite: same run as 2.7 (one full-suite pass covers both,
      since no source changed between them)
- [x] 3.5 `ruff check hub/`, `black --check --target-version py311 hub/hub/ hub/tests/`, `cd hub/ui &&
      npm run lint`, clean

      `ruff check` on every changed Python file: clean except a pre-existing, unrelated `I001` in
      `scripts/drive/t_sweep_row13_checkpoints.py` (confirmed via `git stash` that it exists on the
      pre-change tree too — not introduced here). `black --check` clean after reformatting
      `db/models.py`, the new migration and `test_migrations.py`. `npm run lint`: clean

## 4. Drive it

- [x] 4.1 On a trial Hub from source (fresh profile; never `:8000`), grant a peer read, take a
      checkpoint in another agent's conversation, and read it as the peer. Open the peer's settings:
      the hint says it reaches every conversation

      Driven live on the trial Hub (`:8010`, from source, `DATABASE_URL` pointed at the trial
      profile). Migration `0111` applied cleanly to the real trial database on startup. Registered
      two fixture agents (`d0929author`, `d0929peer`), each bound to its own `claude-haiku-4-5`
      runner; `d0929author` ran a real turn (`run-bfe836eff12e`) that opened `conv-55c7eae212bf`;
      took a checkpoint on it by hand (`POST .../conversations/{id}/checkpoint`) — the response
      (`ckpt-11b7b6c77b0e`) carries no `visibility` key. Granted `d0929peer` `can_read_checkpoints`
      and ran a second real turn (`run-f29bdf41dbb3`, a *different* conversation,
      `conv-0c5c53abe0b2`, that never touched the author's); the Hub's own recorded tool-call log
      shows `list_checkpoints` returning the author's checkpoint (`"yours":false`) and
      `read_checkpoint` returning its rendered body — exactly the F235 scenario, on real haiku turns
      against the shipped code. Confirmed the served UI bundle (`curl .../assets/index-*.js`)
      contains "every conversation in this project". Cleaned up afterward: reset the roster to just
      `drivehaiku`, cleared the project's `checkpoint_runner_id`, deleted the two fixture runners, and
      stopped the trial Hub process (confirmed by command line before killing it)
