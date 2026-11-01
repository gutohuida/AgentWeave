"""A build too large for one call is reviewed in parts (FR-14), each part grounded (FR-8) and each
recorded (FR-12). As in `test_build_retrospective.py` the worker is faked; here it records every
prompt it is handed and answers by which kind of call it is."""

import json

import pytest

from hub import build_retrospective as br
from hub import spec_amendments
from hub.db.models import SpecDocumentEvent
from hub.worker import WorkerResult, WorkerUsage

from .test_build_retrospective import (
    DOC,
    P,
    _approve,
    _configure,
    _document,
    _fire,
    _firings,
    _listed,
    _move,
    _seed,
    _task,
    finding,
)

LIMIT = 11_000
NOTE = "x" * 3000
TASKS = ("t1", "t2", "t3", "t4")


class _Recorder:
    """Answers each part with *part*, the last call with *final*; *fail_part* fails that part."""

    def __init__(self, part=None, final=None, fail_part=None) -> None:
        self.part = part or br.RetrospectiveAnswer()
        self.final = final or br.RetrospectiveAnswer(lessons=[finding("the report", "t1")])
        self.fail_part = fail_part
        self.calls = []

    @property
    def part_calls(self):
        return [c for c in self.calls if c["prompt_version"] == br.PART_PROMPT_VERSION]

    @property
    def final_calls(self):
        return [c for c in self.calls if c["prompt_version"] == br.FINAL_PROMPT_VERSION]

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        is_part = kwargs["prompt_version"] == br.PART_PROMPT_VERSION
        if is_part and len(self.part_calls) == self.fail_part:
            return WorkerResult("spawn_failed", error="the CLI is not installed")
        return WorkerResult(
            "ok",
            parsed=self.part if is_part else self.final,
            usage=WorkerUsage(input_tokens=11, output_tokens=7, cost_usd_micros=100),
            duration_ms=5,
        )


@pytest.fixture
def recorder(monkeypatch):
    monkeypatch.setattr(br, "input_limit", lambda model: LIMIT)

    def install(**kwargs):
        fake = _Recorder(**kwargs)
        monkeypatch.setattr(br, "run_worker", fake)
        return fake

    return install


def _body(call):
    prompt = call["prompt"]
    start = prompt.index(br.RECORD_START) + len(br.RECORD_START)
    return json.loads(prompt[start : prompt.index(br.RECORD_END)])


async def _four_tasks(status="approved"):
    await _seed(
        _document(),
        *[_task(task, status=status, notes=f"{task}-marker {NOTE}") for task in TASKS],
    )


@pytest.mark.asyncio
async def test_a_large_build_is_split_and_written_from_the_part_reviews(
    app, auth_headers, recorder
):
    fake = recorder(part=br.RetrospectiveAnswer(friction=[finding("a part's finding", "t2")]))
    await _configure(app, auth_headers)
    await _four_tasks()
    assert await _fire() == "written"

    assert len(fake.part_calls) > 1
    assert len(fake.final_calls) == 1 and fake.calls[-1] is fake.final_calls[0]
    assert all(len(call["prompt"]) <= LIMIT for call in fake.calls)
    # Every task in exactly one part, whole.
    seen = []
    for call in fake.part_calls:
        tasks = _body(call)["tasks"]
        seen.extend(task["id"] for task in tasks)
        assert all(task["notes"].endswith(NOTE) for task in tasks)
    assert sorted(seen) == list(TASKS)
    for task in TASKS:
        assert sum(f"{task}-marker" in call["prompt"] for call in fake.part_calls) == 1

    # The last call holds the part reviews and the build-wide figures, and no task's records.
    final = _body(fake.final_calls[0])
    assert [row["part"] for row in final["part_reviews"]] == list(
        range(1, len(fake.part_calls) + 1)
    )
    assert final["part_reviews"][0]["review"]["friction"][0]["text"] == "a part's finding"
    assert [row["task_id"] for row in final["figures"]["per_task_time"]] == list(TASKS)
    assert "tasks" not in final and NOTE not in fake.final_calls[0]["prompt"]

    (listed,) = await _listed(app, auth_headers)
    assert listed["parts"] == len(fake.part_calls) == listed["report"]["parts"]
    # The report is the final call's, its figures the Hub's over all four tasks.
    assert [row["text"] for row in listed["report"]["lessons"]] == ["the report"]
    assert len(listed["report"]["where_time_went"]["per_task"]) == 4
    assert listed["cost_usd_micros"] == 100 * len(fake.calls)


@pytest.mark.asyncio
async def test_a_build_that_fits_makes_exactly_one_call(app, auth_headers, recorder):
    fake = recorder(final=br.RetrospectiveAnswer(lessons=[finding("one", "t1")]))
    await _configure(app, auth_headers)
    await _seed(_document(), _task("t1", status="approved", notes="short"))
    assert await _fire() == "written"
    assert [call["prompt_version"] for call in fake.calls] == [br.PROMPT_VERSION]
    (listed,) = await _listed(app, auth_headers)
    assert listed["parts"] == 1 and listed["report"]["parts"] == 1
    assert listed["cost_usd_micros"] == 100
    assert len(await _firings()) == 1


@pytest.mark.asyncio
async def test_each_part_is_its_own_event_and_only_the_firing_is_listed(
    app, auth_headers, recorder
):
    fake = recorder()
    await _configure(app, auth_headers)
    await _four_tasks()
    await _fire()
    firings = await _firings()
    parts = [row for row in firings if row.get("part") is not None]
    assert len(parts) == len(fake.part_calls) and len(firings) == len(parts) + 1
    assert all(row["outcome"] == br.PART_REVIEWED and row["usage"] for row in parts)
    assert all(row["subject"]["document"] == DOC for row in parts)
    assert sorted(task for row in parts for task in row["tasks"]) == list(TASKS)
    # Each event's usage is its own call's, so summing the firings counts nothing twice.
    assert sum(row["usage"]["cost_usd_micros"] for row in firings) == 100 * len(fake.calls)
    assert len(await _listed(app, auth_headers)) == 1


@pytest.mark.asyncio
async def test_grounding_holds_in_every_part_and_the_final_report(app, auth_headers, recorder):
    await _seed(
        _document("spdoc-other", "spec/changes/other/spec.json"),
        _task("t-other", document="spdoc-other"),
    )
    fake = recorder(
        part=br.RetrospectiveAnswer(
            friction=[
                finding("grounded in a part", "t1"),
                finding("another document's", "t-other"),
                finding("cites nothing"),
            ],
            improvements=[br.Improvement(label="tooling", text="made up", cites=["no-such-id"])],
            send_backs=[br.SendBackDraft(transition_id="no-such", cause="spec", cites=["t1"])],
        ),
        final=br.RetrospectiveAnswer(
            lessons=[finding("kept", "t1"), finding("brought back", "t-other"), finding("bare")]
        ),
    )
    await _configure(app, auth_headers)
    await _four_tasks()
    assert await _fire() == "written"

    final_input = fake.final_calls[0]["prompt"].split(br.RECORD_START)[1]
    assert "grounded in a part" in final_input
    for ungrounded in ("another document's", "cites nothing", "made up", "no-such"):
        assert ungrounded not in final_input
    (listed,) = await _listed(app, auth_headers)
    assert [row["text"] for row in listed["report"]["lessons"]] == ["kept"]
    # Four lost in each part, two in the final report.
    assert listed["report"]["dropped"] == 4 * len(fake.part_calls) + 2
    parts = [row for row in await _firings() if row.get("part") is not None]
    assert all("4 claims dropped" in row["detail"] for row in parts)


@pytest.mark.asyncio
async def test_a_part_that_fails_ends_the_firing_as_failed(app, auth_headers, recorder):
    fake = recorder(fail_part=2)
    await _configure(app, auth_headers)
    await _four_tasks()
    assert await _fire() == "failed"
    assert len(fake.part_calls) == 2 and not fake.final_calls
    (listed,) = await _listed(app, auth_headers)
    assert listed["outcome"] == "failed" and listed["report"] is None
    assert "Part 2 of" in listed["detail"] and "not installed" in listed["detail"]
    # What the part before it cost is still the firing's.
    assert listed["cost_usd_micros"] == 100
    outcomes = [row["outcome"] for row in await _firings() if row.get("part") is not None]
    assert outcomes == ["failed", br.PART_REVIEWED]


@pytest.mark.asyncio
async def test_a_failing_part_does_not_hold_up_the_approval_that_fired_it(
    app, auth_headers, recorder
):
    recorder(fail_part=1)
    await _configure(app, auth_headers)
    await _seed(
        _document(),
        *[_task(task, status="approved", notes=f"{task} {NOTE}") for task in TASKS[:3]],
        _task("t4", notes=f"t4 {NOTE}"),
    )
    await _approve(app, auth_headers, "t4")
    firings = await _firings()
    assert firings and all(row["outcome"] == "failed" for row in firings)
    assert {row["trigger"] for row in firings} == {br.LAST_TASK_APPROVED}


@pytest.mark.asyncio
async def test_one_task_too_large_is_refused_not_divided(app, auth_headers, recorder):
    fake = recorder()
    await _configure(app, auth_headers)
    await _seed(
        _document(),
        _task("t1", status="approved", readable_id="RD-1", notes="y" * (LIMIT * 2)),
        _task("t2", status="approved", notes="short"),
    )
    assert await _fire() == "failed"
    assert fake.calls == []
    (listed,) = await _listed(app, auth_headers)
    assert "Task RD-1" in listed["detail"] and "without dividing" in listed["detail"]


@pytest.mark.asyncio
async def test_part_reviews_too_large_together_fail_with_the_reason(app, auth_headers, recorder):
    fake = recorder(part=br.RetrospectiveAnswer(friction=[finding("z" * 5000, "t1")]))
    await _configure(app, auth_headers)
    await _four_tasks()
    assert await _fire() == "failed"
    assert not fake.final_calls
    (listed,) = await _listed(app, auth_headers)
    assert "could not be brought into one report" in listed["detail"]


@pytest.mark.asyncio
async def test_records_of_no_task_and_send_backs_land_where_they_belong(
    app, auth_headers, recorder
):
    fake = recorder()
    await _configure(app, auth_headers)
    await _four_tasks()
    await _seed(
        SpecDocumentEvent(
            id="spev-1",
            project_id=P,
            document_id=DOC,
            kind=spec_amendments.EVENT,
            actor_kind="agent",
            origin="control",
            actor="qa",
            detail={"id": "am-1"},
        ),
        _move("m1", "t3", "completed", "revision_needed", 1, reason_class="flaky"),
    )
    await _fire()
    held = [
        row["id"]
        for call in fake.part_calls
        for row in _body(call).get("amendments_and_reconciles", [])
    ]
    assert held == ["spev-1"]
    with_send_back = [call for call in fake.part_calls if _body(call).get("send_backs")]
    assert len(with_send_back) == 1
    assert "t3" in [task["id"] for task in _body(with_send_back[0])["tasks"]]
    assert _body(fake.final_calls[0])["send_backs"][0]["transition_id"] == "m1"


def test_the_limit_follows_the_chosen_model():
    assert br.input_limit("claude-haiku-4-5-20251001") == int(200_000 * 3 * 0.8)
    assert br.input_limit("claude-sonnet-5-5") == int(1_000_000 * 3 * 0.8)
    assert br.input_limit(None) == br.input_limit("not-a-model") == int(200_000 * 3 * 0.8)
