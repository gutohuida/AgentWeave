"""Tests for runtime diagnostics."""

import argparse
import io
import json
from unittest.mock import MagicMock


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


def test_agent_configure_warns_for_missing_proxy_key(tmp_path, monkeypatch, capsys):
    from agentweave.cli import cmd_agent_configure
    from agentweave.session import Session

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    session = Session.create(name="Test", agents=["minimax"])
    session.save()
    monkeypatch.setattr("agentweave.diagnostics.shutil.which", lambda _cli: "/usr/bin/claude")

    result = cmd_agent_configure(
        argparse.Namespace(
            agent_name="minimax",
            runner="claude_proxy",
            base_url=None,
            api_key_var=None,
            model=None,
            pilot=None,
        )
    )

    assert result == 0
    output = capsys.readouterr().out
    assert "MINIMAX_API_KEY" in output
    assert "not set" in output


def test_watchdog_skips_proxy_launch_when_key_missing(tmp_path, monkeypatch):
    from agentweave import watchdog as wd
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
    monkeypatch.setattr("agentweave.locking.acquire_lock", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("agentweave.locking.release_lock", lambda *_args, **_kwargs: None)
    popen = MagicMock()
    monkeypatch.setattr(wd.subprocess, "Popen", popen)
    transport = MagicMock()

    wd._run_agent_subprocess(
        "minimax",
        ["claude", "-p", "hello"],
        "subject",
        transport,
        True,
        {
            "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
            "ANTHROPIC_API_KEY_VAR": "MINIMAX_API_KEY",
        },
    )

    popen.assert_not_called()
    transport.post_agent_output.assert_called()
    transport.push_log.assert_called()


def test_direct_trigger_missing_cli_preserves_unread_message(tmp_path, monkeypatch):
    from agentweave import watchdog as wd
    from agentweave.session import Session

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(wd, "TRIGGERED_DIRECT_FILE", tmp_path / "triggered_direct.json")
    monkeypatch.setattr(wd, "_load_triggered_ids", lambda max_age_hours=24: set())
    monkeypatch.setattr(wd, "_save_triggered_id", lambda msg_id: None)
    monkeypatch.setattr(wd, "_check_cli_available", lambda agent: False)
    session = Session(
        {
            "id": "test-session",
            "name": "Test",
            "mode": "hierarchical",
            "agents": {"codex": {"runner": "codex"}},
        }
    )
    monkeypatch.setattr(Session, "load", staticmethod(lambda: session))
    transport = MagicMock()
    transport.get_transport_type.return_value = "http"

    callback = wd._make_direct_trigger_callback(transport=transport)
    callback(
        "new_message",
        {
            "from": "user",
            "to": "codex",
            "subject": "Direct message from Hub",
            "id": "msg-retryable",
            "content": "hello",
        },
    )

    transport.archive_message.assert_not_called()


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
