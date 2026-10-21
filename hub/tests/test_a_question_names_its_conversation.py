"""F804: a question reaches the operator's screen naming the conversation it was asked in.

The agent tray filtered by agent alone, so a question nobody waited on in conversation A took over
the composer of conversation B with the same agent. The UI cannot scope the tray without the
conversation on the wire; the column existed (`Question.conversation_id`) and the response schema
dropped it.
"""

import pytest

from hub.db.engine import async_session_factory
from hub.db.models import Question

QUESTIONS = "/api/v1/projects/proj-test/questions"


@pytest.mark.asyncio
async def test_the_questions_list_carries_the_conversation_each_was_asked_in(app, auth_headers):
    async with async_session_factory() as session:
        for qid, conversation in (("q-f804-a", "conv-a"), ("q-f804-none", None)):
            session.add(
                Question(
                    id=qid,
                    project_id="proj-test",
                    from_agent="asker",
                    question="Which name?",
                    blocking=True,
                    answered=False,
                    conversation_id=conversation,
                )
            )
        await session.commit()

    response = await app.get(f"{QUESTIONS}?answered=false", headers=auth_headers)
    assert response.status_code == 200, response.text
    by_id = {row["id"]: row for row in response.json()}
    assert by_id["q-f804-a"]["conversation_id"] == "conv-a"
    assert by_id["q-f804-none"]["conversation_id"] is None
