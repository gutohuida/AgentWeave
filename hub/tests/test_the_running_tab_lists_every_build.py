"""`the-side-panel-s-running-tab-builds-loops-and-jobs-and-what-needs-me` (FR-2, FR-4): the Hub's
one project-scoped read of every build of every document, for the side panel's Running tab.

The rows are written by hand, in the order the route is meant to return them (newest build first),
so a reversed route fails the ordering assertion rather than passing on a fixture the route never
emits.
"""

from datetime import datetime, timedelta, timezone

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import AIJob, Build, Loop, Question, SpecDocument, Task

P = "proj-test"
URL = f"/api/v1/projects/{P}/project/builds"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)


def _document(key: str, title: str) -> SpecDocument:
    return SpecDocument(
        id=f"spdoc-{key}",
        project_id=P,
        path=f"spec/changes/{key}/spec.json",
        title=title,
        kind="change-spec",
        phase="approved",
    )


def _build(key: str, hours_ago: int, **fields) -> Build:
    return Build(
        id=f"build-{key}",
        project_id=P,
        document_id=f"spdoc-{key}",
        state=fields.pop("state", "running"),
        driver=fields.pop("driver", "flow"),
        level="reviewed",
        created_at=NOW - timedelta(hours=hours_ago),
        **fields,
    )


async def _seed() -> None:
    async with async_session_factory() as db:
        for key, title in (
            ("flow", "A flow build"),
            ("lead", "A lead build"),
            ("done", "A finished build"),
            ("early", "A build stopped early"),
        ):
            db.add(_document(key, title))
        db.add(
            AIJob(
                id="job-flow",
                project_id=P,
                name="Flow loop",
                agent="dev",
                message="m",
                cron="* * * * *",
            )
        )
        await db.flush()
        db.add(Loop(id="loop-flow", project_id=P, job_id="job-flow", spec_document_id="spdoc-flow"))
        await db.flush()
        db.add_all(
            [
                _build("flow", 1, loop_id="loop-flow"),
                _build("lead", 2, driver="lead", lead="arch", lead_conversation_id="conv-lead"),
                _build("done", 24, state="finished", stopped_at=NOW - timedelta(hours=20)),
                _build(
                    "early",
                    48,
                    state="stopped",
                    stop_reason="stopped by the operator",
                    stopped_at=NOW - timedelta(hours=40),
                ),
            ]
        )
        await db.flush()
        db.add_all(
            [
                Task(
                    id="t-flow-1",
                    project_id=P,
                    title="one",
                    status="approved",
                    build_id="build-flow",
                ),
                Task(
                    id="t-flow-2",
                    project_id=P,
                    title="two",
                    status="pending",
                    build_id="build-flow",
                ),
            ]
        )
        db.add(
            Question(
                id="q-lead",
                project_id=P,
                from_agent="arch",
                question="Which database?",
                blocking=True,
                conversation_id="conv-lead",
                created_at=NOW,
            )
        )
        # Answered, non-blocking and unrelated questions are not the build's open question.
        db.add(
            Question(
                id="q-answered",
                project_id=P,
                from_agent="arch",
                question="Old?",
                blocking=True,
                answered=True,
                conversation_id="conv-lead",
            )
        )
        db.add(
            Question(
                id="q-note",
                project_id=P,
                from_agent="arch",
                question="FYI",
                blocking=False,
                conversation_id="conv-lead",
            )
        )
        db.add(
            Question(
                id="q-elsewhere",
                project_id=P,
                from_agent="arch",
                question="Other?",
                blocking=True,
                conversation_id="conv-other",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_every_build_is_listed_once_newest_first_with_its_context(app, auth_headers):
    await _seed()

    response = await app.get(URL, headers=auth_headers)

    assert response.status_code == 200, response.text
    rows = response.json()["builds"]
    assert [r["id"] for r in rows] == ["build-flow", "build-lead", "build-done", "build-early"]
    flow, lead, done, early = rows
    assert flow["document_title"] == "A flow build"
    assert flow["loop"] == {"id": "loop-flow", "name": "Flow loop", "enabled": True}
    assert (flow["tasks_done"], flow["tasks_total"]) == (1, 2)
    assert flow["question"] is None and flow["open_questions"] == 0
    assert lead["loop"] is None and lead["driver"] == "lead"
    assert lead["open_questions"] == 1
    assert lead["question"]["id"] == "q-lead"
    assert lead["question"]["question"] == "Which database?"
    assert lead["question"]["conversation_id"] == "conv-lead"
    assert (done["state"], early["state"]) == ("finished", "stopped")
    assert done["stopped_at"] is not None and early["stopped_at"] is not None
    assert early["stop_reason"] == "stopped by the operator"


@pytest.mark.asyncio
async def test_a_project_with_no_builds_answers_an_empty_list(app, auth_headers):
    response = await app.get(URL, headers=auth_headers)

    assert response.status_code == 200, response.text
    assert response.json() == {"builds": []}
