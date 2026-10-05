"""`a-spec-is-written-one-slice-at-a-time` (C1a): a roadmap of slices, a slice document linked to it,
and approval that can start the next slice.

Grows with the change's task groups (`openspec/changes/a-spec-is-written-one-slice-at-a-time/
tasks.md`): 2.x the payload's shape, 3.x completeness, 4.x agent creation and guidance, 5.x the
approval that drafts the next slice, 6.x rendering.
"""

import json

import pytest
from sqlalchemy import select

from hub import spec_completeness, turn_scheduler
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, InboundQueueEntry, Run, SpecDocument, Task
from hub.spec_payload import (
    SCHEMA_VERSION,
    PayloadError,
    payload_to_dict,
    validate_payload,
)

ROADMAP_PATH = "spec/changes/the-plan/spec.html"


def _slices():
    return [
        {"key": "s1", "title": "Slice one", "intent": "First outcome", "done": "S1 is built"},
        {
            "key": "s2",
            "title": "Slice two",
            "intent": "Second outcome",
            "done": "S2 is built",
            "builds_after": ["s1"],
        },
    ]


def _roadmap(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "roadmap",
        "title": "The plan",
        "scope": {"in_scope": ["two slices"], "non_goals": ["a third"]},
        "slices": _slices(),
    }
    payload.update(overrides)
    return payload


def _slice_doc(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Slice one",
        "scope": {"in_scope": ["slice one"], "non_goals": ["slice two"]},
        "requirements": [{"key": "alpha", "statement": "It does one thing", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [{"key": "t1", "description": "Build it", "requirements": ["alpha"]}],
        "delivery": {"mode": "none"},
        "roadmap": {"document": ROADMAP_PATH, "slice": "s1"},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 2.1 The payload's shape (validate_payload) -- refusals at submit, whatever the phase
# ---------------------------------------------------------------------------


def test_a_roadmap_with_ordered_slices_validates():
    payload = validate_payload(_roadmap())
    assert [s.key for s in payload.slices] == ["s1", "s2"]
    assert payload.slices[1].builds_after == ["s1"]
    assert payload.slices[0].done == "S1 is built"


def test_slices_are_refused_on_any_other_kind():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_slice_doc(slices=_slices()))
    assert exc.value.field == "slices"


@pytest.mark.parametrize(
    "field,value",
    [
        ("requirements", [{"key": "alpha", "statement": "It does a thing", "modal": "MUST"}]),
        ("tasks", [{"key": "t1", "description": "Build it", "requirements": []}]),
    ],
)
def test_a_roadmap_carrying_requirements_or_tasks_is_refused(field, value):
    with pytest.raises(PayloadError) as exc:
        validate_payload(_roadmap(**{field: value}))
    assert exc.value.field == field
    assert "slice's change document" in str(exc.value)


def test_a_roadmap_carrying_acceptance_criteria_is_refused():
    criterion = {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
    with pytest.raises(PayloadError):
        validate_payload(_roadmap(acceptance_criteria=[criterion]))


def test_duplicate_slice_keys_are_refused():
    slices = _slices()
    slices[1]["key"] = "s1"
    slices[1]["builds_after"] = []
    with pytest.raises(PayloadError) as exc:
        validate_payload(_roadmap(slices=slices))
    assert "s1" in str(exc.value)
    assert exc.value.field == "slices"


def test_a_malformed_slice_key_is_refused():
    slices = _slices()
    slices[0]["key"] = "Slice One"
    slices[1]["builds_after"] = []
    with pytest.raises(PayloadError) as exc:
        validate_payload(_roadmap(slices=slices))
    assert exc.value.field == "slices[0].key"


@pytest.mark.parametrize("named", ["s9", "s2"])
def test_builds_after_must_name_another_slice_of_the_same_roadmap(named):
    slices = _slices()
    slices[1]["builds_after"] = [named]  # s9 does not exist; s2 is the slice itself
    with pytest.raises(PayloadError) as exc:
        validate_payload(_roadmap(slices=slices))
    assert named in str(exc.value)
    assert exc.value.field == "slices[1].builds_after[0]"


def test_the_roadmap_link_validates_on_a_change_spec():
    payload = validate_payload(_slice_doc())
    assert payload.roadmap is not None
    assert payload.roadmap.document == ROADMAP_PATH
    assert payload.roadmap.slice == "s1"


def test_the_roadmap_link_needs_a_document_and_a_slice():
    with pytest.raises(PayloadError):
        validate_payload(_slice_doc(roadmap={"document": ROADMAP_PATH}))


def test_the_roadmap_link_is_refused_on_a_roadmap():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_roadmap(roadmap={"document": ROADMAP_PATH, "slice": "s1"}))
    assert exc.value.field == "roadmap"


def test_a_document_without_slices_or_link_stores_neither_key():
    """Same trap `delivery` had: a default written into every save changes every document's bytes
    and turns an unchanged contract-rigor resubmission into a spurious metadata proposal."""
    stored = payload_to_dict(validate_payload(_slice_doc(roadmap=None)))
    assert "slices" not in stored
    assert "roadmap" not in stored


def test_slices_and_link_round_trip_when_present():
    assert payload_to_dict(validate_payload(_roadmap()))["slices"][1]["builds_after"] == ["s1"]
    assert payload_to_dict(validate_payload(_slice_doc()))["roadmap"] == {
        "document": ROADMAP_PATH,
        "slice": "s1",
    }


# ---------------------------------------------------------------------------
# 3.1 Completeness (spec_completeness.check)
# ---------------------------------------------------------------------------


def _codes(payload, **kwargs):
    return {f.code for f in spec_completeness.check(validate_payload(payload), **kwargs)}


def _approved_roadmap(phase="approved", keys=("s1", "s2")):
    return {
        ROADMAP_PATH: spec_completeness.RoadmapState(
            phase=phase, title="The plan", slice_keys=tuple(keys)
        )
    }


def test_a_roadmap_with_slices_has_no_findings():
    assert _codes(_roadmap()) == set()


def test_a_roadmap_without_slices_is_incomplete_and_not_for_lack_of_requirements():
    codes = _codes(_roadmap(slices=[]))
    assert "roadmap_without_slices" in codes
    assert "no_requirements" not in codes


def test_a_roadmap_still_needs_non_goals():
    assert "non_goals_empty" in _codes(_roadmap(scope={"in_scope": ["x"], "non_goals": []}))


def test_a_slice_of_an_approved_roadmap_has_no_roadmap_finding():
    assert _codes(_slice_doc(), roadmaps=_approved_roadmap()) == set()


@pytest.mark.parametrize("roadmaps", [{}, None])
def test_a_slice_naming_a_missing_roadmap_is_not_proposable(roadmaps):
    findings = spec_completeness.check(validate_payload(_slice_doc()), roadmaps=roadmaps)
    finding = next(f for f in findings if f.code == "roadmap_not_approved")
    assert ROADMAP_PATH in finding.message
    assert finding.where == "roadmap"


def test_a_slice_of_an_exploring_roadmap_names_the_roadmap_and_its_phase():
    findings = spec_completeness.check(
        validate_payload(_slice_doc()), roadmaps=_approved_roadmap(phase="exploring")
    )
    finding = next(f for f in findings if f.code == "roadmap_not_approved")
    assert ROADMAP_PATH in finding.message
    assert "exploring" in finding.message


def test_a_slice_key_the_roadmap_does_not_hold():
    findings = spec_completeness.check(
        validate_payload(_slice_doc(roadmap={"document": ROADMAP_PATH, "slice": "s7"})),
        roadmaps=_approved_roadmap(),
    )
    finding = next(f for f in findings if f.code == "roadmap_slice_unknown")
    assert "s7" in finding.message
    assert ROADMAP_PATH in finding.message


# ---------------------------------------------------------------------------
# Route level: an agent writes a roadmap and a slice, the operator approves (3.1, 4.1, 5.1)
# ---------------------------------------------------------------------------

BASE = "/api/v1/projects/proj-test/project"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
CONVERSATION = "conv-planner"


async def _run(run_id, token, agent="planner", conversation_id=CONVERSATION):
    async with async_session_factory() as session:
        if conversation_id and await session.get(Conversation, conversation_id) is None:
            session.add(
                Conversation(
                    id=conversation_id, project_id="proj-test", agent=agent, lifecycle="open"
                )
            )
        session.add(
            Run(
                id=run_id,
                project_id="proj-test",
                agent=agent,
                status="running",
                turn_depth=0,
                conversation_id=conversation_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def planner():
    return await _run("run-planner", "aw_run_planner-secret")


async def _agent_create(app, headers, **body):
    response = await app.post(f"{AGENT_DOCS}/create", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["path"]


async def _agent_submit(app, headers, path, payload):
    return await app.post(AGENT_DOCS, json={"path": path, "document": payload}, headers=headers)


async def _propose(app, auth_headers, path):
    """The propose route answers 200 either way; a refusal leaves the phase and lists `blocking`."""
    closed = await app.post(f"{BASE}/documents/close-exploration?path={path}", headers=auth_headers)
    assert closed.status_code == 200, closed.text
    response = await app.post(f"{BASE}/documents/propose?path={path}", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _approve(app, auth_headers, path, **body):
    return await app.post(
        f"{BASE}/documents/phase?path={path}&to=approved", json=body, headers=auth_headers
    )


async def _approved_roadmap_doc(app, auth_headers, planner):
    path = await _agent_create(app, planner, kind="roadmap", title="The plan")
    saved = await _agent_submit(app, planner, path, _roadmap())
    assert saved.status_code == 200, saved.text
    assert (await _propose(app, auth_headers, path))["phase"] == "proposed"
    approved = await _approve(app, auth_headers, path)
    assert approved.status_code == 200, approved.text
    return path, approved.json()


async def _proposed_slice(app, auth_headers, headers, roadmap_path, key="s1"):
    path = await _agent_create(app, headers, title="Slice one")
    saved = await _agent_submit(
        app, headers, path, _slice_doc(roadmap={"document": roadmap_path, "slice": key})
    )
    assert saved.status_code == 200, saved.text
    proposed = await _propose(app, auth_headers, path)
    assert proposed["phase"] == "proposed", proposed
    return path


async def _queued(agent="planner"):
    async with async_session_factory() as session:
        rows = await session.execute(
            select(InboundQueueEntry).where(InboundQueueEntry.agent == agent)
        )
        return list(rows.scalars().all())


@pytest.fixture
def scheduled(monkeypatch):
    calls = []

    async def recording(project_id, agent):
        calls.append((project_id, agent))

    monkeypatch.setattr(turn_scheduler, "schedule_agent", recording)
    return calls


# 4.1 -- creation ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_agent_creates_a_roadmap(app, planner):
    path = await _agent_create(app, planner, kind="roadmap")
    async with async_session_factory() as session:
        row = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
    assert row.kind == "roadmap"
    assert row.phase == "exploring"


@pytest.mark.asyncio
async def test_no_kind_is_a_change_spec(app, planner):
    path = await _agent_create(app, planner)
    async with async_session_factory() as session:
        row = (
            await session.execute(select(SpecDocument).where(SpecDocument.path == path))
        ).scalar_one()
    assert row.kind == "change-spec"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["capability", "baseline", "system-map", "nonsense"])
async def test_any_other_kind_is_refused_naming_both_kinds(app, planner, kind):
    response = await app.post(f"{AGENT_DOCS}/create", json={"kind": kind}, headers=planner)
    assert response.status_code == 422, response.text
    message = json.dumps(response.json())
    assert "change-spec" in message and "roadmap" in message
    async with async_session_factory() as session:
        assert (await session.execute(select(SpecDocument))).scalars().first() is None


@pytest.mark.asyncio
async def test_the_agent_read_view_returns_slices_and_the_link(app, auth_headers, planner):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    read = await app.get(AGENT_DOCS, params={"path": roadmap_path}, headers=planner)
    assert read.status_code == 200, read.text
    assert [s["key"] for s in read.json()["slices"]] == ["s1", "s2"]
    read = await app.get(AGENT_DOCS, params={"path": slice_path}, headers=planner)
    assert read.json()["roadmap"] == {"document": roadmap_path, "slice": "s1"}


# 3.1 -- completeness through the routes ------------------------------------------------------


@pytest.mark.asyncio
async def test_approving_a_roadmap_creates_no_task(app, auth_headers, planner):
    _, approved = await _approved_roadmap_doc(app, auth_headers, planner)
    assert approved["phase"] == "approved"
    assert approved["tasks_created"] == []
    async with async_session_factory() as session:
        assert (await session.execute(select(Task))).scalars().first() is None


@pytest.mark.asyncio
async def test_a_slice_of_an_exploring_roadmap_cannot_be_proposed(app, auth_headers, planner):
    roadmap_path = await _agent_create(app, planner, kind="roadmap")
    assert (await _agent_submit(app, planner, roadmap_path, _roadmap())).status_code == 200
    slice_path = await _agent_create(app, planner)
    saved = await _agent_submit(
        app, planner, slice_path, _slice_doc(roadmap={"document": roadmap_path, "slice": "s1"})
    )
    assert "roadmap_not_approved" in {f["code"] for f in saved.json()["blocking"]}

    refused = await _propose(app, auth_headers, slice_path)
    assert refused["phase"] == "exploring"
    blocking = refused["blocking"]
    finding = next(f for f in blocking if f["code"] == "roadmap_not_approved")
    assert roadmap_path in finding["message"] and "exploring" in finding["message"]


@pytest.mark.asyncio
async def test_a_slice_key_the_roadmap_does_not_hold_cannot_be_proposed(app, auth_headers, planner):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _agent_create(app, planner)
    await _agent_submit(
        app, planner, slice_path, _slice_doc(roadmap={"document": roadmap_path, "slice": "s7"})
    )
    refused = await _propose(app, auth_headers, slice_path)
    assert refused["phase"] == "exploring"
    assert "roadmap_slice_unknown" in {f["code"] for f in refused["blocking"]}


@pytest.mark.asyncio
async def test_a_reopened_roadmap_blocks_its_slice_at_approval(app, auth_headers, planner):
    """Unlike `import_not_approved`, the link finding is not dropped at approval."""
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)
    reopened = await app.post(
        f"{BASE}/documents/phase?path={roadmap_path}&to=exploring",
        json={"reason": "re-order the slices"},
        headers=auth_headers,
    )
    assert reopened.status_code == 200, reopened.text

    refused = await _approve(app, auth_headers, slice_path)
    assert refused.status_code == 409, refused.text
    assert "roadmap_not_approved" in {f["code"] for f in refused.json()["detail"]["blocking"]}


# 5.1 -- approving a slice drafts the next one ------------------------------------------------


@pytest.mark.asyncio
async def test_approving_a_slice_queues_the_next_one_to_its_author(
    app, auth_headers, planner, scheduled
):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    approved = await _approve(app, auth_headers, slice_path, draft_next_slice=True)

    assert approved.status_code == 200, approved.text
    assert approved.json()["next_slice"] == {"state": "queued", "slice": "s2", "agent": "planner"}
    entries = await _queued()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.origin_type == "operator"
    assert entry.origin_agent is None
    assert entry.hop_depth == 0
    assert entry.conversation_id == CONVERSATION
    assert entry.spec_document == roadmap_path
    assert "s2" in entry.content and "Slice two" in entry.content
    assert roadmap_path in entry.content
    assert scheduled == [("proj-test", "planner")]


@pytest.mark.asyncio
async def test_the_next_slice_goes_to_the_slice_author_in_its_creating_conversation(
    app, auth_headers, planner, scheduled
):
    """The roadmap's author and the slice's author may differ; the slice's is asked."""
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    other = await _run(
        "run-other", "aw_run_other-secret", agent="drafter", conversation_id="conv-d"
    )
    slice_path = await _proposed_slice(app, auth_headers, other, roadmap_path)

    approved = await _approve(app, auth_headers, slice_path, draft_next_slice=True)

    assert approved.json()["next_slice"]["agent"] == "drafter"
    entries = await _queued("drafter")
    assert [e.conversation_id for e in entries] == ["conv-d"]
    assert await _queued("planner") == []


@pytest.mark.asyncio
async def test_the_last_slice_queues_nothing(app, auth_headers, planner, scheduled):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path, key="s2")

    approved = await _approve(app, auth_headers, slice_path, draft_next_slice=True)

    assert approved.status_code == 200, approved.text
    assert approved.json()["next_slice"] == {"state": "last_slice", "slice": None, "agent": None}
    assert await _queued() == []
    assert scheduled == []


@pytest.mark.asyncio
async def test_a_slice_the_operator_created_has_no_author_to_ask(
    app, auth_headers, planner, scheduled
):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = "spec/changes/operator-slice/spec.html"
    created = await app.post(
        f"{BASE}/documents", json={"path": slice_path, "title": "Slice one"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await _agent_submit(
        app, planner, slice_path, _slice_doc(roadmap={"document": roadmap_path, "slice": "s1"})
    )
    assert saved.status_code == 200, saved.text
    assert (await _propose(app, auth_headers, slice_path))["phase"] == "proposed"

    approved = await _approve(app, auth_headers, slice_path, draft_next_slice=True)

    assert approved.status_code == 200, approved.text
    assert approved.json()["next_slice"]["state"] == "no_author"
    assert await _queued() == []


@pytest.mark.asyncio
async def test_not_asking_queues_nothing(app, auth_headers, planner, scheduled):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    approved = await _approve(app, auth_headers, slice_path)

    assert approved.status_code == 200, approved.text
    assert "next_slice" not in approved.json()
    assert await _queued() == []
    assert scheduled == []


@pytest.mark.asyncio
async def test_a_document_that_is_not_a_slice_is_unaffected(app, auth_headers, planner, scheduled):
    path = await _agent_create(app, planner)
    assert (await _agent_submit(app, planner, path, _slice_doc(roadmap=None))).status_code == 200
    assert (await _propose(app, auth_headers, path))["phase"] == "proposed"

    approved = await _approve(app, auth_headers, path, draft_next_slice=True)

    assert approved.status_code == 200, approved.text
    assert approved.json()["next_slice"] == {"state": "not_a_slice", "slice": None, "agent": None}
    assert len(approved.json()["tasks_created"]) == 1
    assert await _queued() == []


@pytest.mark.asyncio
async def test_draft_next_slice_is_refused_off_an_approval(app, auth_headers, planner):
    path = await _agent_create(app, planner)
    response = await app.post(
        f"{BASE}/documents/phase?path={path}&to=exploring",
        json={"draft_next_slice": True},
        headers=auth_headers,
    )
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_a_scheduling_failure_leaves_the_approval_standing(
    app, auth_headers, planner, monkeypatch
):
    """What the route returns when scheduling raises: the approval and the board are committed,
    the entry is durable (the next drain delivers it), and the response still says queued."""

    async def broken(project_id, agent):
        raise RuntimeError("scheduler is down")

    monkeypatch.setattr(turn_scheduler, "schedule_agent", broken)
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    approved = await _approve(app, auth_headers, slice_path, draft_next_slice=True)

    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["phase"] == "approved"
    assert len(body["tasks_created"]) == 1
    assert body["next_slice"]["state"] == "queued"
    assert len(await _queued()) == 1


@pytest.mark.asyncio
async def test_a_queueing_failure_leaves_the_approval_standing(
    app, auth_headers, planner, scheduled, monkeypatch
):
    """When the entry itself cannot be written, the approval still stands and says so."""
    from hub.api.v1 import spec as spec_api

    def broken_entry(**kwargs):
        raise ValueError("cannot build the entry")

    monkeypatch.setattr(spec_api, "new_entry", broken_entry)
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    approved = await _approve(app, auth_headers, slice_path, draft_next_slice=True)

    assert approved.status_code == 200, approved.text
    assert approved.json()["phase"] == "approved"
    assert approved.json()["next_slice"]["state"] == "not_queued"
    assert await _queued() == []
    assert scheduled == []


# 4.1 -- guidance -------------------------------------------------------------------------------


@pytest.mark.parametrize("tool", ["create_spec_document", "submit_spec_document"])
def test_the_tools_name_the_roadmap_plus_slice_shape_and_the_slice_size(tool):
    from hub import mcp_server

    doc = getattr(mcp_server, tool).__doc__
    assert "roadmap" in doc
    assert "first slice" in doc
    assert "dozen requirements" in doc


def test_a_specification_turn_is_told_the_shape_and_the_size():
    from hub.api.v1.agents import SPEC_PHASE_DUTIES

    exploring = SPEC_PHASE_DUTIES["exploring"]
    assert "roadmap" in exploring
    assert "dozen requirements" in exploring


async def _context_with_open(path):
    from hub.api.v1.agents import _render_hub_agent_context

    async with async_session_factory() as db:
        rendered = await _render_hub_agent_context(
            agent="planner",
            project_id="proj-test",
            db=db,
            session_data=None,
            agent_row=None,
            work_dir="/tmp/project",
            spec_document=path,
        )
    return rendered["context"]


@pytest.mark.asyncio
async def test_an_approved_roadmap_is_not_implemented(app, auth_headers, planner):
    from hub.api.v1.agents import ROADMAP_APPROVED_DUTY, SPEC_PHASE_DUTIES

    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)

    context = await _context_with_open(roadmap_path)

    assert ROADMAP_APPROVED_DUTY in context
    assert SPEC_PHASE_DUTIES["approved"] not in context
    assert "Do not implement" in ROADMAP_APPROVED_DUTY


@pytest.mark.asyncio
async def test_an_approved_change_document_keeps_its_duty(app, auth_headers, planner):
    from hub.api.v1.agents import SPEC_PHASE_DUTIES

    path = await _agent_create(app, planner)
    assert (await _agent_submit(app, planner, path, _slice_doc(roadmap=None))).status_code == 200
    assert (await _propose(app, auth_headers, path))["phase"] == "proposed"
    assert (await _approve(app, auth_headers, path)).status_code == 200

    assert SPEC_PHASE_DUTIES["approved"] in await _context_with_open(path)


# 6.1 -- rendering -------------------------------------------------------------------------------


def test_a_roadmap_renders_its_slices_in_order():
    from hub.spec_render import render_document

    payload = validate_payload(_roadmap())
    html = render_document(payload, {}, phase="exploring", stored_payload=payload_to_dict(payload))

    assert '<section id="slices">' in html
    first, second = html.index("Slice one"), html.index("Slice two")
    assert first < second
    assert "First outcome" in html and "S2 is built" in html
    assert "Builds after: s1" in html


def test_a_document_without_slices_or_link_renders_as_before():
    from hub.spec_render import render_document

    payload = validate_payload(_slice_doc(roadmap=None))
    html = render_document(payload, {}, phase="exploring", stored_payload=payload_to_dict(payload))
    assert 'id="slices"' not in html
    assert "aw-slice-of" not in html


@pytest.mark.asyncio
async def test_a_slice_document_says_whose_slice_it_is(app, auth_headers, planner, tmp_path):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    html = (tmp_path / slice_path).read_text(encoding="utf-8")
    line = html[html.index("aw-slice-of") :].split("</p>", 1)[0]
    assert "s1" in line and "Slice one" in line and "The plan" in line


@pytest.mark.asyncio
async def test_the_spec_read_names_the_roadmap_slice_for_the_app(app, auth_headers, planner):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)

    got = await app.get(f"{BASE}/spec", params={"path": slice_path}, headers=auth_headers)
    assert got.json()["roadmap_slice"] == {"document": roadmap_path, "slice": "s1"}
    got = await app.get(f"{BASE}/spec", params={"path": roadmap_path}, headers=auth_headers)
    assert "roadmap_slice" not in got.json()
