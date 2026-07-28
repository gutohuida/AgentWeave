"""Tests for `agentweave spec push` — manifest diagnostics, reconciliation, --prune."""

from __future__ import annotations

import argparse
import json
from unittest.mock import MagicMock, patch

import pytest

from agentweave.cli import cmd_spec_push


def _args(prune: bool = False) -> argparse.Namespace:
    return argparse.Namespace(prune=prune)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write_spec(root, path="spec/spec.html", content="<html>main</html>"):
    full = root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def _make_transport(push_ok=True, reconcile_result=None):
    transport = MagicMock()
    transport.get_transport_type.return_value = "http"
    transport.push_spec.return_value = push_ok
    transport.reconcile_specs.return_value = (
        reconcile_result if reconcile_result is not None else {"diagnostics": [], "pruned": []}
    )
    return transport


class TestSpecPushBasics:
    def test_requires_http_transport(self, project):
        transport = MagicMock()
        transport.get_transport_type.return_value = "local"
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args())
        assert code == 1

    def test_no_spec_files(self, project):
        transport = _make_transport()
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args())
        assert code == 0
        transport.push_spec.assert_not_called()

    def test_pushes_and_reconciles(self, project):
        _write_spec(project)
        transport = _make_transport()
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args())
        assert code == 0
        transport.push_spec.assert_called_once_with("spec/spec.html", "<html>main</html>")
        transport.reconcile_specs.assert_called_once_with(
            manifest_text=None,
            manifest_state="absent",
            discovered_paths=["spec/spec.html"],
            prune=False,
        )

    def test_prune_flag_passed_through(self, project):
        _write_spec(project)
        transport = _make_transport()
        with patch("agentweave.transport.get_transport", return_value=transport):
            cmd_spec_push(_args(prune=True))
        _, kwargs = transport.reconcile_specs.call_args
        assert kwargs["prune"] is True

    def test_valid_manifest_state(self, project):
        _write_spec(project)
        manifest = {
            "version": 1,
            "home": "spec/spec.html",
            "documents": [
                {
                    "path": "spec/spec.html",
                    "title": "Main",
                    "kind": "baseline",
                    "status": "living",
                    "parent": None,
                    "order": 10,
                }
            ],
        }
        (project / "spec" / "index.json").write_text(json.dumps(manifest), encoding="utf-8")
        transport = _make_transport()
        with patch("agentweave.transport.get_transport", return_value=transport):
            cmd_spec_push(_args())
        _, kwargs = transport.reconcile_specs.call_args
        assert kwargs["manifest_state"] == "valid"
        assert kwargs["manifest_text"] == json.dumps(manifest)

    def test_invalid_manifest_state_does_not_block_reconciliation(self, project):
        _write_spec(project)
        (project / "spec" / "index.json").write_text("{not json", encoding="utf-8")
        transport = _make_transport()
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args())
        assert code == 0
        _, kwargs = transport.reconcile_specs.call_args
        assert kwargs["manifest_state"] == "invalid"

    def test_failed_push_skips_reconciliation_and_returns_error(self, project):
        _write_spec(project)
        transport = _make_transport(push_ok=False)
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args())
        assert code == 1
        transport.reconcile_specs.assert_not_called()

    def test_old_hub_without_reconcile_endpoint_is_not_fatal(self, project):
        """Backward compatibility: an old Hub has no /project/specs/reconcile.
        Per-file push succeeded, so the command must still succeed overall."""
        _write_spec(project)
        transport = MagicMock()
        transport.get_transport_type.return_value = "http"
        transport.push_spec.return_value = True
        del transport.reconcile_specs
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args())
        assert code == 0

    def test_reconcile_transport_failure_is_not_fatal(self, project):
        """reconcile_specs returning None (Hub error) must not fail a push that
        otherwise succeeded — the files are on the Hub, only reconciliation lagged."""
        _write_spec(project)
        transport = _make_transport(reconcile_result=None)
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args())
        assert code == 0

    def test_reports_pruned_paths(self, project):
        _write_spec(project)
        transport = _make_transport(
            reconcile_result={"diagnostics": [], "pruned": ["spec/changes/old/spec.html"]}
        )
        with patch("agentweave.transport.get_transport", return_value=transport):
            code = cmd_spec_push(_args(prune=True))
        assert code == 0
