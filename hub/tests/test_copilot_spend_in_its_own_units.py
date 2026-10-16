"""Copilot spend is counted in its own units (F665 / WPC-6, `copilot-spend-is-counted-in-its-own-units`).

The figures are the work-PC drive's (trial DB `workpc-drive`, `proj-d73f8848ee60`): 20 Copilot turns
charged 19.0 premium requests and 154,000,145,000 nano-AIU with no allowance reading and no cost; a
checkpoint (1,102,140,000; 1.0) and its probe (822,390,000; 1.0) charged more and reported no tokens.
`GET /accounting` reported 19 and 154.00; the project spent 21 and 155.92.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Run, TurnUsage, WorkerInvocation

PROJECT = "proj-test"
ROUTE = f"/api/v1/projects/{PROJECT}/accounting"


async def _turn(
    run_id,
    *,
    agent="cop-1",
    runner="copilot",
    tokens=125_000,
    nano=None,
    premium=None,
    cost=None,
    allowance=None,
):
    async with async_session_factory() as db:
        db.add(Run(id=run_id, project_id=PROJECT, agent=agent, status="completed"))
        db.add(
            TurnUsage(
                id=f"usage-{run_id}",
                run_id=run_id,
                project_id=PROJECT,
                agent=agent,
                runner=runner,
                status="measured",
                input_tokens=tokens,
                output_tokens=0,
                total_tokens=tokens,
                ai_nano_aiu=nano,
                premium_requests=premium,
                api_equivalent_usd_micros=cost,
                # None is stored as the JSON text 'null' (D5): never read as a reading.
                allowance=allowance,
            )
        )
        await db.commit()


async def _worker(
    invocation_id, kind, *, cli="copilot", nano=None, premium=None, total=None, outcome="ok"
):
    async with async_session_factory() as db:
        db.add(
            WorkerInvocation(
                id=invocation_id,
                project_id=PROJECT,
                kind=kind,
                prompt_version=f"{kind}/1",
                cli=cli,
                outcome=outcome,
                error=None if outcome == "ok" else "failed",
                total_tokens=total,
                input_tokens=total,
                output_tokens=0 if total is not None else None,
                ai_nano_aiu=nano,
                premium_requests=premium,
            )
        )
        await db.commit()


async def _drive_figures():
    await _turn("run-a", nano=100_000_000_000, premium=12.0)
    await _turn("run-b", nano=54_000_145_000, premium=7.0)
    await _worker("wrk-ckpt", "checkpoint", nano=1_102_140_000, premium=1.0)
    await _worker("wrk-probe", "checkpoint_probe", nano=822_390_000, premium=1.0)


@pytest.mark.asyncio
async def test_a_copilot_projects_credits_include_its_worker_calls(app, auth_headers):
    await _drive_figures()
    body = (await app.get(ROUTE, headers=auth_headers)).json()

    assert body["project"]["ai_nano_aiu"] == 155_924_675_000
    assert body["project"]["premium_requests"] == 21.0
    # Agents stay turns only: a worker call belongs to no agent.
    [agent] = body["agents"]
    assert agent["ai_nano_aiu"] == 154_000_145_000
    assert agent["premium_requests"] == 19.0

    lines = {line["kind"]: line for line in body["workers"]}
    assert [line["kind"] for line in body["workers"]] == ["checkpoint", "checkpoint_probe"]
    checkpoint = lines["checkpoint"]
    assert checkpoint["ai_nano_aiu"] == 1_102_140_000
    assert checkpoint["premium_requests"] == 1.0
    assert (checkpoint["measured_calls"], checkpoint["credited_calls"]) == (0, 1)
    assert checkpoint["unmeasured_calls"] == 0, "a call that reported credits was measured in them"
    # Credits are never budgeted, and a one-shot call has no tokens to count.
    assert body["budget"]["used_tokens"] == 250_000


@pytest.mark.asyncio
async def test_the_headline_names_credits_when_they_are_the_only_spend_reported(app, auth_headers):
    await _drive_figures()
    display = (await app.get(ROUTE, headers=auth_headers)).json()["preferred_display"]
    assert display == {
        "kind": "credits",
        "label": "AI credits",
        "runner": "copilot",
        "ai_nano_aiu": 155_924_675_000,
        "premium_requests": 21.0,
    }


@pytest.mark.asyncio
async def test_worker_credits_alone_name_the_headline(app, auth_headers):
    """wpc6-f (recommended yes): a Codex project whose checkpoint runner is Copilot."""
    await _turn("run-x", agent="codex-1", runner="codex")
    await _worker("wrk-ckpt", "checkpoint", nano=1_102_140_000, premium=1.0)
    display = (await app.get(ROUTE, headers=auth_headers)).json()["preferred_display"]
    assert display["kind"] == "credits"


@pytest.mark.asyncio
async def test_a_reported_cost_or_an_allowance_still_leads(app, auth_headers):
    await _drive_figures()
    await _turn("run-claude", agent="claude-1", runner="claude", cost=12_500)
    assert (await app.get(ROUTE, headers=auth_headers)).json()["preferred_display"][
        "kind"
    ] == "api_equivalent"
    await _turn("run-read", allowance={"status": "allowed", "provider": "copilot"}, nano=1)
    assert (await app.get(ROUTE, headers=auth_headers)).json()["preferred_display"][
        "kind"
    ] == "allowance"


@pytest.mark.asyncio
async def test_a_project_with_no_credits_keeps_tokens(app, auth_headers):
    await _turn("run-claude", agent="claude-1", runner="claude")
    await _worker("wrk-ckpt", "checkpoint", cli="claude", total=500)
    body = (await app.get(ROUTE, headers=auth_headers)).json()
    assert body["preferred_display"]["kind"] == "tokens"
    assert body["project"]["ai_nano_aiu"] is None
    assert body["workers"][0]["credited_calls"] == 0


@pytest.mark.asyncio
async def test_a_call_that_reported_nothing_is_still_unmeasured(app, auth_headers):
    await _worker("wrk-none", "checkpoint", outcome="nonzero_exit")
    await _worker("wrk-never", "checkpoint", outcome="budget_exhausted")
    [line] = (await app.get(ROUTE, headers=auth_headers)).json()["workers"]
    assert (line["measured_calls"], line["credited_calls"], line["unmeasured_calls"]) == (0, 0, 1)
    assert line["ai_nano_aiu"] is None


@pytest.mark.asyncio
async def test_a_json_null_allowance_is_never_read_as_a_reading(app, auth_headers):
    """D5's control: the 'null' text every reading-less turn stores."""
    await _turn("run-a", nano=5, premium=1.0)
    body = (await app.get(ROUTE, headers=auth_headers)).json()
    assert body["preferred_display"]["kind"] != "allowance"
    assert body["recent_turns"][0]["allowance"] is None
