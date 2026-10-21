"""The other seams of `a-run-is-a-trace-you-can-export` (trace-1019), and the OTLP push.

`test_a_run_is_one_trace.py` drives a whole turn; these pin the seams that turn did not reach:
a worker invocation's trace, the waits a run's end derives from their own rows, and the outbox
that pushes ended spans to an operator's OTLP/HTTP endpoint (with its headers never returned).
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

import pytest
from sqlalchemy import select

from hub import trace_export, traces
from hub.db.engine import async_session_factory
from hub.db.models import PermissionRequest, Question, Run, TraceSpan
from hub.runner_adapters.one_shot import WorkerUsage
from hub.runner_events import tool_use_event
from hub.usage_accounting import record_turn_usage
from hub.worker import WorkerResult, record_invocation

PROJECT = "proj-test"
SECRET = "aw_live_" + "Kp4" * 11


async def _worker_trace() -> str:
    result = WorkerResult(
        "ok",
        answer_text=f"Title: the key {SECRET}",
        usage=WorkerUsage(input_tokens=10, output_tokens=3),
        exit_code=0,
        duration_ms=1200,
    )
    invocation_id = await record_invocation(
        project_id=PROJECT,
        kind="title",
        prompt_version="t1",
        runner_id=None,
        cli="claude",
        model="claude-haiku-4-5",
        conversation_id=None,
        result=result,
        prompt=f"Name this conversation. It mentions {SECRET}.",
    )
    assert invocation_id
    return invocation_id


@pytest.mark.asyncio
async def test_a_worker_call_is_a_redacted_one_span_trace(app, auth_headers):
    invocation_id = await _worker_trace()
    listed = await app.get(f"/api/v1/projects/{PROJECT}/traces", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    (summary,) = listed.json()["traces"]
    assert summary["kind"] == "worker" and summary["worker_kind"] == "title"
    assert summary["trace_id"] == traces.trace_id_for_worker(invocation_id)

    detail = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/{summary['trace_id']}", headers=auth_headers
    )
    assert detail.status_code == 200, detail.text
    (span,) = detail.json()["spans"]
    assert span["operation"] == "chat" and span["ended"] is True and span["status"] == "ok"
    assert span["attributes"]["gen_ai.usage.input_tokens"] == 10
    assert "Name this conversation" in json.dumps(span["attributes"]["gen_ai.input.messages"])
    assert "Title: the key" in json.dumps(span["attributes"]["gen_ai.output.messages"])
    assert SECRET not in detail.text


@pytest.mark.asyncio
async def test_a_runs_end_closes_its_spans_and_traces_its_waits(app, auth_headers):
    started = datetime.now(timezone.utc) - timedelta(seconds=30)
    run_id = "run-trace-waits"
    async with async_session_factory() as db:
        run = Run(
            id=run_id, project_id=PROJECT, agent="waiter", status="running", started_at=started
        )
        db.add(run)
        traces.start_run(db, run, prompt="wait for me", runner="claude", model="haiku")
        await db.commit()
    async with async_session_factory() as db:
        # A tool call the run ended inside, never answered.
        await traces.observe_output(
            db,
            project_id=PROJECT,
            run_id=run_id,
            kind="tool_use",
            content="Called Write",
            payload={"call_id": "c-open", "tool": "Write", "input": "{}"},
            at=started + timedelta(seconds=1),
        )
        db.add(
            PermissionRequest(
                id="perm-trace-1",
                project_id=PROJECT,
                agent="waiter",
                run_id=run_id,
                tool_name="Write",
                tool_use_id="c-open",
                tool_input={"file_path": "x", "content": SECRET},
                status="denied",
                decided_by="operator",
                created_at=started + timedelta(seconds=2),
                decided_at=started + timedelta(seconds=9),
            )
        )
        db.add(
            Question(
                id="q-trace-1",
                project_id=PROJECT,
                from_agent="waiter",
                question=f"Use {SECRET}?",
                answer="no",
                answered=True,
                created_by_run_id=run_id,
                created_at=started + timedelta(seconds=10),
                answered_at=started + timedelta(seconds=20),
            )
        )
        await db.commit()
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run.status = "failed"
        run.error = "it broke"
        run.ended_at = started + timedelta(seconds=25)
        await record_turn_usage(
            db, run_id=run_id, project_id=PROJECT, agent="waiter", runner="claude", sample=None
        )
        await db.commit()

    detail = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/by-run/{run_id}", headers=auth_headers
    )
    assert detail.status_code == 200, detail.text
    spans = {span["operation"]: span for span in detail.json()["spans"]}
    assert all(span["ended"] for span in detail.json()["spans"])
    assert spans["invoke_agent"]["status"] == "error"
    assert spans["invoke_agent"]["status_message"] == "it broke"
    tool = spans["execute_tool"]
    wait = spans["aw.permission_wait"]
    assert wait["parent_span_id"] == tool["span_id"]
    assert wait["attributes"]["aw.permission.status"] == "denied"
    assert wait["start_time"].startswith((started + timedelta(seconds=2)).isoformat()[:19])
    asked = spans["aw.ask_user"]
    assert asked["attributes"]["aw.question.answer"] == "no"
    assert SECRET not in detail.text


@pytest.mark.asyncio
async def test_a_permission_wait_redacts_its_arguments_as_the_tool_call_does(app, auth_headers):
    """F790: the wait span stored `tool_input` through the named patterns only, so a credential
    no pattern names (the high-entropy catch-all's catch) reached the span and the export, while
    the same call's `execute_tool` span, copied from the already-redacted tool event, hid it."""
    token = "Q7r8S9t0U1v2W3x4Y5z6A7b8C9d0E1f2G3h4"
    command = f"py -3.11 -c \"print('build', '{token}')\""
    started = datetime.now(timezone.utc) - timedelta(seconds=30)
    run_id = "run-trace-f790"
    async with async_session_factory() as db:
        run = Run(
            id=run_id, project_id=PROJECT, agent="waiter", status="running", started_at=started
        )
        db.add(run)
        traces.start_run(db, run, prompt="build it", runner="claude", model="haiku")
        await db.commit()
    event = tool_use_event(
        tool="PowerShell", category="shell", input_data={"command": command}, call_id="c-f790"
    )
    async with async_session_factory() as db:
        await traces.observe_output(
            db,
            project_id=PROJECT,
            run_id=run_id,
            kind=event.kind,
            content=event.content,
            payload=event.payload,
            at=started + timedelta(seconds=1),
        )
        db.add(
            PermissionRequest(
                id="perm-trace-f790",
                project_id=PROJECT,
                agent="waiter",
                run_id=run_id,
                tool_name="PowerShell",
                tool_use_id="c-f790",
                tool_input={"command": command},
                status="allowed",
                decided_by="operator",
                created_at=started + timedelta(seconds=2),
                decided_at=started + timedelta(seconds=9),
            )
        )
        await db.commit()
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
        run.status = "completed"
        run.ended_at = started + timedelta(seconds=25)
        await record_turn_usage(
            db, run_id=run_id, project_id=PROJECT, agent="waiter", runner="claude", sample=None
        )
        await db.commit()

    detail = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/by-run/{run_id}", headers=auth_headers
    )
    assert detail.status_code == 200, detail.text
    spans = {span["operation"]: span for span in detail.json()["spans"]}
    tool_args = spans["execute_tool"]["attributes"]["gen_ai.tool.call.arguments"]
    wait_args = spans["aw.permission_wait"]["attributes"]["gen_ai.tool.call.arguments"]
    assert token not in tool_args
    # The value is refused, not the arguments dropped: the command is still there, redacted.
    assert token not in wait_args
    assert "<redacted>" in wait_args and "print('build'" in wait_args
    assert token not in detail.text

    today = datetime.now(timezone.utc).date()
    exported = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/export",
        params={"since": today.isoformat(), "until": (today + timedelta(days=1)).isoformat()},
        headers=auth_headers,
    )
    assert exported.status_code == 200, exported.text
    assert token not in exported.text
    # The card still needs the raw input; only the span is redacted.
    async with async_session_factory() as db:
        request = await db.get(PermissionRequest, "perm-trace-f790")
        assert request.tool_input == {"command": command}


class _Receiver:
    def __init__(self) -> None:
        self.posts: List[Dict[str, Any]] = []
        receiver = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                receiver.posts.append(
                    {"path": self.path, "headers": dict(self.headers), "body": json.loads(raw)}
                )
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.mark.asyncio
async def test_ended_spans_are_pushed_once_to_the_configured_endpoint(app, auth_headers):
    receiver = _Receiver()
    try:
        before = await _worker_trace()  # ended before export was enabled: not replayed
        settings = await app.put(
            f"/api/v1/projects/{PROJECT}/traces/settings",
            json={
                "otlp_endpoint": receiver.url,
                "otlp_headers": {"Authorization": "Bearer collector-secret"},
                "export_enabled": True,
            },
            headers=auth_headers,
        )
        assert settings.status_code == 200, settings.text
        assert settings.json()["otlp_header_names"] == ["Authorization"]
        assert "collector-secret" not in settings.text
        after = await _worker_trace()

        assert await trace_export.push_once() == 1
        (post,) = receiver.posts
        assert post["path"] == "/v1/traces"
        assert post["headers"].get("Authorization") == "Bearer collector-secret"
        spans = [
            span
            for resource in post["body"]["resourceSpans"]
            for scope in resource["scopeSpans"]
            for span in scope["spans"]
        ]
        assert [span["traceId"] for span in spans] == [traces.trace_id_for_worker(after)]
        assert traces.trace_id_for_worker(before) not in json.dumps(post["body"])

        assert await trace_export.push_once() == 0  # marked; never sent twice
        read = await app.get(f"/api/v1/projects/{PROJECT}/traces/settings", headers=auth_headers)
        assert read.json()["exported_spans"] == 1
        assert read.json()["last_error"] is None
        assert "collector-secret" not in read.text
    finally:
        receiver.close()


@pytest.mark.asyncio
async def test_an_unreachable_endpoint_is_recorded_and_nothing_is_marked(app, auth_headers):
    trace_export._retry_after.clear()
    receiver = _Receiver()
    url = receiver.url
    receiver.close()  # nothing listens there now
    settings = await app.put(
        f"/api/v1/projects/{PROJECT}/traces/settings",
        json={"otlp_endpoint": url, "export_enabled": True},
        headers=auth_headers,
    )
    assert settings.status_code == 200, settings.text
    await _worker_trace()
    assert await trace_export.push_once() == 0
    read = await app.get(f"/api/v1/projects/{PROJECT}/traces/settings", headers=auth_headers)
    assert read.json()["last_error"]
    async with async_session_factory() as db:
        unmarked = (
            await db.execute(select(TraceSpan.span_id).where(TraceSpan.exported_at.is_(None)))
        ).all()
    assert unmarked
    trace_export._retry_after.clear()


@pytest.mark.asyncio
async def test_settings_refuse_a_bad_endpoint_and_enabling_without_one(app, auth_headers):
    bad = await app.put(
        f"/api/v1/projects/{PROJECT}/traces/settings",
        json={"otlp_endpoint": "ftp://nope"},
        headers=auth_headers,
    )
    assert bad.status_code == 422
    bare = await app.put(
        f"/api/v1/projects/{PROJECT}/traces/settings",
        json={"export_enabled": True},
        headers=auth_headers,
    )
    assert bare.status_code == 422
    window = await app.get(
        f"/api/v1/projects/{PROJECT}/traces/export",
        params={"since": "2026-10-20", "until": "2026-10-19"},
        headers=auth_headers,
    )
    assert window.status_code == 422
