"""F793: an endpoint that was down must not delay the endpoint the operator saves next.

`trace_export` backs off per project in process memory; the settings route used to leave that
backoff alone, so a fixed endpoint waited up to five minutes with the screen showing no error.
"""

from __future__ import annotations

import pytest

from hub import trace_export

from .test_trace_seams import PROJECT, _Receiver, _worker_trace


async def _fail_against_a_dead_endpoint(app, auth_headers) -> None:
    dead = _Receiver()
    dead_url = dead.url
    dead.close()
    saved = await app.put(
        f"/api/v1/projects/{PROJECT}/traces/settings",
        json={"otlp_endpoint": dead_url, "export_enabled": True},
        headers=auth_headers,
    )
    assert saved.status_code == 200, saved.text
    await _worker_trace()
    assert await trace_export.push_once() == 0
    assert trace_export._retry_after.get(PROJECT)  # the pusher is now waiting


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["endpoint", "headers", "enable"])
async def test_saving_the_settings_is_tried_at_once(app, auth_headers, change):
    trace_export._retry_after.clear()
    trace_export._failures.clear()
    receiver = _Receiver()
    try:
        await _fail_against_a_dead_endpoint(app, auth_headers)
        if change == "enable":
            off = await app.put(
                f"/api/v1/projects/{PROJECT}/traces/settings",
                json={"otlp_endpoint": receiver.url, "export_enabled": False},
                headers=auth_headers,
            )
            assert off.status_code == 200, off.text
            trace_export._retry_after[PROJECT] = 10**12  # the wait the first PUT should have ended
            body = {"export_enabled": True}
        elif change == "headers":
            body = {"otlp_endpoint": receiver.url, "otlp_headers": {"X-Key": "v"}}
        else:
            body = {"otlp_endpoint": receiver.url}
        put = await app.put(
            f"/api/v1/projects/{PROJECT}/traces/settings", json=body, headers=auth_headers
        )
        assert put.status_code == 200, put.text
        assert PROJECT not in trace_export._retry_after
        assert PROJECT not in trace_export._failures
        await _worker_trace()
        assert await trace_export.push_once() >= 1
        assert receiver.posts
    finally:
        receiver.close()
        trace_export._retry_after.clear()
        trace_export._failures.clear()


@pytest.mark.asyncio
async def test_a_setting_that_does_not_touch_the_export_keeps_the_wait(app, auth_headers):
    trace_export._retry_after.clear()
    trace_export._failures.clear()
    try:
        await _fail_against_a_dead_endpoint(app, auth_headers)
        put = await app.put(
            f"/api/v1/projects/{PROJECT}/traces/settings",
            json={"record_reads": True},
            headers=auth_headers,
        )
        assert put.status_code == 200, put.text
        assert trace_export._retry_after.get(PROJECT)
    finally:
        trace_export._retry_after.clear()
        trace_export._failures.clear()
