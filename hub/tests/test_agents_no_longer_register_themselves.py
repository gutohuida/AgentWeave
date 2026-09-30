"""Self-registration leaves the product (`agents-no-longer-register-themselves`; F111, F136, F3).

The operator decided on 2026-08-29 that an agent does not register itself: every agent is made by
the operator or by a governed agent request, and the Hub starts it. So the register route goes, and
with it the watchdog-era columns that described how a self-registered agent was contacted
(`contact_mode`, `self_registered`, `mcp_endpoint`, `spawn_cmd`) and the launchability exemption
that told an unbound self-registered agent to install a binary named after itself.
"""

from pathlib import Path

import pytest

import hub.launchability as launchability


@pytest.mark.asyncio
async def test_the_register_route_is_gone(app, auth_headers):
    response = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "selfreg", "contact_mode": "poll"},
        headers=auth_headers,
    )

    assert response.status_code in (404, 405), response.text


@pytest.mark.asyncio
async def test_an_agent_with_no_runner_is_reported_unbound_everywhere(app, auth_headers, add_agent):
    """F136's population is gone, so the one verdict left must hold on every surface F111 named:
    the probe, and the queue's waiting reason on a trigger. Neither may name a CLI after the agent.
    """
    await add_agent("lonely")

    probe = await app.get("/api/v1/projects/proj-test/agents/launchability", headers=auth_headers)
    assert probe.status_code == 200, probe.text
    verdict = probe.json()["agents"]["lonely"]
    assert verdict["runner"] == "unbound"
    assert verdict["runnable"] is False
    assert "Runner CLI 'lonely'" not in (verdict["reason"] or "")

    triggered = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "lonely", "message": "hello", "session_mode": "new"},
        headers=auth_headers,
    )
    assert triggered.status_code == 200, triggered.text
    assert triggered.json()["status"] == "queued"
    assert "No runner is bound" in triggered.json()["waiting_reason"]
    assert "Runner CLI 'lonely'" not in triggered.json()["waiting_reason"]


def test_launchability_exempts_no_agent_by_origin():
    """What stops the exemption returning once the column is gone: the guard has nothing to read,
    and this names the word so a reintroduction is caught in review, not by an operator."""
    source = Path(launchability.__file__).read_text(encoding="utf-8")

    assert "self_registered" not in source


@pytest.mark.asyncio
async def test_a_created_agent_is_not_described_in_watchdog_terms(app, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "hub.api.v1.agents.probe_agent",
        lambda name, config: {
            "runner": config["runner"],
            "present": True,
            "authorized": True,
            "runnable": True,
            "reason": None,
        },
    )
    runners = (await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)).json()

    created = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": "made", "runner_id": runners[0]["id"]},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    # The agent's full record is what `PATCH /agents/{name}` answers with; there is no GET for one.
    detail = await app.patch(
        "/api/v1/projects/proj-test/agents/made",
        json={"description": "made by the operator"},
        headers=auth_headers,
    )
    assert detail.status_code == 200, detail.text
    listed = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    [summary] = [a for a in listed.json() if a["name"] == "made"]

    for body in (created.json(), detail.json(), summary):
        for field in ("contact_mode", "self_registered", "mcp_endpoint", "spawn_cmd", "liveness"):
            assert field not in body, (field, body)


@pytest.mark.asyncio
async def test_patching_a_contact_mode_is_refused_as_an_unknown_field(app, auth_headers, add_agent):
    await add_agent("patched")

    response = await app.patch(
        "/api/v1/projects/proj-test/agents/patched",
        json={"contact_mode": "poll"},
        headers=auth_headers,
    )

    assert response.status_code == 400, response.text
    unknown, valid = response.json()["detail"].split(". Valid: ")
    assert unknown == "Unknown agent field(s): contact_mode"
    for field in ("contact_mode", "mcp_endpoint", "spawn_cmd"):
        assert field not in valid.split(", "), valid
