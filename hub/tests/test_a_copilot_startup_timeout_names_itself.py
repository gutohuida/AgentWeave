"""F789: a Copilot ACP startup request that times out fails with an error that says what timed out.

`asyncio.wait_for` raises a bare `TimeoutError`, and `str(TimeoutError())` is `''`, so the run's
`error`, its `run_failed` event and the conversation said nothing under load. Two seams: the
process names the method and the limit; and the executor's pre-spawn failure record is never
empty even when some other transport raises a bare timeout.
"""

import asyncio
import sys

import pytest

from hub.api.v1.agent_trigger import _transport_failure_fields
from hub.codex_appserver import AppServerError
from hub.copilot_acp import ACPProcess, CopilotACPError


@pytest.mark.asyncio
async def test_a_request_that_is_never_answered_raises_an_error_naming_the_method():
    session = await ACPProcess.spawn(
        [
            sys.executable,
            "-u",
            "-c",
            "import sys\nsys.stdin.readline()\nimport time; time.sleep(30)",
        ]
    )
    try:
        with pytest.raises(AppServerError) as caught:
            await session.request("initialize", {"protocolVersion": 1}, timeout=0.1)
    finally:
        await session.close(force=True)

    exc = caught.value
    assert isinstance(exc, CopilotACPError)
    assert str(exc), "a timeout must not read as an empty error"
    assert "initialize" in str(exc)
    assert exc.method == "initialize"


def test_a_bare_timeout_still_yields_a_non_empty_failure_error():
    fields = _transport_failure_fields(asyncio.TimeoutError(), "conv-1")
    assert fields["error"], "the run_failed event's error must never be empty"
    assert fields["error"] == "TimeoutError"
