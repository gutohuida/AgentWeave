"""ask_user waits for the operator instead of asking into the void."""

from __future__ import annotations

import pytest

from hub import mcp_server


@pytest.fixture(autouse=True)
def _no_run_token(monkeypatch):
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)


def test_asking_waits_for_the_answer_and_returns_it(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    polls = {"n": 0}

    def hub(method, path, *_a, **_k):
        if method == "POST":
            return {"id": "q-1"}
        polls["n"] += 1
        # Unanswered at first, so the wait is genuinely exercised rather than short-circuited.
        if polls["n"] < 3:
            return {"answered": False}
        return {"answered": True, "answer": "use the blue one"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user("which colour?")
    assert result["answered"] is True
    assert result["answer"] == "use the blue one"
    assert polls["n"] >= 3


def test_blocking_is_the_default():
    """An agent that has to opt in to being answered mostly will not, and the question is lost."""
    import inspect

    assert inspect.signature(mcp_server.ask_user).parameters["blocking"].default is True


def test_not_blocking_returns_immediately_without_polling(monkeypatch):
    calls = []

    def hub(method, path, *_a, **_k):
        calls.append((method, path))
        return {"id": "q-1"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user("anything?", blocking=False)
    assert result["answered"] is False
    assert calls == [("POST", "/questions")]


def test_an_unanswered_question_gives_up_and_says_so(monkeypatch):
    """Bounded like the permission wait: a turn suspended forever is worse than one told
    nobody replied."""
    monkeypatch.setattr(mcp_server, "QUESTION_ANSWER_TIMEOUT", 0.05)
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(
        mcp_server,
        "_hub_request",
        lambda method, *a, **k: {"id": "q-1"} if method == "POST" else {"answered": False},
    )
    result = mcp_server.ask_user("which colour?")
    assert result["answered"] is False
    assert "without an answer" in result["note"]


def test_a_transient_hub_failure_does_not_end_the_wait(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    state = {"n": 0}

    def hub(method, path, *_a, **_k):
        if method == "POST":
            return {"id": "q-1"}
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("blip")
        return {"answered": True, "answer": "fine"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    assert mcp_server.ask_user("q?")["answer"] == "fine"


def test_the_question_wait_stays_inside_what_was_measured():
    """An ordinary MCP tool call was measured tolerating 240s against Claude Code 2.1.221.
    Raising this above that ceiling would make the wait itself the failure."""
    assert mcp_server.QUESTION_ANSWER_TIMEOUT <= 240
