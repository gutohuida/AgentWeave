"""F771 -- a reviewer is told which of the document's requirements are another task's.

Found in the tasks sweep (2026-10-19): `t-clamp` served FR-1 and `t-sub` served FR-2. The reviewer read
the whole document, saw FR-2 unmet, and sent correct work back twice ("sub() is entirely missing").
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument, Task
from hub.review_turn import verdict_evidence_sentence
from hub.spec_payload import SCHEMA_VERSION

from ._spec_files import stored_text
from .test_agent_trigger import _init_repo

pytestmark = pytest.mark.asyncio


async def _document(repo, tasks):
    document = repo / "spec" / "changes" / "c" / "spec.json"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        stored_text(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "requirements": [{"key": "FR-1"}, {"key": "FR-2"}],
                "tasks": tasks,
                "delivery": {"mode": "flow", "agent": "builder"},
            },
            phase="approved",
        ),
        encoding="utf-8",
    )
    async with async_session_factory() as db:
        db.add(
            SpecDocument(
                id="doc-f771",
                project_id="proj-test",
                path="spec/changes/c/spec.json",
                title="F771",
                phase="approved",
                kind="change-spec",
            )
        )
        await db.commit()
        for key, title in (("t-clamp", "Fix clamp upper bound"), ("t-sub", "Add sub()")):
            db.add(
                Task(
                    id=f"task-f771-{key}",
                    project_id="proj-test",
                    title=title,
                    status="under_review" if key == "t-clamp" else "pending",
                    spec_document_id="doc-f771",
                    spec_task_key=key,
                )
            )
        await db.commit()


async def _sentence(task_id="task-f771-t-clamp"):
    async with async_session_factory() as session:
        task = await session.get(Task, task_id)
        return await verdict_evidence_sentence(session, task, may_decide=False) or ""


TWO_TASKS = [
    {"key": "t-clamp", "requirements": ["FR-1"]},
    {"key": "t-sub", "requirements": ["FR-2"]},
]


async def test_the_other_tasks_requirement_is_named_as_theirs(
    app, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _document(repo, TWO_TASKS)
    sentence = await _sentence()
    assert "FR-1" in sentence
    assert "FR-2" in sentence and "task-f771-t-sub" in sentence and "Add sub()" in sentence
    assert "do not send this task back" in sentence


async def test_a_requirement_both_tasks_serve_is_not_called_the_others(
    app, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _document(
        repo,
        [
            {"key": "t-clamp", "requirements": ["FR-1", "FR-2"]},
            {"key": "t-sub", "requirements": ["FR-2"]},
        ],
    )
    assert "belong to other tasks" not in await _sentence()


async def test_a_document_with_one_task_says_nothing_new(app, bind_project_workspace, tmp_path):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _document(repo, [{"key": "t-clamp", "requirements": ["FR-1", "FR-2"]}])
    assert "belong to other tasks" not in await _sentence()
