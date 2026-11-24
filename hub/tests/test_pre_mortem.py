"""The manager's pre-mortem: its button, its automatic firing, what it lists and what reaches the author.

`the-spec-journey-spends-the-operator-s-attention-only-on-their-decisions`, FR-11 (D7). As in
`test_build_retrospective.py` the worker is faked: a test hands `pre_mortem.run_worker` what the
model would answer, so what is checked is what the Hub does with it. The real spawn is the
acceptance drive's (`scripts/drive/spec_journey_attention_drive.py`, phases 1 and 2).
"""

import pytest
from sqlalchemy import select

from hub import manager, pre_mortem
from hub.db.engine import async_session_factory
from hub.db.models import SpecDocument
from hub.worker import WorkerResult, WorkerUsage

from .test_spec_documents_api import BASE as DOCS
from .test_spec_documents_api import (
    _create,
    _document,
    _submit,
    run_headers,  # noqa: F401  (fixture)
)

P = "proj-test"
BASE = f"/api/v1/projects/{P}"
JOB = "pre-mortem"
PATH = "spec/changes/demo/spec.json"
HAIKU = "claude-haiku-4-5-20251001"
PREVIEW = f"{BASE}/agents/agent-context"

STORY = "The 200ms budget was measured on an idle machine; under load the route took 900ms."


class _Worker:
    """Stands in for `run_worker`: every call answers *answer*, or fails with a spawn failure."""

    def __init__(self, answer=None, *, fail=False) -> None:
        self.answer = answer
        self.fail = fail
        self.calls = []

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            return WorkerResult("spawn_failed", error="the CLI is not installed")
        answer = self.answer or pre_mortem.PreMortemAnswer(
            findings=[pre_mortem.Finding(story=STORY, requirement="FR-1", cites=["app.py:12"])]
        )
        return WorkerResult(
            "ok",
            parsed=answer,
            usage=WorkerUsage(input_tokens=11, output_tokens=7, cost_usd_micros=900),
            duration_ms=5,
        )


@pytest.fixture
def worker(monkeypatch):
    def install(answer=None, **kwargs):
        fake = _Worker(answer, **kwargs)
        monkeypatch.setattr(pre_mortem, "run_worker", fake)
        return fake

    return install


async def _configure(app, auth_headers, mode="button", **fields):
    created = await app.post(
        f"{BASE}/runners",
        json={"name": "pre-mortem", "cli": "claude", "model": HAIKU},
        headers=auth_headers,
    )
    assert created.status_code == 201, created.text
    patched = await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "runner_id": created.json()["id"], "mode": mode, **fields},
        headers=auth_headers,
    )
    assert patched.status_code == 200, patched.text
    return patched.json()


async def _drafted(app, auth_headers, run_headers, path=PATH):  # noqa: F811
    """A change document holding a requirement and its criterion."""
    await _create(app, auth_headers, path=path)
    submitted = await _submit(app, run_headers, _document(), path=path)
    assert submitted.status_code in (200, 201), submitted.text


async def _move(app, auth_headers, path=PATH, **change):
    moved = await app.post(
        f"{DOCS}/documents/journey", params={"path": path}, json=change, headers=auth_headers
    )
    assert moved.status_code == 200, moved.text
    return moved.json()


async def _document_id(path=PATH):
    async with async_session_factory() as session:
        return (
            await session.execute(select(SpecDocument.id).where(SpecDocument.path == path))
        ).scalar_one()


async def _listed(app, auth_headers, path=PATH):
    await pre_mortem.settled()
    listed = await app.get(
        f"{BASE}/manager/jobs/{JOB}/pre-mortems", params={"path": path}, headers=auth_headers
    )
    assert listed.status_code == 200, listed.text
    return listed.json()["pre_mortems"]


async def _firings():
    await pre_mortem.settled()
    async with async_session_factory() as session:
        return await manager.list_firings(session, P, job=JOB)


async def _briefing(app, auth_headers, path=PATH):
    response = await app.get(
        PREVIEW, params={"agent": "claude-1", "spec_document": path}, headers=auth_headers
    )
    assert response.status_code == 200, response.text
    return response.json()["context"]


# pre-mortem-button
@pytest.mark.asyncio
async def test_the_button_fires_once_and_the_route_lists_it(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    fake = worker()
    await _configure(app, auth_headers)
    await _drafted(app, auth_headers, run_headers)

    pressed = await app.post(
        f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers
    )

    assert pressed.status_code == 202, pressed.text
    (firing,) = await _firings()
    document_id = await _document_id()
    assert firing["job"] == JOB and firing["outcome"] == "written"
    assert firing["subject"] == {"document": document_id, "path": PATH}
    assert firing["trigger"] == pre_mortem.REQUESTED
    assert firing["findings"] == [{"story": STORY, "requirement": "FR-1", "cites": ["app.py:12"]}]
    (listed,) = await _listed(app, auth_headers)
    assert listed["id"] == firing["id"] and listed["outcome"] == "written"
    assert listed["trigger"] == "requested" and listed["model"] == HAIKU
    assert listed["cost_usd_micros"] == 900
    # The read adds each finding's answer, null until the author answers it.
    assert listed["findings"] == [{**f, "answer": None} for f in firing["findings"]]
    # The reader is given the drafted requirement under its identifier, with its criterion.
    (call,) = fake.calls
    assert call["initiator"] == "operator" and call["kind"] == JOB
    assert '"identifier": "FR-1"' in call["prompt"] and '"key": "c1"' in call["prompt"]


@pytest.mark.asyncio
async def test_the_button_is_refused_while_the_job_is_off_and_nothing_fires(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    fake = worker()
    await _drafted(app, auth_headers, run_headers)

    pressed = await app.post(
        f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers
    )

    assert pressed.status_code == 409
    assert "Pre-mortem job is off" in pressed.json()["detail"]
    assert await _firings() == [] and fake.calls == []


@pytest.mark.asyncio
async def test_the_button_answers_404_for_an_unknown_document_and_409_with_no_runner(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    worker()
    await _drafted(app, auth_headers, run_headers)
    unknown = await app.post(
        f"{BASE}/manager/jobs/{JOB}/run",
        json={"path": "spec/changes/nope/spec.json"},
        headers=auth_headers,
    )
    await app.patch(f"{BASE}/manager/jobs/{JOB}", json={"enabled": True}, headers=auth_headers)
    no_runner = await app.post(
        f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers
    )
    listed_unknown = await app.get(
        f"{BASE}/manager/jobs/{JOB}/pre-mortems",
        params={"path": "spec/changes/nope/spec.json"},
        headers=auth_headers,
    )

    assert unknown.status_code == 404
    assert no_runner.status_code == 409 and "no runner" in no_runner.json()["detail"]
    assert listed_unknown.status_code == 404
    assert await _firings() == []


@pytest.mark.asyncio
async def test_a_button_whose_reader_finds_nothing_or_fails_is_listed_unwritten(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    worker(pre_mortem.PreMortemAnswer(findings=[]))
    await _configure(app, auth_headers)
    await _drafted(app, auth_headers, run_headers)
    await app.post(f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers)
    await pre_mortem.settled()
    worker(fail=True)
    await app.post(f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers)

    failed, empty = await _listed(app, auth_headers)

    assert (failed["outcome"], empty["outcome"]) == ("failed", "empty")
    assert failed["findings"] == empty["findings"] == []
    assert "### Pre-mortem findings" not in await _briefing(app, auth_headers)


# pre-mortem-automatic
@pytest.mark.asyncio
async def test_automatic_fires_on_leaving_the_criteria_steps_and_not_for_a_fix(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    fake = worker()
    await _configure(app, auth_headers, mode="automatic")
    large, small, fix = (f"spec/changes/{name}/spec.json" for name in ("large", "small", "fix"))
    for path, size, step in (
        (large, "large", "acceptance"),
        (small, "small", "requirements-and-acceptance"),
        (fix, "fix", "intake"),
    ):
        await _drafted(app, auth_headers, run_headers, path=path)
        await _move(app, auth_headers, path=path, size=size, step=step)
    assert await _firings() == [], "reaching a criteria step fires nothing"

    await _move(app, auth_headers, path=large, step="approach")
    await _move(app, auth_headers, path=small, step="tasks")
    await _move(app, auth_headers, path=fix, step="tasks")

    firings = await _firings()
    fired_for = sorted(f["subject"]["path"] for f in firings)
    assert fired_for == sorted([large, small])
    assert all(f["trigger"] == pre_mortem.CRITERIA_WRITTEN for f in firings)
    assert all(f["outcome"] == "written" for f in firings)
    assert len(fake.calls) == 2 and {c["initiator"] for c in fake.calls} == {"autonomous"}
    assert await _listed(app, auth_headers, path=fix) == []


@pytest.mark.asyncio
async def test_button_only_mode_fires_on_no_advance(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    fake = worker()
    await _configure(app, auth_headers, mode="button")
    await _drafted(app, auth_headers, run_headers)
    await _move(app, auth_headers, size="large", step="acceptance")

    await _move(app, auth_headers, step="approach")

    assert await _firings() == [] and fake.calls == []


@pytest.mark.asyncio
async def test_automatic_does_not_fire_moving_back_or_while_the_job_is_off(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    fake = worker()
    await _drafted(app, auth_headers, run_headers)
    await _move(app, auth_headers, size="large", step="acceptance")
    await _move(app, auth_headers, step="approach")  # the job is off: nothing
    await pre_mortem.settled()  # judged when it fires, so let it fire before switching on
    await _configure(app, auth_headers, mode="automatic")
    await _move(app, auth_headers, step="acceptance")

    await _move(app, auth_headers, step="requirements")  # back: the criteria were not written

    assert await _firings() == [] and fake.calls == []


@pytest.mark.asyncio
async def test_automatic_with_no_runner_records_that_it_did_nothing(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    fake = worker()
    await app.patch(
        f"{BASE}/manager/jobs/{JOB}",
        json={"enabled": True, "mode": "automatic"},
        headers=auth_headers,
    )
    await _drafted(app, auth_headers, run_headers)
    await _move(app, auth_headers, size="large", step="acceptance")

    await _move(app, auth_headers, step="approach")

    (firing,) = await _firings()
    assert firing["outcome"] == "failed" and "no runner" in firing["detail"]
    assert fake.calls == []


# pre-mortem-reaches-author
@pytest.mark.asyncio
async def test_the_briefing_carries_the_latest_written_findings(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    await _configure(app, auth_headers)
    await _drafted(app, auth_headers, run_headers)
    assert "### Pre-mortem findings" not in await _briefing(app, auth_headers)

    worker()
    await app.post(f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers)
    await pre_mortem.settled()
    newer = "Nobody checks the route returns 404 for a trailing slash."
    worker(pre_mortem.PreMortemAnswer(findings=[pre_mortem.Finding(story=newer, cites=[])]))
    await app.post(f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers)
    await pre_mortem.settled()
    worker(fail=True)  # a failed firing after them does not hide the written one
    await app.post(f"{BASE}/manager/jobs/{JOB}/run", json={"path": PATH}, headers=auth_headers)
    await pre_mortem.settled()

    text = await _briefing(app, auth_headers)

    assert text.count("### Pre-mortem findings") == 1
    block = text[text.index("### Pre-mortem findings") :]
    assert newer in block and STORY not in block
    assert "Fix what you can" in block and "Bring the rest to the operator as questions" in block


@pytest.mark.asyncio
async def test_the_briefing_of_a_document_with_no_firing_has_no_heading(
    app, auth_headers, run_headers, tmp_path, worker  # noqa: F811
):
    worker()
    await _configure(app, auth_headers)
    await _drafted(app, auth_headers, run_headers)
    other = "spec/changes/other/spec.json"
    await _drafted(app, auth_headers, run_headers, path=other)
    await app.post(f"{BASE}/manager/jobs/{JOB}/run", json={"path": other}, headers=auth_headers)
    await pre_mortem.settled()

    assert "### Pre-mortem findings" in await _briefing(app, auth_headers, path=other)
    assert "### Pre-mortem findings" not in await _briefing(app, auth_headers)


def test_a_finding_names_a_requirement_only_by_one_of_the_documents_identifiers():
    answer = pre_mortem.PreMortemAnswer(
        findings=[
            pre_mortem.Finding(story="a", requirement="FR-1"),
            pre_mortem.Finding(story="b", requirement="alpha"),
            pre_mortem.Finding(story="c", requirement="FR-99"),
            pre_mortem.Finding(story="  "),
        ]
    )

    kept = pre_mortem.kept_findings(answer, {"alpha": "FR-1"})

    assert [(f["story"], f["requirement"]) for f in kept] == [
        ("a", "FR-1"),
        ("b", "FR-1"),
        ("c", None),
    ]
