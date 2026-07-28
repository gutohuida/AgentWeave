"""Tests for the transport factory's HTTP spec-sync source ID handling."""

from __future__ import annotations

import json

from agentweave.transport.config import _ensure_spec_source_id, get_transport
from agentweave.transport.http import HttpTransport


def _write_transport_json(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


class TestEnsureSpecSourceId:
    def test_generates_and_persists_when_missing(self, tmp_path):
        path = tmp_path / "transport.json"
        config = {"type": "http", "url": "http://x", "api_key": "k", "project_id": "p"}
        source_id = _ensure_spec_source_id(config, path)

        assert source_id
        assert config["spec_source_id"] == source_id
        persisted = json.loads(path.read_text(encoding="utf-8"))
        assert persisted["spec_source_id"] == source_id

    def test_returns_existing_without_rewriting(self, tmp_path):
        path = tmp_path / "transport.json"
        config = {
            "type": "http",
            "url": "http://x",
            "api_key": "k",
            "project_id": "p",
            "spec_source_id": "spec-src-existing",
        }
        _write_transport_json(path, config)
        mtime_before = path.stat().st_mtime

        source_id = _ensure_spec_source_id(config, path)

        assert source_id == "spec-src-existing"
        assert path.stat().st_mtime == mtime_before

    def test_generated_id_has_no_path_or_credential(self, tmp_path):
        path = tmp_path / "transport.json"
        config = {"type": "http", "api_key": "aw_live_secret", "url": "http://x"}
        source_id = _ensure_spec_source_id(config, path)

        assert "aw_live_secret" not in source_id
        assert str(tmp_path) not in source_id


class TestGetTransportSpecSourceId:
    def test_http_transport_gets_a_source_id(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_transport_json(
            tmp_path / ".agentweave" / "transport.json",
            {"type": "http", "url": "http://localhost:8000", "api_key": "k", "project_id": "p"},
        )

        transport = get_transport()

        assert isinstance(transport, HttpTransport)
        assert transport.source_id
        persisted = json.loads((tmp_path / ".agentweave" / "transport.json").read_text())
        assert persisted["spec_source_id"] == transport.source_id

    def test_existing_source_id_is_reused_across_calls(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write_transport_json(
            tmp_path / ".agentweave" / "transport.json",
            {"type": "http", "url": "http://localhost:8000", "api_key": "k", "project_id": "p"},
        )

        first = get_transport()
        second = get_transport()

        assert first.source_id == second.source_id
