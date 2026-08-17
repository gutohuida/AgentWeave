"""The gate, and the two ways a gate stops being one.

A gate fails in exactly two ways. It can be **removed by the party it blocks** — which is why an
agent has no route to rigor in either direction, and why demotion is the more dangerous direction to
overlook. And it can be **switched off by the person it frustrates** — which is why a refusal has to
name every blocking requirement and say what would satisfy it. An unactionable gate gets disabled,
and that is worse than never having built one.

The first test is the demonstrable case from the design source: the same task completion, three
outcomes.
"""

import pytest
from sqlalchemy import select

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run, SpecDocument, SpecRigorEvent, TaskTransition
from hub.spec_payload import SCHEMA_VERSION, extract_payload

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/gate-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}
BETA = {"key": "beta", "statement": "It records a completed watering", "modal": "SHOULD"}


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-gate", project_id="proj-test", name="gate-builder"))
        session.add(
            Run(
                id="run-gate",
                project_id="proj-test",
                agent="gate-builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_gate-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_gate-secret"}


async def _document(app, auth_headers, run_headers, requirements=(ALPHA,)):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Gate demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Gate demo",
                "requirements": list(requirements),
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


async def _set_rigor(app, auth_headers, rigor, **body):
    return await app.post(
        f"{BASE}/documents/{PATH}/rigor", json={"rigor": rigor, **body}, headers=auth_headers
    )


async def _task_to(app, auth_headers, task_id, *statuses):
    response = None
    for next_status in statuses:
        response = await app.patch(
            f"{TASKS}/{task_id}", json={"status": next_status}, headers=auth_headers
        )
        if response.status_code != 200:
            return response
    return response


async def _linked_task(app, auth_headers, identifiers=("FR-1",)):
    created = await app.post(
        TASKS,
        json={"title": "Build it", "requirement_ids": list(identifiers)},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


# ---------------------------------------------------------------------------
# The demonstrable case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_same_completion_three_outcomes(app, auth_headers, builder, tmp_path):
    """Sketch approves, gate refuses, evidence opens it. One task's worth of work,
    three answers, and the only thing that changed is what the operator asked for."""
    await _document(app, auth_headers, builder)

    # 1. A sketch blocks nothing. It is the default, and it has to be: a change that made every
    #    approved document start refusing approvals would arrive as a barrier nobody asked for.
    first = await _linked_task(app, auth_headers)
    approved = await _task_to(
        app, auth_headers, first, "assigned", "in_progress", "completed", "under_review", "approved"
    )
    assert approved.status_code == 200, approved.text

    # 2. Promoted to gate, the same sequence refuses.
    promoted = await _set_rigor(app, auth_headers, "gate")
    assert promoted.status_code == 200, promoted.text

    second = await _linked_task(app, auth_headers)
    refused = await _task_to(
        app,
        auth_headers,
        second,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )
    assert refused.status_code == 409, refused.text
    assert "FR-1" in refused.text

    # 3. Evidence accepted independently opens it.
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran the tests"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text

    finally_approved = await _task_to(app, auth_headers, second, "approved")
    assert finally_approved.status_code == 200, finally_approved.text


# ---------------------------------------------------------------------------
# What the gate does and does not touch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_task_linked_to_nothing_is_unaffected(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")

    created = await app.post(TASKS, json={"title": "Unrelated"}, headers=auth_headers)
    response = await _task_to(
        app,
        auth_headers,
        created.json()["id"],
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_completed_is_never_blocked(app, auth_headers, builder, tmp_path):
    """Refusing `completed` would deadlock the ordinary path: evidence is accepted after review, and
    review follows completion, so the task could never reach the step that produces the acceptance
    it is blocked for."""
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers)

    response = await _task_to(app, auth_headers, task_id, "assigned", "in_progress", "completed")

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_a_contract_reports_and_blocks_nothing(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "contract")
    task_id = await _linked_task(app, auth_headers)

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_a_contract_names_the_unmet_requirement_on_the_approval_response(
    app, auth_headers, builder, tmp_path
):
    """5.5 of `2026-08-13-a-gate-that-only-evidence-opens`: `contract` reports rather than staying
    silent like `sketch`. The report rides the response of the call that approved, the same way a
    `gate` refusal names its blockers — not a second thing to go and look up."""
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "contract")
    task_id = await _linked_task(app, auth_headers)

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved"
    reported = body["approval_report"]
    assert len(reported) == 1, reported
    assert reported[0]["identifier"] == "FR-1"
    assert reported[0]["state"] != "verified"
    assert reported[0]["remedy"]


@pytest.mark.asyncio
async def test_a_sketch_reports_nothing_on_approval(app, auth_headers, builder, tmp_path):
    """The default rigor stays silent — `approval_report` is `contract`'s behaviour, not every
    rigor's, or it would just be `requirement_links` under a new name."""
    await _document(app, auth_headers, builder)
    task_id = await _linked_task(app, auth_headers)

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 200, response.text
    assert response.json()["approval_report"] == []


@pytest.mark.asyncio
async def test_a_contract_stops_reporting_once_the_requirement_is_verified(
    app, auth_headers, builder, tmp_path
):
    """The report describes this approval, not a permanent scar — a `contract` requirement that
    was satisfied before approval has nothing left to name."""
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "contract")
    task_id = await _linked_task(app, auth_headers)
    recorded = await app.post(
        AGENT_EVIDENCE, json={"identifier": "FR-1", "summary": "ran the tests"}, headers=builder
    )
    assert recorded.status_code == 201, recorded.text
    accepted = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    assert accepted.status_code == 200, accepted.text

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 200, response.text
    assert response.json()["approval_report"] == []


@pytest.mark.asyncio
async def test_the_refusal_names_every_blocking_requirement_and_its_reason(
    app, auth_headers, builder, tmp_path
):
    """Asserted on the payload, not on a message string: a surface has to be able to render each
    blocked requirement without parsing prose."""
    await _document(app, auth_headers, builder, requirements=(ALPHA, BETA))
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers, identifiers=("FR-1", "FR-2"))
    # One has evidence waiting; the other has nothing at all. Two different reasons, both named.
    await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    blocking = {entry["identifier"]: entry for entry in detail["blocking"]}
    assert set(blocking) == {"FR-1", "FR-2"}
    assert blocking["FR-1"]["state"] == "evidence_awaiting_review"
    assert "accept" in blocking["FR-1"]["remedy"]
    # The task serving FR-2 is under review by now, so its state is work-with-nothing-to-show
    # rather than no-work-at-all — and the remedy says so, which is the part that matters.
    assert blocking["FR-2"]["state"] == "in_progress"
    assert "evidence" in blocking["FR-2"]["remedy"]


@pytest.mark.asyncio
async def test_rejected_evidence_blocks_with_its_own_remedy(app, auth_headers, builder, tmp_path):
    """A rejected requirement is not `in_progress` to the gate either — it gets `REJECTED`'s more
    specific remedy, naming that evidence was judged and turned down, not the generic "no evidence
    yet" text `in_progress` carries."""
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers)
    recorded = await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)
    await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "rejected", "reason": "does not demonstrate it"},
        headers=auth_headers,
    )

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 409
    blocking = response.json()["detail"]["blocking"][0]
    assert blocking["state"] == "rejected"
    assert "rejected" in blocking["remedy"]


@pytest.mark.asyncio
async def test_stale_evidence_does_not_open_the_gate(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)
    recorded = await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)
    await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Gate demo",
                "requirements": [{**ALPHA, "statement": "Something else entirely"}],
            },
        },
        headers=builder,
    )
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers)

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 409
    assert response.json()["detail"]["blocking"][0]["state"] == "stale"


@pytest.mark.asyncio
async def test_the_gate_and_the_badge_cannot_disagree(app, auth_headers, builder, tmp_path):
    """Both read `requirement_coverage`. If the gate computed its own answer, a task could be
    refused while the document beside it showed everything green."""
    await _document(app, auth_headers, builder, requirements=(ALPHA, BETA))
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers, identifiers=("FR-1", "FR-2"))
    await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)

    refused = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )
    coverage = await app.get(f"{BASE}/spec/coverage", headers=auth_headers)

    from_gate = {
        entry["identifier"]: entry["state"] for entry in refused.json()["detail"]["blocking"]
    }
    from_badge = {
        entry["identifier"]: entry["state"]
        for entry in coverage.json()["requirements"]
        if entry["identifier"] in from_gate
    }
    assert from_gate == from_badge


@pytest.mark.asyncio
async def test_a_broken_requirement_blocks_as_a_diagnostic(app, auth_headers, builder, tmp_path):
    """Not as an unverified requirement: "this is unverified" would send someone to record evidence
    for something that cannot hold any."""
    from hub.db.models import SpecRequirement

    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers)

    async with async_session_factory() as session:
        row = (
            (
                await session.execute(
                    select(SpecRequirement).where(SpecRequirement.identifier == "FR-1")
                )
            )
            .scalars()
            .first()
        )
        row.digest = ""
        await session.commit()

    response = await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["blocking"] == []
    assert detail["diagnostics"][0]["identifier"] == "FR-1"


# ---------------------------------------------------------------------------
# An agent cannot touch rigor
# ---------------------------------------------------------------------------


def _rigor_mutations(module) -> list:
    """Every way *module* could change a document's rigor, found in its syntax tree.

    Originally `assert "rigor" not in source`. That forbade the *word*, which conflates reading the
    value with setting it — and an agent reading `rigor` is how it judges whether a document is
    settled enough to build on (`read_spec_document`, design D7). The property B4 wanted is that no
    agent-facing surface can **set** it, so that is what this looks for.

    Stricter than the substring in the direction that counts: `"rigor" in source` would have been
    satisfied by any spelling that avoided the literal word, while this catches the assignment
    itself.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    found = []
    for node in ast.walk(tree):
        # `document.rigor = …`, or `rigor = …` at any level.
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and target.attr == "rigor":
                    found.append(f"assignment to .rigor (line {node.lineno})")
                if isinstance(target, ast.Name) and target.id == "rigor":
                    found.append(f"binds a name `rigor` (line {node.lineno})")
        # A route or tool that accepts rigor as an argument — including a Pydantic body field,
        # which is an AnnAssign inside a class and is caught above.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for argument in [*args.args, *args.posonlyargs, *args.kwonlyargs]:
                if argument.arg == "rigor":
                    found.append(f"{node.name}() takes a `rigor` argument (line {node.lineno})")
        # The only function that can change it, and the module that owns it.
        if isinstance(node, ast.Name) and node.id in {"set_rigor", "spec_rigor"}:
            found.append(f"references {node.id} (line {node.lineno})")
        if isinstance(node, ast.Attribute) and node.attr == "set_rigor":
            found.append(f"calls set_rigor (line {node.lineno})")
    return found


def test_no_agent_facing_route_sets_rigor():
    """Enforced by absence, as approval is — not by an instruction telling agents not to.

    A source scan rather than a request, because the property is that the surface does not exist:
    a test that posted somewhere would only prove that one path is closed."""
    from hub.api.v1 import agent_actions

    assert _rigor_mutations(agent_actions) == []


def test_the_tool_surface_offers_no_way_to_set_rigor():
    from hub import mcp_server

    assert _rigor_mutations(mcp_server) == []


def test_no_tool_advertises_a_rigor_argument():
    """Checked against the schema an agent is actually served, not against the source.

    A tool could take rigor through a differently-named parameter, or a model could grow the field
    without the word appearing in a signature. The generated schema is what the agent sees, so it is
    the honest place to assert that the argument is not on offer.
    """
    import asyncio

    from hub import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    offering = [
        tool.name for tool in tools if "rigor" in (tool.parameters or {}).get("properties", {})
    ]
    assert offering == [], f"these tools advertise a rigor argument: {offering}"


@pytest.mark.asyncio
async def test_the_function_itself_refuses_a_non_operator(app, auth_headers, builder, tmp_path):
    """So the rule survives a second caller being added later."""
    from hub import spec_rigor
    from hub.spec_lifecycle import Actor

    await _document(app, auth_headers, builder)

    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
        with pytest.raises(spec_rigor.RigorRefusedError) as refusal:
            await spec_rigor.set_rigor(
                session,
                document,
                "gate",
                actor=Actor(kind="agent", name="gate-builder", run_id="run-gate"),
            )
        assert document.rigor == "sketch"

    assert refusal.value.code == "rigor_is_the_operators"


@pytest.mark.asyncio
async def test_a_blocked_agent_cannot_demote(app, auth_headers, builder, tmp_path):
    """The dangerous direction. If the party a gate blocks can lower it, the gate is a speed bump
    the blocked party removes."""
    from hub import spec_rigor
    from hub.spec_lifecycle import Actor

    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")

    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
        with pytest.raises(spec_rigor.RigorRefusedError):
            await spec_rigor.set_rigor(
                session,
                document,
                "sketch",
                actor=Actor(kind="agent", name="gate-builder", run_id="run-gate"),
            )
        assert document.rigor == "gate"


# ---------------------------------------------------------------------------
# Promotion, demotion, and the record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_promotion_is_refused_on_a_document_with_no_requirements(
    app, auth_headers, builder, tmp_path
):
    """Rigor is a claim about enforceability. A document with nothing to enforce cannot make it."""
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Empty"}, headers=auth_headers
    )
    assert created.status_code == 201
    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Empty",
                "requirements": [],
            },
        },
        headers=builder,
    )

    response = await _set_rigor(app, auth_headers, "gate")

    assert response.status_code == 409
    assert "nothing to enforce" in response.text


@pytest.mark.asyncio
async def test_promotion_is_refused_on_a_document_that_does_not_parse(
    app, auth_headers, builder, tmp_path
):
    await _document(app, auth_headers, builder)
    (tmp_path / PATH).write_text("<html><body>hand written</body></html>", encoding="utf-8")

    response = await _set_rigor(app, auth_headers, "gate")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "document_not_enforceable"


@pytest.mark.asyncio
async def test_demotion_works_on_a_document_that_does_not_parse(
    app, auth_headers, builder, tmp_path
):
    """The document an operator most needs to stop enforcing is exactly the one that has stopped
    parsing."""
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")
    (tmp_path / PATH).write_text("<html><body>hand written</body></html>", encoding="utf-8")

    response = await _set_rigor(app, auth_headers, "sketch")

    assert response.status_code == 200, response.text
    assert response.json()["rigor"] == "sketch"


@pytest.mark.asyncio
async def test_demotion_keeps_the_links_evidence_and_reviews(app, auth_headers, builder, tmp_path):
    """Otherwise lowering rigor to unblock something urgent is a laundering step."""
    from hub.db.models import EvidenceReview, RequirementEvidence, TaskRequirementLink

    await _document(app, auth_headers, builder)
    task_id = await _linked_task(app, auth_headers)
    recorded = await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)
    await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    await _set_rigor(app, auth_headers, "gate")

    await _set_rigor(app, auth_headers, "sketch", reason="shipping today")

    async with async_session_factory() as session:
        links = (
            (
                await session.execute(
                    select(TaskRequirementLink).where(TaskRequirementLink.task_id == task_id)
                )
            )
            .scalars()
            .all()
        )
        evidence = (await session.execute(select(RequirementEvidence))).scalars().all()
        reviews = (await session.execute(select(EvidenceReview))).scalars().all()

    assert len(links) == 1
    assert len(evidence) == 1
    assert len(reviews) == 1


@pytest.mark.asyncio
async def test_every_rigor_change_is_recorded_and_attributed(app, auth_headers, builder, tmp_path):
    """There is no unrecorded override. Demotion is a legitimate decision *because* of this row."""
    await _document(app, auth_headers, builder)

    await _set_rigor(app, auth_headers, "gate", reason="ready to enforce")
    await _set_rigor(app, auth_headers, "sketch", reason="shipping today")

    async with async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(SpecRigorEvent).order_by(SpecRigorEvent.created_at, SpecRigorEvent.id)
                )
            )
            .scalars()
            .all()
        )

    assert [(e.from_rigor, e.to_rigor) for e in events] == [
        ("sketch", "gate"),
        ("gate", "sketch"),
    ]
    assert all(event.actor_kind == "operator" for event in events)
    assert events[1].reason == "shipping today"


@pytest.mark.asyncio
async def test_a_rigor_change_against_a_stale_digest_is_refused(
    app, auth_headers, builder, tmp_path
):
    """What was promoted must be what was read."""
    await _document(app, auth_headers, builder)

    response = await _set_rigor(app, auth_headers, "gate", expected_digest="0" * 64)

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stale_digest"


@pytest.mark.asyncio
async def test_the_document_itself_states_its_rigor(app, auth_headers, builder, tmp_path):
    await _document(app, auth_headers, builder)

    await _set_rigor(app, auth_headers, "gate")

    content = (tmp_path / PATH).read_text(encoding="utf-8")
    assert 'name="aw-spec-rigor" content="gate"' in content
    # And a save afterwards does not silently reset it — the row is what the renderer reads.
    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Gate demo",
                "requirements": [ALPHA],
            },
        },
        headers=builder,
    )
    assert 'content="gate"' in (tmp_path / PATH).read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_an_agent_cannot_set_rigor_through_the_payload(app, auth_headers, builder, tmp_path):
    """The renderer takes rigor from the row. A payload field would be an agent lowering its own gate."""
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")

    await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Gate demo",
                "requirements": [ALPHA],
                "rigor": "sketch",
                "gate_policy": "sketch",
            },
        },
        headers=builder,
    )

    async with async_session_factory() as session:
        document = (
            (await session.execute(select(SpecDocument).where(SpecDocument.path == PATH)))
            .scalars()
            .first()
        )
    assert document.rigor == "gate"
    stored = extract_payload((tmp_path / PATH).read_text(encoding="utf-8"))
    # The submitted field survives as data — unknown fields round-trip — and governs nothing.
    assert stored.get("rigor") == "sketch"
    assert 'name="aw-spec-rigor" content="gate"' in (tmp_path / PATH).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The policy that governed a decision
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transitions_policy_survives_a_later_rigor_change(
    app, auth_headers, builder, tmp_path
):
    """A gate that passed last month has to be explainable today, and rigor being
    operator-editable is what makes that a live risk rather than a theoretical one."""
    await _document(app, auth_headers, builder)
    recorded = await app.post(AGENT_EVIDENCE, json={"identifier": "FR-1"}, headers=builder)
    await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers)
    await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    async with async_session_factory() as session:
        transition = (
            (
                await session.execute(
                    select(TaskTransition).where(
                        TaskTransition.task_id == task_id, TaskTransition.to_status == "approved"
                    )
                )
            )
            .scalars()
            .first()
        )
        recorded_digest = transition.policy_digest

    assert recorded_digest

    await _set_rigor(app, auth_headers, "sketch")

    async with async_session_factory() as session:
        transition = (
            (
                await session.execute(
                    select(TaskTransition).where(
                        TaskTransition.task_id == task_id, TaskTransition.to_status == "approved"
                    )
                )
            )
            .scalars()
            .first()
        )
    assert transition.policy_digest == recorded_digest


@pytest.mark.asyncio
async def test_an_ungated_approval_records_no_policy(app, auth_headers, builder, tmp_path):
    """Null because no policy governed it — a fact about the transition, not a gap in it."""
    await _document(app, auth_headers, builder)
    task_id = await _linked_task(app, auth_headers)
    await _task_to(
        app,
        auth_headers,
        task_id,
        "assigned",
        "in_progress",
        "completed",
        "under_review",
        "approved",
    )

    async with async_session_factory() as session:
        transition = (
            (
                await session.execute(
                    select(TaskTransition).where(
                        TaskTransition.task_id == task_id, TaskTransition.to_status == "approved"
                    )
                )
            )
            .scalars()
            .first()
        )
    assert transition.policy_digest is None


# ---------------------------------------------------------------------------
# Every surface, not only the operator route
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_gate_holds_over_the_agent_plane(app, auth_headers, builder, tmp_path):
    """All four surfaces call the one service. Asserted rather than assumed."""
    await _document(app, auth_headers, builder)
    await _set_rigor(app, auth_headers, "gate")
    task_id = await _linked_task(app, auth_headers)
    await _task_to(
        app, auth_headers, task_id, "assigned", "in_progress", "completed", "under_review"
    )

    response = await app.patch(
        f"/api/v1/agent-actions/tasks/{task_id}",
        json={"status": "approved"},
        headers=builder,
    )

    assert response.status_code == 409, response.text
    assert "FR-1" in response.text


def test_the_gate_lives_inside_the_transition_service():
    """A second enforcement point is a second thing to bypass. The rule that no route assigns
    `Task.status` directly is what makes one point sufficient — so the gate has to be here."""
    import inspect

    from hub import task_transition_service

    source = inspect.getsource(task_transition_service.apply_transition)
    assert "requirement_gate" in source
    assert "approved" in source
