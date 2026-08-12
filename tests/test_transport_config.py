"""Tests for the transport factory's configuration discovery and construction."""

from __future__ import annotations

import json

import pytest

from agentweave.transport.config import _find_transport_config, get_transport
from agentweave.transport.http import HttpTransport


def _write_transport_json(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestGetTransportBoundRun:
    def test_bound_run_constructs_keyless_http_transport_without_reading_project_config(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_secret")
        monkeypatch.setenv("HUB_URL", "http://runtime:9000")
        _write_transport_json(
            tmp_path / ".agentweave" / "transport.json",
            {
                "type": "http",
                "url": "http://operator",
                "api_key": "aw_live_operator-secret",
                "project_id": "operator-project",
            },
        )

        transport = get_transport()

        assert isinstance(transport, HttpTransport)
        assert transport.url == "http://runtime:9000"
        assert transport.api_key == ""
        assert transport.project_id == ""


class TestTransportProjectBoundary:
    def test_nested_project_does_not_inherit_parent_http_transport(self, tmp_path, monkeypatch):
        parent = tmp_path / "parent"
        child = parent / "child"
        _write_transport_json(
            parent / ".agentweave" / "transport.json",
            {
                "type": "http",
                "url": "http://localhost:8000",
                "api_key": "parent-key",
                "project_id": "parent-project",
            },
        )
        (child / ".agentweave").mkdir(parents=True)
        monkeypatch.chdir(child)

        with pytest.raises(RuntimeError):
            get_transport()

    def test_subdirectory_uses_nearest_project_transport(self, tmp_path, monkeypatch):
        project = tmp_path / "project"
        nested = project / "src" / "package"
        nested.mkdir(parents=True)
        config_path = project / ".agentweave" / "transport.json"
        _write_transport_json(
            config_path,
            {"type": "http", "url": "http://localhost:8000", "api_key": "k", "project_id": "p"},
        )
        monkeypatch.chdir(nested)

        found = _find_transport_config()

        assert found is not None
        config, path = found
        assert config["type"] == "http"
        assert path == config_path


class TestGetTransportUnconfigured:
    def test_no_config_and_no_run_token_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AW_RUN_TOKEN", raising=False)

        with pytest.raises(RuntimeError, match="No transport configured"):
            get_transport()

    def test_unsupported_transport_type_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
        _write_transport_json(tmp_path / ".agentweave" / "transport.json", {"type": "git"})

        with pytest.raises(RuntimeError, match="Unsupported transport type"):
            get_transport()
