"""Unit tests for the canonical Hub-owned, identity-bound MCP surface."""

import json
import urllib.error
from unittest.mock import MagicMock

import pytest


def _response(body=b"{}"):
    response = MagicMock()
    response.read.return_value = body
    response.__enter__ = lambda value: value
    response.__exit__ = MagicMock(return_value=False)
    return response


@pytest.fixture
def hub(monkeypatch):
    calls = []
    responses = []

    def urlopen(request, timeout=10):
        calls.append(request)
        result = responses.pop(0) if responses else b"{}"
        if isinstance(result, Exception):
            raise result
        return _response(result)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setenv("HUB_URL", "http://localhost:8000")
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_test-key")
    return calls, responses


def _body(request):
    return json.loads(request.data) if request.data else None


def test_hub_request_binds_run_token_without_identity_headers(hub):
    from hub.mcp_server import _hub_request

    calls, responses = hub
    responses.append(b'{"ok": true}')
    assert _hub_request("POST", "/tasks", {"title": "T"}) == {"ok": True}
    request = calls[0]
    assert request.get_header("Authorization") == "Bearer aw_run_test-key"
    assert request.get_header("X-agentweave-agent") is None
    assert request.get_header("X-agentweave-run") is None
    assert request.full_url.endswith("/api/v1/agent-actions/tasks")
    assert _body(request) == {"title": "T"}


def test_create_spec_document_reaches_the_create_route_with_no_title(hub):
    from hub.mcp_server import create_spec_document

    calls, responses = hub
    responses.append(b'{"path": "spec/changes/amber-griffin/spec.html", "phase": "exploring"}')
    assert create_spec_document() == {
        "path": "spec/changes/amber-griffin/spec.html",
        "phase": "exploring",
    }
    request = calls[0]
    assert request.full_url.endswith("/api/v1/agent-actions/spec/documents/create")
    assert _body(request) == {}


def test_create_spec_document_sends_only_the_title_it_was_given(hub):
    from hub.mcp_server import create_spec_document

    calls, responses = hub
    responses.append(b'{"path": "spec/changes/amber-griffin/spec.html", "phase": "exploring"}')
    create_spec_document(title="A finding worth writing up")
    assert _body(calls[0]) == {"title": "A finding worth writing up"}


def test_send_message_payload_contains_no_identity_or_run(hub):
    from hub.mcp_server import send_message

    calls, responses = hub
    responses.append(b'{"id": "msg-1"}')
    assert send_message("worker", "Subject", "Content") == {
        "success": True,
        "message_id": "msg-1",
    }
    assert _body(calls[0]) == {
        "recipient": "worker",
        "subject": "Subject",
        "content": "Content",
        "type": "message",
        "task_id": None,
        # Where the message goes is the sender's choice; unset means the thread already bound
        # between sender and recipient, or a fresh one if none is bound. It is routing, not
        # identity — which is what this test guards.
        "conversation_id": None,
        "start_new_thread": False,
    }


def test_send_message_docstring_does_not_claim_recency_and_declares_start_new_thread():
    """Recency delivery was removed when the binding contract shipped; the tool's own
    documentation must not keep teaching agents the old model."""
    from hub.mcp_server import send_message

    doc = send_message.__doc__ or ""
    assert "most recent" not in doc.lower()
    assert "recent" not in doc.lower()
    assert "start_new_thread" in doc
    import inspect

    default = inspect.signature(send_message).parameters["start_new_thread"].default
    assert default is False


def test_effect_refuses_unbound_run_credential(hub, monkeypatch):
    from hub.mcp_server import send_message

    calls, _ = hub
    monkeypatch.delenv("AW_RUN_TOKEN")
    with pytest.raises(RuntimeError, match="No bound run credential"):
        send_message("worker", "Subject", "Content")
    assert calls == []


def test_task_tools_use_agent_ledger_endpoints_without_assigner(hub):
    from hub.mcp_server import create_task, get_task, list_tasks, update_task

    calls, responses = hub
    responses.extend(
        [
            b'{"id":"task-1"}',
            b'[{"id":"task-1"}]',
            b'{"id":"task-1"}',
            b'{"id":"task-1","status":"completed"}',
        ]
    )
    assert create_task("Build", assignee="worker")["id"] == "task-1"
    assert "assigner" not in _body(calls[0])
    assert list_tasks("worker")[0]["id"] == "task-1"
    assert "agent=worker" in calls[1].full_url
    assert get_task("task-1")["id"] == "task-1"
    assert update_task("task-1", "completed")["status"] == "completed"
    assert _body(calls[3]) == {"status": "completed", "notes": None}


def test_update_task_forwards_notes_so_a_rejection_is_legible_on_the_task_itself(hub):
    """A status change alone leaves the task record silent about why; `notes` is the only way a
    reviewer's reasoning survives on the task rather than only in its own run transcript."""
    from hub.mcp_server import update_task

    calls, responses = hub
    responses.append(b'{"id":"task-1","status":"revision_needed"}')
    update_task(
        "task-1",
        "revision_needed",
        notes="Scope creep in the same commit: quantize() "
        "logic looks wrong and needs to be split out before this can be reviewed.",
    )
    assert _body(calls[0]) == {
        "status": "revision_needed",
        "notes": "Scope creep in the same commit: quantize() logic looks wrong and needs to be "
        "split out before this can be reviewed.",
    }


def test_question_tools_bind_asker_and_return_answer(hub, monkeypatch):
    """`ask_user` now waits and returns the answer itself, so it consumes the poll response its
    own wait makes. `get_answer` remains for an agent that deliberately did not block."""
    from hub import mcp_server
    from hub.mcp_server import ask_user, get_answer

    monkeypatch.setattr(mcp_server, "QUESTION_POLL_SECONDS", 0.01)
    calls, responses = hub
    responses.extend(
        [
            b'{"batch_id":"qbatch-1","questions":[{"id":"q-1"}]}',
            b'{"answered":true,"answer":"yes"}',  # consumed by ask_user's own wait
            b'{"answered":true,"answer":"yes"}',  # for the explicit get_answer below
        ]
    )
    answered = ask_user(
        [
            {
                "question": "Proceed?",
                "header": "Decide",
                "options": [{"label": "Yes"}, {"label": "No"}],
                "multi_select": False,
            }
        ]
    )
    assert answered["question_ids"] == ["q-1"]
    assert answered["answered"] is True
    assert answered["answers"][0]["answer"] == "yes"
    # The whole batch goes in one request, and each entry carries its full structure —
    # `header`/`options`/`multi_select` are sent unconditionally, so the Hub never has to
    # distinguish "absent" from "not wanted".
    assert _body(calls[0]) == {
        "questions": [
            {
                "question": "Proceed?",
                "header": "Decide",
                "options": [{"label": "Yes"}, {"label": "No"}],
                "multi_select": False,
            }
        ],
        "blocking": True,
    }
    # `declined` is reported alongside `answered`: a question the operator closed without answering
    # is settled, not pending, and a poller told otherwise would wait forever for a decision that
    # has already been made.
    assert get_answer("q-1") == {
        "answered": True,
        "declined": False,
        "answer": "yes",
        "pending": False,
    }


def test_request_agent_uses_bound_run_without_requester_field(hub):
    from hub.mcp_server import request_agent

    calls, responses = hub
    responses.append(b'{"agent":"worker-2","status":"queued"}')
    assert request_agent("worker-2", "worker-template", "Implement it")["status"] == "queued"
    assert _body(calls[0]) == {
        "name": "worker-2",
        "template": "worker-template",
        "task": "Implement it",
    }


@pytest.mark.parametrize(
    ("call", "method", "path", "body"),
    [
        (
            lambda module: module.create_job("N", "worker", "M", "0 2 * * *"),
            "POST",
            "/api/v1/agent-actions/jobs",
            {
                "name": "N",
                "agent": "worker",
                "message": "M",
                "cron": "0 2 * * *",
                "session_mode": "new",
            },
        ),
        (
            lambda module: module.toggle_job("job-1", True),
            "PATCH",
            "/api/v1/agent-actions/jobs/job-1",
            {"enabled": True},
        ),
        (
            lambda module: module.run_job("job-1"),
            "POST",
            "/api/v1/agent-actions/jobs/job-1/run",
            None,
        ),
    ],
)
def test_job_mutations_reach_only_governed_api(call, method, path, body, hub):
    from hub import mcp_server

    calls, responses = hub
    responses.append(b'{"ok":true}')
    assert call(mcp_server)["ok"] is True
    assert calls[0].method == method
    assert calls[0].full_url.endswith(path)
    assert _body(calls[0]) == body


def test_archive_job_asks_the_operator_before_reaching_the_archive_route(hub, monkeypatch):
    """D18/B3.2: `archive_job` puts the request to the operator itself — via `_ask_operator`,
    the same mechanism `approve_tool_call` uses for a `manual`-posture harness prompt — before
    ever calling the governed archive route. This is deliberately NOT the ordinary
    `_job_effect`/governed-API pattern the other job tools use (see the parametrize above),
    because none of those reach the operator at all unless the run's own permission posture
    already routes through `approve_tool_call` — an `auto` posture would skip that entirely."""
    from hub import mcp_server
    from hub.mcp_server import archive_job

    monkeypatch.setattr(mcp_server, "OPERATOR_POLL_SECONDS", 0.01)
    calls, responses = hub
    responses.extend(
        [
            b'{"id":"perm-1","status":"pending"}',
            b'{"id":"perm-1","status":"allowed"}',
            b'{"ok":true}',
        ]
    )
    assert archive_job("job-1") == {"ok": True}

    assert calls[0].method == "POST"
    assert calls[0].full_url.endswith("/api/v1/agent-actions/permission-requests")
    assert _body(calls[0]) == {
        "tool_name": "archive_job",
        "tool_use_id": "archive-job-1",
        "tool_input": {"job_id": "job-1"},
    }
    assert calls[1].method == "GET"
    assert calls[1].full_url.endswith("/api/v1/agent-actions/permission-requests/perm-1")
    assert calls[2].method == "POST"
    assert calls[2].full_url.endswith("/api/v1/agent-actions/jobs/job-1/archive")


@pytest.mark.parametrize("posture", [None, "auto", "operator"])
def test_archive_job_asks_the_operator_under_every_posture(hub, monkeypatch, posture):
    """D18's whole point: the standing `allow_agent_jobs` allowance is not enough alone, and
    this must not silently degrade to `_decide`'s blanket 'the Hub's own tools' allow just
    because the run's posture happens to be `auto` or unset."""
    from hub import mcp_server
    from hub.mcp_server import archive_job

    monkeypatch.setattr(mcp_server, "OPERATOR_POLL_SECONDS", 0.01)
    if posture is None:
        monkeypatch.delenv("AW_PERMISSION_POSTURE", raising=False)
    else:
        monkeypatch.setenv("AW_PERMISSION_POSTURE", posture)
    calls, responses = hub
    responses.extend(
        [
            b'{"id":"perm-1","status":"pending"}',
            b'{"id":"perm-1","status":"allowed"}',
            b'{"ok":true}',
        ]
    )
    archive_job("job-1")
    assert calls[0].full_url.endswith("/permission-requests")


def test_archive_job_denied_by_the_operator_never_reaches_the_archive_route(hub, monkeypatch):
    from hub import mcp_server
    from hub.mcp_server import HubAPIError, archive_job

    monkeypatch.setattr(mcp_server, "OPERATOR_POLL_SECONDS", 0.01)
    calls, responses = hub
    responses.extend(
        [
            b'{"id":"perm-1","status":"pending"}',
            b'{"id":"perm-1","status":"denied"}',
        ]
    )
    with pytest.raises(HubAPIError, match="not approved"):
        archive_job("job-1")
    # Only the operator ask happened -- a denial must never fall through to archiving anyway.
    assert len(calls) == 2


def test_create_loop_refuses_with_no_stop_condition_before_any_hub_call(hub):
    """Design D2: the refusal is client-side, in `create_loop` itself, checked before the HTTP
    call is made — a loop with no stop condition never reaches the Hub at all."""
    from hub.mcp_server import HubAPIError, create_loop

    calls, _ = hub
    with pytest.raises(HubAPIError, match="stop condition"):
        create_loop("N", "worker", "M", "0 2 * * *")
    assert calls == []


def test_create_loop_accepts_stop_at_alone(hub):
    from hub.mcp_server import create_loop

    calls, responses = hub
    responses.append(b'{"ok":true}')
    create_loop("N", "worker", "M", "0 2 * * *", stop_at="2026-09-01T00:00:00Z")
    assert calls[0].method == "POST"


def test_create_loop_sends_the_widened_governed_jobs_payload(hub):
    """`create_loop` posts to the same `/agent-actions/jobs` route `create_job` does, now
    widened with the loop-opt-in and `initial_tasks` fields (design D2). No `session_mode` —
    a loop's continuity is always by checkpoint (design D4), never a resumed session.

    `spec_document_id` is `None` here as of `loop-becomes-a-flow` group 7: a loop that declares a
    document is a flow, and `create_loop` now refuses one. The field stays in the payload because
    the route still accepts it — see the schema test that asserts the two agree."""
    from hub.mcp_server import create_loop

    calls, responses = hub
    responses.append(b'{"ok":true}')
    create_loop(
        "Nightly sweep",
        "worker",
        "Work the queue",
        "0 2 * * *",
        purpose="keep the backlog tidy",
        stop_when_queue_empties=True,
        initial_tasks=[{"title": "First task"}],
    )
    assert calls[0].method == "POST"
    assert calls[0].full_url.endswith("/api/v1/agent-actions/jobs")
    assert _body(calls[0]) == {
        "name": "Nightly sweep",
        "agent": "worker",
        "message": "Work the queue",
        "cron": "0 2 * * *",
        "purpose": "keep the backlog tidy",
        "stop_at": None,
        "stop_when_queue_empties": True,
        # None, not False: "the operator did not say" and "the operator said no" are different
        # rows, and only the first resolves to the product's current default.
        "work_needs_evidence": None,
        "spec_document_id": None,
        "initial_tasks": [{"title": "First task"}],
    }


def test_create_flow_sends_the_same_payload_a_loop_does_plus_the_document(hub):
    """`loop-becomes-a-flow` task 7.3, and the load-bearing test of design D1.

    D1 says a flow is *a configuration, not a record* — three tiers, one row, one route. So this
    body must be identical to `create_loop`'s but for `spec_document_id`. If the two ever diverge, a
    `Flow` table has grown in all but name, which is the thing D1 rejected.

    This assertion is inherited from `create_loop`, where it lived with `spec_document_id="doc-1"`
    until group 7 moved the capability. It is moved rather than dropped because it is what keeps the
    tool and the route it posts to in step."""
    from hub.mcp_server import create_flow

    calls, responses = hub
    responses.append(b'{"ok":true}')
    create_flow(
        "Nightly decomposition",
        "worker",
        "Work the queue",
        "doc-1",
        cron="0 2 * * *",
        purpose="decompose the backlog",
        stop_when_queue_empties=True,
        initial_tasks=[{"title": "First task"}],
    )
    assert calls[0].method == "POST"
    assert calls[0].full_url.endswith("/api/v1/agent-actions/jobs")
    assert _body(calls[0]) == {
        "name": "Nightly decomposition",
        "agent": "worker",
        "message": "Work the queue",
        "cron": "0 2 * * *",
        "purpose": "decompose the backlog",
        "stop_at": None,
        "stop_when_queue_empties": True,
        # Always None on this tool: a flow refuses the field client-side, and it stays in the body
        # so the two payloads remain identical but for the document, which is what D1 asserts.
        "work_needs_evidence": None,
        "spec_document_id": "doc-1",
        "initial_tasks": [{"title": "First task"}],
    }


def test_the_two_tools_post_bodies_that_differ_only_in_the_document(hub):
    """D1 asserted directly rather than inferred from the two tests above, which could drift apart
    one edit at a time without either failing."""
    from hub.mcp_server import create_flow, create_loop

    calls, responses = hub
    responses.extend([b'{"ok":true}', b'{"ok":true}'])
    kwargs = {"purpose": "p", "stop_when_queue_empties": True, "initial_tasks": [{"title": "T"}]}
    create_loop("N", "worker", "M", "0 2 * * *", **kwargs)
    create_flow("N", "worker", "M", "doc-1", cron="0 2 * * *", **kwargs)

    loop_body, flow_body = _body(calls[0]), _body(calls[1])
    assert loop_body["spec_document_id"] is None
    assert flow_body["spec_document_id"] == "doc-1"
    assert {k: v for k, v in loop_body.items() if k != "spec_document_id"} == {
        k: v for k, v in flow_body.items() if k != "spec_document_id"
    }


def test_create_flow_without_a_document_is_refused_before_any_hub_call(hub):
    """Task 7.1. The `str` annotation is what a well-behaved client enforces; this is what catches
    the empty string, and a `None` from a client that did not. Not redundant with the annotation —
    deleting it as such is the mistake the review anticipated."""
    from hub.mcp_server import HubAPIError, create_flow

    calls, _responses = hub
    for missing in ("", None):
        with pytest.raises(HubAPIError) as excinfo:
            create_flow("N", "worker", "M", missing, stop_when_queue_empties=True)
        assert "spec_document_id" in str(excinfo.value)
        assert "create_loop" in str(excinfo.value)
    assert calls == []


def test_create_flow_still_needs_a_stop_condition(hub):
    """A flow is a loop in every respect but its queue behaviour, and *"a loop that cannot stop is
    not created"* is one of the respects it keeps."""
    from hub.mcp_server import HubAPIError, create_flow

    calls, _responses = hub
    with pytest.raises(HubAPIError) as excinfo:
        create_flow("N", "worker", "M", "doc-1")
    assert "stop condition" in str(excinfo.value)
    assert calls == []


def test_create_loop_with_a_document_is_refused_and_names_create_flow(hub):
    """Task 7.2. The refusal keeps the parameter rather than dropping it from the signature: the
    schema test asserts `create_loop` offers exactly the fields the route accepts, precisely so a
    caller's intent is never silently dropped, and an unexpected-argument `TypeError` tells the
    caller nothing about what to do instead."""
    from hub.mcp_server import HubAPIError, create_loop

    calls, _responses = hub
    with pytest.raises(HubAPIError) as excinfo:
        create_loop(
            "N", "worker", "M", "0 2 * * *", stop_when_queue_empties=True, spec_document_id="doc-1"
        )
    assert "create_flow" in str(excinfo.value)
    assert calls == []


def test_job_mutation_preserves_forbidden_failure(hub):
    from hub.mcp_server import HubAPIError, run_job

    _, responses = hub
    responses.append(
        urllib.error.HTTPError(
            "http://localhost/api/v1/projects/proj-test/jobs/job-1/run",
            403,
            "Forbidden",
            {},
            MagicMock(read=lambda: b'{"detail":"operator approval required"}'),
        )
    )
    with pytest.raises(HubAPIError) as raised:
        run_job("job-1")
    assert raised.value.status_code == 403
    assert "operator approval required" in raised.value.detail


@pytest.mark.parametrize("status_code", [403, 404, 409, 422])
def test_mcp_adapter_preserves_typed_application_failures(hub, status_code):
    from hub.mcp_server import HubAPIError, _hub_request

    _, responses = hub
    responses.append(
        urllib.error.HTTPError(
            "http://localhost/api/v1/agent-actions/tasks/x",
            status_code,
            "application failure",
            {},
            MagicMock(read=lambda: b'{"detail":"typed failure"}'),
        )
    )

    with pytest.raises(HubAPIError) as raised:
        _hub_request("GET", "/tasks/x")
    assert raised.value.status_code == status_code
    assert raised.value.detail == "typed failure"


def test_hub_request_timeout_is_ten_seconds(monkeypatch):
    from hub.mcp_server import _hub_request

    captured = {}

    def urlopen(request, timeout=None):
        captured["timeout"] = timeout
        return _response(b"{}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.setenv("AW_RUN_TOKEN", "aw_run_test")
    _hub_request("GET", "/tasks")
    assert captured["timeout"] == 10


def test_rejected_request_names_the_attempted_endpoint(hub):
    """Task 5.1/5.4: a request the Hub reached and rejected must name which endpoint was
    attempted, not just the bare status code and detail."""
    from hub.mcp_server import HubAPIError, _hub_request

    _, responses = hub
    responses.append(
        urllib.error.HTTPError(
            "http://localhost/api/v1/agent-actions/messages",
            404,
            "Not Found",
            {},
            MagicMock(read=lambda: b'{"detail":"Unknown recipient \'ghost\'"}'),
        )
    )

    with pytest.raises(HubAPIError) as raised:
        _hub_request("POST", "/messages")

    assert raised.value.method == "POST"
    assert raised.value.path == "/messages"
    assert "POST /messages" in str(raised.value)
    assert "Unknown recipient" in str(raised.value)


def test_unreachable_hub_is_distinguishable_from_a_rejected_request(hub):
    """Task 5.2: an unreachable destination (no Hub answered at all) must be
    distinguishable, by exception type and by message, from a reached-and-rejected
    request — the two point at different problems (network/misconfiguration vs. a
    validation or policy failure the Hub itself raised)."""
    from hub.mcp_server import HubAPIError, HubUnreachableError, _hub_request

    _, responses = hub
    responses.append(urllib.error.URLError("Connection refused"))

    with pytest.raises(HubUnreachableError) as raised:
        _hub_request("POST", "/messages")

    assert not isinstance(raised.value, HubAPIError)
    assert "Cannot reach the Hub" in str(raised.value)
    assert "POST /messages" in str(raised.value)
    assert "HUB_URL" in str(raised.value)
    # Distinguishable phrasing from the rejected case, not just a distinguishable type.
    assert "rejected" not in str(raised.value)


def test_create_loop_carries_the_declaration_it_was_given(hub):
    """`a-loop-declares-whether-it-needs-evidence` task 7.1.

    An agent creating a loop is the caller who most needs to know that approving its tasks writes
    to the project's main branch, so the tool takes the declaration rather than leaving it to a
    surface the agent cannot reach.
    """
    from hub.mcp_server import create_loop

    calls, responses = hub
    responses.append(b'{"ok":true}')
    create_loop(
        "Nightly sweep",
        "worker",
        "Work the queue",
        "0 2 * * *",
        stop_when_queue_empties=True,
        work_needs_evidence=True,
    )
    assert _body(calls[0])["work_needs_evidence"] is True


def test_create_flow_refuses_the_declaration_and_says_why(hub):
    """Task 7.5, and it is one decision with the resolver's flow arm rather than two.

    A flow decomposes a document, so its requirements *are* the evidence chain and accepted
    evidence always decides what approval merges. The parameter stays in the signature for the
    reason `create_loop` keeps `spec_document_id`: an unexpected-argument `TypeError` tells the
    caller nothing about what to do instead, and the schema parity test requires the two tools to
    offer the same fields.
    """
    from hub.mcp_server import HubAPIError, create_flow

    calls, _responses = hub
    for value in (True, False):
        with pytest.raises(HubAPIError) as excinfo:
            create_flow(
                "N",
                "worker",
                "M",
                "doc-1",
                stop_when_queue_empties=True,
                work_needs_evidence=value,
            )
        assert "create_loop" in str(excinfo.value)
        assert "evidence" in str(excinfo.value)
    assert calls == []
