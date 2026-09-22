"""F117: `PATCH /agents/{name}` refuses a field it does not know instead of answering 200.

The body is an untyped `dict` (`NO_CONTRACT_BY_DESIGN` in `test_request_strictness.py` says why),
and until this change the handler honoured only the keys it recognised and ignored the rest. So
`{"permission_timeout_secondz": 5}` on an agent's *safety* settings answered 200 and changed
nothing. The one vocabulary check it had fired only for a session-synced configured agent, and
answered 409 about the agent's *name*.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Agent

PROJECT = "proj-test"


async def _create_hub_owned(app, auth_headers, name: str) -> None:
    runners = await app.get(f"/api/v1/projects/{PROJECT}/runners", headers=auth_headers)
    # Creating an agent checks its runner CLI is on PATH; CI runners have no `claude`.
    with patch("hub.launchability.shutil.which", return_value="/usr/bin/claude"):
        resp = await app.post(
            f"/api/v1/projects/{PROJECT}/agents",
            json={"name": name, "runner_id": runners.json()[0]["id"]},
            headers=auth_headers,
        )
    assert resp.status_code == 201, resp.text


async def _row(name: str) -> Agent:
    async with async_session_factory() as db:
        return (
            (await db.execute(select(Agent).where(Agent.project_id == PROJECT, Agent.name == name)))
            .scalars()
            .one()
        )


@pytest.mark.asyncio
async def test_a_misspelled_setting_on_a_hub_owned_agent_is_refused(app, auth_headers):
    """The finding's own body, on the kind of agent the UI creates."""
    await _create_hub_owned(app, auth_headers, "asker")

    resp = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/asker",
        json={"permission_timeout_secondz": 5},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    assert "permission_timeout_secondz" in resp.json()["detail"]
    assert (await _row("asker")).permission_timeout_seconds is None


@pytest.mark.asyncio
async def test_a_body_with_one_unknown_field_applies_none_of_it(app, auth_headers):
    """Refused whole: applying the half that was spelled right would leave the operator believing
    the half that was not had been saved too."""
    await _create_hub_owned(app, auth_headers, "mixed")

    resp = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/mixed",
        json={"question_timeout_seconds": 300, "permission_timeout_secondz": 5},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    assert (await _row("mixed")).question_timeout_seconds is None


@pytest.mark.asyncio
async def test_a_configured_agent_is_told_about_the_field_not_its_name(app, auth_headers):
    """The old guard answered 409 "reserved for a configured agent" to a typo; the operator needs
    to hear which field was wrong."""
    sync = await app.post(
        f"/api/v1/projects/{PROJECT}/session/sync",
        json={"data": {"agents": {"synced": {}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text

    resp = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/synced",
        json={"question_timeout_secondz": 5},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    assert "question_timeout_secondz" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_every_field_the_ui_sends_is_still_accepted(app, auth_headers):
    """The keys `hub/ui/src/api/{agents,charters,runners}.ts` send, in one body, so a vocabulary
    that forgot one of them fails here rather than in the settings panel."""
    await _create_hub_owned(app, auth_headers, "settled")

    resp = await app.patch(
        f"/api/v1/projects/{PROJECT}/agents/settled",
        json={
            "description": "d",
            "permission_timeout_seconds": 60,
            "question_timeout_seconds": 300,
            "default_permission_mode": "acceptEdits",
            "checkpoint_mode": "off",
            "can_read_checkpoints": True,
            "can_recall": False,
            "can_accept_evidence": False,
            "charter_id": None,
        },
        headers=auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert (await _row("settled")).question_timeout_seconds == 300
