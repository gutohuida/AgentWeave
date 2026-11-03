"""`a-traces-view-with-filters-grouping-and-stats`: the traces view's statistics, over everything
the filter matches (FR-8) and per group (FR-5): cost with unpriced runs left out and counted
(FR-14), total and average duration and errors first (FR-6), tokens, calls and waiting second
(FR-7). Read through `GET /traces/totals`, the route the view is fed from."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from hub import traces
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Run, Task, TraceSpan, TurnUsage

PROJECT = "proj-test"
NOW = datetime.now(timezone.utc).replace(microsecond=0)


async def _run(
    run_id,
    agent,
    *,
    started=None,
    seconds=10,
    status="completed",
    task_id=None,
    conv=None,
    micros=None,
    unpriced=False,
    model="claude-haiku-5-5",
    tokens=(100, 20, 300, 40),
    chats=0,
    tools=0,
    failed_tools=0,
    wait_seconds=0,
    trace_error=False,
):
    """One run with its trace, ended (unless *status* is running) with what its row and the
    totals read: a measured cost (*micros*), an unmeasured one (*unpriced*), or no usage row at
    all; *chats* model calls and *tools* tool calls inside it, *failed_tools* of them failed; a
    permission wait of *wait_seconds*; and a root that ended in error (*trace_error*)."""
    started = started or NOW - timedelta(minutes=5)
    async with async_session_factory() as db:
        run = Run(
            id=run_id,
            project_id=PROJECT,
            agent=agent,
            status="running",
            started_at=started,
            task_id=task_id,
            conversation_id=conv,
        )
        db.add(run)
        traces.start_run(db, run, prompt="go", runner="claude", model=model)
        await db.commit()
    async with async_session_factory() as db:
        root = await db.get(TraceSpan, traces.root_span_id(run_id))
        root.start_time = started
        root.trace_started_at = started

        def child(name, operation, n, status="ok", length=1):
            db.add(
                TraceSpan(
                    span_id=traces._span_id(run_id, name, str(n)),
                    trace_id=root.trace_id,
                    parent_span_id=root.span_id,
                    project_id=PROJECT,
                    run_id=run_id,
                    name=name,
                    operation=operation,
                    status=status,
                    start_time=started + timedelta(seconds=1),
                    end_time=started + timedelta(seconds=1 + length),
                    ended=True,
                    trace_started_at=started,
                    attributes={},
                )
            )

        for n in range(chats):
            child("chat", "chat", n)
        for n in range(tools):
            child("execute_tool Bash", "execute_tool", n, "error" if n < failed_tools else "ok")
        if wait_seconds:
            child("aw.permission_wait Bash", "aw.permission_wait", 0, length=wait_seconds)
        await db.commit()
    if status == "running":
        return
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run.status = status
        run.ended_at = started + timedelta(seconds=seconds)
        if micros is not None:
            i, o, cr, cw = tokens
            db.add(
                TurnUsage(
                    id=f"tu-{run_id}",
                    run_id=run_id,
                    project_id=PROJECT,
                    agent=agent,
                    status="measured",
                    input_tokens=i,
                    output_tokens=o,
                    cache_read_tokens=cr,
                    cache_write_tokens=cw,
                    total_tokens=i + o,
                    model=model,
                    api_equivalent_usd_micros=micros,
                )
            )
        elif unpriced:
            db.add(
                TurnUsage(
                    id=f"tu-{run_id}",
                    run_id=run_id,
                    project_id=PROJECT,
                    agent=agent,
                    status="unavailable",
                    model=model,
                )
            )
        await traces.finish_run(db, run_id)
        if trace_error:
            root = await db.get(TraceSpan, traces.root_span_id(run_id))
            root.status = "error"
            root.status_message = "the trace ended in error"
        await db.commit()


async def _totals(app, auth_headers, **params):
    res = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/totals",
        params={"operation": "invoke_agent", **params},
        headers=auth_headers,
    )
    assert res.status_code == 200, res.text
    return res.json()


def _groups(answer):
    return {g["key"]: g for g in answer["groups"]}


@pytest.mark.asyncio
async def test_headline_numbers_and_the_error_rule(app, auth_headers):
    """headline-numbers: five runs with known costs and durations; errors are the failed, the
    stopped and the trace that ended in error, never the completed run with a failed tool call."""
    await _run("run-h-ok", "hana", micros=100_000, seconds=10)
    await _run("run-h-failed", "hana", status="failed", micros=200_000, seconds=20)
    await _run("run-h-stopped", "hana", status="stopped", micros=300_000, seconds=30)
    await _run("run-h-traceerr", "hana", micros=400_000, seconds=40, trace_error=True)
    await _run("run-h-toolfail", "hana", micros=500_000, seconds=50, tools=2, failed_tools=1)

    answer = await _totals(app, auth_headers, agent="hana")
    t = answer["totals"]
    assert t["count"] == 5
    assert t["cost_usd_micros"] == 1_500_000 and t["priced"] == 5 and t["unpriced"] == 0
    assert t["duration_seconds"] == 150 and t["duration_avg_seconds"] == 30
    assert t["errors"] == 3
    assert t["error_kinds"] == {"failed": 1, "stopped": 1, "trace_error": 1}
    assert answer["groups"] is None

    # The same figures for a group, and the list's rows agree on which runs are errors.
    group = _groups(await _totals(app, auth_headers, agent="hana", group_by="agent"))["hana"]
    assert group["totals"]["count"] == 5 and group["totals"]["errors"] == 3
    assert group["totals"]["cost_usd_micros"] == 1_500_000
    assert group["totals"]["duration_avg_seconds"] == 30
    res = await app.get(
        f"/api/v1/projects/{PROJECT}/traces", params={"agent": "hana"}, headers=auth_headers
    )
    errors = {t["run_id"] for t in res.json()["traces"] if t["is_error"]}
    assert errors == {"run-h-failed", "run-h-stopped", "run-h-traceerr"}


@pytest.mark.asyncio
async def test_secondary_numbers_match_what_was_recorded(app, auth_headers):
    """secondary-numbers: tokens, model calls, tool calls and a permission wait."""
    await _run("run-s-1", "sora", micros=1_000, tokens=(100, 20, 300, 40), chats=3, tools=4)
    await _run(
        "run-s-2", "sora", micros=2_000, tokens=(7, 3, 0, 1), chats=1, tools=1, wait_seconds=12
    )
    t = (await _totals(app, auth_headers, agent="sora"))["totals"]
    assert t["tokens"] == {"input": 107, "output": 23, "cache_read": 300, "cache_write": 41}
    assert t["model_calls"] == 4
    assert t["tool_calls"] == 5
    assert t["wait_seconds"] == 12


@pytest.mark.asyncio
async def test_unpriced_runs_are_left_out_and_counted_and_running_ones_are_neither(
    app, auth_headers
):
    """unpriced-shown: two measured, one finished unmeasured, one still running."""
    await _run("run-u-a", "umi", micros=250_000, conv="conv-u")
    await _run("run-u-b", "umi", micros=750_000, conv="conv-u")
    await _run("run-u-none", "umi", unpriced=True, conv="conv-u2")
    await _run("run-u-live", "umi", status="running", conv="conv-u3")

    t = (await _totals(app, auth_headers, agent="umi"))["totals"]
    assert t["count"] == 4
    assert t["cost_usd_micros"] == 1_000_000
    assert t["priced"] == 2 and t["unpriced"] == 1
    assert t["running"] == 1
    assert t["duration_avg_seconds"] == 10  # the running run has no duration yet

    groups = _groups(await _totals(app, auth_headers, agent="umi", group_by="conversation"))
    assert groups["conv-u"]["totals"]["cost_usd_micros"] == 1_000_000
    # A group of only unpriced runs has no cost figure, not a zero.
    assert groups["conv-u2"]["totals"]["cost_usd_micros"] is None
    assert groups["conv-u2"]["totals"]["unpriced"] == 1
    # A group of only a running run is neither priced nor unpriced.
    live = groups["conv-u3"]["totals"]
    assert live["cost_usd_micros"] is None and live["unpriced"] == 0 and live["running"] == 1


@pytest.mark.asyncio
async def test_grouping_switches_and_every_group_adds_up(app, auth_headers):
    """grouping-switches: two agents, two models, two tasks, two days; each grouping regroups the
    same runs and the groups' counts add up to the filtered total."""
    async with async_session_factory() as db:
        db.add(Task(id="task-g1", readable_id="GS-1", project_id=PROJECT, title="First"))
        db.add(Task(id="task-g2", readable_id="GS-2", project_id=PROJECT, title="Second"))
        db.add(Conversation(id="conv-g1", project_id=PROJECT, agent="gina", title="Talk"))
        await db.commit()
    yesterday = NOW - timedelta(days=1)
    await _run("run-g-1", "gina", task_id="task-g1", micros=10, model="claude-haiku-5-5")
    await _run("run-g-2", "gina", task_id="task-g2", micros=20, model="claude-sonnet-5-5")
    await _run(
        "run-g-3", "gus", task_id="task-g1", micros=30, model="claude-haiku-5-5", started=yesterday
    )
    await _run("run-g-4", "gus", conv="conv-g1", micros=40, status="failed", started=yesterday)
    await _run("run-g-5", "gus", task_id="task-gone", unpriced=True, started=yesterday)

    since = (NOW - timedelta(days=3)).isoformat()
    total = (await _totals(app, auth_headers, since=since))["totals"]
    assert total["count"] == 5
    for grouping in ("agent", "model", "task", "conversation", "kind", "day"):
        answer = await _totals(app, auth_headers, since=since, group_by=grouping)
        assert answer["totals"] == total, grouping
        assert sum(g["totals"]["count"] for g in answer["groups"]) == 5, grouping
        assert sum(g["totals"]["errors"] for g in answer["groups"]) == 1, grouping
        for group in answer["groups"]:
            assert group["label"], (grouping, group)
            assert {"cost_usd_micros", "duration_seconds", "errors"} <= set(group["totals"])

    agents = _groups(await _totals(app, auth_headers, since=since, group_by="agent"))
    assert {k: g["totals"]["count"] for k, g in agents.items()} == {"gina": 2, "gus": 3}
    models = _groups(await _totals(app, auth_headers, since=since, group_by="model"))
    assert models["claude-sonnet-5-5"]["totals"]["count"] == 1
    tasks = _groups(await _totals(app, auth_headers, since=since, group_by="task"))
    assert (tasks["task-g1"]["label"], tasks["task-g1"]["detail"]) == ("GS-1", "First")
    assert tasks["task-g1"]["totals"]["count"] == 2
    gone = tasks["task-gone"]
    assert gone["missing"] is True and gone["label"] == "Task no longer exists"
    assert "task-gone" not in gone["label"]
    assert tasks[""]["label"] == "No task" and tasks[""]["totals"]["count"] == 1
    conversations = _groups(await _totals(app, auth_headers, since=since, group_by="conversation"))
    assert conversations["conv-g1"]["label"] == "Talk"
    kinds = _groups(await _totals(app, auth_headers, since=since, group_by="kind"))
    assert list(kinds) == ["run"] and kinds["run"]["label"] == "Agent runs"
    days = (await _totals(app, auth_headers, since=since, group_by="day"))["groups"]
    assert [g["key"] for g in days] == [NOW.date().isoformat(), yesterday.date().isoformat()]
    assert [g["totals"]["count"] for g in days] == [2, 3]

    # Combined with a filter, the groups regroup only what it leaves.
    narrowed = _groups(
        await _totals(
            app, auth_headers, since=since, agent="gus", task_id="task-g1", group_by="day"
        )
    )
    assert {k: g["totals"]["count"] for k, g in narrowed.items()} == {
        yesterday.date().isoformat(): 1
    }

    bad = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/totals",
        params={"group_by": "colour"},
        headers=auth_headers,
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_a_day_is_the_operators_own_calendar_day(app, auth_headers):
    """A run at 23:30 UTC is the next day for an operator three hours east of UTC."""
    late = datetime(2026, 10, 1, 23, 30, tzinfo=timezone.utc)
    await _run("run-d-late", "dora", started=late, micros=1)
    utc = _groups(await _totals(app, auth_headers, agent="dora", group_by="day"))
    east = _groups(await _totals(app, auth_headers, agent="dora", group_by="day", utc_offset=180))
    assert list(utc) == ["2026-10-01"] and list(east) == ["2026-10-02"]


@pytest.mark.asyncio
async def test_the_statistics_count_every_matching_run_not_one_page(app, auth_headers):
    """stats-beyond-the-page: more runs than a page of the list holds; the list's first page has
    a page's worth and a cursor, the totals count and cost all of them."""
    for n in range(60):
        await _run(
            f"run-p-{n:02d}",
            "paz",
            started=NOW - timedelta(minutes=60 - n),
            micros=1_000,
            status="failed" if n % 20 == 0 else "completed",
        )
    page = await app.get(
        f"/api/v1/projects/{PROJECT}/traces", params={"agent": "paz"}, headers=auth_headers
    )
    listed = page.json()
    assert len(listed["traces"]) == 50 and listed["next_before"]

    t = (await _totals(app, auth_headers, agent="paz"))["totals"]
    assert t["count"] == 60
    assert t["cost_usd_micros"] == 60_000
    assert t["errors"] == 3
    group = _groups(await _totals(app, auth_headers, agent="paz", group_by="agent"))["paz"]
    assert group["totals"]["count"] == 60 and group["totals"]["cost_usd_micros"] == 60_000


@pytest.mark.asyncio
async def test_the_hubs_own_traces_are_totalled_without_a_cost(app, auth_headers):
    """Hub internals: requests are counted and timed, never priced or unpriced."""
    async with async_session_factory() as db:
        for n in range(3):
            start = NOW - timedelta(minutes=n + 1)
            db.add(
                TraceSpan(
                    span_id=traces._span_id("req-total", str(n)),
                    trace_id=traces._hex(f"req-total-{n}", 32),
                    parent_span_id=None,
                    project_id=PROJECT,
                    run_id=None,
                    name="GET /api/v1/x",
                    operation="aw.request",
                    status="error" if n == 0 else "ok",
                    start_time=start,
                    end_time=start + timedelta(seconds=2),
                    ended=True,
                    trace_started_at=start,
                    attributes={},
                )
            )
        await db.commit()
    await _run("run-i-1", "ines", micros=5)
    answer = await _totals(app, auth_headers, operation="aw.request", group_by="kind")
    t = answer["totals"]
    assert t["count"] == 3 and t["errors"] == 1 and t["error_kinds"]["trace_error"] == 1
    assert t["cost_usd_micros"] is None and t["unpriced"] == 0
    assert t["duration_seconds"] == 6
    assert [g["label"] for g in answer["groups"]] == ["Requests"]
