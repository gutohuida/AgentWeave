"""A finished change is folded into its capability, then archived.

`spec/changes/a-finished-change-is-folded-into-its-capability`: the Hub drafts the capability's new
content from the change's requirements, one operator request folds it in through the merge and
archives the change, archiving an approved change is refused until its tasks are done and it was
folded somewhere (or the operator says it changes no capability), and a capability's content changes
only through a merge.
"""

import pytest
from sqlalchemy import select, update

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, SpecDocumentEvent, SpecDocumentMerge, Task
from hub.spec_payload import KEY_RE, SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
CAP = "spec/capabilities/widgets/spec.html"
CAP2 = "spec/capabilities/gadgets/spec.html"
CHANGE = "spec/changes/widgets-glow/spec.html"


def _change(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Widgets glow",
        "scope": {"in_scope": ["widgets"], "non_goals": ["gadgets"]},
        "requirements": [
            {
                "key": "glow",
                "statement": "A widget MUST glow when hovered.",
                "modal": "MUST",
                "rationale": "visible",
            },
            {"key": "dim", "statement": "A widget SHOULD dim when idle.", "modal": "SHOULD"},
        ],
        "acceptance_criteria": [
            {
                "key": "glow-c",
                "requirement": "glow",
                "given": "a widget",
                "when": "hovered",
                "then": "it glows",
            },
            {
                "key": "glow-d",
                "requirement": "glow",
                "given": "a widget",
                "when": "unhovered",
                "then": "it stops",
            },
            {
                "key": "dim-c",
                "requirement": "dim",
                "given": "a widget",
                "when": "idle",
                "then": "it dims",
            },
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["glow", "dim"]}],
        "delivery": {"mode": "none"},
    }
    payload.update(overrides)
    return payload


def _capability(title="Widgets", requirements=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "capability",
        "title": title,
        "requirements": requirements
        or [{"key": "widgets-exist", "statement": "A widget MUST exist.", "modal": "MUST"}],
    }


async def _create_capability(app, auth_headers, path=CAP, payload=None):
    created = await app.post(
        f"{BASE}/documents",
        json={"path": path, "title": "Widgets", "kind": "capability"},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    merged = await app.post(
        f"{BASE}/documents/{path}/merge",
        json={"payload": payload or _capability(), "from_changes": []},
        headers=auth_headers,
    )
    assert merged.status_code == 200, merged.text


async def _approved_change(app, auth_headers, path=CHANGE, payload=None):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": "Widgets glow"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    written = await app.put(
        f"{BASE}/documents/{path}/content",
        json={"document": payload or _change()},
        headers=auth_headers,
    )
    assert written.status_code == 200, written.text
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": path}, headers=auth_headers
    )
    await app.post(f"{BASE}/documents/propose", params={"path": path}, headers=auth_headers)
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": path, "to": "approved"},
        json={},
        headers=auth_headers,
    )
    assert approved.json()["phase"] == "approved", approved.text


async def _finish_tasks(path=CHANGE, status="approved"):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        await session.execute(
            update(Task).where(Task.spec_document_id == document.id).values(status=status)
        )
        await session.commit()


async def _state(path=CHANGE):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        merges = (
            (
                await session.execute(
                    select(SpecDocumentMerge).where(
                        SpecDocumentMerge.change_document_id == document.id
                    )
                )
            )
            .scalars()
            .all()
        )
        return document.phase, len(merges)


async def _capability_payload(app, auth_headers, path=CAP):
    from hub.spec_payload import extract_payload

    response = await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)
    assert response.status_code == 200, response.text
    return extract_payload(response.json()["content"])


async def _digest(path=CAP):
    async with async_session_factory() as session:
        return (
            await session.execute(
                select(SpecDocument.content_digest).where(SpecDocument.path == path)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_the_draft_appends_prefixed_requirements_and_reports_a_collision(
    app, auth_headers, tmp_path
):
    await _create_capability(
        app,
        auth_headers,
        payload=_capability(
            requirements=[
                {"key": "widgets-exist", "statement": "A widget MUST exist.", "modal": "MUST"},
                {"key": "widgets-glow-dim", "statement": "Already here.", "modal": "MUST"},
            ]
        ),
    )
    await _approved_change(app, auth_headers)
    before = await _digest()

    response = await app.get(
        f"{BASE}/documents/{CHANGE}/fold-draft", params={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    draft = response.json()
    assert [(r["from"], r["key"]) for r in draft["requirements"]] == [
        ("glow", "widgets-glow-glow"),
        ("dim", "widgets-glow-dim"),
    ]
    assert draft["requirements"][0]["statement"] == "A widget MUST glow when hovered."
    assert draft["collisions"] == ["widgets-glow-dim"]
    keys = [r["key"] for r in draft["payload"]["requirements"]]
    assert keys == ["widgets-exist", "widgets-glow-dim", "widgets-glow-glow"]
    # A colliding requirement is left out, and so is its criterion: it would otherwise attach to the
    # capability's unrelated requirement of that key.
    criteria = {c["key"]: c["requirement"] for c in draft["payload"]["acceptance_criteria"]}
    assert criteria == {
        "widgets-glow-glow-c": "widgets-glow-glow",
        "widgets-glow-glow-d": "widgets-glow-glow",
    }
    # The existing requirement's text is not overwritten by the colliding draft entry.
    existing = [r for r in draft["payload"]["requirements"] if r["key"] == "widgets-glow-dim"]
    assert existing[0]["statement"] == "Already here."
    assert await _digest() == before, "a draft writes nothing"


@pytest.mark.asyncio
async def test_a_fold_writes_edits_and_replacements_merges_once_and_archives(
    app, auth_headers, tmp_path
):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    await _finish_tasks()

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold",
        json={
            "into": CAP,
            "requirements": [
                {"key": "glow", "statement": "A widget MUST glow while hovered."},
                {"key": "dim", "replaces": "widgets-exist"},
            ],
            "note": "folded by the test",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["phase"] == "archived" and body["archived"] is True and body["merged"] == 1
    capability = await _capability_payload(app, auth_headers)
    statements = {r["key"]: r["statement"] for r in capability["requirements"]}
    assert statements == {
        "widgets-exist": "A widget SHOULD dim when idle.",
        "widgets-glow-glow": "A widget MUST glow while hovered.",
    }
    criteria = {c["key"]: c["requirement"] for c in capability["acceptance_criteria"]}
    assert criteria["widgets-glow-dim-c"] == "widgets-exist"
    assert criteria["widgets-glow-glow-c"] == "widgets-glow-glow"
    assert await _state() == ("archived", 1)
    async with async_session_factory() as session:
        merged_events = (
            (
                await session.execute(
                    select(SpecDocumentEvent).where(SpecDocumentEvent.kind == "merged")
                )
            )
            .scalars()
            .all()
        )
    assert [e.detail.get("note") for e in merged_events if e.detail.get("change_document_id")] == [
        "folded by the test"
    ]


@pytest.mark.asyncio
async def test_the_folded_change_s_file_states_it_is_archived(app, auth_headers, tmp_path):
    """The file's status is a copy for its reader; a fold that archives rewrites it as the phase
    route does, or the document reads `approved` on disk while the Hub has it archived."""
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    await _finish_tasks()

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    content = (tmp_path / CHANGE).read_text(encoding="utf-8")
    assert '<meta name="aw-spec-status" content="archived">' in content


@pytest.mark.asyncio
async def test_a_change_touching_two_capabilities_is_folded_twice_archiving_on_the_second(
    app, auth_headers, tmp_path
):
    await _create_capability(app, auth_headers)
    await _create_capability(app, auth_headers, path=CAP2, payload=_capability(title="Gadgets"))
    await _approved_change(app, auth_headers)
    await _finish_tasks()

    first = await app.post(
        f"{BASE}/documents/{CHANGE}/fold",
        json={"into": CAP, "requirements": [{"key": "glow"}], "archive": False},
        headers=auth_headers,
    )
    assert first.status_code == 200, first.text
    assert first.json()["phase"] == "approved"
    second = await app.post(
        f"{BASE}/documents/{CHANGE}/fold",
        json={"into": CAP2, "requirements": [{"key": "dim"}]},
        headers=auth_headers,
    )
    assert second.status_code == 200, second.text
    assert await _state() == ("archived", 2)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case, body, code",
    [
        ("task_open", {"into": CAP}, "fold_tasks_open"),
        ("unknown", {"into": CAP, "requirements": [{"key": "nope"}]}, "fold_unknown_requirement"),
        (
            "collision",
            {"into": CAP, "requirements": [{"key": "glow", "as_key": "widgets-exist"}]},
            "fold_key_collision",
        ),
        (
            "replaces",
            {"into": CAP, "requirements": [{"key": "glow", "replaces": "ghost"}]},
            "fold_replaces_unknown",
        ),
        ("target", {"into": "spec/changes/other/spec.html"}, "fold_target_not_capability"),
        (
            "bad_key",
            {"into": CAP, "requirements": [{"key": "glow", "as_key": "Bad Key"}]},
            "fold_key_invalid",
        ),
    ],
)
async def test_a_refused_fold_writes_nothing(app, auth_headers, tmp_path, case, body, code):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    if case == "target":
        await _approved_change(app, auth_headers, path="spec/changes/other/spec.html")
    if case != "task_open":
        await _finish_tasks()
    before = await _digest()

    response = await app.post(f"{BASE}/documents/{CHANGE}/fold", json=body, headers=auth_headers)

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == code
    assert await _digest() == before
    assert await _state() == ("approved", 0)


@pytest.mark.asyncio
async def test_a_change_that_is_not_approved_is_not_folded(app, auth_headers, tmp_path):
    await _create_capability(app, auth_headers)
    await app.post(f"{BASE}/documents", json={"path": CHANGE, "title": "W"}, headers=auth_headers)
    await app.put(
        f"{BASE}/documents/{CHANGE}/content", json={"document": _change()}, headers=auth_headers
    )

    response = await app.post(
        f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "fold_change_not_approved"


async def _archive(app, auth_headers, body=None):
    return await app.post(
        f"{BASE}/documents/phase",
        params={"path": CHANGE, "to": "archived"},
        json=body or {},
        headers=auth_headers,
    )


@pytest.mark.asyncio
async def test_archiving_a_change_with_an_open_task_is_refused_naming_it(
    app, auth_headers, tmp_path
):
    await _approved_change(app, auth_headers)

    response = await _archive(app, auth_headers, {"no_capability_change": True, "reason": "none"})

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "archive_tasks_open"
    assert "task-" in detail["message"]
    assert (await _state())[0] == "approved"


@pytest.mark.asyncio
async def test_archiving_an_unfolded_change_is_refused_until_the_operator_says_why(
    app, auth_headers, tmp_path
):
    await _approved_change(app, auth_headers)
    await _finish_tasks(status="rejected")

    plain = await _archive(app, auth_headers)
    no_reason = await _archive(app, auth_headers, {"no_capability_change": True, "reason": "  "})
    stated = await _archive(
        app, auth_headers, {"no_capability_change": True, "reason": "it retired a finding"}
    )

    assert plain.status_code == 409 and plain.json()["detail"]["code"] == "archive_not_folded"
    assert no_reason.status_code == 409
    assert no_reason.json()["detail"]["code"] == "archive_not_folded"
    assert stated.status_code == 200, stated.text
    assert stated.json()["phase"] == "archived"


@pytest.mark.asyncio
async def test_a_folded_change_archives_through_the_phase_route(app, auth_headers, tmp_path):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)
    await _finish_tasks()
    folded = await app.post(
        f"{BASE}/documents/{CHANGE}/fold",
        json={"into": CAP, "archive": False},
        headers=auth_headers,
    )
    assert folded.status_code == 200, folded.text

    response = await _archive(app, auth_headers)

    assert response.status_code == 200, response.text
    assert await _state() == ("archived", 1)


@pytest.mark.asyncio
async def test_a_capability_is_written_only_through_a_merge(app, auth_headers, tmp_path):
    await _create_capability(app, auth_headers)
    edited = _capability(
        requirements=[
            {
                "key": "widgets-exist",
                "statement": "A widget MUST exist and be counted.",
                "modal": "MUST",
            },
        ]
    )

    put = await app.put(
        f"{BASE}/documents/{CAP}/content", json={"document": edited}, headers=auth_headers
    )
    merge = await app.post(
        f"{BASE}/documents/{CAP}/merge",
        json={"payload": edited, "from_changes": [], "note": "wording"},
        headers=auth_headers,
    )

    assert put.status_code == 409, put.text
    assert put.json()["detail"]["code"] == "capability_written_through_merge"
    assert "/merge" in put.json()["detail"]["message"]
    assert merge.status_code == 200, merge.text
    capability = await _capability_payload(app, auth_headers)
    assert capability["requirements"][0]["statement"] == "A widget MUST exist and be counted."
    async with async_session_factory() as session:
        edits = (
            (
                await session.execute(
                    select(SpecDocumentEvent).where(SpecDocumentEvent.kind == "merged")
                )
            )
            .scalars()
            .all()
        )
    assert [e.detail for e in edits if e.detail.get("edit")][-1]["note"] == "wording"


@pytest.mark.asyncio
async def test_fold_state_reads_tasks_open_then_ready_then_folded(app, auth_headers, tmp_path):
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers)

    async def fold_state():
        response = await app.get(f"{BASE}/spec", params={"path": CHANGE}, headers=auth_headers)
        assert response.status_code == 200, response.text
        return response.json()["fold_state"]

    open_state = await fold_state()
    await _finish_tasks()
    ready = await fold_state()
    await app.post(f"{BASE}/documents/{CHANGE}/fold", json={"into": CAP}, headers=auth_headers)
    folded = await fold_state()

    assert open_state["state"] == "tasks_open" and len(open_state["open_tasks"]) == 1
    assert ready == {"state": "ready", "open_tasks": [], "capabilities": []}
    assert folded["state"] == "folded" and folded["capabilities"] == [CAP]


@pytest.mark.asyncio
async def test_a_long_change_name_is_trimmed_to_a_valid_key(app, auth_headers, tmp_path):
    long_path = "spec/changes/" + "a-very-long-change-name-" * 3 + "end/spec.html"
    await _create_capability(app, auth_headers)
    await _approved_change(app, auth_headers, path=long_path)

    response = await app.get(
        f"{BASE}/documents/{long_path}/fold-draft", params={"into": CAP}, headers=auth_headers
    )

    assert response.status_code == 200, response.text
    for entry in response.json()["requirements"]:
        assert len(entry["key"]) <= 64 and KEY_RE.match(entry["key"]), entry["key"]
        assert entry["key"].endswith("-" + entry["from"])
