"""`the-copilot-catalog-tracks-the-cli` (F662, decision fix-D5).

A model the catalog no longer declares keeps working where it is already stored, and is flagged; a
newly chosen one is refused. Validate on write, tolerate at run. The worker half is
`test_worker.test_a_stored_model_the_catalog_no_longer_declares_still_runs`.
"""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Conversation
from hub.model_catalog import validate_overrides
from tests.test_agent_trigger import _await_background_run, _fake_pty

RETIRED = "claude-retired-9"  # a model id the claude catalog does not declare
BASE = "/api/v1/projects/proj-test"


def test_an_override_equal_to_the_stored_model_is_accepted_and_a_new_one_refused() -> None:
    accepted, rejection = validate_overrides(
        "copilot", {"model": "claude-opus-4.7"}, stored_model="claude-opus-4.7"
    )
    assert rejection is None and accepted == {"model": "claude-opus-4.7"}

    _, rejection = validate_overrides(
        "copilot", {"model": "kimi-k2.7-code"}, stored_model="claude-opus-4.7"
    )
    assert rejection is not None and "kimi-k2.7-code" in rejection.reason

    accepted, rejection = validate_overrides("copilot", {"model": "claude-haiku-5.5"})
    assert rejection is None and accepted == {"model": "claude-haiku-5.5"}


async def _trigger(app, auth_headers, overrides, conversation_id=None):
    body = {"agent": "stored", "message": "hi", "session_mode": "new", "overrides": overrides}
    if conversation_id:
        body["conversation_id"] = conversation_id
    fake_spawn = _fake_pty(
        ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']
    )
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(f"{BASE}/agent/trigger", json=body, headers=auth_headers)
            if response.status_code == 200:
                await _await_background_run()
    return response


@pytest.mark.asyncio
async def test_a_conversation_stored_on_a_dropped_model_keeps_working_and_is_flagged(
    app, auth_headers, bind_runner
) -> None:
    sync = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"stored": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("stored", cli="claude")
    first = await _trigger(app, auth_headers, {"effort": "high"})
    assert first.status_code == 200, first.text
    conversation_id = first.json()["conversation_id"]
    async with async_session_factory() as db:
        row = (
            await db.execute(select(Conversation).where(Conversation.id == conversation_id))
        ).scalar_one()
        row.runtime_overrides = {"model": RETIRED, "effort": "high"}  # stored before it was dropped
        await db.commit()

    listed = await app.get(f"{BASE}/agent/stored/conversations", headers=auth_headers)
    assert listed.json()[0]["model_unrecognised"] is True

    kept = await _trigger(app, auth_headers, {"model": RETIRED, "effort": "high"}, conversation_id)
    assert kept.status_code == 200, kept.text

    fresh = await _trigger(app, auth_headers, {"model": "claude-retired-8"}, conversation_id)
    assert fresh.status_code == 400, fresh.text
    assert "claude-retired-8" in fresh.json()["detail"]


@pytest.mark.asyncio
async def test_a_newly_set_checkpoint_model_must_be_declared(
    app, auth_headers, bind_runner
) -> None:
    runner = await app.post(
        f"{BASE}/runners",
        json={"name": "ckpt", "cli": "claude", "model": "claude-haiku-4-5-20251001"},
        headers=auth_headers,
    )
    assert runner.status_code == 201, runner.text

    refused = await app.put(
        f"{BASE}/settings",
        json={"checkpoint_runner_id": runner.json()["id"], "checkpoint_model": RETIRED},
        headers=auth_headers,
    )

    assert refused.status_code == 400, refused.text
    assert "checkpoint_model" in refused.json()["detail"] and RETIRED in refused.json()["detail"]
