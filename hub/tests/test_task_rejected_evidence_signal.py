"""Rejected evidence at a requirement's current digest reads identically to "never attempted".

`requirement_coverage._state` has no precedence level for "tried and rejected" — evidence that
exists, is current, and was rejected falls through every check to `in_progress`, the same state as
a requirement with a task and no evidence at all. Approving the task that serves it ("approving is
what merges it") gave no warning that the evidence backing it had actually been turned down. This
covers the signal `TaskResponse.requirement_links[]` adds to close that gap: `has_rejected_evidence`,
`rejected_evidence_count`, `latest_rejection_reason`. `requirement_gate.py`'s blocking behaviour is
untouched — this is visibility only.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Run
from hub.spec_payload import SCHEMA_VERSION

BASE = "/api/v1/projects/proj-test/project"
TASKS = "/api/v1/projects/proj-test/tasks"
SUBMIT = "/api/v1/agent-actions/spec/documents"
AGENT_EVIDENCE = "/api/v1/agent-actions/spec/evidence"
PATH = "spec/changes/rejected-evidence-demo/spec.html"

ALPHA = {"key": "alpha", "statement": "It lists what is due today", "modal": "MUST"}


@pytest.fixture
async def builder():
    async with async_session_factory() as session:
        session.add(Agent(id="ag-red", project_id="proj-test", name="builder"))
        session.add(
            Run(
                id="run-red",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_red-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_red-secret"}


async def _document(app, auth_headers, run_headers):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Rejected evidence demo"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    saved = await app.post(
        SUBMIT,
        json={
            "path": PATH,
            "document": {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "title": "Rejected evidence demo",
                "requirements": [ALPHA],
            },
        },
        headers=run_headers,
    )
    assert saved.status_code == 200, saved.text


def _link(task_json):
    links = task_json["requirement_links"]
    assert len(links) == 1, links
    return links[0]


@pytest.mark.asyncio
async def test_a_rejected_current_digest_evidence_is_named_on_the_task(
    app, auth_headers, builder
):
    await _document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]

    recorded = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "ran it"},
        headers=builder,
    )
    assert recorded.status_code == 201, recorded.text

    decided = await app.post(
        f"{BASE}/spec/evidence/{recorded.json()['id']}/decision",
        json={"decision": "rejected", "reason": "tests never actually exercise FR-1"},
        headers=auth_headers,
    )
    assert decided.status_code == 200, decided.text

    fetched = await app.get(f"{TASKS}/{task_id}", headers=auth_headers)
    assert fetched.status_code == 200, fetched.text
    link = _link(fetched.json())
    assert link["has_rejected_evidence"] is True
    assert link["rejected_evidence_count"] == 1
    assert link["latest_rejection_reason"] == "tests never actually exercise FR-1"

    listed = await app.get(TASKS, headers=auth_headers)
    assert listed.status_code == 200, listed.text
    [listed_task] = [t for t in listed.json() if t["id"] == task_id]
    assert _link(listed_task)["has_rejected_evidence"] is True


@pytest.mark.asyncio
async def test_a_requirement_nobody_has_attempted_carries_no_rejection_signal(
    app, auth_headers, builder
):
    await _document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    assert created.status_code == 201, created.text

    fetched = await app.get(f"{TASKS}/{created.json()['id']}", headers=auth_headers)
    link = _link(fetched.json())
    assert link["has_rejected_evidence"] is False
    assert link["rejected_evidence_count"] == 0
    assert link["latest_rejection_reason"] is None


@pytest.mark.asyncio
async def test_a_later_acceptance_does_not_erase_the_earlier_rejection_signal(
    app, auth_headers, builder
):
    """A second, accepted submission does not un-reject the first. Coverage itself moves to
    `verified` — the requirement is now demonstrated — but the fact that one attempt was turned
    down is still true and still worth an approver knowing, so the count still names it."""
    await _document(app, auth_headers, builder)
    created = await app.post(
        TASKS, json={"title": "Build it", "requirement_ids": ["FR-1"]}, headers=auth_headers
    )
    task_id = created.json()["id"]

    first = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "first attempt"},
        headers=builder,
    )
    await app.post(
        f"{BASE}/spec/evidence/{first.json()['id']}/decision",
        json={"decision": "rejected", "reason": "not enough"},
        headers=auth_headers,
    )

    second = await app.post(
        AGENT_EVIDENCE,
        json={"identifier": "FR-1", "kind": "test_result", "summary": "second attempt"},
        headers=builder,
    )
    await app.post(
        f"{BASE}/spec/evidence/{second.json()['id']}/decision",
        json={"decision": "accepted"},
        headers=auth_headers,
    )

    fetched = await app.get(f"{TASKS}/{task_id}", headers=auth_headers)
    link = _link(fetched.json())
    # The rejected row is still there and still rejected — coverage does not erase history — but
    # the signal is about whether *this* task's approval should be wary, and an accepted piece of
    # current-digest evidence answers that. The count still names the rejected row.
    assert link["rejected_evidence_count"] == 1
    assert link["has_rejected_evidence"] is True
