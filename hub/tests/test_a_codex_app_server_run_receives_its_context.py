"""F325 -- a Codex app-server run receives its canonical context.

Every turn renders the canonical context (charter, operating profile, roster, project
instructions, tool section) to `.agentweave/context/<agent>.md`. Claude reads it through
`--append-system-prompt-file` and Codex `exec` through `-c model_instructions_file=`, but the
app-server transport -- Codex's default -- reads no argv, so the file was written and never handed
over: the thread got only the turn prompt. Re-verified live on 2026-11-11 against Codex 0.167.1.

Codex app-server 0.167.1's `ThreadStartParams` and `ThreadResumeParams` both carry
`developerInstructions` (`codex app-server generate-json-schema`), but driven on 2026-11-11 only
`thread/start` records it: a resumed thread keeps its first turn's. So a new thread starts with the
context as its developer instructions, and a resumed one is handed the context rendered for *this*
turn as its input's leading block, so a charter edit or a roster change reaches it.

Held at the two seams, as F462's test is: the real `POST /agent/trigger` handing the rendered
context to `run_turn`, and the real `run_turn` putting it on the thread request.
"""

from unittest.mock import patch

from hub import codex_appserver
from hub.codex_appserver import run_turn
from tests.test_agent_trigger import _await_background_run, _fake_run_turn
from tests.test_codex_appserver_run_turn import (
    THREAD_START_RESULT,
    TURN_START_RESULT,
    _FakeSession,
    _noop,
    _patch_spawn,
)

MARKER = "F325_CHARTER_MARKER"


async def test_the_dispatch_hands_the_rendered_context_to_run_turn(app, auth_headers, bind_runner):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"codexer": {"runner": "codex"}, "peer": {"runner": "claude"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text
    await bind_runner("codexer", cli="codex")
    charter = await app.post(
        "/api/v1/projects/proj-test/charters",
        json={"name": "Codex Charter", "content": MARKER},
        headers=auth_headers,
    )
    assert charter.status_code == 201, charter.text
    bound = await app.patch(
        "/api/v1/projects/proj-test/agents/codexer",
        json={"charter_id": charter.json()["id"]},
        headers=auth_headers,
    )
    assert bound.status_code == 200, bound.text

    fake = _fake_run_turn()
    with patch("hub.codex_appserver.run_turn", fake):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/codex"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": "codexer", "message": "hello", "session_mode": "new"},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await _await_background_run()

    fake.assert_called_once()
    instructions = fake.call_args.kwargs.get("developer_instructions") or ""
    # The charter, the operating profile and the roster -- the parts a Codex agent never saw.
    assert "## Charter: Codex Charter" in instructions
    assert MARKER in instructions
    assert "### Your workspace" in instructions
    assert "`peer`" in instructions
    # Exactly what the context file holds -- the content a Claude run is handed.
    context_file = fake.call_args.kwargs["cwd"] + "/.agentweave/context/codexer.md"
    with open(context_file, encoding="utf-8") as handle:
        assert instructions == handle.read()


def _session(start_method):
    return _FakeSession(
        responses={
            "initialize": {},
            start_method: THREAD_START_RESULT,
            "turn/start": TURN_START_RESULT,
        },
        notifications=[{"method": "turn/completed", "params": {"turn": {"status": "completed"}}}],
    )


async def _turn(monkeypatch, *, resume_thread_id, method, instructions):
    fake = _session(method)
    _patch_spawn(monkeypatch, fake)
    await run_turn(
        cli="codex",
        cwd="/workspace",
        env=None,
        prompt="the turn's message",
        model=None,
        resume_thread_id=resume_thread_id,
        yolo=False,
        mcp_command=None,
        on_event=_noop,
        developer_instructions=instructions,
    )
    thread = next(p for m, p in fake.sent_requests if m == method)
    turn = next(p for m, p in fake.sent_requests if m == "turn/start")
    return thread, turn


async def test_a_new_thread_starts_with_the_context(monkeypatch):
    context = f"## Charter: X\n\n{MARKER}"
    thread, turn = await _turn(
        monkeypatch, resume_thread_id=None, method="thread/start", instructions=context
    )

    assert thread["developerInstructions"] == context
    # Additive: Codex's own base instructions are left in place.
    assert "baseInstructions" not in thread
    # Delivered once, not repeated in the turn's input.
    assert turn["input"] == [{"type": "text", "text": "the turn's message"}]


async def test_a_resumed_thread_is_given_this_turns_context_in_its_input(monkeypatch):
    """Codex 0.167.1 records no `developerInstructions` sent on `thread/resume` (measured
    2026-11-11: the rollout kept the first marker and never the second), so a resumed thread is
    handed the current context as the turn's leading block -- a charter edit reaches it."""
    context = f"## Charter: Edited\n\n{MARKER}"
    thread, turn = await _turn(
        monkeypatch, resume_thread_id="thread-earlier", method="thread/resume", instructions=context
    )

    assert "developerInstructions" not in thread
    assert "baseInstructions" not in thread
    lead, message = turn["input"]
    assert lead["type"] == "text"
    assert lead["text"].startswith(codex_appserver.RESUMED_CONTEXT_HEAD)
    assert lead["text"].endswith(context)
    assert message == {"type": "text", "text": "the turn's message"}


async def test_no_context_sends_no_instructions(monkeypatch):
    """A caller with nothing rendered sends no key at all, not an empty one."""
    fake = _session("thread/start")
    _patch_spawn(monkeypatch, fake)

    await run_turn(
        cli="codex",
        cwd="/workspace",
        env=None,
        prompt="hi",
        model=None,
        resume_thread_id=None,
        yolo=False,
        mcp_command=None,
        on_event=_noop,
    )

    params = next(p for m, p in fake.sent_requests if m == "thread/start")
    assert "developerInstructions" not in params
