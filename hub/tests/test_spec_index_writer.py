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
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.spec_manifest import load_manifest
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"


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
    _write(tmp_path, "spec/spec.json")

    for header in ({}, {"Authorization": "Bearer aw_run_not_an_operator"}):
        response = await app.post(f"{BASE}/spec/reindex", headers=header)
        assert response.status_code == 401, response.text
    assert not (tmp_path / "spec" / "index.json").exists()


def _write(tmp_path, relative: str, content: str = "<html><body>doc</body></html>") -> None:
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _make_hub_block_stale(tmp_path, relative: str) -> str:
    """Leave a file's hub block disagreeing with its row, as a phase move whose write failed does.

    Returns the file's text as it now stands. The payload is untouched; only the block (the row's
    copy, never the authority) is wrong.
    """
    target = tmp_path / relative
    text = target.read_text(encoding="utf-8")
    block = spec_documents.parse_hub(text)
    block["phase"] = "proposed"
    stale = spec_documents.serialize(spec_documents.parse_stored(text), block)
    assert stale != text
    target.write_text(stale, encoding="utf-8")
    return stale


async def _page(app, auth_headers, path: str) -> str:
    """The page `GET /spec` renders for a document: navigation and maps are rendered on read."""
    response = await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["content"]


def _rows(*specs):
    """`(path, title, kind, phase)` tuples, as `build_index` takes them."""
    return list(specs)


class TestBuildIndex:
    def test_a_lone_document_needs_no_home_decision(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.json"], _rows(("spec/a.json", "A", "capability", "current")), None
        )
        assert manifest is not None
        assert manifest.home == "spec/a.json"
        assert diagnostics == []

    def test_several_documents_with_no_home_write_nothing(self):
        """The Hub refuses to guess a home, so there is nothing valid to write. This is the case
        the 33-document corpus migration hits immediately."""
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.json", "spec/b.json"],
            _rows(
                ("spec/a.json", "A", "capability", "current"),
                ("spec/b.json", "B", "capability", "current"),
            ),
            None,
        )
        assert manifest is None
        codes = {d["code"] for d in diagnostics}
        assert "home_ambiguous" in codes
        assert "index_home_required" in codes

    def test_an_explicit_home_answers_the_question(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.json", "spec/b.json"],
            _rows(
                ("spec/a.json", "A", "capability", "current"),
                ("spec/b.json", "B", "capability", "current"),
            ),
            None,
            home="spec/b.json",
        )
        assert manifest is not None
        assert manifest.home == "spec/b.json"
        assert diagnostics == []

    def test_an_explicit_home_that_does_not_exist_is_refused_not_substituted(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.json", "spec/b.json"],
            _rows(
                ("spec/a.json", "A", "capability", "current"),
                ("spec/b.json", "B", "capability", "current"),
            ),
            None,
            home="spec/nowhere.json",
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
                    "home": "spec/b.json",
                    "documents": [
                        {
                            "path": "spec/b.json",
                            "title": "B",
                            "kind": "capability",
                            "status": "current",
                            "parent": None,
                            "order": 10,
                        },
                        {
                            "path": "spec/c.json",
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
            ["spec/a.json", "spec/b.json", "spec/c.json"],
            _rows(
                ("spec/a.json", "A", "capability", "current"),
                ("spec/b.json", "B", "capability", "current"),
                ("spec/c.json", "C", "capability", "current"),
            ),
            existing,
        )
        by_path = manifest.by_path()
        assert by_path["spec/b.json"].order == 10, "an arranged document must not move"
        assert by_path["spec/c.json"].order == 20
        assert by_path["spec/a.json"].order == 30, "the new document goes after, not among"
        orders = [document.order for document in manifest.documents]
        assert len(orders) == len(set(orders)), f"orders collide: {orders}"

    def test_order_is_a_stable_path_sort_and_repeats_identically(self):
        args = (
            ["spec/c.json", "spec/a.json", "spec/b.json"],
            _rows(
                ("spec/c.json", "C", "capability", "current"),
                ("spec/a.json", "A", "capability", "current"),
                ("spec/b.json", "B", "capability", "current"),
            ),
            None,
        )
        first, _ = spec_documents.build_index(*args, home="spec/a.json")
        second, _ = spec_documents.build_index(*args, home="spec/a.json")
        assert [d.path for d in first.documents] == ["spec/a.json", "spec/b.json", "spec/c.json"]
        assert first == second

    def test_documents_are_left_unparented_rather_than_nested_by_directory(self):
        manifest, _ = spec_documents.build_index(
            ["spec/capabilities/a/spec.json", "spec/changes/b/spec.json"],
            _rows(
                ("spec/capabilities/a/spec.json", "A", "capability", "current"),
                ("spec/changes/b/spec.json", "B", "change-spec", "archived"),
            ),
            None,
            home="spec/capabilities/a/spec.json",
        )
        assert all(document.parent is None for document in manifest.documents)

    def test_a_file_the_hub_has_no_row_for_is_reported_not_invented(self):
        manifest, diagnostics = spec_documents.build_index(
            ["spec/a.json", "spec/stray.json"],
            _rows(("spec/a.json", "A", "capability", "current")),
            None,
        )
        assert manifest is not None
        assert [d.path for d in manifest.documents] == ["spec/a.json"]
        assert any(
            d["code"] == "unindexable_document" and d["path"] == "spec/stray.json"
            for d in diagnostics
        )

    def test_the_phase_is_recorded_as_the_status(self):
        manifest, _ = spec_documents.build_index(
            ["spec/a.json"], _rows(("spec/a.json", "A", "change-spec", "archived")), None
        )
        assert manifest.documents[0].status == "archived"


class TestArrangementIsPreserved:
    def _existing(self):
        manifest, _ = load_manifest(
            json.dumps(
                {
                    "version": 1,
                    "home": "spec/b.json",
                    "documents": [
                        {
                            "path": "spec/a.json",
                            "title": "stale title",
                            "kind": "capability",
                            "status": "current",
                            "parent": "spec/b.json",
                            "order": 999,
                        },
                        {
                            "path": "spec/b.json",
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
            ["spec/a.json", "spec/b.json"],
            _rows(
                ("spec/a.json", "A", "capability", "current"),
                ("spec/b.json", "B", "capability", "current"),
            ),
            self._existing(),
            **kwargs,
        )

    def test_a_recorded_home_survives(self):
        manifest, _ = self._rebuild()
        assert manifest.home == "spec/b.json"

    def test_recorded_parent_and_order_survive(self):
        """`parent` and `order` have no database column, so the index file is their only copy —
        a rebuild that recomputed them would silently discard the operator's arrangement."""
        manifest, _ = self._rebuild()
        entry = manifest.by_path()["spec/a.json"]
        assert entry.parent == "spec/b.json"
        assert entry.order == 999

    def test_the_title_is_refreshed_from_the_hub_not_carried(self):
        """Arrangement is the operator's and is preserved; title is the document's and is not."""
        manifest, _ = self._rebuild()
        assert manifest.by_path()["spec/a.json"].title == "A"

    def test_an_explicit_home_overrides_the_recorded_one(self):
        manifest, _ = self._rebuild(home="spec/a.json")
        assert manifest.home == "spec/a.json"


@pytest.mark.asyncio
class TestReindexRoute:
    async def test_reindex_writes_an_index_that_files_the_documents(
        self, app, auth_headers, tmp_path
    ):
        _write(tmp_path, "spec/spec.json")
        created = await app.post(
            f"{BASE}/documents",
            json={"path": "spec/spec.json", "title": "Only", "kind": "capability"},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text

        response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert response.status_code == 200, response.text
        written = response.json()["index"]["written"]
        assert written["documents"] == 1
        assert written["home"] == "spec/spec.json"

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
        await app.post(
            f"{BASE}/documents",
            json={"path": "spec/spec.json", "title": "Only", "kind": "capability"},
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
            _write(tmp_path, f"spec/{name}.json")
            await app.post(
                f"{BASE}/documents",
                json={"path": f"spec/{name}.json", "title": name.upper(), "kind": "capability"},
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
            _write(tmp_path, f"spec/{name}.json")
            await app.post(
                f"{BASE}/documents",
                json={"path": f"spec/{name}.json", "title": name.upper(), "kind": "capability"},
                headers=auth_headers,
            )

        response = await app.post(
            f"{BASE}/spec/reindex", json={"home": "spec/b.json"}, headers=auth_headers
        )
        assert response.json()["index"]["written"]["home"] == "spec/b.json"

        listed = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
        assert listed["home"] == "spec/b.json"
        assert {s["state"] for s in listed["specs"]} == {"filed"}

    async def test_rebuilding_twice_leaves_the_file_byte_identical(
        self, app, auth_headers, tmp_path
    ):
        _write(tmp_path, "spec/spec.json")
        await app.post(
            f"{BASE}/documents",
            json={"path": "spec/spec.json", "title": "Only", "kind": "capability"},
            headers=auth_headers,
        )
        await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        first = (tmp_path / "spec" / "index.json").read_text(encoding="utf-8")
        await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        second = (tmp_path / "spec" / "index.json").read_text(encoding="utf-8")
        assert first == second


@pytest.fixture
async def run_headers():
    """A run credential, for writing content through `/agent-actions` (corpus-aware-documents §4
    tests need an approved document, and only an agent submission — not `POST /documents`, which
    leaves a document empty — can carry it through `propose`'s completeness check)."""
    token = "aw_run_corpus-rerender-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-corpus-rerender",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _full_document(**overrides):
    """A payload complete enough to clear `propose`'s completeness check."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Corpus rerender demo",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}
        ],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
        "delivery": {"mode": "none"},
    }
    payload.update(overrides)
    return payload


class TestReindexCorpusRerender:
    """corpus-aware-documents §4: reindex re-renders exactly the documents whose corpus
    navigation or map changed — design D2's bound — and updates `content_digest` (D7) for the
    ones with a row, driven from each file's own embedded payload rather than the database (D6).
    """

    async def test_setting_a_parent_shows_in_the_parent_and_the_recursive_home_and_nothing_else(
        self, app, auth_headers, tmp_path
    ):
        for name in ("home", "area", "other"):
            _write(tmp_path, f"spec/{name}.json")
            created = await app.post(
                f"{BASE}/documents",
                json={"path": f"spec/{name}.json", "title": name.upper(), "kind": "capability"},
                headers=auth_headers,
            )
            assert created.status_code == 201, created.text

        first = await app.post(
            f"{BASE}/spec/reindex", json={"home": "spec/home.json"}, headers=auth_headers
        )
        assert first.status_code == 200, first.text
        # Navigation is rendered when a page is read, never written into a file, so filing the
        # documents rewrites none of them: the files `POST /documents` wrote are already what the
        # Hub would write.
        assert first.json()["corpus"]["rerendered"] == []
        assert first.json()["corpus"]["skipped"] == []

        home_before = await _page(app, auth_headers, "spec/home.json")
        other_before = await _page(app, auth_headers, "spec/other.json")
        assert 'class="aw-map"' not in home_before, "no child yet, so no map"
        files_before = {
            name: (tmp_path / "spec" / f"{name}.json").read_bytes()
            for name in ("home", "area", "other")
        }

        # Arrange `area` under `home` by hand-editing the index: the operator's other route is
        # `POST /project/spec/documents/arrange`, and D4 documents hand-editing the file as a
        # legitimate way to rearrange the corpus.
        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        for doc in manifest_data["documents"]:
            if doc["path"] == "spec/area.json":
                doc["parent"] = "spec/home.json"
        index_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

        second = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert second.status_code == 200, second.text
        body = second.json()
        assert body["corpus"]["rerendered"] == []
        assert body["corpus"]["skipped"] == []
        assert files_before == {
            name: (tmp_path / "spec" / f"{name}.json").read_bytes()
            for name in ("home", "area", "other")
        }, "arranging a document changes no stored file"

        # `area` gained a parent link; `home` gained a map entry because its map is recursive over
        # the whole corpus (design D-S2-recursive). `other` has no relation to either, and its
        # page is exactly what it was.
        home_page = await _page(app, auth_headers, "spec/home.json")
        assert "AREA" in home_page
        assert 'class="aw-map"' in home_page
        assert 'class="aw-nav"' in await _page(app, auth_headers, "spec/area.json")
        assert await _page(app, auth_headers, "spec/other.json") == other_before

    async def test_a_reindex_rewrites_only_the_file_whose_hub_block_is_stale(
        self, app, auth_headers, tmp_path
    ):
        """What a rebuild can still find wrong in a stored file is its hub block (a phase moved
        while the write failed). Exactly that file is rewritten, to what the Hub would write."""
        await _three_filed(app, auth_headers, tmp_path)
        stale_text = _make_hub_block_stale(tmp_path, "spec/area.json")
        home_bytes = (tmp_path / "spec" / "home.json").read_bytes()
        other_bytes = (tmp_path / "spec" / "other.json").read_bytes()

        response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)

        assert response.status_code == 200, response.text
        assert response.json()["corpus"]["rerendered"] == ["spec/area.json"]
        assert response.json()["corpus"]["skipped"] == []
        area_text = (tmp_path / "spec" / "area.json").read_text(encoding="utf-8")
        assert area_text != stale_text
        assert spec_documents.parse_hub(area_text)["phase"] == "current"
        assert (tmp_path / "spec" / "home.json").read_bytes() == home_bytes
        assert (tmp_path / "spec" / "other.json").read_bytes() == other_bytes

    async def test_a_rebuild_that_changes_nothing_writes_no_file(self, app, auth_headers, tmp_path):
        _write(tmp_path, "spec/spec.json")
        await app.post(
            f"{BASE}/documents",
            json={"path": "spec/spec.json", "title": "Only", "kind": "capability"},
            headers=auth_headers,
        )
        first = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert first.status_code == 200, first.text

        before = (tmp_path / "spec" / "spec.json").stat().st_mtime_ns
        second = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert second.status_code == 200, second.text
        assert second.json()["corpus"]["rerendered"] == []
        assert second.json()["corpus"]["skipped"] == []
        after = (tmp_path / "spec" / "spec.json").stat().st_mtime_ns
        assert before == after

    async def test_an_approved_document_regenerates_rather_than_being_refused(
        self, app, auth_headers, run_headers, tmp_path
    ):
        home_path = "spec/home.json"
        child_path = "spec/changes/approved-demo/spec.json"
        for path, title, kind in (
            (home_path, "Home", "capability"),
            (child_path, "Approved demo", "change-spec"),
        ):
            _write(tmp_path, path)
            created = await app.post(
                f"{BASE}/documents",
                json={"path": path, "title": title, "kind": kind},
                headers=auth_headers,
            )
            assert created.status_code == 201, created.text

        baseline = await app.post(
            f"{BASE}/spec/reindex", json={"home": home_path}, headers=auth_headers
        )
        assert baseline.status_code == 200, baseline.text

        submitted = await app.post(
            AGENT, json={"path": child_path, "document": _full_document()}, headers=run_headers
        )
        assert submitted.status_code == 200, submitted.text
        await app.post(
            f"{BASE}/documents/close-exploration", params={"path": child_path}, headers=auth_headers
        )
        await app.post(
            f"{BASE}/documents/propose", params={"path": child_path}, headers=auth_headers
        )
        approved = await app.post(
            f"{BASE}/documents/phase",
            params={"path": child_path, "to": "approved"},
            json={"reason": "", "approve_anyway": True},
            headers=auth_headers,
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["phase"] == "approved"

        # Confirm the refusal this section deliberately bypasses actually fires on the ordinary
        # write path, so the next assertion is proof of something real.
        refused = await app.post(
            AGENT, json={"path": child_path, "document": _full_document()}, headers=run_headers
        )
        assert refused.status_code == 422
        assert refused.json()["detail"]["code"] == "document_approved"

        # Arrange the approved document under home, and leave its hub block stale, forcing a
        # rewrite of it by the rebuild.
        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        for doc in manifest_data["documents"]:
            if doc["path"] == child_path:
                doc["parent"] = home_path
        index_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
        _make_hub_block_stale(tmp_path, child_path)

        response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert response.status_code == 200, response.text
        assert child_path in response.json()["corpus"]["rerendered"]

        listed = await app.get(f"{BASE}/specs", headers=auth_headers)
        entry = next(s for s in listed.json()["specs"] if s["path"] == child_path)
        assert entry["state"] == "filed"
        child_text = (tmp_path / "spec" / "changes" / "approved-demo" / "spec.json").read_text(
            encoding="utf-8"
        )
        assert spec_documents.parse_hub(child_text)["phase"] == "approved"
        assert 'class="aw-nav"' in await _page(app, auth_headers, child_path)

    async def test_drift_is_not_reported_after_a_regeneration_but_is_after_an_outside_edit(
        self, app, auth_headers, tmp_path
    ):
        """`/spec/drift/detect` is requirement-evidence drift, unrelated to a document's own
        content digest — that divergence is reported inline on the next write attempt
        (`spec_lifecycle.divergence`, surfaced as `result["divergence"]` by the merge, the only way a
        capability is written).
        Design D7's promise is exercised here at that boundary: a rerender updates the digest, so
        the very next write reports no divergence; an edit made outside the Hub after that does.
        """
        home_path = "spec/home.json"
        child_path = "spec/child.json"
        for path, title in ((home_path, "Home"), (child_path, "Child")):
            _write(tmp_path, path)
            created = await app.post(
                f"{BASE}/documents",
                json={"path": path, "title": title, "kind": "capability"},
                headers=auth_headers,
            )
            assert created.status_code == 201, created.text
        await app.post(f"{BASE}/spec/reindex", json={"home": home_path}, headers=auth_headers)

        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        for doc in manifest_data["documents"]:
            if doc["path"] == child_path:
                doc["parent"] = home_path
        index_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")
        _make_hub_block_stale(tmp_path, child_path)

        rerendered = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert child_path in rerendered.json()["corpus"]["rerendered"]

        clean_write = await app.post(
            f"{BASE}/documents/{child_path}/merge",
            json={
                "payload": {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "capability",
                    "title": "Child",
                },
                "from_changes": [],
            },
            headers=auth_headers,
        )
        assert clean_write.status_code == 200, clean_write.text
        assert clean_write.json()["divergence"] is None

        # An outside edit that keeps the file a readable document: its layout is changed.
        child_file = tmp_path / "spec" / "child.json"
        child_file.write_text(
            json.dumps(json.loads(child_file.read_text(encoding="utf-8")), indent=4),
            encoding="utf-8",
        )

        dirty_write = await app.post(
            f"{BASE}/documents/{child_path}/merge",
            json={
                "payload": {
                    "schema_version": SCHEMA_VERSION,
                    "kind": "capability",
                    "title": "Child",
                },
                "from_changes": [],
            },
            headers=auth_headers,
        )
        assert dirty_write.status_code == 200, dirty_write.text
        assert dirty_write.json()["divergence"] is not None


class TestArrangeRoute:
    """corpus-aware-documents §5: `POST /project/spec/documents/arrange` sets or clears a
    document's parent. Validation is reused from `load_manifest`'s own structural rules
    (unknown parent, self-parent, cycle) rather than reimplemented, and the re-render step
    reuses `spec_service.rerender_corpus`, the same function §4's reindex route calls.
    """

    async def _seed(self, app, auth_headers, tmp_path, *names):
        for name in names:
            _write(tmp_path, f"spec/{name}.json")
            created = await app.post(
                f"{BASE}/documents",
                json={"path": f"spec/{name}.json", "title": name.upper(), "kind": "capability"},
                headers=auth_headers,
            )
            assert created.status_code == 201, created.text
        reindexed = await app.post(
            f"{BASE}/spec/reindex", json={"home": f"spec/{names[0]}.json"}, headers=auth_headers
        )
        assert reindexed.status_code == 200, reindexed.text

    async def test_arranging_a_document_shows_in_it_and_its_recursive_home(
        self, app, auth_headers, tmp_path
    ):
        await self._seed(app, auth_headers, tmp_path, "home", "area", "other")

        response = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/area.json", "parent": "spec/home.json"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["path"] == "spec/area.json"
        assert body["parent"] == "spec/home.json"
        # Navigation is rendered on read, so no stored file needed rewriting.
        assert body["corpus"]["rerendered"] == []
        assert body["corpus"]["skipped"] == []

        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        area_entry = next(d for d in manifest_data["documents"] if d["path"] == "spec/area.json")
        assert area_entry["parent"] == "spec/home.json"
        other_entry = next(d for d in manifest_data["documents"] if d["path"] == "spec/other.json")
        assert other_entry["parent"] is None

        home_html = await _page(app, auth_headers, "spec/home.json")
        assert "AREA" in home_html
        assert 'class="aw-map"' in home_html
        assert 'class="aw-nav"' in await _page(app, auth_headers, "spec/area.json")

    async def test_setting_parent_to_null_unparents(self, app, auth_headers, tmp_path):
        await self._seed(app, auth_headers, tmp_path, "home", "area")
        first = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/area.json", "parent": "spec/home.json"},
            headers=auth_headers,
        )
        assert first.status_code == 200, first.text

        response = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/area.json", "parent": None},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["parent"] is None

        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        area_entry = next(d for d in manifest_data["documents"] if d["path"] == "spec/area.json")
        assert area_entry["parent"] is None

    async def test_an_unknown_document_is_refused(self, app, auth_headers, tmp_path):
        await self._seed(app, auth_headers, tmp_path, "home")
        response = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/nope.json", "parent": None},
            headers=auth_headers,
        )
        assert response.status_code == 404, response.text

    async def test_an_unknown_parent_is_refused(self, app, auth_headers, tmp_path):
        await self._seed(app, auth_headers, tmp_path, "home", "area")
        response = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/area.json", "parent": "spec/nope.json"},
            headers=auth_headers,
        )
        assert response.status_code == 422, response.text
        codes = {d["code"] for d in response.json()["detail"]["diagnostics"]}
        assert "manifest_unknown_parent" in codes

        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        area_entry = next(d for d in manifest_data["documents"] if d["path"] == "spec/area.json")
        assert area_entry["parent"] is None

    async def test_a_self_parent_is_refused(self, app, auth_headers, tmp_path):
        await self._seed(app, auth_headers, tmp_path, "home", "area")
        response = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/area.json", "parent": "spec/area.json"},
            headers=auth_headers,
        )
        assert response.status_code == 422, response.text
        codes = {d["code"] for d in response.json()["detail"]["diagnostics"]}
        assert "manifest_self_parent" in codes

    async def test_a_cycle_is_refused(self, app, auth_headers, tmp_path):
        await self._seed(app, auth_headers, tmp_path, "home", "area", "leaf")
        first = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/area.json", "parent": "spec/home.json"},
            headers=auth_headers,
        )
        assert first.status_code == 200, first.text
        second = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/leaf.json", "parent": "spec/area.json"},
            headers=auth_headers,
        )
        assert second.status_code == 200, second.text

        response = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/home.json", "parent": "spec/leaf.json"},
            headers=auth_headers,
        )
        assert response.status_code == 422, response.text
        codes = {d["code"] for d in response.json()["detail"]["diagnostics"]}
        assert "manifest_parent_cycle" in codes

        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        home_entry = next(d for d in manifest_data["documents"] if d["path"] == "spec/home.json")
        assert home_entry["parent"] is None

    async def test_the_placement_survives_a_subsequent_reindex(self, app, auth_headers, tmp_path):
        await self._seed(app, auth_headers, tmp_path, "home", "area")
        arranged = await app.post(
            f"{BASE}/spec/documents/arrange",
            json={"path": "spec/area.json", "parent": "spec/home.json"},
            headers=auth_headers,
        )
        assert arranged.status_code == 200, arranged.text

        response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
        assert response.status_code == 200, response.text
        assert response.json()["corpus"]["rerendered"] == []
        assert response.json()["corpus"]["skipped"] == []

        index_path = tmp_path / "spec" / "index.json"
        manifest_data = json.loads(index_path.read_text(encoding="utf-8"))
        area_entry = next(d for d in manifest_data["documents"] if d["path"] == "spec/area.json")
        assert area_entry["parent"] == "spec/home.json"


# --------------------------------------------------------------------------- the corpus from the app
#
# `the-corpus-is-indexed-arranged-and-adopted-from-the-app`: D5 (reindex broadcasts) and D6 (F434:
# a failed file write is reported, never a bare 500 that rolls the requirement index back).


async def _three_filed(app, auth_headers, tmp_path):
    """home, area and other, filed with `home` as the corpus's home."""
    for name in ("home", "area", "other"):
        _write(tmp_path, f"spec/{name}.json")
        created = await app.post(
            f"{BASE}/documents",
            json={"path": f"spec/{name}.json", "title": name.upper(), "kind": "capability"},
            headers=auth_headers,
        )
        assert created.status_code == 201, created.text
    first = await app.post(
        f"{BASE}/spec/reindex", json={"home": "spec/home.json"}, headers=auth_headers
    )
    assert first.status_code == 200, first.text


def _failing_write_text(monkeypatch, should_fail):
    import pathlib

    real = pathlib.Path.write_text

    def write_text(self, *args, **kwargs):
        if should_fail(self):
            raise OSError(28, "No space left on device")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", write_text)


def _is_the_index(path) -> bool:
    return path.parent.name == "spec" and path.name.startswith("index.json")


@pytest.mark.asyncio
async def test_reindex_broadcasts_after_the_index_is_written(app, auth_headers, tmp_path):
    """1.1 (D5). An open tab could not learn that a rebuild happened."""
    from unittest.mock import AsyncMock, patch

    _write(tmp_path, "spec/spec.json")
    await app.post(
        f"{BASE}/documents",
        json={"path": "spec/spec.json", "title": "Only", "kind": "capability"},
        headers=auth_headers,
    )
    seen = []

    async def broadcast(project_id, event, payload):
        seen.append((event, payload, (tmp_path / "spec" / "index.json").exists()))

    with patch("hub.api.v1.spec.sse_manager.broadcast", AsyncMock(side_effect=broadcast)):
        response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert seen == [("spec_updated", {"path": None}, True)]


@pytest.mark.asyncio
async def test_an_index_that_cannot_be_written_still_rebuilds_the_requirements(
    app, auth_headers, run_headers, tmp_path, monkeypatch
):
    """1.12 (D6, F434). The existing SHALL -- a failure to write the index does not abandon the
    requirement index -- held only for a missing home. A full disk gave a 500 and rolled it back.

    The change on disk is a reworded requirement: one added by hand has no identity the Hub minted,
    and reindexing from a file does not mint one."""
    from sqlalchemy import select

    from hub.db.models import SpecRequirement

    path = "spec/changes/f434/spec.json"
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "F434"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        AGENT, json={"path": path, "document": _full_document()}, headers=run_headers
    )
    assert saved.status_code == 200, saved.text
    assert (await app.post(f"{BASE}/spec/reindex", headers=auth_headers)).status_code == 200
    index = tmp_path / "spec" / "index.json"
    before = index.read_bytes()

    async def alpha_digest():
        async with async_session_factory() as session:
            return (
                await session.execute(
                    select(SpecRequirement.digest).where(SpecRequirement.key == "alpha")
                )
            ).scalar_one()

    digest_before = await alpha_digest()
    target = tmp_path / path
    content = target.read_text(encoding="utf-8")
    payload = spec_documents.parse_stored(content)
    payload["requirements"][0]["statement"] = "It responds within 100ms"
    target.write_text(
        spec_documents.serialize(payload, spec_documents.parse_hub(content)), encoding="utf-8"
    )

    _failing_write_text(monkeypatch, _is_the_index)
    response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["documents"][path]["reworded"] == ["FR-1"]
    assert body["index"]["written"] is None
    last = body["index"]["diagnostics"][-1]
    assert last["code"] == "index_write_failed"
    assert "No space left on device" in last["actual"]
    assert body["corpus"]["rerendered"] == []
    assert index.read_bytes() == before
    assert not (tmp_path / "spec" / "index.json.tmp").exists()
    # Committed: a fresh session reads the reworded requirement.
    assert await alpha_digest() != digest_before


@pytest.mark.asyncio
async def test_a_document_that_cannot_be_rewritten_is_skipped_not_fatal(
    app, auth_headers, tmp_path, monkeypatch
):
    """1.13 (D6, F434). One document's write fails; the other is re-rendered and its digest kept
    true, and the failed one's digest does not advance."""
    from sqlalchemy import select

    from hub import spec_lifecycle
    from hub.db.models import SpecDocument

    await _three_filed(app, auth_headers, tmp_path)
    _make_hub_block_stale(tmp_path, "spec/home.json")
    _make_hub_block_stale(tmp_path, "spec/area.json")

    async def digests():
        async with async_session_factory() as session:
            rows = (await session.execute(select(SpecDocument))).scalars().all()
            return {row.path: row.content_digest for row in rows}

    before = await digests()
    _failing_write_text(monkeypatch, lambda p: p.name == "area.json")
    response = await app.post(f"{BASE}/spec/reindex", headers=auth_headers)

    assert response.status_code == 200, response.text
    corpus = response.json()["corpus"]
    (skipped,) = corpus["skipped"]
    assert skipped["path"] == "spec/area.json"
    assert skipped["reason"] == "write_failed"
    assert "No space left on device" in skipped["message"]
    assert corpus["rerendered"] == ["spec/home.json"]
    after = await digests()
    assert after["spec/area.json"] == before["spec/area.json"]
    home_text = (tmp_path / "spec" / "home.json").read_text(encoding="utf-8")
    assert after["spec/home.json"] == spec_lifecycle.digest(home_text)


@pytest.mark.asyncio
async def test_an_arrangement_whose_index_cannot_be_written_says_so(
    app, auth_headers, tmp_path, monkeypatch
):
    """1.14 (D6, F434). A sentence, not a bare 500; nothing placed, nothing re-rendered."""
    await _three_filed(app, auth_headers, tmp_path)
    files = {
        p: p.read_bytes() for p in (tmp_path / "spec").glob("*.json") if p.name != "index.json"
    }
    index_before = (tmp_path / "spec" / "index.json").read_bytes()

    _failing_write_text(monkeypatch, _is_the_index)
    response = await app.post(
        f"{BASE}/spec/documents/arrange",
        json={"path": "spec/area.json", "parent": "spec/home.json"},
        headers=auth_headers,
    )

    assert response.status_code == 500, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "index_write_failed"
    assert "No space left on device" in detail["message"]
    assert (tmp_path / "spec" / "index.json").read_bytes() == index_before
    assert {p: p.read_bytes() for p in files} == files


def test_the_hub_writes_documents_and_the_index_with_lf_line_endings(tmp_path):
    """F524. `Path.write_text` in text mode writes `\r\n` on Windows, so every document and index
    the Hub wrote into a project was CRLF there: a whole-file change in a repository that does not
    normalise line endings. The bytes on disk are the bytes rendered."""
    from hub.project_workspace import ProjectWorkspace
    from hub.spec_manifest import Manifest, ManifestDocument

    workspace = ProjectWorkspace(project_id="proj-test", root=tmp_path, path_key="test:proj-test")
    spec_documents.write_document(workspace, "spec/a.json", '{\n  "title": "a"\n}\n')
    manifest = Manifest(
        version=1,
        home="spec/a.json",
        documents=(
            ManifestDocument(
                path="spec/a.json",
                title="A",
                kind="capability",
                status="current",
                parent=None,
                order=10,
            ),
        ),
    )
    spec_documents.write_index(workspace, manifest)

    assert b"\r\n" not in (tmp_path / "spec" / "a.json").read_bytes()
    assert b"\r\n" not in (tmp_path / "spec" / "index.json").read_bytes()
