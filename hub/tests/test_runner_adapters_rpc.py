"""RPC-executor tests for `hub.runner_adapters` (task 1.4).

`rpc_kwargs_golden.json` was captured by `fixtures/runner_adapters/capture_goldens.py` from
today's `hub.api.v1.agent_trigger._execute_codex_appserver_run`, driven end to end before group 2
builds the adapter package and before design D9's `_execute_rpc_run(adapter, transport, …)`
replaces today's `_execute_codex_appserver_run` (which itself already delegates to a
differently-shaped, Copilot-shared `_execute_rpc_run` -- see FINDINGS.md F470 for the naming
collision group 2 has to resolve, since `RpcCallbacks`/`_execute_rpc_run` already exist in
`agent_trigger.py` today as an explicit placeholder for this slice). This file fails on
`ModuleNotFoundError: hub.runner_adapters` until group 2 lands; that is correct per tasks.md's
ordering (goldens/tests first, group 2 second).

Each case is checked two ways (task 1.4's own wording):
1. `_execute_rpc_run(get_adapter("codex"), CodexAppServerTransport(), **inputs)`, driven with the
   same seeded Conversation/Run and the same `_await_operator_permission`/`sse_manager.broadcast`
   patches the capture used, but patching `hub.codex_appserver.run_turn` (D9: "the patch seam
   moves") instead of `hub.api.v1.agent_trigger.codex_run_turn`.
2. `CodexAppServerTransport().run_turn(RpcTurnRequest(...), RpcCallbacks(...))` called directly,
   bypassing `_execute_rpc_run` entirely, checking the same data kwargs reach
   `codex_appserver.run_turn`.

The golden's `resume_thread_id` key (today's name, on `codex_run_turn`'s own parameter, which does
not rename) is `RpcTurnRequest.resume_session_id` on the request side (D3, design.md:178).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from hub.runner_adapters import get_adapter
from hub.runner_adapters.base import RpcCallbacks, RpcTurnRequest
from hub.runner_adapters.codex import CodexAppServerTransport

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "runner_adapters"
GOLDEN_PATH = FIXTURES_DIR / "rpc_kwargs_golden.json"

with open(GOLDEN_PATH, encoding="utf-8") as f:
    RPC_GOLDEN = json.load(f)


def _case_ids():
    return [case["id"] for case in RPC_GOLDEN]


def _data_kwargs_from_golden(case):
    k = case["codex_run_turn_kwargs"]
    return {
        "cli": k["cli"],
        "posture": k["posture"],
        "workspace": k["workspace"],
        "cwd": k["cwd"],
        "env": k["env"],
        "prompt": k["prompt"],
        "model": k["model"],
        "resume_thread_id": k["resume_thread_id"],
        "yolo": k["yolo"],
        "mcp_command": k["mcp_command"],
        "config_overrides": k["config_overrides"],
    }


def _approval_subject(work_dir):
    return {
        "cwd": f"{work_dir}/nested",
        "paths": [f"{work_dir}/nested/file.py"],
    }


async def _drive_case(case, *, project_id):
    """Seed a Conversation/Run (mirroring the golden's own capture, task 1.4/1.5) and drive the
    case's inputs through `_execute_rpc_run`, recording the same four behaviours the golden
    captured off `_execute_codex_appserver_run`."""
    from hub import codex_appserver
    from hub.api.v1 import agent_trigger
    from hub.codex_appserver import TurnOutcome
    from hub.db.engine import async_session_factory
    from hub.db.models import Conversation, EventLog, Run

    slug = case["id"].replace("/", "_").replace("=", "-")
    agent = f"rpc-test-{slug}"
    run_id = f"run-test-{slug}"
    conversation_id = f"conv-test-{slug}"

    async with async_session_factory() as db:
        db.add(
            Conversation(id=conversation_id, project_id=project_id, agent=agent, lifecycle="open")
        )
        db.add(Run(id=run_id, project_id=project_id, agent=agent, conversation_id=conversation_id))
        await db.commit()

    inputs = dict(case["input"])
    refusal_method = case["refusal"]["method"] if case["refusal"] else None

    permission_calls = []

    async def _fake_await_operator_permission(**kwargs):
        permission_calls.append(
            {
                "method": kwargs["method"],
                "subject": kwargs["subject"],
                "project_id": kwargs["project_id"],
                "agent": kwargs["agent"],
                "run_id": kwargs["run_id"],
                "timeout_seconds": kwargs["timeout_seconds"],
            }
        )
        return True

    broadcasts = []

    async def _fake_broadcast(project_id, event_type, payload):
        broadcasts.append({"event_type": event_type, "payload": payload})

    captured = {}

    async def _recorder(**kwargs):
        captured["data_kwargs"] = {
            "cli": kwargs["cli"],
            "posture": kwargs["posture"],
            "workspace": kwargs["workspace"],
            "cwd": kwargs["cwd"],
            "env": kwargs["env"],
            "prompt": kwargs["prompt"],
            "model": kwargs["model"],
            "resume_thread_id": kwargs["resume_thread_id"],
            "yolo": kwargs["yolo"],
            "mcp_command": kwargs["mcp_command"],
            "config_overrides": kwargs["config_overrides"],
        }

        should_interrupt = kwargs["should_interrupt"]
        before = should_interrupt()
        agent_trigger._stop_requested.add(run_id)
        after = should_interrupt()
        agent_trigger._stop_requested.discard(run_id)
        captured["should_interrupt"] = {"before": before, "after": after}

        thread_id = f"thread-test-{slug}"
        await kwargs["on_thread_started"](thread_id)
        captured["thread_id"] = thread_id

        await kwargs["request_approval"](
            codex_appserver.FILE_CHANGE_APPROVAL_METHOD, _approval_subject(inputs["work_dir"])
        )

        if refusal_method is not None:
            await kwargs["on_refusal"](
                refusal_method,
                {"reason": "captured", "paths": [f"{inputs['work_dir']}/refused.py"]},
            )

        return TurnOutcome(thread_id=thread_id, status="completed")

    with patch.object(codex_appserver, "run_turn", AsyncMock(side_effect=_recorder)):
        with patch.object(
            agent_trigger,
            "_await_operator_permission",
            AsyncMock(side_effect=_fake_await_operator_permission),
        ):
            with patch.object(
                agent_trigger.sse_manager, "broadcast", AsyncMock(side_effect=_fake_broadcast)
            ):
                await agent_trigger._execute_rpc_run(
                    get_adapter("codex"),
                    CodexAppServerTransport(),
                    project_id=project_id,
                    agent=agent,
                    run_id=run_id,
                    conversation_id=conversation_id,
                    **inputs,
                )

    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run_session_id_after = run.session_id if run else None

    refusal_result = None
    if refusal_method is not None:
        from sqlalchemy import select

        async with async_session_factory() as db:
            result = await db.execute(
                select(EventLog)
                .where(EventLog.event_type == "permission_denied", EventLog.agent == agent)
                .order_by(EventLog.timestamp.desc())
            )
            row = result.scalars().first()
            persisted_tool_name = (row.data or {}).get("tool_name") if row else None
        broadcast_tool_name = next(
            (
                b["payload"].get("tool_name")
                for b in broadcasts
                if b["event_type"] == "permission_denied"
            ),
            None,
        )
        refusal_result = {
            "method": refusal_method,
            "persisted_tool_name": persisted_tool_name,
            "broadcast_tool_name": broadcast_tool_name,
        }

    return {
        "codex_run_turn_kwargs": captured["data_kwargs"],
        "request_approval": permission_calls[0] if permission_calls else None,
        "should_interrupt": captured["should_interrupt"],
        "bound_thread_id": captured["thread_id"],
        "run_session_id_after": run_session_id_after,
        "refusal": refusal_result,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("case", RPC_GOLDEN, ids=_case_ids())
async def test_execute_rpc_run_matches_golden(app, case):
    actual = await _drive_case(case, project_id="proj-test")

    assert actual["codex_run_turn_kwargs"] == _data_kwargs_from_golden(case)
    assert actual["request_approval"]["method"] == case["request_approval"]["method"]
    assert actual["request_approval"]["subject"] == case["request_approval"]["subject"]
    assert (
        actual["request_approval"]["timeout_seconds"] == case["request_approval"]["timeout_seconds"]
    )
    assert actual["should_interrupt"] == case["should_interrupt"]
    assert actual["run_session_id_after"] == actual["bound_thread_id"]

    if case["refusal"] is not None:
        assert actual["refusal"]["persisted_tool_name"] == case["refusal"]["persisted_tool_name"]
        assert actual["refusal"]["broadcast_tool_name"] == case["refusal"]["broadcast_tool_name"]
    else:
        assert actual["refusal"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", RPC_GOLDEN, ids=_case_ids())
async def test_transport_run_turn_matches_golden_data_kwargs(case):
    """Task 1.4's second assertion: `CodexAppServerTransport.run_turn` driven directly against a
    hand-built `RpcTurnRequest`/`RpcCallbacks`, bypassing `_execute_rpc_run` entirely."""
    from hub import codex_appserver
    from hub.codex_appserver import TurnOutcome

    inputs = case["input"]
    captured = {}

    async def _recorder(**kwargs):
        captured["data_kwargs"] = {
            "cli": kwargs["cli"],
            "posture": kwargs["posture"],
            "workspace": kwargs["workspace"],
            "cwd": kwargs["cwd"],
            "env": kwargs["env"],
            "prompt": kwargs["prompt"],
            "model": kwargs["model"],
            "resume_thread_id": kwargs["resume_thread_id"],
            "yolo": kwargs["yolo"],
            "mcp_command": kwargs["mcp_command"],
            "config_overrides": kwargs["config_overrides"],
        }
        return TurnOutcome(thread_id="thread-direct", status="completed")

    request = RpcTurnRequest(
        cli=inputs["cli"],
        cwd=inputs["work_dir"],
        env=inputs["env"],
        prompt=inputs["prompt"],
        model=inputs["model"],
        resume_session_id=inputs["known_session_id"],
        yolo=inputs["yolo"],
        mcp_command=inputs["mcp_command"],
        config_overrides=inputs["config_overrides"],
        permission_mode=inputs["permission_mode"],
        workspace=inputs["work_dir"],
        extra_flags=[],
        restrict_spec_writes=False,
    )
    callbacks = RpcCallbacks(
        on_event=AsyncMock(),
        on_usage=AsyncMock(),
        on_accounting=AsyncMock(),
        on_session=AsyncMock(),
        should_interrupt=lambda: False,
        request_approval=AsyncMock(return_value=True),
        on_refusal=AsyncMock(),
    )

    with patch.object(codex_appserver, "run_turn", AsyncMock(side_effect=_recorder)):
        await CodexAppServerTransport().run_turn(request, callbacks)

    assert captured["data_kwargs"] == _data_kwargs_from_golden(case)


def test_rpc_golden_covers_cross_product_axes_and_refusals():
    ids = _case_ids()
    assert any(cid.startswith("cross/") for cid in ids)
    assert any(cid.startswith("axis/") for cid in ids)
    assert any(cid.startswith("refusal/") for cid in ids)
