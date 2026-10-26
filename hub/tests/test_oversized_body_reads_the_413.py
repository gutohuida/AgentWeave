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
    # Read the body first, as every Hub route does: answering an unread 64 KiB body lets the server
    # close while the client is still sending, a reset under load (WinError 10054) that is the echo
    # app's, not the middleware's.
    while True:
        message = await receive()
        if message["type"] != "http.request" or not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.fixture
def server_url():
    # The socket is bound here and handed to the server, never closed and re-bound: between a probe
    # closing a free port and uvicorn binding it, another process on a busy machine may take it.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    config = uvicorn.Config(
        ContentSizeLimitMiddleware(_echo, max_size=LIMIT),
        log_level="warning",
        lifespan="off",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    # A hang guard that ends as soon as the server is up, not an expected start time.
    deadline = time.monotonic() + 120
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=30)
    listener.close()


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


def _chunked_post(server_url: str, total: int, chunk: int = 16 * 1024):
    """POST *total* bytes with Transfer-Encoding: chunked, so no Content-Length is declared (F739)."""
    import http.client

    def body():
        sent = 0
        while sent < total:
            piece = min(chunk, total - sent)
            sent += piece
            yield b"x" * piece

    host, port = server_url.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=30)
    try:
        conn.request("POST", "/api/v1/anything", body=body(), encode_chunked=True)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def test_a_chunked_body_over_the_limit_is_refused_with_the_413(server_url):
    status, raw = _chunked_post(server_url, LIMIT * 4)

    assert status == 413
    detail = json.loads(raw)["detail"]
    assert "Request body too large" in detail and "64 KiB" in detail


def test_a_chunked_body_within_the_limit_still_passes(server_url):
    status, raw = _chunked_post(server_url, LIMIT // 2)

    assert status == 200 and raw == b"ok"
