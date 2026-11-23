"""GET /overview, the one read both Overview tabs show (`overview-at-a-glance-with-dashboard-and-
briefing-tabs`, task overview-read): the Hub halves of ac-needs-kinds-ranked, ac-main-states,
ac-spend-units, ac-running-duration, ac-finished-today and ac-build-stage.

Rows are seeded straight into the database, each with the time the criterion's story needs, and
read back through the route as the UI reads it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import pytest

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import (
    Build,
    Conversation,
    EventLog,
    KnownFailingTest,
    MainNotice,
    PermissionRequest,
    Project,
    Question,
    Run,
    SpecDocument,
    Stall,
    Task,
    TaskCheckRun,
    TaskIntegration,
    TaskLanding,
    TaskTransition,
    TurnUsage,
)

from .conftest import TEST_PROJECT_ID

P = TEST_PROJECT_ID
URL = f"/api/v1/projects/{P}/overview"
NOW = datetime.now(timezone.utc)


def ago(**delta: float) -> datetime:
    return NOW - timedelta(**delta)


async def _add(*rows: Any) -> None:
    async with async_session_factory() as db:
        for row in rows:
            db.add(row)
            await db.flush()
        await db.commit()


async def _read(app, auth_headers, day_start: Optional[datetime] = None) -> Dict[str, Any]:
    params = {"day_start": day_start.isoformat()} if day_start is not None else {}
    response = await app.get(URL, headers=auth_headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _task(task_id: str, **fields: Any) -> Task:
    return Task(id=task_id, project_id=P, title=fields.pop("title", f"Task {task_id}"), **fields)


def _checked() -> TaskCheckRun:
    """A finished check run, so the known-failing list counts as checked."""
    return TaskCheckRun(
        id="tcr-checked",
        project_id=P,
        task_id="t-checked",
        main_sha="a" * 40,
        target_shas=[],
        state="passed",
        results=[{"name": "hub-tests", "exit_code": 0}],
        ended_at=ago(days=2),
    )


def _could_not_run(check: str = "hub-ui", at: Optional[datetime] = None) -> TaskCheckRun:
    return TaskCheckRun(
        id=f"tcr-{check}",
        project_id=P,
        task_id="t-checked",
        main_sha="b" * 40,
        target_shas=[],
        state="failed",
        results=[
            {"name": check, "outcome": project_checks.COULD_NOT_RUN, "missing_program": "eslint"}
        ],
        started_at=at or ago(hours=1),
        ended_at=at or ago(hours=1),
    )


# --- ac-needs-kinds-ranked -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_kind_of_need_is_listed_ranked_by_urgency_then_age(
    app, auth_headers, monkeypatch
):
    from hub import slice_drafting

    await _add(
        _task("t-checked", status="approved"),
        _task("t-merge", title="Merge me", status="approved", builder="dev", assignee="dev"),
        _task("t-stalled", title="Stuck", status="in_progress", assignee="dev"),
        _task("t-review", title="Review me", status="under_review", assignee="user", builder="dev"),
        # An agent's own review is not the operator's: never a need.
        _task(
            "t-agent-review", title="QA has it", status="under_review", assignee="qa", builder="dev"
        ),
        Stall(
            id="stall-merge",
            project_id=P,
            key="integration_failed:t-merge",
            cause="integration_failed",
            reason="Approved work failed to merge",
            task_id="t-merge",
            first_seen_at=ago(minutes=5),
        ),
        Stall(
            id="stall-1",
            project_id=P,
            key="stuck_task:t-stalled",
            cause="stuck_task",
            reason="Nobody could take the task",
            task_id="t-stalled",
            first_seen_at=ago(minutes=50),
        ),
        Question(
            id="q-1",
            project_id=P,
            from_agent="arch",
            question="Which tab first?",
            created_at=ago(minutes=30),
        ),
        TaskTransition(
            id="ttr-review",
            project_id=P,
            task_id="t-review",
            from_status="completed",
            to_status="under_review",
            actor_kind="operator",
            created_at=ago(minutes=40),
        ),
        PermissionRequest(
            id="perm-1",
            project_id=P,
            agent="dev",
            tool_name="Bash",
            status="pending",
            created_at=ago(minutes=20),
        ),
        _could_not_run("hub-ui", ago(minutes=10)),
    )

    async def offers(session, workspace, project_id):
        return [
            {
                "roadmap": "spec/changes/roadmap/spec.json",
                "document_id": "spdoc-roadmap",
                "next_slice": {"key": "s3", "title": "Manager indicators"},
                "agent": "arch",
                "conversation_id": None,
            }
        ]

    monkeypatch.setattr(slice_drafting, "list_offers", offers)

    needs = (await _read(app, auth_headers))["needs"]

    kinds = [n["kind"] for n in needs]
    # A check that could not run makes main failing (FR-4), so main's own need leads.
    assert kinds == ["main", "merge", "stall", "question", "review", "permission", "check", "offer"]
    assert [n["rank"] for n in needs] == [1, 2, 3, 4, 5, 5, 6, 6]
    by_kind = {n["kind"]: n for n in needs}
    for kind in ("merge", "stall", "question", "review", "permission", "check", "offer"):
        need = by_kind[kind]
        assert need["title"], kind
        assert need["action"], kind
        assert need["target"]["type"] in {
            "thread",
            "task",
            "build",
            "permission",
            "check",
            "setting",
            "spec",
        }
    assert by_kind["question"]["agent"] == "arch"
    assert by_kind["review"]["agent"] == "dev"
    assert by_kind["permission"]["agent"] == "dev"
    assert by_kind["stall"]["agent"] == "dev"
    assert by_kind["merge"]["target"] == {
        "type": "task",
        "id": "t-merge",
        "conversation_id": None,
        "path": None,
    }
    assert by_kind["review"]["target"]["id"] == "t-review"
    # Each carries how long it has waited: the question since it was asked, the review since the
    # task entered review, the permission since it was requested.
    assert datetime.fromisoformat(by_kind["question"]["waiting_since"]) == ago(minutes=30)
    assert datetime.fromisoformat(by_kind["review"]["waiting_since"]) == ago(minutes=40)
    assert "t-agent-review" not in {n["target"]["id"] for n in needs}


@pytest.mark.asyncio
async def test_within_a_rank_the_oldest_waits_first(app, auth_headers):
    await _add(
        _task("t-review", title="Review me", status="under_review", assignee="user"),
        TaskTransition(
            id="ttr-review",
            project_id=P,
            task_id="t-review",
            from_status="completed",
            to_status="under_review",
            actor_kind="operator",
            created_at=ago(minutes=10),
        ),
        PermissionRequest(
            id="perm-old",
            project_id=P,
            agent="dev",
            tool_name="Bash",
            status="pending",
            created_at=ago(minutes=60),
        ),
        PermissionRequest(
            id="perm-new",
            project_id=P,
            agent="dev",
            tool_name="Edit",
            status="pending",
            created_at=ago(minutes=1),
        ),
        # Decided or dismissed requests wait on nobody.
        PermissionRequest(
            id="perm-done",
            project_id=P,
            agent="dev",
            tool_name="Read",
            status="allowed",
            created_at=ago(minutes=90),
        ),
        PermissionRequest(
            id="perm-gone",
            project_id=P,
            agent="dev",
            tool_name="Read",
            dismissed=True,
            created_at=ago(minutes=90),
        ),
        Question(
            id="q-new", project_id=P, from_agent="a", question="new?", created_at=ago(minutes=2)
        ),
        Question(
            id="q-old", project_id=P, from_agent="a", question="old?", created_at=ago(minutes=20)
        ),
        Question(
            id="q-answered",
            project_id=P,
            from_agent="a",
            question="done?",
            answered=True,
            created_at=ago(minutes=99),
        ),
    )

    needs = (await _read(app, auth_headers))["needs"]

    assert [n["id"] for n in needs] == [
        "question-q-old",
        "question-q-new",
        "permission-perm-old",
        "review-t-review",
        "permission-perm-new",
    ]


@pytest.mark.asyncio
async def test_a_completed_task_nobody_could_review_is_the_operators(app, auth_headers):
    await _add(
        _task("t-unstaffed", status="completed", builder="dev"),
        _task("t-routed", status="completed", builder="dev"),
        TaskTransition(
            id="ttr-u",
            project_id=P,
            task_id="t-unstaffed",
            from_status="in_progress",
            to_status="completed",
            actor_kind="run",
            created_at=ago(minutes=30),
        ),
        EventLog(
            id="ev-u",
            project_id=P,
            event_type="review_unstaffed",
            data={"task_id": "t-unstaffed", "reason": "no reviewer"},
            timestamp=ago(minutes=29),
        ),
    )

    needs = (await _read(app, auth_headers))["needs"]

    assert [n["id"] for n in needs if n["kind"] == "review"] == ["review-t-unstaffed"]


# --- ac-main-states ------------------------------------------------------------------------------


async def _main(app, auth_headers) -> Dict[str, Any]:
    return await _read(app, auth_headers)


@pytest.mark.asyncio
async def test_main_fails_on_a_fails_on_main_entry(app, auth_headers):
    await _add(
        KnownFailingTest(
            id="kf-1", project_id=P, check_name="hub-tests", test="t::a", kind="fails on main"
        ),
        KnownFailingTest(
            id="kf-2", project_id=P, check_name="hub-tests", test="t::b", kind="flaky"
        ),
    )
    body = await _main(app, auth_headers)
    assert body["main"]["state"] == "failing"
    assert body["main"]["fails_on_main"] == 1
    assert body["main"]["flaky"] == 1
    assert body["needs"][0]["kind"] == "main"


@pytest.mark.asyncio
async def test_main_fails_when_a_check_could_not_run(app, auth_headers):
    await _add(_task("t-checked"), _could_not_run())
    body = await _main(app, auth_headers)
    assert body["main"]["state"] == "failing"
    assert body["main"]["fails_on_main"] == 0
    assert "could not run" in body["main"]["detail"]


@pytest.mark.asyncio
async def test_flaky_entries_alone_leave_main_green_with_their_count(app, auth_headers):
    await _add(
        KnownFailingTest(
            id="kf-1", project_id=P, check_name="hub-tests", test="t::a", kind="flaky"
        ),
        KnownFailingTest(
            id="kf-2", project_id=P, check_name="hub-tests", test="t::b", kind="flaky"
        ),
    )
    body = await _main(app, auth_headers)
    assert body["main"]["state"] == "green"
    assert body["main"]["flaky"] == 2
    assert not [n for n in body["needs"] if n["kind"] == "main"]


@pytest.mark.asyncio
async def test_one_held_landing_makes_main_held_with_its_count(app, auth_headers):
    await _add(
        _task("t-checked"),
        _checked(),
        _task("t-held", status="approved"),
        TaskLanding(
            id="tl-held",
            project_id=P,
            task_id="t-held",
            state="held",
            order_key=1.0,
            reason="waits on t-x",
        ),
    )
    body = await _main(app, auth_headers)
    assert body["main"]["state"] == "held"
    assert body["main"]["held_landings"] == 1
    assert body["needs"][0]["kind"] == "main"


@pytest.mark.asyncio
async def test_a_list_never_checked_is_unknown_never_green(app, auth_headers):
    body = await _main(app, auth_headers)
    assert body["main"]["state"] == "unknown"
    assert body["main"]["fails_on_main"] is None
    assert body["main"]["flaky"] is None


@pytest.mark.asyncio
async def test_a_checked_list_with_nothing_wrong_is_green(app, auth_headers):
    await _add(_task("t-checked"), _checked())
    body = await _main(app, auth_headers)
    assert body["main"]["state"] == "green"
    assert body["main"]["fails_on_main"] == 0
    assert body["main"]["flaky"] == 0
    assert body["needs"] == []


@pytest.mark.asyncio
async def test_main_moved_outside_the_hub_is_a_need_not_a_failure(app, auth_headers):
    await _add(
        _task("t-checked"),
        _checked(),
        MainNotice(
            id="mn-1", project_id=P, branch="master", old_tip="a" * 40, new_tip="c" * 40, commits=[]
        ),
    )
    body = await _main(app, auth_headers)
    assert body["main"]["state"] == "green"
    assert [n["kind"] for n in body["needs"]] == ["main_moved"]
    assert body["needs"][0]["title"] == "master moved outside the Hub"


# --- ac-spend-units ------------------------------------------------------------------------------


def _usage(usage_id: str, at: datetime, **fields: Any) -> TurnUsage:
    """A turn's usage, on its own run (one usage row per run)."""
    return TurnUsage(
        id=usage_id,
        run_id=f"run-{usage_id}",
        project_id=P,
        agent="dev",
        status=fields.pop("status", "measured"),
        observed_at=at,
        **fields,
    )


@pytest.mark.asyncio
async def test_spend_comes_per_day_in_dollars_credits_or_unknown_with_the_budget(app, auth_headers):
    # The operator's local midnight, two hours ago, at UTC+02:00.
    local = timezone(timedelta(hours=2))
    day_start = (NOW - timedelta(hours=2)).astimezone(local)
    async with async_session_factory() as db:
        (await db.get(Project, P)).token_budget = 10_000
        await db.commit()
    names = ("u-today-1", "u-today-2", "u-copilot", "u-unpriced", "u-old")
    await _add(*(Run(id=f"run-{n}", project_id=P, agent="dev", status="completed") for n in names))
    await _add(
        # Today: priced Claude turns.
        _usage("u-today-1", ago(hours=1), total_tokens=1000, api_equivalent_usd_micros=1_500_000),
        _usage("u-today-2", ago(minutes=30), total_tokens=500, api_equivalent_usd_micros=250_000),
        # Yesterday: Copilot, credits only.
        _usage(
            "u-copilot",
            day_start - timedelta(hours=20),
            runner="copilot",
            total_tokens=200,
            premium_requests=3.0,
        ),
        # Two days ago: a turn nobody could price.
        _usage("u-unpriced", day_start - timedelta(hours=40), total_tokens=300),
        # Before the window: not counted per day.
        _usage(
            "u-old",
            day_start - timedelta(days=9),
            total_tokens=50,
            api_equivalent_usd_micros=9_000_000,
        ),
    )

    spend = (await _read(app, auth_headers, day_start))["spend"]

    days = spend["days"]
    assert len(days) == 7
    assert [d["day"] for d in days][-1] == day_start.date().isoformat()
    today, yesterday, before = days[-1], days[-2], days[-3]
    assert today["usd"] == 1.75 and today["tokens"] == 1500 and today["unpriced_turns"] == 0
    assert (
        yesterday["usd"] is None
        and yesterday["credits"] == 3.0
        and yesterday["unpriced_turns"] == 0
    )
    # Unknown, never $0: no dollars and no credits, and the turn counted as unpriced.
    assert before["usd"] is None and before["credits"] is None and before["unpriced_turns"] == 1
    # A day with no turns has nothing to price.
    assert days[0] == {
        "day": days[0]["day"],
        "usd": None,
        "tokens": 0,
        "credits": None,
        "unpriced_turns": 0,
    }
    assert spend["token_budget"] == {"limit": 10_000, "used": 2050}


@pytest.mark.asyncio
async def test_no_token_budget_reads_null(app, auth_headers):
    assert (await _read(app, auth_headers))["spend"]["token_budget"] is None


@pytest.mark.asyncio
async def test_a_day_start_that_is_not_a_time_is_refused(app, auth_headers):
    response = await app.get(URL, headers=auth_headers, params={"day_start": "tomorrow"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "bad_day_start"


# --- ac-running-duration -------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_running_turn_is_timed_from_its_start_not_its_threads_last_event(app, auth_headers):
    await _add(
        Conversation(
            id="conv-1", project_id=P, agent="dev", title="Fix the tiles", updated_at=ago(minutes=1)
        ),
        _task("t-run", title="Build the tiles", status="in_progress"),
        Run(
            id="run-live",
            project_id=P,
            agent="dev",
            conversation_id="conv-1",
            task_id="t-run",
            status="running",
            started_at=ago(minutes=10),
        ),
        Run(
            id="run-chat",
            project_id=P,
            agent="arch",
            conversation_id="conv-1",
            status="running",
            started_at=ago(minutes=3),
        ),
        Run(
            id="run-ended",
            project_id=P,
            agent="dev",
            status="completed",
            started_at=ago(minutes=30),
        ),
    )

    running = (await _read(app, auth_headers))["running"]

    assert [r["run_id"] for r in running] == ["run-live", "run-chat"]
    live = running[0]
    assert (
        live["agent"] == "dev"
        and live["task_id"] == "t-run"
        and live["conversation_id"] == "conv-1"
    )
    assert live["what"] == "Build the tiles"
    assert running[1]["what"] == "Fix the tiles"
    minutes = (NOW - datetime.fromisoformat(live["started_at"])).total_seconds() / 60
    assert 9.9 < minutes < 10.1


# --- ac-finished-today ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finished_lists_todays_outcomes_with_their_costs(app, auth_headers):
    day_start = ago(hours=5)
    await _add(
        _task("t-landed", title="Landed today", status="approved", builder="dev"),
        _task("t-sent", title="Sent back today", status="revision_needed", builder="dev"),
        _task("t-failed", title="Failed today", status="in_progress"),
        _task("t-stopped", title="Stopped today", status="in_progress"),
        _task("t-yesterday", title="Landed yesterday", status="approved"),
        TaskIntegration(
            id="tint-today",
            project_id=P,
            task_id="t-landed",
            outcome="merged",
            actor_kind="operator",
            created_at=ago(hours=1),
        ),
        TaskIntegration(
            id="tint-yday",
            project_id=P,
            task_id="t-yesterday",
            outcome="merged",
            actor_kind="operator",
            created_at=ago(hours=26),
        ),
        # Skipped is not landed.
        TaskIntegration(
            id="tint-skip",
            project_id=P,
            task_id="t-sent",
            outcome="skipped",
            actor_kind="operator",
            created_at=ago(hours=2),
        ),
        TaskTransition(
            id="ttr-sent",
            project_id=P,
            task_id="t-sent",
            from_status="under_review",
            to_status="revision_needed",
            actor_kind="run",
            created_at=ago(hours=2),
        ),
        Run(
            id="run-landed",
            project_id=P,
            agent="dev",
            task_id="t-landed",
            status="completed",
            ended_at=ago(hours=1, minutes=10),
        ),
        Run(
            id="run-sent",
            project_id=P,
            agent="dev",
            task_id="t-sent",
            status="completed",
            ended_at=ago(hours=3),
        ),
        Run(
            id="run-failed",
            project_id=P,
            agent="dev",
            task_id="t-failed",
            status="failed",
            ended_at=ago(hours=3),
        ),
        Run(
            id="run-stopped",
            project_id=P,
            agent="dev",
            task_id="t-stopped",
            status="stopped",
            ended_at=ago(hours=4),
        ),
        TurnUsage(
            id="u-landed",
            run_id="run-landed",
            project_id=P,
            agent="dev",
            status="measured",
            total_tokens=100,
            api_equivalent_usd_micros=2_000_000,
        ),
        TurnUsage(
            id="u-sent",
            run_id="run-sent",
            project_id=P,
            agent="dev",
            status="measured",
            total_tokens=50,
            api_equivalent_usd_micros=500_000,
        ),
        # The failed turn has no price.
        TurnUsage(
            id="u-failed",
            run_id="run-failed",
            project_id=P,
            agent="dev",
            status="measured",
            total_tokens=70,
        ),
        TurnUsage(
            id="u-stopped",
            run_id="run-stopped",
            project_id=P,
            agent="dev",
            status="measured",
            total_tokens=10,
            api_equivalent_usd_micros=100_000,
        ),
    )

    finished = (await _read(app, auth_headers, day_start))["finished"]

    by_outcome = {}
    for item in finished:
        by_outcome.setdefault(item["outcome"], []).append(item)
    assert {k: len(v) for k, v in by_outcome.items()} == {
        "landed": 1,
        "sent_back": 1,
        "failed": 1,
        "stopped": 1,
    }
    # Newest first, every one with its time.
    assert [i["title"] for i in finished] == [
        "Landed today",
        "Sent back today",
        "Failed today",
        "Stopped today",
    ]
    assert all(i["at"] for i in finished)
    landed, sent, failed, stopped = finished
    assert landed["usd"] == 2.0 and landed["tokens"] == 100 and landed["task_id"] == "t-landed"
    assert sent["usd"] == 0.5
    # Not priced: null, never $0.
    assert failed["usd"] is None and failed["credits"] is None and failed["tokens"] == 70
    assert failed["run_id"] == "run-failed"
    assert stopped["usd"] == 0.1
    assert "Landed yesterday" not in {i["title"] for i in finished}


@pytest.mark.asyncio
@pytest.mark.parametrize("offset_hours", [2, -3])
async def test_a_local_day_start_bounds_finished_and_spend_at_its_real_moment(
    app, auth_headers, offset_hours
):
    """The client sends local midnight with its offset (D6). Stored times are UTC, and SQLite
    compares a bound's wall-clock digits, so the bound must be converted before the query: a
    merge and a turn made after local midnight are today's at any offset, and one made just
    before it is not."""
    local = timezone(timedelta(hours=offset_hours))
    day_start = (NOW - timedelta(hours=3)).astimezone(local)
    await _add(
        _task("t-today", title="Merged after midnight", status="approved"),
        _task("t-before", title="Merged before midnight", status="approved"),
        TaskIntegration(
            id="tint-today",
            project_id=P,
            task_id="t-today",
            outcome="merged",
            actor_kind="operator",
            created_at=ago(hours=2),
        ),
        TaskIntegration(
            id="tint-before",
            project_id=P,
            task_id="t-before",
            outcome="merged",
            actor_kind="operator",
            created_at=ago(hours=3, minutes=10),
        ),
        Run(id="run-u-now", project_id=P, agent="dev", status="completed"),
        Run(id="run-u-early", project_id=P, agent="dev", status="completed"),
    )
    await _add(
        _usage("u-now", ago(minutes=10), total_tokens=100, api_equivalent_usd_micros=1_000_000),
        _usage(
            "u-early", ago(hours=3, minutes=10), total_tokens=7, api_equivalent_usd_micros=5_000
        ),
    )

    body = await _read(app, auth_headers, day_start)

    assert [i["title"] for i in body["finished"]] == ["Merged after midnight"]
    today, yesterday = body["spend"]["days"][-1], body["spend"]["days"][-2]
    assert today["day"] == day_start.date().isoformat()
    assert today["usd"] == 1.0 and today["tokens"] == 100
    assert yesterday["usd"] == 0.005 and yesterday["tokens"] == 7


# --- ac-build-stage ------------------------------------------------------------------------------


async def _seed_builds() -> None:
    rows: list = [
        SpecDocument(
            id="spdoc-a",
            project_id=P,
            path="spec/changes/a/spec.json",
            title="Build A",
            phase="approved",
        ),
        SpecDocument(
            id="spdoc-b",
            project_id=P,
            path="spec/changes/b/spec.json",
            title="Build B",
            phase="approved",
        ),
        Build(
            id="build-a",
            project_id=P,
            document_id="spdoc-a",
            state="running",
            driver="flow",
            level="reviewed",
        ),
        Build(
            id="build-b",
            project_id=P,
            document_id="spdoc-b",
            state="running",
            driver="flow",
            level="reviewed",
        ),
        Build(
            id="build-done",
            project_id=P,
            document_id="spdoc-b",
            state="finished",
            driver="flow",
            level="reviewed",
        ),
    ]
    for n in range(1, 9):
        rows.append(
            Task(
                id=f"ta-{n}",
                readable_id=f"A-{n}",
                project_id=P,
                title=f"A task {n}",
                status="approved",
                build_id="build-a",
                created_at=ago(hours=10 - n),
            )
        )
    rows.append(
        TaskLanding(id="tl-a8", project_id=P, task_id="ta-8", state="checking", order_key=8.0)
    )
    rows += [
        Task(
            id="tb-1",
            readable_id="B-1",
            project_id=P,
            title="B task 1",
            status="approved",
            build_id="build-b",
        ),
        Task(
            id="tb-2",
            readable_id="B-2",
            project_id=P,
            title="B task 2",
            status="in_progress",
            build_id="build-b",
        ),
        Run(
            id="run-b2",
            project_id=P,
            agent="dev",
            task_id="tb-2",
            status="running",
            started_at=ago(minutes=5),
        ),
        Question(
            id="q-b",
            project_id=P,
            from_agent="dev",
            question="Which way?",
            blocking=True,
            created_by_run_id="run-b2",
        ),
    ]
    await _add(*rows)


@pytest.mark.asyncio
async def test_builds_in_progress_say_what_each_is_doing(app, auth_headers):
    await _seed_builds()

    builds = (await _read(app, auth_headers))["builds"]

    by_id = {b["build_id"]: b for b in builds}
    assert set(by_id) == {"build-a", "build-b"}, "only running builds are in progress"
    a, b = by_id["build-a"], by_id["build-b"]
    assert (a["tasks_done"], a["tasks_total"]) == (7, 8)
    assert a["stage_words"] == "Checking task A-8"
    assert a["needs_operator"] is False
    assert a["title"] == "Build A" and a["document_path"] == "spec/changes/a/spec.json"
    assert b["stage_words"] == "Waiting for your answer"
    assert b["needs_operator"] is True
