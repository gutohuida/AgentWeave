"""The Hub's background jobs, configured per project and recorded when they spawn a model.

`the-hubs-background-jobs-are-configured-on-a-manager-page` (Tier 2): the registry, the job rows,
the three manager routes, the settings route's compatibility mapping, and the firing record the
titler writes. The spawn is faked throughout, as in `test_title_generation.py`.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import hub.conversation_titles as conversation_titles
from hub import manager
from hub.db.engine import async_session_factory
from hub.db.models import EventLog, Run

BASE = "/api/v1/projects/proj-test"
JOB = "conversation-titles"


async def _runner(app, auth_headers, name="titles", cli="claude", model=None) -> str:
    payload = {"name": name, "cli": cli}
    if model:
        payload["model"] = model
    created = await app.post(f"{BASE}/runners", json=payload, headers=auth_headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _job(app, auth_headers) -> dict:
    listed = await app.get(f"{BASE}/manager/jobs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    return next(job for job in listed.json()["jobs"] if job["key"] == JOB)


# ---------------------------------------------------------------------------
# jobs-listed, job-configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_project_with_no_rows_lists_the_title_job_disabled(app, auth_headers) -> None:
    """jobs-default: a job never configured is still listed, with nothing chosen."""
    listed = await app.get(f"{BASE}/manager/jobs", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    jobs = listed.json()["jobs"]
    assert [job["key"] for job in jobs] == [spec.key for spec in manager.JOBS]
    first = jobs[0]
    assert first["key"] == JOB
    assert first["enabled"] is False
    assert first["runner_id"] is None
    assert first["model"] is None
    assert first["title"] and first["description"] and first["trigger"]


@pytest.mark.asyncio
async def test_patching_refuses_unknown_jobs_and_foreign_runners(app, auth_headers) -> None:
    """routes: 404, then 400 with the job unchanged, then 200 with the job as listed."""
    runner_id = await _runner(app, auth_headers)

    unknown = await app.patch(
        f"{BASE}/manager/jobs/no-such-job", json={"enabled": True}, headers=auth_headers
    )
    assert unknown.status_code == 404, unknown.text

    foreign = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": "runner-elsewhere"},
        headers=auth_headers,
    )
    assert foreign.status_code == 400, foreign.text
    assert (await _job(app, auth_headers))["enabled"] is False

    valid = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": runner_id, "model": "claude-haiku-4-5-20251001"},
        headers=auth_headers,
    )
    assert valid.status_code == 200, valid.text
    assert valid.json() == await _job(app, auth_headers)
    assert valid.json()["enabled"] is True
    assert valid.json()["runner_id"] == runner_id
    assert valid.json()["model"] == "claude-haiku-4-5-20251001"


@pytest.mark.asyncio
async def test_a_patch_changes_only_the_fields_it_sends(app, auth_headers) -> None:
    runner_id = await _runner(app, auth_headers)
    await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": runner_id, "model": "m"},
        headers=auth_headers,
    )
    off = await app.patch(
        f"{BASE}/manager/jobs/{JOB}", json={"enabled": False}, headers=auth_headers
    )
    assert off.status_code == 200, off.text
    assert (off.json()["enabled"], off.json()["runner_id"], off.json()["model"]) == (
        False,
        runner_id,
        "m",
    )
    cleared = await app.patch(
        f"{BASE}/manager/jobs/{JOB}", json={"runner_id": None, "model": None}, headers=auth_headers
    )
    assert (cleared.json()["runner_id"], cleared.json()["model"]) == (None, None)


# ---------------------------------------------------------------------------
# settings-compatible
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_settings_fields_read_and_write_the_job(app, auth_headers) -> None:
    """compat: a client that knows only the old settings fields still drives the job."""
    runner_id = await _runner(app, auth_headers)
    current = await app.get(f"{BASE}/settings", headers=auth_headers)
    put = await app.put(
        f"{BASE}/settings",
        json={
            **current.json(),
            "conversation_title_mode": "generate",
            "conversation_title_runner_id": runner_id,
        },
        headers=auth_headers,
    )
    assert put.status_code == 200, put.text

    job = await _job(app, auth_headers)
    assert (job["enabled"], job["runner_id"]) == (True, runner_id)

    off = await app.patch(
        f"{BASE}/manager/jobs/{JOB}", json={"enabled": False}, headers=auth_headers
    )
    assert off.status_code == 200, off.text
    reread = await app.get(f"{BASE}/settings", headers=auth_headers)
    assert reread.json()["conversation_title_mode"] == "truncate"
    assert reread.json()["conversation_title_runner_id"] == runner_id


@pytest.mark.asyncio
async def test_a_settings_save_that_omits_the_title_fields_leaves_the_job_alone(
    app, auth_headers
) -> None:
    """The new Settings panel no longer sends them; a save there must not switch titles off."""
    runner_id = await _runner(app, auth_headers)
    await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": runner_id, "model": "m"},
        headers=auth_headers,
    )
    saved = await app.put(f"{BASE}/settings", json={"hop_budget": 7}, headers=auth_headers)
    assert saved.status_code == 200, saved.text
    job = await _job(app, auth_headers)
    assert (job["enabled"], job["runner_id"], job["model"]) == (True, runner_id, "m")


# ---------------------------------------------------------------------------
# activity-listed
# ---------------------------------------------------------------------------


async def _record(job: str, at: datetime, subject: str) -> None:
    async with async_session_factory() as session:
        session.add(
            EventLog(
                id=f"evt-{subject}",
                project_id="proj-test",
                event_type=manager.FIRED_EVENT,
                data={"job": job, "subject": {"conversation_id": subject}, "outcome": "written"},
                timestamp=at,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_activity_is_newest_first_bounded_and_filterable(app, auth_headers) -> None:
    """activity-order."""
    start = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
    await _record(JOB, start, "one")
    await _record("another-job", start + timedelta(minutes=1), "two")
    await _record(JOB, start + timedelta(minutes=2), "three")

    every = await app.get(f"{BASE}/manager/activity", headers=auth_headers)
    assert every.status_code == 200, every.text
    assert [f["subject"]["conversation_id"] for f in every.json()["firings"]] == [
        "three",
        "two",
        "one",
    ]
    assert all(f["at"] for f in every.json()["firings"])

    two = await app.get(f"{BASE}/manager/activity?limit=2", headers=auth_headers)
    assert [f["subject"]["conversation_id"] for f in two.json()["firings"]] == ["three", "two"]

    one_job = await app.get(f"{BASE}/manager/activity?job={JOB}", headers=auth_headers)
    assert [f["subject"]["conversation_id"] for f in one_job.json()["firings"]] == [
        "three",
        "one",
    ]

    too_many = await app.get(f"{BASE}/manager/activity?limit=500", headers=auth_headers)
    assert too_many.status_code == 422


# ---------------------------------------------------------------------------
# title-is-a-job, firing-recorded, not-an-agent
# ---------------------------------------------------------------------------


async def _sync_agent(app, auth_headers) -> None:
    sync = await app.post(
        f"{BASE}/session/sync",
        json={"data": {"agents": {"offline": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _conversation(app, auth_headers, message="Investigate the flaky checkout test") -> str:
    created = await app.post(
        f"{BASE}/agent/trigger",
        json={"agent": "offline", "message": message},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    return created.json()["conversation_id"]


async def _firings() -> list:
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(EventLog)
                .where(EventLog.event_type == manager.FIRED_EVENT)
                .order_by(EventLog.timestamp)
            )
        ).scalars()
        return [(row.agent, row.data) for row in rows]


def _fake_spawn(monkeypatch, outputs: dict, calls: list) -> None:
    """Output keyed by a word of the conversation's opening message."""

    def _run(cmd, cwd, env=None):
        calls.append(cmd)
        prompt = cmd[-1]
        return next(out for word, out in outputs.items() if word in prompt)

    monkeypatch.setattr(conversation_titles, "_run_titler", _run)


@pytest.mark.asyncio
async def test_each_spawn_records_one_firing_and_no_run(
    app, auth_headers, bind_runner, monkeypatch
) -> None:
    """firing-shape and no-run-row: written, empty, and nothing for an excerpt already titled."""
    await _sync_agent(app, auth_headers)
    written = await _conversation(app, auth_headers, "Investigate the flaky checkout test")
    empty = await _conversation(app, auth_headers, "Silent request")
    await bind_runner("offline", cli="claude", model="claude-opus-5")
    titles_runner = await _runner(app, auth_headers, model="claude-sonnet-5")
    await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": titles_runner, "model": "claude-haiku-4-5-20251001"},
        headers=auth_headers,
    )
    calls: list = []
    _fake_spawn(monkeypatch, {"checkout": "Checkout flake investigation", "Silent": ""}, calls)

    async with async_session_factory() as session:
        runs_before = len((await session.execute(select(Run.id))).scalars().all())

    for conversation_id in (written, empty, written):
        await conversation_titles.generate_conversation_title(
            project_id="proj-test", conversation_id=conversation_id
        )

    async with async_session_factory() as session:
        runs_after = len((await session.execute(select(Run.id))).scalars().all())
    assert runs_after == runs_before, "a manager firing is not a run"

    # The job's model, not the runner's.
    assert len(calls) == 2
    assert calls[0][calls[0].index("--model") + 1] == "claude-haiku-4-5-20251001"

    firings = await _firings()
    assert [data["outcome"] for _, data in firings] == ["written", "empty"]
    for agent, data in firings:
        assert agent is None
        assert "agent" not in data
        assert {
            "job",
            "trigger",
            "subject",
            "runner_id",
            "cli",
            "model",
            "outcome",
            "detail",
            "duration_ms",
            "usage",
        } <= data.keys()
        assert data["job"] == JOB
        assert data["runner_id"] == titles_runner
        assert data["cli"] == "claude"
        assert data["model"] == "claude-haiku-4-5-20251001"
        assert isinstance(data["duration_ms"], int)
        assert data["usage"] is None
    assert firings[0][1]["subject"] == {"conversation_id": written}
    assert firings[0][1]["detail"] == "Checkout flake investigation"
    assert firings[1][1]["subject"] == {"conversation_id": empty}
    assert firings[1][1]["detail"] is None

    listed = await app.get(f"{BASE}/manager/activity", headers=auth_headers)
    assert [f["outcome"] for f in listed.json()["firings"]] == ["empty", "written"]


@pytest.mark.asyncio
async def test_a_failed_spawn_is_recorded_as_failed(
    app, auth_headers, bind_runner, monkeypatch
) -> None:
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers)
    await bind_runner("offline", cli="claude")
    await app.patch(f"{BASE}/manager/jobs/{JOB}", json={"enabled": True}, headers=auth_headers)
    monkeypatch.setattr(conversation_titles, "_run_titler", lambda cmd, cwd, env=None: None)

    await conversation_titles.generate_conversation_title(
        project_id="proj-test", conversation_id=conversation_id
    )

    firings = await _firings()
    assert [data["outcome"] for _, data in firings] == ["failed"]


@pytest.mark.asyncio
async def test_with_no_job_runner_the_agents_runner_and_model_title(
    app, auth_headers, bind_runner, monkeypatch
) -> None:
    """title-is-a-job's fallbacks: the agent's bound runner, and that runner's model."""
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers)
    await bind_runner("offline", cli="claude", model="claude-opus-5")
    await app.patch(f"{BASE}/manager/jobs/{JOB}", json={"enabled": True}, headers=auth_headers)
    calls: list = []
    _fake_spawn(monkeypatch, {"checkout": "Checkout flake"}, calls)

    await conversation_titles.generate_conversation_title(
        project_id="proj-test", conversation_id=conversation_id
    )

    assert calls[0][calls[0].index("--model") + 1] == "claude-opus-5"
    ((_, data),) = await _firings()
    assert data["model"] == "claude-opus-5"
    assert data["outcome"] == "written"
