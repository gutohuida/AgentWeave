"""A multi-task document whose tasks declare no `files` is warned on submission (F509).

Route level: an agent's submission through the submit route, as in test_spec_roadmaps.py.
"""

import subprocess
from pathlib import Path

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Run
from hub.spec_payload import SCHEMA_VERSION

AGENT_DOCS = "/api/v1/agent-actions/spec/documents"
CODE = "undeclared_task_files"


@pytest.fixture
async def planner():
    async with async_session_factory() as session:
        session.add(
            Conversation(
                id="conv-planner", project_id="proj-test", agent="planner", lifecycle="open"
            )
        )
        session.add(
            Run(
                id="run-planner",
                project_id="proj-test",
                agent="planner",
                status="running",
                turn_depth=0,
                conversation_id="conv-planner",
                capability_token_hash=hash_run_token("aw_run_planner-secret"),
            )
        )
        await session.commit()
    return {"Authorization": "Bearer aw_run_planner-secret"}


def _doc(*specs):
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "change-spec",
        "title": "A change",
        "scope": {"in_scope": ["x"], "non_goals": ["y"]},
        "requirements": [{"key": "alpha", "statement": "It responds", "modal": "MUST"}],
        "acceptance_criteria": [
            {"key": "c1", "requirement": "alpha", "given": "g", "when": "w", "then": "t"}
        ],
        "tasks": [
            {"key": key, "description": "work", "requirements": ["alpha"], **extra}
            for key, extra in specs
        ],
        "delivery": {"mode": "none"},
    }


async def _submit(app, headers, payload):
    created = await app.post(f"{AGENT_DOCS}/create", json={}, headers=headers)
    assert created.status_code == 201, created.text
    response = await app.post(
        AGENT_DOCS, json={"path": created.json()["path"], "document": payload}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _undeclared(body):
    return [w for w in body["warnings"] if w["code"] == CODE]


@pytest.mark.asyncio
async def test_three_unfiled_tasks_are_named_in_one_warning(app, planner):
    body = await _submit(app, planner, _doc(("a", {}), ("b", {}), ("c", {})))
    (warning,) = _undeclared(body)
    assert warning["where"] == "tasks"
    for key in ("'a'", "'b'", "'c'"):
        assert key in warning["message"]
    assert "files" in warning["message"] and "depends_on" in warning["message"]


@pytest.mark.asyncio
async def test_only_the_unfiled_task_is_named(app, planner):
    body = await _submit(app, planner, _doc(("filed", {"files": ["x.py"]}), ("bare", {})))
    (warning,) = _undeclared(body)
    assert "'bare'" in warning["message"]
    assert "'filed'" not in warning["message"]


@pytest.mark.asyncio
async def test_the_warning_never_blocks(app, planner):
    body = await _submit(app, planner, _doc(("a", {}), ("b", {})))
    assert _undeclared(body)
    assert body["blocking"] == []
    assert body["ready_to_propose"] is True


@pytest.mark.asyncio
async def test_the_overlap_warning_is_unchanged(app, planner):
    body = await _submit(app, planner, _doc(("a", {"files": ["x.py"]}), ("b", {"files": ["x.py"]})))
    assert [w["code"] for w in body["warnings"]] == ["unordered_file_overlap"]
    assert body["ready_to_propose"] is True


@pytest.mark.asyncio
async def test_silent_for_one_local_task(app, planner):
    assert _undeclared(await _submit(app, planner, _doc(("a", {})))) == []


@pytest.mark.asyncio
async def test_imported_entries_neither_count_nor_are_named(app, planner):
    imported = ("imp", {"from": {"document": "spec/changes/x/spec.html", "key": "k"}})
    body = await _submit(app, planner, _doc(("a", {}), imported))
    assert _undeclared(body) == []


@pytest.mark.asyncio
async def test_silent_when_every_local_task_declares_files(app, planner):
    body = await _submit(
        app,
        planner,
        _doc(("a", {"files": ["a.py"]}), ("b", {"files": ["b.py"]}), ("c", {"files": ["c.py"]})),
    )
    assert _undeclared(body) == []


def test_the_change_adds_no_migration():
    versions = Path(__file__).resolve().parents[1] / "hub" / "migrations" / "versions"
    diff = subprocess.run(
        ["git", "diff", "--name-only", "master", "--", str(versions)],
        capture_output=True,
        text=True,
        cwd=versions,
    )
    if diff.returncode != 0:
        pytest.skip("master is not resolvable here")
    assert diff.stdout.strip() == ""
