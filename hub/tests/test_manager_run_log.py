"""The run log (`background-manager-work-you-can-see`, BWYCS-4, design D6).

`GET /manager/runs` lists every manager run newest first -- the jobs' runs from their
`manager_job_fired` events, the mender's from its `runs` rows joined to their `turn_usage` -- with
every job's totals, narrowed by job and paged by `before`; `GET /manager/runs/{run_id}` is one run
with the model's answer. Events are written through `manager.record_firing`, as a run's end is.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from hub import manager, stalls
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Conversation, EventLog, Run, Stall, TurnUsage

from .test_vault_spec_check import PROJECT

PROJECT_ID = "proj-test"
RUNS = f"{PROJECT}/manager/runs"
T0 = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


async def _firing(
    run_id,
    job,
    *,
    minute,
    outcome="written",
    detail=None,
    cost=None,
    initiator="autonomous",
    trigger="spec_saved",
    subject=None,
    runner_id="runner-x",
    seconds=3,
    answer=None,
) -> None:
    """A run's end: it started `minute` minutes after T0 and took `seconds`."""
    started = T0 + timedelta(minutes=minute)
    async with async_session_factory() as db:
        await manager.record_firing(
            db,
            PROJECT_ID,
            job=job,
            trigger=trigger,
            subject=subject if subject is not None else {"document": "spec/a.json"},
            runner_id=runner_id,
            cli="claude",
            model="haiku" if runner_id else None,
            outcome=outcome,
            detail=detail,
            duration_ms=seconds * 1000,
            usage={"input_tokens": 10, "cost_usd_micros": cost} if cost is not None else None,
            answer=answer,
            extra={"run_id": run_id, "initiator": initiator, "started_at": started.isoformat()},
        )
    # The event's own time is when it was recorded: a run's end follows its start.
    async with async_session_factory() as db:
        row = (
            await db.execute(
                select(EventLog).order_by(EventLog.timestamp.desc(), EventLog.id.desc()).limit(1)
            )
        ).scalar_one()
        row.timestamp = started + timedelta(seconds=seconds)
        await db.commit()


async def _log(app, auth_headers, **params) -> dict:
    listed = await app.get(RUNS, headers=auth_headers, params=params)
    assert listed.status_code == 200, listed.text
    return listed.json()


@pytest.mark.asyncio
async def test_log_by_job(app, auth_headers) -> None:
    """log-by-job: 60 title runs newer than 3 spec-vault-check runs, one failed: narrowed to the
    check, its 3 runs show, and its totals read 3 runs, 1 failed and the sum of their costs."""
    for n, (outcome, cost) in enumerate([("written", 100), ("failed", 50), ("written", 25)]):
        await _firing(
            f"mrun-check{n}",
            manager.SPEC_VAULT_CHECK,
            minute=n,
            outcome=outcome,
            detail="refused" if outcome == "failed" else None,
            cost=cost,
        )
    for n in range(60):
        await _firing(
            f"mrun-title{n:02d}",
            manager.TITLES,
            minute=10 + n,
            cost=1,
            subject={"conversation_id": f"conv-{n}"},
        )

    flat = await _log(app, auth_headers)
    assert len(flat["runs"]) == 50 and flat["has_more"] is True
    assert {run["job"] for run in flat["runs"]} == {manager.TITLES}
    assert flat["runs"][0]["run_id"] == "mrun-title59"  # newest first

    narrowed = await _log(app, auth_headers, job=manager.SPEC_VAULT_CHECK)
    assert [run["run_id"] for run in narrowed["runs"]] == [
        "mrun-check2",
        "mrun-check1",
        "mrun-check0",
    ]
    assert narrowed["has_more"] is False
    assert narrowed["totals"][manager.SPEC_VAULT_CHECK] == {
        "runs": 3,
        "failed": 1,
        "cost_usd_micros": 175,
    }
    # Totals cover every job whatever the narrowing.
    assert narrowed["totals"][manager.TITLES]["runs"] == 60


@pytest.mark.asyncio
async def test_log_pages_by_before(app, auth_headers) -> None:
    for n in range(5):
        await _firing(f"mrun-p{n}", manager.TITLES, minute=n, subject={"conversation_id": "c"})
    first = await _log(app, auth_headers, limit=2)
    assert [r["run_id"] for r in first["runs"]] == ["mrun-p4", "mrun-p3"] and first["has_more"]
    second = await _log(app, auth_headers, limit=2, before="mrun-p3")
    assert [r["run_id"] for r in second["runs"]] == ["mrun-p2", "mrun-p1"] and second["has_more"]
    last = await _log(app, auth_headers, limit=2, before="mrun-p1")
    assert [r["run_id"] for r in last["runs"]] == ["mrun-p0"] and not last["has_more"]
    missing = await app.get(RUNS, headers=auth_headers, params={"before": "mrun-nope"})
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_log_columns(app, auth_headers) -> None:
    """log-columns (route half): a failed check started by Check now, an automatic distillation
    that spent tokens, and a failed run that never reached a model carry what each row shows."""
    await _firing(
        "mrun-now",
        manager.SPEC_VAULT_CHECK,
        minute=0,
        outcome="failed",
        detail="The check was refused.",
        initiator="operator",
        trigger="check_now",
        cost=70_000,
        seconds=12,
    )
    await _firing(
        "mrun-distil",
        manager.DISTILLATION,
        minute=1,
        cost=4000,
        subject={"source": "src-1"},
        trigger="source_added",
    )
    await _firing(
        "mrun-never",
        manager.CHAPTERS,
        minute=2,
        outcome="failed",
        detail="Did nothing: the Chapters job is on but has no runner.",
        runner_id="",
        seconds=0,
        subject={},
    )
    by_id = {run["run_id"]: run for run in (await _log(app, auth_headers))["runs"]}

    now = by_id["mrun-now"]
    assert (now["job"], now["trigger"], now["initiator"]) == (
        manager.SPEC_VAULT_CHECK,
        "check_now",
        "operator",
    )
    assert now["subject"] == {"document": "spec/a.json"}
    assert now["outcome"] == "failed" and now["detail"] == "The check was refused."
    assert now["started_at"] == T0.isoformat() and now["duration_ms"] == 12_000
    assert now["usage"]["cost_usd_micros"] == 70_000 and now["no_cost_reason"] is None

    distil = by_id["mrun-distil"]
    assert distil["initiator"] == "autonomous" and distil["usage"]["cost_usd_micros"] == 4000

    never = by_id["mrun-never"]
    assert never["usage"] is None and never["no_cost_reason"] == "never reached a model"


@pytest.mark.asyncio
async def test_a_run_by_id_carries_its_answer(app, auth_headers) -> None:
    await _firing("mrun-ans", manager.CHAPTERS, minute=0, answer="The thread, woven.", subject={})
    got = await app.get(f"{RUNS}/mrun-ans", headers=auth_headers)
    assert got.status_code == 200, got.text
    assert got.json()["run_id"] == "mrun-ans" and got.json()["answer"] == "The thread, woven."
    assert (await app.get(f"{RUNS}/mrun-nope", headers=auth_headers)).status_code == 404
    # The fixed paths are not taken for a run's id.
    assert (await app.get(f"{RUNS}/running", headers=auth_headers)).status_code == 200


async def _mender_run(*, status="completed") -> None:
    async with async_session_factory() as db:
        db.add(
            Agent(
                id="ag-mender",
                project_id=PROJECT_ID,
                name=stalls.MENDER,
                config={"hub_role": stalls.HUB_ROLE},
            )
        )
        db.add(
            Conversation(
                id="conv-mending", project_id=PROJECT_ID, agent=stalls.MENDER, origin="mender"
            )
        )
        db.add(
            Stall(
                id="stall-1",
                project_id=PROJECT_ID,
                key="integration_failed:task-x",
                cause="integration_failed",
                reason="The merge of task-x failed.",
                conversation_id="conv-mending",
            )
        )
        db.add(
            Run(
                id="run-mending",
                project_id=PROJECT_ID,
                agent=stalls.MENDER,
                conversation_id="conv-mending",
                status=status,
                started_at=T0,
                ended_at=T0 + timedelta(seconds=90),
                turn_depth=0,
            )
        )
        db.add(
            TurnUsage(
                id="tu-1",
                run_id="run-mending",
                project_id=PROJECT_ID,
                agent=stalls.MENDER,
                status="measured",
                model="claude-sonnet-5-5",
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
                api_equivalent_usd_micros=100_000,
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_mender_in_log(app, auth_headers) -> None:
    """mender-in-log: a finished mender run is listed under mender with its stall's reason,
    duration, outcome and cost, and names its conversation; it counts in the mender's totals."""
    await _mender_run()
    log = await _log(app, auth_headers, job=stalls.MENDER)
    [run] = log["runs"]
    assert run["run_id"] == "run-mending" and run["job"] == stalls.MENDER
    assert run["subject"] == {"stall": "stall-1", "reason": "The merge of task-x failed."}
    assert run["duration_ms"] == 90_000 and run["outcome"] == "answered"
    assert run["usage"]["cost_usd_micros"] == 100_000 and run["no_cost_reason"] is None
    assert run["conversation_id"] == "conv-mending"
    assert log["totals"][stalls.MENDER] == {"runs": 1, "failed": 0, "cost_usd_micros": 100_000}
    assert (await app.get(f"{RUNS}/run-mending", headers=auth_headers)).status_code == 200


@pytest.mark.asyncio
async def test_a_failed_mender_run_gives_its_reason_and_a_project_agent_named_mender_is_not_one(
    app, auth_headers
) -> None:
    await _mender_run(status="failed")
    async with async_session_factory() as db:
        run = await db.get(Run, "run-mending")
        run.error = "The mender's CLI exited 1."
        await db.commit()
    [failed] = (await _log(app, auth_headers, job=stalls.MENDER))["runs"]
    assert failed["outcome"] == "failed" and failed["detail"] == "The mender's CLI exited 1."
    assert (await _log(app, auth_headers))["totals"][stalls.MENDER]["failed"] == 1

    async with async_session_factory() as db:
        agent = await db.get(Agent, "ag-mender")
        agent.config = {}
        await db.commit()
    assert (await _log(app, auth_headers, job=stalls.MENDER))["runs"] == []
