"""Worker spend counts against the budget (F240, `worker-spend-counts-against-the-budget`).

Every model call the Hub makes for a project outside a turn is recorded with one normalised token
total, joins the project total and the budget as a per-kind `workers` line, and is not spawned at
exhaustion unless the operator asked for it. F240 drove the defect: a budget below usage, autonomy
"paused" on screen, and a checkpoint plus its probe spending what reached no total.
"""

import json
import subprocess

import pytest
from pydantic import BaseModel
from sqlalchemy import select

import hub.conversation_titles as conversation_titles
from hub.checkpoint_generation import generate_checkpoint
from hub.checkpoint_handover import consider_handover
from hub.checkpoint_trigger import consider
from hub.conversations import get_conversation_by_id
from hub.db.engine import async_session_factory
from hub.db.models import Checkpoint, CheckpointNote, Project, Run, TurnUsage, WorkerInvocation
from hub.usage_accounting import project_budget_state
from hub.worker import _Spawn, run_worker

from .test_accounting_budget import _set_budget_and_usage
from .test_checkpoint_cutover import AGENT, _configured_project
from .test_checkpoint_cutover import _conversation as _cutover_conversation
from .test_handover_briefs_the_reviewer import (
    AUTHOR,
    _checkpoint_runner,
    _flow_handover,
)
from .test_review_turn import _roster
from .test_title_generation import _conversation as _title_conversation
from .test_title_generation import _set_mode, _sync_agent

PROJECT = "proj-test"


class Answer(BaseModel):
    state: str


def _claude_envelope(answer, *, usage):
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": answer if isinstance(answer, str) else json.dumps(answer),
            "usage": usage,
            "total_cost_usd": 0.01,
        }
    )


CLAUDE_USAGE = {
    "input_tokens": 2,
    "cache_read_input_tokens": 47091,
    "cache_creation_input_tokens": 100,
    "output_tokens": 497,
}
CODEX_STDOUT = "\n".join(
    [
        json.dumps(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": json.dumps({"state": "done"})},
            }
        ),
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1000, "cached_input_tokens": 800, "output_tokens": 50},
            }
        ),
    ]
)


def _spawns(monkeypatch, stdout):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr("hub.worker.resolve_executable", lambda cmd: cmd)
    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def _no_spawn(monkeypatch):
    def explode(*_a, **_k):  # pragma: no cover - the point is that nothing spawns
        raise AssertionError("nothing may be spawned at exhaustion")

    monkeypatch.setattr(subprocess, "run", explode)
    monkeypatch.setattr(conversation_titles, "_run_titler", explode)


async def _work(**overrides):
    kwargs = {
        "project_id": PROJECT,
        "kind": "checkpoint",
        "prompt": "Summarise.",
        "prompt_version": "checkpoint/1",
        "output_model": Answer,
        "cli": "claude",
        "model": "claude-haiku-4-5-20251001",
        "conversation_id": "conv-1",
        "initiator": "autonomous",
    }
    kwargs.update(overrides)
    return await run_worker(**kwargs)


async def _rows(kind=None):
    async with async_session_factory() as db:
        query = select(WorkerInvocation).order_by(WorkerInvocation.created_at)
        if kind is not None:
            query = query.where(WorkerInvocation.kind == kind)
        return list((await db.execute(query)).scalars().all())


async def _exhaust():
    await _set_budget_and_usage(limit=10, used=50)


# --------------------------------------------------------------------- the normalised total (D1)


@pytest.mark.asyncio
async def test_a_claude_worker_counts_its_cache_as_input_like_a_turn(app, monkeypatch):
    _spawns(monkeypatch, _claude_envelope({"state": "done"}, usage=CLAUDE_USAGE))
    result = await _work()
    assert result.ok
    [row] = await _rows()
    assert row.total_tokens == 2 + 47091 + 100 + 497


@pytest.mark.asyncio
async def test_a_codex_worker_does_not_count_its_cache_twice(app, monkeypatch):
    _spawns(monkeypatch, CODEX_STDOUT)
    result = await _work(cli="codex", model="gpt-5.6-terra")
    assert result.ok
    [row] = await _rows()
    assert row.total_tokens == 1050


# ------------------------------------------------------------------- totals and budget (D2)


async def _seed_worker(kind, total, *, invocation_id):
    async with async_session_factory() as db:
        db.add(
            WorkerInvocation(
                id=invocation_id,
                project_id=PROJECT,
                kind=kind,
                prompt_version=f"{kind}/1",
                cli="claude",
                outcome="ok",
                input_tokens=total,
                output_tokens=0,
                total_tokens=total,
            )
        )
        await db.commit()


async def _seed_turn(total):
    async with async_session_factory() as db:
        db.add(Run(id="run-w1", project_id=PROJECT, agent="history", status="completed"))
        db.add(
            TurnUsage(
                id="usage-w1",
                run_id="run-w1",
                project_id=PROJECT,
                agent="history",
                status="measured",
                input_tokens=total,
                output_tokens=0,
                total_tokens=total,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_worker_tokens_join_the_project_total_and_the_budget(app, auth_headers):
    await _seed_turn(1000)
    # Seeded out of kind order: the route orders the lines, and the assertion is by position.
    await _seed_worker("conversation_title", 200, invocation_id="wrk-t")
    await _seed_worker("checkpoint", 300, invocation_id="wrk-c")
    response = await app.get(f"/api/v1/projects/{PROJECT}/accounting", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"]["total_tokens"] == 1500
    assert body["budget"]["used_tokens"] == 1500
    assert [(w["kind"], w["total_tokens"], w["measured_calls"]) for w in body["workers"]] == [
        ("checkpoint", 300, 1),
        ("conversation_title", 200, 1),
    ]
    assert [a["total_tokens"] for a in body["agents"]] == [1000], "agents stay turns only"


@pytest.mark.asyncio
async def test_worker_tokens_can_exhaust_the_budget(app, auth_headers):
    await _seed_turn(1000)
    await _seed_worker("checkpoint", 500, invocation_id="wrk-c")
    async with async_session_factory() as db:
        project = await db.get(Project, PROJECT)
        project.token_budget = 1200
        await db.commit()
        state = await project_budget_state(db, PROJECT)
    assert state["used_tokens"] == 1500
    assert state["exhausted"] is True

    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/accounting/budget",
        json={"token_budget": 1400},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    snapshot = await app.get(f"/api/v1/projects/{PROJECT}/accounting", headers=auth_headers)
    assert snapshot.json()["budget"]["used_tokens"] == 1500


# ------------------------------------------------------------------------------ the gate (D3)


@pytest.mark.asyncio
async def test_an_autonomous_worker_is_not_spawned_at_exhaustion(app, monkeypatch):
    await _exhaust()
    _no_spawn(monkeypatch)
    result = await _work(initiator="autonomous")
    assert result.outcome == "budget_exhausted"
    [row] = await _rows()
    assert row.outcome == "budget_exhausted"
    assert row.total_tokens is None


@pytest.mark.asyncio
async def test_an_operator_worker_runs_at_exhaustion_and_is_counted(app, monkeypatch):
    await _exhaust()
    _spawns(monkeypatch, _claude_envelope({"state": "done"}, usage=CLAUDE_USAGE))
    result = await _work(initiator="operator")
    assert result.ok
    async with async_session_factory() as db:
        state = await project_budget_state(db, PROJECT)
    assert state["used_tokens"] == 50 + 47690


@pytest.mark.asyncio
async def test_an_unreadable_budget_does_not_authorise_autonomous_spend(app, monkeypatch):
    _no_spawn(monkeypatch)

    async def broken(db, project_id):
        raise RuntimeError("budget unreadable")

    monkeypatch.setattr("hub.worker.project_budget_state", broken)
    result = await _work(initiator="autonomous")
    assert result.outcome == "spawn_failed"
    assert "budget" in result.error


@pytest.mark.asyncio
async def test_a_checkpoint_is_operator_work_only_when_the_operator_pressed_it(app, monkeypatch):
    seen = []

    async def capture(**kwargs):
        from hub.worker import WorkerResult

        seen.append(kwargs["initiator"])
        return WorkerResult("spawn_failed", error="captured")

    monkeypatch.setattr("hub.checkpoint_generation.run_worker", capture)
    async with async_session_factory() as db:
        await _configured_project(db)
        conversation = await _cutover_conversation(db)
        for trigger in ("operator", "context_pressure", "task_completion"):
            await generate_checkpoint(db, conversation, trigger=trigger, cli="claude", probe=False)
    assert seen == ["operator", "autonomous", "autonomous"]


def test_vault_work_is_operator_work_only_when_the_operator_asked():
    from hub import distillation, vault_spec_check

    assert distillation.initiator_for(distillation.REQUESTED) == "operator"
    assert distillation.initiator_for(distillation.UPLOADED) == "autonomous"
    assert distillation.initiator_for(distillation.FACTS_WRITTEN) == "autonomous"
    assert vault_spec_check.initiator_for(vault_spec_check.REQUESTED) == "operator"
    assert vault_spec_check.initiator_for(vault_spec_check.TRIGGER) == "autonomous"


# -------------------------------------------------------------- the automatic triggers (D3a)


@pytest.mark.asyncio
async def test_an_automatic_checkpoint_at_exhaustion_warns_and_spends_nothing(app, monkeypatch):
    broadcasts = []

    async def record(project_id, event, payload):
        broadcasts.append((event, payload.get("final")))

    monkeypatch.setattr("hub.checkpoint_trigger.sse_manager.broadcast", record)
    async with async_session_factory() as db:
        await _configured_project(db)
        await _cutover_conversation(db)
    await _exhaust()
    _no_spawn(monkeypatch)

    assert await consider(PROJECT, AGENT, "conv-1", context_tokens=None, percent=85.0) is None
    async with async_session_factory() as db:
        conversation = await get_conversation_by_id(db, "conv-1")
        checkpoints = (await db.execute(select(Checkpoint))).scalars().all()
    assert checkpoints == []
    assert conversation.checkpoint_warning == "due"
    assert broadcasts == [("checkpoint_due", None)]

    # Dismissed: honoured below the final point, then the final warning still fires.
    async with async_session_factory() as db:
        conversation = await get_conversation_by_id(db, "conv-1")
        conversation.checkpoint_warning = "dismissed"
        await db.commit()
    broadcasts.clear()
    assert await consider(PROJECT, AGENT, "conv-1", context_tokens=None, percent=86.0) is None
    assert broadcasts == []
    assert await consider(PROJECT, AGENT, "conv-1", context_tokens=None, percent=99.0) is None
    assert broadcasts == [("checkpoint_due", True)]


@pytest.mark.asyncio
async def test_with_no_budget_the_trigger_does_not_read_one_below_threshold(app, monkeypatch):
    async def broken(db, project_id):
        raise AssertionError("the budget is read only when an automatic checkpoint is due")

    monkeypatch.setattr("hub.checkpoint_trigger.project_budget_state", broken)
    async with async_session_factory() as db:
        await _configured_project(db)
        await _cutover_conversation(db)
    assert await consider(PROJECT, AGENT, "conv-1", context_tokens=None, percent=40.0) is None


@pytest.mark.asyncio
async def test_a_handover_at_exhaustion_declines_and_keeps_the_note(
    app, auth_headers, bind_runner, monkeypatch
):
    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _checkpoint_runner(db)
        _, _, _, _, run = await _flow_handover(db, suffix="w")
    await _exhaust()
    _no_spawn(monkeypatch)

    assert await consider_handover(run.id) is None
    async with async_session_factory() as db:
        assert (await db.execute(select(Checkpoint))).scalars().all() == []
        note = await db.get(CheckpointNote, "note-hand-w")
    assert note.consumed_by_checkpoint_id is None


# --------------------------------------------------------------------------- the titler (D4)


@pytest.mark.asyncio
async def test_the_titler_records_its_call_and_its_tokens(
    app, auth_headers, bind_runner, monkeypatch
):
    await _sync_agent(app, auth_headers)
    conversation_id = await _title_conversation(app, auth_headers, bind_runner)
    await _set_mode("generate")
    calls = []

    def run(cmd, cwd, env=None):
        calls.append(cmd)
        return _Spawn("ok", stdout=_claude_envelope("Checkout flake", usage=CLAUDE_USAGE))

    monkeypatch.setattr(conversation_titles, "_run_titler", run)
    title = await conversation_titles.generate_conversation_title(
        project_id=PROJECT, conversation_id=conversation_id
    )
    assert title == "Checkout flake"
    assert "--output-format" in calls[0] and "json" in calls[0]
    [row] = await _rows("conversation_title")
    assert row.outcome == "ok"
    assert row.total_tokens == 47690
    assert row.prompt_version == "conversation-title/1"


@pytest.mark.asyncio
async def test_the_titler_is_not_spawned_at_exhaustion(app, auth_headers, bind_runner, monkeypatch):
    await _sync_agent(app, auth_headers)
    conversation_id = await _title_conversation(app, auth_headers, bind_runner)
    await _set_mode("generate")
    await _exhaust()
    _no_spawn(monkeypatch)

    assert (
        await conversation_titles.generate_conversation_title(
            project_id=PROJECT, conversation_id=conversation_id
        )
        is None
    )
    [row] = await _rows("conversation_title")
    assert row.outcome == "budget_exhausted"
