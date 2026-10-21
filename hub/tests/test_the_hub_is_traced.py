"""Acceptance test for `everything-the-hub-does-is-in-a-trace` (trace-hub-wide, trace-D4, Tier 2).

Each test drives one slice through the product's real seams and reads the result back through the
product's own trace routes:

1. requests: the real ASGI stack answers the operator's and a run's requests; the mutating, the
   failing and the run's are recorded, the operator's routine reads are not unless asked, and the
   run's request nests under its open tool span;
2. events: `persist_event`, from a route and from nowhere;
3. background work: a real project check run, real git and real check subprocesses;
4. logs: the warning the check runner really logs when its merge raises.

Spans the Hub writes off the request path are flushed with `traces.flush_spans()` (design D1)
instead of waiting for the lifespan writer. Written before the build and seen failing; each test
is a strict xfail until the slice its marker names removes the marker.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from hub import project_checks, trace_export, traces
from hub.agent_auth import hash_run_token, mint_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.output_recording import record_agent_output
from hub.utils import persist_event, short_id

from .test_project_checks_run import FAIL, PASS, _project, _task_with_work
from .test_trace_seams import _Receiver

PROJECT = "proj-test"
BASE = f"/api/v1/projects/{PROJECT}"
CALL = "toolu_hub_wide_1"
#: A Hub key shape, which the named patterns redact wherever it appears.
SECRET = "aw_live_" + "Hw9" * 11


async def _flush() -> None:
    flush = getattr(traces, "flush_spans", None)
    if flush is not None:
        await flush()


async def _roots(app, headers, operation: str) -> List[Dict[str, Any]]:
    """Every root of *operation*, each with its full spans (the list carries no attributes)."""
    listed = await app.get(f"{BASE}/traces", params={"operation": operation}, headers=headers)
    assert listed.status_code == 200, listed.text
    found = []
    for row in listed.json()["traces"]:
        if row["operation"] != operation:
            continue
        one = await app.get(f"{BASE}/traces/{row['trace_id']}", headers=headers)
        assert one.status_code == 200, one.text
        spans = one.json()["spans"]
        root = next(span for span in spans if span["parent_span_id"] is None)
        found.append({"root": root, "spans": spans, "trace_id": row["trace_id"]})
    return found


def _requests(roots, method: str, route_end: str) -> List[Dict[str, Any]]:
    return [
        r["root"]
        for r in roots
        if r["root"]["attributes"].get("http.request.method") == method
        and str(r["root"]["attributes"].get("http.route", "")).endswith(route_end)
    ]


# --- 1. requests ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mutating_and_failing_requests_are_spans_and_reads_only_when_asked(app, auth_headers):
    created = await app.post(f"{BASE}/tasks", json={"title": "Traced work"}, headers=auth_headers)
    assert created.status_code == 201, created.text
    polled = await app.get(f"{BASE}/tasks", headers=auth_headers)
    assert polled.status_code == 200, polled.text
    missing = await app.get(f"{BASE}/tasks/task-000000000000", headers=auth_headers)
    assert missing.status_code == 404, missing.text
    await _flush()

    roots = await _roots(app, auth_headers, "aw.request")
    [post] = _requests(roots, "POST", "/tasks")
    attributes = post["attributes"]
    assert "{project_id}" in attributes["http.route"], "the route template, not the path"
    assert attributes["http.response.status_code"] == 201
    assert attributes["aw.actor"] == "operator"
    assert attributes["aw.project.id"] == PROJECT
    assert post["end_time"] is not None and post["status"] != "error"
    [not_found] = _requests(roots, "GET", "/{task_id}")
    assert not_found["attributes"]["http.response.status_code"] == 404
    assert _requests(roots, "GET", "/tasks") == [], "the app's routine read is not recorded"

    # 2. events: the event the create emitted is on its request span.
    assert "task_created" in [event["name"] for event in post["events"]]

    asked = await app.put(
        f"{BASE}/traces/settings", json={"record_reads": True}, headers=auth_headers
    )
    assert asked.status_code == 200, asked.text
    assert asked.json()["record_reads"] is True
    polled = await app.get(f"{BASE}/tasks", headers=auth_headers)
    assert polled.status_code == 200, polled.text
    await _flush()
    roots = await _roots(app, auth_headers, "aw.request")
    assert len(_requests(roots, "GET", "/tasks")) == 1, "recorded once the project asks"


@pytest.mark.asyncio
async def test_a_runs_request_nests_under_its_open_tool_span(app, auth_headers):
    token = mint_run_token()
    run_id = f"run-{short_id()}"
    async with async_session_factory() as db:
        run = Run(
            id=run_id,
            project_id=PROJECT,
            agent="tracer",
            status="running",
            turn_depth=0,
            capability_token_hash=hash_run_token(token),
        )
        db.add(run)
        traces.start_run(db, run, prompt="Look around.", runner="claude", model=None)
        await db.commit()
    async with async_session_factory() as db:
        await record_agent_output(
            db,
            PROJECT,
            "tracer",
            content="Bash",
            session_id=None,
            kind="tool_use",
            payload={"call_id": CALL, "tool": "Bash", "input": {"command": "ls"}},
            run_id=run_id,
        )

    report = await app.post(
        "/api/v1/agent-actions/permission-decisions",
        json={"tool_name": "Bash", "tool_use_id": CALL, "allowed": True, "reason": "a listing"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert report.status_code == 202, report.text
    await _flush()

    by_run = await app.get(f"{BASE}/traces/by-run/{run_id}", headers=auth_headers)
    assert by_run.status_code == 200, by_run.text
    spans = by_run.json()["spans"]
    [tool] = [span for span in spans if span["operation"] == "execute_tool"]
    [request] = [span for span in spans if span["operation"] == "aw.request"]
    assert request["parent_span_id"] == tool["span_id"]
    assert request["attributes"]["http.route"].endswith("/permission-decisions")
    assert request["attributes"]["http.response.status_code"] == 202
    assert request["attributes"]["aw.actor"] == "run"
    assert request["attributes"]["aw.run.id"] == run_id
    roots = await _roots(app, auth_headers, "aw.request")
    assert _requests(roots, "POST", "/permission-decisions") == [], "never a trace of its own"


@pytest.mark.asyncio
async def test_a_span_that_cannot_be_written_never_fails_the_request(app, auth_headers):
    def _refuse(*_args, **_kwargs):
        raise RuntimeError("the span store is unavailable")

    with patch.object(traces, "_write_spans", _refuse, create=True):
        created = await app.post(
            f"{BASE}/tasks", json={"title": "Still created"}, headers=auth_headers
        )
        await _flush()
    assert created.status_code == 201, created.text
    settings = await app.get(f"{BASE}/traces/settings", headers=auth_headers)
    assert settings.status_code == 200, settings.text
    assert settings.json().get("dropped_spans", 0) >= 1


# --- 2. events -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_event_with_no_trace_current_is_a_trace_of_its_own(app, auth_headers):
    async with async_session_factory() as db:
        await persist_event(db, PROJECT, "hub_wide_probe", {"note": f"key {SECRET}"})
    await _flush()

    events = await _roots(app, auth_headers, "aw.event")
    [probe] = [
        r for r in events if r["root"]["attributes"].get("aw.event.type") == "hub_wide_probe"
    ]
    assert probe["root"]["ended"] is True
    assert SECRET not in json.dumps(probe)


@pytest.mark.asyncio
async def test_an_event_a_run_emits_is_on_the_runs_root(app, auth_headers):
    """D5: the executor runs inside its run's trace (`traces.within_run`), so an event it emits is
    a span event on the run's root, not a trace of its own."""
    run_id = f"run-{short_id()}"
    async with async_session_factory() as db:
        run = Run(id=run_id, project_id=PROJECT, agent="tracer", status="running", turn_depth=0)
        db.add(run)
        traces.start_run(db, run, prompt="Work.", runner="claude", model=None)
        await db.commit()

    async def _executor() -> None:
        async with async_session_factory() as db:
            await persist_event(db, PROJECT, "run_probe", {"note": f"key {SECRET}"}, agent="tracer")

    await traces.within_run(PROJECT, run_id, _executor())
    await _flush()

    by_run = await app.get(f"{BASE}/traces/by-run/{run_id}", headers=auth_headers)
    spans = by_run.json()["spans"]
    [root] = [span for span in spans if span["parent_span_id"] is None]
    [probe] = [event for event in root["events"] if event["name"] == "run_probe"]
    assert probe["attributes"]["aw.agent"] == "tracer"
    assert SECRET not in json.dumps(probe)
    assert [
        r
        for r in await _roots(app, auth_headers, "aw.event")
        if r["root"]["attributes"].get("aw.event.type") == "run_probe"
    ] == []


@pytest.mark.asyncio
async def test_an_event_after_its_request_was_recorded_is_a_trace_of_its_own(app, auth_headers):
    """Work a request spawned inherits its span; once the request's span is handed to the writer,
    an event appended to it would be lost, so the event gets a span of its own instead."""
    span = traces.PendingSpan(
        project_id=PROJECT,
        name="POST /x",
        operation="aw.request",
        start_time=datetime.now(timezone.utc),
    )
    token = traces.set_current(span)
    try:
        traces.enqueue(span)
        async with async_session_factory() as db:
            await persist_event(db, PROJECT, "late_probe", {})
    finally:
        traces.reset_current(token)
    await _flush()

    events = await _roots(app, auth_headers, "aw.event")
    assert [r for r in events if r["root"]["attributes"].get("aw.event.type") == "late_probe"]


@pytest.mark.asyncio
async def test_a_read_that_emits_an_event_is_recorded(app, auth_headers):
    """A routine read is not recorded, but one that emitted an event did something: the request
    is kept so the event is in a trace (`every-event-is-in-a-trace`)."""
    from hub import trace_requests
    from hub.auth import PROJECT_SCOPE_KEY

    span = traces.PendingSpan(
        project_id="", name="", operation="aw.request", start_time=datetime.now(timezone.utc)
    )
    token = traces.set_current(span)
    try:
        async with async_session_factory() as db:
            await persist_event(db, PROJECT, "read_probe", {})
    finally:
        traces.reset_current(token)
    scope = {"method": "GET", "path": f"{BASE}/tasks", PROJECT_SCOPE_KEY: PROJECT}
    trace_requests._finish(scope, span, status=200, stream=False, elapsed=0.01)
    await _flush()

    roots = await _roots(app, auth_headers, "aw.request")
    [read] = [r["root"] for r in roots if "read_probe" in [e["name"] for e in r["root"]["events"]]]
    assert read["attributes"]["http.request.method"] == "GET"


# --- 3. background work and 4. logs --------------------------------------------------------------


def _commands(spans) -> List[Dict[str, Any]]:
    return [span for span in spans if span["operation"] == "aw.command"]


@pytest.mark.asyncio
async def test_a_check_run_is_a_trace_of_its_commands(app, auth_headers, tmp_path):
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS, FAIL])

    assert await project_checks.request_run(PROJECT, task_id)
    await project_checks.drain()
    await _flush()

    work = await _roots(app, auth_headers, "aw.work")
    [check] = [r for r in work if r["root"]["attributes"].get("aw.work.kind") == "check_run"]
    assert check["root"]["attributes"]["aw.task.id"] == task_id
    commands = _commands(check["spans"])
    assert any("git" in json.dumps(c["attributes"].get("process.command_args")) for c in commands)
    failing = [c for c in commands if c["attributes"].get("process.exit.code") == 3]
    assert failing and all(c["status"] == "error" for c in failing)
    assert any(c["attributes"].get("process.exit.code") == 0 for c in commands)


def _git_version() -> None:
    traces.run(["git", "--version"], capture_output=True, text=True, check=False)


@pytest.mark.asyncio
async def test_work_inside_work_is_its_child_and_an_idle_pass_is_not_recorded(app, auth_headers):
    """A batch's distils are in the batch's trace, a command in the work that ran it (in a thread:
    `asyncio.to_thread` carries the current span); quiet work that did nothing is not a trace."""
    async with traces.work("distil_batch", PROJECT):
        async with traces.work("distil", PROJECT, **{"aw.vault.source.id": "src-1"}):
            await asyncio.to_thread(_git_version)
    async with traces.work("inbound_queue", PROJECT, quiet=True):
        pass
    await _flush()

    work = await _roots(app, auth_headers, "aw.work")
    kinds = [r["root"]["attributes"]["aw.work.kind"] for r in work]
    assert "inbound_queue" not in kinds and "distil" not in kinds, kinds
    [batch] = [r for r in work if r["root"]["attributes"]["aw.work.kind"] == "distil_batch"]
    [distil] = [s for s in batch["spans"] if s["name"] == "distil"]
    assert distil["parent_span_id"] == batch["root"]["span_id"]
    [git] = _commands(batch["spans"])
    assert git["parent_span_id"] == distil["span_id"]
    assert git["name"] == "git --version"
    assert git["attributes"]["process.exit.code"] == 0 and git["status"] == "ok"


@pytest.mark.asyncio
async def test_a_command_goes_with_its_request_kept_or_not(app, auth_headers):
    """The app's routine read that runs git (a diff, a status) is not recorded, and neither is its
    command; a request that is recorded holds its commands as children."""
    from hub import trace_requests
    from hub.auth import PROJECT_SCOPE_KEY

    for method in ("GET", "POST"):
        span = traces.PendingSpan(
            project_id="", name="", operation="aw.request", start_time=datetime.now(timezone.utc)
        )
        token = traces.set_current(span)
        try:
            await asyncio.to_thread(_git_version)
        finally:
            traces.reset_current(token)
        scope = {"method": method, "path": f"{BASE}/tasks", PROJECT_SCOPE_KEY: PROJECT}
        trace_requests._finish(scope, span, status=200, stream=False, elapsed=0.01)
    await _flush()

    roots = await _roots(app, auth_headers, "aw.request")
    assert _requests(roots, "GET", "/tasks") == []
    [post] = [r for r in roots if r["root"]["attributes"]["http.request.method"] == "POST"]
    [git] = _commands(post["spans"])
    assert git["parent_span_id"] == post["root"]["span_id"]
    assert git["trace_id"] == post["trace_id"]


@pytest.mark.asyncio
async def test_a_command_a_runs_executor_makes_is_in_the_runs_trace(app, auth_headers):
    run_id = f"run-{short_id()}"
    async with async_session_factory() as db:
        run = Run(id=run_id, project_id=PROJECT, agent="tracer", status="running", turn_depth=0)
        db.add(run)
        traces.start_run(db, run, prompt="Look around.", runner="claude", model=None)
        await db.commit()

    async def _executor() -> None:
        await asyncio.to_thread(_git_version)

    await traces.within_run(PROJECT, run_id, _executor())
    await _flush()

    by_run = await app.get(f"{BASE}/traces/by-run/{run_id}", headers=auth_headers)
    assert by_run.status_code == 200, by_run.text
    spans = by_run.json()["spans"]
    [root] = [span for span in spans if span["parent_span_id"] is None]
    [git] = _commands(spans)
    assert git["parent_span_id"] == root["span_id"] and git["trace_id"] == root["trace_id"]


@pytest.mark.asyncio
async def test_a_loops_firing_is_a_loop_tick_trace(app, auth_headers):
    from hub.db.models import AIJob
    from hub.scheduler import JobScheduler

    from .test_scheduler import _make_job, _make_loop

    async with async_session_factory() as db:
        job = await _make_job(db, suffix="traced-tick", agent="loop-agent-traced")
        await _make_loop(
            db,
            job_id=job.id,
            purpose="traced loop",
            stop_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
    async with async_session_factory() as db:
        fresh = await db.get(AIJob, job.id)
        await JobScheduler()._fire_job_internal(fresh, trigger="scheduled", session=db)
    await _flush()

    work = await _roots(app, auth_headers, "aw.work")
    [tick] = [r["root"] for r in work if r["root"]["attributes"].get("aw.job.id") == job.id]
    assert tick["attributes"]["aw.work.kind"] == "loop_tick" and tick["name"] == "loop_tick"
    assert tick["attributes"]["aw.loop.id"] == f"loop-{job.id}"
    assert tick["attributes"]["aw.job.trigger"] == "scheduled"


@pytest.mark.asyncio
async def test_a_warning_the_hub_logs_is_on_its_trace_and_exported_as_a_log(
    app, auth_headers, tmp_path
):
    task_id, _ = await _task_with_work(tmp_path)
    await _project([PASS])

    def _broken_merge(*_args, **_kwargs):
        raise RuntimeError(f"merge-tree refused the token {SECRET}")

    with patch.object(project_checks, "build_merged_commit", _broken_merge):
        assert await project_checks.request_run(PROJECT, task_id)
        await project_checks.drain()
    await _flush()

    work = await _roots(app, auth_headers, "aw.work")
    [check] = [r for r in work if r["root"]["attributes"].get("aw.work.kind") == "check_run"]
    logs = [event for span in check["spans"] for event in span["events"] if event["name"] == "log"]
    assert logs, "the runner's warning is on the check's trace"
    assert any(
        log["attributes"].get("log.severity") == "WARNING"
        and "failed to complete" in log["attributes"].get("log.body", "")
        for log in logs
    )
    assert SECRET not in json.dumps(check)

    today = datetime.now(timezone.utc).date()
    window = {"since": today.isoformat(), "until": (today + timedelta(days=1)).isoformat()}
    exported = await app.get(f"{BASE}/traces/export", params=window, headers=auth_headers)
    assert exported.status_code == 200, exported.text
    records = [
        record
        for resource in exported.json().get("resourceLogs", [])
        for scope in resource["scopeLogs"]
        for record in scope["logRecords"]
    ]
    assert any(record["traceId"] == check["trace_id"] for record in records)
    assert SECRET not in exported.text


@pytest.mark.asyncio
async def test_a_warning_a_runs_executor_logs_is_on_the_runs_root(app, auth_headers):
    run_id = f"run-{short_id()}"
    async with async_session_factory() as db:
        run = Run(id=run_id, project_id=PROJECT, agent="tracer", status="running", turn_depth=0)
        db.add(run)
        traces.start_run(db, run, prompt="Work.", runner="claude", model=None)
        await db.commit()

    async def _executor() -> None:
        logging.getLogger("hub.agent_trigger").warning("the runner said %s", SECRET)

    await traces.within_run(PROJECT, run_id, _executor())
    await _flush()

    by_run = await app.get(f"{BASE}/traces/by-run/{run_id}", headers=auth_headers)
    root = next(span for span in by_run.json()["spans"] if span["parent_span_id"] is None)
    [log] = [event for event in root["events"] if event["name"] == "log"]
    assert log["attributes"]["log.logger"] == "hub.agent_trigger"
    assert log["attributes"]["log.body"].startswith("the runner said ")
    assert SECRET not in by_run.text


@pytest.mark.asyncio
async def test_a_warning_on_work_is_pushed_to_the_logs_endpoint(app, auth_headers):
    receiver = _Receiver()
    try:
        settings = await app.put(
            f"{BASE}/traces/settings",
            json={"otlp_endpoint": receiver.url, "export_enabled": True},
            headers=auth_headers,
        )
        assert settings.status_code == 200, settings.text
        with traces.work("spec_fold", PROJECT) as span:
            logging.getLogger("hub.spec_fold").error("folding failed for %s", SECRET)
        await _flush()
        assert await trace_export.push_once() == 2  # the settings PUT's request span, the fold
        paths = [post["path"] for post in receiver.posts]
        assert paths == ["/v1/traces", "/v1/logs"], "the batch's log records go with its spans"
        [record] = [
            record
            for resource in receiver.posts[1]["body"]["resourceLogs"]
            for scope in resource["scopeLogs"]
            for record in scope["logRecords"]
        ]
        assert record["traceId"] == span.trace_id and record["spanId"] == span.span_id
        assert record["severityText"] == "ERROR" and record["severityNumber"] == 17
        assert record["body"]["stringValue"].startswith("folding failed for ")
        assert SECRET not in json.dumps(receiver.posts)
    finally:
        receiver.close()


@pytest.mark.asyncio
async def test_a_warning_with_no_trace_is_not_stored_and_still_reaches_stderr(
    app, auth_headers, monkeypatch, capsys
):
    """Before the root logger is configured the Hub's warnings reach stderr through
    `logging.lastResort` (the database line at startup); the trace handler must not swallow them."""
    monkeypatch.setattr(logging.getLogger(), "handlers", [])
    logging.getLogger("hub.main").warning("Hub database: opening nowhere")
    assert "Hub database: opening nowhere" in capsys.readouterr().err
    await _flush()
    settings = await app.get(f"{BASE}/traces/settings", headers=auth_headers)
    assert settings.json()["span_count"] == 0


@pytest.mark.asyncio
async def test_a_batch_the_locked_database_refused_is_written_on_the_next_pass(app, auth_headers):
    """Found by the slice-1 drive: a trigger held the write lock past the 30 s busy timeout and
    the writer dropped the span it was writing. A lock is waited out, not a reason to drop."""
    from sqlalchemy.exc import OperationalError

    real = traces._write_spans
    calls = []

    async def _locked_once(batch):
        calls.append(len(batch))
        if len(calls) == 1:
            raise OperationalError("INSERT", {}, Exception("database is locked"))
        await real(batch)

    with patch.object(traces, "_write_spans", _locked_once):
        created = await app.post(f"{BASE}/tasks", json={"title": "Waits"}, headers=auth_headers)
        assert created.status_code == 201, created.text
        assert await traces.flush_spans() == 0
        assert await traces.flush_spans() == 1
    roots = await _roots(app, auth_headers, "aw.request")
    assert len(_requests(roots, "POST", "/tasks")) == 1
    settings = await app.get(f"{BASE}/traces/settings", headers=auth_headers)
    assert settings.json()["dropped_spans"] == 0


@pytest.mark.asyncio
async def test_a_request_nests_under_a_tool_call_whose_line_arrived_after_it_began(
    app, auth_headers
):
    """Found by the slice-1 drive on a real Claude turn: `mcp__agentweave__list_tasks`'s line was
    recorded 50 ms after its `GET /agent-actions/tasks` began, and the request fell to the root."""
    run_id = f"run-{short_id()}"
    async with async_session_factory() as db:
        run = Run(id=run_id, project_id=PROJECT, agent="tracer", status="running", turn_depth=0)
        db.add(run)
        traces.start_run(db, run, prompt="List the tasks.", runner="claude", model=None)
        await db.commit()
    began = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        await record_agent_output(
            db,
            PROJECT,
            "tracer",
            content="mcp__agentweave__list_tasks",
            session_id=None,
            kind="tool_use",
            payload={"call_id": CALL, "tool": "mcp__agentweave__list_tasks", "input": {}},
            run_id=run_id,
        )
    traces.enqueue(
        traces.PendingSpan(
            project_id=PROJECT,
            name="GET /api/v1/agent-actions/tasks",
            operation="aw.request",
            start_time=began - timedelta(milliseconds=50),
            end_time=datetime.now(timezone.utc) + timedelta(milliseconds=100),
            run_id=run_id,
        )
    )
    await _flush()

    by_run = await app.get(f"{BASE}/traces/by-run/{run_id}", headers=auth_headers)
    spans = by_run.json()["spans"]
    [tool] = [span for span in spans if span["operation"] == "execute_tool"]
    [request] = [span for span in spans if span["operation"] == "aw.request"]
    assert request["parent_span_id"] == tool["span_id"]


@pytest.mark.asyncio
async def test_a_backend_that_takes_no_logs_still_gets_every_span_once(app, auth_headers):
    """Review 0203: an endpoint that implements traces only (Jaeger, Tempo) answers 404 on
    `/v1/logs`. The log records are best-effort beside the spans, so one warning must not hold the
    accepted spans back: they are marked exported, later spans still go, nothing is sent twice."""
    receiver = _Receiver(answers={"/v1/logs": 404})
    try:
        settings = await app.put(
            f"{BASE}/traces/settings",
            json={"otlp_endpoint": receiver.url, "export_enabled": True},
            headers=auth_headers,
        )
        assert settings.status_code == 200, settings.text
        with traces.work("spec_fold", PROJECT):
            logging.getLogger("hub.spec_fold").warning("one warning")
        await _flush()
        assert await trace_export.push_once() == 2  # the settings PUT's request span, the fold
        with traces.work("spec_fold", PROJECT):
            logging.getLogger("hub.spec_fold").warning("another warning")
        await _flush()
        trace_export._retry_after.clear()
        assert await trace_export.push_once() == 1

        sent = [
            span["spanId"]
            for post in receiver.posts
            if post["path"] == "/v1/traces"
            for resource in post["body"]["resourceSpans"]
            for scope in resource["scopeSpans"]
            for span in scope["spans"]
        ]
        assert len(sent) == 3 and len(set(sent)) == 3, "every span once, none re-sent"
        read = (await app.get(f"{BASE}/traces/settings", headers=auth_headers)).json()
        assert read["exported_spans"] == 3
        assert "404" in read["last_error"], "the operator still sees the refused log records"
    finally:
        receiver.close()


@pytest.mark.asyncio
async def test_an_event_its_transaction_rolled_back_is_not_on_the_request(app, auth_headers):
    """Review 0203: `persist_event(commit=False)` inside a savepoint that rolls back (a flow that
    would be empty, `spec.py`'s `_FlowWouldBeEmptyError`) leaves no `event_logs` row, so its
    request's trace must not show it either; the one that commits is shown."""
    span = traces.PendingSpan(
        project_id="", name="POST /x", operation="aw.request", start_time=datetime.now(timezone.utc)
    )
    token = traces.set_current(span)
    try:
        async with async_session_factory() as db:
            try:
                async with db.begin_nested():
                    await persist_event(db, PROJECT, "loop_created", {"id": "loop-x"}, commit=False)
                    raise RuntimeError("the flow would be empty")
            except RuntimeError:
                pass
            await persist_event(db, PROJECT, "loop_kept", {"id": "loop-y"}, commit=False)
            assert [event["name"] for event in span.events] == [], "nothing before the commit"
            await db.commit()
        async with async_session_factory() as db:
            await persist_event(db, PROJECT, "never_committed", {}, commit=False)
    finally:
        traces.reset_current(token)
    assert [event["name"] for event in span.events] == ["loop_kept"]
    assert span.keep


@pytest.mark.asyncio
async def test_the_writer_and_a_runs_session_both_keep_their_event_on_the_root(app, auth_headers):
    """Review 0203: the writer's attach (a warning) and a run's own session (an event) each append
    to the run root's `events`; neither may write back a copy it read before the other committed."""
    run_id = f"run-{short_id()}"
    async with async_session_factory() as db:
        run = Run(id=run_id, project_id=PROJECT, agent="tracer", status="running", turn_depth=0)
        db.add(run)
        traces.start_run(db, run, prompt="Work.", runner="claude", model=None)
        await db.commit()

    token = traces.set_current(traces.RunTrace(project_id=PROJECT, run_id=run_id))
    try:
        session = async_session_factory()
        await persist_event(session, PROJECT, "some_event", {"x": 1}, agent="tracer", commit=False)
        logging.getLogger("hub.agent_trigger").warning("runner hiccup")
        flush = asyncio.create_task(traces.flush_spans())
        await asyncio.sleep(0.5)  # the writer is waiting on the run session's write lock
        await session.commit()
        await session.close()
        await flush
    finally:
        traces.reset_current(token)
    await _flush()
    by_run = await app.get(f"{BASE}/traces/by-run/{run_id}", headers=auth_headers)
    root = next(span for span in by_run.json()["spans"] if span["parent_span_id"] is None)
    names = [event["name"] for event in root["events"]]
    assert "some_event" in names and "log" in names, names
