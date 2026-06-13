"""Tests for agentweave.messaging via LocalTransport."""

import pytest

from agentweave.messaging import Message, MessageBus, _check_id_safe
from agentweave.utils import ensure_dirs


def _init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ensure_dirs()
    # Ensure LocalTransport is active (no transport.json)
    return tmp_path


def test_message_create(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    msg = Message.create(
        sender="claude",
        recipient="kimi",
        content="Hello Kimi",
        subject="Greeting",
        message_type="message",
    )
    assert msg.sender == "claude"
    assert msg.recipient == "kimi"
    assert msg.content == "Hello Kimi"
    assert msg.subject == "Greeting"
    assert not msg.is_read


def test_message_send_and_receive(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    msg = Message.create(sender="claude", recipient="kimi", content="Task ready")
    ok = MessageBus.send(msg)
    assert ok

    inbox = MessageBus.get_inbox("kimi")
    assert any(m.id == msg.id for m in inbox)


def test_message_mark_read(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    msg = Message.create(sender="claude", recipient="kimi", content="Read me")
    MessageBus.send(msg)

    ok = MessageBus.mark_read(msg.id)
    assert ok

    # Should no longer be in inbox
    inbox = MessageBus.get_inbox("kimi")
    assert not any(m.id == msg.id for m in inbox)


def test_inbox_empty_for_unknown_agent(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    inbox = MessageBus.get_inbox("nobody")
    assert inbox == []


def test_message_invalid_type_defaults_to_message(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    msg = Message.create(
        sender="claude",
        recipient="kimi",
        content="x",
        message_type="invalid_type",
    )
    assert msg.message_type == "message"


def test_message_to_markdown():
    msg = Message.create(sender="alice", recipient="bob", content="Hello", subject="Hi")
    md = msg.to_markdown()
    assert "ALICE" in md
    assert "bob" in md
    assert "Hello" in md


# ---------------------------------------------------------------------------
# S2: defense-in-depth path-traversal protection at the transport boundary
# ---------------------------------------------------------------------------


def test_check_id_safe_rejects_path_traversal():
    with pytest.raises(ValueError):
        _check_id_safe("../../etc/passwd")


def test_check_id_safe_rejects_backslash():
    with pytest.raises(ValueError):
        _check_id_safe("..\\windows\\system32")


def test_check_id_safe_rejects_absolute_path():
    with pytest.raises(ValueError):
        _check_id_safe("/etc/passwd")


def test_check_id_safe_rejects_empty():
    with pytest.raises(ValueError):
        _check_id_safe("")


def test_check_id_safe_rejects_non_string():
    with pytest.raises(ValueError):
        _check_id_safe(None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        _check_id_safe(123)  # type: ignore[arg-type]


def test_check_id_safe_accepts_legitimate_msg_id():
    # Should not raise
    _check_id_safe("msg-abcdef12")
    _check_id_safe("msg-12345678")
    _check_id_safe("a")
    _check_id_safe("task-001")


def test_message_load_rejects_path_traversal(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        Message.load("../../etc/passwd")
    with pytest.raises(ValueError):
        Message.load("..\\..\\sensitive.json")


def test_message_load_rejects_path_traversal_archive(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        Message.load("../../etc/passwd", pending=False)


def test_local_transport_archive_message_rejects_bad_id(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    from agentweave.transport.local import LocalTransport

    t = LocalTransport()
    with pytest.raises(ValueError):
        t.archive_message("../escape")
    with pytest.raises(ValueError):
        t.archive_message("")


def test_message_mark_read_rejects_bad_id(tmp_path, monkeypatch):
    _init(tmp_path, monkeypatch)
    msg = Message.create(sender="claude", recipient="kimi", content="x")
    MessageBus.send(msg)
    # Valid id works
    assert MessageBus.mark_read(msg.id) is True
    # Bad id raises
    with pytest.raises(ValueError):
        MessageBus.mark_read("../../etc/passwd")
