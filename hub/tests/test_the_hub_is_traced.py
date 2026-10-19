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

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from hub import project_checks, traces
from hub.agent_auth import hash_run_token, mint_run_token
from hub.db.engine import async_session_factory
from hub.db.models import Run
from hub.output_recording import record_agent_output
from hub.utils import persist_event, short_id

from .test_project_checks_run import FAIL, PASS, _project, _task_with_work

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


@pytest.mark.xfail(strict=True, reason="trace-hub-wide slices 1 and 2 not built")
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


@pytest.mark.xfail(strict=True, reason="trace-hub-wide slice 1 not built")
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


@pytest.mark.xfail(strict=True, reason="trace-hub-wide slice 1 not built")
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


@pytest.mark.xfail(strict=True, reason="trace-hub-wide slice 2 not built")
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


# --- 3. background work and 4. logs --------------------------------------------------------------


def _commands(spans) -> List[Dict[str, Any]]:
    return [span for span in spans if span["operation"] == "aw.command"]


@pytest.mark.xfail(strict=True, reason="trace-hub-wide slice 3 not built")
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


@pytest.mark.xfail(strict=True, reason="trace-hub-wide slices 3 and 4 not built")
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
