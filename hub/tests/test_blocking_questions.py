"""ask_user waits for the operator instead of asking into the void, and can ask several at once."""

from __future__ import annotations

import pytest

from hub import mcp_server


@pytest.fixture(autouse=True)
def _no_run_token(monkeypatch):
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)


def one(question="which colour?", header="H", multi_select=False, labels=("a", "b")):
    """One well-formed question, so a test says what it is about rather than restating the shape."""
    return {
        "question": question,
        "header": header,
        "options": [{"label": label} for label in labels],
        "multi_select": multi_select,
    }


def batch_post(ids):
    """The Hub's reply to a batch create, in the shape the tool reads."""
    return {"batch_id": "qbatch-1", "questions": [{"id": qid} for qid in ids]}


def test_asking_waits_for_the_answer_and_returns_it(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    polls = {"n": 0}

    def hub(method, path, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1"])
        polls["n"] += 1
        # Unanswered at first, so the wait is genuinely exercised rather than short-circuited.
        if polls["n"] < 3:
            return {"answered": False}
        return {"answered": True, "answer": "use the blue one"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user([one()])
    assert result["answered"] is True
    assert result["answers"][0]["answer"] == "use the blue one"
    assert polls["n"] >= 3


def test_blocking_is_the_default():
    """An agent that has to opt in to being answered mostly will not, and the question is lost."""
    import inspect

    assert inspect.signature(mcp_server.ask_user).parameters["blocking"].default is True


def test_not_blocking_returns_immediately_without_polling(monkeypatch):
    calls = []

    def hub(method, path, *_a, **_k):
        calls.append((method, path))
        return batch_post(["q-1"])

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user([one("anything?")], blocking=False)
    assert result["answered"] is False
    assert calls == [("POST", "/questions/batch")]


def test_an_unanswered_question_gives_up_and_says_so(monkeypatch):
    """Bounded like the permission wait: a turn suspended forever is worse than one told
    nobody replied."""
    monkeypatch.setattr(mcp_server, "QUESTION_ANSWER_TIMEOUT", 0.05)
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(
        mcp_server,
        "_hub_request",
        lambda method, *a, **k: batch_post(["q-1"]) if method == "POST" else {"answered": False},
    )
    result = mcp_server.ask_user([one()])
    assert result["answered"] is False
    assert "went unanswered" in result["note"]


def test_a_transient_hub_failure_does_not_end_the_wait(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    state = {"n": 0}

    def hub(method, path, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1"])
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("blip")
        return {"answered": True, "answer": "fine"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    assert mcp_server.ask_user([one("q?")])["answers"][0]["answer"] == "fine"


def test_the_question_wait_stays_inside_what_was_measured():
    """An ordinary MCP tool call was measured tolerating 240s against Claude Code 2.1.221.
    Raising this above that ceiling would make the wait itself the failure."""
    assert mcp_server.QUESTION_ANSWER_TIMEOUT <= 240


def test_offered_options_reach_the_hub(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    bodies = []

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            bodies.append(body)
            return batch_post(["q-1"])
        return {"answered": True, "answer": "Postgres"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user(
        [
            {
                "question": "Which database?",
                "header": "Database",
                "options": [
                    {"label": "Postgres", "description": "server"},
                    {"label": "SQLite"},
                ],
                "multi_select": False,
            }
        ]
    )
    sent = bodies[0]["questions"][0]
    assert [o["label"] for o in sent["options"]] == ["Postgres", "SQLite"]
    assert result["answers"][0]["answer"] == "Postgres"


def test_the_structure_is_always_sent(monkeypatch):
    """There is no open-question shape any more — every entry carries options."""
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    bodies = []

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            bodies.append(body)
            return batch_post(["q-1"])
        return {"answered": True, "answer": "x"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    mcp_server.ask_user([one("Anything?")])
    sent = bodies[0]["questions"][0]
    assert len(sent["options"]) == 2
    assert sent["header"] == "H"


def test_a_multi_select_answer_comes_back_as_a_list(monkeypatch):
    """Returning a joined string would make every caller re-split it."""
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1"])
        return {"answered": True, "answer": "a, c", "answer_labels": ["a", "c"]}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user([one(multi_select=True, labels=("a", "c"))])
    assert result["answers"][0]["answer"] == ["a", "c"]


def test_a_single_select_answer_stays_a_string(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1"])
        return {"answered": True, "answer": "a", "answer_labels": ["a"]}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user([one()])
    assert result["answers"][0]["answer"] == "a"


def test_a_typed_answer_to_a_multi_select_is_not_forced_into_a_list(monkeypatch):
    """The operator answered with none of the options; there are no labels to return."""
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1"])
        return {"answered": True, "answer": "none of these", "answer_labels": []}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user([one(multi_select=True)])
    assert result["answers"][0]["answer"] == "none of these"


def test_header_and_multi_select_reach_the_hub(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    bodies = []

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            bodies.append(body)
            return batch_post(["q-1"])
        return {"answered": True, "answer": "x"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    mcp_server.ask_user([one(header="Database", multi_select=True)])
    sent = bodies[0]["questions"][0]
    assert sent["header"] == "Database"
    assert sent["multi_select"] is True


# --- batching -------------------------------------------------------------------------------


def test_a_batch_returns_every_answer_in_the_order_asked(monkeypatch):
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    answers = {
        "q-1": {"answered": True, "answer": "Postgres", "question": "Which database?"},
        "q-2": {"answered": True, "answer": "pnpm", "question": "Which package manager?"},
        "q-3": {"answered": True, "answer": "yes", "question": "Write tests?"},
    }

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1", "q-2", "q-3"])
        return answers[path.rsplit("/", 1)[-1]]

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user(
        [one("Which database?"), one("Which package manager?"), one("Write tests?")]
    )
    assert result["answered"] is True
    assert [entry["answer"] for entry in result["answers"]] == ["Postgres", "pnpm", "yes"]
    assert [entry["question_id"] for entry in result["answers"]] == ["q-1", "q-2", "q-3"]


def test_the_whole_batch_goes_in_one_request(monkeypatch):
    """Three separate posts would be three separate prompts, which is the thing being fixed."""
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    posts = []

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            posts.append(body)
            return batch_post(["q-1", "q-2"])
        return {"answered": True, "answer": "x"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    mcp_server.ask_user([one("first?"), one("second?")])
    assert len(posts) == 1
    assert [q["question"] for q in posts[0]["questions"]] == ["first?", "second?"]


def test_a_partly_answered_batch_reports_which_went_unanswered(monkeypatch):
    """The agent has to be able to say which decisions it made without an answer."""
    monkeypatch.setattr(mcp_server, "QUESTION_ANSWER_TIMEOUT", 0.05)
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1", "q-2"])
        if path.endswith("q-1"):
            return {"answered": True, "answer": "Postgres"}
        return {"answered": False}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user([one("Which database?"), one("Which package manager?")])
    assert result["answered"] is False
    assert result["answers"][0]["answer"] == "Postgres"
    assert result["answers"][1]["answered"] is False
    assert result["answers"][1]["answer"] is None
    assert "1 of 2" in result["note"]


def test_each_questions_own_multi_select_governs_its_answer_shape(monkeypatch):
    """A batch mixes shapes; using the first question's flag for all of them would be wrong."""
    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)

    def hub(method, path, body=None, *_a, **_k):
        if method == "POST":
            return batch_post(["q-1", "q-2"])
        if path.endswith("q-1"):
            return {"answered": True, "answer": "Postgres", "answer_labels": ["Postgres"]}
        return {"answered": True, "answer": "a, b", "answer_labels": ["a", "b"]}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    result = mcp_server.ask_user([one(multi_select=False), one(multi_select=True)])
    assert result["answers"][0]["answer"] == "Postgres"
    assert result["answers"][1]["answer"] == ["a", "b"]
