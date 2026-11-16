# DCUSW-2 spike: start the previous commit from a throwaway worktree

Spec `a-development-checkout-updates-the-same-way`, D5 / FR-11 (previous-commit-ready). Run
2026-11-16 on Windows 11, `py -3.11`, scratch port 8791, scratch database under `%TEMP%`; :8000
and :8010 untouched. Script: `testbed/previous_commit_spike.py <scratch> <prev sha> [port]`.

**Verdict: it works.** A Hub starts from a `git worktree add --detach <dir> <sha>` of an older
commit, on the restored database, with nothing installed and nothing built.

## What was run

PREV = `4ab5b6e` (migration head 0177), NEW = this checkout (head 0178, `0178_dashboards_edit_history`).

| Step | Result |
|---|---|
| `git worktree add --detach %TEMP%/aw-prevspike/previous-commit/<sha> <sha>` | 7 s, 84 MB, 5760 files; `hub/hub/static/ui` present (committed bundle) |
| 1. PREV Hub from the worktree on a fresh db | healthy in 10.1 s, head 0177; serves PREV's code (no CDA-2 `/dashboards/{id}/undo` route, no `version`/`install` in /health); `/` serves the bundle |
| 2. sqlite backup-API copy | head 0177, content checksum b287c4b2a2bf1670 |
| 3. NEW Hub (checkout) on the same db | healthy 11.6 s, migrated to 0178, CDA-2 routes present |
| 4. PREV Hub on the **unrestored** 0178 db | **healthy in 5.5 s anyway**: log `Alembic upgrade failed (continuing startup): Can't locate revision identified by '0178'` |
| 5. backup restored (backup API, -wal/-shm removed first), PREV Hub | healthy 5.0 s, head 0177, checksum equal to the backup |

## What it needs

1. **Start command**: `[sys.executable, "-m", "uvicorn", "hub.main:app", "--host", "127.0.0.1",
   "--port", N]` with **cwd = `<worktree>/hub`**. `-m` puts cwd first on `sys.path`, so `hub` is
   imported from the worktree, not from the editable install that points at the operator's
   checkout (verified: `hub.main.__file__` is the worktree's). Do **not** go through
   `python -m agentweave --hub-only` (`_hub_start_for_update`, cli.py ~2703): that imports
   `hub.main` in-process from the editable install, i.e. the NEW code, and runs NEW migrations.
2. **Environment**: `DATABASE_URL` (the Hub refuses to start without it), plus the HUB_DIR `.env`
   values (`AW_BOOTSTRAP_API_KEY`, `AW_TICKET_SECRET`) and `AW_PORT`, as `_prepare()` builds them.
   Strip `PYTHONPATH`. No `.env` exists in the worktree's `hub/`, so F1181's cwd-`.env` trap does not fire.
3. **Migrations**: none to run separately — `init_db` runs `alembic upgrade head` from the
   worktree's own `hub/hub/migrations` at start; on the restored db it is a no-op.
4. **Dependencies**: the same interpreter and site-packages. Nothing reinstalled. Risk (not
   exercised): a NEW commit that changed Python dependencies and had them installed leaves PREV on
   newer packages; out of scope per the spec's non-goals.
5. **UI bundle**: nothing to build; the committed `hub/hub/static/ui` is checked out with the
   commit. PREV here reported `ui_stale: true`, but that is PREV's own state on master (hub/ui/src
   changed 22 files after the stamp's `src_commit` 092c77e), not a worktree artefact: this
   checkout's fingerprint matches its stamp under the same `core.autocrlf=true`.

## What the updater (DCUSW-4) must do because of it

- **Restore the database BEFORE starting PREV, always.** A PREV Hub on the NEW-migrated database
  reports healthy (the Alembic failure is swallowed, `hub/hub/db/engine.py` `_run_alembic_upgrade`),
  so "/health is 200" proves nothing about schema compatibility.
- **FR-11 "blocked" signal**: `git worktree add` exits 128 before anything is stopped when the
  location cannot be prepared. With `previous-commit` made a plain file:
  `fatal: could not create leading directories of '.../previous-commit/<sha>/.git': Not a directory`.
  Use its last stderr line as the blocked reason.
- **Leftovers make `add` fail too** (exit 128): an existing directory (`'<dir>' already exists`)
  and a registered-but-deleted one (`is a missing but already registered worktree`). Reuse an
  existing healthy worktree for the same sha (check `git worktree list --porcelain`), else
  `git worktree prune` then add; only then treat failure as blocked.
- **Never remove the worktree while a Hub runs from it.** On Windows `git worktree remove --force`
  with a Hub running from it failed (`Permission denied`, exit 255) **after** unregistering the
  worktree and deleting part of the files; the running Hub kept answering 200. After a restore,
  PREV runs from the worktree, so it must persist until a later successful update replaces it.
  Remove it only after the NEW Hub is healthy (as the CONTRACT says); `remove` took 2.6 s.
- Budget: add ~7 s + 84 MB before the stop; PREV starts in 5-10 s on the restored db.
- Run `git worktree add` against the checkout (`git -C <checkout>`); the worktree's admin entry
  lives in the checkout's `.git/worktrees/`, which is the one shared side effect.
