"""`a-document-names-its-default-reviewer` (F508's default half).

A change-spec document's `delivery.reviewer` is the reviewer of every task whose own entry names
none. It is a declaration like the task's own `reviewer`, so it gets rung 1b's rule: a name that
does not resolve is surfaced, never substituted. `aaa-stub` below is free and sorts first, which is
the agent rung 2 ("any free agent", roster by name) picks when nothing is declared — F508's leftover
stub agent.
"""

import pytest
from sqlalchemy import update

from hub import review_turn
from hub.api.v1.agents import SPEC_PHASE_DUTIES
from hub.db.engine import async_session_factory
from hub.db.models import Agent
from hub.scheduler import resolve_reviewer
from hub.spec_payload import SCHEMA_VERSION, embed_payload, validate_payload

from .test_a_document_says_how_it_will_be_built import (
    BASE,
    FLOW,
    _agent,
    _create,
    _document,
    _submit_document,
    run_headers,  # noqa: F401 - fixture
)
from .test_agent_trigger import _init_repo
from .test_review_turn import _roster
from .test_reviewer_ladder import AUTHOR, _task
from .test_spec_reviewer_undeclared_warning import _flow, _warned
from .test_spec_undeclared_files_warning import _submit, planner  # noqa: F401 - fixture

pytestmark = pytest.mark.asyncio


async def _document_declaring(repo, db, *, default=None, task_reviewer=None):
    """A document on disk whose task `t1` names *task_reviewer* and whose delivery names *default*.

    Written with the real `embed_payload`, as `test_reviewer_ladder._declare_reviewer` is.
    """
    from hub.db.models import SpecDocument

    task = {"key": "t1", **({"reviewer": task_reviewer} if task_reviewer else {})}
    delivery = {"mode": "flow", "agent": AUTHOR, "stop_when_queue_empties": True}
    if default:
        delivery["reviewer"] = default
    document = repo / "spec" / "changes" / "c" / "spec.html"
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text(
        embed_payload(
            {
                "schema_version": SCHEMA_VERSION,
                "kind": "change-spec",
                "tasks": [task],
                "delivery": delivery,
            }
        ),
        encoding="utf-8",
    )
    db.add(
        SpecDocument(
            id="doc-default",
            project_id="proj-test",
            path="spec/changes/c/spec.html",
            title="Default reviewer",
            phase="approved",
            kind="change-spec",
        )
    )
    await db.commit()


async def _choose(db, task):
    return await resolve_reviewer(
        db, task, project_id="proj-test", exclude={AUTHOR: "is the one that completed this task"}
    )


def test_delivery_carries_a_reviewer():
    payload = validate_payload(
        {
            "schema_version": SCHEMA_VERSION,
            "kind": "change-spec",
            "title": "t",
            "delivery": {**FLOW, "reviewer": "critic"},
        }
    )
    assert payload.delivery.reviewer == "critic"


async def test_the_default_reviewer_staffs_a_task_that_names_none(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "aaa-stub", "critic")

    async with async_session_factory() as db:
        await _document_declaring(repo, db, default="critic")
        task = await _task(db, document_id="doc-default", task_key="t1")
        choice = await _choose(db, task)

    assert (choice.agent, choice.rung) == ("critic", "declared")


@pytest.mark.parametrize("missing", ["unknown", "archived"])
async def test_a_default_that_does_not_resolve_is_surfaced_never_substituted(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, missing
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    names = [AUTHOR, "aaa-stub"] + (["critic"] if missing == "archived" else [])
    await _roster(app, auth_headers, bind_runner, *names)

    async with async_session_factory() as db:
        if missing == "archived":
            await db.execute(
                update(Agent)
                .where(Agent.project_id == "proj-test", Agent.name == "critic")
                .values(lifecycle="archived")
            )
        await _document_declaring(repo, db, default="critic")
        task = await _task(db, document_id="doc-default", task_key="t1")
        resolution = await review_turn.resolve_declared_reviewer(
            db, project_id="proj-test", task=task
        )
        choice = await _choose(db, task)

    assert resolution.declared == "critic" and resolution.agent is None
    assert "this document's default reviewer" in resolution.unresolved
    assert "this task's reviewer" not in resolution.unresolved
    assert (choice.agent, choice.rung) == (None, "unresolved")


async def test_the_tasks_own_reviewer_wins_over_the_default(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "auditor", "critic")

    async with async_session_factory() as db:
        await _document_declaring(repo, db, default="critic", task_reviewer="auditor")
        task = await _task(db, document_id="doc-default", task_key="t1")
        choice = await _choose(db, task)

    assert (choice.agent, choice.rung) == ("auditor", "declared")


async def test_no_default_and_no_task_reviewer_is_still_any_free_agent(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    await _roster(app, auth_headers, bind_runner, AUTHOR, "aaa-stub", "critic")

    async with async_session_factory() as db:
        await _document_declaring(repo, db)
        task = await _task(db, document_id="doc-default", task_key="t1")
        choice = await _choose(db, task)

    assert (choice.agent, choice.rung) == ("aaa-stub", "available")


async def test_a_default_reviewer_quiets_the_undeclared_warning(app, planner):  # noqa: F811
    payload = _flow(("a", {"files": ["x.py"]}))
    payload["delivery"] = {"mode": "flow", "reviewer": "critic"}
    body = await _submit(app, planner, payload)
    assert _warned(body) == []


async def test_the_undeclared_warning_names_the_default_field(app, planner):  # noqa: F811
    body = await _submit(app, planner, _flow(("a", {"files": ["x.py"]})))
    (warning,) = _warned(body)
    assert "delivery.reviewer" in warning["message"]


def test_the_exploring_duty_names_the_default_field():
    assert "delivery.reviewer" in SPEC_PHASE_DUTIES["exploring"]


async def test_delivery_status_names_the_default_reviewer(
    app, auth_headers, run_headers  # noqa: F811
):
    async def status_of():
        got = await app.get(
            f"{BASE}/spec", params={"path": "spec/changes/demo/spec.html"}, headers=auth_headers
        )
        assert got.status_code == 200, got.text
        return got.json().get("delivery_status")

    path = "spec/changes/demo/spec.html"
    await _create(app, auth_headers, path)
    await _agent("dev")
    await _submit_document(app, run_headers, _document(delivery=FLOW), path=path)
    # No default named: unchanged, and the bar reads "any free agent".
    assert await status_of() == {"state": "ok", "agent": "dev"}

    await _submit_document(
        app, run_headers, _document(delivery={**FLOW, "reviewer": "critic"}), path=path
    )
    assert await status_of() == {
        "state": "ok",
        "agent": "dev",
        "reviewer": "critic",
        "reviewer_state": "unknown",
    }
    await _agent("critic")
    assert (await status_of())["reviewer_state"] == "ok"
    async with async_session_factory() as db:
        await db.execute(update(Agent).where(Agent.name == "critic").values(lifecycle="archived"))
        await db.commit()
    assert (await status_of())["reviewer_state"] == "archived"


def test_the_submit_tool_says_delivery_takes_a_reviewer():
    from hub.mcp_server import submit_spec_document

    doc = submit_spec_document.__doc__ or ""
    assert '"reviewer"' in doc
