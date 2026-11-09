"""The agent's tidy acts (`spec_tidy`, task `agent-tools` of
`an-agent-the-operator-trusts-can-tidy-the-specs`).

Each act goes through `POST /agent-actions/spec/documents/tidy` with a run credential, the route the
`tidy_spec_document` tool calls. The order of the refusals is part of the contract: the operator's
acts (`operators_act`) whatever the switch says, then the switch (`spec_admin_off`), the reason
(`reason_required`), the hold (`document_held`) and live work (`live_work`).
"""

import hashlib
import json
import re

import pytest
from sqlalchemy import select, update

from hub import spec_tidy
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    Run,
    SpecDocument,
    SpecDocumentEvent,
    SpecDocumentMerge,
    Task,
)

from .test_a_finished_change_is_folded_into_its_capability import (
    _approved_change,
    _capability,
    _change,
    _create_capability,
    _finish_tasks,
)
from .test_a_roadmap_shows_which_of_its_slices_are_done import (
    ROADMAP,
    ROADMAP_PAYLOAD,
    _approve,
    _write,
)

BASE = "/api/v1/projects/proj-test/project"
AGENTS = "/api/v1/projects/proj-test/agents"
TIDY = "/api/v1/agent-actions/spec/documents/tidy"
CAP = "spec/capabilities/widgets/spec.json"
TWIN_CAP = "spec/capabilities/widgets-twin/spec.json"
CHANGE = "spec/changes/widgets-glow/spec.json"
TWIN = "spec/changes/widgets-glow-twin/spec.json"
OTHER = "spec/changes/other/spec.json"
TIDIER = "tidier"


def _capability_two():
    return _capability(
        requirements=[
            {"key": "widgets-exist", "statement": "A widget MUST exist.", "modal": "MUST"},
            {"key": "widgets-old", "statement": "A widget MUST be grey.", "modal": "MUST"},
        ]
    )


async def _agent(name, token, *, switch):
    async with async_session_factory() as session:
        session.add(
            Agent(id=f"ag-{name}", project_id="proj-test", name=name, can_admin_specs=switch)
        )
        session.add(
            Run(
                id=f"run-{name}",
                project_id="proj-test",
                agent=name,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def tidier():
    """An agent whose switch the operator turned on, and its running run's credential."""
    return await _agent(TIDIER, "aw_run_tidier-secret", switch=True)


@pytest.fixture
async def bystander():
    """An agent with the switch off."""
    return await _agent("bystander", "aw_run_bystander-secret", switch=False)


async def _tidy(app, headers, path, op, reason="the change is built", **fields):
    return await app.post(
        TIDY, json={"path": path, "op": op, "reason": reason, **fields}, headers=headers
    )


def _refused(response, code, status=None):
    assert response.status_code >= 400, response.text
    if status is not None:
        assert response.status_code == status, response.text
    detail = response.json()["detail"]
    assert detail["code"] == code, response.text
    assert detail["ok"] is False and detail["reason"]
    return detail["reason"]


async def _built(app, auth_headers, path=CHANGE, title="Widgets glow"):
    await _approved_change(app, auth_headers, path=path, payload=_change(title=title))
    await _finish_tasks(path=path)


async def _row(path):
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one_or_none()


async def _state(tmp_path):
    """The spec tree on disk and every document row, as one digest (ac-off)."""
    h = hashlib.sha256()
    for file in sorted((tmp_path / "spec").rglob("*")):
        if file.is_file():
            h.update(str(file.relative_to(tmp_path)).encode())
            h.update(file.read_bytes())
    async with async_session_factory() as session:
        rows = (await session.execute(select(SpecDocument).order_by(SpecDocument.path))).scalars()
        for row in rows:
            h.update(
                repr(
                    {
                        c.name: getattr(row, c.name)
                        for c in SpecDocument.__table__.columns
                        if c.name != "updated_at"
                    }
                ).encode()
            )
    return h.hexdigest()


def _stored(tmp_path, path):
    return json.loads((tmp_path / path).read_text(encoding="utf-8"))


async def _acts(app, auth_headers):
    response = await app.get(
        f"{BASE}/tidy-acts", params={"reviewed": "false"}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body.get("acts", body) if isinstance(body, dict) else body


# ------------------------------------------------------------------ FR-2 fold, as the operator's


@pytest.mark.asyncio
async def test_an_agents_fold_carries_what_the_operators_fold_carries(
    app, auth_headers, tidier, tmp_path
):
    """ac-fold: the same choices on two copies, once by the operator with archive off, once by the
    agent; the capabilities carry the same requirements and criteria, and the agent's change is
    marked superseded by its capability instead of archived."""
    for cap in (CAP, TWIN_CAP):
        await _create_capability(app, auth_headers, path=cap, payload=_capability_two())
    await _built(app, auth_headers, CHANGE)
    await _built(app, auth_headers, TWIN, title="Widgets glow twin")
    choices = {"items": [{"key": "glow"}, {"key": "dim"}], "retire": ["widgets-old"]}

    applied = await _tidy(app, tidier, CHANGE, "fold", capability=CAP, **choices)
    assert applied.status_code == 200, applied.text
    assert applied.json()["ok"] is True and applied.json()["act_id"]
    operator = await app.post(
        f"{BASE}/documents/{TWIN}/fold",
        json={
            "into": TWIN_CAP,
            "requirements": choices["items"],
            "retire": ["widgets-old"],
            "archive": False,
        },
        headers=auth_headers,
    )
    assert operator.status_code == 200, operator.text

    def shape(path):
        doc = _stored(tmp_path, path)
        return (
            sorted((r["statement"], r.get("modal")) for r in doc["requirements"]),
            sorted((c["given"], c["when"], c["then"]) for c in doc.get("acceptance_criteria", [])),
        )

    assert shape(CAP) == shape(TWIN_CAP)
    assert "widgets-old" not in [r["key"] for r in _stored(tmp_path, CAP)["requirements"]]

    change = await _row(CHANGE)
    assert change.phase == "approved", "an agent's fold never archives"
    assert change.superseded_successor == CAP and change.superseded_by == TIDIER
    assert change.superseded_reason == "the change is built"
    async with async_session_factory() as session:
        merge = (
            await session.execute(
                select(SpecDocumentMerge).where(SpecDocumentMerge.change_document_id == change.id)
            )
        ).scalar_one()
    assert (merge.actor_kind, merge.actor, merge.run_id) == ("agent", TIDIER, f"run-{TIDIER}")

    acts = await _acts(app, auth_headers)
    assert [(a["act"], a["path"], a["agent"], a["reason"]) for a in acts] == [
        ("fold", CHANGE, TIDIER, "the change is built")
    ]


@pytest.mark.asyncio
async def test_a_fresh_project_folds_the_same_way(app, auth_headers, tidier, tmp_path):
    """ac-any: nothing in the act depends on this repository's names or layout."""
    await _create_capability(
        app, auth_headers, path="spec/capabilities/anything/spec.json", payload=_capability()
    )
    await _built(app, auth_headers, "spec/changes/x/spec.json", title="X")
    applied = await _tidy(
        app,
        tidier,
        "spec/changes/x/spec.json",
        "fold",
        capability="spec/capabilities/anything/spec.json",
    )
    assert applied.status_code == 200, applied.text
    statements = [
        r["statement"]
        for r in _stored(tmp_path, "spec/capabilities/anything/spec.json")["requirements"]
    ]
    assert "A widget MUST glow when hovered." in statements


# ------------------------------------------------------------------ FR-2 create a capability


@pytest.mark.asyncio
async def test_a_new_capability_holds_the_folded_change_and_is_in_the_map(
    app, auth_headers, tidier, tmp_path
):
    """ac-new-capability, with the project's map already present: the new capability is current,
    lists the folded requirements and is filed in `spec/index.json`, under the area named."""
    await _create_capability(app, auth_headers, path=CAP, payload=_capability())
    reindexed = await app.post(f"{BASE}/spec/reindex", json={"home": CAP}, headers=auth_headers)
    assert reindexed.status_code == 200, reindexed.text
    assert (tmp_path / "spec/index.json").exists()
    await _built(app, auth_headers, OTHER, title="Other")

    applied = await _tidy(
        app, tidier, OTHER, "create_capability", title="Glowing things", fold_from=OTHER, area=CAP
    )
    assert applied.status_code == 200, applied.text
    created = applied.json()["detail"]["capability"]
    assert created.startswith("spec/capabilities/")
    row = await _row(created)
    assert row.kind == "capability" and row.phase == "current"
    statements = [r["statement"] for r in _stored(tmp_path, created)["requirements"]]
    assert "A widget MUST glow when hovered." in statements
    index = json.loads((tmp_path / "spec/index.json").read_text(encoding="utf-8"))
    entry = next(d for d in index["documents"] if d["path"] == created)
    assert entry["parent"] == CAP
    change = await _row(OTHER)
    assert change.superseded_successor == created and change.phase == "approved"


@pytest.mark.asyncio
async def test_a_create_that_cannot_fold_leaves_no_capability(app, auth_headers, tidier, tmp_path):
    await app.post(
        f"{BASE}/documents", json={"path": OTHER, "title": "Other"}, headers=auth_headers
    )
    before = await _state(tmp_path)
    refused = await _tidy(app, tidier, OTHER, "create_capability", title="Never", fold_from=OTHER)
    _refused(refused, "fold_change_not_approved")
    assert await _state(tmp_path) == before
    assert not (tmp_path / "spec/capabilities/never").exists()


# ------------------------------------------------------------------ FR-2 / FR-13 edit a capability


@pytest.mark.asyncio
async def test_a_requirement_rewritten_to_match_the_code_is_recorded_apart(
    app, auth_headers, tidier, tmp_path
):
    """ac-code-wins."""
    await _create_capability(app, auth_headers, path=CAP, payload=_capability_two())
    old, new = "A widget MUST be grey.", "A widget MUST be blue."
    applied = await _tidy(
        app,
        tidier,
        CAP,
        "edit_capability",
        reason="widget.py paints them blue",
        requirement="widgets-old",
        statement=new,
        code_wins={"cited": "widget.py"},
    )
    assert applied.status_code == 200, applied.text
    statements = [r["statement"] for r in _stored(tmp_path, CAP)["requirements"]]
    assert new in statements and old not in statements

    async with async_session_factory() as session:
        details = [
            json.dumps(e.detail)
            for e in (
                await session.execute(
                    select(SpecDocumentEvent)
                    .join(SpecDocument, SpecDocument.id == SpecDocumentEvent.document_id)
                    .where(SpecDocument.path == CAP)
                )
            ).scalars()
        ]
    assert any(old in detail for detail in details), "the old statement stays in the history"

    (act,) = await _acts(app, auth_headers)
    assert act["act"] == "edit_capability"
    assert act["code_wins"] == {
        "requirement": "widgets-old",
        "before": old,
        "after": new,
        "cited": "widget.py",
    }


@pytest.mark.asyncio
async def test_a_requirement_is_retired_and_an_edit_without_code_wins_is_not_marked(
    app, auth_headers, tidier, tmp_path
):
    await _create_capability(app, auth_headers, path=CAP, payload=_capability_two())
    retired = await _tidy(
        app, tidier, CAP, "edit_capability", requirement="widgets-old", retire=True
    )
    assert retired.status_code == 200, retired.text
    assert [r["key"] for r in _stored(tmp_path, CAP)["requirements"]] == ["widgets-exist"]
    (act,) = await _acts(app, auth_headers)
    assert act["code_wins"] is None

    both = await _tidy(
        app, tidier, CAP, "edit_capability", requirement="widgets-exist", retire=True, statement="x"
    )
    _refused(both, "field_required", 422)
    on_a_change = await _tidy(
        app,
        tidier,
        CAP.replace("capabilities/widgets", "changes/none"),
        "edit_capability",
        requirement="a",
        statement="b",
    )
    _refused(on_a_change, "document_not_found", 404)


# ------------------------------------------------------------------ FR-9 supersede and clear


@pytest.mark.asyncio
async def test_a_mark_reads_with_who_why_and_successor_and_clears_to_as_before(
    app, auth_headers, tidier
):
    """ac-mark-clear (the read; Build's refusal is `hub-core`'s test)."""
    await _create_capability(app, auth_headers, path=CAP, payload=_capability())
    await _built(app, auth_headers, CHANGE)

    async def read():
        listed = await app.get(f"{BASE}/documents", headers=auth_headers)
        row = next(d for d in listed.json()["documents"] if d["path"] == CHANGE)
        page = await app.get(f"{BASE}/spec", params={"path": CHANGE}, headers=auth_headers)
        return {k: v for k, v in row.items() if k != "updated_at"}, page.json()

    before = await read()
    marked = await _tidy(
        app, tidier, CHANGE, "supersede", reason="widgets covers it", successor=CAP
    )
    assert marked.status_code == 200, marked.text
    row, _ = await read()
    assert row["superseded"]["by"] == TIDIER
    assert row["superseded"]["reason"] == "widgets covers it"
    assert row["superseded"]["successor"] == CAP
    assert row["phase"] == "approved"

    cleared = await _tidy(app, tidier, CHANGE, "clear_superseded", reason="marked by mistake")
    assert cleared.status_code == 200, cleared.text
    assert await read() == before

    again = await _tidy(app, tidier, CHANGE, "clear_superseded", reason="twice")
    _refused(again, "not_superseded")
    itself = await _tidy(app, tidier, CHANGE, "supersede", successor=CHANGE)
    _refused(itself, "successor_is_itself", 422)


# ------------------------------------------------------------------ FR-2 set or correct a slice


@pytest.mark.asyncio
async def test_a_slice_is_set_and_corrected(app, auth_headers, tidier, tmp_path):
    """ac-slice: the roadmap shows the slice specified by the change; a wrong slice is corrected
    (the operator's link is set-once; the agent's act is recorded and listed instead)."""
    await _write(app, auth_headers, ROADMAP, "The roadmap", ROADMAP_PAYLOAD, kind="roadmap")
    assert (await _approve(app, auth_headers, ROADMAP)).status_code == 200
    await _built(app, auth_headers, CHANGE)

    applied = await _tidy(app, tidier, CHANGE, "set_slice", roadmap=ROADMAP, slice="second")
    assert applied.status_code == 200, applied.text
    corrected = await _tidy(app, tidier, CHANGE, "set_slice", roadmap=ROADMAP, slice="first")
    assert corrected.status_code == 200, corrected.text
    assert _stored(tmp_path, CHANGE)["roadmap"] == {"document": ROADMAP, "slice": "first"}

    page = (await app.get(f"{BASE}/spec", params={"path": ROADMAP}, headers=auth_headers)).json()
    first = re.search(r'<li id="slice-first".*?</li>', page["content"], flags=re.S).group(0)
    assert CHANGE in first
    second = re.search(r'<li id="slice-second".*?</li>', page["content"], flags=re.S).group(0)
    assert CHANGE not in second

    unknown = await _tidy(app, tidier, CHANGE, "set_slice", roadmap=ROADMAP, slice="nope")
    _refused(unknown, "roadmap_slice_unknown", 422)


# ------------------------------------------------------------------ FR-4 the switch off


@pytest.mark.asyncio
async def test_an_agent_with_the_switch_off_is_refused_every_act(
    app, auth_headers, bystander, tmp_path
):
    """ac-off: every act refused `spec_admin_off`, naming the switch and the operator; nothing
    on disk or in a document row changes."""
    await _create_capability(app, auth_headers, path=CAP, payload=_capability_two())
    await _built(app, auth_headers, CHANGE)
    before = await _state(tmp_path)
    attempts = [
        (CHANGE, "fold", {"capability": CAP}),
        (CHANGE, "create_capability", {"title": "New", "fold_from": CHANGE}),
        (CAP, "edit_capability", {"requirement": "widgets-old", "statement": "x MUST y."}),
        (CHANGE, "supersede", {"successor": CAP}),
        (CHANGE, "clear_superseded", {}),
        (CHANGE, "set_slice", {"roadmap": ROADMAP, "slice": "first"}),
    ]
    for path, op, fields in attempts:
        reason = _refused(await _tidy(app, bystander, path, op, **fields), "spec_admin_off", 403)
        assert "switch" in reason and "operator" in reason, (op, reason)
    assert await _state(tmp_path) == before
    assert await _acts(app, auth_headers) == []


@pytest.mark.asyncio
async def test_the_switch_is_read_on_every_call(app, auth_headers, tidier, tmp_path):
    """Turned off by the operator, the next act is refused: nothing caches the switch."""
    await _create_capability(app, auth_headers, path=CAP, payload=_capability())
    await _built(app, auth_headers, CHANGE)
    off = await app.patch(
        f"{AGENTS}/{TIDIER}", json={"can_admin_specs": False}, headers=auth_headers
    )
    assert off.status_code == 200, off.text
    _refused(await _tidy(app, tidier, CHANGE, "supersede"), "spec_admin_off", 403)


@pytest.mark.asyncio
async def test_a_capability_write_by_a_switched_off_agent_stays_refused(
    app, auth_headers, bystander
):
    """The guard relaxed in `spec_service.save_document` admits only a switched-on agent's run."""
    from hub import spec_lifecycle, spec_service
    from hub.project_workspace import resolve_project_workspace

    await _create_capability(app, auth_headers, path=CAP, payload=_capability())
    async with async_session_factory() as session:
        workspace = await resolve_project_workspace(session, "proj-test")
        document = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == CAP))
        ).scalar_one()
        for actor in (
            spec_lifecycle.Actor(kind="agent", name="bystander", run_id="run-bystander"),
            spec_lifecycle.Actor(kind="agent", name=TIDIER, run_id=None),
        ):
            with pytest.raises(spec_service.SaveRefusedError) as refused:
                await spec_service.merge_document(
                    session, workspace, document, [], _capability(title="Hijacked"), actor=actor
                )
            assert refused.value.code == "capability_write_is_the_operators"


# ------------------------------------------------------------------ FR-7 the reason


@pytest.mark.asyncio
async def test_a_fold_without_a_reason_is_refused(app, auth_headers, tidier, tmp_path):
    """ac-reason."""
    await _create_capability(app, auth_headers, path=CAP, payload=_capability())
    await _built(app, auth_headers, CHANGE)
    before = await _state(tmp_path)
    for reason in ("", "   "):
        refused = await _tidy(app, tidier, CHANGE, "fold", reason=reason, capability=CAP)
        assert "reason" in _refused(refused, "reason_required", 422)
    assert await _state(tmp_path) == before


# ------------------------------------------------------------------ FR-5 live work


@pytest.mark.asyncio
async def test_a_change_with_an_open_task_is_left_alone(app, auth_headers, tidier, tmp_path):
    """ac-live: refused `live_work`, naming the open task."""
    await _write(app, auth_headers, ROADMAP, "The roadmap", ROADMAP_PAYLOAD, kind="roadmap")
    assert (await _approve(app, auth_headers, ROADMAP)).status_code == 200
    await _create_capability(app, auth_headers, path=CAP, payload=_capability())
    await _approved_change(app, auth_headers, path=CHANGE, payload=_change())
    change = await _row(CHANGE)
    async with async_session_factory() as session:
        await session.execute(
            update(Task).where(Task.spec_document_id == change.id).values(status="in_progress")
        )
        await session.commit()
        task_id = (
            (await session.execute(select(Task.id).where(Task.spec_document_id == change.id)))
            .scalars()
            .first()
        )
    before = await _state(tmp_path)
    for op, fields in (
        ("fold", {"capability": CAP}),
        ("supersede", {"successor": CAP}),
        ("set_slice", {"roadmap": ROADMAP, "slice": "first"}),
    ):
        reason = _refused(await _tidy(app, tidier, CHANGE, op, **fields), "live_work", 409)
        assert task_id in reason, (op, reason)
    assert await _state(tmp_path) == before


# ------------------------------------------------------------------ FR-11 held


@pytest.mark.asyncio
async def test_a_held_document_is_refused_until_released(app, auth_headers, tidier, tmp_path):
    """ac-held."""
    await _create_capability(app, auth_headers, path=CAP, payload=_capability_two())
    await _built(app, auth_headers, CHANGE)
    for path in (CHANGE, CAP):
        held = await app.post(
            f"{BASE}/documents/{path}/hold", json={"note": "mine"}, headers=auth_headers
        )
        assert held.status_code == 200, held.text
    before = await _state(tmp_path)
    for path, op, fields in (
        (CHANGE, "fold", {"capability": CAP}),
        (CHANGE, "supersede", {"successor": CAP}),
        (CAP, "edit_capability", {"requirement": "widgets-old", "statement": "x MUST y."}),
    ):
        reason = _refused(await _tidy(app, tidier, path, op, **fields), "document_held", 409)
        assert "mine" in reason and "operator" in reason
    assert await _state(tmp_path) == before

    # Folding a released change into a capability still held is refused too: the fold writes it.
    released = await app.delete(f"{BASE}/documents/{CHANGE}/hold", headers=auth_headers)
    assert released.status_code == 200, released.text
    _refused(await _tidy(app, tidier, CHANGE, "fold", capability=CAP), "document_held")
    released = await app.delete(f"{BASE}/documents/{CAP}/hold", headers=auth_headers)
    assert released.status_code == 200, released.text
    folded = await _tidy(app, tidier, CHANGE, "fold", capability=CAP)
    assert folded.status_code == 200, folded.text


# ------------------------------------------------------------------ FR-12 the operator's acts


@pytest.mark.asyncio
async def test_the_operators_acts_are_refused_whatever_the_switch_says(
    app, auth_headers, tidier, bystander, tmp_path
):
    """ac-no-operator-acts: each is refused `operators_act`, naming it the operator's, even with
    the switch on (and the switch off answers the same, since the switch is not what refuses)."""
    created = await app.post(
        f"{BASE}/documents", json={"path": OTHER, "title": "Proposed"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    before = await _state(tmp_path)
    for headers in (tidier, bystander):
        for op in spec_tidy.OPERATOR_OPS:
            reason = _refused(await _tidy(app, headers, OTHER, op), "operators_act", 403)
            assert "operator" in reason, (op, reason)
    assert await _state(tmp_path) == before
    assert (await _row(OTHER)).phase == "exploring"


@pytest.mark.asyncio
async def test_an_unknown_op_is_named(app, tidier):
    response = await _tidy(app, tidier, OTHER, "delete")
    _refused(response, "unknown_op", 422)


@pytest.mark.asyncio
async def test_the_route_needs_a_run_credential(app):
    response = await app.post(TIDY, json={"path": CHANGE, "op": "fold"})
    assert response.status_code == 401, response.text


# ------------------------------------------------------------------ D5 the tool's listing


def test_the_tool_is_described_only_with_the_switch_on():
    from hub.api.v1.agents import SWITCHED_TOOLS, _tool_surface_lines
    from hub.mcp_server import SWITCHED_TOOLS as SERVED_SWITCHED

    assert set(SWITCHED_TOOLS) == set(SERVED_SWITCHED) == {"tidy_spec_document"}
    assert SERVED_SWITCHED["tidy_spec_document"] == "AW_CAN_ADMIN_SPECS"
    assert "tidy_spec_document" not in "\n".join(_tool_surface_lines())
    assert "tidy_spec_document(" in "\n".join(_tool_surface_lines(can_admin_specs=True))


def test_the_server_withholds_the_tool_unless_the_run_says_the_switch_is_on(monkeypatch):
    import asyncio

    from hub import mcp_server

    monkeypatch.delenv("AW_CAN_ADMIN_SPECS", raising=False)
    calls = []
    monkeypatch.setattr(
        mcp_server.mcp.local_provider, "remove_tool", lambda name, *a: calls.append(name)
    )
    callable_tools = dict(mcp_server._CALLABLE_TOOLS)
    monkeypatch.setattr(mcp_server, "_CALLABLE_TOOLS", callable_tools)
    mcp_server._withhold_switched_tools()
    assert calls == ["tidy_spec_document"] and "tidy_spec_document" not in callable_tools

    calls.clear()
    callable_tools["tidy_spec_document"] = mcp_server.tidy_spec_document
    monkeypatch.setenv("AW_CAN_ADMIN_SPECS", "1")
    mcp_server._withhold_switched_tools()
    assert calls == [] and "tidy_spec_document" in callable_tools
    assert "tidy_spec_document" in {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}


def test_the_run_variable_is_forwarded_to_a_codex_tool_server():
    from hub.runner_commands import CODEX_MCP_ENV_NAMES

    assert "AW_CAN_ADMIN_SPECS" in CODEX_MCP_ENV_NAMES
