"""The acceptance drive of `amendments-main-watch-and-the-next-slice` (slice D2, Tier 2).

Written first and red on master c281c26, one case per task that closes it:

* `lead_amendment` -- the lead of a running build proposes a task; nothing moves until the operator
  accepts it, and then it is in the build and the flow's next firing stages it. On master the
  lead's call is refused 403 ("only a run testing a task of this document may amend it").
* `hand_commit` -- a commit made on main by hand is raised as an open main notice naming it. On
  master the watch looks only at projects with checks and tells nobody.
* `offer` -- when a slice's last task closes, drafting the next slice is offered and nothing is
  queued. On master there is no offer; with `draft_next_slice` the turn was queued at once.
"""

import pytest
from sqlalchemy import select

from hub import project_checks
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, InboundQueueEntry, Project

from .test_a_lead_hands_out_the_work import (
    AGENT_DOCS,
    BASE,
    PATH,
    _approved,
    _build,
    _rows,
    _run_headers,
    _scheduling,
    _tasks,
    _tick,
)
from .test_review_turn import _roster
from .test_spec_roadmaps import (  # noqa: F401 -- fixtures
    _approve,
    _approved_roadmap_doc,
    _move,
    _proposed_slice,
    _settle,
    planner,
    scheduled,
)
from .test_task_integration import git, make_repo, set_main_branch

AMEND = f"{AGENT_DOCS}/amend"
PROJECT = "/api/v1/projects/proj-test"


# ---------------------------------------------------------------------------------------------
# lead-amendment-joins-running-build
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lead_amendment_waits_for_the_operator_then_joins_the_running_build(
    app, auth_headers, bind_runner
):
    await _roster(app, auth_headers, bind_runner, "lead", "dev", "dev2", "dev3")
    await _approved(app, auth_headers)
    outcome = await _build(
        app,
        auth_headers,
        driver="flow",
        lead="lead",
        builders=["dev", "dev2", "dev3"],
        level="reviewed",
    )
    build_id = outcome["build"]["id"]
    before = set(await _tasks())
    document_before = (
        await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    ).json()["content_version"]

    lead = await _run_headers("run-lead-amend", "lead")
    proposed = await app.post(
        AMEND,
        json={
            "path": PATH,
            "op": "add_task",
            "reason": "gamma is needed before beta can be checked",
            "how_to_check": "pytest -k gamma",
            "task": {
                "key": "t3",
                "title": "Build gamma",
                "description": "Build gamma",
                "requirements": ["alpha"],
            },
        },
        headers=lead,
    )

    # Master: 403 "only a run testing a task of this document may amend it".
    assert proposed.status_code == 201, proposed.text
    amendment_id = proposed.json()["id"]
    assert proposed.json()["state"] == "proposed"
    # Proposed changes neither the document nor the board.
    assert set(await _tasks()) == before
    assert (await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)).json()[
        "content_version"
    ] == document_before
    listed = (await app.get(f"{BASE}/documents/{PATH}/amendments", headers=auth_headers)).json()[
        "amendments"
    ]
    (row,) = [a for a in listed if a["id"] == amendment_id]
    assert (row["state"], row["author"], row["op"]) == ("proposed", "lead", "add_task")
    assert row["how_to_check"] == "pytest -k gamma"

    with _scheduling():
        accepted = await app.post(
            f"{BASE}/documents/{PATH}/amendments/{amendment_id}/accept", headers=auth_headers
        )
    assert accepted.status_code == 200, accepted.text

    tasks = await _tasks()
    assert set(tasks) == before | {"t3"}
    assert (tasks["t3"].build_id, tasks["t3"].level) == (build_id, "reviewed")
    for _ in range(3):
        await _tick()
    staged = await _rows(InboundQueueEntry, InboundQueueEntry.task_id == tasks["t3"].id)
    assert staged, "the flow's next firing stages the accepted task"
    # The proposer is told the decision.
    told = await _rows(InboundQueueEntry, InboundQueueEntry.agent == "lead")
    assert any(amendment_id in entry.content and "accepted" in entry.content for entry in told)


# ---------------------------------------------------------------------------------------------
# hand-commit-raised
# ---------------------------------------------------------------------------------------------


def _tip(root):
    return git(root, "rev-parse", "main").stdout.strip()


@pytest.mark.asyncio
async def test_a_hand_commit_on_main_is_raised(app, auth_headers, tmp_path):
    make_repo(tmp_path)
    await set_main_branch("main")
    async with async_session_factory() as session:
        assert not (await session.get(Project, "proj-test")).checks, "no checks: watched anyway"

    await project_checks.watch_main_once()  # the first look records the tip, raising nothing
    old = _tip(tmp_path)
    (tmp_path / "by-hand.txt").write_text("by hand\n", encoding="utf-8")
    git(tmp_path, "add", "by-hand.txt")
    git(
        tmp_path,
        "-c",
        "user.name=Hand Person",
        "-c",
        "user.email=hand@example.com",
        "commit",
        "-q",
        "-m",
        "A change made by hand",
    )
    new = _tip(tmp_path)

    await project_checks.watch_main_once()

    assert project_checks.WATCH_SECONDS <= 60
    response = await app.get(f"{PROJECT}/main-notices", headers=auth_headers)
    # Master: 404, and nothing recorded.
    assert response.status_code == 200, response.text
    (notice,) = response.json()["notices"]
    assert (notice["old_tip"], notice["new_tip"]) == (old, new)
    assert notice["rewrite"] is False
    (commit,) = notice["commits"]
    assert new.startswith(commit["sha"])
    assert commit["subject"] == "A change made by hand"
    assert commit["author"] == "Hand Person"
    async with async_session_factory() as session:
        events = (
            (await session.execute(select(EventLog).where(EventLog.event_type == "main_moved")))
            .scalars()
            .all()
        )
    assert len(events) == 1


# ---------------------------------------------------------------------------------------------
# offer-not-queued
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_next_slice_is_offered_not_queued(
    app, auth_headers, planner, scheduled  # noqa: F811
):
    roadmap_path, _ = await _approved_roadmap_doc(app, auth_headers, planner)
    slice_path = await _proposed_slice(app, auth_headers, planner, roadmap_path)
    approved = await _approve(app, auth_headers, slice_path)
    assert approved.status_code == 200, approved.text
    (task_id,) = approved.json()["tasks_created"]

    await _move(app, auth_headers, task_id, "in_progress", "completed", "under_review", "approved")
    await _settle()

    offers = await app.get(f"{BASE}/next-slice-offers", headers=auth_headers)
    # Master: 404 -- there is no offer; a requested drafting turn was queued at once instead.
    assert offers.status_code == 200, offers.text
    (offer,) = offers.json()["offers"]
    assert offer["document"] == slice_path
    assert offer["next_slice"]["key"] == "s2"
    assert offer["agent"] == "planner"
    async with async_session_factory() as session:
        assert (await session.execute(select(InboundQueueEntry))).scalars().first() is None
        notified = (
            (
                await session.execute(
                    select(EventLog).where(EventLog.event_type == "next_slice_offered")
                )
            )
            .scalars()
            .all()
        )
    assert len(notified) == 1
    assert scheduled == []
