"""Tests for codex_appserver.AppServerProcess against a real subprocess.

Spawns a tiny Python stand-in speaking the same NDJSON-over-stdio shape `codex app-server`
does, rather than mocking `asyncio.create_subprocess_exec` — real subprocess I/O is what
this class exists to get right (request/response correlation, notification delivery,
UTF-8 framing, and answering a server->client request), and a mock event loop wouldn't
exercise the OS pipe behavior that actually broke a live probe (see the module docstring's
UnicodeDecodeError note).
"""

import sys

import pytest

from hub.codex_appserver import AppServerError, AppServerProcess

_STAND_IN_SCRIPT = r"""
import sys, json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method")
    if method == "initialize":
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"ok": True}}), flush=True)
    elif method == "emit_unicode_notification":
        print(json.dumps({
            "jsonrpc": "2.0", "method": "server/notified",
            "params": {"text": "café ’ — done"},
        }), flush=True)
    elif method == "ask_client":
        print(json.dumps({
            "jsonrpc": "2.0", "id": 999, "method": "server/askApproval", "params": {},
        }), flush=True)
    elif msg.get("id") == 999 and "result" in msg:
        print(json.dumps({
            "jsonrpc": "2.0", "method": "server/gotAnswer", "params": msg["result"],
        }), flush=True)
    elif method == "slow_reply":
        import time
        time.sleep(2)
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {}}), flush=True)
    elif method == "shutdown":
        break
"""


@pytest.fixture
async def stand_in():
    session = await AppServerProcess.spawn([sys.executable, "-c", _STAND_IN_SCRIPT])
    yield session
    await session.close(force=True)


class TestAppServerProcess:
    @pytest.mark.asyncio
    async def test_request_receives_matching_response(self, stand_in):
        response = await stand_in.request("initialize", {})
        assert response["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_notification_is_decoded_as_utf8_not_locale_encoding(self, stand_in):
        """The exact bug a live probe hit: default subprocess text-mode decoding uses the
        platform locale encoding (CP-1252 on Windows), which mangles non-ASCII content
        Codex's own output routinely contains (smart quotes, em dashes)."""
        await stand_in.notify("emit_unicode_notification", {})
        notif = await stand_in.next_notification(timeout=5)
        assert notif["params"]["text"] == "café ’ — done"

    @pytest.mark.asyncio
    async def test_server_request_is_answerable_via_respond(self, stand_in):
        await stand_in.notify("ask_client", {})
        request = await stand_in.next_notification(timeout=5)
        assert request["method"] == "server/askApproval"
        assert "id" in request  # distinguishes a request from a plain notification

        await stand_in.respond(request["id"], {"decision": "decline"})

        confirmation = await stand_in.next_notification(timeout=5)
        assert confirmation["method"] == "server/gotAnswer"
        assert confirmation["params"] == {"decision": "decline"}

    @pytest.mark.asyncio
    async def test_request_times_out_if_never_answered(self, stand_in):
        with pytest.raises((AppServerError, TimeoutError, Exception)) as excinfo:
            await stand_in.request("never_answered_method", {}, timeout=0.3)
        # asyncio.TimeoutError (a subclass of TimeoutError since Python 3.11)
        assert "Timeout" in type(excinfo.value).__name__ or isinstance(
            excinfo.value, AppServerError
        )

    @pytest.mark.asyncio
    async def test_pending_request_fails_when_process_dies(self, stand_in):
        """Task 2.7: process death mid-turn must not hang a pending request forever."""
        import asyncio

        pending = asyncio.get_running_loop().create_task(
            stand_in.request("slow_reply", {}, timeout=30)
        )
        await asyncio.sleep(0.2)
        await stand_in.close(force=True)
        with pytest.raises(AppServerError):
            await pending

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, stand_in):
        await stand_in.close()
        await stand_in.close()  # must not raise
        assert not stand_in.is_running()

    @pytest.mark.asyncio
    async def test_pid_is_available(self, stand_in):
        assert stand_in.pid is not None
        assert stand_in.pid > 0
