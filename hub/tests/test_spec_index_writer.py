"""Writing `spec/index.json` — the file that carries a corpus's structure between machines.

Until 2026-08-20 nothing in the product wrote this file, so every project reported its documents
as `unindexed` with a `home_ambiguous` diagnostic no matter how well formed they were. These tests
cover the writer and the operator route that reaches it.

The distinction that matters throughout: `POST /spec/reindex` rebuilds *two* indexes. The
requirement index is database rows and does not travel. `spec/index.json` is a file and is the only
record of home, hierarchy and ordering that survives the folder being copied.
"""

from __future__ import annotations

import json

import pytest

from hub import spec_documents
from hub.spec_manifest import load_manifest

BASE = "/api/v1/projects/proj-test/project"


def test_no_agent_facing_tool_can_write_the_index():
    """Presentation is an operator decision, and the agent surface must not offer it.

    Asserted against the real tool list rather than by reading the module, because the failure
    this guards against is someone adding a convenience tool later — which reads as helpful and
    would let a run rearrange a corpus the operator arranged.
    """
    import asyncio

    from hub import mcp_server

    names = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
    assert not {name for name in names if "index" in name or "reindex" in name}


@pytest.mark.asyncio
async def test_reindex_refuses_a_credential_that_is_not_the_operators(app, tmp_path):
    """The route's other half of the same boundary. `get_project` resolves an operator credential
    (`aw_live_...`) and nothing else, so a run-scoped token cannot reach the writer."""
    _write(tmp_path, "spec/spec.html")

    for header in ({}, {"Authorization": "Bearer aw_run_not_an_operator"}):
        response = await app.post(f"{BASE}/spec/reindex", headers=header)
        assert response.status_code == 401, response.text
    assert not (tmp_path / "spec" / "index.json").exists()


def _write(tmp_path, relative: str, content: str = "<html><body>doc</body></html>") -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _rows(*specs):
    """`(path, title, kind, phase)` tuples, as `build_index` takes them."""
    return list(specs)


class TestBuildIndex:
    def test_a_lone_document_needs_no_home_decision(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.html"], _rows(("spec/a.html", "A", "capability", "current")), None
        )
        assert manifest is not None
        assert manifest.home == "spec/a.html"
        assert diagnostics == []

    def test_several_documents_with_no_home_write_nothing(self):
        """The Hub refuses to guess a home, so there is nothing valid to write. This is the case
        the 33-document corpus migration hits immediately."""
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.html", "spec/b.html"],
            _rows(
                ("spec/a.html", "A", "capability", "current"),
                ("spec/b.html", "B", "capability", "current"),
            ),
            None,
        )
        assert manifest is None
        codes = {d["code"] for d in diagnostics}
        assert "home_ambiguous" in codes
        assert "index_home_required" in codes

    def test_an_explicit_home_answers_the_question(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.html", "spec/b.html"],
            _rows(
                ("spec/a.html", "A", "capability", "current"),
                ("spec/b.html", "B", "capability", "current"),
            ),
            None,
            home="spec/b.html",
        )
        assert manifest is not None
        assert manifest.home == "spec/b.html"
        assert diagnostics == []

    def test_an_explicit_home_that_does_not_exist_is_refused_not_substituted(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.html", "spec/b.html"],
            _rows(
                ("spec/a.html", "A", "capability", "current"),
                ("spec/b.html", "B", "capability", "current"),
            ),
            None,
            home="spec/nowhere.html",
        )
        assert manifest is None
        assert any(d["code"] == "home_missing" for d in diagnostics)

    def test_a_new_document_is_ordered_after_an_arranged_corpus_not_among_it(self):
        """Regression: adding one document to an arranged corpus must not collide with it.

        Numbering a new document from its position alone put it at order 10 alongside whatever the
        operator had already placed there. `order` carries no uniqueness constraint, so the
        manifest still validated and the display order among the tie was arbitrary — found by
        adding a system map to a 33-document imported corpus, which produced three entries all
        claiming order 10.
        """
        existing, _ = load_manifest(
            json.dumps(
                {
                    "version": 1,
                    "home": "spec/b.html",
                    "documents": [
                        {
                            "path": "spec/b.html",
                            "title": "B",
                            "kind": "capability",
                            "status": "current",
                            "parent": None,
                            "order": 10,
                        },
                        {
                            "path": "spec/c.html",
                            "title": "C",
                            "kind": "capability",
                            "status": "current",
                            "parent": None,
                            "order": 20,
                        },
                    ],
                }
            )
        )
        manifest, _ = spec_documents.build_index(
            ["spec/a.html", "spec/b.html", "spec/c.html"],
            _rows(
                ("spec/a.html", "A", "capability", "current"),
                ("spec/b.html", "B", "capability", "current"),
                ("spec/c.html", "C", "capability", "current"),
            ),
            existing,
        )
        by_path = manifest.by_path()
        assert by_path["spec/b.html"].order == 10, "an arranged document must not move"
        assert by_path["spec/c.html"].order == 20
        assert by_path["spec/a.html"].order == 30, "the new document goes after, not among"
        orders = [document.order for document in manifest.documents]
        assert len(orders) == len(set(orders)), f"orders collide: {orders}"

    def test_order_is_a_stable_path_sort_and_repeats_identically(self):
        args = (
            ["spec/c.html", "spec/a.html", "spec/b.html"],
            _rows(
                ("spec/c.html", "C", "capability", "current"),
                ("spec/a.html", "A", "capability", "current"),
                ("spec/b.html", "B", "capability", "current"),
            ),
            None,
        )
        first, _ = spec_documents.build_index(*args, home="spec/a.html")
        second, _ = spec_documents.build_index(*args, home="spec/a.html")
        assert [d.path for d in first.documents] == ["spec/a.html", "spec/b.html", "spec/c.html"]
        assert first == second

    def test_documents_are_left_unparented_rather_than_nested_by_directory(self):
        manifest, _ = spec_documents.build_index(
            ["spec/capabilities/a/spec.html", "spec/changes/b/spec.html"],
            _rows(
                ("spec/capabilities/a/spec.html", "A", "capability", "current"),
                ("spec/changes/b/spec.html", "B", "change-spec", "archived"),
            ),
            None,
            home="spec/capabilities/a/spec.html",
        )
        assert all(document.parent is None for document in manifest.documents)

    def test_a_file_the_hub_has_no_row_for_is_reported_not_invented(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.html", "spec/stray.html"],
            _rows(("spec/a.html", "A", "capability", "current")),
            None,
        )
        assert manifest is not None
        assert [d.path for d in manifest.documents] == ["spec/a.html"]
        assert any(
            d["code"] == "unindexable_document" and d["path"] == "spec/stray.html"
            for d in diagnostics
        )

    def test_the_phase_is_recorded_as_the_status(self):
        manifest, _ = spec_documents.build_index(
            ["spec/a.html"], _rows(("spec/a.html", "A", "change-spec", "archived")), None
        )
        assert manifest.documents[0].status == "archived"


class TestArrangementIsPreserved:
    def _existing(self):
        manifest, _ = load_manifest(
            json.dumps(
                {
                    "version": 1,
                    "home": "spec/b.html",
                    "documents": [
                        {
                            "path": "spec/a.html",
                            "title": "stale title",
                            "kind": "capability",
                            "status": "current",
                            "parent": "spec/b.html",
                            "order": 999,
                        },
                        {
                            "path": "spec/b.html",
                            "title": "B",
                            "kind": "capability",
                            "status": "current",
                            "parent": None,
                            "order": 5,
                        },
                    ],
                }
            )
        )
        assert manifest is not None
        return manifest

    def _rebuild(self, **kwargs):
        return spec_documents.build_index(
            ["spec/a.html", "spec/b.html"],
            _rows(
                ("spec/a.html", "A", "capability", "current"),
                ("spec/b.html", "B", "capability", "current"),
            ),
            self._existing(),
            **kwargs,
        )

    def test_a_recorded_home_survives(self):
        manifest, _ = self._rebuild()
        assert manifest.home == "spec/b.html"

    def test_recorded_parent_and_order_survive(self):
        """`parent` and `order` have no database column, so the index file is their only copy —
        a rebuild that recomputed them would silently discard the operator's arrangement."""
        manifest, _ = self._rebuild()
        entry = manifest.by_path()["spec/a.html"]
        assert entry.parent == "spec/b.html"
        assert entry.order == 999

    def test_the_title_is_refreshed_from_the_hub_not_carried(self):
        """Arrangement is the operator's and is preserved; title is the document's and is not."""
        manifest, _ = self._rebuild()
        assert manifest.by_path()["spec/a.html"].title == "A"

    def test_an_explicit_home_overrides_the_recorded_one(self):
        manifest, _ = self._rebuild(home="spec/a.html")
        assert manifest.home == "spec/a.html"


@pytest.mark.asyncio
class TestReindexRoute:
    async def test_reindex_writes_an_index_that_files_the_documents(
        self, app, auth_headers, tmp_path
    ):
        _write(tmp_path, "spec/spec.html")
        created = await app.post(
            f"{BASE}/documents",
            json={"path": "spec/spec.html", "title": "Only", "kind": "capability"},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text

        response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert response.status_code == 200, response.text
        written = response.json()["index"]["written"]
        assert written["documents"] == 1
        assert written["home"] == "spec/spec.html"

        assert (tmp_path / "spec" / "index.json").is_file()

        listed = await app.get(f"{BASE}/specs", headers=auth_headers)
        entry = listed.json()["specs"][0]
        assert entry["state"] == "filed"
        assert entry["title"] == "Only"

    async def test_the_written_index_reports_no_metadata_conflict(
        self, app, auth_headers, tmp_path
    ):
        """The regression that motivated the change: an index the Hub wrote, describing a document
        the Hub rendered, must not disagree with it."""
        _write(
            tmp_path,
            "spec/spec.html",
            "<html><head><title>Only</title>"
            '<meta name="aw-spec-kind" content="capability">'
            '<meta name="aw-spec-status" content="current"></head><body>d</body></html>',
        )
        await app.post(
            f"{BASE}/documents",
            json={"path": "spec/spec.html", "title": "Only", "kind": "capability"},
            headers=auth_headers,
        )
        await app.post(f"{BASE}/spec/reindex", headers=auth_headers)

        listed = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
        codes = {d["code"] for d in listed["diagnostics"]}
        assert "intrinsic_metadata_conflict" not in codes
        assert "home_ambiguous" not in codes
        assert listed["manifest"]["state"] == "valid"

    async def test_reindex_without_a_home_still_rebuilds_requirements_and_says_why(
        self, app, auth_headers, tmp_path
    ):
        for name in ("a", "b"):
            _write(tmp_path, f"spec/{name}.html")
            await app.post(
                f"{BASE}/documents",
                json={"path": f"spec/{name}.html", "title": name.upper(), "kind": "capability"},
                headers=auth_headers,
            )

        response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["index"]["written"] is None
        assert any(d["code"] == "home_ambiguous" for d in body["index"]["diagnostics"])
        assert not (tmp_path / "spec" / "index.json").exists()

    async def test_the_operator_can_name_the_home(self, app, auth_headers, tmp_path):
        for name in ("a", "b"):
            _write(tmp_path, f"spec/{name}.html")
            await app.post(
                f"{BASE}/documents",
                json={"path": f"spec/{name}.html", "title": name.upper(), "kind": "capability"},
                headers=auth_headers,
            )

        response = await app.post(
            f"{BASE}/spec/reindex", json={"home": "spec/b.html"}, headers=auth_headers
        )
        assert response.json()["index"]["written"]["home"] == "spec/b.html"

        listed = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
        assert listed["home"] == "spec/b.html"
        assert {s["state"] for s in listed["specs"]} == {"filed"}

    async def test_rebuilding_twice_leaves_the_file_byte_identical(
        self, app, auth_headers, tmp_path
    ):
        _write(tmp_path, "spec/spec.html")
        await app.post(
            f"{BASE}/documents",
            json={"path": "spec/spec.html", "title": "Only", "kind": "capability"},
            headers=auth_headers,
        )
        await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        first = (tmp_path / "spec" / "index.json").read_text(encoding="utf-8")
        await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        second = (tmp_path / "spec" / "index.json").read_text(encoding="utf-8")
        assert first == second
