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


def test_session_get_runner_options_present():
    """get_runner_options returns the dict when set."""
    sess = Session(
        {
            "agents": {
                "codex": {"runner_options": {"memory": False}},
            }
        }
    )
    assert sess.get_runner_options("codex") == {"memory": False}


def test_session_get_runner_options_absent():
    """get_runner_options returns {} when not set."""
    sess = Session(
        {
            "agents": {
                "claude": {},
            }
        }
    )
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
    sess.sync_agents({"codex": {"runner": "codex", "runner_options": {"memory": False}}})
    # Second sync with memory true
    added, updated, orphaned = sess.sync_agents(
        {"codex": {"runner": "codex", "runner_options": {"memory": True}}}
    )
    assert "codex" in updated
    assert sess.agents["codex"]["runner_options"] == {"memory": True}


def test_session_sync_agents_can_clear_read_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Test", agents=["reader"])
    sess.sync_agents({"reader": {"runner": "claude", "read_only": True}})
    assert sess.agents["reader"]["read_only"] is True

    sess.sync_agents({"reader": {"runner": "claude", "read_only": False}})

    assert sess.agents["reader"]["read_only"] is False


def test_session_sync_agents_updates_model(tmp_path, monkeypatch):
    """sync_agents persists model from declared config."""
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Test", agents=["kimi"])
    sess.sync_agents({"kimi": {"runner": "kimi", "model": "kimi-k2"}})
    assert sess.agents["kimi"]["model"] == "kimi-k2"


def test_session_sync_agents_clears_model_when_removed(tmp_path, monkeypatch):
    """sync_agents clears an old model when agentweave.yml no longer declares it."""
    monkeypatch.chdir(tmp_path)
    sess = Session.create(name="Test", agents=["kimi"])
    sess.sync_agents({"kimi": {"runner": "kimi", "model": "kimi-k2"}})

    _added, updated, _orphaned = sess.sync_agents({"kimi": {"runner": "kimi", "model": None}})

    assert "kimi" in updated
    assert "model" not in sess.agents["kimi"]
