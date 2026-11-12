"""A change names the capabilities it changes (`a-change-names-the-capabilities-it-changes`,
spdoc-f214c91aac0e, task `hub`).

The link is a change's `capabilities` field; each capability lists the open changes naming it, in a
total order; a fold with no target goes where the change says; an off-link fold is recorded.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update

from hub.db.engine import async_session_factory
from hub.db.models import Project, SpecDocument, SpecDocumentEvent, SpecRequirement

from .test_a_finished_change_is_folded_into_its_capability import (
    _approved_change,
    _change,
    _create_capability,
    _finish_tasks,
)
from .test_spec_tidy import _agent, _refused, _row, _tidy

BASE = "/api/v1/projects/proj-test/project"
READ = "/api/v1/agent-actions/spec/documents"
SUBMIT = "/api/v1/agent-actions/spec/documents"
ALPHA = "spec/capabilities/alpha/spec.json"
BETA = "spec/capabilities/beta/spec.json"
GAMMA = "spec/capabilities/gamma/spec.json"
NOPE = "spec/capabilities/nope/spec.json"
C_BUILT = "spec/changes/c-built/spec.json"
C_UNBUILT = "spec/changes/c-unbuilt/spec.json"
C_EXPLORING = "spec/changes/c-exploring/spec.json"
C_FOLDED = "spec/changes/c-folded/spec.json"
C_OLD = "spec/changes/c-old/spec.json"


@pytest.fixture
async def tidier():
    """An agent whose spec-admin switch is on, and its run's credential."""
    return await _agent("tidier", "aw_run_tidier-secret", switch=True)


def _named(changes=(), creates=(), **overrides):
    payload = _change(**overrides)
    payload["capabilities"] = {
        "changes": list(changes),
        "creates": [{"title": t} for t in creates],
    }
    return payload


async def _caps(app, auth_headers, *paths):
    for path in paths:
        await _create_capability(app, auth_headers, path=path)


async def _exploring(app, auth_headers, path, payload):
    created = await app.post(
        f"{BASE}/documents", json={"path": path, "title": payload["title"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    written = await app.put(
        f"{BASE}/documents/{path}/content", json={"document": payload}, headers=auth_headers
    )
    assert written.status_code == 200, written.text
    return written.json()


async def _rows(app, auth_headers):
    response = await app.get(f"{BASE}/documents", headers=auth_headers)
    assert response.status_code == 200, response.text
    return {row["path"]: row for row in response.json()["documents"]}


async def _waiting(app, auth_headers, capability):
    return [
        (entry["path"], entry["built"])
        for entry in (await _rows(app, auth_headers))[capability]["waiting_changes"]
    ]


async def _agent_waiting(app, headers, capability):
    response = await app.get(
        READ, params={"path": capability, "include": "waiting"}, headers=headers
    )
    assert response.status_code == 200, response.text
    return [(entry["path"], entry["built"]) for entry in response.json()["waiting_changes"]]


async def _digests(path):
    async with async_session_factory() as session:
        rows = await session.execute(
            select(SpecRequirement.key, SpecRequirement.digest)
            .join(SpecDocument, SpecDocument.id == SpecRequirement.document_id)
            .where(SpecDocument.path == path, SpecRequirement.state == "active")
        )
        return sorted(rows.all())


# ------------------------------------------------------------------ FR-1, FR-2, FR-3


@pytest.mark.asyncio
async def test_a_change_names_existing_and_new_capabilities(app, auth_headers, tidier):
    await _caps(app, auth_headers, ALPHA)
    payload = _named([ALPHA], ["Beta things"])
    saved = await _exploring(app, auth_headers, C_EXPLORING, payload)
    assert "capability_unnamed" not in [w["code"] for w in saved["warnings"]]
    want = {"changes": [ALPHA], "creates": [{"title": "Beta things"}]}
    assert (await _rows(app, auth_headers))[C_EXPLORING]["capabilities"] == want
    read = await app.get(READ, params={"path": C_EXPLORING}, headers=tidier)
    assert read.json()["capabilities"] == want and read.json()["folded_into"] is None
    page = await app.get(f"{BASE}/spec", params={"path": C_EXPLORING}, headers=auth_headers)
    assert page.json()["capabilities"] == want
    # A later submission carrying it keeps it.
    again = await app.put(
        f"{BASE}/documents/{C_EXPLORING}/content",
        json={"document": {**payload, "summary": "Reworded."}},
        headers=auth_headers,
    )
    assert again.status_code == 200, again.text
    assert (await _rows(app, auth_headers))[C_EXPLORING]["capabilities"] == want


@pytest.mark.asyncio
async def test_an_agent_submission_names_a_capability(app, auth_headers, tidier):
    await _caps(app, auth_headers, ALPHA)
    created = await app.post(
        f"{BASE}/documents", json={"path": C_EXPLORING, "title": "x"}, headers=auth_headers
    )
    assert created.status_code == 201
    submitted = await app.post(
        SUBMIT, json={"path": C_EXPLORING, "document": _named([ALPHA])}, headers=tidier
    )
    assert submitted.status_code == 200, submitted.text
    assert await _waiting(app, auth_headers, ALPHA) == [(C_EXPLORING, False)]


@pytest.mark.asyncio
async def test_an_unknown_or_foreign_capability_is_refused_and_nothing_changes(
    app, auth_headers, tmp_path
):
    await _caps(app, auth_headers, ALPHA)
    await _exploring(app, auth_headers, C_EXPLORING, _named([ALPHA]))
    foreign = "spec/capabilities/theirs/spec.json"
    async with async_session_factory() as session:
        session.add(Project(id="proj-other", name="Other"))
        session.add(
            SpecDocument(
                id="spdoc-theirs",
                project_id="proj-other",
                path=foreign,
                title="Theirs",
                kind="capability",
                phase="current",
            )
        )
        await session.commit()
    before = (tmp_path / C_EXPLORING).read_bytes()
    for bad in (NOPE, foreign, C_EXPLORING):
        response = await app.put(
            f"{BASE}/documents/{C_EXPLORING}/content",
            json={"document": _named([bad])},
            headers=auth_headers,
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["code"] == "capability_unknown"
        assert bad in response.json()["detail"]["message"]
        assert (tmp_path / C_EXPLORING).read_bytes() == before
    assert (await _rows(app, auth_headers))[C_EXPLORING]["capabilities"]["changes"] == [ALPHA]


@pytest.mark.asyncio
async def test_a_change_naming_nothing_warns_on_save_and_approval_and_is_approved(
    app, auth_headers
):
    saved = await _exploring(app, auth_headers, C_BUILT, _change())
    assert "capability_unnamed" in [w["code"] for w in saved["warnings"]]
    await app.post(
        f"{BASE}/documents/close-exploration", params={"path": C_BUILT}, headers=auth_headers
    )
    from ._spec_versions import content_version

    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": C_BUILT, "to": "approved"},
        json={
            "content_version": await content_version(app, auth_headers, C_BUILT),
            "approve_anyway": True,
        },
        headers=auth_headers,
    )
    assert approved.json()["phase"] == "approved", approved.text
    assert "capability_unnamed" in [n["code"] for n in approved.json()["approval_notes"]]


# ------------------------------------------------------------------ FR-4


@pytest.mark.asyncio
async def test_an_agent_relinks_an_approved_change_and_its_approval_stands(
    app, auth_headers, tidier
):
    await _caps(app, auth_headers, ALPHA, GAMMA)
    await _approved_change(app, auth_headers, path=C_UNBUILT, payload=_named([ALPHA]))
    before = await _digests(C_UNBUILT)
    assert before
    assert await _waiting(app, auth_headers, ALPHA) == [(C_UNBUILT, False)]
    # Open tasks do not stop a relink: the link is not content.
    response = await _tidy(
        app, tidier, C_UNBUILT, "set_capabilities", "it changes gamma", changes=[GAMMA]
    )
    assert response.status_code == 200, response.text
    rows = await _rows(app, auth_headers)
    assert rows[C_UNBUILT]["capabilities"]["changes"] == [GAMMA]
    assert rows[C_UNBUILT]["phase"] == "approved"
    assert await _digests(C_UNBUILT) == before
    assert rows[ALPHA]["waiting_count"] == 0
    assert await _waiting(app, auth_headers, GAMMA) == [(C_UNBUILT, False)]
    acts = await app.get(f"{BASE}/tidy-acts", params={"reviewed": "false"}, headers=auth_headers)
    body = acts.json()
    listed = body.get("acts", body) if isinstance(body, dict) else body
    assert any(
        a["act"] == "set_capabilities" and a["path"] == C_UNBUILT and "gamma" in a["reason"]
        for a in listed
    )
    # The operator's route does the same.
    put = await app.put(
        f"{BASE}/documents/{C_UNBUILT}/capabilities",
        json={"changes": [ALPHA], "creates": [], "reason": "back to alpha"},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text
    assert put.json()["capabilities"]["changes"] == [ALPHA] and put.json()["phase"] == "approved"
    assert await _digests(C_UNBUILT) == before
    unknown = await app.put(
        f"{BASE}/documents/{C_UNBUILT}/capabilities",
        json={"changes": [NOPE]},
        headers=auth_headers,
    )
    assert unknown.json()["detail"]["code"] == "capability_unknown"


@pytest.mark.asyncio
async def test_a_folded_changes_link_is_fixed(app, auth_headers, tidier):
    await _caps(app, auth_headers, ALPHA, GAMMA)
    await _approved_change(app, auth_headers, path=C_FOLDED, payload=_named([ALPHA]))
    await _finish_tasks(path=C_FOLDED)
    folded = await app.post(
        f"{BASE}/documents/{C_FOLDED}/fold", json={"archive": False}, headers=auth_headers
    )
    assert folded.status_code == 200, folded.text
    assert folded.json()["folded_into"] == ALPHA
    assert folded.json()["fold_target_not_named"] is False
    put = await app.put(
        f"{BASE}/documents/{C_FOLDED}/capabilities",
        json={"changes": [GAMMA], "reason": "late"},
        headers=auth_headers,
    )
    assert put.status_code == 409 and put.json()["detail"]["code"] == "change_folded"
    _refused(
        await _tidy(app, tidier, C_FOLDED, "set_capabilities", "late", changes=[GAMMA]),
        "change_folded",
        409,
    )
    assert (await _rows(app, auth_headers))[C_FOLDED]["capabilities"]["changes"] == [ALPHA]


# ------------------------------------------------------------------ FR-5, FR-6, FR-8


@pytest.mark.asyncio
async def test_the_waiting_list_is_ordered_and_the_same_on_every_read(app, auth_headers, tidier):
    await _caps(app, auth_headers, ALPHA, BETA)
    await _approved_change(app, auth_headers, path=C_BUILT, payload=_named([ALPHA]))
    await _finish_tasks(path=C_BUILT)
    await _approved_change(app, auth_headers, path=C_UNBUILT, payload=_named([ALPHA]))
    await _exploring(app, auth_headers, C_EXPLORING, _named([ALPHA]))
    await _approved_change(app, auth_headers, path=C_FOLDED, payload=_named([ALPHA]))
    await _finish_tasks(path=C_FOLDED)
    folded = await app.post(
        f"{BASE}/documents/{C_FOLDED}/fold",
        json={"into": ALPHA, "archive": False},
        headers=auth_headers,
    )
    assert folded.status_code == 200, folded.text
    # Approval order differs from path order (c-built < c-exploring < c-folded < c-unbuilt), so
    # a list sorted by path, or reversed, fails here.
    want = [(C_BUILT, True), (C_UNBUILT, False), (C_EXPLORING, False)]
    for _ in range(2):
        assert await _waiting(app, auth_headers, ALPHA) == want
        assert await _agent_waiting(app, tidier, ALPHA) == want
        page = await app.get(f"{BASE}/spec", params={"path": ALPHA}, headers=auth_headers)
        assert [(e["path"], e["built"]) for e in page.json()["waiting_changes"]] == want
    rows = await _rows(app, auth_headers)
    assert rows[ALPHA]["waiting_count"] == 3 and rows[BETA]["waiting_count"] == 0
    assert await _agent_waiting(app, tidier, BETA) == []
    entry = rows[ALPHA]["waiting_changes"][0]
    assert entry["title"] and entry["phase"] == "approved" and entry["first_approved_at"]
    assert rows[ALPHA]["waiting_changes"][2]["first_approved_at"] is None


@pytest.mark.asyncio
async def test_tied_approval_times_fall_back_to_creation_order(app, auth_headers):
    await _caps(app, auth_headers, ALPHA)
    later_path, earlier_path = "spec/changes/zz-first/spec.json", "spec/changes/aa-second/spec.json"
    await _approved_change(app, auth_headers, path=later_path, payload=_named([ALPHA]))
    await _approved_change(app, auth_headers, path=earlier_path, payload=_named([ALPHA]))
    tie = datetime(2026, 11, 12, 9, 0, 0, tzinfo=timezone.utc)
    async with async_session_factory() as session:
        await session.execute(
            update(SpecDocument)
            .where(SpecDocument.path.in_([later_path, earlier_path]))
            .values(first_approved_at=tie)
        )
        await session.commit()
    for _ in range(3):
        assert [p for p, _ in await _waiting(app, auth_headers, ALPHA)] == [
            later_path,
            earlier_path,
        ]


@pytest.mark.asyncio
async def test_a_folded_change_says_where_before_and_after_this_slice(
    app, auth_headers, tidier, tmp_path
):
    await _caps(app, auth_headers, ALPHA, GAMMA)
    # Folded before the link existed: no `capabilities`, only the merge row the fold left.
    await _approved_change(app, auth_headers, path=C_OLD, payload=_change())
    await _finish_tasks(path=C_OLD)
    old = await app.post(
        f"{BASE}/documents/{C_OLD}/fold",
        json={"into": GAMMA, "archive": False},
        headers=auth_headers,
    )
    assert old.status_code == 200, old.text
    await _approved_change(app, auth_headers, path=C_FOLDED, payload=_named([ALPHA]))
    await _finish_tasks(path=C_FOLDED)
    await app.post(f"{BASE}/documents/{C_FOLDED}/fold", json={"into": ALPHA}, headers=auth_headers)
    rows = await _rows(app, auth_headers)
    assert rows[C_OLD]["folded_into"] == GAMMA and rows[C_FOLDED]["folded_into"] == ALPHA
    for path, into in ((C_OLD, GAMMA), (C_FOLDED, ALPHA)):
        read = await app.get(READ, params={"path": path}, headers=tidier)
        assert read.json()["folded_into"] == into
    assert rows[ALPHA]["waiting_changes"] == [] and rows[GAMMA]["waiting_changes"] == []


# ------------------------------------------------------------------ FR-7


@pytest.mark.asyncio
async def test_an_agents_fold_with_no_capability_goes_where_the_change_says(
    app, auth_headers, tidier
):
    await _caps(app, auth_headers, ALPHA, GAMMA)
    await _approved_change(app, auth_headers, path=C_BUILT, payload=_named([ALPHA]))
    await _finish_tasks(path=C_BUILT)
    response = await _tidy(app, tidier, C_BUILT, "fold", "c-built is built")
    assert response.status_code == 200, response.text
    assert response.json()["detail"]["capability"] == ALPHA
    assert response.json()["detail"]["fold_target_not_named"] is False
    assert (await _rows(app, auth_headers))[C_BUILT]["folded_into"] == ALPHA


@pytest.mark.asyncio
async def test_a_fold_with_no_capability_is_refused_when_the_link_does_not_say(
    app, auth_headers, tidier
):
    await _caps(app, auth_headers, ALPHA, GAMMA)
    await _approved_change(app, auth_headers, path=C_BUILT, payload=_named([ALPHA, GAMMA]))
    await _approved_change(app, auth_headers, path=C_UNBUILT, payload=_change())
    for path in (C_BUILT, C_UNBUILT):
        await _finish_tasks(path=path)
    _refused(await _tidy(app, tidier, C_BUILT, "fold", "fold it"), "capability_ambiguous")
    _refused(await _tidy(app, tidier, C_UNBUILT, "fold", "fold it"), "capability_unnamed")
    operator = await app.post(f"{BASE}/documents/{C_UNBUILT}/fold", json={}, headers=auth_headers)
    assert operator.json()["detail"]["code"] == "capability_unnamed"
    assert (await _row(C_BUILT)).phase == "approved"


@pytest.mark.asyncio
async def test_an_off_link_fold_succeeds_and_its_record_says_so(app, auth_headers):
    await _caps(app, auth_headers, ALPHA, BETA)
    await _approved_change(app, auth_headers, path=C_BUILT, payload=_named([ALPHA]))
    await _finish_tasks(path=C_BUILT)
    folded = await app.post(
        f"{BASE}/documents/{C_BUILT}/fold",
        json={"into": BETA, "archive": False},
        headers=auth_headers,
    )
    assert folded.status_code == 200, folded.text
    assert folded.json()["fold_target_not_named"] is True
    async with async_session_factory() as session:
        details = (
            (
                await session.execute(
                    select(SpecDocumentEvent.detail)
                    .join(SpecDocument, SpecDocument.id == SpecDocumentEvent.document_id)
                    .where(SpecDocument.path == BETA, SpecDocumentEvent.kind == "merged")
                )
            )
            .scalars()
            .all()
        )
    assert any(d.get("fold_target_not_named") is True for d in details)


@pytest.mark.asyncio
async def test_a_fold_into_the_capability_it_said_it_creates_is_on_the_link(
    app, auth_headers, tidier
):
    await _approved_change(app, auth_headers, path=C_BUILT, payload=_named([], ["Beta things"]))
    await _finish_tasks(path=C_BUILT)
    response = await _tidy(
        app,
        tidier,
        C_BUILT,
        "create_capability",
        "it creates beta",
        title="Beta things",
        fold_from=C_BUILT,
    )
    assert response.status_code == 200, response.text
    assert response.json()["detail"]["fold_target_not_named"] is False
