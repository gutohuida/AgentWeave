## 1. Adopt an orphaned marker in `open_existing`

- [x] 1.1 Add a failing test in `hub/tests/test_project_lifecycle.py`: a directory carrying a
      marker for a project id absent from the database is opened, and the resulting project keeps
      the marker's id, has `charters_seeded = True`, and has the default runner set.
      (`test_orphaned_marker_is_adopted_under_its_own_id`)
- [x] 1.2 Add a failing test: the same scenario, then assert the project row is queryable by that
      exact id afterward (not merely that `open_existing` returned something with that id).
      (folded into the same test — asserts `session.get(Project, orphan_id)` after the call)
- [x] 1.3 In `hub/hub/project_lifecycle.py`, rewrite `open_existing` case 3 (currently the
      unconditional `raise ProjectIdentityConflict` at lines 86-90 reached when
      `marked_project is None`): construct `Project(id=marker["project_id"], name=name or
      canonical.path.name, charters_seeded=False)`, call the existing `self._seed_new_project`,
      then fall through to the same `_observe` / `_write_marker_and_commit` / `seed_repo_excludes`
      tail every other branch uses.
- [x] 1.4 Add the `logger.info` adoption record (decided in design.md: no new table/column) at the
      point of adoption, carrying the project id and canonical path.
- [x] 1.5 Run the two new tests; confirm they pass against the new code and fail against a revert
      of 1.3 (mutation check). Reverted `hub/hub/project_lifecycle.py` via `git stash`: both new
      tests failed with `ProjectIdentityConflict: marked directory is a copied or orphaned...`,
      the other 10 in the file unaffected. Restored and re-ran green.

## 2. Delete-then-reopen keeps the same id

- [x] 2.1 Add a failing test: create a project, delete it via `ProjectLifecycleService.delete`,
      then call `open_existing` on the same directory again. Assert the returned project's id
      equals the deleted project's original id, and that seeding (runners, charters) happened
      again for the new row. (`test_deleted_project_directory_is_adopted_back_under_the_same_id`)
- [x] 2.2 Confirmed: passes once 1.3 lands, with no additional code — `delete()` never touches the
      filesystem, so the marker alone was sufficient.

## 3. Guard the untouched case-2 path

- [x] 3.1 `test_copied_marker_conflicts_until_explicitly_registered_as_new` still green, unedited.
- [x] 3.2 Already covered, not duplicated: that same test IS the case-2 scenario — it opens
      `original` (marker's id present in the database), copies the marker to `copied` while
      `original` is still available, and asserts `_guard_relocation` still refuses. A second test
      would have been a copy of it under a new name; recorded here instead of adding one.

## 4. Full verification

- [x] 4.1 `pytest hub/tests/test_project_lifecycle.py hub/tests/test_project_persistence.py -v`
      (via the Python 3.11 interpreter that has `pytest_asyncio` installed — the default `python`
      on PATH in this shell does not) — **19 passed** (12 lifecycle incl. 2 new, 7 persistence).
- [x] 4.2 `npx openspec validate --changes --strict` — `✓ change/portable-project-identity`,
      1 passed / 0 failed.
- [x] 4.3 Checkboxes above reflect only work verified this session.
