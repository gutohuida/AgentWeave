"""Tests for agentweave.messaging via LocalTransport."""

from agentweave.messaging import Message, MessageBus
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
