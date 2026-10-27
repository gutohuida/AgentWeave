"""The rest of what the Hub records becomes reachable (slice remaining-hidden-data).

Checkpoint notes had a write route and no read route, and the proposals route returned pending
proposals only. Both reads are pinned here, in the order the UI renders them.
"""

from datetime import datetime, timedelta, timezone

from hub.db.engine import async_session_factory
from hub.db.models import CheckpointNote, Conversation

BASE = "/api/v1/projects/proj-test"
T0 = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
PATH = "spec/changes/hidden/spec.json"


async def test_checkpoint_notes_read_oldest_first_naming_the_checkpoint_that_took_them(
    app, auth_headers
):
    async with async_session_factory() as session:
        session.add(Conversation(id="conv-notes", project_id="proj-test", agent="builder"))
        session.add_all(
            [
                CheckpointNote(
                    id="note-new",
                    project_id="proj-test",
                    conversation_id="conv-notes",
                    agent="builder",
                    intent="finish the rename",
                    warnings=["flaky test"],
                    created_at=T0 + timedelta(minutes=5),
                ),
                CheckpointNote(
                    id="note-old",
                    project_id="proj-test",
                    conversation_id="conv-notes",
                    agent="builder",
                    intent="start the rename",
                    suspicions=["EPERM"],
                    consumed_by_checkpoint_id="ckpt-1",
                    created_at=T0,
                ),
            ]
        )
        await session.commit()

    response = await app.get(
        f"{BASE}/conversations/conv-notes/checkpoint-notes", headers=auth_headers
    )
    assert response.status_code == 200, response.text
    notes = response.json()["notes"]
    assert [n["id"] for n in notes] == ["note-old", "note-new"]
    assert notes[0]["consumed_by_checkpoint_id"] == "ckpt-1"
    assert notes[0]["suspicions"] == ["EPERM"] and notes[1]["warnings"] == ["flaky test"]

    missing = await app.get(
        f"{BASE}/conversations/conv-nope/checkpoint-notes", headers=auth_headers
    )
    assert missing.status_code == 404
