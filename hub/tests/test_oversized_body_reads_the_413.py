"""F734: a client that sends its whole body before reading got a connection abort, not the 413.

`ContentSizeLimitMiddleware` answered from `content-length` without reading the body, and the
server then closed a socket with unread bytes in it: the peer sees a reset (`[WinError 10053]` from
Python's urllib), never the sentence F641 wrote. curl reads early responses, so F641 held for curl
only. Driven over a real socket with a real uvicorn server, as urllib sends.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request

import pytest
import uvicorn

from hub.main import ContentSizeLimitMiddleware

LIMIT = 64 * 1024


async def _echo(scope, receive, send):
    if scope["type"] != "http":
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.fixture
def server_url():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(
        ContentSizeLimitMiddleware(_echo, max_size=LIMIT),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


@pytest.mark.parametrize("size", [LIMIT + 1, 10 * 1024 * 1024 + 1, 40 * 1024 * 1024])
def test_a_client_that_sends_first_reads_the_413_sentence(server_url, size):
    request = urllib.request.Request(
        f"{server_url}/api/v1/anything", data=b"x" * size, method="POST"
    )

    with pytest.raises(urllib.error.HTTPError) as refused:
        urllib.request.urlopen(request, timeout=30)

    assert refused.value.code == 413
    detail = json.loads(refused.value.read())["detail"]
    assert "Request body too large" in detail and "64 KiB" in detail


def test_a_body_within_the_limit_still_passes(server_url):
    request = urllib.request.Request(f"{server_url}/x", data=b"x" * LIMIT, method="POST")
    with urllib.request.urlopen(request, timeout=30) as resp:
        assert resp.status == 200
