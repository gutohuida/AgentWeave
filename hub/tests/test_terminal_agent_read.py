"""The conversation's agent reads its shells (`a-terminal-in-the-side-panel`, FR-12, TSP-4).

`ac-agent-reads`: a conversation with two open shells, one of them ended, and another
conversation with its own agent. The first agent's read returns both shells with name, directory,
running state and their last lines (at most 500 each); the second's returns none of them; and
neither can send input. Each agent is a real run calling with its own run credential, as the
`read_shells` tool does -- identity comes from the credential, never from a parameter.

The tab's footer saying the agent can read these shells is the Terminal tab's (TSP-3).
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from hub import mcp_server
from hub.agent_auth import hash_run_token, mint_run_token
from hub.api.v1.terminal import agent_router
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.terminal.sessions import AGENT_READ_LINES, registry
from tests._routing import iter_api_routes
from tests.test_changes_route import P, seed
from tests.test_terminal import (
    HOST,
    IS_WINDOWS,
    LOCAL,
    TERMINALS,
    Socket,
    _real_shell,
    _say,
    attach_path,
    open_shell,
)
from tests.test_terminal import _fresh_registry as _fresh
from tests.test_terminal import repo as _repo
from tests.test_terminal import spawned as _spawned

# Fixtures, used by name: test_terminal's clean registry around every test, its repository and
# its fake shells.
_fresh_registry, repo, spawned = _fresh, _repo, _spawned

READ = "/api/v1/agent-actions/terminal/shells"


async def _run_in(conversation: str, agent: str) -> dict:
    """A running run of *agent* in *conversation*, and the headers its tool connection sends."""
    token = mint_run_token()
    async with async_session_factory() as db:
        db.add(
            Run(
                id=f"run-{conversation}",
                project_id=P,
                agent=agent,
                status="running",
                conversation_id=conversation,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


async def _two_conversations(app, auth_headers):
    """conv-ch (agent `worker`) with two shells, the second ended; conv-two (agent `other`)."""
    await seed()
    await seed(agent="other", conv="conv-two")
    first = (await open_shell(app, auth_headers)).json()
    second = (await open_shell(app, auth_headers, shell="wsl:Ubuntu")).json()
    a, b = registry.get(first["id"]), registry.get(second["id"])
    a._on_output("".join(f"\x1b[32mone {i}\x1b[0m\r\n" for i in range(1, 801)))
    b._on_output("PS> pytest\r\n3 passed\r\n")
    b._on_exit(0)
    return a, b


@pytest.mark.asyncio
async def test_ac_agent_reads_its_conversations_shells_and_no_other(
    app, auth_headers, repo, spawned
):
    a, b = await _two_conversations(app, auth_headers)
    mine = await _run_in("conv-ch", "worker")
    theirs = await _run_in("conv-two", "other")

    read = await app.get(READ, headers=mine)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["conversation_id"] == "conv-ch" and body["max_lines"] == AGENT_READ_LINES == 500
    first, second = body["shells"]
    assert first["name"] == "Windows PowerShell" and second["name"] == "Ubuntu (WSL)"
    assert first["directory"] == a.directory and second["directory"] == b.directory
    assert second["directory"].startswith("/mnt/")
    assert first["running"] is True and first["exit_code"] is None
    assert second["running"] is False and second["exit_code"] == 0
    # The last 500 lines, as plain text: escape sequences gone.
    assert len(first["lines"]) == 500
    assert first["lines"][0] == "one 301" and first["lines"][-1] == "one 800"
    assert second["lines"] == ["PS> pytest", "3 passed"]
    # Nothing in the answer addresses a shell: no id a later call could act on.
    assert all("id" not in shell for shell in body["shells"])

    other = await app.get(READ, headers=theirs)
    assert other.status_code == 200, other.text
    assert other.json()["conversation_id"] == "conv-two" and other.json()["shells"] == []


@pytest.mark.asyncio
async def test_the_read_needs_a_run_credential_and_names_no_conversation(
    app, auth_headers, repo, spawned
):
    await _two_conversations(app, auth_headers)
    # The operator's key is not a run credential.
    assert (await app.get(READ, headers=auth_headers)).status_code == 401
    # A conversation named in the query is not how the scope is chosen.
    theirs = await _run_in("conv-two", "other")
    named = await app.get(READ, params={"conversation_id": "conv-ch"}, headers=theirs)
    assert named.status_code == 200 and named.json()["shells"] == []


@pytest.mark.asyncio
async def test_no_input_path_from_the_agent(app, auth_headers, repo, spawned):
    """Neither the tool nor the run's credential can type into, start or end a shell."""
    a, _b = await _two_conversations(app, auth_headers)
    mine = await _run_in("conv-ch", "worker")

    # The tool takes nothing, and calls only the read.
    assert list(inspect.signature(mcp_server.read_shells).parameters) == []
    calls = []
    original = mcp_server._hub_request
    mcp_server._hub_request = lambda method, path, *a, **k: calls.append((method, path)) or {}
    try:
        mcp_server.read_shells()
    finally:
        mcp_server._hub_request = original
    assert calls == [("GET", "/terminal/shells")]

    # The agent plane has one terminal route, and it is a read.
    # Its router holds that one route, sockets included; and the app serves nothing else under it.
    assert [(r.path, getattr(r, "methods", None)) for r in agent_router.routes] == [
        ("/agent-actions/terminal/shells", {"GET"})
    ]
    served = {
        (method, path)
        for path, route in iter_api_routes(app._transport.app)
        if path.startswith("/api/v1/agent-actions/terminal")
        for method in route.methods
    }
    assert served == {("GET", READ)}, served

    # The operator's routes refuse the run's credential: no start, no end, no restart, no attach.
    run_local = {**mine, **LOCAL}
    shells = len(registry.all())
    opened = await app.post(TERMINALS, json={"shell": "powershell"}, headers=run_local)
    assert opened.status_code in (401, 403), opened.text
    ended = await app.delete(f"{TERMINALS}/{a.id}", headers=run_local)
    assert ended.status_code in (401, 403), ended.text
    restarted = await app.post(f"{TERMINALS}/{a.id}/restart", headers=run_local)
    assert restarted.status_code in (401, 403), restarted.text
    assert len(registry.all()) == shells and registry.get(a.id) is a and a.running

    typed = []
    a.write = lambda data: typed.append(data)  # type: ignore[method-assign]
    sock = Socket(app, attach_path(a.id), {"Host": HOST, "Origin": LOCAL["Origin"], **mine})
    assert await sock.handshake() != "websocket.accept"
    await sock.close()
    assert typed == []


@pytest.mark.asyncio
@pytest.mark.timeout(120)
async def test_a_real_shell_reads_what_it_printed(app, auth_headers, repo, monkeypatch):
    """End to end on this machine's own shell: the operator types, the agent reads it back."""
    await seed()
    option, shell, sock = await _real_shell(app, auth_headers, monkeypatch)
    mine = await _run_in("conv-ch", "worker")
    await asyncio.sleep(1.0)
    marker = "agent-can-read-" + ("$(1+1)" if IS_WINDOWS else "$((1+1))")
    await sock.send({"type": "input", "data": _say(option, f"echo {marker}")})
    assert await sock.read_until(lambda s: "agent-can-read-2" in s.text, 30), sock.text[-1000:]
    body = (await app.get(READ, headers=mine)).json()
    (read,) = body["shells"]
    assert read["running"] is True and read["directory"] == shell["directory"]
    assert any(line.strip() == "agent-can-read-2" for line in read["lines"]), read["lines"]
    assert all("\x1b" not in line for line in read["lines"])
    await sock.close()
