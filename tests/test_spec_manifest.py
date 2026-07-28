"""Tests for the spec manifest module: safe path validation, recursive
discovery, manifest structural validation, and HTML head metadata parsing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentweave.spec_manifest import (
    MANIFEST_MAX_BYTES,
    MANIFEST_MAX_DOCUMENTS,
    SpecPathError,
    compute_intrinsic_conflicts,
    discover_spec_files,
    load_manifest,
    parse_html_head,
    validate_spec_path,
)


def _write(path: Path, content: str = "<html><head></head><body></body></html>") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestValidateSpecPath:
    def test_accepts_baseline_path(self):
        assert validate_spec_path("spec/agentweave-spec.html") == "spec/agentweave-spec.html"

    def test_accepts_nested_change_spec(self):
        path = "spec/changes/add-thing/spec.html"
        assert validate_spec_path(path) == path

    def test_rejects_backslash(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec\\spec.html")

    def test_rejects_uppercase(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec/Spec.html")

    def test_rejects_missing_spec_prefix(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("docs/spec.html")

    def test_rejects_non_html(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec/index.json")

    def test_rejects_dot_dot_segment(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec/../secret.html")

    def test_rejects_empty_segment(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec//spec.html")

    def test_rejects_hidden_segment(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec/.hidden/spec.html")

    def test_rejects_control_character(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec/spec\x00.html")

    def test_rejects_too_long(self):
        long_name = "a" * 260
        with pytest.raises(SpecPathError):
            validate_spec_path(f"spec/{long_name}.html")

    def test_rejects_non_string(self):
        with pytest.raises(SpecPathError):
            validate_spec_path(None)  # type: ignore[arg-type]


class TestDiscoverSpecFiles:
    def test_missing_root_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        discovered, diagnostics = discover_spec_files()
        assert discovered == {}
        assert diagnostics == []

    def test_discovers_nested_documents_in_sorted_order(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write(tmp_path / "spec" / "agentweave-spec.html")
        _write(tmp_path / "spec" / "system-map.html")
        _write(tmp_path / "spec" / "roadmaps" / "epic.html")
        _write(tmp_path / "spec" / "changes" / "add-thing" / "spec.html")
        _write(tmp_path / "spec" / "changes" / "archive" / "old-thing" / "spec.html")

        discovered, diagnostics = discover_spec_files()

        assert diagnostics == []
        assert list(discovered.keys()) == sorted(discovered.keys())
        assert "spec/agentweave-spec.html" in discovered
        assert "spec/system-map.html" in discovered
        assert "spec/roadmaps/epic.html" in discovered
        assert "spec/changes/add-thing/spec.html" in discovered
        assert "spec/changes/archive/old-thing/spec.html" in discovered

    def test_excludes_markdown(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write(tmp_path / "spec" / "spec.html")
        _write(tmp_path / "spec" / "discovery" / "notes.md", "# notes")

        discovered, _ = discover_spec_files()

        assert list(discovered.keys()) == ["spec/spec.html"]

    def test_reports_hidden_path_as_diagnostic_not_fatal(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write(tmp_path / "spec" / "spec.html")
        _write(tmp_path / "spec" / ".hidden" / "spec.html")

        discovered, diagnostics = discover_spec_files()

        assert "spec/spec.html" in discovered
        assert any(d.path == "spec/.hidden/spec.html" for d in diagnostics)

    def test_reports_uppercase_path_as_diagnostic(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _write(tmp_path / "spec" / "Weird.html")

        discovered, diagnostics = discover_spec_files()

        assert discovered == {}
        assert len(diagnostics) == 1

    @pytest.mark.skipif(
        __import__("sys").platform.startswith("win"),
        reason="symlinks require elevated privileges on Windows",
    )
    def test_escaping_symlink_is_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        outside = tmp_path / "outside.html"
        _write(outside)
        link = tmp_path / "spec" / "escape.html"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)

        discovered, diagnostics = discover_spec_files()

        assert discovered == {}
        assert any("outside spec/" in d.reason for d in diagnostics)


class TestLoadManifest:
    def _valid_manifest(self) -> dict:
        return {
            "version": 1,
            "home": "spec/agentweave-spec.html",
            "documents": [
                {
                    "path": "spec/agentweave-spec.html",
                    "title": "Baseline",
                    "kind": "baseline",
                    "status": "living",
                    "parent": None,
                    "order": 10,
                },
                {
                    "path": "spec/changes/add-thing/spec.html",
                    "title": "Add thing",
                    "kind": "change-spec",
                    "status": "draft",
                    "parent": "spec/agentweave-spec.html",
                    "order": 20,
                },
            ],
        }

    def test_valid_manifest_parses(self):
        manifest, diagnostics = load_manifest(json.dumps(self._valid_manifest()))
        assert manifest is not None
        assert diagnostics == []
        assert manifest.home == "spec/agentweave-spec.html"
        assert len(manifest.documents) == 2

    def test_malformed_json(self):
        manifest, diagnostics = load_manifest("{not json")
        assert manifest is None
        assert diagnostics[0].code == "manifest_invalid_json"

    def test_too_large(self):
        raw = json.dumps({"version": 1, "home": "spec/spec.html", "documents": []})
        padded = raw[:-1] + (" " * (MANIFEST_MAX_BYTES + 1)) + raw[-1]
        manifest, diagnostics = load_manifest(padded)
        assert manifest is None
        assert diagnostics[0].code == "manifest_too_large"

    def test_unsupported_version(self):
        data = self._valid_manifest()
        data["version"] = 2
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert diagnostics[0].code == "manifest_unsupported_version"

    def test_too_many_documents(self):
        doc = self._valid_manifest()["documents"][0]
        data = {
            "version": 1,
            "home": doc["path"],
            "documents": [doc] * (MANIFEST_MAX_DOCUMENTS + 1),
        }
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert diagnostics[0].code == "manifest_too_many_documents"

    def test_duplicate_path(self):
        data = self._valid_manifest()
        data["documents"].append(dict(data["documents"][0]))
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_duplicate_path" for d in diagnostics)

    def test_invalid_home(self):
        data = self._valid_manifest()
        data["home"] = "spec/does-not-exist.html"
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert diagnostics[-1].code == "manifest_invalid_home"

    def test_unsafe_path_rejected(self):
        data = self._valid_manifest()
        data["documents"][0]["path"] = "../escape.html"
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_unsafe_path" for d in diagnostics)

    def test_unknown_parent(self):
        data = self._valid_manifest()
        data["documents"][1]["parent"] = "spec/nonexistent.html"
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_unknown_parent" for d in diagnostics)

    def test_self_parent(self):
        data = self._valid_manifest()
        data["documents"][0]["parent"] = data["documents"][0]["path"]
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_self_parent" for d in diagnostics)

    def test_parent_cycle(self):
        data = self._valid_manifest()
        data["documents"][0]["parent"] = data["documents"][1]["path"]
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_parent_cycle" for d in diagnostics)

    @pytest.mark.parametrize(
        "kind,status",
        [("baseline", "draft"), ("system-map", "approved"), ("roadmap", "draft")],
    )
    def test_living_kind_rejects_non_living_status(self, kind, status):
        data = self._valid_manifest()
        data["documents"][0]["kind"] = kind
        data["documents"][0]["status"] = status
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_kind_status_mismatch" for d in diagnostics)

    def test_change_spec_rejects_living_status(self):
        data = self._valid_manifest()
        data["documents"][1]["status"] = "living"
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_kind_status_mismatch" for d in diagnostics)

    def test_invalid_kind(self):
        data = self._valid_manifest()
        data["documents"][0]["kind"] = "not-a-kind"
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_invalid_kind" for d in diagnostics)


class TestComputeIntrinsicConflicts:
    def _manifest(self, tmp_path):
        data = {
            "version": 1,
            "home": "spec/agentweave-spec.html",
            "documents": [
                {
                    "path": "spec/agentweave-spec.html",
                    "title": "Baseline",
                    "kind": "baseline",
                    "status": "living",
                    "parent": None,
                    "order": 10,
                }
            ],
        }
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is not None
        return manifest

    def test_no_conflict_when_html_matches(self, tmp_path):
        manifest = self._manifest(tmp_path)
        html_path = tmp_path / "spec.html"
        _write(
            html_path,
            "<html><head><title>Baseline</title>"
            '<meta name="aw-spec-kind" content="baseline">'
            '<meta name="aw-spec-status" content="living"></head></html>',
        )
        conflicts = compute_intrinsic_conflicts(manifest, {"spec/agentweave-spec.html": html_path})
        assert conflicts == []

    def test_title_conflict_detected(self, tmp_path):
        manifest = self._manifest(tmp_path)
        html_path = tmp_path / "spec.html"
        _write(html_path, "<html><head><title>Renamed</title></head></html>")
        conflicts = compute_intrinsic_conflicts(manifest, {"spec/agentweave-spec.html": html_path})
        assert len(conflicts) == 1
        assert conflicts[0].code == "intrinsic_metadata_conflict"
        assert conflicts[0].field == "title"
        assert conflicts[0].expected == "Baseline"
        assert conflicts[0].actual == "Renamed"

    def test_missing_document_is_not_a_conflict(self, tmp_path):
        manifest = self._manifest(tmp_path)
        conflicts = compute_intrinsic_conflicts(manifest, {})
        assert conflicts == []


class TestParseHtmlHead:
    def test_extracts_title_kind_status(self):
        html = """
        <html><head>
            <title>My Spec</title>
            <meta name="aw-spec-kind" content="baseline">
            <meta name="aw-spec-status" content="living">
        </head><body>ignored</body></html>
        """
        result = parse_html_head(html)
        assert result["title"] == "My Spec"
        assert result["kind"] == "baseline"
        assert result["status"] == "living"

    def test_missing_metadata_returns_none_values(self):
        result = parse_html_head("<html><head><title>Only Title</title></head></html>")
        assert result["title"] == "Only Title"
        assert result["kind"] is None
        assert result["status"] is None

    def test_ignores_content_after_head(self):
        html = (
            "<html><head><title>Head</title></head>"
            '<body><meta name="aw-spec-kind" content="roadmap"></body></html>'
        )
        result = parse_html_head(html)
        assert result["kind"] is None

    def test_handles_malformed_html_without_raising(self):
        result = parse_html_head("<html><head><title>Unclosed")
        assert result["title"] == "Unclosed"
