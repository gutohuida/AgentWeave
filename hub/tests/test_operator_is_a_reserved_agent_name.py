"""F415: `operator` is reserved as an agent name, as `user` is.

Round 3a (F261) made `operator` the runless sender of `POST /messages` and left that name out of
`GET /agents`' activity fallback and `GET /status`'s `agents_active`. An agent named `operator` could
still be declared, and would then be hidden from both and have its messages read as the operator's.
"""

import ast
from pathlib import Path

import pytest

from hub import worktrees
from hub.model_catalog import get_provider
from hub.schemas.messages import OPERATOR_SENDER

SYNC = "/api/v1/projects/proj-test/session/sync"
CLAUDE_MODEL = get_provider("claude").models[0].id


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["operator", "Operator"])
async def test_a_session_declaring_an_agent_named_operator_is_refused(app, auth_headers, name):
    resp = await app.post(
        SYNC, json={"data": {"agents": {name: {}, "worker": {}}}}, headers=auth_headers
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json()["detail"]
    assert f"reserved agent name '{name}'" in detail
    assert "operator's own messages" in detail
    roster = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert roster.json() == []


@pytest.mark.asyncio
async def test_registering_an_agent_named_operator_is_refused(app, auth_headers):
    resp = await app.post(
        "/api/v1/projects/proj-test/agents/register",
        json={"name": "operator", "contact_mode": "poll"},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    assert "reserved agent name 'operator'" in resp.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["operator", "Operator", "user"])
async def test_the_create_dialog_route_refuses_a_reserved_name(app, auth_headers, name):
    """Round 4 review: `POST /agents`, the Add-agent dialog's route, checked only the pattern and
    created all three, each then unable to run a single turn."""
    resp = await app.post(
        "/api/v1/projects/proj-test/agents",
        json={"name": name, "provider": "claude", "model": CLAUDE_MODEL},
        headers=auth_headers,
    )

    assert resp.status_code == 400, resp.text
    # A sentence: the dialog renders `detail` as text, so a validator's list would not do.
    assert resp.json()["detail"].startswith(f"reserved agent name '{name}'")
    roster = await app.get("/api/v1/projects/proj-test/agents", headers=auth_headers)
    assert name not in {row["name"] for row in roster.json()}


def test_the_reserved_name_is_the_sender_the_hub_gives_the_operator():
    with pytest.raises(ValueError, match="reserved"):
        worktrees.validate_agent_name(OPERATOR_SENDER)
    with pytest.raises(ValueError, match="reserved agent name 'user'"):
        worktrees.validate_agent_name("user")
    # Reserved as a whole name only: a name that merely contains it is an ordinary agent.
    worktrees.validate_agent_name("operator-2")
    worktrees.validate_agent_name("ops")


def test_the_cli_reserves_the_same_names():
    """CLAUDE.md: the CLI and Hub name rules change together. Read from the CLI's source rather
    than imported, so this compares against the checkout's own CLI, not the installed one."""
    constants = Path(__file__).resolve().parents[2] / "src" / "agentweave" / "constants.py"
    tree = ast.parse(constants.read_text(encoding="utf-8"))
    reserved = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "RESERVED_AGENT_NAMES" for t in node.targets)
    )
    cli_names = ast.literal_eval(reserved.args[0])

    assert set(cli_names) == set(worktrees._RESERVED_AGENT_NAMES)
