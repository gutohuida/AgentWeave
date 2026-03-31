"""Tests for agentweave.transport.local (LocalTransport)."""

from agentweave.transport.local import LocalTransport
from agentweave.utils import ensure_dirs, generate_id, now_iso


def _transport(tmp_path, monkeypatch) -> LocalTransport:
    monkeypatch.chdir(tmp_path)
    ensure_dirs()
    return LocalTransport()


def _msg(sender="claude", recipient="kimi", content="hello"):
    return {
        "id": generate_id("msg"),
        "from": sender,
        "to": recipient,
        "content": content,
        "subject": "",
        "type": "message",
        "timestamp": now_iso(),
        "read": False,
    }


def _task(assignee="kimi"):
    return {
        "id": generate_id("task"),
        "title": "Test task",
        "description": "",
        "status": "pending",
        "priority": "medium",
        "assignee": assignee,
        "created_at": now_iso(),
    }


def test_transport_type(tmp_path, monkeypatch):
    t = _transport(tmp_path, monkeypatch)
    assert t.get_transport_type() == "local"


def test_send_and_receive_message(tmp_path, monkeypatch):
    t = _transport(tmp_path, monkeypatch)
    msg = _msg()
    assert t.send_message(msg) is True

    pending = t.get_pending_messages("kimi")
    assert any(m["id"] == msg["id"] for m in pending)


def test_archive_message(tmp_path, monkeypatch):
    t = _transport(tmp_path, monkeypatch)
    msg = _msg()
    t.send_message(msg)
    assert t.archive_message(msg["id"]) is True

    # Should no longer be pending
    pending = t.get_pending_messages("kimi")
    assert not any(m["id"] == msg["id"] for m in pending)


def test_get_pending_messages_empty(tmp_path, monkeypatch):
    t = _transport(tmp_path, monkeypatch)
    assert t.get_pending_messages("nobody") == []


def test_send_task(tmp_path, monkeypatch):
    t = _transport(tmp_path, monkeypatch)
    task = _task()
    assert t.send_task(task) is True

    tasks = t.get_active_tasks()
    assert any(tk["id"] == task["id"] for tk in tasks)


def test_get_active_tasks_filtered_by_agent(tmp_path, monkeypatch):
    t = _transport(tmp_path, monkeypatch)
    t.send_task(_task(assignee="kimi"))
    t.send_task(_task(assignee="claude"))

    kimi_tasks = t.get_active_tasks(agent="kimi")
    assert all(tk.get("assignee") == "kimi" for tk in kimi_tasks)


def test_get_active_tasks_empty(tmp_path, monkeypatch):
    t = _transport(tmp_path, monkeypatch)
    assert t.get_active_tasks() == []
