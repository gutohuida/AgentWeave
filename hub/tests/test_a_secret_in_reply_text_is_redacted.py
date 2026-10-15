"""A secret in an agent's reply text is redacted (F602, `a-secret-in-reply-text-is-redacted`).

Tool rows were redacted by pattern while the `text` row beside them stored a quoted `aw_live_` key
verbatim, and `POST /agents/{name}/output` stored `sk-...` and an `api_key` value as written. The
values here are fake. The live drive is `scripts/drive/d1015_f602_text_redaction.py`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from hub import run_secrets
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput
from hub.runner_events import redact_text_secrets, text_event, thinking_event

LIVE = "aw_live_" + "Fake0123456789abcdefghijABCDEFGH"
RUN = "aw_run_" + "fakeRunToken0123456789"
SK = "sk-" + "fakeOpenAI0123456789abcd"


@pytest.fixture(autouse=True)
def _clean():
    yield
    for run in ("run-602", "run-602b"):
        run_secrets.forget(run)


@pytest.mark.parametrize(
    "text, gone",
    [
        (f"release tag: {LIVE}", LIVE),
        (f"build ref {RUN}.", RUN),
        (f"```\nmirror: {SK}\n```", SK),
        ("api_key=hunter2-fake", "hunter2-fake"),
        ('{"api_key": "hunter2-fake"}', "hunter2-fake"),
        ("PASSWORD: correct-horse", "correct-horse"),
        ("access_token='tok-abcdef'", "tok-abcdef"),
    ],
)
def test_a_named_secret_in_prose_is_redacted(text, gone):
    redacted = redact_text_secrets(text)
    assert gone not in redacted
    assert "<redacted>" in redacted


@pytest.mark.parametrize(
    "text",
    [
        "Merged 3b3aff3c6d5e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2 into master.",
        "Edited hub/hub/turn_scheduler.py and C:/Users/huida/Documents/x/calc/__init__.py",
        "The token budget: 500 tokens left; the password policy is in SECURITY.md.",
        "AbcdefghijklmnopqrstuvwxyzABCDEFGHIJ0123456789 is a long identifier",
        "Ask for the password: then wait.",
    ],
)
def test_prose_without_a_named_secret_is_kept(text):
    """Not the tool events' high-entropy catch-all: replies keep SHAs, paths and identifiers."""
    assert redact_text_secrets(text) == text


def test_a_payload_field_named_for_a_credential_is_redacted():
    assert redact_text_secrets({"api_key": "hunter2-fake", "n": 3}) == {
        "api_key": "<redacted>",
        "n": 3,
    }


def _stream(run_id, *events):
    run_secrets.register(run_id, [])  # as the trigger does for every run
    return [run_secrets.scrub_stream(run_id, event) for event in events]


def test_a_key_split_across_two_text_events_is_redacted_with_nothing_registered():
    """F488's shape for patterns: neither half matched alone, and the run registered nothing."""
    first, second = _stream(
        "run-602", text_event(f"tag: {LIVE[:14]}"), text_event(LIVE[14:] + " ok")
    )
    assert LIVE[14:] not in second.content
    assert second.content.startswith("<redacted>")
    assert second.payload["text"] == second.content


def test_a_field_value_split_at_its_separator_is_redacted():
    _first, second = _stream(
        "run-602", thinking_event("then api_key="), text_event("hunter2-fake done")
    )
    assert "hunter2-fake" not in second.content


def test_a_tool_row_between_the_halves_does_not_break_the_join():
    from hub.runner_events import tool_use_event

    _a, _b, third = _stream(
        "run-602b",
        text_event(f"see {LIVE[:20]}"),
        tool_use_event(tool="Read", category="read", input_data={"file_path": "x"}),
        text_event(LIVE[20:]),
    )
    assert LIVE[20:] not in third.content


def test_forget_clears_the_carried_prose():
    _stream("run-602", text_event("anything"))
    run_secrets.forget("run-602")
    assert "run-602" not in run_secrets._tail_by_run


@pytest.mark.asyncio
async def test_the_operator_output_route_stores_no_named_secret(app, auth_headers):
    await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"writer602": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    posted = await app.post(
        "/api/v1/projects/proj-test/agents/writer602/output",
        json={
            "kind": "text",
            "content": f'key {SK} and {{"api_key": "hunter2-fake"}}',
            "payload": {"text": f"key {SK}", "api_key": "hunter2-fake"},
        },
        headers=auth_headers,
    )
    assert posted.status_code == 201, posted.text
    async with async_session_factory() as db:
        row = (
            (await db.execute(select(AgentOutput).where(AgentOutput.agent == "writer602")))
            .scalars()
            .one()
        )
    stored = row.content + str(row.payload)
    assert SK not in stored and "hunter2-fake" not in stored
    assert "<redacted>" in row.content
