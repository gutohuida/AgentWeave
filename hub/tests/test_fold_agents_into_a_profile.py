"""Folding an agent into another agent, its profile (`fold-duplicate-agents-into-one-profile-with-
their-history-kept`, task fold-core): the fold's refusals (FR-1), its preview (FR-2), the pool merge
(FR-3), the folded record (FR-4), refusal while work runs (FR-6), re-pointing open work (FR-7) and
never into a self-check (FR-8), history kept (FR-10) and grouping by profile (FR-11).

Every fold here goes through the routes the dialog uses, `GET /agents/{name}/fold?into=` and
`POST /agents/{name}/fold`; every read back goes through the route the app reads or the row itself.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi import APIRouter
from sqlalchemy import select

from hub import dashboard_query
from hub.db.engine import async_session_factory
from hub.db.models import (
    Agent,
    AIJob,
    Build,
    Checkpoint,
    Conversation,
    EventLog,
    Loop,
    Message,
    Project,
    RequirementEvidence,
    Run,
    Task,
    TaskTransition,
)
from tests.test_migrations import (
    _create_all_at,
    _downgrade_to,
    _insert_agent,
    _run,
    _upgrade_to,
)

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
AGENTS = f"{BASE}/agents"


# ------------------------------------------------------------------------------------- helpers


async def _fold(app, headers, name: str, into: str):
    return await app.post(f"{AGENTS}/{name}/fold", json={"into": into}, headers=headers)


async def _preview(app, headers, name: str, into: str):
    return await app.get(f"{AGENTS}/{name}/fold", params={"into": into}, headers=headers)


async def _runner(app, headers, name: str, model: str) -> str:
    created = await app.post(
        f"{BASE}/runners", json={"name": name, "cli": "claude", "model": model}, headers=headers
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _set_pool(app, headers, name: str, entries: list) -> None:
    resp = await app.patch(f"{AGENTS}/{name}", json={"pool": entries}, headers=headers)
    assert resp.status_code == 200, resp.text


async def _listed(app, headers, name: str) -> dict:
    roster = (await app.get(f"{AGENTS}?lifecycle=all", headers=headers)).json()
    return next(a for a in roster if a["name"] == name)


async def _agent_rows(project_id: str = P) -> dict:
    """Every agent row's every column, by name: what "no agent record changes" compares."""
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(Agent).where(Agent.project_id == project_id))).scalars().all()
        )
        return {
            row.name: {c.name: getattr(row, c.key) for c in Agent.__table__.columns} for row in rows
        }


async def _add(*rows) -> None:
    async with async_session_factory() as db:
        for row in rows:
            db.add(row)
        await db.commit()


async def _get(model, row_id):
    """The row whose `id` is *row_id* (some history tables key on `sequence`, not `id`)."""
    async with async_session_factory() as db:
        return (await db.execute(select(model).where(model.id == row_id))).scalars().first()


def _task(task_id: str, **columns) -> Task:
    columns.setdefault("title", f"Task {task_id}")
    columns.setdefault("status", "assigned")
    return Task(id=task_id, project_id=P, readable_id=task_id.upper(), **columns)


# --------------------------------------------------------------------- FR-1: fold-refusals


@pytest.mark.asyncio
async def test_each_refusal_names_its_rule_and_changes_no_agent(app, auth_headers, add_agent):
    await _add(Project(id="proj-other", name="Other"))
    for name in ("A", "B", "C", "E"):
        await add_agent(name)
    await add_agent("D", project_id="proj-other")
    assert (await app.post(f"{AGENTS}/E/archive", headers=auth_headers)).status_code == 200
    first = await _fold(app, auth_headers, "B", "A")
    assert first.status_code == 200, first.text
    before = await _agent_rows()
    other_before = await _agent_rows("proj-other")

    cases = [
        ("A", "A", "fold_same_agent", "itself"),
        ("E", "A", "fold_source_archived", "archived"),
        ("A", "E", "fold_profile_archived", "archived"),
        ("C", "B", "fold_profile_folded", "folded into A"),
        ("A", "C", "fold_source_is_profile", "profile"),
    ]
    for name, into, code, words in cases:
        preview = await _preview(app, auth_headers, name, into)
        assert preview.status_code == 200, preview.text
        assert preview.json()["can_fold"] is False
        assert code in [r["code"] for r in preview.json()["refusals"]], (name, into)

        resp = await _fold(app, auth_headers, name, into)
        assert resp.status_code == 409, (name, into, resp.text)
        detail = resp.json()["detail"]
        assert detail["code"] == code, (name, into, detail)
        assert words in detail["message"], (name, into, detail["message"])

    # The profile in another project: not an agent of this one.
    other = await _fold(app, auth_headers, "C", "D")
    assert other.status_code == 404
    assert "own project" in other.json()["detail"]

    assert await _agent_rows() == before
    assert await _agent_rows("proj-other") == other_before

    ok = await _fold(app, auth_headers, "C", "A")
    assert ok.status_code == 200, ok.text
    assert ok.json()["folded_into"] == "A"
    assert ok.json()["lifecycle"] == "archived"


# --------------------------------------------------------- FR-2: preview-lists-differences


@pytest.mark.asyncio
async def test_preview_lists_differences_and_the_fold_keeps_the_profiles_settings(
    app, auth_headers, add_agent
):
    sonnet = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    opus = await _runner(app, auth_headers, "Claude Opus", "claude-opus-5-5")
    charters = []
    for name in ("Profile charter", "Source charter"):
        made = await app.post(
            f"{BASE}/charters", json={"name": name, "content": "Do it."}, headers=auth_headers
        )
        assert made.status_code == 201, made.text
        charters.append(made.json()["id"])
    await add_agent(
        "Dev",
        charter_id=charters[0],
        reach_grants={"read": ["docs"]},
        checkpoint_mode="auto",
        permission_timeout_seconds=600,
    )
    await add_agent(
        "DevOpus",
        charter_id=charters[1],
        can_accept_evidence=True,
        default_permission_mode="bypassPermissions",
    )
    await _set_pool(app, auth_headers, "Dev", [{"runner_id": sonnet, "default": True}])
    await _set_pool(app, auth_headers, "DevOpus", [{"runner_id": opus, "default": True}])
    await _add(
        _task("t-open-1", assignee="DevOpus"),
        _task("t-open-2", assignee="DevOpus", status="pending"),
    )
    profile_before = await _listed(app, auth_headers, "Dev")

    preview = await _preview(app, auth_headers, "DevOpus", "Dev")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_fold"] is True and body["refusals"] == []
    differences = {d["setting"]: d for d in body["setting_differences"]}
    assert differences["runner"]["source"]["model"] == "claude-opus-5-5"
    assert differences["runner"]["profile"]["model"] == "claude-sonnet-5-5"
    assert differences["charter"]["source"]["name"] == "Source charter"
    assert differences["charter"]["profile"]["name"] == "Profile charter"
    assert differences["can_accept_evidence"] == {
        "setting": "can_accept_evidence",
        "source": True,
        "profile": False,
    }
    assert differences["default_permission_mode"]["source"] == "bypassPermissions"
    assert differences["default_permission_mode"]["profile"] is None
    assert {"reach_grants", "checkpoint_policy", "permission_timeout_seconds"} <= set(differences)
    assert "can_recall" not in differences  # equal settings are not listed
    assert sorted((w["kind"], w["id"], w["field"]) for w in body["open_work"]) == [
        ("task", "t-open-1", "assignee"),
        ("task", "t-open-2", "assignee"),
    ]
    assert [e["runner_id"] for e in body["pool_entries_added"]] == [opus]
    assert body["profile_changes"] == []  # a profile with a default keeps every setting

    folded = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert folded.status_code == 200, folded.text

    profile_after = await _listed(app, auth_headers, "Dev")
    for setting in (
        "charter_id",
        "can_read_checkpoints",
        "can_recall",
        "can_accept_evidence",
        "can_admin_specs",
        "default_permission_mode",
        "reach_grants",
        "checkpoint_mode",
        "checkpoint_threshold_mode",
        "checkpoint_threshold_value",
        "checkpoint_notes_value",
        "permission_timeout_seconds",
        "question_timeout_seconds",
        "runner_id",
    ):
        assert profile_after[setting] == profile_before[setting], setting


# ---------------------------------------------------------------- FR-3: pool-gains-entries


@pytest.mark.asyncio
async def test_the_profiles_pool_gains_the_sources_entries_once(app, auth_headers, add_agent):
    sonnet = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    opus = await _runner(app, auth_headers, "Claude Opus", "claude-opus-5-5")
    await add_agent("Dev")
    await add_agent("DevOpus")
    await _set_pool(app, auth_headers, "Dev", [{"runner_id": sonnet, "default": True}])
    await _set_pool(
        app,
        auth_headers,
        "DevOpus",
        [{"runner_id": sonnet}, {"runner_id": opus, "effort": "high", "default": True}],
    )

    resp = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert resp.status_code == 200, resp.text

    pool = (await _listed(app, auth_headers, "Dev"))["pool"]
    assert [(e["runner_id"], e["effort"], e["default"]) for e in pool] == [
        (sonnet, None, True),
        (opus, "high", False),
    ]
    assert resp.json()["profile"]["pool"] == pool
    assert (await _listed(app, auth_headers, "Dev"))["runner_id"] == sonnet


@pytest.mark.asyncio
async def test_a_profile_with_no_pool_takes_a_default_and_the_preview_says_so(
    app, auth_headers, add_agent
):
    """The one setting a fold writes: a profile with no pool default (so no runner) takes the
    first added entry as its default, since a non-empty pool has exactly one. FR-2 keeps the
    profile's settings unchanged, so the preview names this change before the operator confirms."""
    sonnet = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    opus = await _runner(app, auth_headers, "Claude Opus", "claude-opus-5-5")
    await add_agent("Dev")
    await add_agent("DevOpus")
    await _set_pool(
        app,
        auth_headers,
        "DevOpus",
        [{"runner_id": opus, "default": True}, {"runner_id": sonnet}],
    )
    assert (await _listed(app, auth_headers, "Dev"))["pool"] == []
    before = (await _listed(app, auth_headers, "Dev"))["runner_id"]

    body = (await _preview(app, auth_headers, "DevOpus", "Dev")).json()
    assert body["profile_changes"] == [{"setting": "runner_id", "profile": before, "after": opus}]

    assert (await _fold(app, auth_headers, "DevOpus", "Dev")).status_code == 200
    listed = await _listed(app, auth_headers, "Dev")
    assert [(e["runner_id"], e["default"]) for e in listed["pool"]] == [
        (opus, True),
        (sonnet, False),
    ]
    assert listed["runner_id"] == opus


# ------------------------------------------------------------ FR-4: folded-record-stays


@pytest.mark.asyncio
async def test_the_folded_record_stays_and_cannot_be_reopened_or_retaken(
    app, auth_headers, add_agent
):
    runner = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    await add_agent("Dev")
    await add_agent("DevOpus")
    assert (await _fold(app, auth_headers, "DevOpus", "Dev")).status_code == 200
    record = (await _agent_rows())["DevOpus"]
    assert record["folded_into"] == "Dev" and record["lifecycle"] == "archived"

    got = await app.get(f"{AGENTS}/DevOpus", headers=auth_headers)
    assert got.status_code == 200, got.text
    assert got.json()["folded_into"] == "Dev"
    assert got.json()["lifecycle"] == "archived"
    assert (await app.get(f"{AGENTS}/Dev", headers=auth_headers)).json()["folded_into"] is None

    reopened = await app.post(f"{AGENTS}/DevOpus/unarchive", headers=auth_headers)
    assert reopened.status_code == 409
    assert reopened.json()["detail"] == {
        "code": "agent_folded",
        "message": "DevOpus was folded into Dev; address Dev instead.",
        "agent": "DevOpus",
        "folded_into": "Dev",
    }

    archived = await app.post(f"{AGENTS}/DevOpus/archive", headers=auth_headers)
    assert archived.status_code == 200
    assert "nothing changed" in archived.json()["message"]

    retaken = await app.post(
        AGENTS, json={"name": "DevOpus", "runner_id": runner}, headers=auth_headers
    )
    assert retaken.status_code == 409, retaken.text

    # A session sync that omits it does not delete it either.
    assert (await _agent_rows())["DevOpus"] == record

    open_names = [a["name"] for a in (await app.get(AGENTS, headers=auth_headers)).json()]
    archived_names = [
        a["name"]
        for a in (await app.get(f"{AGENTS}?lifecycle=archived", headers=auth_headers)).json()
    ]
    assert "DevOpus" not in open_names and "DevOpus" in archived_names


@pytest.mark.asyncio
async def test_a_session_sync_omitting_a_folded_agent_keeps_its_record(
    app, auth_headers, add_agent
):
    await add_agent("Dev")
    await add_agent("DevOpus")
    assert (await _fold(app, auth_headers, "DevOpus", "Dev")).status_code == 200
    synced = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"Dev": {}}}},
        headers=auth_headers,
    )
    assert synced.status_code in (200, 201), synced.text
    assert (await _agent_rows())["DevOpus"]["folded_into"] == "Dev"


def test_no_route_deletes_an_agent():
    """Criterion no-agent-delete: no DELETE route on `/agents/{name}`, in any router of the API."""
    import hub.api.v1 as api

    offenders = []
    for info in pkgutil.iter_modules(api.__path__):
        module = importlib.import_module(f"hub.api.v1.{info.name}")
        for value in vars(module).values():
            if not isinstance(value, APIRouter):
                continue
            for route in value.routes:
                path = getattr(route, "path", "")
                if "DELETE" in (getattr(route, "methods", None) or set()) and re.search(
                    r"/agents?/\{[^/}]+\}$", path
                ):
                    offenders.append(path)
    assert offenders == []


@pytest.mark.asyncio
async def test_a_name_stays_unique_open_archived_or_folded(app, auth_headers, add_agent):
    """Criterion name-stays-unique: the (project, name) index and the create route's 409."""
    runner = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    await add_agent("Open")
    await add_agent("Shelved")
    await add_agent("Folded")
    assert (await app.post(f"{AGENTS}/Shelved/archive", headers=auth_headers)).status_code == 200
    assert (await _fold(app, auth_headers, "Folded", "Open")).status_code == 200
    for name in ("Open", "Shelved", "Folded"):
        resp = await app.post(
            AGENTS, json={"name": name, "runner_id": runner}, headers=auth_headers
        )
        assert resp.status_code == 409, (name, resp.text)


# ------------------------------------------------------- FR-6: fold-refused-while-running


@pytest.mark.asyncio
async def test_the_fold_is_refused_while_the_source_runs_or_holds_running_build_work(
    app, auth_headers, add_agent
):
    await add_agent("Dev")
    await add_agent("DevOpus")
    await _add(
        Run(id="run-live", project_id=P, agent="DevOpus", status="running"),
        _task("t-idle", assignee="DevOpus"),
    )
    before = await _agent_rows()

    live = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert live.status_code == 409
    assert live.json()["detail"]["code"] == "fold_live_run"
    assert "run-live" in live.json()["detail"]["message"]
    assert (await _get(Task, "t-idle")).assignee == "DevOpus"
    assert await _agent_rows() == before

    async with async_session_factory() as db:
        (await db.get(Run, "run-live")).status = "completed"
        await db.commit()
    await _add(
        Build(id="build-live", project_id=P, document_id="doc-x", driver="flow", level="reviewed"),
        _task("t-building", assignee="DevOpus", status="in_progress", build_id="build-live"),
    )

    busy = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert busy.status_code == 409
    detail = busy.json()["detail"]
    assert detail["code"] == "fold_build_running"
    assert "build-live" in detail["message"] and "T-BUILDING" in detail["message"]
    assert {"build-live", "t-building"} <= set(detail["refusals"][0]["ids"])
    assert (await _get(Task, "t-idle")).assignee == "DevOpus"
    assert (await _get(Task, "t-building")).assignee == "DevOpus"
    assert await _agent_rows() == before


@pytest.mark.asyncio
async def test_queued_messages_refuse_the_fold_with_their_count(app, auth_headers, add_agent):
    from hub.db.models import InboundQueueEntry

    await add_agent("Dev")
    await add_agent("DevOpus")
    await _add(
        InboundQueueEntry(
            id="entry-q1",
            project_id=P,
            agent="DevOpus",
            origin_type="operator",
            content="hello",
            hop_depth=0,
            state="queued",
        )
    )
    resp = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "fold_queued_messages"
    assert "1 queued message" in resp.json()["detail"]["message"]


# ------------------------------------------------------------------- FR-7: open-work-moves


@pytest.mark.asyncio
async def test_open_work_moves_to_the_profile_and_finished_work_keeps_its_name(
    app, auth_headers, add_agent
):
    await add_agent("Dev")
    await add_agent("DevOpus")
    await add_agent("QA")
    await _add(
        _task("t-assigned", assignee="DevOpus"),
        _task(
            "t-built",
            assignee="QA",
            builder="DevOpus",
            builder_entry={"agent": "DevOpus", "runner_id": "runner-x", "effort": None},
        ),
        _task("t-approved", assignee="DevOpus", status="approved"),
        TaskTransition(
            id="tt-1",
            project_id=P,
            task_id="t-approved",
            from_status="under_review",
            to_status="approved",
            actor_kind="run",
            actor_agent="DevOpus",
        ),
        Build(
            id="build-open",
            project_id=P,
            document_id="doc-open",
            driver="flow",
            level="reviewed",
            state="stopped",
            builders=["DevOpus", "Dev"],
            reviewers=["DevOpus"],
            people={
                "builder": "Dev",
                "checker": "DevOpus",
                "tasks": {"k1": {"builder": "DevOpus", "checker": "QA"}},
            },
        ),
        Build(
            id="build-done",
            project_id=P,
            document_id="doc-done",
            driver="flow",
            level="reviewed",
            state="finished",
            builders=["DevOpus"],
            reviewers=[],
            people={"builder": "DevOpus", "checker": "QA", "tasks": {}},
        ),
        AIJob(
            id="job-plain",
            project_id=P,
            name="Nightly",
            agent="DevOpus",
            message="go",
            cron="0 0 * * *",
        ),
        AIJob(
            id="job-flow",
            project_id=P,
            name="Flow job",
            agent="DevOpus",
            message="go",
            cron="*/5 * * * *",
        ),
        AIJob(
            id="job-off",
            project_id=P,
            name="Disabled",
            agent="DevOpus",
            message="go",
            cron="0 0 * * *",
            enabled=False,
        ),
        Loop(id="loop-flow", project_id=P, job_id="job-flow", spec_document_id="doc-open"),
        AIJob(
            id="job-qa", project_id=P, name="QA loop", agent="QA", message="go", cron="0 * * * *"
        ),
        Loop(id="loop-staged", project_id=P, job_id="job-qa", pending_agent="DevOpus"),
    )

    resp = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert resp.status_code == 200, resp.text
    moved = {(w["kind"], w["id"], w["field"]) for w in resp.json()["repointed"]}
    assert moved == {
        ("task", "t-assigned", "assignee"),
        ("task", "t-built", "builder"),
        ("build", "build-open", "builders"),
        ("build", "build-open", "reviewers"),
        ("build", "build-open", "people.checker"),
        ("build", "build-open", "people.tasks.k1.builder"),
        ("job", "job-plain", "agent"),
        ("flow", "loop-flow", "agent"),
        ("loop", "loop-staged", "pending_agent"),
    }

    assert (await _get(Task, "t-assigned")).assignee == "Dev"
    built = await _get(Task, "t-built")
    assert built.builder == "Dev" and built.assignee == "QA"
    assert built.builder_entry == {"agent": "Dev", "runner_id": "runner-x", "effort": None}
    open_build = await _get(Build, "build-open")
    assert open_build.builders == ["Dev"]
    assert open_build.reviewers == ["Dev"]
    assert open_build.people == {
        "builder": "Dev",
        "checker": "Dev",
        "tasks": {"k1": {"builder": "Dev", "checker": "QA"}},
    }
    assert (await _get(AIJob, "job-plain")).agent == "Dev"
    assert (await _get(AIJob, "job-flow")).agent == "Dev"
    assert (await _get(Loop, "loop-staged")).pending_agent == "Dev"

    # Finished, approved and disabled work keeps the name it was done under.
    assert (await _get(Task, "t-approved")).assignee == "DevOpus"
    assert (await _get(TaskTransition, "tt-1")).actor_agent == "DevOpus"
    done = await _get(Build, "build-done")
    assert done.builders == ["DevOpus"] and done.people["builder"] == "DevOpus"
    assert (await _get(AIJob, "job-off")).agent == "DevOpus"

    async with async_session_factory() as db:
        logged = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "agent_folded")))
            .scalars()
            .all()
        )
    assert len(logged) == 1
    data = logged[0].data
    assert data["agent"] == "DevOpus" and data["folded_into"] == "Dev"
    assert {(w["kind"], w["id"], w["field"]) for w in data["repointed"]} == moved


# --------------------------------------------------------- FR-8: no-self-check-by-repoint


@pytest.mark.asyncio
async def test_a_fold_that_would_make_the_profile_check_its_own_task_is_refused(
    app, auth_headers, add_agent
):
    await add_agent("Dev")
    await add_agent("DevOpus")
    await _add(_task("t-clash", assignee="Dev", builder="Dev", checker="DevOpus"))
    before = await _agent_rows()

    preview = await _preview(app, auth_headers, "DevOpus", "Dev")
    assert [r["code"] for r in preview.json()["refusals"]] == ["fold_self_check"]

    resp = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "fold_self_check"
    assert "T-CLASH" in detail["message"]
    assert detail["refusals"][0]["ids"] == ["t-clash"]
    clash = await _get(Task, "t-clash")
    assert (clash.builder, clash.checker) == ("Dev", "DevOpus")
    assert await _agent_rows() == before


@pytest.mark.asyncio
async def test_a_build_checker_that_would_check_the_profiles_build_work_is_refused(
    app, auth_headers, add_agent
):
    """The checker the build names (`builds.checker_of`) counts, not only the task's own column."""
    await add_agent("Dev")
    await add_agent("DevOpus")
    await _add(
        Build(
            id="build-c",
            project_id=P,
            document_id="doc-c",
            driver="flow",
            level="reviewed",
            people={"builder": "Dev", "checker": "DevOpus", "tasks": {"k": {"builder": "Dev"}}},
        ),
        _task("t-k", assignee="Dev", builder="Dev", build_id="build-c", spec_task_key="k"),
    )
    resp = await _fold(app, auth_headers, "DevOpus", "Dev")
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "fold_self_check"


# ----------------------------------------------------------------- FR-10: history-unchanged


GROUP_BY_AGENT = "select agent, count(*) as runs from runs group by agent order by agent"


@pytest.mark.asyncio
async def test_history_keeps_its_names_and_still_opens(app, auth_headers, add_agent):
    await add_agent("Dev")
    await add_agent("DevOpus")
    now = datetime.now(timezone.utc)
    await _add(
        Conversation(id="conv-old", project_id=P, agent="DevOpus"),
        Run(
            id="run-old-1",
            project_id=P,
            agent="DevOpus",
            status="completed",
            conversation_id="conv-old",
            ended_at=now,
        ),
        Run(id="run-old-2", project_id=P, agent="DevOpus", status="failed", ended_at=now),
        Run(id="run-dev", project_id=P, agent="Dev", status="completed", ended_at=now),
        Checkpoint(
            id="ckpt-old",
            project_id=P,
            conversation_id="conv-old",
            agent="DevOpus",
            trigger="operator",
            status="ready",
            lineage_id="lin-1",
            body="What was decided.",
        ),
        Message(id="msg-old", project_id=P, sender="DevOpus", recipient="Dev", content="hi"),
        _task("t-done", assignee="DevOpus", status="approved"),
        TaskTransition(
            id="tt-old",
            project_id=P,
            task_id="t-done",
            from_status="in_progress",
            to_status="completed",
            actor_kind="run",
            actor_agent="DevOpus",
        ),
        RequirementEvidence(
            id="ev-old",
            project_id=P,
            requirement_id="spreq-x",
            digest="d" * 64,
            kind="test_result",
            actor_kind="agent",
            actor="DevOpus",
        ),
    )
    saved = await app.post(
        f"{BASE}/dashboards",
        json={
            "name": "Runs by agent",
            "description": "How many runs each agent made",
            "panels": [{"title": "Runs", "query": GROUP_BY_AGENT, "kind": "bar"}],
        },
        headers=auth_headers,
    )
    assert saved.status_code == 201, saved.text
    dashboard_id = saved.json()["id"]

    async def _dashboard_rows():
        ran = await app.get(f"{BASE}/dashboards/{dashboard_id}/run", headers=auth_headers)
        assert ran.status_code == 200, ran.text
        return [(p.get("columns"), p.get("rows"), p.get("error")) for p in ran.json()["panels"]]

    rows_before = await _dashboard_rows()
    assert rows_before[0][1] == [["Dev", 1], ["DevOpus", 2]]
    run_before = (await app.get(f"{BASE}/runs/run-old-1", headers=auth_headers)).json()
    chat_before = await app.get(
        f"/api/v1/projects/{P}/agent/DevOpus/chat/conv-old", headers=auth_headers
    )

    assert (await _fold(app, auth_headers, "DevOpus", "Dev")).status_code == 200

    assert await _dashboard_rows() == rows_before
    run_after = await app.get(f"{BASE}/runs/run-old-1", headers=auth_headers)
    assert run_after.status_code == 200
    assert run_after.json() == run_before and run_after.json()["agent"] == "DevOpus"
    chat_after = await app.get(
        f"/api/v1/projects/{P}/agent/DevOpus/chat/conv-old", headers=auth_headers
    )
    assert chat_after.status_code == chat_before.status_code == 200
    for model, row_id, column in (
        (Run, "run-old-1", "agent"),
        (Run, "run-old-2", "agent"),
        (Conversation, "conv-old", "agent"),
        (Checkpoint, "ckpt-old", "agent"),
        (Message, "msg-old", "sender"),
        (TaskTransition, "tt-old", "actor_agent"),
        (RequirementEvidence, "ev-old", "actor"),
        (Task, "t-done", "assignee"),
    ):
        assert getattr(await _get(model, row_id), column) == "DevOpus", (model, row_id)


# -------------------------------------------------------------- FR-10: no-fold-no-change


def test_the_migration_adds_one_null_column_and_changes_no_row(tmp_path) -> None:
    db_file = tmp_path / "fold.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    _run(_create_all_at(db_url))
    with sqlite3.connect(db_file) as conn:
        conn.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        conn.execute("INSERT INTO alembic_version (version_num) VALUES ('0188')")
        conn.commit()
    _downgrade_to(db_url, "0187")
    with sqlite3.connect(db_file) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info('agents')")}
        assert "folded_into" not in columns
        conn.execute(
            "INSERT INTO projects (id, name, created_at) VALUES ('proj-m', 'M', '2026-11-20')"
        )
        _insert_agent(conn, "agent-1", "proj-m", "Dev")
        _insert_agent(conn, "agent-2", "proj-m", "QA")
        conn.commit()
        before = conn.execute("SELECT * FROM agents ORDER BY id").fetchall()

    _upgrade_to(db_url, "0188")

    with sqlite3.connect(db_file) as conn:
        names = [row[1] for row in conn.execute("PRAGMA table_info('agents')")]
        assert names[-1] == "folded_into" or "folded_into" in names
        rows = conn.execute(
            f"SELECT {', '.join(n for n in names if n != 'folded_into')}, folded_into "
            "FROM agents ORDER BY id"
        ).fetchall()
    assert [row[:-1] for row in rows] == before
    assert [row[-1] for row in rows] == [None, None]

    _upgrade_to(db_url, "0188")  # idempotent
    _downgrade_to(db_url, "0187")
    with sqlite3.connect(db_file) as conn:
        assert "folded_into" not in {row[1] for row in conn.execute("PRAGMA table_info('agents')")}
        assert conn.execute("SELECT * FROM agents ORDER BY id").fetchall() == before


# ---------------------------------------------------------------- FR-11: group-by-profile


GROUP_BY_PROFILE = (
    "select coalesce(a.folded_into, a.name) as profile, count(*) as runs "
    "from runs r join agents a on a.name = r.agent group by profile order by profile"
)


@pytest.mark.asyncio
async def test_a_query_groups_runs_by_profile(app, auth_headers, add_agent):
    for name in ("Dev", "DevOpus", "DevSonnet", "Arch"):
        await add_agent(name)
    now = datetime.now(timezone.utc)
    runs = {"Dev": 1, "DevOpus": 2, "DevSonnet": 3, "Arch": 4}
    await _add(
        *(
            Run(id=f"run-{name}-{i}", project_id=P, agent=name, status="completed", ended_at=now)
            for name, count in runs.items()
            for i in range(count)
        )
    )
    for name in ("DevOpus", "DevSonnet"):
        assert (await _fold(app, auth_headers, name, "Dev")).status_code == 200

    result = await dashboard_query.run_query(P, GROUP_BY_PROFILE)
    assert result["rows"] == [["Arch", 4], ["Dev", 6]]
    by_agent = await dashboard_query.run_query(P, GROUP_BY_AGENT)
    assert by_agent["rows"] == [["Arch", 4], ["Dev", 1], ["DevOpus", 2], ["DevSonnet", 3]]

    reference = dashboard_query.query_reference(["agents"])
    table = next(t for t in reference["tables"] if t["name"] == "agents")
    column = next(c for c in table["columns"] if c["name"] == "folded_into")
    assert "coalesce(folded_into, name)" in column["meaning"]
