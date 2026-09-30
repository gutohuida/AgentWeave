"""`copilot_acp.ACPProcess` against a real stand-in process (task 6.2, design D3/D12/D17).

Modelled on `test_codex_appserver_process.py`: real subprocesses on real pipes, because what is
under test is the stdio framing, the read loop's delivery order, and what happens when the child
dies or is closed -- none of which a fake can demonstrate. The stand-in speaks newline-delimited
JSON-RPC the way `copilot.exe --acp --stdio` does (`evidence/acp4-turn-mcp-shell-1.0.88.log`):
the `session/prompt` result arrives *after* that turn's `session/update` notifications, and the
agent asks the client things (`session/request_permission`) mid-request.
"""

import asyncio
import os
import subprocess
import sys
import time

import pytest

import hub.copilot_acp as copilot_acp
from hub.codex_appserver import AppServerError
from hub.copilot_acp import ACPProcess, CopilotACPError

pytestmark = pytest.mark.asyncio

# The stand-in's own helpers, prepended to every script: read one JSON-RPC line, write one.
_PRELUDE = (
    "import json, sys\n"
    "def recv():\n"
    "    line = sys.stdin.readline()\n"
    "    return json.loads(line) if line else None\n"
    "def send(msg):\n"
    "    sys.stdout.write(json.dumps(msg) + '\\n')\n"
    "    sys.stdout.flush()\n"
)


async def spawn_child(script, **handlers) -> ACPProcess:
    return await ACPProcess.spawn([sys.executable, "-u", "-c", _PRELUDE + script], **handlers)


async def test_a_request_resolves_to_its_result():
    session = await spawn_child(
        "msg = recv()\n"
        "send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'echo': msg['method']}})\n"
        "recv()\n"
    )
    try:
        result = await session.request("initialize", {"protocolVersion": 1}, timeout=15)
    finally:
        await session.close()
    assert result == {"echo": "initialize"}, "request() returns the result, not the envelope"


async def test_notifications_are_delivered_in_order_while_the_request_is_pending():
    """`session/prompt`'s shape: its notifications come first, its result last. Each one must
    reach the handler before the awaited result returns, in wire order."""
    seen = []
    order = []

    async def on_notification(method, params):
        seen.append((method, params["n"]))
        order.append("notification")

    session = await spawn_child(
        "msg = recv()\n"
        "for n in range(3):\n"
        "    send({'jsonrpc': '2.0', 'method': 'session/update', 'params': {'n': n}})\n"
        "send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'stopReason': 'end_turn'}})\n"
        "recv()\n",
        on_notification=on_notification,
    )
    try:
        result = await session.request("session/prompt", {"prompt": []}, timeout=None)
        order.append("result")
    finally:
        await session.close()

    assert result == {"stopReason": "end_turn"}
    assert seen == [("session/update", 0), ("session/update", 1), ("session/update", 2)]
    assert order == ["notification", "notification", "notification", "result"], order


async def test_an_agent_request_is_answered_by_the_handler_while_a_request_is_pending():
    """The permission round trip: the stand-in asks mid-prompt, reads our answer, and reports
    what it received in its own result, so the answer's wire shape is what is asserted."""
    asked = []

    async def on_server_request(method, params):
        asked.append((method, params))
        return {"outcome": {"outcome": "selected", "optionId": "reject_once"}}

    session = await spawn_child(
        "msg = recv()\n"
        "send({'jsonrpc': '2.0', 'id': 0, 'method': 'session/request_permission',\n"
        "      'params': {'toolCall': {'kind': 'execute'}}})\n"
        "answer = recv()\n"
        "send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'answer': answer}})\n"
        "recv()\n",
        on_server_request=on_server_request,
    )
    try:
        result = await session.request("session/prompt", {"prompt": []}, timeout=15)
    finally:
        await session.close()

    assert asked == [("session/request_permission", {"toolCall": {"kind": "execute"}})]
    assert result["answer"] == {
        "jsonrpc": "2.0",
        "id": 0,
        "result": {"outcome": {"outcome": "selected", "optionId": "reject_once"}},
    }


async def test_an_agent_request_with_no_handler_is_answered_with_an_error_not_silence():
    """Every agent->client request gets an answer: silence would hang the turn (D8)."""
    session = await spawn_child(
        "msg = recv()\n"
        "send({'jsonrpc': '2.0', 'id': 5, 'method': 'fs/read_text_file', 'params': {}})\n"
        "answer = recv()\n"
        "send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {'answer': answer}})\n"
        "recv()\n"
    )
    try:
        result = await session.request("session/prompt", {}, timeout=15)
    finally:
        await session.close()
    assert result["answer"]["id"] == 5
    assert result["answer"]["error"]["code"] == -32601


async def test_a_json_rpc_error_response_raises_copilot_acp_error_with_code_and_data():
    """D12: an error response is raised, carrying `.code` (D7 reads `-32002` from it) and
    `.data` (slice 4's quota fields), and it is an `AppServerError` for the executor's except."""
    session = await spawn_child(
        "msg = recv()\n"
        "send({'jsonrpc': '2.0', 'id': msg['id'], 'error': {'code': -32002,\n"
        "      'message': 'Resource not found', 'data': {'uri': 'Session s-1 not found'}}})\n"
        "recv()\n"
    )
    try:
        with pytest.raises(CopilotACPError) as caught:
            await session.request("session/load", {"sessionId": "s-1"}, timeout=15)
    finally:
        await session.close()

    error = caught.value
    assert isinstance(error, AppServerError)
    assert error.code == -32002
    assert error.data == {"uri": "Session s-1 not found"}
    assert "Resource not found" in str(error)


async def test_process_exit_before_the_response_raises_app_server_error_with_its_facts():
    session = await spawn_child(
        "recv(); sys.stderr.write('copilot: auth token rejected\\n'); sys.stderr.flush(); "
        "sys.exit(9)"
    )
    try:
        with pytest.raises(AppServerError) as caught:
            await session.request("session/prompt", {}, timeout=15)
    finally:
        await session.close()

    error = caught.value
    assert not isinstance(error, CopilotACPError), "a death carries no JSON-RPC code"
    assert error.exit_code == 9
    assert error.method == "session/prompt"
    assert "auth token rejected" in error.stderr_tail


def _alive(pid: int) -> bool:
    if os.name == "nt":
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in listing
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_close_ends_the_process_tree_through_terminate_process_tree(monkeypatch):
    """D17: `copilot.exe` runs its shells as children, so `close()` ends the whole tree, on every
    exit -- not a single-process kill that would leave `powershell.exe` behind. The stand-in
    starts a grandchild (the shell's place) and reports its pid; after `close()` both are gone,
    and the tree kill is what was called."""
    real = copilot_acp.terminate_process_tree
    calls = []

    def recording(pid, force=True):
        calls.append((pid, force))
        real(pid, force)

    monkeypatch.setattr(copilot_acp, "terminate_process_tree", recording)
    grandchild = []

    async def on_notification(method, params):
        grandchild.append(params["pid"])

    session = await spawn_child(
        "import subprocess\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "msg = recv()\n"
        "send({'jsonrpc': '2.0', 'method': 'shell/started', 'params': {'pid': child.pid}})\n"
        "send({'jsonrpc': '2.0', 'id': msg['id'], 'result': {}})\n"
        "recv()\n",
        on_notification=on_notification,
    )
    await session.request("session/new", {}, timeout=15)
    assert grandchild and _alive(grandchild[0]), "the stand-in's grandchild must be running"
    pid = session.pid

    await session.close(force=True)

    assert calls == [(pid, True)], "close() must end the tree through terminate_process_tree"
    assert session.returncode is not None
    deadline = time.monotonic() + 10
    while _alive(grandchild[0]) and time.monotonic() < deadline:
        await asyncio.sleep(0.1)
    assert not _alive(grandchild[0]), "the grandchild must not survive its parent's close()"


async def test_close_is_idempotent_and_fails_a_pending_request():
    session = await spawn_child("recv(); recv()")
    pending = asyncio.ensure_future(session.request("session/prompt", {}, timeout=None))
    await asyncio.sleep(0.2)
    await session.close()
    await session.close()
    with pytest.raises(AppServerError):
        await asyncio.wait_for(pending, timeout=5)
