"""After approval the authors and the lead propose; the operator decides
(`amendments-main-watch-and-the-next-slice`, task `amendments`).

Named by acceptance criterion: `-k next_build` (task-waits-for-next-build), `-k who`
(only-author-and-lead), `-k decide` (accept-stale-decline). The lead's proposal joining a running
build is the acceptance drive's `lead_amendment`.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import InboundQueueEntry, Run
from hub.spec_documents import parse_stored

from .test_a_lead_hands_out_the_work import (
    AGENT_DOCS,
    BASE,
    PATH,
    _approved,
    _build,
    _rows,
    _run_headers,
    _scheduling,
    _tasks,
)
from .test_review_turn import _roster

AMEND = f"{AGENT_DOCS}/amend"
AMENDMENTS = f"{BASE}/documents/{PATH}/amendments"


async def _version(app, auth_headers):
    return (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()[
        "content_version"
    ]


async def _author():
    """The agent that wrote the document before approval (`_approved`'s author), on a new turn."""
    return await _run_headers(f"run-author-{len(await _rows(Run))}", "author")


def _criterion(key="c-extra", requirement="alpha"):
    return {
        "path": PATH,
        "op": "add_criterion",
        "reason": "the edge case is not covered",
        "how_to_check": "pytest -k edge",
        "criterion": key,
        "requirement": requirement,
        "change": {"given": "an edge", "when": "it runs", "then": "it holds"},
    }


async def _listed(app, auth_headers):
    return {
        row["id"]: row
        for row in (await app.get(AMENDMENTS, headers=auth_headers)).json()["amendments"]
    }


@pytest.mark.asyncio
async def test_an_accepted_task_waits_for_the_next_build(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev")
    await _approved(app, auth_headers)
    proposed = await app.post(
        AMEND,
        json={
            "path": PATH,
            "op": "add_task",
            "reason": "gamma is missing",
            "how_to_check": "pytest -k gamma",
            "task": {"key": "t3", "title": "Gamma", "requirements": ["alpha"], "builder": "dev"},
        },
        headers=await _author(),
    )
    assert proposed.status_code == 201, proposed.text

    with _scheduling():
        accepted = await app.post(
            f"{AMENDMENTS}/{proposed.json()['id']}/accept", headers=auth_headers
        )
    assert accepted.status_code == 200, accepted.text
    t3 = (await _tasks())["t3"]
    assert (t3.status, t3.build_id, t3.level) == ("pending", None, None)
    assert accepted.json()["task_created"] == t3.id

    outcome = await _build(app, auth_headers, driver="hand", level="gated")
    t3 = (await _tasks())["t3"]
    assert (t3.build_id, t3.level) == (outcome["build"]["id"], "gated")
    assert t3.builder == "dev"


@pytest.mark.asyncio
async def test_who_may_propose_the_authors_and_the_lead(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "lead", "dev", "qa")
    await _approved(app, auth_headers)
    await _build(app, auth_headers, driver="lead", lead="lead", builders=["dev"])
    before = await _version(app, auth_headers)

    by_author = await app.post(AMEND, json=_criterion("c-a"), headers=await _author())
    by_lead = await app.post(
        AMEND, json=_criterion("c-l"), headers=await _run_headers("run-lead-who", "lead")
    )
    by_qa = await app.post(
        AMEND, json=_criterion("c-q"), headers=await _run_headers("run-qa-who", "qa")
    )

    assert by_author.status_code == 201, by_author.text
    assert by_lead.status_code == 201, by_lead.text
    assert by_author.json()["state"] == by_lead.json()["state"] == "proposed"
    assert await _version(app, auth_headers) == before, "a proposal changes nothing"
    assert by_qa.status_code == 403, by_qa.text
    message = by_qa.json()["detail"]["message"]
    assert "author" in message and "lead" in message
    listed = await _listed(app, auth_headers)
    assert {row["author"] for row in listed.values()} == {"author", "lead"}


@pytest.mark.asyncio
async def test_decide_accept_stale_and_decline(app, auth_headers, bind_runner, tmp_path):
    await _roster(app, auth_headers, bind_runner, "lead", "dev")
    await _approved(app, auth_headers)
    await _build(app, auth_headers, driver="lead", lead="lead", builders=["dev"])
    lead = await _run_headers("run-lead-decide", "lead")
    first = (await app.post(AMEND, json=_criterion("c-same"), headers=await _author())).json()
    second = (await app.post(AMEND, json=_criterion("c-same"), headers=lead)).json()
    third = (await app.post(AMEND, json=_criterion("c-other"), headers=lead)).json()

    with _scheduling():
        accepted = await app.post(f"{AMENDMENTS}/{first['id']}/accept", headers=auth_headers)
        assert accepted.status_code == 200, accepted.text
        after_first = await _version(app, auth_headers)
        stale = await app.post(f"{AMENDMENTS}/{second['id']}/accept", headers=auth_headers)
        no_reason = await app.post(
            f"{AMENDMENTS}/{third['id']}/decline", json={"reason": ""}, headers=auth_headers
        )
        declined = await app.post(
            f"{AMENDMENTS}/{third['id']}/decline",
            json={"reason": "covered by c-alpha already"},
            headers=auth_headers,
        )

    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "amendment_stale"
    assert "c-same" in stale.json()["detail"]["message"]
    assert await _version(app, auth_headers) == after_first, "the stale one changed nothing"
    assert no_reason.status_code == 422, no_reason.text
    assert declined.status_code == 200, declined.text

    listed = await _listed(app, auth_headers)
    assert listed[first["id"]]["state"] == "accepted"
    assert listed[first["id"]]["decided_by"] == "operator"
    assert listed[first["id"]]["reviewed"] is True
    assert listed[second["id"]]["state"] == "stale"
    assert (listed[third["id"]]["state"], listed[third["id"]]["decided_reason"]) == (
        "declined",
        "covered by c-alpha already",
    )
    spec = parse_stored((tmp_path / PATH).read_text(encoding="utf-8"))
    assert [c["key"] for c in spec["acceptance_criteria"]].count("c-same") == 1

    async with async_session_factory() as db:
        from sqlalchemy import select

        entries = list((await db.execute(select(InboundQueueEntry))).scalars())
    told = {
        (e.agent, i["id"]) for e in entries for i in (first, second, third) if i["id"] in e.content
    }
    assert told == {("author", first["id"]), ("lead", second["id"]), ("lead", third["id"])}
    assert any("accepted" in e.content for e in entries if first["id"] in e.content)
    assert any(
        "covered by c-alpha already" in e.content for e in entries if third["id"] in e.content
    )


@pytest.mark.asyncio
async def test_a_proposal_is_not_marked_reviewed(app, auth_headers, bind_runner):
    await _roster(app, auth_headers, bind_runner, "dev")
    await _approved(app, auth_headers)
    proposed = (await app.post(AMEND, json=_criterion(), headers=await _author())).json()

    whole = await app.post(f"{AMENDMENTS}/review", json={}, headers=auth_headers)
    named = await app.post(
        f"{AMENDMENTS}/review", json={"ids": [proposed["id"]]}, headers=auth_headers
    )

    assert whole.status_code == 200 and whole.json()["marked"] == []
    assert named.status_code == 409, named.text
    assert (await _listed(app, auth_headers))[proposed["id"]]["state"] == "proposed"
