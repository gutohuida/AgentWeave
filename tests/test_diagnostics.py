"""Tests for runtime diagnostics."""

import argparse
import io
import json


def test_collect_diagnostics_is_instance_level_and_non_mutating(tmp_path, monkeypatch):
    from agentweave import diagnostics

    hub_dir = tmp_path / "native-hub"
    monkeypatch.setattr(diagnostics, "NATIVE_HUB_DIR", hub_dir)
    monkeypatch.setattr(diagnostics, "_port_is_available", lambda _port: True)
    monkeypatch.setattr(diagnostics.shutil, "which", lambda cli: f"/bin/{cli}")

    results = diagnostics.collect_diagnostics(include_network=False)
    ids = {result.id for result in results}

    assert {
        "python_version_supported",
        "hub_runtime_installed",
        "runner_cli_available",
        "hub_port_available",
        "database_location_ready",
        "hub_state_permissions_ready",
    } <= ids
    assert not {"session_missing", "config_missing", "project_context_missing"} & ids
    assert not hub_dir.exists()


def test_database_diagnostic_reports_unreadable_database(tmp_path, monkeypatch):
    from agentweave import diagnostics

    hub_dir = tmp_path / "native-hub"
    database = hub_dir / "data" / "agentweave.db"
    database.parent.mkdir(parents=True)
    database.write_text("not sqlite", encoding="utf-8")
    monkeypatch.setattr(diagnostics, "NATIVE_HUB_DIR", hub_dir)

    result = diagnostics.check_database_accessibility()

    assert result.status == "fail"
    assert result.id == "database_inaccessible"
    assert result.hint


def test_port_diagnostic_names_conflict_and_remediation(monkeypatch):
    from agentweave import diagnostics

    monkeypatch.setattr(diagnostics, "_port_is_available", lambda _port: False)

    result = diagnostics.check_port_availability(8123)

    assert result.status == "fail"
    assert result.id == "hub_port_unavailable"
    assert "8123" in result.message
    assert result.hint


def test_doctor_json_redacts_transport_api_key(tmp_path, monkeypatch, capsys):
    from agentweave.cli import cmd_doctor
    from agentweave.session import Session

    monkeypatch.chdir(tmp_path)
    session = Session.create(name="Test", agents=["claude"])
    session.save()
    transport_dir = tmp_path / ".agentweave"
    (transport_dir / "transport.json").write_text(
        json.dumps(
            {
                "type": "http",
                "url": "http://localhost:65535",
                "api_key": "aw_live_secretkey_1234567890",
                "project_id": "proj-test",
            }
        )
    )

    result = cmd_doctor(argparse.Namespace(json=True, no_network=True))

    assert result in (0, 1)
    output = capsys.readouterr().out
    assert "aw_live_secretkey" not in output
    payload = json.loads(output)
    assert "results" in payload


def test_proxy_agent_readiness_reports_missing_key(tmp_path, monkeypatch):
    from agentweave.diagnostics import check_agent_readiness
    from agentweave.session import Session

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    session = Session.create(name="Test", agents=["minimax"])
    session.set_runner_config(
        "minimax",
        "claude_proxy",
        {
            "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
            "ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY",
        },
    )
    session.save()
    monkeypatch.setattr("agentweave.diagnostics.shutil.which", lambda _cli: "/usr/bin/claude")

    results = check_agent_readiness("minimax")

    missing = [result for result in results if result.id == "proxy_api_key_missing"]
    assert missing
    assert missing[0].status == "fail"
    assert "MINIMAX_API_KEY" in missing[0].message


def test_http_transport_classifies_auth_failure():
    import urllib.error

    import pytest

    from agentweave.transport.http import HttpTransport, HubTransportError

    transport = HttpTransport("http://hub", "bad-key", "proj-test")
    err = urllib.error.HTTPError(
        url="",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b"unauthorized"),
    )

    def raise_error(*_args, **_kwargs):
        raise err

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("urllib.request.urlopen", raise_error)
        with pytest.raises(HubTransportError) as exc:
            transport._request("GET", "/status")

    assert exc.value.classification == "hub_auth_failed"


def test_http_status_check_uses_the_project_scoped_status_route(monkeypatch):
    """The Hub mounts /status only beneath /api/v1/projects/{project_id}; the
    doctor check must not call the removed unscoped route with a project_id
    query parameter (local multi-project workspace phase 6.2 cleanup)."""
    from agentweave import diagnostics

    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        return _Response()

    monkeypatch.setattr(diagnostics.urllib.request, "urlopen", fake_urlopen)

    result = diagnostics._http_status_check(
        {"url": "http://hub:8000", "api_key": "aw_live_x", "project_id": "proj-abc"}
    )

    assert result.status == "pass"
    assert captured["url"] == "http://hub:8000/api/v1/projects/proj-abc/status"
    assert "project_id=" not in captured["url"]


def test_diagnostics_warns_for_placeholder_ai_context(tmp_path, monkeypatch):
    from agentweave.diagnostics import check_project_context

    monkeypatch.chdir(tmp_path)
    context_dir = tmp_path / ".agentweave"
    context_dir.mkdir()
    (context_dir / "ai_context.md").write_text(
        "# AI Workflow Context\n\n[Replace with: what this project does]",
        encoding="utf-8",
    )

    results = check_project_context()

    assert results[0].id == "project_context_placeholder"
    assert results[0].status == "warn"


def test_agent_context_diagnostics_report_injection_and_staleness(tmp_path, monkeypatch):
    import os
    import time

    from agentweave.diagnostics import check_agent_readiness
    from agentweave.session import Session

    monkeypatch.chdir(tmp_path)
    session = Session.create(name="Test", agents=["claude"])
    session.save()
    context_dir = tmp_path / ".agentweave" / "context"
    context_dir.mkdir(parents=True)
    context_path = context_dir / "claude.md"
    context_path.write_text("# old context\n", encoding="utf-8")
    ai_context = tmp_path / ".agentweave" / "ai_context.md"
    ai_context.write_text("# Project\n\nFresh context.", encoding="utf-8")
    future = time.time() + 10
    os.utime(ai_context, (future, future))
    monkeypatch.setattr("agentweave.diagnostics.shutil.which", lambda _cli: "/usr/bin/claude")

    results = check_agent_readiness("claude")
    by_id = {result.id: result for result in results}

    assert by_id["agent_context_present"].data["injection"] == "--append-system-prompt-file"
    assert "agent_context_stale" in by_id
    assert "agent_context_incomplete" in by_id
