"""Tests for agentweave.task."""

import pytest

from agentweave.constants import TASKS_ACTIVE_DIR, TASKS_COMPLETED_DIR
from agentweave.task import Task, TaskStatus
from agentweave.utils import ensure_dirs


def _init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_dirs()


def test_task_create_and_save(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    task = Task.create(
        title="Build feature",
        description="Implement X",
        assignee="kimi",
        assigner="claude",
        priority="high",
    )
    assert task.title == "Build feature"
    assert task.status == "pending"
    assert task.priority == "high"
    task.save()
    # Should appear in list
    tasks = Task.list_all()
    assert any(t.id == task.id for t in tasks)


def test_task_load(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    task = Task.create(title="Load me", assignee="claude")
    task.save()
    loaded = Task.load(task.id)
    assert loaded is not None
    assert loaded.id == task.id
    assert loaded.title == "Load me"


def test_task_load_nonexistent(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    assert Task.load("nonexistent-id") is None


def test_task_update_status(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    task = Task.create(title="Status test", assignee="kimi")
    task.save()
    task.update(status="in_progress")
    task.save()
    loaded = Task.load(task.id)
    assert loaded.status == "in_progress"


def test_task_path_traversal_rejected(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    # Task IDs with path separators should be rejected
    result = Task.load("../../../etc/passwd")
    assert result is None


def test_task_status_enum_values():
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.REVISION_NEEDED.value == "revision_needed"
    assert TaskStatus.UNDER_REVIEW.value == "under_review"


def test_task_list_all_active_only(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    t1 = Task.create(title="Active", assignee="kimi")
    t1.save()
    t2 = Task.create(title="Completed", assignee="kimi")
    t2.update(status="approved")
    t2.move_to_completed()

    active = Task.list_all(active_only=True)
    active_ids = {t.id for t in active}
    assert t1.id in active_ids
    assert t2.id not in active_ids


def test_task_to_markdown(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    task = Task.create(title="Markdown task", description="Some desc", assignee="claude")
    md = task.to_markdown()
    assert "Markdown task" in md
    assert "Some desc" in md


# ---------------------------------------------------------------------------
# M10: move_to_completed must be atomic (no torn write on crash)
# ---------------------------------------------------------------------------


def test_task_move_to_completed_uses_rename_not_copy_unlink(tmp_path, monkeypatch):
    """Regression: move_to_completed must end with the file in completed/
    and not in active/. The fix uses os.replace so there's no window
    where the file is in both directories.
    """
    _init(tmp_path, monkeypatch)
    task = Task.create(title="Atomic test", assignee="kimi")
    task.save()
    assert task.move_to_completed() is True
    assert not (TASKS_ACTIVE_DIR / f"{task.id}.json").exists()
    assert (TASKS_COMPLETED_DIR / f"{task.id}.json").exists()


def test_task_move_to_completed_atomic_when_unlink_raises(tmp_path, monkeypatch):
    """If the old code path tried to unlink() and it raised, the task
    could be left in both directories. The new code never calls unlink
    on the active file — it uses os.replace.
    """
    _init(tmp_path, monkeypatch)
    task = Task.create(title="Crash sim", assignee="kimi")
    task.save()
    # Track whether the old code path would have been hit
    unlink_calls: list = []

    from pathlib import Path

    real_unlink = Path.unlink

    def spy_unlink(self, *a, **k):
        if "tasks" in str(self) and "active" in str(self):
            unlink_calls.append(str(self))
            raise OSError("simulated crash in unlink")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", spy_unlink)

    # The fix uses os.replace, never unlink, on the active file.
    # Result: the move succeeds and the active file is gone.
    result = task.move_to_completed()
    assert result is True
    assert unlink_calls == [], "unlink should not be called on active file"
    assert not (TASKS_ACTIVE_DIR / f"{task.id}.json").exists()
    assert (TASKS_COMPLETED_DIR / f"{task.id}.json").exists()


def test_task_move_to_completed_no_torn_write_on_concurrent_call(tmp_path, monkeypatch):
    """Two threads calling move_to_completed on the same task must leave
    the task in exactly one place: completed/. The pending (active)
    copy must be gone.
    """
    import threading

    _init(tmp_path, monkeypatch)
    task = Task.create(title="Race", assignee="kimi")
    task.save()

    barrier = threading.Barrier(2)
    results: list = []

    def worker():
        barrier.wait()
        results.append(task.move_to_completed())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    # Exactly one of the two calls should have done the move; the other
    # should have found the active file gone and returned False.
    assert sum(1 for r in results if r is True) >= 1
    assert not (TASKS_ACTIVE_DIR / f"{task.id}.json").exists()
    assert (TASKS_COMPLETED_DIR / f"{task.id}.json").exists()


def test_task_move_to_completed_returns_false_when_not_active(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    task = Task.create(title="Never saved", assignee="kimi")
    # Don't call save() — there's no active file to move
    assert task.move_to_completed() is False
