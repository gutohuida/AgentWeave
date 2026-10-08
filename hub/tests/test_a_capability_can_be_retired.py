"""A capability can be retired (F536).

`spec/changes/a-capability-can-be-retired`: the operator moves a capability from `current` to
`archived` with a reason and, optionally, the capability that absorbed it. Its requirements are
retired and stay retired through any reindex, nothing can be merged or folded into it, the phase
event and `GET /spec` say why, and the index lists it as archived. Refused without a reason, with a
bad absorber, by an agent, and while open work links one of its requirements.
"""

import pytest
from sqlalchemy import select

from hub import spec_lifecycle
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent, SpecRequirement
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
OLD = "spec/capabilities/old/spec.html"
NEW = "spec/capabilities/new/spec.html"
CHANGE = "spec/changes/widgets-glow/spec.html"
REASON = "Describes nothing the product does any more."


def _capability(title, keys):
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability",
        "title": title,
        "requirements": [
            {"key": k, "statement": f"A widget MUST {k}.", "modal": "MUST"} for k in keys
        ],
    }


async def _create(app, auth_headers, path, title, keys):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": path, "title": title, "kind": "capability"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    merged = await app.post(
        f"{BASE}/documents/{path}/merge",
        json={"payload": _capability(title, keys), "from_changes": []},
        headers=auth_headers,
    )
    assert merged.status_code == 200, merged.text


async def _two_capabilities(app, auth_headers):
    await _create(app, auth_headers, OLD, "Old", ["a", "b"])
    await _create(app, auth_headers, NEW, "New", ["c"])


async def _retire(app, auth_headers, path=OLD, **body):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": "archived"},
        json=body,
        headers=auth_headers,
    )


async def _document(path=OLD):
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()


async def _requirement_states(path=OLD):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        rows = await session.execute(
            select(SpecRequirement.identifier, SpecRequirement.state)
            .where(SpecRequirement.document_id == document.id)
            .order_by(SpecRequirement.identifier)
        )
        return [tuple(row) for row in rows]


@pytest.mark.asyncio
async def test_retiring_archives_it_and_retires_its_requirements(app, auth_headers, tmp_path):
    await _two_capabilities(app, auth_headers)

    response = await _retire(app, auth_headers, reason=REASON, absorbed_by=NEW)

    assert response.status_code == 200, response.text
    assert response.json()["phase"] == "archived"
    assert (await _document()).phase == "archived"
    assert await _requirement_states() == [("FR-1", "retired"), ("FR-2", "retired")]
    coverage = (await app.get(f"{BASE}/spec/coverage", headers=auth_headers)).json()
    old_id = (await _document()).id
    assert [r for r in coverage["requirements"] if r["document_id"] == old_id] == []
    assert [r for r in coverage["unserved"] if r["document_id"] == old_id] == []
    # The other capability is untouched.
    assert await _requirement_states(NEW) == [("FR-1", "active")]


@pytest.mark.asyncio
async def test_the_phase_event_and_get_spec_say_why_and_what_absorbed_it(
    app, auth_headers, tmp_path
):
    await _two_capabilities(app, auth_headers)
    await _retire(app, auth_headers, reason=REASON, absorbed_by=NEW)

    async with async_session_factory() as session:
        event = (
            (
                await session.execute(
                    select(SpecDocumentEvent)
                    .where(
                        SpecDocumentEvent.document_id == (await _document()).id,
                        SpecDocumentEvent.kind == "phase",
                    )
                    .order_by(SpecDocumentEvent.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
    assert event.detail["from"] == "current"
    assert event.detail["to"] == "archived"
    assert event.detail["reason"] == REASON
    assert event.detail["absorbed_by"] == NEW

    spec = (await app.get(f"{BASE}/spec", params={"path": OLD}, headers=auth_headers)).json()
    assert spec["retired"]["reason"] == REASON
    assert spec["retired"]["absorbed_by"] == NEW
    assert spec["retired"]["at"]
    assert 'aw-spec-status" content="archived"' in spec["content"] or "archived" in spec["content"]
    current = (await app.get(f"{BASE}/spec", params={"path": NEW}, headers=auth_headers)).json()
    assert "retired" not in current


@pytest.mark.asyncio
async def test_without_an_absorber_the_event_records_none(app, auth_headers, tmp_path):
    await _two_capabilities(app, auth_headers)

    response = await _retire(app, auth_headers, reason=REASON)

    assert response.status_code == 200, response.text
    spec = (await app.get(f"{BASE}/spec", params={"path": OLD}, headers=auth_headers)).json()
    assert spec["retired"]["absorbed_by"] is None


@pytest.mark.asyncio
async def test_a_reindex_leaves_a_retired_capability_s_requirements_retired(
    app, auth_headers, tmp_path
):
    await _two_capabilities(app, auth_headers)
    await _retire(app, auth_headers, reason=REASON)

    reindexed = await app.post(f"{BASE}/spec/reindex", json={"home": NEW}, headers=auth_headers)

    assert reindexed.status_code == 200, reindexed.text
    assert await _requirement_states() == [("FR-1", "retired"), ("FR-2", "retired")]
    index = (tmp_path / "spec" / "index.json").read_text(encoding="utf-8")
    import json

    entry = next(d for d in json.loads(index)["documents"] if d["path"] == OLD)
    assert entry["status"] == "archived"


@pytest.mark.asyncio
async def test_a_merge_or_fold_into_a_retired_capability_is_refused(app, auth_headers, tmp_path):
    await _two_capabilities(app, auth_headers)
    await _retire(app, auth_headers, reason=REASON)
    before = (await _document()).content_digest

    merged = await app.post(
        f"{BASE}/documents/{OLD}/merge",
        json={"payload": _capability("Old", ["a", "b", "z"]), "from_changes": []},
        headers=auth_headers,
    )
    assert merged.status_code == 409, merged.text
    assert merged.json()["detail"]["code"] == "capability_retired"

    draft = await app.get(
        f"{BASE}/documents/{CHANGE}/fold-draft", params={"into": OLD}, headers=auth_headers
    )
    assert draft.status_code in (404, 409), draft.text
    assert (await _document()).content_digest == before
    assert await _requirement_states() == [("FR-1", "retired"), ("FR-2", "retired")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body, code",
    [
        ({}, "retire_needs_reason"),
        ({"reason": "   "}, "retire_needs_reason"),
        ({"reason": REASON, "absorbed_by": OLD}, "absorber_invalid"),
        (
            {"reason": REASON, "absorbed_by": "spec/capabilities/nowhere/spec.html"},
            "absorber_invalid",
        ),
    ],
)
async def test_a_refused_retirement_changes_nothing(app, auth_headers, tmp_path, body, code):
    await _two_capabilities(app, auth_headers)

    response = await _retire(app, auth_headers, **body)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == code
    assert (await _document()).phase == "current"
    assert await _requirement_states() == [("FR-1", "active"), ("FR-2", "active")]


@pytest.mark.asyncio
async def test_a_change_document_cannot_absorb_a_capability(app, auth_headers, tmp_path):
    await _two_capabilities(app, auth_headers)
    created = await app.post(
        f"{BASE}/documents", json={"path": CHANGE, "title": "Widgets glow"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    response = await _retire(app, auth_headers, reason=REASON, absorbed_by=CHANGE)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "absorber_invalid"


@pytest.mark.asyncio
async def test_absorbed_by_is_refused_on_any_other_move(app, auth_headers, tmp_path):
    created = await app.post(
        f"{BASE}/documents", json={"path": CHANGE, "title": "Widgets glow"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    response = await app.post(
        f"{BASE}/documents/phase",
        params={"path": CHANGE, "to": "archived"},
        json={"reason": "a mistake", "absorbed_by": NEW},
        headers=auth_headers,
    )

    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_open_work_linking_a_requirement_refuses_retirement(app, auth_headers, tmp_path):
    await _two_capabilities(app, auth_headers)
    task = await app.post(
        "/api/v1/projects/proj-test/tasks",
        json={"title": "Serve a", "requirement_ids": ["FR-1"], "spec_document": OLD},
        headers=auth_headers,
    )
    assert task.status_code in (200, 201), task.text
    task_id = task.json()["id"]

    response = await _retire(app, auth_headers, reason=REASON)

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "capability_has_open_work"
    assert task_id in detail["message"]
    assert (await _document()).phase == "current"


@pytest.mark.asyncio
async def test_an_agent_cannot_retire_a_capability(app, auth_headers, tmp_path):
    await _two_capabilities(app, auth_headers)
    from hub.project_workspace import ProjectWorkspace  # noqa: F401  (workspace type only)

    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == OLD))
        ).scalar_one()
        with pytest.raises(spec_lifecycle.PhaseError) as refused:
            await spec_lifecycle.transition(
                session,
                document,
                to_phase="archived",
                actor=spec_lifecycle.Actor(kind="agent", name="bot", run_id="run-x"),
                workspace=None,
                reason=REASON,
            )
    assert refused.value.code == "archive_is_the_operators"


@pytest.mark.asyncio
async def test_the_index_stays_valid_after_a_retirement(app, auth_headers, tmp_path):
    """Found by the acceptance drive: the manifest rule held a capability to `current`, so the
    index the retirement wrote read as invalid (`manifest_kind_status_mismatch`)."""
    await _two_capabilities(app, auth_headers)
    reindexed = await app.post(f"{BASE}/spec/reindex", json={"home": NEW}, headers=auth_headers)
    assert reindexed.status_code == 200, reindexed.text

    await _retire(app, auth_headers, reason=REASON)

    specs = (await app.get(f"{BASE}/specs", headers=auth_headers)).json()
    assert specs["manifest"]["state"] != "invalid", specs["diagnostics"]
    assert not [d for d in specs["diagnostics"] if d["code"] == "manifest_kind_status_mismatch"]


def test_adoption_keeps_a_capability_the_file_says_is_archived():
    """A corpus re-adopted from its files must not bring a retired capability back to current."""
    from hub import spec_adoption

    assert spec_adoption.phase_is_holdable("archived", "capability")
    assert spec_adoption.phase_is_holdable("current", "capability")
    assert not spec_adoption.phase_is_holdable("approved", "capability")
    assert not spec_adoption.phase_is_holdable("current", "change-spec")
