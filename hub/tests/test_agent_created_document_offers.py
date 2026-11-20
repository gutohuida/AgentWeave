"""A document an agent creates in a conversation is offered to it
(`every-spec-entry-point-leads-into-the-journey`, ESEPL-4: FR-6 to FR-10, Hub half).

The create answer carries the journey's first step; `GET .../spec-documents` lists, as `offers`,
the change documents created by runs of that conversation that it has not answered or opened;
`POST .../spec-documents/answer` records `open` or `not_now`.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Run, SpecDocument

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
CREATE = "/api/v1/agent-actions/spec/documents/create"


async def _conversation_with_run(name: str) -> tuple:
    """A conversation and the credential of a run that belongs to it."""
    token = f"aw_run_offer-{name}"
    async with async_session_factory() as session:
        session.add(Conversation(id=f"conv-{name}", project_id=P, agent=f"agent-{name}"))
        await session.flush()
        session.add(
            Run(
                id=f"run-{name}",
                project_id=P,
                agent=f"agent-{name}",
                conversation_id=f"conv-{name}",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return f"conv-{name}", {"Authorization": f"Bearer {token}"}


async def _offers(app, auth_headers, conversation_id: str) -> dict:
    read = await app.get(
        f"{BASE}/conversations/{conversation_id}/spec-documents", headers=auth_headers
    )
    assert read.status_code == 200, read.text
    return read.json()


async def _answer(app, auth_headers, conversation_id: str, path: str, answer: str):
    return await app.post(
        f"{BASE}/conversations/{conversation_id}/spec-documents/answer",
        json={"path": path, "answer": answer},
        headers=auth_headers,
    )


async def _row(path: str) -> tuple:
    async with async_session_factory() as session:
        row = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == path)))
            .scalars()
            .one()
        )
        return (row.phase, row.step, row.size, row.content_digest, row.title)


@pytest.mark.asyncio
async def test_create_answer_has_step(app, auth_headers):
    from hub import spec_journey

    _, headers = await _conversation_with_run("a")
    change = await app.post(CREATE, json={}, headers=headers)
    assert change.status_code == 201, change.text
    body = change.json()
    assert body["step"] == "intake"
    assert "[step: intake]" in body["instructions"]
    assert body["instructions"] == spec_journey.duty("intake", spec_journey.BUILT_IN)
    assert body["journey"][0] == "intake"

    roadmap = await app.post(CREATE, json={"kind": "roadmap"}, headers=headers)
    assert roadmap.status_code == 201, roadmap.text
    assert "step" not in roadmap.json() and "instructions" not in roadmap.json()


@pytest.mark.asyncio
async def test_notice_shown_for_agent_created_change_spec(app, auth_headers):
    conversation, headers = await _conversation_with_run("b")
    assert (await _offers(app, auth_headers, conversation))["offers"] == []
    path = (await app.post(CREATE, json={"title": "Offered"}, headers=headers)).json()["path"]

    body = await _offers(app, auth_headers, conversation)
    assert body["attached"] is None
    assert [offer["path"] for offer in body["offers"]] == [path]
    assert body["offers"][0]["step"] == "intake"

    # An open document that is a different one does not stop the offer.
    other = (
        await app.post(f"{BASE}/project/documents", json={"title": "Other"}, headers=auth_headers)
    ).json()["path"]
    put = await app.put(
        f"{BASE}/conversations/{conversation}/spec-document",
        json={"path": other},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text
    body = await _offers(app, auth_headers, conversation)
    assert body["attached"]["path"] == other
    assert [offer["path"] for offer in body["offers"]] == [path]

    # Open makes it the conversation's document and removes the notice.
    opened = await _answer(app, auth_headers, conversation, path, "open")
    assert opened.status_code == 200, opened.text
    assert opened.json()["attached"]["path"] == path
    assert opened.json()["offers"] == []
    assert (await _offers(app, auth_headers, conversation))["attached"]["path"] == path


@pytest.mark.asyncio
async def test_not_now_hides_and_changes_nothing(app, auth_headers):
    conversation, headers = await _conversation_with_run("c")
    path = (await app.post(CREATE, json={}, headers=headers)).json()["path"]
    before = await _row(path)

    declined = await _answer(app, auth_headers, conversation, path, "not_now")
    assert declined.status_code == 200, declined.text
    for _reload in range(2):
        body = await _offers(app, auth_headers, conversation)
        assert body["offers"] == []
        assert body["attached"] is None
    assert await _row(path) == before


@pytest.mark.asyncio
async def test_no_notice_for_non_journey_or_open_document(app, auth_headers):
    roadmap_conv, roadmap_headers = await _conversation_with_run("d")
    await app.post(CREATE, json={"kind": "roadmap"}, headers=roadmap_headers)
    assert (await _offers(app, auth_headers, roadmap_conv))["offers"] == []

    open_conv, open_headers = await _conversation_with_run("e")
    opened = (await app.post(CREATE, json={}, headers=open_headers)).json()["path"]
    # Explore: the document is the conversation's own before anything is offered.
    put = await app.put(
        f"{BASE}/conversations/{open_conv}/spec-document",
        json={"path": opened},
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text
    assert (await _offers(app, auth_headers, open_conv))["offers"] == []

    third_conv, third_headers = await _conversation_with_run("f")
    third = (await app.post(CREATE, json={}, headers=third_headers)).json()["path"]
    assert [o["path"] for o in (await _offers(app, auth_headers, third_conv))["offers"]] == [third]
    # Another conversation's creation is not offered here.
    assert (await _offers(app, auth_headers, open_conv))["offers"] == []


@pytest.mark.asyncio
async def test_answering_an_unknown_document_is_404(app, auth_headers):
    conversation, _ = await _conversation_with_run("g")
    response = await _answer(
        app, auth_headers, conversation, "spec/changes/nothing/spec.json", "open"
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "unknown_document"
