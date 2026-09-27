"""`a-document-says-how-it-will-be-built-and-approval-starts-it`.

This file grows with the change (design.md's rounds; `openspec/changes/
a-document-says-how-it-will-be-built-and-approval-starts-it/tasks.md`). This slice is task 1.1
only: `delivery`'s shape at save time. Propose- and approve-time behaviour (1.2 onward) needs
completeness and `set_phase` work this slice does not touch yet.
"""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.spec_payload import SCHEMA_VERSION, PayloadError, payload_to_dict, validate_payload

BASE = "/api/v1/projects/proj-test/project"
AGENT = "/api/v1/agent-actions/spec/documents"


@pytest.fixture
async def run_headers():
    token = "aw_run_delivery-secret"
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-delivery",
                project_id="proj-test",
                agent="claude-1",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides):
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Demo",
        "summary": "Original summary",
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Shape (validate_payload)
# ---------------------------------------------------------------------------


def test_delivery_absent_validates():
    payload = validate_payload(_payload())
    assert payload.delivery is None


def test_a_flow_delivery_validates():
    payload = validate_payload(
        _payload(
            delivery={
                "mode": "flow",
                "agent": "dev",
                "stop_when_queue_empties": True,
                "cron": "*/5 * * * *",
            }
        )
    )
    assert payload.delivery is not None
    assert payload.delivery.mode == "flow"
    assert payload.delivery.agent == "dev"


def test_a_none_delivery_validates():
    payload = validate_payload(_payload(delivery={"mode": "none"}))
    assert payload.delivery.mode == "none"


def test_an_unknown_mode_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "maybe"}))
    assert "delivery.mode" in exc.value.field


def test_an_unparseable_cron_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "cron": "not a cron"}))
    assert exc.value.field == "delivery.cron"


def test_a_stop_at_with_no_timezone_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "stop_at": "2026-10-01T00:00:00"}))
    assert exc.value.field == "delivery.stop_at"


def test_a_stop_at_with_a_timezone_is_accepted():
    payload = validate_payload(
        _payload(delivery={"mode": "flow", "stop_at": "2026-10-01T00:00:00+01:00"})
    )
    assert payload.delivery.stop_at == "2026-10-01T00:00:00+01:00"


def test_a_cron_over_128_characters_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "cron": "*/5 * * * *" + " " * 120}))
    assert "delivery.cron" in exc.value.field


def test_an_agent_over_32_characters_is_refused():
    with pytest.raises(PayloadError) as exc:
        validate_payload(_payload(delivery={"mode": "flow", "agent": "a" * 33}))
    assert "delivery.agent" in exc.value.field


# ---------------------------------------------------------------------------
# `payload_to_dict` — no `delivery: null` for a document that never declared one (R3)
# ---------------------------------------------------------------------------


def test_payload_to_dict_drops_an_absent_delivery():
    payload = validate_payload(_payload())
    data = payload_to_dict(payload)
    assert "delivery" not in data


def test_payload_to_dict_keeps_a_present_delivery():
    payload = validate_payload(_payload(delivery={"mode": "none"}))
    data = payload_to_dict(payload)
    assert data["delivery"] == {
        "mode": "none",
        "agent": None,
        "stop_when_queue_empties": False,
        "stop_at": None,
        "cron": "*/5 * * * *",
    }


# ---------------------------------------------------------------------------
# End to end: a `contract` document written without the `delivery` key answers an unchanged
# resubmission with `unchanged` containing `metadata` and zero proposals — the regression D1
# guards against (a stored-null `delivery` would otherwise diff against an absent one).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unchanged_resubmission_with_no_delivery_key_proposes_nothing(
    app, auth_headers, run_headers
):
    path = "spec/changes/delivery-demo/spec.html"
    document = _payload(
        requirements=[{"key": "alpha", "statement": "It responds within 200ms", "modal": "MUST"}]
    )
    await app.post(f"{BASE}/documents", json={"path": path, "title": "Demo"}, headers=auth_headers)
    write = await app.post(AGENT, json={"path": path, "document": document}, headers=run_headers)
    assert write.status_code == 200, write.text
    rigor = await app.post(
        f"{BASE}/documents/{path}/rigor", json={"rigor": "gate"}, headers=auth_headers
    )
    assert rigor.status_code == 200, rigor.text

    response = await app.post(AGENT, json={"path": path, "document": document}, headers=run_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["proposals"] == []
    assert "metadata" in body["unchanged"]
