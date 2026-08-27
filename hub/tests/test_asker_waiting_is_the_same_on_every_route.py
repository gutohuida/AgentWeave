"""Finding F80 — `asker_waiting` is computed on the list route and defaulted on every other one.

`QuestionResponse.asker_waiting` answers one question: is there still a run awake to receive an
answer to this? It is what separates a question worth answering from a record of one that has been
overtaken. `_with_asker_state` computes it, in one query for a whole page, and `GET /questions`
calls it.

The other four routes that return a `QuestionResponse` return the ORM row instead, so Pydantic fills
the field from its schema default — `asker_waiting: bool = True`. The field is therefore not merely
stale on those routes; it is a constant, and it is the answer that means "still waiting" no matter
what the run is doing.

Measured live 2026-08-27 driving `proj-46b602c1f3cb`, on two questions whose asking runs had both
ended — one answered, one declined:

```
GET /questions          -> asker_waiting: false, false     (correct)
GET /questions/q-a06...  -> asker_waiting: true            (the default)
GET /questions/q-d44...  -> asker_waiting: true            (the default, on a DECLINED question)
```

`answer_question` is the sharp one: it computes this exact fact internally, as
`asker_still_waiting`, to decide whether to queue the answer as a turn — and then returns a body
saying the opposite. The truth was in the function, one line above the return.

Not currently visible in the dashboard, which reads the list and discards the mutation bodies. It is
a lie to every other client, including an agent reading the API, and it points the wrong way: a
surface that says the asker is waiting sends the operator to an answer that `release_block_for
_question`'s own guard (F60) may then refuse.
"""

import pytest
from sqlalchemy import select

from hub.db.engine import async_session_factory
from hub.db.models import Question, Run

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"


async def _question_from_a_dead_run(qid: str, run_id: str, *, blocking: bool = True) -> None:
    """A question whose asking run has ended — the only state in which the default is wrong."""
    async with async_session_factory() as session:
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent="builder",
                status="completed",
            )
        )
        session.add(
            Question(
                id=qid,
                project_id=PROJECT,
                from_agent="builder",
                question=f"question {qid}?",
                blocking=blocking,
                created_by_run_id=run_id,
                options=[{"label": "yes"}, {"label": "no"}],
            )
        )
        await session.commit()


async def test_the_list_and_the_detail_route_agree(app, auth_headers):
    """The two reads of one row must not disagree about whether anyone is listening."""
    await _question_from_a_dead_run("q-f80-read", "run-f80-read")

    listed = await app.get(f"/api/v1/projects/{PROJECT}/questions", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    from_list = {row["id"]: row["asker_waiting"] for row in listed.json()}
    assert from_list["q-f80-read"] is False, "the list route already gets this right"

    detail = await app.get(f"/api/v1/projects/{PROJECT}/questions/q-f80-read", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    assert (
        detail.json()["asker_waiting"] is False
    ), "the detail route returned the schema default instead of computing it"


async def test_answering_reports_that_nobody_was_waiting(app, auth_headers):
    """`answer_question` computes this fact to decide whether to queue the answer as a turn, then
    returned a body contradicting it."""
    await _question_from_a_dead_run("q-f80-answer", "run-f80-answer")

    response = await app.patch(
        f"/api/v1/projects/{PROJECT}/questions/q-f80-answer",
        json={"answer": "yes", "labels": ["yes"]},
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answered"] is True
    assert body["asker_waiting"] is False


async def test_declining_reports_that_nobody_was_waiting(app, auth_headers):
    """The live case: a declined question whose run had ended still read `asker_waiting: true`."""
    await _question_from_a_dead_run("q-f80-decline", "run-f80-decline")

    response = await app.post(
        f"/api/v1/projects/{PROJECT}/questions/q-f80-decline/decline", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["declined"] is True
    assert body["asker_waiting"] is False


async def test_a_live_asker_is_still_reported_as_waiting(app, auth_headers):
    """The mutation check. `asker_waiting` must not become a constant `False` either — a running
    asker is the case the whole field exists to report, and it is also the default's one correct
    answer, so a fix that hardcoded the opposite would pass the three tests above."""
    async with async_session_factory() as session:
        session.add(Run(id="run-f80-live", project_id=PROJECT, agent="builder", status="running"))
        session.add(
            Question(
                id="q-f80-live",
                project_id=PROJECT,
                from_agent="builder",
                question="still waiting?",
                blocking=True,
                created_by_run_id="run-f80-live",
                options=[{"label": "yes"}, {"label": "no"}],
            )
        )
        await session.commit()

    detail = await app.get(f"/api/v1/projects/{PROJECT}/questions/q-f80-live", headers=auth_headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["asker_waiting"] is True


async def test_an_unrecorded_asker_is_still_presumed_waiting(app, auth_headers):
    """The presumption `_asking_run_has_ended` documents survives. A question with no recorded run
    — one posted through the operator route — is left alone rather than guessed about."""
    async with async_session_factory() as session:
        session.add(
            Question(
                id="q-f80-unknown",
                project_id=PROJECT,
                from_agent="builder",
                question="who asked?",
                blocking=True,
                options=[{"label": "yes"}, {"label": "no"}],
            )
        )
        await session.commit()

    detail = await app.get(
        f"/api/v1/projects/{PROJECT}/questions/q-f80-unknown", headers=auth_headers
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["asker_waiting"] is True

    async with async_session_factory() as session:
        rows = (
            (await session.execute(select(Question).where(Question.id == "q-f80-unknown")))
            .scalars()
            .all()
        )
        assert rows[0].created_by_run_id is None
