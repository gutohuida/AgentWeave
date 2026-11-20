"""A spec task recommends a pool entry and Build chooses one (`a-profile-runs-each-task-on-a-runner-
and-model-chosen-from-its-pool`, task `spec-and-build-choice`).

A task may name a pool entry for its builder and its checker; one its profile's pool lacks is kept
and warned of, naming the task and the entry (FR-5). The recommendation read carries the entries
and their reasons. A Build naming an entry outside the pool of the agent a task resolves to is
refused naming the task and the entry, and nothing is created or moved; one inside it is stored on
the build for the launch path to read (FR-6).

Named by acceptance criterion: `-k warns_outside_pool`, `-k refuses_outside_pool`,
`-k recommendation`.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select

from hub import builds
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, SpecDocument, Task
from hub.spec_payload import SCHEMA_VERSION

from ._spec_confirmations import confirm_criteria

P = "proj-test"
API = f"/api/v1/projects/{P}"
BASE = f"{API}/project"
AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
PATH = "spec/changes/build-pool-choice/spec.json"


def _scheduling():
    return patch(
        "hub.turn_scheduler.schedule_agent",
        AsyncMock(return_value=MagicMock(waiting_reason=None, terminal_failure=False)),
    )


async def _runner(app, auth_headers, name, model, cli="claude"):
    created = await app.post(
        f"{API}/runners", json={"name": name, "cli": cli, "model": model}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _pool(app, auth_headers, agent, entries):
    resp = await app.patch(f"{API}/agents/{agent}", json={"pool": entries}, headers=auth_headers)
    assert resp.status_code == 200, resp.text


@pytest.fixture
async def runners(app, auth_headers, add_agent):
    """`dev` may run on Haiku (default), Sonnet and Sonnet high; `qa` on Sonnet only. Neither
    holds Opus."""
    haiku = await _runner(app, auth_headers, "Claude Haiku", "claude-haiku-5-5")
    sonnet = await _runner(app, auth_headers, "Claude Sonnet", "claude-sonnet-5-5")
    opus = await _runner(app, auth_headers, "Claude Opus", "claude-opus-5-5")
    await add_agent("dev")
    await add_agent("qa")
    await _pool(
        app,
        auth_headers,
        "dev",
        [
            {"runner_id": haiku, "default": True},
            {"runner_id": sonnet},
            {"runner_id": sonnet, "effort": "high"},
        ],
    )
    await _pool(app, auth_headers, "qa", [{"runner_id": sonnet, "default": True}])
    return {"haiku": haiku, "sonnet": sonnet, "opus": opus}


async def _author_headers(run_id="run-pool-author"):
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id=run_id,
                project_id=P,
                agent="author",
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()
    return {"Authorization": f"Bearer {token}"}


def _document(tasks):
    keys = [task["key"] for task in tasks]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "Build pool choice",
        "problem": "A task cannot say which model it runs on.",
        "scope": {"in_scope": ["the thing"], "non_goals": ["the other thing"]},
        "requirements": [
            {"key": f"r-{key}", "statement": f"It does {key}", "modal": "MUST"} for key in keys
        ],
        "acceptance_criteria": [
            {
                "key": f"c-{key}",
                "requirement": f"r-{key}",
                "given": "g",
                "when": "w",
                "then": "t",
                "how_to_check": "pytest",
                "checked_by": "agent",
            }
            for key in keys
        ],
        "tasks": [
            {
                "description": f"Build {task['key']}",
                "requirements": [f"r-{task['key']}"],
                "builder": "dev",
                "builder_reason": "It builds.",
                "checker": "qa",
                "checker_reason": "It checks.",
                **task,
            }
            for task in tasks
        ],
        "delivery": {
            "mode": "flow",
            "agent": "dev",
            "checker": "qa",
            "stop_when_queue_empties": True,
            "cron": "*/10 * * * *",
        },
    }


async def _save(app, auth_headers, document):
    created = await app.post(
        f"{BASE}/documents", json={"path": PATH, "title": "Pool"}, headers=auth_headers
    )
    assert created.status_code == 201, created.text
    author = await _author_headers()
    saved = await app.post(AGENT_DOCS, json={"path": PATH, "document": document}, headers=author)
    assert saved.status_code == 200, saved.text
    async with async_session_factory() as db:  # the author's turn is over
        (await db.get(Run, "run-pool-author")).status = "completed"
        await db.commit()
    return saved.json()


async def _approved(app, auth_headers, document):
    await _save(app, auth_headers, document)
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    await confirm_criteria(PATH)
    approved = await app.post(
        f"{BASE}/documents/phase",
        params={"path": PATH, "to": "approved"},
        json={
            "reason": "",
            "approve_anyway": True,
            "content_version": read.json()["content_version"],
        },
        headers=auth_headers,
    )
    assert approved.status_code == 200, approved.text


async def _post_build(app, auth_headers, **choices):
    with _scheduling():
        return await app.post(
            f"{BASE}/documents/build", params={"path": PATH}, json=choices, headers=auth_headers
        )


async def _counts():
    async with async_session_factory() as db:
        build_rows = (await db.execute(select(func.count()).select_from(Build))).scalar_one()
        run_rows = (await db.execute(select(func.count()).select_from(Run))).scalar_one()
        tasks = (
            (await db.execute(select(Task).where(Task.project_id == P).order_by(Task.id)))
            .scalars()
            .all()
        )
        return build_rows, run_rows, [(t.id, t.status, t.assignee, t.build_id) for t in tasks]


def _pool_warnings(answer):
    return [w for w in answer["warnings"] if w["code"] == "pool_entry_outside_pool"]


# ---------------------------------------------------------------- FR-5: the spec's recommendation


@pytest.mark.asyncio
async def test_spec_save_warns_outside_pool_and_keeps_the_entry(app, auth_headers, runners):
    answer = await _save(
        app,
        auth_headers,
        _document(
            [
                {"key": "heavy", "builder_entry": {"runner_id": runners["opus"], "effort": "high"}},
                {"key": "light", "builder_entry": {"runner_id": runners["sonnet"]}},
            ]
        ),
    )

    warned = _pool_warnings(answer)
    assert len(warned) == 1, answer["warnings"]
    assert warned[0]["where"] == "tasks.heavy.builder_entry"
    assert "'heavy'" in warned[0]["message"]
    assert "Opus 5.5 · high" in warned[0]["message"]
    assert "dev's pool" in warned[0]["message"]
    # Kept, not refused: the stored document still carries it.
    async with async_session_factory() as db:
        document = (
            await db.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        assert document.phase == "exploring"
    read = await app.get(
        AGENT_DOCS,
        params={"path": PATH, "include": "full"},
        headers=await _author_headers("run-pool-reader"),
    )
    assert read.status_code == 200, read.text
    stored = {t["key"]: t for t in read.json()["tasks"]}
    assert stored["heavy"]["builder_entry"] == {"runner_id": runners["opus"], "effort": "high"}
    assert stored["light"]["builder_entry"] == {"runner_id": runners["sonnet"]}


@pytest.mark.asyncio
async def test_spec_save_warns_outside_pool_for_the_checker_by_its_own_pool(
    app, auth_headers, runners
):
    # Haiku is in dev's pool but not qa's: the checker's entry is judged by the checker's pool.
    answer = await _save(
        app,
        auth_headers,
        _document([{"key": "only", "checker_entry": {"runner_id": runners["haiku"]}}]),
    )
    warned = _pool_warnings(answer)
    assert [w["where"] for w in warned] == ["tasks.only.checker_entry"]
    assert "qa's pool" in warned[0]["message"] and "Haiku" in warned[0]["message"]


@pytest.mark.asyncio
async def test_spec_save_warns_outside_pool_never_gates_approval(app, auth_headers, runners):
    await _approved(
        app,
        auth_headers,
        _document([{"key": "only", "builder_entry": {"runner_id": runners["opus"]}}]),
    )
    async with async_session_factory() as db:
        document = (
            await db.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        assert document.phase == "approved"


@pytest.mark.asyncio
async def test_recommendation_read_carries_entries_and_their_reasons(app, auth_headers, runners):
    await _save(
        app,
        auth_headers,
        _document(
            [
                {
                    "key": "heavy",
                    "builder_entry": {
                        "runner_id": runners["sonnet"],
                        "effort": "high",
                        "reason": "Multi-file.",
                    },
                    "checker_entry": {"runner_id": runners["sonnet"]},
                },
                {"key": "light"},
            ]
        ),
    )
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    recommended = read.json()["recommended_build"]
    assert recommended["task_builder_entries"] == {
        "heavy": {"runner_id": runners["sonnet"], "effort": "high"},
        "light": None,
    }
    assert recommended["task_checker_entries"] == {
        "heavy": {"runner_id": runners["sonnet"], "effort": None},
        "light": None,
    }
    assert recommended["task_reasons"]["heavy"]["builder_entry"] == "Multi-file."
    assert "checker_entry" not in recommended["task_reasons"]["heavy"]


# ---------------------------------------------------------------- FR-6: the operator's choice


@pytest.mark.asyncio
async def test_build_refuses_outside_pool_and_starts_nothing(app, auth_headers, runners):
    await _approved(app, auth_headers, _document([{"key": "one"}, {"key": "two"}]))
    before = await _counts()

    resp = await _post_build(
        app,
        auth_headers,
        task_builder_entries={
            "one": {"runner_id": runners["sonnet"], "effort": None},
            "two": {"runner_id": runners["opus"], "effort": None},
        },
    )

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "entry_outside_pool"
    assert "'two'" in detail["message"] and "Opus 5.5" in detail["message"]
    assert "dev's pool" in detail["message"]
    assert await _counts() == before
    assert before[0] == 0


@pytest.mark.asyncio
async def test_build_refuses_outside_pool_by_the_agent_chosen_in_the_dialog(
    app, auth_headers, runners
):
    # Haiku is in dev's pool; the operator moved the task to qa, whose pool lacks it.
    await _approved(app, auth_headers, _document([{"key": "one"}]))
    resp = await _post_build(
        app,
        auth_headers,
        builder="qa",
        checker="dev",
        task_builders={"one": "qa"},
        task_checkers={"one": "dev"},
        task_builder_entries={"one": {"runner_id": runners["haiku"]}},
    )
    assert resp.status_code == 422, resp.text
    assert "qa's pool" in resp.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_build_refuses_outside_pool_for_a_checker(app, auth_headers, runners):
    await _approved(app, auth_headers, _document([{"key": "one"}]))
    resp = await _post_build(
        app,
        auth_headers,
        task_checker_entries={"one": {"runner_id": runners["haiku"], "effort": None}},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "'one'" in detail["message"] and "qa's pool" in detail["message"]
    assert "checker" in detail["message"]


@pytest.mark.asyncio
async def test_build_refuses_outside_pool_for_an_undeclared_task(app, auth_headers, runners):
    await _approved(app, auth_headers, _document([{"key": "one"}]))
    resp = await _post_build(
        app, auth_headers, task_builder_entries={"ghost": {"runner_id": runners["haiku"]}}
    )
    assert resp.status_code == 422, resp.text
    assert "'ghost'" in resp.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_approve_and_build_refuses_outside_pool_before_approving(app, auth_headers, runners):
    await _save(app, auth_headers, _document([{"key": "one"}]))
    read = await app.get(f"{BASE}/spec", params={"path": PATH}, headers=auth_headers)
    await confirm_criteria(PATH)
    with _scheduling():
        resp = await app.post(
            f"{BASE}/documents/approve-and-build",
            params={"path": PATH},
            json={
                "approve_anyway": True,
                "content_version": read.json()["content_version"],
                "task_builder_entries": {"one": {"runner_id": runners["opus"]}},
            },
            headers=auth_headers,
        )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["code"] == "entry_outside_pool"
    async with async_session_factory() as db:
        document = (
            await db.execute(select(SpecDocument).where(SpecDocument.path == PATH))
        ).scalar_one()
        assert document.phase == "exploring"
        assert (await db.execute(select(func.count()).select_from(Task))).scalar_one() == 0


@pytest.mark.asyncio
async def test_build_stores_the_chosen_entries_on_the_build(app, auth_headers, runners):
    await _approved(app, auth_headers, _document([{"key": "one"}, {"key": "two"}]))

    resp = await _post_build(
        app,
        auth_headers,
        task_builder_entries={
            "one": {"runner_id": runners["sonnet"], "effort": "high"},
            "two": {"runner_id": runners["haiku"], "effort": None},
        },
        task_checker_entries={"one": {"runner_id": runners["sonnet"], "effort": None}},
    )

    assert resp.status_code == 200, resp.text
    people = resp.json()["build_outcome"]["build"]["tasks"]
    assert people["one"]["builder_entry"] == {"runner_id": runners["sonnet"], "effort": "high"}
    assert people["one"]["checker_entry"] == {"runner_id": runners["sonnet"], "effort": None}
    assert people["two"]["builder_entry"] == {"runner_id": runners["haiku"], "effort": None}
    assert "checker_entry" not in people["two"]
    async with async_session_factory() as db:
        build = (await db.execute(select(Build))).scalar_one()
        one = (await db.execute(select(Task).where(Task.spec_task_key == "one"))).scalar_one()
        two = (await db.execute(select(Task).where(Task.spec_task_key == "two"))).scalar_one()
        assert builds.chosen_entry(build, one, "builder") == {
            "runner_id": runners["sonnet"],
            "effort": "high",
        }
        assert builds.chosen_entry(build, two, "checker") is None


@pytest.mark.asyncio
async def test_build_at_fast_drops_checker_entries(app, auth_headers, runners):
    await _approved(app, auth_headers, _document([{"key": "one"}]))
    resp = await _post_build(
        app,
        auth_headers,
        level="fast",
        checker="",
        task_checkers={},
        task_checker_entries={"one": {"runner_id": runners["opus"]}},
    )
    assert resp.status_code == 200, resp.text
    assert "checker_entry" not in resp.json()["build_outcome"]["build"]["tasks"]["one"]


@pytest.mark.asyncio
async def test_build_with_no_entries_is_unchanged(app, auth_headers, runners):
    await _approved(app, auth_headers, _document([{"key": "one"}]))
    resp = await _post_build(app, auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["build_outcome"]["build"]["tasks"]["one"] == {
        "builder": "dev",
        "checker": "qa",
    }
