"""Tests for agentweave.validator."""

from agentweave.validator import (
    sanitize_task_data,
    validate_agent_config,
    validate_message,
    validate_session,
    validate_task,
)

# ---------------------------------------------------------------------------
# validate_task
# ---------------------------------------------------------------------------


def _base_task():
    return {
        "id": "task-abc12345",
        "title": "Do something",
        "status": "pending",
        "created_at": "2026-01-01T00:00:00",
    }


def test_validate_task_valid():
    ok, errors = validate_task(_base_task())
    assert ok
    assert errors == []


def test_validate_task_missing_required_field():
    data = _base_task()
    del data["title"]
    ok, errors = validate_task(data)
    assert not ok
    assert any("title" in e for e in errors)


def test_validate_task_invalid_status():
    data = {**_base_task(), "status": "flying"}
    ok, errors = validate_task(data)
    assert not ok
    assert any("status" in e for e in errors)


def test_validate_task_invalid_priority():
    data = {**_base_task(), "priority": "superurgent"}
    ok, errors = validate_task(data)
    assert not ok
    assert any("priority" in e for e in errors)


def test_validate_task_valid_all_statuses():
    statuses = [
        "pending",
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "revision_needed",
        "approved",
        "rejected",
    ]
    for s in statuses:
        ok, errors = validate_task({**_base_task(), "status": s})
        assert ok, f"Status {s!r} should be valid, got: {errors}"


def test_validate_task_cluster_agent_assignee():
    data = {**_base_task(), "assignee": "alice.claude"}
    ok, errors = validate_task(data)
    assert ok, errors


def test_validate_task_invalid_assignee():
    data = {**_base_task(), "assignee": "bad agent name!"}
    ok, errors = validate_task(data)
    assert not ok


# ---------------------------------------------------------------------------
# validate_message
# ---------------------------------------------------------------------------


def _base_message():
    return {
        "id": "msg-abc12345",
        "from": "claude",
        "to": "kimi",
        "content": "Hello",
        "timestamp": "2026-01-01T00:00:00",
    }


def test_validate_message_valid():
    ok, errors = validate_message(_base_message())
    assert ok
    assert errors == []


def test_validate_message_missing_field():
    data = _base_message()
    del data["content"]
    ok, errors = validate_message(data)
    assert not ok
    assert any("content" in e for e in errors)


def test_validate_message_invalid_type():
    data = {**_base_message(), "type": "unknown_type"}
    ok, errors = validate_message(data)
    assert not ok


def test_validate_message_valid_types():
    for t in ("message", "delegation", "review", "discussion"):
        ok, _ = validate_message({**_base_message(), "type": t})
        assert ok, f"Type {t!r} should be valid"


# ---------------------------------------------------------------------------
# validate_session
# ---------------------------------------------------------------------------


def _base_session():
    return {
        "id": "sess-abc12345",
        "name": "Test Project",
        "created": "2026-01-01T00:00:00",
        "mode": "hierarchical",
        "principal": "claude",
    }


def test_validate_session_valid():
    ok, errors = validate_session(_base_session())
    assert ok
    assert errors == []


def test_validate_session_invalid_mode():
    data = {**_base_session(), "mode": "chaos"}
    ok, errors = validate_session(data)
    assert not ok


def test_validate_session_missing_field():
    data = _base_session()
    del data["principal"]
    ok, errors = validate_session(data)
    assert not ok


# ---------------------------------------------------------------------------
# sanitize_task_data
# ---------------------------------------------------------------------------


def test_sanitize_task_data_basic():
    data = {
        "id": "task-abc",
        "title": "My task",
        "description": "Details",
        "status": "pending",
        "priority": "high",
        "assignee": "kimi",
        "created_at": "2026-01-01T00:00:00",
    }
    result = sanitize_task_data(data)
    assert result["title"] == "My task"
    assert result["status"] == "pending"
    assert result["priority"] == "high"
    assert result["assignee"] == "kimi"


def test_sanitize_task_data_rejects_invalid_status():
    data = {"id": "t-1", "title": "x", "status": "invalid", "created_at": "now"}
    result = sanitize_task_data(data)
    assert "status" not in result


def test_sanitize_task_data_truncates_long_strings():
    data = {
        "id": "t-1",
        "title": "x" * 300,
        "description": "y" * 6000,
        "created_at": "now",
    }
    result = sanitize_task_data(data)
    assert len(result["title"]) <= 200
    assert len(result["description"]) <= 5000


# ---------------------------------------------------------------------------
# validate_agent_config
# ---------------------------------------------------------------------------


def test_validate_agent_config_valid():
    """Test valid agent config with all allowed keys."""
    data = {
        "role": "backend_dev",
        "runner": "native",
        "env_vars": {},
        "model": "claude-3-5-sonnet",
        "yolo": True,
        "pilot": False,
    }
    ok, errors = validate_agent_config(data)
    assert ok, errors
    assert errors == []


def test_validate_agent_config_invalid_key():
    """Test that invalid config keys are rejected."""
    data = {"invalid_key": "value"}
    ok, errors = validate_agent_config(data)
    assert not ok
    assert any("invalid_key" in e for e in errors)


def test_validate_agent_config_invalid_runner():
    """Test that invalid runner types are rejected."""
    data = {"runner": "invalid_runner"}
    ok, errors = validate_agent_config(data)
    assert not ok
    assert any("runner" in e for e in errors)


def test_validate_agent_config_invalid_types():
    """Test that invalid types for known keys are rejected."""
    data = {
        "yolo": "not_a_boolean",
        "pilot": "not_a_boolean",
        "env_vars": "not_a_dict",
        "model": 123,
        "role": 456,
    }
    ok, errors = validate_agent_config(data)
    assert not ok
    assert any("yolo" in e for e in errors)
    assert any("pilot" in e for e in errors)
    assert any("env_vars" in e for e in errors)
    assert any("model" in e for e in errors)
    assert any("role" in e for e in errors)


def test_validate_agent_config_empty():
    """Test that empty config is valid."""
    ok, errors = validate_agent_config({})
    assert ok
    assert errors == []
