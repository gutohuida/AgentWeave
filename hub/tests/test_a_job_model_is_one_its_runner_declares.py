"""F630: a manager job's model is one its runner's CLI declares, checked when it is set.

`PATCH /manager/jobs/{key} {"model": "gpt-9"}` answered 200 with a Claude runner and with none;
the next firing failed with the catalog's sentence. The same sentence now refuses the PATCH, as
`POST /runners` does, and a model with no runner to judge it is refused naming that.
"""

import pytest

from hub import manager

BASE = "/api/v1/projects/proj-test"
JOB = manager.DISTILLATION


async def _runner(app, auth_headers):
    resp = await app.post(
        f"{BASE}/runners", json={"name": "c", "cli": "claude"}, headers=auth_headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_an_undeclared_model_is_refused_and_nothing_changes(app, auth_headers):
    runner_id = await _runner(app, auth_headers)
    refused = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"runner_id": runner_id, "model": "gpt-9"},
        headers=auth_headers,
    )
    assert refused.status_code == 400, refused.text
    assert "'gpt-9' is not a model 'claude' declares" in refused.json()["detail"]
    job = (await app.get(f"{BASE}/manager/jobs", headers=auth_headers)).json()
    listed = next(j for j in (job["jobs"] if isinstance(job, dict) else job) if j["key"] == JOB)
    assert listed["model"] is None and listed["runner_id"] is None


@pytest.mark.asyncio
async def test_a_model_with_no_runner_is_refused(app, auth_headers):
    refused = await app.patch(
        f"{BASE}/manager/jobs/{JOB}", json={"model": "haiku"}, headers=auth_headers
    )
    assert refused.status_code == 400, refused.text
    assert "runner" in refused.json()["detail"]


@pytest.mark.asyncio
async def test_a_declared_model_is_accepted(app, auth_headers):
    runner_id = await _runner(app, auth_headers)
    ok = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"runner_id": runner_id, "model": "haiku"},
        headers=auth_headers,
    )
    assert ok.status_code == 200, ok.text
    cleared = await app.patch(
        f"{BASE}/manager/jobs/{JOB}", json={"model": None}, headers=auth_headers
    )
    assert cleared.status_code == 200, cleared.text
