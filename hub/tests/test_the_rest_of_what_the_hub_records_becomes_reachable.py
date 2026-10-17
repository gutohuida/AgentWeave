"""The rest of what the Hub records becomes reachable (slice remaining-hidden-data).

Checkpoint notes had a write route and no read route, and the proposals route returned pending
proposals only. Both reads are pinned here, in the order the UI renders them.
"""

from datetime import datetime, timedelta, timezone

from hub.db.engine import async_session_factory
from hub.db.models import CheckpointNote, Conversation, SpecDocument, SpecEditProposal

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


async def test_the_proposals_route_answers_resolved_ones_with_their_reasons(app, auth_headers):
    async with async_session_factory() as session:
        session.add(
            SpecDocument(id="spdoc-hidden", project_id="proj-test", path=PATH, title="Hidden")
        )
        await session.flush()
        for pid, status, resolved, reason in [
            ("sprop-pending", "pending", None, ""),
            ("sprop-ok", "accepted", T0, "matches"),
            ("sprop-no", "rejected", T0 + timedelta(hours=1), "too narrow"),
        ]:
            session.add(
                SpecEditProposal(
                    id=pid,
                    document_id="spdoc-hidden",
                    unit_kind="requirement",
                    unit_key="r1",
                    change_kind="modify",
                    proposed_payload={"key": "r1"},
                    status=status,
                    created_at=T0,
                    resolved_at=resolved,
                    resolved_by_actor_name="operator" if resolved else None,
                    resolution_reason=reason,
                )
            )
        await session.commit()

    async def ids(query=""):
        response = await app.get(
            f"{BASE}/project/documents/{PATH}/proposals{query}", headers=auth_headers
        )
        assert response.status_code == 200, response.text
        return response.json()["proposals"]

    assert [p["id"] for p in await ids()] == ["sprop-pending"], "pending stays the default"
    resolved = await ids("?status=resolved")
    assert [p["id"] for p in resolved] == ["sprop-no", "sprop-ok"], "newest decision first"
    assert resolved[0]["resolution_reason"] == "too narrow"
    assert resolved[0]["resolved_by_actor_name"] == "operator"
    assert {p["id"] for p in await ids("?status=all")} == {"sprop-pending", "sprop-ok", "sprop-no"}
    bad = await app.get(
        f"{BASE}/project/documents/{PATH}/proposals?status=nope", headers=auth_headers
    )
    assert bad.status_code == 422
