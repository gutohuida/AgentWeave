"""Tests for the Hub's own spec manifest module (structural validation +
HTML head parsing). No filesystem discovery here — the Hub only ever sees
uploaded content and manifest text."""

from __future__ import annotations

import json

import pytest

from hub.spec_manifest import (
    MANIFEST_MAX_BYTES,
    MANIFEST_MAX_DOCUMENTS,
    SpecPathError,
    compute_intrinsic_conflicts,
    load_manifest,
    parse_html_head,
    validate_spec_path,
)


class TestValidateSpecPath:
    def test_accepts_baseline_path(self):
        assert validate_spec_path("spec/agentweave-spec.html") == "spec/agentweave-spec.html"

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

    def test_rejects_hidden_segment(self):
        with pytest.raises(SpecPathError):
            validate_spec_path("spec/.hidden/spec.html")


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

    def test_unknown_parent(self):
        data = self._valid_manifest()
        data["documents"][1]["parent"] = "spec/nonexistent.html"
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_unknown_parent" for d in diagnostics)

    def test_parent_cycle(self):
        data = self._valid_manifest()
        data["documents"][0]["parent"] = data["documents"][1]["path"]
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_parent_cycle" for d in diagnostics)

    def test_living_kind_rejects_draft_status(self):
        data = self._valid_manifest()
        data["documents"][0]["status"] = "draft"
        manifest, diagnostics = load_manifest(json.dumps(data))
        assert manifest is None
        assert any(d.code == "manifest_kind_status_mismatch" for d in diagnostics)

    def test_diagnostic_serializes_to_dict(self):
        _, diagnostics = load_manifest("{not json")
        assert diagnostics[0].to_dict()["code"] == "manifest_invalid_json"


class TestComputeIntrinsicConflicts:
    def _manifest(self):
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
        manifest, _ = load_manifest(json.dumps(data))
        assert manifest is not None
        return manifest

    def test_no_conflict_when_content_matches(self):
        manifest = self._manifest()
        content = (
            "<html><head><title>Baseline</title>"
            '<meta name="aw-spec-kind" content="baseline">'
            '<meta name="aw-spec-status" content="living"></head></html>'
        )
        conflicts = compute_intrinsic_conflicts(manifest, {"spec/agentweave-spec.html": content})
        assert conflicts == []

    def test_title_conflict_detected(self):
        manifest = self._manifest()
        content = "<html><head><title>Renamed</title></head></html>"
        conflicts = compute_intrinsic_conflicts(manifest, {"spec/agentweave-spec.html": content})
        assert len(conflicts) == 1
        assert conflicts[0].field == "title"

    def test_missing_content_is_not_a_conflict(self):
        manifest = self._manifest()
        assert compute_intrinsic_conflicts(manifest, {}) == []


class TestParseHtmlHead:
    def test_extracts_title_kind_status(self):
        html = (
            "<html><head><title>My Spec</title>"
            '<meta name="aw-spec-kind" content="baseline">'
            '<meta name="aw-spec-status" content="living"></head></html>'
        )
        result = parse_html_head(html)
        assert result == {"title": "My Spec", "kind": "baseline", "status": "living"}
