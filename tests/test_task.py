"""Tests for agentweave.task."""

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
