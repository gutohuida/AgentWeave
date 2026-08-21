"""corpus-aware-documents §1: assembling the corpus context `render_document` will consume.

`corpus_summaries` and `build_corpus_context` live in `spec_documents.py` because they are the only
things in this change that reach the filesystem — `spec_render.py` stays exactly as ignorant of the
database and disk as its docstring says. These tests exercise them directly, against real files on
disk, rather than through a route: the route that calls them (reindex, corpus-aware-documents §4)
does not exist yet.
"""

from __future__ import annotations

import json

import pytest

from hub import spec_documents
from hub.project_workspace import ProjectWorkspace
from hub.spec_manifest import load_manifest
from hub.spec_payload import SCHEMA_VERSION, payload_to_dict, validate_payload
from hub.spec_render import render_document


@pytest.fixture
def workspace(tmp_path):
    return ProjectWorkspace(project_id="proj-test", root=tmp_path, path_key="test:proj-test")


def _write_document(workspace, path, *, summary="", kind="capability"):
    payload = validate_payload(
        {"schema_version": SCHEMA_VERSION, "kind": kind, "title": path, "summary": summary}
    )
    stored = payload_to_dict(payload)
    html = render_document(payload, {}, phase="current", stored_payload=stored)
    spec_documents.write_document(workspace, path, html)


def _manifest(home, entries):
    """`entries`: (path, title, kind, status, parent, order) tuples."""
    manifest, diagnostics = load_manifest(
        json.dumps(
            {
                "version": 1,
                "home": home,
                "documents": [
                    {
                        "path": path,
                        "title": title,
                        "kind": kind,
                        "status": status,
                        "parent": parent,
                        "order": order,
                    }
                    for path, title, kind, status, parent, order in entries
                ],
            }
        )
    )
    assert manifest is not None, diagnostics
    return manifest


class TestCorpusSummaries:
    def test_reads_each_documents_summary_once(self, workspace):
        _write_document(workspace, "spec/a.html", summary="What A does.")
        _write_document(workspace, "spec/b.html", summary="What B does.")
        manifest = _manifest(
            "spec/a.html",
            [
                ("spec/a.html", "A", "capability", "current", None, 10),
                ("spec/b.html", "B", "capability", "current", None, 20),
            ],
        )

        summaries = spec_documents.corpus_summaries(workspace, manifest)

        assert summaries == {"spec/a.html": "What A does.", "spec/b.html": "What B does."}

    def test_an_empty_summary_is_absent_not_a_blank_string(self, workspace):
        _write_document(workspace, "spec/a.html", summary="")
        manifest = _manifest(
            "spec/a.html", [("spec/a.html", "A", "capability", "current", None, 10)]
        )

        assert spec_documents.corpus_summaries(workspace, manifest) == {}

    def test_a_manifest_entry_with_no_file_on_disk_is_simply_absent(self, workspace):
        manifest = _manifest(
            "spec/a.html", [("spec/a.html", "A", "capability", "current", None, 10)]
        )

        assert spec_documents.corpus_summaries(workspace, manifest) == {}

    def test_a_file_with_no_payload_block_is_simply_absent(self, workspace):
        spec_documents.write_document(
            workspace, "spec/a.html", "<html><body>hand-written</body></html>"
        )
        manifest = _manifest(
            "spec/a.html", [("spec/a.html", "A", "capability", "current", None, 10)]
        )

        assert spec_documents.corpus_summaries(workspace, manifest) == {}


class TestBuildCorpusContext:
    def test_the_home_has_no_parent(self, workspace):
        manifest = _manifest(
            "spec/home.html", [("spec/home.html", "Home", "system-map", "approved", None, 10)]
        )

        context = spec_documents.build_corpus_context(manifest, "spec/home.html", {})

        assert context.home == "spec/home.html"
        assert context.parent is None

    def test_a_filed_documents_parent_is_its_path_and_title(self, workspace):
        manifest = _manifest(
            "spec/home.html",
            [
                ("spec/home.html", "Home", "system-map", "approved", None, 10),
                ("spec/a.html", "A", "capability", "current", "spec/home.html", 20),
            ],
        )

        context = spec_documents.build_corpus_context(manifest, "spec/a.html", {})

        assert context.parent == ("spec/home.html", "Home")

    def test_children_are_ordered_by_the_manifests_order_not_alphabetically(self, workspace):
        manifest = _manifest(
            "spec/home.html",
            [
                ("spec/home.html", "Home", "system-map", "approved", None, 10),
                ("spec/z.html", "Z", "capability", "current", "spec/home.html", 20),
                ("spec/a.html", "A", "capability", "current", "spec/home.html", 30),
            ],
        )

        context = spec_documents.build_corpus_context(manifest, "spec/home.html", {})

        assert [child.path for child in context.children] == ["spec/z.html", "spec/a.html"]

    def test_a_document_with_no_children_gets_an_empty_tuple(self, workspace):
        manifest = _manifest(
            "spec/home.html",
            [
                ("spec/home.html", "Home", "system-map", "approved", None, 10),
                ("spec/a.html", "A", "capability", "current", "spec/home.html", 20),
            ],
        )

        context = spec_documents.build_corpus_context(manifest, "spec/a.html", {})

        assert context.children == ()

    def test_a_grandchild_is_not_a_child(self, workspace):
        """D2/D5: navigation is bounded to direct relationships. A capability nested two deep under
        the home must not show up in the home's own child list."""
        manifest = _manifest(
            "spec/home.html",
            [
                ("spec/home.html", "Home", "system-map", "approved", None, 10),
                ("spec/area.html", "Area", "system-map", "approved", "spec/home.html", 20),
                ("spec/leaf.html", "Leaf", "capability", "current", "spec/area.html", 30),
            ],
        )

        context = spec_documents.build_corpus_context(manifest, "spec/home.html", {})

        assert [child.path for child in context.children] == ["spec/area.html"]

    def test_each_child_carries_its_summary_from_the_precomputed_map(self, workspace):
        manifest = _manifest(
            "spec/home.html",
            [
                ("spec/home.html", "Home", "system-map", "approved", None, 10),
                ("spec/a.html", "A", "capability", "current", "spec/home.html", 20),
            ],
        )

        context = spec_documents.build_corpus_context(
            manifest, "spec/home.html", {"spec/a.html": "What A does."}
        )

        assert context.children[0].summary == "What A does."

    def test_a_child_with_no_summary_in_the_map_gets_the_empty_string_not_a_lookup_error(
        self, workspace
    ):
        manifest = _manifest(
            "spec/home.html",
            [
                ("spec/home.html", "Home", "system-map", "approved", None, 10),
                ("spec/a.html", "A", "capability", "current", "spec/home.html", 20),
            ],
        )

        context = spec_documents.build_corpus_context(manifest, "spec/home.html", {})

        assert context.children[0].summary == ""

    def test_a_child_carries_its_kind_and_phase(self, workspace):
        manifest = _manifest(
            "spec/home.html",
            [
                ("spec/home.html", "Home", "system-map", "approved", None, 10),
                ("spec/a.html", "A", "change-spec", "proposed", "spec/home.html", 20),
            ],
        )

        context = spec_documents.build_corpus_context(manifest, "spec/home.html", {})

        assert context.children[0].kind == "change-spec"
        assert context.children[0].phase == "proposed"

    def test_a_path_not_in_the_manifest_still_gets_the_home_and_an_empty_shape(self, workspace):
        """A document being rendered for the first time, before it has a row or an index entry,
        still needs a home to link to."""
        manifest = _manifest(
            "spec/home.html", [("spec/home.html", "Home", "system-map", "approved", None, 10)]
        )

        context = spec_documents.build_corpus_context(manifest, "spec/not-yet-filed.html", {})

        assert context.home == "spec/home.html"
        assert context.parent is None
        assert context.children == ()
