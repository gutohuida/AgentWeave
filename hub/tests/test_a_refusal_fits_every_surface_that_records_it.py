"""F566: the review-reassignment refusal keeps its remedy whole on every surface that records it.

`_guard_reviewer_is_not_the_author` refuses a move to `under_review` that names the task's author
as its holder. Four places record that sentence, and each cuts differently:

* the operator's `PATCH /tasks/{id}` 403 detail,
* the agent's `PATCH /agent-actions/tasks/{id}` 403 detail,
* the dispatch route's `POST /agent/trigger` 403 detail,
* a failed job firing's `JobRun.error_summary` (500 characters, redacted first), reached through
  `scheduler._safe_error_summary` and `api/v1/jobs._safe_error_summary`.

The sentence is built at the longest task id (64) and agent name (32) the Hub accepts. It must fit
the shortest limit (500) and every surface must hold the remedy, the task id and the agent name
whole. Restored from `a-refusal-names-a-remedy-that-works` (dropped by the overhaul with no test).
"""

from __future__ import annotations

import pytest

from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import JOB_RUN_ERROR_SUMMARY_CHARS, Run, fit_error_summary

from .test_a_refusal_names_a_remedy_that_works import (
    _completed_by_author,
    _document,
    _evidence,
    _padded,
    _roster,
)

pytestmark = pytest.mark.asyncio

OPERATOR_REMEDY = "Land it, on the task, to review it yourself"
AGENT_REMEDY = "None of the task tools you are offered reassigns a task"
AGENT_REMEDY_END = "the operator can move it on."
OPERATOR_REMEDY_ENDS = ("review it yourself.", "(POST /agent/trigger with review_task_id).")

TASK_ID = _padded("taskf566", 64)
AUTHOR = _padded("authorf566", 32)
OTHER = _padded("otherf566", 32)


def _whole(text: str, *, remedy: str, remedy_end) -> None:
    assert remedy in text, text
    assert text.rstrip().endswith(remedy_end), text  # str or tuple of accepted endings
    assert TASK_ID in text, text
    assert AUTHOR in text, text
    assert "<redacted>" not in text, text
    assert "…" not in text, text


async def test_the_refusal_is_whole_on_every_surface_at_the_longest_ids(
    app, auth_headers, bind_runner
):
    from hub.api.v1.jobs import _safe_error_summary as jobs_summary
    from hub.scheduler import _safe_error_summary as scheduler_summary
    from hub.task_transition_service import (
        ActorNotPermittedError,
        _guard_reviewer_is_not_the_author,
    )
    from hub.task_transitions import operator, run_actor

    await _roster(app, auth_headers, bind_runner, AUTHOR)
    async with async_session_factory() as db:
        await _document(db, "doc-f566")
        task = await _completed_by_author(db, TASK_ID, author=AUTHOR)
        await _evidence(db, task.id, suffix="f566", agent=AUTHOR, document_id="doc-f566")

    token = "aw_run_f566-other-secret"
    async with async_session_factory() as db:
        db.add(
            Run(
                id="run-f566-other",
                project_id="proj-test",
                agent=OTHER,
                status="running",
                turn_depth=0,
                capability_token_hash=hash_run_token(token),
            )
        )
        await db.commit()

    # The guard's own sentence, per actor kind -- what every surface below receives.
    sentences = {}
    async with async_session_factory() as db:
        task = await db.get(type(task), TASK_ID)
        for kind, actor in (
            ("operator", operator()),
            ("agent", run_actor("run-f566-other", OTHER)),
        ):
            with pytest.raises(ActorNotPermittedError) as raised:
                await _guard_reviewer_is_not_the_author(db, task, "under_review", actor)
            sentences[kind] = str(raised.value)

    # Surface 1: the operator's task PATCH.
    operator_patch = await app.patch(
        f"/api/v1/projects/proj-test/tasks/{TASK_ID}",
        json={"status": "under_review"},
        headers=auth_headers,
    )
    assert operator_patch.status_code == 403, operator_patch.text
    patch_detail = operator_patch.json()["detail"]
    assert len(patch_detail) <= JOB_RUN_ERROR_SUMMARY_CHARS, (len(patch_detail), patch_detail)
    _whole(patch_detail, remedy=OPERATOR_REMEDY, remedy_end=OPERATOR_REMEDY_ENDS)

    # Surface 2: the agent's task PATCH, through a run token.
    agent_patch = await app.patch(
        f"/api/v1/agent-actions/tasks/{TASK_ID}",
        json={"status": "under_review"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert agent_patch.status_code == 403, agent_patch.text
    agent_detail = agent_patch.json()["detail"]
    assert len(agent_detail) <= JOB_RUN_ERROR_SUMMARY_CHARS, (len(agent_detail), agent_detail)
    _whole(agent_detail, remedy=AGENT_REMEDY, remedy_end=AGENT_REMEDY_END)

    # Surface 3: the dispatch route, before any job-run fitting could hide an overflow.
    dispatch = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={
            "agent": AUTHOR,
            "message": "review it",
            "review_task_id": TASK_ID,
            "session_mode": "new",
        },
        headers=auth_headers,
    )
    assert dispatch.status_code == 403, dispatch.text
    dispatch_detail = dispatch.json()["detail"]
    assert len(dispatch_detail) <= JOB_RUN_ERROR_SUMMARY_CHARS, (
        len(dispatch_detail),
        dispatch_detail,
    )
    _whole(dispatch_detail, remedy=OPERATOR_REMEDY, remedy_end=OPERATOR_REMEDY_ENDS)

    # Surface 4: a failed firing's JobRun.error_summary, through both recorders.
    for kind, remedy, remedy_end in (
        ("operator", OPERATOR_REMEDY, OPERATOR_REMEDY_ENDS),
        ("agent", AGENT_REMEDY, AGENT_REMEDY_END),
    ):
        sentence = sentences[kind]
        assert len(sentence) <= JOB_RUN_ERROR_SUMMARY_CHARS, (kind, len(sentence), sentence)
        _whole(sentence, remedy=remedy, remedy_end=remedy_end)
        for recorder in (scheduler_summary, jobs_summary):
            recorded = recorder(ActorNotPermittedError(sentence))
            # The secret redactor replaces an opaque run of 32+ alphanumerics, which the padded
            # worst-case ids are, so the ids may read `<redacted>` here; the remedy is what must
            # survive, uncut.
            assert len(recorded) <= JOB_RUN_ERROR_SUMMARY_CHARS, (kind, len(recorded))
            assert remedy in recorded, (kind, recorder.__module__, recorded)
            assert recorded.rstrip().endswith(remedy_end), (kind, recorder.__module__, recorded)
            assert "…" not in recorded
            assert fit_error_summary(recorded) == recorded
