"""Every body an MCP tool builds must validate against the schema on the route it posts to.

`hub/hub/mcp_server.py` is spawned standalone and may import only stdlib + fastmcp, so it
restates what it sends rather than importing the Hub's models. That restatement is free to drift,
and when it does the failure is silent until an agent tries to use the tool.

It drifted once already, and expensively. `conversation_id` was added to the MCP `send_message`
tool and to `MessageCreate` (the *operator* route's schema) but not to `AgentMessageCreate` (the
agent route's). Because the tool puts the key in every body it builds — null included — and the
schema sets `extra: "forbid"`, which rejects a forbidden key regardless of value, **every**
agent-to-agent message failed with `422: conversation_id: Extra inputs are not permitted`. Not
only the ones naming a conversation.

The existing tests could not see it: `test_mcp_server.py` mocks `urlopen` and asserts the body
the tool builds, and `test_archived_send_refusal.py` reaches the *operator* route while claiming
to reach "the same route". Both sides were tested; the join between them was not.

This test is that join. It reads the real request model off each FastAPI route and feeds it the
real body the tool produces.
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel, ValidationError

from ._routing import iter_api_routes

AGENT_ACTIONS_PREFIX = "/api/v1/agent-actions"


@pytest.fixture(scope="module")
def routes():
    """The real FastAPI app. The suite's `app` fixture is an httpx client wrapping it, which
    does not expose the routing table this test has to read."""
    from hub.main import create_app

    return create_app()


def _request_model(app, method: str, path: str) -> type[BaseModel]:
    """The Pydantic model FastAPI will validate this route's body against.

    Matched through the route's own compiled pattern rather than by string equality, so a tool
    posting to `/tasks/task-1` resolves against the `/tasks/{task_id}` route the way a real
    request would.
    """
    full_path = f"{AGENT_ACTIONS_PREFIX}{path}"
    for template, route in iter_api_routes(app):
        if method not in route.methods:
            continue
        # `template` is the full path with parameters still in `{braces}`; `route.path_regex` only
        # understands the route's own tail, because a router's prefix is not part of it on newer
        # Starlette. Match the tail and require the prefix to be a literal match.
        prefix = template[: len(template) - len(route.path)]
        if not full_path.startswith(prefix):
            continue
        if not route.path_regex.match(full_path[len(prefix) :]):
            continue
        for field in route.dependant.body_params:
            annotation = field.field_info.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                return annotation
    raise AssertionError(f"no {method} {AGENT_ACTIONS_PREFIX}{path} route with a body model")


@pytest.fixture
def capture(monkeypatch):
    """Run an MCP tool and hand back the (method, path, body) it tried to send."""
    sent: Dict[str, Any] = {}

    def urlopen(request, timeout=10):
        sent["path"] = request.full_url.split(AGENT_ACTIONS_PREFIX, 1)[1]
        sent["method"] = request.get_method()
        sent["body"] = json.loads(request.data) if request.data else None
        response = MagicMock()
        response.read.return_value = b"{}"
        response.__enter__ = lambda value: value
        response.__exit__ = MagicMock(return_value=False)
        return response

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_test-key")
    return sent


def _assert_body_is_accepted(app, sent: Dict[str, Any]) -> None:
    model = _request_model(app, sent["method"], sent["path"])
    try:
        model(**sent["body"])
    except ValidationError as exc:
        rejected = ", ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise AssertionError(
            f"mcp_server sends a body that {model.__name__} rejects "
            f"({sent['method']} {sent['path']}): {rejected}"
        ) from exc


def test_send_message_without_a_conversation_is_accepted(routes, capture):
    """The common case: a sending agent has no reason to know another agent's conversation ids."""
    from hub.mcp_server import send_message

    send_message(to_agent="codex-2", subject="Handover", content="Please pick this up.")
    assert capture["body"]["conversation_id"] is None, "the key is sent even when unset"
    _assert_body_is_accepted(routes, capture)


def test_send_message_naming_a_conversation_is_accepted(routes, capture):
    from hub.mcp_server import send_message

    send_message(
        to_agent="codex-2",
        subject="Handover",
        content="Please pick this up.",
        conversation_id="conv-abc123",
    )
    assert capture["body"]["conversation_id"] == "conv-abc123"
    _assert_body_is_accepted(routes, capture)


def _create_task(**kwargs: Any) -> None:
    from hub.mcp_server import create_task

    create_task(**kwargs)


def _update_task(**kwargs: Any) -> None:
    from hub.mcp_server import update_task

    update_task(**kwargs)


def _ask_user(**kwargs: Any) -> None:
    from hub.mcp_server import ask_user

    ask_user(**kwargs)


def _record_evidence(**kwargs: Any) -> None:
    from hub.mcp_server import record_evidence

    record_evidence(**kwargs)


def _decide_evidence(**kwargs: Any) -> None:
    from hub.mcp_server import decide_evidence

    decide_evidence(**kwargs)


@pytest.mark.parametrize(
    "call, kwargs",
    [
        (_create_task, {"title": "Ship it", "description": "All of it", "assignee": "codex-2"}),
        (_create_task, {"title": "Minimal"}),
        (_update_task, {"task_id": "task-1", "status": "in_progress"}),
        (
            _ask_user,
            {
                "questions": [
                    {
                        "question": "Which package manager?",
                        "header": "Package manager",
                        "options": [{"label": "npm"}, {"label": "pnpm"}],
                        "multi_select": False,
                    }
                ]
            },
        ),
        (
            _record_evidence,
            {"identifier": "FR-1", "summary": "18 tests pass", "kind": "test_result"},
        ),
        # The minimal call, which is the one that matters: `EvidenceRecord` sets
        # `extra: "forbid"`, so an optional key the tool sends unconditionally would reject every
        # body -- exactly the `send_message`/`conversation_id` outage this file exists for.
        (_record_evidence, {"identifier": "FR-1"}),
        (
            _record_evidence,
            {"identifier": "FR-1", "document": "spec/x.html", "task_id": "task-1"},
        ),
        (_decide_evidence, {"evidence_id": "ev-1", "decision": "accepted"}),
        (
            _decide_evidence,
            {"evidence_id": "ev-1", "decision": "rejected", "reason": "does not cover FR-1"},
        ),
    ],
    ids=[
        "create_task-full",
        "create_task-minimal",
        "update_task",
        "ask_user",
        "record_evidence-full",
        "record_evidence-minimal",
        "record_evidence-scoped",
        "decide_evidence-accept",
        "decide_evidence-reject",
    ],
)
def test_every_other_tool_body_is_accepted_by_its_route(routes, capture, call, kwargs):
    """The same join for the rest of the surface, so the next drift is caught by this file
    rather than by an agent mid-turn."""
    try:
        call(**kwargs)
    except Exception as exc:  # noqa: BLE001 — a stubbed response may not satisfy the tool
        # The request still went out; what came back is not this test's subject.
        if "path" not in capture:
            raise AssertionError(f"{call.__name__} sent no request at all: {exc}") from exc
    _assert_body_is_accepted(routes, capture)


def test_the_helper_would_actually_fail_on_drift(routes, capture):
    """A contract test that cannot fail is worse than none — this proves this one can."""
    from hub.mcp_server import send_message

    send_message(to_agent="codex-2", subject="s", content="c")
    capture["body"]["invented_field"] = "drift"
    with pytest.raises(AssertionError, match="Extra inputs are not permitted"):
        _assert_body_is_accepted(routes, capture)
