"""F651: an answer the asking run already read with `get_answer` is not delivered again.

A late answer -- given after `ask_user`'s wait ended, while its run still lives -- is queued as new
input (`a-late-answer-is-delivered`), and the run's end starts a turn for it. When the run had
polled `get_answer` and read the answer meanwhile, that turn only repeated what the agent knew:
"the operator's answers have now come through, and they confirm my implementation decisions".
"""

from __future__ import annotations

import pytest

from .test_a_late_answer_is_delivered import (
    answer,
    ask,
    entries,
    expire,
    make_agent,
    make_run,
    report,
)

pytestmark = pytest.mark.asyncio


async def _late_answer(app, auth_headers):
    """A question whose wait ended, answered while its run still lives: one queued delivery."""
    await make_agent()
    headers = await make_run()
    (question_id,) = await ask(app, headers, "Which colour?")
    await expire(question_id)
    await report(app, headers, question_id)
    await answer(app, auth_headers, question_id, "blue")
    queued = [entry for entry in await entries() if entry.state == "queued"]
    assert len(queued) == 1 and "Answer: blue" in queued[0].content
    return headers, question_id, queued[0].id


async def test_reading_a_late_answer_in_run_withdraws_its_delivery(app, auth_headers):
    headers, question_id, entry_id = await _late_answer(app, auth_headers)

    read = await app.get(f"/api/v1/agent-actions/questions/{question_id}", headers=headers)

    assert read.status_code == 200
    assert read.json()["answer"] == "blue"
    (entry,) = [row for row in await entries() if row.id == entry_id]
    assert entry.state == "withdrawn"
    assert "get_answer" in (entry.abandoned_reason or "")


async def test_a_read_before_the_answer_withdraws_nothing(app, auth_headers):
    """Polling while unanswered must not take the answer's later delivery with it."""
    await make_agent()
    headers = await make_run()
    (question_id,) = await ask(app, headers, "Which colour?")
    await expire(question_id)
    await report(app, headers, question_id)

    await app.get(f"/api/v1/agent-actions/questions/{question_id}", headers=headers)
    await answer(app, auth_headers, question_id, "green")

    assert [entry.state for entry in await entries()] == ["queued"]


async def test_an_unrelated_operator_message_is_left_alone(app, auth_headers):
    headers, question_id, entry_id = await _late_answer(app, auth_headers)
    sent = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "asker", "message": "Also: rename the module."},
        headers=auth_headers,
    )
    assert sent.status_code == 200, sent.text

    await app.get(f"/api/v1/agent-actions/questions/{question_id}", headers=headers)

    states = {row.content: row.state for row in await entries()}
    assert states["Also: rename the module."] == "queued"
    assert [row.state for row in await entries() if row.id == entry_id] == ["withdrawn"]
