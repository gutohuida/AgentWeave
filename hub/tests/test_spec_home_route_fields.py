"""`spec-home-shows-what-is-being-built-what-was-built-and-how-it-relates` (FR-3, FR-7, FR-9, task
`route-fields`): the build list and the document list gain the fields the Spec home reads.

Rows are seeded by hand in the order the routes are meant to return them, so a reversed route fails
the ordering assertions rather than passing on a fixture it never emits.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Build, SpecDocument, SpecDocumentMerge

P = "proj-test"
BASE = f"/api/v1/projects/{P}/project"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
ROADMAP = "spec/roadmaps/big/spec.json"
CAP_A = "spec/capabilities/alpha/spec.json"
CAP_B = "spec/capabilities/beta/spec.json"
CAP_C = "spec/capabilities/gamma/spec.json"


def _write(tmp_path, path, payload):
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")


def _doc(key, kind="change-spec", phase="approved", title=None, path=None):
    return SpecDocument(
        id=f"spdoc-{key}",
        project_id=P,
        path=path or f"spec/changes/{key}/spec.json",
        title=title or f"Title {key}",
        kind=kind,
        phase=phase,
    )


def _build(key, hours_ago, state="finished", doc=None, **fields):
    created = NOW - timedelta(hours=hours_ago + 1)
    if state == "finished":
        fields.setdefault("stopped_at", NOW - timedelta(hours=hours_ago))
    return Build(
        id=f"build-{key}",
        project_id=P,
        document_id=f"spdoc-{doc or key}",
        state=state,
        driver="flow",
        level="reviewed",
        created_at=created,
        **fields,
    )


# ------------------------------------------------------------------ FR-3: ac-recent's route part


@pytest.mark.asyncio
async def test_a_build_row_names_its_document_finish_roadmap_and_capabilities(
    app, auth_headers, tmp_path
):
    _write(tmp_path, ROADMAP, {"title": "Big roadmap", "slices": [{"key": "s1", "title": "One"}]})
    _write(
        tmp_path,
        "spec/changes/linked/spec.json",
        {
            "roadmap": {"document": ROADMAP, "slice": "s1"},
            "capabilities": {"changes": [CAP_A, CAP_B], "creates": []},
        },
    )
    _write(tmp_path, "spec/changes/plain/spec.json", {"title": "plain"})
    async with async_session_factory() as db:
        db.add_all(
            [
                _doc("linked"),
                _doc("plain"),
                _doc("roadmap", kind="roadmap", title="Big roadmap", path=ROADMAP),
                _doc("alpha", kind="capability", phase="current", title="Alpha", path=CAP_A),
                _doc("beta", kind="capability", phase="current", title="Beta", path=CAP_B),
            ]
        )
        await db.flush()
        db.add_all(
            [
                _build("linked", 1),
                _build("plain", 2, state="running"),
            ]
        )
        await db.commit()

    response = await app.get(f"{BASE}/builds", headers=auth_headers)
    assert response.status_code == 200, response.text
    rows = {row["id"]: row for row in response.json()["builds"]}

    linked = rows["build-linked"]
    assert linked["document_path"] == "spec/changes/linked/spec.json"
    assert linked["finished_at"] == (NOW - timedelta(hours=1)).isoformat()
    assert linked["roadmap"] == {
        "path": ROADMAP,
        "title": "Big roadmap",
        "slice": {"key": "s1", "title": "One"},
    }
    assert linked["capabilities"] == [
        {"path": CAP_A, "title": "Alpha"},
        {"path": CAP_B, "title": "Beta"},
    ]

    plain = rows["build-plain"]
    assert plain["document_path"] == "spec/changes/plain/spec.json"
    assert plain["finished_at"] is None  # still running
    assert plain["roadmap"] is None
    assert plain["capabilities"] == []


@pytest.mark.asyncio
async def test_an_archived_document_keeps_its_build_row(app, auth_headers, tmp_path):
    async with async_session_factory() as db:
        db.add(_doc("old", phase="archived"))
        await db.flush()
        db.add(_build("old", 3))
        await db.commit()

    rows = (await app.get(f"{BASE}/builds", headers=auth_headers)).json()["builds"]

    assert [r["document_path"] for r in rows] == ["spec/changes/old/spec.json"]


# ------------------------------------------------------------------ FR-7: ac-touched's route part


@pytest.mark.asyncio
async def test_a_capability_row_lists_every_folded_change_newest_first(app, auth_headers, tmp_path):
    async with async_session_factory() as db:
        db.add_all(
            [
                _doc("cap", kind="capability", phase="current", title="Gamma", path=CAP_C),
                _doc("old", phase="archived", title="Old change"),
                _doc("mid", phase="approved", title="Mid change"),
                _doc("sup", phase="approved", title="Superseded change"),
                _doc("other", kind="capability", phase="current", path=CAP_A, title="Alpha"),
            ]
        )
        await db.flush()
        for key, days_ago, cap in (
            ("old", 5, "cap"),
            ("mid", 1, "cap"),
            ("sup", 3, "cap"),
            ("old", 2, "other"),  # folded into another capability too: not this one's
        ):
            db.add(
                SpecDocumentMerge(
                    id=f"merge-{key}-{cap}",
                    project_id=P,
                    capability_document_id=f"spdoc-{cap}",
                    change_document_id=f"spdoc-{key}",
                    actor_kind="operator",
                    actor="op",
                    created_at=NOW - timedelta(days=days_ago),
                )
            )
        await db.commit()

    rows = (await app.get(f"{BASE}/documents", headers=auth_headers)).json()["documents"]
    by_path = {row["path"]: row for row in rows}

    assert by_path[CAP_C]["folded_changes"] == [
        {
            "path": "spec/changes/mid/spec.json",
            "title": "Mid change",
            "folded_at": (NOW - timedelta(days=1)).isoformat(),
        },
        {
            "path": "spec/changes/sup/spec.json",
            "title": "Superseded change",
            "folded_at": (NOW - timedelta(days=3)).isoformat(),
        },
        {
            "path": "spec/changes/old/spec.json",
            "title": "Old change",
            "folded_at": (NOW - timedelta(days=5)).isoformat(),
        },
    ]
    assert [c["path"] for c in by_path[CAP_A]["folded_changes"]] == ["spec/changes/old/spec.json"]


@pytest.mark.asyncio
async def test_a_capability_with_nothing_folded_says_so_and_a_change_has_no_field(
    app, auth_headers, tmp_path
):
    async with async_session_factory() as db:
        db.add_all(
            [
                _doc("cap", kind="capability", phase="current", path=CAP_C),
                _doc("change"),
            ]
        )
        await db.commit()

    rows = (await app.get(f"{BASE}/documents", headers=auth_headers)).json()["documents"]
    by_path = {row["path"]: row for row in rows}

    assert by_path[CAP_C]["folded_changes"] == []
    assert "folded_changes" not in by_path["spec/changes/change/spec.json"]


# ------------------------------------------------------------------ FR-9: ac-additive


@pytest.mark.asyncio
async def test_every_field_the_routes_returned_before_is_still_there(app, auth_headers, tmp_path):
    async with async_session_factory() as db:
        db.add(_doc("one"))
        db.add(_doc("cap", kind="capability", phase="current", path=CAP_C))
        await db.flush()
        db.add(_build("one", 1))
        await db.commit()

    build = (await app.get(f"{BASE}/builds", headers=auth_headers)).json()["builds"][0]
    before = {
        "id": str,
        "document_id": str,
        "document_title": str,
        "state": str,
        "driver": str,
        "level": str,
        "lead": (str, type(None)),
        "loop_id": (str, type(None)),
        "loop": (dict, type(None)),
        "tasks_total": int,
        "tasks_done": int,
        "tasks_landing": int,
        "landings": list,
        "spent_usd": (float, int, type(None)),
        "stop_reason": (str, type(None)),
        "created_at": (str, type(None)),
        "stopped_at": (str, type(None)),
        "open_questions": int,
        "question": (dict, type(None)),
    }
    for field, kind in before.items():
        assert field in build, field
        assert isinstance(build[field], kind), field

    documents = (await app.get(f"{BASE}/documents", headers=auth_headers)).json()["documents"]
    capability = next(d for d in documents if d["path"] == CAP_C)
    for field in ("path", "title", "kind", "phase", "waiting_changes", "waiting_count", "roadmap"):
        assert field in capability, field
