"""A project's checks are configured by the operator only (`approval-runs-the-projects-checks`)."""

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Project, Run

URL = "/api/v1/projects/proj-test/settings"
CHECKS = [
    {"name": "lint", "command": "ruff check .", "timeout_seconds": 120},
    {"name": "tests", "command": "py -3.11 -m pytest -q", "timeout_seconds": 900},
]


@pytest.mark.asyncio
async def test_the_operator_saves_and_reads_checks_in_order(app, auth_headers):
    saved = await app.put(URL, json={"checks": CHECKS}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["checks"] == CHECKS

    read = await app.get(URL, headers=auth_headers)
    assert read.json()["checks"] == CHECKS
    async with async_session_factory() as session:
        assert (await session.get(Project, "proj-test")).checks == CHECKS


@pytest.mark.asyncio
async def test_a_timeout_defaults_and_other_settings_are_untouched(app, auth_headers):
    before = (await app.get(URL, headers=auth_headers)).json()
    saved = await app.put(
        URL, json={"checks": [{"name": "t", "command": "pytest"}]}, headers=auth_headers
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["checks"] == [{"name": "t", "command": "pytest", "timeout_seconds": 900}]
    assert saved.json()["hop_budget"] == before["hop_budget"]


@pytest.mark.asyncio
async def test_no_checks_is_null_and_clearing_is_expressible(app, auth_headers):
    assert (await app.get(URL, headers=auth_headers)).json()["checks"] is None
    await app.put(URL, json={"checks": CHECKS}, headers=auth_headers)
    cleared = await app.put(URL, json={"checks": None}, headers=auth_headers)
    assert cleared.json()["checks"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "checks, field",
    [
        ([{"name": "a", "command": "x"}, {"name": "a", "command": "y"}], "unique"),
        ([{"name": "a", "command": "   "}], "command"),
        ([{"name": "", "command": "x"}], "name"),
        ([{"name": "a", "command": "x", "timeout_seconds": 5}], "timeout_seconds"),
        ([{"name": "a", "command": "x", "timeout_seconds": 3601}], "timeout_seconds"),
    ],
)
async def test_bad_checks_are_refused_naming_the_problem(app, auth_headers, checks, field):
    refused = await app.put(URL, json={"checks": checks}, headers=auth_headers)
    assert refused.status_code == 422, refused.text
    assert field in refused.text
    assert (await app.get(URL, headers=auth_headers)).json()["checks"] is None


@pytest.mark.asyncio
async def test_a_run_credential_cannot_change_checks(app, auth_headers):
    """No agent surface writes project settings; the operator route refuses a run's token."""
    async with async_session_factory() as session:
        session.add(
            Run(
                id="run-checks-agent",
                project_id="proj-test",
                agent="builder",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token("aw_run_checks-secret"),
            )
        )
        await session.commit()
    agent = {"Authorization": "Bearer aw_run_checks-secret"}
    refused = await app.put(URL, json={"checks": CHECKS}, headers=agent)
    assert refused.status_code in (401, 403), refused.text
    assert (await app.get(URL, headers=auth_headers)).json()["checks"] is None
