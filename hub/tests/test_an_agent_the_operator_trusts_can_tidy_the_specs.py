"""The Hub's half of `an-agent-the-operator-trusts-can-tidy-the-specs` (task `hub-core`).

The spec-admin switch on the agent (FR-1), the superseded and held marks (FR-9, FR-11), the
superseded filter and the operator's batch archive (FR-10), the tidy record and its review list
(FR-6), and the operator's acts staying the operator's (FR-12). The agent's tidy tool is task
`agent-tools`; acts are recorded here through `spec_lifecycle` directly, as that tool will.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from hub import spec_lifecycle
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument, SpecDocumentEvent

from .test_a_finished_change_is_folded_into_its_capability import (
    _approved_change,
    _change,
    _finish_tasks,
)

BASE = "/api/v1/projects/proj-test/project"
AGENTS = "/api/v1/projects/proj-test/agents"
TIDIER = "tidier"
RUN = "run-tidier"


def _path(name):
    return f"spec/changes/{name}/spec.json"


@pytest.fixture
async def tidier():
    """An agent and a running run of it, with the run's credential."""
    token = "aw_run_tidier-secret"
    async with async_session_factory() as session:
        session.add(Agent(id="ag-tidier", project_id="proj-test", name=TIDIER))
        session.add(
            Run(
                id=RUN,
                project_id="proj-test",
                agent=TIDIER,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


AGENT_ACTOR = spec_lifecycle.Actor(kind="agent", name=TIDIER, run_id=RUN)


async def _document(path):
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()


async def _supersede(path, *, reason="covered elsewhere", successor=None):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        spec_lifecycle.mark_superseded(
            document, actor=AGENT_ACTOR, reason=reason, successor=successor
        )
        await session.commit()


async def _clear(path):
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        spec_lifecycle.clear_superseded(document)
        await session.commit()


async def _listed(app, auth_headers, **params):
    response = await app.get(f"{BASE}/documents", params=params, headers=auth_headers)
    assert response.status_code == 200, response.text
    return {d["path"]: d for d in response.json()["documents"]}


async def _change_named(app, auth_headers, name):
    path = _path(name)
    await _approved_change(
        app, auth_headers, path=path, payload=_change(title=name.replace("-", " ").capitalize())
    )
    return path


# ------------------------------------------------------------------ FR-1 the switch


@pytest.mark.asyncio
async def test_the_switch_reads_off_and_only_the_operator_changes_it(app, auth_headers, tidier):
    listed = await app.get(AGENTS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert all(row["can_admin_specs"] is False for row in listed.json())

    # The agent's own credential cannot turn its switch on, nor anyone else's.
    refused = await app.patch(f"{AGENTS}/{TIDIER}", json={"can_admin_specs": True}, headers=tidier)
    assert refused.status_code == 401, refused.text

    turned = await app.patch(
        f"{AGENTS}/{TIDIER}", json={"can_admin_specs": True}, headers=auth_headers
    )
    assert turned.status_code == 200, turned.text
    assert turned.json()["can_admin_specs"] is True
    listed = await app.get(AGENTS, headers=auth_headers)
    row = next(r for r in listed.json() if r["name"] == TIDIER)
    assert row["can_admin_specs"] is True, "the roster reads back its own default"

    # Switched on, it still cannot turn itself off.
    refused = await app.patch(f"{AGENTS}/{TIDIER}", json={"can_admin_specs": False}, headers=tidier)
    assert refused.status_code == 401, refused.text
    async with async_session_factory() as session:
        agent = (await session.execute(select(Agent).where(Agent.name == TIDIER))).scalar_one()
        assert agent.can_admin_specs is True

    bad = await app.patch(
        f"{AGENTS}/{TIDIER}", json={"can_admin_specs": "yes"}, headers=auth_headers
    )
    assert bad.status_code == 400, bad.text


@pytest.mark.asyncio
async def test_a_new_agent_reads_the_switch_off(app, auth_headers):
    async with async_session_factory() as session:
        session.add(Agent(id="ag-fresh", project_id="proj-test", name="fresh"))
        await session.commit()
    listed = await app.get(AGENTS, headers=auth_headers)
    assert next(r for r in listed.json() if r["name"] == "fresh")["can_admin_specs"] is False


# ------------------------------------------------------------------ FR-9 superseded


@pytest.mark.asyncio
async def test_a_superseded_document_is_not_built_and_reads_as_before_once_cleared(
    app, auth_headers
):
    path = await _change_named(app, auth_headers, "mark-me")
    before = (await _listed(app, auth_headers))[path]
    page_before = (
        await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)
    ).json()
    assert before["superseded"] is None and page_before["superseded"] is None

    await _supersede(path, reason="the widgets cover it", successor="spec/capabilities/w/spec.json")

    marked = (await _listed(app, auth_headers))[path]
    assert marked["phase"] == "approved"
    mark = marked["superseded"]
    assert (mark["by"], mark["reason"], mark["successor"]) == (
        TIDIER,
        "the widgets cover it",
        "spec/capabilities/w/spec.json",
    )
    assert mark["at"]
    page = (await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)).json()
    assert page["superseded"] == mark
    assert page["content"] == page_before["content"], "the mark leaves the content alone"

    for route in ("build", "approve-and-build"):
        refused = await app.post(
            f"{BASE}/documents/{route}", params={"path": path}, json={}, headers=auth_headers
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"]["code"] == "superseded", refused.text

    await _clear(path)

    after = (await _listed(app, auth_headers))[path]
    strip = lambda view: {k: v for k, v in view.items() if k != "updated_at"}  # noqa: E731
    assert strip(after) == strip(before)
    page_after = (await app.get(f"{BASE}/spec", params={"path": path}, headers=auth_headers)).json()
    assert page_after == page_before
    built = await app.post(
        f"{BASE}/documents/build", params={"path": path}, json={}, headers=auth_headers
    )
    assert built.status_code == 200, built.text


# ------------------------------------------------------------------ FR-10 filter and batch archive


@pytest.mark.asyncio
async def test_the_operator_filters_superseded_and_archives_a_selection(app, auth_headers, tidier):
    marked = []
    for n in range(5):
        path = await _change_named(app, auth_headers, f"old-idea-{n}")
        await _finish_tasks(path)
        await _supersede(path, reason=f"idea {n} lives on in widgets")
        marked.append(path)
    plain = await _change_named(app, auth_headers, "still-live")

    filtered = await _listed(app, auth_headers, superseded="true")
    assert sorted(filtered) == sorted(marked)
    assert all(view["superseded"]["reason"] for view in filtered.values())
    assert plain in await _listed(app, auth_headers)

    # An agent cannot archive anything, switch or no switch.
    refused = await app.post(
        f"{BASE}/documents/archive-batch", json={"paths": marked[:1]}, headers=tidier
    )
    assert refused.status_code == 401, refused.text

    chosen = marked[:3]
    archived = await app.post(
        f"{BASE}/documents/archive-batch",
        json={"paths": [*chosen, plain, "spec/changes/nowhere/spec.json"]},
        headers=auth_headers,
    )
    assert archived.status_code == 200, archived.text
    body = archived.json()
    assert body["archived"] == chosen
    refused_by_path = {r["path"]: r for r in body["refused"]}
    # Not superseded and folded nowhere: the archive's own close-out guard, as on the phase route.
    assert refused_by_path[plain]["code"] == "archive_tasks_open"
    assert refused_by_path["spec/changes/nowhere/spec.json"]["code"] == "http_404"

    after = await _listed(app, auth_headers)
    assert all(after[p]["phase"] == "archived" for p in chosen)
    for p in marked[3:]:
        assert after[p]["phase"] == "approved" and after[p]["superseded"] is not None
    assert after[plain]["phase"] == "approved"
    assert sorted(await _listed(app, auth_headers, superseded="true")) == sorted(marked)


# ------------------------------------------------------------------ FR-11 hold


@pytest.mark.asyncio
async def test_the_operator_holds_and_releases_a_document(app, auth_headers, tidier):
    path = await _change_named(app, auth_headers, "held-change")
    q = f"{BASE}/documents/{path}/hold"

    assert (await app.post(q, json={"note": "x"}, headers=tidier)).status_code == 401

    held = await app.post(q, json={"note": "the operator keeps this"}, headers=auth_headers)
    assert held.status_code == 200, held.text
    assert held.json()["held"]["note"] == "the operator keeps this"
    assert held.json()["held"]["at"]
    assert (await _listed(app, auth_headers))[path]["held"]["note"] == "the operator keeps this"

    assert (await app.delete(q, headers=tidier)).status_code == 401
    released = await app.delete(q, headers=auth_headers)
    assert released.status_code == 200, released.text
    assert released.json()["held"] is None
    # DELETE .../hold released the hold; it did not delete the document.
    assert path in await _listed(app, auth_headers)

    again = await app.delete(q, headers=auth_headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "not_held"

    document = await _document(path)
    async with async_session_factory() as session:
        holds = (
            (
                await session.execute(
                    select(SpecDocumentEvent.detail).where(
                        SpecDocumentEvent.document_id == document.id,
                        SpecDocumentEvent.kind == spec_lifecycle.HOLD_EVENT,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert [h["held"] for h in holds] == [True, False]


@pytest.mark.asyncio
async def test_only_the_operator_holds_releases_or_reviews_in_spec_lifecycle(app, auth_headers):
    """The rule held at the function as well as at the route: no agent actor reaches a hold."""
    path = await _change_named(app, auth_headers, "guarded")
    async with async_session_factory() as session:
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
        for call in (
            spec_lifecycle.hold(session, document, actor=AGENT_ACTOR, note="mine"),
            spec_lifecycle.release(session, document, actor=AGENT_ACTOR),
            spec_lifecycle.mark_tidy_reviewed(session, "proj-test", actor=AGENT_ACTOR),
        ):
            with pytest.raises(spec_lifecycle.MarkError) as refused:
                await call
            assert refused.value.code == "operators_act"
        with pytest.raises(spec_lifecycle.MarkError):
            await spec_lifecycle.record_tidy_act(
                session,
                document,
                actor=spec_lifecycle.Actor(kind="agent", name=TIDIER),
                act="supersede",
                reason="no run",
            )
        assert document.held_at is None


# ------------------------------------------------------------------ FR-6 the tidy record

BURST = datetime(2026, 11, 9, 1, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_five_tidy_acts_are_listed_and_reviewed_and_stay_in_history(
    app, auth_headers, tidier
):
    first = await _change_named(app, auth_headers, "tidy-one")
    second = await _change_named(app, auth_headers, "tidy-two")
    code_wins = {"requirement": "glow", "before": "old", "after": "new", "cited": "glow.py"}
    async with async_session_factory() as session:
        documents = {
            d.path: d
            for d in (await session.execute(select(SpecDocument))).scalars()
            if d.path in (first, second)
        }
        for n, (path, act) in enumerate(
            (
                (first, "supersede"),
                (first, "clear_superseded"),
                (second, "set_slice"),
                (second, "edit_capability"),
                (second, "supersede"),
            )
        ):
            event = await spec_lifecycle.record_tidy_act(
                session,
                documents[path],
                actor=AGENT_ACTOR,
                act=act,
                reason=f"reason {n}",
                code_wins=code_wins if act == "edit_capability" else None,
            )
            # A burst inside one 15.625 ms clock tick, as an agent folding a backlog makes: every
            # act at the same instant, so only insertion order can put them oldest first.
            event.created_at = BURST
            # One act per request, as the tool makes them: each its own commit.
            await session.commit()

    for headers in (tidier,):
        assert (await app.get(f"{BASE}/tidy-acts", headers=headers)).status_code == 401
        marked = await app.post(f"{BASE}/tidy-acts/reviewed", json={"all": True}, headers=headers)
        assert marked.status_code == 401

    listed = await app.get(f"{BASE}/tidy-acts", params={"reviewed": "false"}, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    acts = listed.json()
    assert [a["reason"] for a in acts] == [f"reason {n}" for n in range(5)]
    for act in acts:
        assert act["agent"] == TIDIER and act["run_id"] == RUN and act["at"] and act["id"]
        assert act["path"] in (first, second) and act["act"]
    assert [a["code_wins"] for a in acts] == [None, None, None, code_wins, None]

    for body in ({}, {"ids": [acts[0]["id"]], "all": True}):
        bad = await app.post(f"{BASE}/tidy-acts/reviewed", json=body, headers=auth_headers)
        assert bad.status_code == 422, bad.text
    unknown = await app.post(
        f"{BASE}/tidy-acts/reviewed", json={"ids": ["spev-nope"]}, headers=auth_headers
    )
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "unknown_tidy_act"

    one = await app.post(
        f"{BASE}/tidy-acts/reviewed", json={"ids": [acts[2]["id"]]}, headers=auth_headers
    )
    assert one.status_code == 200, one.text
    assert one.json()["marked"] == [acts[2]["id"]]
    assert [a["id"] for a in one.json()["unreviewed"]] == [
        a["id"] for i, a in enumerate(acts) if i != 2
    ]

    rest = await app.post(f"{BASE}/tidy-acts/reviewed", json={"all": True}, headers=auth_headers)
    assert rest.status_code == 200, rest.text
    assert len(rest.json()["marked"]) == 4
    empty = await app.get(f"{BASE}/tidy-acts", params={"reviewed": "false"}, headers=auth_headers)
    assert empty.json() == []
    reviewed = await app.get(f"{BASE}/tidy-acts", params={"reviewed": "true"}, headers=auth_headers)
    assert [a["id"] for a in reviewed.json()] == [a["id"] for a in acts]

    async with async_session_factory() as session:
        kinds = (
            (
                await session.execute(
                    select(SpecDocumentEvent.kind).where(
                        SpecDocumentEvent.kind.in_(("tidy", "tidy_reviewed"))
                    )
                )
            )
            .scalars()
            .all()
        )
    assert kinds.count("tidy") == 5
    # One review of the single act, then one per document for the rest.
    assert kinds.count("tidy_reviewed") == 3


# ------------------------------------------------------------------ FR-12 the operator's acts


@pytest.mark.asyncio
async def test_a_switched_on_agent_reaches_none_of_the_operators_routes(app, auth_headers, tidier):
    await app.patch(f"{AGENTS}/{TIDIER}", json={"can_admin_specs": True}, headers=auth_headers)
    path = await _change_named(app, auth_headers, "operators-only")
    before = (await _listed(app, auth_headers))[path]

    attempts = (
        ("POST", f"{BASE}/documents/phase", {"path": path, "to": "archived"}, {"reason": "x"}),
        ("POST", f"{BASE}/documents/phase", {"path": path, "to": "exploring"}, {}),
        ("POST", f"{BASE}/documents/close-exploration", {"path": path}, None),
        ("POST", f"{BASE}/documents/archive-batch", None, {"paths": [path]}),
        ("POST", f"{BASE}/documents/{path}/hold", None, {"note": "agent"}),
        ("DELETE", f"{BASE}/documents/{path}/hold", None, None),
        ("POST", f"{BASE}/tidy-acts/reviewed", None, {"all": True}),
        ("PATCH", f"{AGENTS}/{TIDIER}", None, {"can_admin_specs": False}),
    )
    for method, url, params, body in attempts:
        response = await app.request(method, url, params=params, json=body, headers=tidier)
        assert response.status_code == 401, (method, url, response.text)

    after = (await _listed(app, auth_headers))[path]
    assert after == before
