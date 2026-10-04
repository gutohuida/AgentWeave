"""Slice 5 amendment D8a (F484), task 4.4: the review bullet says how to dispatch, and the stream
says what ran.

Drive 7.7 (2026-10-03) found a Copilot reviewer told to consult `code-review` that never
dispatched it, then wrote into its verdict and into `update_task`'s notes that "the independent
code-review agent" had flagged the defect. The Hub does not judge the reviewer's prose (CLAUDE.md:
the retired prose detector). It states the fact: a `review_agents_report` status at the end of
every Copilot review turn whose context named review agents, built from the subagent events
Copilot reported in that run, "none" included.

Every test here failed before D8a was built (no such wording, key, keyword or phase), except
those asserting that nothing is emitted, which guard the build.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import copilot_acp, worktrees
from hub.copilot_acp import RAW_EVENT_METHOD, CopilotEventMapper
from hub.db.engine import async_session_factory
from hub.db.models import Agent
from hub.runner_events import RunEvent

from .test_copilot_acp_run_turn import _END_TURN, _drive, _new_with, _raw_event
from .test_review_turn_copilot_agents import PROJECT, _context, _review

FIXTURES = Path(__file__).parent / "fixtures" / "copilot"


def _load(name: str) -> List[Dict[str, Any]]:
    return [
        json.loads(line)
        for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _feed(messages, mapper) -> List[RunEvent]:
    events: List[RunEvent] = []
    for message in messages:
        params = message.get("params") or {}
        if message.get("method") == RAW_EVENT_METHOD:
            events += mapper.on_raw_event(params.get("type"), params.get("data"), params)
        elif message.get("method") == "session/update":
            update = params.get("update")
            if isinstance(update, dict) and update.get("sessionUpdate") != "usage_update":
                events += mapper.on_session_update(update)
    return events + mapper.finish()


def _as_code_review(messages):
    """The captured `explore` dispatch, renamed: the second capture dispatched `code-review` the
    same way (`ghcp-s5-subagent-capture` item 2); agentName and agentType are the dispatch id."""
    out = []
    for message in messages:
        params = message.get("params") or {}
        data = params.get("data") if isinstance(params.get("data"), dict) else None
        if message.get("method") == RAW_EVENT_METHOD and str(params.get("type")).startswith(
            "subagent."
        ):
            data = dict(data)
            data["agentName"] = "code-review"
            if "agentType" in data:
                data["agentType"] = "code-review"
            message = {**message, "params": {**params, "data": data}}
        out.append(message)
    return out


def _reports(events):
    return [
        e for e in events if e.kind == "status" and e.payload.get("phase") == "review_agents_report"
    ]


# --------------------------------------------------------------------------- the bullet


BULLET_ONE = (
    "- Before your verdict, run Copilot's `code-review` agent as a subagent on the changes from "
    f"`{'b' * 40}` to `{'c' * 40}`: call the `task` tool with `agent_type` exactly "
    '`"code-review"`. If it fails because a model is not available, call it again with `model` '
    "set to the model you are running on if the error lists it, otherwise to the first named "
    "model it lists, never `auto`. Weigh what it reports and check it yourself. It does not see "
    "this repository's instructions, and its findings are not your verdict. If it did not run, "
    "say so; never describe a review it did not give. The verdict is yours, and it is recorded "
    "only by `update_task`."
)


@pytest.mark.asyncio
async def test_the_bullet_names_the_dispatch_exactly(app, auth_headers, add_agent):
    await add_agent("critic", config={"copilot_review_agents": ["code-review"]})
    context = await _context(
        "critic", runner="copilot", review=_review(commit_sha="c" * 40, base_sha="b" * 40)
    )
    assert BULLET_ONE in context


@pytest.mark.asyncio
async def test_several_agents_get_the_written_out_template_once_each(app, auth_headers, add_agent):
    await add_agent(
        "critic",
        config={"copilot_review_agents": ["code-review", "security-review", "code-review"]},
    )
    context = await _context("critic", runner="copilot", review=_review(commit_sha="c" * 40))
    assert (
        "- Before your verdict, run Copilot's `code-review`, `security-review` agents as subagents "
        f"on `{'c' * 40}`'s own changes: call the `task` tool once for each, with `agent_type` "
        'exactly `"code-review"`, then `"security-review"`.'
    ) in context
    assert context.count("`code-review`") == 1


async def _rendered(name, *, runner, review):
    async with async_session_factory() as session:
        agent_row = (
            await session.execute(
                select(Agent).where(Agent.project_id == PROJECT, Agent.name == name)
            )
        ).scalar_one()
        from hub.api.v1.agents import _render_hub_agent_context

        return await _render_hub_agent_context(
            agent=name,
            project_id=PROJECT,
            db=session,
            session_data=None,
            agent_row=agent_row,
            work_dir="/work",
            review=review,
            runner=runner,
        )


@pytest.mark.asyncio
async def test_the_rendered_context_carries_the_list_the_bullet_names(app, auth_headers, add_agent):
    await add_agent("critic", config={"copilot_review_agents": ["code-review", "code-review"]})
    assert (await _rendered("critic", runner="copilot", review=_review()))[
        "copilot_review_agents"
    ] == ["code-review"]
    # No bullet, no list: an ordinary turn, and another runner.
    assert (await _rendered("critic", runner="copilot", review=None))["copilot_review_agents"] == []
    assert (await _rendered("critic", runner="claude", review=_review()))[
        "copilot_review_agents"
    ] == []


# --------------------------------------------------------------------------- the report


def test_a_review_agent_that_ran_is_reported_with_its_outcome_and_model():
    mapper = CopilotEventMapper(review_agents=["code-review"])
    events = _feed(_as_code_review(_load("subagent.jsonl")), mapper)

    (report,) = _reports(events)
    assert events[-1] is report, "the report is the turn's last card"
    facts = report.payload
    assert facts["asked"] == ["code-review"]
    assert facts["missing"] == []
    (ran,) = facts["ran"]
    assert ran["agent_name"] == "code-review"
    assert ran["agent_type"] == "code-review"
    assert ran["outcome"] == "completed"
    assert ran["model"] == "claude-haiku-4.5"
    assert ran["agent_id"] == "87c20d8e-8d8b-4523-a4b2-4c7f5d625672"
    assert "in this run" in report.content
    assert "`code-review` (completed, claude-haiku-4.5)" in report.content


def test_a_review_agent_that_did_not_run_is_reported_missing():
    mapper = CopilotEventMapper(review_agents=["code-review"])
    events = _feed(_load("error.jsonl"), mapper)

    (report,) = _reports(events)
    assert report.kind == "status"
    assert report.payload["ran"] == []
    assert report.payload["missing"] == ["code-review"]
    assert "Copilot ran no subagent in this run" in report.content


def test_the_display_name_is_not_the_dispatch_id():
    """The fixture's `agentDisplayName` is the `task` call's free-text name (`file-name-probe`);
    the asked name is matched against the dispatch id only."""
    mapper = CopilotEventMapper(review_agents=["file-name-probe"])
    (report,) = _reports(_feed(_load("subagent.jsonl"), mapper))
    assert report.payload["missing"] == ["file-name-probe"]
    assert [r["agent_name"] for r in report.payload["ran"]] == ["explore"]


def test_a_same_named_agent_of_another_type_does_not_count():
    """Pre-approval review finding 6: a repository's own agent named `code-review` must not
    satisfy the report as Copilot's built-in review."""
    messages = []
    for message in _load("subagent.jsonl"):
        params = message.get("params") or {}
        if message.get("method") == RAW_EVENT_METHOD and str(params.get("type")).startswith(
            "subagent."
        ):
            data = {**params["data"], "agentName": "code-review"}
            if "agentType" in data:
                data["agentType"] = "custom"
            message = {**message, "params": {**params, "data": data}}
        messages.append(message)
    mapper = CopilotEventMapper(review_agents=["code-review"])
    (report,) = _reports(_feed(messages, mapper))
    assert report.payload["missing"] == ["code-review"]


def test_a_subagent_that_started_and_never_ended_is_reported_started():
    messages = [
        m
        for m in _as_code_review(_load("subagent.jsonl"))
        if (m.get("params") or {}).get("type") != "subagent.completed"
    ]
    mapper = CopilotEventMapper(review_agents=["code-review"])
    (report,) = _reports(_feed(messages, mapper))
    assert [r["outcome"] for r in report.payload["ran"]] == ["started"]
    assert report.payload["missing"] == []


def test_without_named_review_agents_nothing_is_reported():
    assert _reports(_feed(_load("subagent.jsonl"), CopilotEventMapper())) == []
    assert _reports(_feed(_load("subagent.jsonl"), CopilotEventMapper(review_agents=[]))) == []


# --------------------------------------------------------------------------- run_turn


_SUBAGENT_DONE = [
    _raw_event(
        "subagent.started",
        {"toolCallId": "call_t", "agentName": "code-review", "agentType": "code-review"},
    ),
    _raw_event(
        "subagent.completed",
        {"toolCallId": "call_t", "agentName": "code-review", "model": "claude-haiku-4.5"},
    ),
]


@pytest.mark.asyncio
async def test_run_turn_passes_the_list_and_the_report_ends_the_turn(monkeypatch):
    _fake, events, outcome = await _drive(
        monkeypatch,
        _new_with() + _SUBAGENT_DONE + [_END_TURN],
        agent_config={"review_agents": ["code-review"]},
    )
    (report,) = _reports(events)
    assert report.payload["missing"] == []
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_an_interrupted_review_turn_still_reports(monkeypatch):
    _fake, events, outcome = await _drive(
        monkeypatch,
        _new_with() + [_END_TURN],
        agent_config={"review_agents": ["code-review"]},
        should_interrupt=lambda: True,
    )
    assert len(_reports(events)) == 1


@pytest.mark.asyncio
async def test_a_report_that_raises_loses_the_card_never_the_turn(monkeypatch):
    def boom(self):
        raise RuntimeError("report failed")

    monkeypatch.setattr(CopilotEventMapper, "_review_agents_report", boom)
    _fake, events, outcome = await _drive(
        monkeypatch,
        _new_with() + [_END_TURN],
        agent_config={"review_agents": ["code-review"]},
    )
    assert _reports(events) == []
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_a_turn_without_review_agents_reports_nothing(monkeypatch):
    _fake, events, _outcome = await _drive(
        monkeypatch, _new_with() + _SUBAGENT_DONE + [_END_TURN], agent_config={}
    )
    assert _reports(events) == []


# --------------------------------------------------------------------------- the trigger


@pytest.fixture
def _copilot_review_setup(tmp_path, monkeypatch, bind_project_workspace, add_agent):
    from .test_agent_trigger import _init_repo
    from .test_review_turn import _REAL_ENSURE_REVIEW_CHECKOUT, _author_commit

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    exe = tmp_path / "copilot.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", lambda override: exe)
    monkeypatch.setattr(worktrees, "ensure_review_checkout", _REAL_ENSURE_REVIEW_CHECKOUT)
    repo = _init_repo(tmp_path / "repo")
    sha = _author_commit(repo, filename="ledger.py", body="x = 1\n")

    async def setup(app, auth_headers, bind_runner):
        from .test_review_turn import _reviewable_task

        await bind_project_workspace(repo)
        await add_agent("critic", config={"copilot_review_agents": ["code-review"]})
        await bind_runner("critic", cli="copilot")
        await _reviewable_task(commit=sha)

    return setup


def _fake_turn():
    from .test_copilot_trigger import _fake_turn as fake

    return fake()


@pytest.mark.asyncio
async def test_a_review_turn_carries_the_list_to_run_turn(
    app, auth_headers, bind_runner, _copilot_review_setup
):
    from ._background_runs import await_background_runs

    await _copilot_review_setup(app, auth_headers, bind_runner)
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        response = await app.post(
            f"/api/v1/projects/{PROJECT}/agent/trigger",
            json={"agent": "critic", "message": "review", "review_task_id": "task-1"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        await await_background_runs()
    assert fake.call_args.kwargs["agent_config"]["review_agents"] == ["code-review"]


@pytest.mark.asyncio
async def test_an_ordinary_turn_of_the_same_agent_carries_no_list(
    app, auth_headers, bind_runner, _copilot_review_setup
):
    """Finding 5: a trigger that read the stored config, not the rendered list, would fail this."""
    from ._background_runs import await_background_runs

    await _copilot_review_setup(app, auth_headers, bind_runner)
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        response = await app.post(
            f"/api/v1/projects/{PROJECT}/agent/trigger",
            json={"agent": "critic", "message": "hi", "session_mode": "new"},
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        await await_background_runs()
    assert "review_agents" not in fake.call_args.kwargs["agent_config"]


@pytest.mark.asyncio
async def test_a_dispatched_review_carries_the_list_too(
    app, auth_headers, bind_runner, _copilot_review_setup
):
    """The flow's path: `trigger_agent_directly(review_task_id=…)`, not the route's body."""
    from hub.api.v1.agent_trigger import trigger_agent_directly
    from hub.conversations import new_conversation

    from ._background_runs import await_background_runs

    await _copilot_review_setup(app, auth_headers, bind_runner)
    fake = _fake_turn()
    with patch("hub.copilot_acp.run_turn", fake):
        async with async_session_factory() as db:
            conversation = new_conversation(project_id=PROJECT, agent="critic", origin="operator")
            db.add(conversation)
            await db.commit()
            await trigger_agent_directly(
                project_id=PROJECT,
                agent="critic",
                message="review task-1",
                conversation_id=conversation.id,
                session=db,
                review_task_id="task-1",
            )
        await await_background_runs()
    assert fake.call_args.kwargs["agent_config"]["review_agents"] == ["code-review"]


def test_the_report_builder_exists():
    assert hasattr(copilot_acp.CopilotEventMapper, "_review_agents_report")
