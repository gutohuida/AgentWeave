"""Tests for generated AgentWeave context rendering."""

import json

from agentweave.context_builder import (
    build_agent_context,
    build_external_agent_context,
    is_placeholder_ai_context,
    render_project_operating_profile,
)
from agentweave.session import Session


def _session() -> Session:
    session = Session.create(
        name="Context Test",
        principal="claude",
        mode="hierarchical",
        agents=["claude", "kimi"],
    )
    session.set_runner_config(
        "kimi",
        "claude_proxy",
        {
            "ANTHROPIC_BASE_URL": "https://api.example.test/v1",
            "ANTHROPIC_API_KEY_VAR": "KIMI_API_KEY",
        },
        model="kimi-k2",
    )
    session.set_agent_pilot("kimi", True)
    session.set_agent_yolo("kimi", True)
    session._data["quality"] = {
        "review_required": True,
        "docs_path": "docs/decisions",
        "docs_threshold": "non_trivial",
        "echo_chamber_guard": "enforce",
        "attribution_tag": True,
        "dependency_check": True,
    }
    return session


def _roles_config():
    return {
        "version": 2,
        "agent_roles": {"claude": ["tech_lead"], "kimi": ["backend_dev"]},
        "roles": {
            "tech_lead": {"label": "Tech Lead", "file": "roles/tech_lead.md"},
            "backend_dev": {"label": "Backend Developer", "file": "roles/backend_dev.md"},
        },
    }


def test_project_operating_profile_lists_safe_team_facts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    profile = render_project_operating_profile(_session(), roles_config=_roles_config())

    assert "Project: Context Test" in profile
    assert "Mode: hierarchical" in profile
    assert "`kimi`: runner=claude_proxy; model=kimi-k2; roles=backend_dev" in profile
    assert "flags=pilot,yolo" in profile
    assert "KIMI_API_KEY" in profile
    assert "https://api.example.test" not in profile


def test_agent_context_includes_role_quality_and_project_context(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    roles_dir = tmp_path / ".agentweave" / "roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "backend_dev.md").write_text(
        "# Backend Developer\n\nBuild APIs.", encoding="utf-8"
    )
    (tmp_path / ".agentweave" / "ai_context.md").write_text(
        "# Project Context\n\nPython service.", encoding="utf-8"
    )

    result = build_agent_context(
        "kimi",
        _session(),
        roles_config=_roles_config(),
        project_instructions="Always run tests.",
    )

    assert result.declared is True
    assert result.roles == ["backend_dev"]
    assert "## Project Operating Profile" in result.context
    assert "review_required: `true`" in result.context
    assert "# Backend Developer" in result.context
    assert "Always run tests." in result.context
    assert "Python service." in result.context


def test_placeholder_ai_context_is_warned_not_injected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    roles_dir = tmp_path / ".agentweave" / "roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "backend_dev.md").write_text("# Backend Developer", encoding="utf-8")
    placeholder = "# AI Workflow Context\n\n[Replace with: what this project does]"
    (tmp_path / ".agentweave" / "ai_context.md").write_text(placeholder, encoding="utf-8")

    result = build_agent_context("kimi", _session(), roles_config=_roles_config())

    assert is_placeholder_ai_context(placeholder) is True
    assert "[Replace with:" not in result.context
    assert "contains template placeholders" in result.context
    assert ".agentweave/ai_context.md contains placeholders" in result.missing


def test_external_registered_agent_gets_provisional_boundaries(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    roles_dir = tmp_path / ".agentweave" / "roles"
    roles_dir.mkdir(parents=True)
    (roles_dir / "backend_dev.md").write_text("# Backend Developer", encoding="utf-8")

    result = build_external_agent_context(
        "hermes",
        session=_session(),
        roles_config=_roles_config(),
        registered=True,
        requested_roles=["backend_dev"],
    )

    response = result.to_response()
    assert response["registered"] is True
    assert response["declared"] is False
    assert response["provisional"] is True
    assert "do not modify files" in response["context"]
    assert "# Backend Developer" in response["context"]


def test_external_unknown_agent_gets_registration_guidance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = build_external_agent_context(
        "hermes", session=_session(), roles_config=_roles_config()
    )

    assert result.known is False
    assert result.registered is False
    assert "register_agent" in result.context
    assert "agent registration" in result.missing


def test_context_response_is_json_serializable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = build_external_agent_context(
        "hermes", session=_session(), roles_config=_roles_config()
    )

    json.dumps(result.to_response())
