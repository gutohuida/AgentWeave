"""One notice per event that calls the operator, and the Hub-held Windows choices.

Change `windows-notifications-for-what-calls-the-operator` (FR-7, FR-9, FR-10). The fixture's
expected kinds and texts were taken from the page's rules (`hub/ui/src/lib/notify/classify.ts`)
before they moved into `hub/hub/operator_notices.py`. The stream is read from a real operator
subscriber of the shared `sse_manager`, which is what `/api/v1/events` yields from, in its order.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from sqlalchemy import select

from hub import operator_notices
from hub.agent_auth import hash_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Agent, Conversation, EventLog, Run
from hub.sse import SSEManager, sse_manager, stream_frames

pytestmark = pytest.mark.asyncio

PROJECT = "proj-test"

# (event, payload, expected kind or None for silent, expected text) -- from classify.ts as it
# stood before this change.
RECORDED = [
    ("run_started", {"run_id": "r1", "agent": "alice"}, None, None),
    (
        "question_asked",
        {"id": "q-1", "from_agent": "alice", "blocking": True},
        "ask",
        "alice asked you a question",
    ),
    (
        "question_asked",
        {"id": "q-2", "from_agent": "bob", "blocking": False},
        "ask",
        "bob asked you a question",
    ),
    (
        "permission_requested",
        {"agent": "carol", "tool_name": "Bash"},
        "ask",
        "carol wants permission for Bash",
    ),
    ("permission_requested", {"agent": "carol"}, "ask", "carol wants permission"),
    ("run_failed", {"run_id": "r2", "agent": "dave"}, "fail", "dave's run failed"),
    ("loop_stopped", {"reason": "loop queue is empty"}, "done", "A loop finished its queue"),
    ("loop_stopped", {"reason": "budget spent"}, "fail", "A loop stopped: budget spent"),
    (
        "run_completed",
        {"agent": "erin", "initiator": "operator", "conversation_id": "conv-e"},
        "reply",
        "erin replied",
    ),
    (
        "run_completed",
        {"agent": "erin", "initiator": "autonomous", "conversation_id": "conv-e"},
        None,
        None,
    ),
    ("run_completed", {"agent": "erin", "initiator": "operator"}, None, None),
    (
        "task_checks_finished",
        {"task_title": "Ship it", "state": "passed"},
        "done",
        "Checks passed for Ship it: it can be landed",
    ),
    (
        "task_checks_finished",
        {"task_id": "task-9", "state": "failed"},
        "fail",
        "Checks did not pass for task-9",
    ),
    ("task_landing_changed", {"task_title": "T", "state": "landed"}, "done", "T landed on main"),
    (
        "task_landing_changed",
        {"task_title": "T", "state": "sent_back"},
        "fail",
        "T was sent back by its landing batch",
    ),
    ("task_landing_changed", {"task_title": "T", "state": "held"}, "ask", "T's landing is held"),
    ("task_landing_changed", {"task_title": "T", "state": "queued"}, None, None),
    ("stall_recorded", {"reason": "no reviewer"}, "fail", "Work stalled: no reviewer"),
    ("stall_recorded", {}, "fail", "Work stalled"),
    ("queue_chain_suspended", {"agent": "frank"}, "fail", "A message chain to frank was suspended"),
    (
        "main_moved",
        {"branch": "master", "moved_rewrite": True},
        "fail",
        "The history of master was rewritten outside the Hub",
    ),
    ("main_moved", {}, "fail", "main moved outside the Hub"),
    (
        "next_slice_offered",
        {"next_slice": {"title": "Slice 5"}},
        "done",
        "A slice is built: draft Slice 5?",
    ),
    ("task_created", {"id": "task-1"}, None, None),
    ("message_sent", {"id": "m-1"}, None, None),
]


def _frames(queue) -> list[tuple[str, dict]]:
    out = []
    while not queue.empty():
        evt = queue.get_nowait()
        out.append((evt.event, json.loads(evt.data)))
    return out


async def test_the_recorded_sequence_gives_one_notice_per_call_and_none_for_the_silent():
    q = sse_manager.subscribe_operator()
    try:
        for event, payload, _, _ in RECORDED:
            await sse_manager.broadcast(PROJECT, event, payload)
        frames = _frames(q)
    finally:
        sse_manager.unsubscribe_operator(q)

    # Walk the stream in its own order: each event, then its notice (if any) immediately after.
    i = 0
    seen_ids = set()
    for event, payload, kind, text in RECORDED:
        name, data = frames[i]
        assert name == event, (i, name, event)
        i += 1
        if kind is None:
            assert i >= len(frames) or frames[i][0] != "operator_notice", (event, payload)
            continue
        name, notice = frames[i]
        i += 1
        assert name == "operator_notice", (event, payload)
        assert notice["kind"] == kind
        assert notice["text"] == text
        assert notice["title"] == operator_notices.TITLES[kind]
        assert notice["source_event"] == event
        assert notice["project_id"] == PROJECT
        assert set(notice) == {
            "id",
            "kind",
            "project_id",
            "agent",
            "conversation_id",
            "title",
            "text",
            "source_event",
        }
        assert notice["id"] not in seen_ids
        seen_ids.add(notice["id"])
    assert i == len(frames)
    assert len(seen_ids) == sum(1 for r in RECORDED if r[2] is not None)


async def test_a_notice_names_its_agent_and_conversation():
    reply = operator_notices.notice_for(
        PROJECT,
        "run_completed",
        {"agent": "erin", "initiator": "operator", "conversation_id": "conv-e"},
    )
    assert reply["agent"] == "erin" and reply["conversation_id"] == "conv-e"
    ask = operator_notices.notice_for(
        PROJECT, "question_asked", {"id": "q", "from_agent": "al", "conversation_id": None}
    )
    assert ask["agent"] == "al" and ask["conversation_id"] is None
    loop = operator_notices.notice_for(PROJECT, "loop_stopped", {"reason": "x"})
    assert loop["agent"] is None


async def test_a_long_text_is_cut_as_the_page_cut_it():
    notice = operator_notices.notice_for(PROJECT, "stall_recorded", {"reason": "x" * 300})
    assert len(notice["text"]) == 140 and notice["text"].endswith("…")


async def test_the_notice_follows_its_event_through_the_route_generator():
    """`/api/v1/events` yields `stream_frames`: the event, then its notice, in that order."""
    manager = SSEManager()
    q = manager.subscribe_operator()
    manager.publish(PROJECT, "run_failed", {"agent": "dave"})

    async def never() -> bool:
        return False

    frames = stream_frames(q, never)
    # Bounded: on a build that publishes no notice the third frame never comes.
    names = [(await asyncio.wait_for(frames.__anext__(), 2.0)).event for _ in range(3)]
    await frames.aclose()
    assert names == ["connected", "run_failed", "operator_notice"]


async def test_a_failing_classifier_never_stops_the_event(monkeypatch):
    import hub.sse as sse_module

    def boom(*_a, **_k):
        raise RuntimeError("bad rule")

    monkeypatch.setattr(sse_module, "notice_for", boom)
    manager = SSEManager()
    q = manager.subscribe_operator()
    manager.publish(PROJECT, "run_failed", {"agent": "dave"})
    assert [name for name, _ in _frames(q)] == ["run_failed"]


async def test_a_project_subscriber_also_sees_the_notice_once():
    manager = SSEManager()
    q = manager.subscribe(PROJECT)
    manager.publish(PROJECT, "question_asked", {"id": "q", "from_agent": "al"})
    assert [name for name, _ in _frames(q)] == ["question_asked", "operator_notice"]


# --- FR-7: question_asked carries its conversation ---------------------------------------------


async def _run_in_conversation(run_id: str, conversation_id: str | None) -> dict:
    token = f"aw_run_{run_id}-secret"
    async with async_session_factory() as session:
        session.add(Agent(id=f"ag-asker-{run_id}", project_id=PROJECT, name="asker"))
        if conversation_id:
            session.add(Conversation(id=conversation_id, project_id=PROJECT, agent="asker"))
        session.add(
            Run(
                id=run_id,
                project_id=PROJECT,
                agent="asker",
                status="running",
                turn_depth=0,
                conversation_id=conversation_id,
                capability_token_hash=hash_run_token(token),
            )
        )
        await session.commit()
    return {"Authorization": f"Bearer {token}"}


QUESTION = {
    "blocking": False,
    "question": "Blue or green?",
    "header": "Colour",
    "options": [{"label": "blue"}, {"label": "green"}],
    "multi_select": False,
}


async def test_a_question_asked_from_a_conversation_carries_it_on_the_stream(app):
    headers = await _run_in_conversation("run-conv", "conv-q")
    q = sse_manager.subscribe_operator()
    try:
        asked = await app.post("/api/v1/agent-actions/questions", headers=headers, json=QUESTION)
        assert asked.status_code in (200, 201), asked.text
        frames = _frames(q)
    finally:
        sse_manager.unsubscribe_operator(q)

    asked_frames = [(i, d) for i, (n, d) in enumerate(frames) if n == "question_asked"]
    assert len(asked_frames) == 1
    index, event = asked_frames[0]
    assert event["conversation_id"] == "conv-q"
    # An old-style consumer reads the fields it always read, unchanged.
    assert event["id"] == asked.json()["id"]
    assert event["from_agent"] == "asker" and event["blocking"] is False
    # Its notice follows it and can open the conversation.
    name, notice = frames[index + 1]
    assert name == "operator_notice"
    assert notice["kind"] == "ask" and notice["conversation_id"] == "conv-q"
    assert notice["agent"] == "asker"

    async with async_session_factory() as session:
        row = (
            await session.execute(select(EventLog).where(EventLog.event_type == "question_asked"))
        ).scalar_one()
    persisted = row.data if isinstance(row.data, dict) else json.loads(row.data)
    assert persisted == {k: v for k, v in event.items() if k != "project_id"}


async def test_a_question_with_no_conversation_carries_null(app, auth_headers):
    q = sse_manager.subscribe_operator()
    try:
        asked = await app.post(
            f"/api/v1/projects/{PROJECT}/questions",
            headers=auth_headers,
            json={**QUESTION, "from_agent": "asker"},
        )
        assert asked.status_code == 201, asked.text
        frames = _frames(q)
    finally:
        sse_manager.unsubscribe_operator(q)
    event = next(d for n, d in frames if n == "question_asked")
    assert "conversation_id" in event and event["conversation_id"] is None


# --- FR-10: the Windows choices ----------------------------------------------------------------


@pytest.fixture
def kinds_file(tmp_path, monkeypatch):
    path = tmp_path / "profile" / operator_notices.WINDOWS_KINDS_FILE
    monkeypatch.setattr(operator_notices, "windows_kinds_path", lambda: path)
    return path


async def test_the_defaults_are_question_and_failure_on(app, auth_headers, kinds_file):
    got = await app.get("/api/v1/notify-settings", headers=auth_headers)
    assert got.status_code == 200
    assert got.json() == {"ask": True, "fail": True, "done": False, "reply": False}
    assert not kinds_file.exists()


async def test_a_changed_choice_is_kept_and_survives_a_restart(app, auth_headers, kinds_file):
    want = {"ask": False, "fail": True, "done": False, "reply": True}
    put = await app.put("/api/v1/notify-settings", headers=auth_headers, json=want)
    assert put.status_code == 200 and put.json() == want
    # What a restarted Hub reads: the file alone, nothing held in this process.
    assert json.loads(kinds_file.read_text(encoding="utf-8")) == want
    assert operator_notices.load_windows_kinds() == want
    got = await app.get("/api/v1/notify-settings", headers=auth_headers)
    assert got.json() == want


async def test_a_partial_or_unknown_body_is_refused(app, auth_headers, kinds_file):
    partial = await app.put("/api/v1/notify-settings", headers=auth_headers, json={"ask": False})
    assert partial.status_code == 422
    extra = await app.put(
        "/api/v1/notify-settings",
        headers=auth_headers,
        json={"ask": True, "fail": True, "done": True, "reply": True, "sound": True},
    )
    assert extra.status_code == 422
    assert not kinds_file.exists()


async def test_an_unreadable_file_reads_as_the_defaults(app, auth_headers, kinds_file):
    kinds_file.parent.mkdir(parents=True)
    kinds_file.write_text("{not json", encoding="utf-8")
    got = await app.get("/api/v1/notify-settings", headers=auth_headers)
    assert got.json() == operator_notices.DEFAULT_WINDOWS_KINDS


async def test_the_choices_are_the_operators_only(app, kinds_file):
    assert (await app.get("/api/v1/notify-settings")).status_code == 401
    headers = await _run_in_conversation("run-agent", None)
    agent_get = await app.get("/api/v1/notify-settings", headers=headers)
    assert agent_get.status_code in (401, 403)
    agent_put = await app.put(
        "/api/v1/notify-settings",
        headers=headers,
        json={"ask": False, "fail": False, "done": False, "reply": False},
    )
    assert agent_put.status_code in (401, 403)
    assert not kinds_file.exists()


async def test_the_file_sits_beside_the_hubs_database(monkeypatch):
    monkeypatch.setattr(
        operator_notices.settings, "database_url", "sqlite+aiosqlite:///C:/p/data/agentweave.db"
    )
    assert operator_notices.windows_kinds_path().as_posix() == "C:/p/data/notify_settings.json"
    monkeypatch.setattr(operator_notices.settings, "database_url", "sqlite+aiosqlite:///:memory:")
    assert operator_notices.windows_kinds_path() is None
