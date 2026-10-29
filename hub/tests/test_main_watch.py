"""Main is watched and its moves raised (`amendments-main-watch-and-the-next-slice`, task
`main-watch`).

Red first: on master the watch looked only at projects with checks, kept the tip in memory and told
nobody. Real git repositories, as in `test_checks_refresh_when_main_moves.py`. The acceptance
drive's `hand_commit` is the first case; here `-k rewrite`, `-k own_merge`, `-k coalesce`.
"""

import pytest
from sqlalchemy import select

from hub import main_watch, project_checks
from hub.db.engine import async_session_factory
from hub.db.models import MainNotice, Project, Task, TaskCheckRun, TaskIntegration

from .test_project_checks_gate import _approve
from .test_project_checks_run import _task_with_work
from .test_task_integration import git, make_repo, set_main_branch

pytestmark = pytest.mark.asyncio
PROJECT = "/api/v1/projects/proj-test"


def _tip(root):
    return git(root, "rev-parse", "main").stdout.strip()


def _commit(root, name, subject, author="Hand Person"):
    (root / name).write_text(f"{name}\n", encoding="utf-8")
    git(root, "add", name)
    git(
        root,
        "-c",
        f"user.name={author}",
        "-c",
        "user.email=hand@example.com",
        "commit",
        "-q",
        "-m",
        subject,
    )
    return _tip(root)


async def _notices(app, auth_headers, **params):
    response = await app.get(f"{PROJECT}/main-notices", params=params, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["notices"]


def _restart():
    """Clear the watch's in-memory state, as a Hub restart does."""
    project_checks._seen_tips.clear()
    main_watch.forget()


async def test_a_rewrite_is_raised_as_one(app, auth_headers, tmp_path):
    base = make_repo(tmp_path)
    await set_main_branch("main")
    later = _commit(tmp_path, "later.txt", "Later work")
    await project_checks.watch_main_once()

    git(tmp_path, "reset", "-q", "--hard", base)
    await project_checks.watch_main_once()

    (notice,) = await _notices(app, auth_headers)
    assert notice["rewrite"] is True
    assert (notice["old_tip"], notice["new_tip"]) == (later, base)
    async with async_session_factory() as session:
        assert (await session.execute(select(Task))).scalars().first() is None
        assert (await session.execute(select(TaskCheckRun))).scalars().first() is None
        assert (await session.execute(select(TaskIntegration))).scalars().first() is None


async def test_own_merge_is_silent(app, auth_headers, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await project_checks.watch_main_once()
    before = _tip(tmp_path)

    approved = await _approve(app, auth_headers, task_id)
    assert approved.status_code == 200, approved.text
    after = _tip(tmp_path)
    assert after != before
    _restart()  # the record, not memory, recognises the merge
    await project_checks.watch_main_once()

    async with async_session_factory() as session:
        (row,) = (await session.execute(select(TaskIntegration))).scalars().all()
        assert (row.outcome, row.merged_sha) == ("merged", after)
        assert (await session.get(Project, "proj-test")).main_tip_seen == after
    assert await _notices(app, auth_headers) == []


async def test_moves_coalesce_into_one_notice_that_survives_a_restart(app, auth_headers, tmp_path):
    make_repo(tmp_path)
    await set_main_branch("main")
    await project_checks.watch_main_once()
    _commit(tmp_path, "a.txt", "A")
    await project_checks.watch_main_once()
    assert len(await _notices(app, auth_headers)) == 1

    _commit(tmp_path, "b.txt", "B")
    _commit(tmp_path, "c.txt", "C")
    await project_checks.watch_main_once()
    _restart()
    last = _commit(tmp_path, "d.txt", "D")  # made "while the Hub was down"
    await project_checks.watch_main_once()

    (notice,) = await _notices(app, auth_headers)
    assert [c["subject"] for c in notice["commits"]] == ["D", "C", "B", "A"]
    assert notice["new_tip"] == last
    seen = await app.post(f"{PROJECT}/main-notices/{notice['id']}/seen", headers=auth_headers)
    assert seen.status_code == 200, seen.text
    assert await _notices(app, auth_headers) == []
    assert len(await _notices(app, auth_headers, include_seen=True)) == 1

    # A fresh project's first look records its tip and raises nothing.
    async with async_session_factory() as session:
        (await session.get(Project, "proj-test")).main_tip_seen = None
        await session.commit()
    _commit(tmp_path, "e.txt", "E")
    await project_checks.watch_main_once()
    assert await _notices(app, auth_headers) == []
    async with async_session_factory() as session:
        assert len((await session.execute(select(MainNotice))).scalars().all()) == 1


def test_0154_adds_the_merge_sha_the_seen_tip_and_notices_and_round_trips(tmp_path) -> None:
    import sqlite3

    from tests.test_migrations import _create_all_at, _downgrade_to, _run, _upgrade_to

    def columns(conn, table):
        return {row[1] for row in conn.execute(f"PRAGMA table_info('{table}')")}

    def tables(conn):
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    db_file = tmp_path / "watch.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0154')")
        conn.commit()
    _downgrade_to(db_url, "0153")
    with sqlite3.connect(db_file) as conn:
        assert "main_notices" not in tables(conn)
        assert "merged_sha" not in columns(conn, "task_integrations")
        assert "main_tip_seen" not in columns(conn, "projects")
        conn.execute(
            "INSERT INTO projects (id, name, created_at, main_branch) VALUES ('proj-old', 'Old', "
            "'2026-10-01T00:00:00', 'main')"
        )
        conn.commit()

    _upgrade_to(db_url, "0154")

    with sqlite3.connect(db_file) as conn:
        assert "main_notices" in tables(conn)
        assert "merged_sha" in columns(conn, "task_integrations")
        assert conn.execute(
            "SELECT main_branch, main_tip_seen FROM projects WHERE id = 'proj-old'"
        ).fetchone() == ("main", None)

    _downgrade_to(db_url, "0153")

    with sqlite3.connect(db_file) as conn:
        assert "main_notices" not in tables(conn)
        assert "main_tip_seen" not in columns(conn, "projects")
        assert conn.execute("SELECT id FROM projects").fetchall() == [("proj-old",)]


async def test_a_batched_landing_is_the_hubs_own_and_a_hand_commit_still_raises(
    app, auth_headers, tmp_path, tmp_path_factory, monkeypatch
):
    """B2: every integration row a batch writes carries its merge commit, so the watch (restarted,
    memory empty) raises nothing for the batch and adds nothing to an open notice."""
    from . import test_approved_work_merges_in_batches as batches

    monkeypatch.setattr(batches.queue(), "BATCH_GATHER_SECONDS", 3600.0)
    check, _ = batches.counting_check(tmp_path_factory)
    ids, _ = await batches.tasks_under_review(tmp_path, 2)
    await batches.set_checks([check])  # with checks, approval lands through the batch queue
    await project_checks.drain()
    await project_checks.watch_main_once()
    hand = _commit(tmp_path, "hand.txt", "Hand work")
    await project_checks.watch_main_once()
    (opened,) = await _notices(app, auth_headers)
    assert [c["subject"] for c in opened["commits"]] == ["Hand work"]

    for task_id in ids:
        assert (await batches.approve(app, auth_headers, task_id)).status_code == 200
    await batches.queue().drain()
    await project_checks.drain()
    merges = git(tmp_path, "rev-list", "--first-parent", f"{hand}..main").stdout.split()
    assert len(merges) == 2
    for task_id in ids:
        [row] = await batches.merged_rows(task_id)
        assert row.merged_sha in merges, (task_id, row.merged_sha, merges)

    _restart()
    await project_checks.watch_main_once()
    (notice,) = await _notices(app, auth_headers)
    assert [c["subject"] for c in notice["commits"]] == ["Hand work"], notice["commits"]

    later = _commit(tmp_path, "later.txt", "Later hand work")
    await project_checks.watch_main_once()
    (notice,) = await _notices(app, auth_headers)
    assert [c["subject"] for c in notice["commits"]][0] == "Later hand work"
    assert notice["new_tip"] == later
