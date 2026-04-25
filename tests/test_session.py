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


def test_session_get_set_agent_pilot(tmp_path, monkeypatch):
    """Test that get_agent_pilot and set_agent_pilot round-trip correctly."""
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="PilotTest", principal="claude", agents=["claude", "kimi"])

    # Default should be False
    assert sess.get_agent_pilot("claude") is False
    assert sess.get_agent_pilot("kimi") is False

    # Enable pilot mode for claude
    sess.set_agent_pilot("claude", True)
    assert sess.get_agent_pilot("claude") is True
    assert sess.get_agent_pilot("kimi") is False  # kimi unchanged

    # Disable pilot mode for claude
    sess.set_agent_pilot("claude", False)
    assert sess.get_agent_pilot("claude") is False

    # Test persistence through save/load
    sess.set_agent_pilot("claude", True)
    sess.save()

    loaded = Session.load()
    assert loaded is not None
    assert loaded.get_agent_pilot("claude") is True
    assert loaded.get_agent_pilot("kimi") is False


def test_session_set_agent_pilot_invalid_agent(tmp_path, monkeypatch):
    """Test that set_agent_pilot raises ValueError for unknown agents."""
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="PilotTest", agents=["claude"])

    try:
        sess.set_agent_pilot("unknown_agent", True)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "unknown_agent" in str(e)


def test_session_get_runner_options_present():
    """get_runner_options returns the dict when set."""
    sess = Session({
        "agents": {
            "codex": {"runner_options": {"memory": False}},
        }
    })
    assert sess.get_runner_options("codex") == {"memory": False}


def test_session_get_runner_options_absent():
    """get_runner_options returns {} when not set."""
    sess = Session({
        "agents": {
            "claude": {},
        }
    })
    assert sess.get_runner_options("claude") == {}


def test_session_get_runner_options_agent_missing():
    """get_runner_options returns {} for unknown agents."""
    sess = Session({"agents": {}})
    assert sess.get_runner_options("unknown") == {}


def test_session_sync_agents_preserves_runner_options(tmp_path, monkeypatch):
    """sync_agents persists runner_options from declared config."""
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Test", agents=["codex"])
    declared = {
        "codex": {
            "runner": "codex",
            "runner_options": {"memory": False},
        }
    }
    added, updated, orphaned = sess.sync_agents(declared)
    assert "runner_options" in sess.agents["codex"]
    assert sess.agents["codex"]["runner_options"] == {"memory": False}


def test_session_sync_agents_updates_runner_options(tmp_path, monkeypatch):
    """sync_agents updates runner_options when changed."""
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Test", agents=["codex"])
    # First sync with memory false
    sess.sync_agents({
        "codex": {"runner": "codex", "runner_options": {"memory": False}}
    })
    # Second sync with memory true
    added, updated, orphaned = sess.sync_agents({
        "codex": {"runner": "codex", "runner_options": {"memory": True}}
    })
    assert "codex" in updated
    assert sess.agents["codex"]["runner_options"] == {"memory": True}
