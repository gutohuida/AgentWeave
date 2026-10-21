"""F626: a vault job that is on with no runner says, in the Manager activity, that it did nothing.

The upload, the proposal and the filed report each started the job in the background, which
returned silently on "no runner": no firing, an empty activity list, nothing on the page. Only
the on-demand Distil route said why. Each now records a `failed` firing naming the remedy.
"""

import asyncio
from pathlib import Path

import pytest

from hub import distillation, manager, vault, vault_reports, vault_spec_check

BASE = "/api/v1/projects/proj-test"


async def _enable_without_runner(app, auth_headers, key):
    resp = await app.patch(
        f"{BASE}/manager/jobs/{key}", json={"enabled": True}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["runner_id"] is None


async def _firings(app, auth_headers):
    resp = await app.get(f"{BASE}/manager/activity", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["firings"]


async def _one_firing(app, auth_headers, key):
    for _ in range(50):
        firings = [f for f in await _firings(app, auth_headers) if f["job"] == key]
        if firings:
            break
        await asyncio.sleep(0.1)
    assert len(firings) == 1, firings
    assert firings[0]["outcome"] == "failed"
    assert "no runner" in firings[0]["detail"] and "Manager page" in firings[0]["detail"]


@pytest.mark.asyncio
async def test_an_upload_with_distillation_on_and_no_runner_says_so(app, auth_headers):
    await _enable_without_runner(app, auth_headers, manager.DISTILLATION)
    uploaded = await app.post(
        f"{BASE}/vault/sources",
        json={"name": "Limits", "type": "note", "content": "The limit is 300 euros."},
        headers=auth_headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    await _one_firing(app, auth_headers, manager.DISTILLATION)


@pytest.mark.asyncio
async def test_a_spec_check_with_no_runner_says_so(app, auth_headers):
    await _enable_without_runner(app, auth_headers, manager.SPEC_VAULT_CHECK)
    created = await app.post(
        f"{BASE}/project/documents", json={"title": "Checked"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    await vault_spec_check.check_in_background(
        "proj-test", created.json()["path"], trigger="document_proposed"
    )
    await _one_firing(app, auth_headers, manager.SPEC_VAULT_CHECK)


@pytest.mark.asyncio
async def test_a_report_review_with_no_runner_says_so(app, auth_headers, tmp_path):
    await _enable_without_runner(app, auth_headers, manager.REPORTS)
    source = await app.post(
        f"{BASE}/vault/sources",
        json={"name": "Limits", "type": "note", "content": "The limit is 300 euros."},
        headers=auth_headers,
    )
    assert source.status_code == 201, source.text
    settings = await app.get(f"{BASE}/vault/settings", headers=auth_headers)
    private = Path(settings.json()["effective_private_location"])
    report = vault.add_report(
        tmp_path,
        private,
        entry_id=source.json()["id"],
        message="This looks wrong.",
        reporter={"agent": "helper", "run_id": "run-1"},
    )
    await vault_reports.review_in_background("proj-test", report["id"])
    await _one_firing(app, auth_headers, manager.REPORTS)
    # F801: the sentence says what becomes of the report.
    (firing,) = [f for f in await _firings(app, auth_headers) if f["job"] == manager.REPORTS]
    assert "stays pending" in firing["detail"] and "Look into it" in firing["detail"]


@pytest.mark.asyncio
async def test_a_job_that_is_off_records_nothing(app, auth_headers):
    await distillation.distil_in_background(
        "proj-test", "src-0123456789ab", trigger="source_uploaded"
    )
    assert await _firings(app, auth_headers) == []
