"""Tests for agentweave.session."""

from agentweave.session import Session


def test_create_session_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="TestProject")
    assert sess.name == "TestProject"
    assert sess.principal == "claude"
    assert sess.mode == "hierarchical"
    assert "claude" in sess.agent_names
    assert "kimi" in sess.agent_names


def test_create_session_custom_agents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Multi", principal="gemini", agents=["gemini", "codex"])
    assert sess.principal == "gemini"
    assert set(sess.agent_names) == {"gemini", "codex"}


def test_session_save_and_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Persist")
    assert sess.save() is True

    loaded = Session.load()
    assert loaded is not None
    assert loaded.name == "Persist"
    assert loaded.id == sess.id


def test_session_load_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert Session.load() is None


def test_session_agent_names(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="X", principal="alpha", agents=["alpha", "beta"])
    # Both provided agents must be present
    assert {"alpha", "beta"}.issubset(set(sess.agent_names))


def test_session_get_agent_role(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Roles", principal="claude", agents=["claude", "kimi"])
    # Principal should have principal role
    assert sess.get_agent_role("claude") == "principal"
