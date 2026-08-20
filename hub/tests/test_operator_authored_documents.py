"""The operator writes a document's content directly — `PUT /documents/{path}/content`.

This route reaches a branch of `spec_service.save_document` that has existed since capability
documents shipped and has never been callable over HTTP. The service refuses a capability write
from any actor that is not the operator, and `spec-document-authority` already requires that "the
same submission from the operator succeeds" — but `save_document`'s only API caller was the agent
route, which binds the actor to a run. The requirement was exercisable only by importing the module
in-process, which `test_spec_capability_kind.py` does.

What these tests are careful about: the route must add **no rules of its own**. Every refusal an
agent gets, the operator gets too. The only difference is who the actor is.
"""

import pytest
from sqlalchemy import select

from hub import spec_lifecycle
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run, SpecDocumentEvent
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"
CAP_PATH = "spec/capabilities/demo/spec.html"
CHANGE_PATH = "spec/changes/demo/spec.html"


@pytest.fixture
async def run_headers():
    token = "aw_run_operator-authoring-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-operator-authoring",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _payload(kind, **overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "title": "Demo",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}
        ],
    }
    payload.update(overrides)
    return payload


def _complete_payload(kind, **overrides):
    """A payload that `spec_completeness.check` passes, so the document can actually be proposed.

    The minimal payload above is deliberately incomplete — fine for a write, since a document under
    discussion is incomplete by definition. Proposing is what cares, and it wants three things:
    non-empty `non_goals`, an acceptance criterion covering every requirement, and a task covering
    every requirement ("a task tracing to nothing is work nobody asked for", and a requirement
    tracing to no task is something nothing implements).
    """
    return _payload(
        kind,
        acceptance_criteria=[
            {
                "key": "ac1",
                "requirement": "alpha",
                "given": "a request is in flight",
                "when": "the response is measured",
                "then": "it arrived within 200ms",
            }
        ],
        tasks=[
            {
                "key": "t1",
                "title": "Meet the latency budget",
                "description": "Measure the response path and bring it under 200ms",
                "requirements": ["alpha"],
            }
        ],
        **overrides,
    )


async def _create(app, headers, path, kind, title="Demo"):
    response = await app.post(
        f"{BASE}/documents", json={"path": path, "title": title, "kind": kind}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response


async def _write(app, headers, path, payload):
    return await app.put(
        f"{BASE}/documents/{path}/content", json={"document": payload}, headers=headers
    )


@pytest.mark.asyncio
class TestTheOperatorCanWrite:
    async def test_the_operator_writes_a_capability_document(self, app, auth_headers, tmp_path):
        """The requirement that existed and could not be satisfied over the API."""
        await _create(app, auth_headers, CAP_PATH, "capability")

        response = await _write(app, auth_headers, CAP_PATH, _payload("capability"))

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["phase"] == "current"
        assert body["identifiers"]
        assert (tmp_path / CAP_PATH).is_file()

    async def test_the_written_document_reads_back_with_its_requirement(
        self, app, auth_headers, tmp_path
    ):
        await _create(app, auth_headers, CAP_PATH, "capability")
        await _write(app, auth_headers, CAP_PATH, _payload("capability"))

        content = (tmp_path / CAP_PATH).read_text(encoding="utf-8")
        assert "It responds within 200ms" in content
        assert 'name="aw-spec-kind" content="capability"' in content
        assert 'name="aw-spec-status" content="current"' in content

    async def test_the_operator_writes_a_change_document_too(self, app, auth_headers, tmp_path):
        """Not capability-specific: the operator can write anything an agent could."""
        await _create(app, auth_headers, CHANGE_PATH, "change-spec")

        response = await _write(app, auth_headers, CHANGE_PATH, _payload("change-spec"))

        assert response.status_code == 200, response.text
        assert response.json()["phase"] == "exploring"

    async def test_writing_the_same_payload_twice_leaves_the_same_content(
        self, app, auth_headers, tmp_path
    ):
        """`PUT`'s promise, and what makes an interrupted 33-document import safe to re-run."""
        await _create(app, auth_headers, CAP_PATH, "capability")
        await _write(app, auth_headers, CAP_PATH, _payload("capability"))
        first = (tmp_path / CAP_PATH).read_text(encoding="utf-8")

        await _write(app, auth_headers, CAP_PATH, _payload("capability"))
        assert (tmp_path / CAP_PATH).read_text(encoding="utf-8") == first

    async def test_a_missing_document_is_a_404_not_a_create(self, app, auth_headers):
        """The operator starts an exploration explicitly; this route never creates one."""
        response = await _write(app, auth_headers, CAP_PATH, _payload("capability"))
        assert response.status_code == 404


@pytest.mark.asyncio
class TestNoRuleIsRelaxedForTheOperator:
    async def test_an_agent_still_cannot_write_a_capability_document(
        self, app, auth_headers, run_headers, tmp_path
    ):
        await _create(app, auth_headers, CAP_PATH, "capability")
        await _write(app, auth_headers, CAP_PATH, _payload("capability", title="Operator's"))
        before = (tmp_path / CAP_PATH).read_text(encoding="utf-8")

        response = await app.post(
            AGENT,
            json={"path": CAP_PATH, "document": _payload("capability", title="Agent's")},
            headers=run_headers,
        )

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "capability_write_is_the_operators"
        assert (tmp_path / CAP_PATH).read_text(encoding="utf-8") == before

    async def test_an_invalid_payload_is_refused_and_names_its_field(self, app, auth_headers):
        await _create(app, auth_headers, CAP_PATH, "capability")

        response = await _write(
            app,
            auth_headers,
            CAP_PATH,
            _payload("capability", requirements=[{"key": "alpha", "statement": "no modal here"}]),
        )

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "payload_invalid"
        assert response.json()["detail"]["field"]

    async def test_the_operator_cannot_reclassify_a_document(self, app, auth_headers):
        await _create(app, auth_headers, CHANGE_PATH, "change-spec")

        response = await _write(app, auth_headers, CHANGE_PATH, _payload("capability"))

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "kind_is_fixed"

    async def test_an_approved_document_is_refused_until_reopened(self, app, auth_headers):
        """The operator does not get to quietly rewrite what they approved."""
        await _create(app, auth_headers, CHANGE_PATH, "change-spec")
        await _write(app, auth_headers, CHANGE_PATH, _complete_payload("change-spec"))

        # The real sequence, learned the hard way: a document cannot be proposed while its
        # exploration is open, so `close-exploration` comes first and `propose` is its own route
        # rather than a phase transition. Only `approved` goes through `/documents/phase`.
        #
        # `propose` also answers 200 with a list of *blocking findings* when the document is
        # incomplete, rather than erroring — so the status code alone proves nothing, and the empty
        # body is the real assertion.
        for route in ("close-exploration", "propose"):
            stepped = await app.post(
                f"{BASE}/documents/{route}", params={"path": CHANGE_PATH}, headers=auth_headers
            )
            assert stepped.status_code == 200, stepped.text
        assert stepped.json()["blocking"] == [], stepped.text
        moved = await app.post(
            f"{BASE}/documents/phase",
            params={"path": CHANGE_PATH, "to": "approved"},
            json={"reason": "test"},
            headers=auth_headers,
        )
        assert moved.status_code == 200, moved.text

        response = await _write(app, auth_headers, CHANGE_PATH, _payload("change-spec"))

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "document_approved"

    async def test_a_gated_document_records_a_proposal_rather_than_writing(
        self, app, auth_headers, tmp_path
    ):
        """Rigor is the document's property, not the caller's — including when the caller is the
        operator. They accept their own proposal, which is a record, not a bypass."""
        await _create(app, auth_headers, CHANGE_PATH, "change-spec")
        await _write(app, auth_headers, CHANGE_PATH, _payload("change-spec"))
        raised = await app.post(
            f"{BASE}/documents/{CHANGE_PATH}/rigor",
            json={"rigor": "contract"},
            headers=auth_headers,
        )
        assert raised.status_code == 200, raised.text
        before = (tmp_path / CHANGE_PATH).read_text(encoding="utf-8")

        response = await _write(
            app,
            auth_headers,
            CHANGE_PATH,
            _payload(
                "change-spec",
                requirements=[
                    {"key": "alpha", "statement": "It responds within 50ms", "modal": "MUST"}
                ],
            ),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert "proposals" in body and "identifiers" not in body
        assert (tmp_path / CHANGE_PATH).read_text(encoding="utf-8") == before

    async def test_the_route_refuses_a_credential_that_is_not_the_operators(
        self, app, auth_headers, run_headers
    ):
        await _create(app, auth_headers, CAP_PATH, "capability")

        response = await _write(app, run_headers, CAP_PATH, _payload("capability"))

        assert response.status_code == 401


@pytest.mark.asyncio
class TestAttribution:
    async def _events(self, path):
        async with async_session_factory() as session:
            document = await spec_lifecycle.get_document(session, "proj-test", path)
            rows = await session.execute(
                select(SpecDocumentEvent).where(SpecDocumentEvent.document_id == document.id)
            )
            return list(rows.scalars().all())

    async def test_an_operator_write_is_recorded_as_the_operators(self, app, auth_headers):
        await _create(app, auth_headers, CAP_PATH, "capability")
        await _write(app, auth_headers, CAP_PATH, _payload("capability"))

        submissions = [e for e in await self._events(CAP_PATH) if e.actor_kind == "operator"]
        assert submissions, "no operator-attributed event was recorded"
        assert all(event.run_id is None for event in submissions)

    async def test_an_agent_write_is_recorded_as_that_run(self, app, auth_headers, run_headers):
        await _create(app, auth_headers, CHANGE_PATH, "change-spec")

        response = await app.post(
            AGENT,
            json={"path": CHANGE_PATH, "document": _payload("change-spec")},
            headers=run_headers,
        )
        assert response.status_code == 200, response.text

        agent_events = [e for e in await self._events(CHANGE_PATH) if e.actor_kind == "agent"]
        assert agent_events
        assert any(event.run_id == "run-operator-authoring" for event in agent_events)

    async def test_an_identity_named_in_the_body_is_not_accepted(self, app, auth_headers):
        """`extra: forbid` means a body cannot even carry an actor to be ignored — the strongest
        form of "identity is never the caller's to assert"."""
        await _create(app, auth_headers, CAP_PATH, "capability")

        response = await app.put(
            f"{BASE}/documents/{CAP_PATH}/content",
            json={"document": _payload("capability"), "actor": "claude-1", "run_id": "run-x"},
            headers=auth_headers,
        )

        assert response.status_code == 422
        events = [e for e in await self._events(CAP_PATH) if e.actor_kind == "agent"]
        assert not events
