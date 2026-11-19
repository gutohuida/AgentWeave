"""Runs launch with their chosen entry (`a-profile-runs-each-task-on-a-runner-and-model-chosen-from-
its-pool`, task launch-path): FR-7, FR-8, FR-10, FR-12 and FR-13.

Every start enters through `POST /agent/trigger` with the CLIs replaced by the stubs
`test_rebinding_an_agents_runner_starts_clean` uses, so what is asserted is the argv the CLI was
handed, the `Run` row, `GET /runs/{id}` and the run's trace root -- never the resolver alone.
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import select

from hub import launch_entry
from hub.api.v1.agent_trigger import trigger_agent_directly
from hub.conversations import (
    get_conversation_by_id,
    inherit_runtime_overrides,
    new_conversation,
)
from hub.db.engine import async_session_factory
from hub.db.models import Build, Run, Task
from hub.review_turn import ReviewContext

from ._background_runs import await_background_runs
from .test_rebinding_an_agents_runner_starts_clean import _Claude, _Codex

PROJECT = "/api/v1/projects/proj-test"
HAIKU = "claude-haiku-5-5"
SONNET = "claude-sonnet-5-5"
OPUS = "claude-opus-5-5"

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _copilot_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    exe = tmp_path / "copilot.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", lambda override: exe)


class _Drive:
    """One test's operator: runners, agents with pools, tasks, builds and stubbed turns."""

    def __init__(self, app, headers) -> None:
        self.app = app
        self.headers = headers
        self.claude = _Claude()
        self.codex = _Codex()
        self.runners: Dict[str, str] = {}
        self.names: List[str] = []

    def _stubs(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch("hub.api.v1.agent_trigger.PtySession.spawn", self.claude.spawn))
        stack.enter_context(patch("hub.api.v1.agent_trigger.PipeSession.spawn", self.codex.spawn))
        stack.enter_context(
            patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/cli")
        )
        stack.enter_context(
            patch("hub.api.v1.agent_trigger.review_turn.prepare_review_turn", self._review)
        )
        # The route's early answer reads the task's branch; there is no repository here.
        stack.enter_context(patch("hub.task_integration.review_target", self._target))
        return stack

    @staticmethod
    async def _review(session, *, project_id, reviewer, task_id, repo_root, run_id=None):
        task = await session.get(Task, task_id)
        return ReviewContext(
            task_id=task_id,
            task_title=task.title,
            reviewer=reviewer,
            commit_sha="a" * 40,
            evidence_id="ev-launch",
            workspace=Path(repo_root),
            earlier_commits=[],
        )

    @staticmethod
    async def _target(session, task):
        return SimpleNamespace(resolved=True, refusal=None)

    async def runner(self, label: str, model: str, cli: str = "claude", flags=None) -> str:
        payload: Dict[str, Any] = {"name": label, "cli": cli, "model": model}
        if flags:
            payload["flags"] = flags
        created = await self.app.post(f"{PROJECT}/runners", json=payload, headers=self.headers)
        assert created.status_code == 201, created.text
        self.runners[label] = created.json()["id"]
        return self.runners[label]

    async def agent(self, name: str, pool: List[Dict[str, Any]]) -> None:
        """An agent bound the legacy way to the pool's first entry, then given *pool*."""
        # A sync states the whole roster, so it names every agent this test has made.
        self.names.append(name)
        sync = await self.app.post(
            f"{PROJECT}/session/sync",
            json={"data": {"agents": {n: {"runner": "claude"} for n in self.names}}},
            headers=self.headers,
        )
        assert sync.status_code == 200, sync.text
        bound = await self.app.patch(
            f"{PROJECT}/agents/{name}",
            json={"runner_id": pool[0]["runner_id"]},
            headers=self.headers,
        )
        assert bound.status_code == 200, bound.text
        await self.pool(name, pool)

    async def pool(self, name: str, pool: List[Dict[str, Any]]) -> None:
        resp = await self.app.patch(
            f"{PROJECT}/agents/{name}", json={"pool": pool}, headers=self.headers
        )
        assert resp.status_code == 200, resp.text

    async def task(
        self,
        task_id: str,
        *,
        builder: str = "builder",
        checker: Optional[str] = None,
        status: str = "assigned",
        builder_entry=None,
        checker_entry=None,
    ) -> str:
        """A task of a build that chose *builder_entry*/*checker_entry* for it at Build."""
        async with async_session_factory() as db:
            own: Dict[str, Any] = {"builder": builder, "checker": checker or ""}
            if builder_entry is not None:
                own["builder_entry"] = builder_entry
            if checker_entry is not None:
                own["checker_entry"] = checker_entry
            db.add(
                Build(
                    id=f"build-{task_id}",
                    project_id="proj-test",
                    document_id="spdoc-launch",
                    state="running",
                    driver="flow",
                    level="reviewed",
                    builders=[builder],
                    reviewers=[],
                    people={"builder": builder, "checker": checker, "tasks": {task_id: own}},
                )
            )
            db.add(
                Task(
                    id=task_id,
                    project_id="proj-test",
                    title=f"Task {task_id}",
                    status=status,
                    assignee=builder,
                    builder=builder,
                    checker=checker,
                    spec_task_key=task_id,
                    build_id=f"build-{task_id}",
                )
            )
            await db.commit()
        return task_id

    async def send(self, agent: str, **body: Any) -> dict:
        with self._stubs():
            response = await self.app.post(
                f"{PROJECT}/agent/trigger",
                json={"agent": agent, "message": "go", **body},
                headers=self.headers,
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "running", response.text
            await asyncio.wait_for(await_background_runs(), timeout=60)
        return response.json()


@pytest.fixture
def drive(app, auth_headers):
    return _Drive(app, auth_headers)


def _flag(argv: List[str], name: str) -> Optional[str]:
    return argv[argv.index(name) + 1] if name in argv else None


async def _run(run_id: str) -> Run:
    async with async_session_factory() as db:
        run = await db.get(Run, run_id)
    assert run is not None
    return run


async def _task_row(task_id: str) -> Task:
    async with async_session_factory() as db:
        task = await db.get(Task, task_id)
    assert task is not None
    return task


async def _trace_root(drive: _Drive, run_id: str) -> Dict[str, Any]:
    resp = await drive.app.get(f"{PROJECT}/traces/by-run/{run_id}", headers=drive.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["root"]


async def _haiku_sonnet(drive: _Drive, name: str = "builder") -> None:
    haiku = await drive.runner("Claude Haiku", HAIKU)
    sonnet = await drive.runner("Claude Sonnet", SONNET)
    await drive.agent(name, [{"runner_id": haiku, "default": True}, {"runner_id": sonnet}])


# ------------------------------------------------------------------ FR-7: start precedence


async def test_build_choice_wins_over_the_recommendation(drive):
    """Criterion build-choice-wins: a task recommending Sonnet, Haiku chosen at Build, runs Haiku."""
    await _haiku_sonnet(drive)
    haiku, sonnet = drive.runners["Claude Haiku"], drive.runners["Claude Sonnet"]
    # Sonnet made the default, so a run that ignored the Build choice would show Sonnet twice over.
    await drive.pool("builder", [{"runner_id": haiku}, {"runner_id": sonnet, "default": True}])
    await drive.task("t-choice", builder_entry={"runner_id": haiku, "effort": None})

    async def _recommends_sonnet(session, task, role):
        return {"runner_id": sonnet, "effort": None}

    with patch("hub.launch_entry._recommended", _recommends_sonnet):
        started = await drive.send("builder", task_id="t-choice")

    (argv,) = drive.claude.argvs
    assert _flag(argv, "--model") == HAIKU
    run = await _run(started["run_id"])
    assert (run.runner_id, run.model, run.effort) == (haiku, HAIKU, None)
    task = await _task_row("t-choice")
    assert task.builder_entry == {"agent": "builder", "runner_id": haiku, "effort": None}


async def test_the_recommendation_runs_when_the_pool_holds_it(drive):
    await _haiku_sonnet(drive)
    sonnet = drive.runners["Claude Sonnet"]
    await drive.task("t-rec")

    async def _recommends_sonnet(session, task, role):
        return {"runner_id": sonnet, "effort": None}

    with patch("hub.launch_entry._recommended", _recommends_sonnet):
        started = await drive.send("builder", task_id="t-rec")

    assert _flag(drive.claude.argvs[0], "--model") == SONNET
    assert (await _run(started["run_id"])).runner_id == sonnet


async def test_a_recommendation_outside_the_pool_runs_the_default(drive):
    await _haiku_sonnet(drive)
    opus = await drive.runner("Claude Opus", OPUS)
    await drive.task("t-outside")

    async def _recommends_opus(session, task, role):
        return {"runner_id": opus, "effort": None}

    with patch("hub.launch_entry._recommended", _recommends_opus):
        started = await drive.send("builder", task_id="t-outside")

    assert _flag(drive.claude.argvs[0], "--model") == HAIKU
    run = await _run(started["run_id"])
    assert run.runner_id == drive.runners["Claude Haiku"]
    # Not chosen, so nothing was dropped: the trace has no removal line.
    root = await _trace_root(drive, started["run_id"])
    assert not [e for e in root.get("events") or [] if e["name"] == launch_entry.FALLBACK_EVENT]


async def test_the_recommendation_is_read_from_the_tasks_document(drive):
    """`_recommended` reads the task's own declared entry from its document's payload."""
    sonnet = await drive.runner("Claude Sonnet", SONNET)
    payload = {
        "tasks": [
            {"key": "t-doc", "builder_entry": {"runner_id": sonnet, "effort": "high"}},
            {"key": "other", "builder_entry": {"runner_id": "runner-x"}},
        ]
    }
    async with async_session_factory() as db:
        from hub.db.models import SpecDocument

        db.add(
            SpecDocument(
                id="spdoc-doc",
                project_id="proj-test",
                path="spec/changes/doc/spec.json",
                title="Doc",
                phase="approved",
                kind="change-spec",
            )
        )
        task = Task(
            id="t-doc",
            project_id="proj-test",
            title="t",
            status="assigned",
            spec_document_id="spdoc-doc",
            spec_task_key="t-doc",
        )
        db.add(task)
        await db.commit()
        with patch("hub.launch_entry.spec_documents.read_payload", lambda ws, path: payload):
            got = await launch_entry._recommended(db, task, "builder")
            nothing = await launch_entry._recommended(db, task, "checker")
    assert got == {"runner_id": sonnet, "effort": "high"}
    assert nothing is None


async def test_the_builder_entry_is_kept_for_every_later_turn(drive):
    """Fixed at the first run: a later turn, after the default changed, still runs Sonnet."""
    await _haiku_sonnet(drive)
    haiku, sonnet = drive.runners["Claude Haiku"], drive.runners["Claude Sonnet"]
    await drive.task("t-kept", builder_entry={"runner_id": sonnet, "effort": None})
    await drive.send("builder", task_id="t-kept")
    # The Build choice is gone and the default moved; the task keeps what it started on.
    async with async_session_factory() as db:
        build = await db.get(Build, "build-t-kept")
        build.people = {"builder": "builder", "tasks": {"t-kept": {"builder": "builder"}}}
        await db.commit()
    await drive.pool("builder", [{"runner_id": haiku, "default": True}, {"runner_id": sonnet}])
    second = await drive.send("builder", task_id="t-kept")

    assert [_flag(argv, "--model") for argv in drive.claude.argvs] == [SONNET, SONNET]
    assert (await _run(second["run_id"])).runner_id == sonnet
    root = await _trace_root(drive, second["run_id"])
    assert root["attributes"]["aw.launch.source"] == "fixed"


async def test_checker_entry_kept_after_a_send_back(drive):
    """Criterion checker-entry-kept-after-send-back: Opus high checks the task; the checker's
    default since changed to Sonnet; the task is sent back, rebuilt and reviewed again on Opus
    high."""
    haiku = await drive.runner("Claude Haiku", HAIKU)
    opus = await drive.runner("Claude Opus", OPUS)
    sonnet = await drive.runner("Claude Sonnet", SONNET)
    await drive.agent("builder", [{"runner_id": haiku, "default": True}])
    await drive.agent(
        "checker",
        [{"runner_id": opus, "effort": "high", "default": True}, {"runner_id": sonnet}],
    )
    await drive.task(
        "t-review",
        checker="checker",
        status="completed",
        checker_entry={"runner_id": opus, "effort": "high"},
    )
    first = await drive.send("checker", review_task_id="t-review")

    await drive.pool(
        "checker",
        [{"runner_id": opus, "effort": "high"}, {"runner_id": sonnet, "default": True}],
    )
    # Sent back, rebuilt by its builder, and completed again.
    async with async_session_factory() as db:
        task = await db.get(Task, "t-review")
        task.status = "revision_needed"
        task.assignee = "builder"
        await db.commit()
    await drive.send("builder", task_id="t-review")
    async with async_session_factory() as db:
        task = await db.get(Task, "t-review")
        task.status = "completed"
        await db.commit()
    second = await drive.send("checker", review_task_id="t-review")

    models = [(_flag(a, "--model"), _flag(a, "--effort")) for a in drive.claude.argvs]
    assert models == [(OPUS, "high"), (HAIKU, None), (OPUS, "high")]
    for run_id in (first["run_id"], second["run_id"]):
        run = await _run(run_id)
        assert (run.runner_id, run.model, run.effort) == (opus, OPUS, "high")
    assert (await _task_row("t-review")).checker_entry == {
        "agent": "checker",
        "runner_id": opus,
        "effort": "high",
    }


# ------------------------------------------------------------------ FR-8: a removed entry


async def test_removed_entry_falls_back_to_the_default_with_a_trace_line(drive):
    """Criterion removed-entry-falls-back."""
    await _haiku_sonnet(drive)
    haiku, sonnet = drive.runners["Claude Haiku"], drive.runners["Claude Sonnet"]
    await drive.task("t-removed", builder_entry={"runner_id": sonnet, "effort": None})
    await drive.pool("builder", [{"runner_id": haiku, "default": True}])

    started = await drive.send("builder", task_id="t-removed")

    assert _flag(drive.claude.argvs[0], "--model") == HAIKU
    run = await _run(started["run_id"])
    assert (run.runner_id, run.model) == (haiku, HAIKU)
    root = await _trace_root(drive, started["run_id"])
    (line,) = [e for e in root["events"] if e["name"] == launch_entry.FALLBACK_EVENT]
    message = line["attributes"]["aw.message"]
    assert "Sonnet 5.5" in message and "removed from builder's pool" in message
    assert line["attributes"]["aw.pool.dropped_runner_id"] == sonnet
    assert root["attributes"]["aw.launch.source"] == "fallback"


async def test_a_conversation_already_started_keeps_its_runner(drive):
    """FR-8's second half: Sonnet leaves the pool mid-task; the task's conversation that started on
    it carries on on Sonnet."""
    await _haiku_sonnet(drive)
    haiku, sonnet = drive.runners["Claude Haiku"], drive.runners["Claude Sonnet"]
    await drive.task("t-started", builder_entry={"runner_id": sonnet, "effort": None})
    first = await drive.send("builder", task_id="t-started")
    await drive.pool("builder", [{"runner_id": haiku, "default": True}])

    second = await drive.send(
        "builder", task_id="t-started", conversation_id=first["conversation_id"]
    )

    assert [_flag(a, "--model") for a in drive.claude.argvs] == [SONNET, SONNET]
    assert (await _run(second["run_id"])).runner_id == sonnet


# ------------------------------------------------------------------ FR-10: chat picks stay put


async def _chat_with_sonnet(drive: _Drive) -> str:
    """The operator picks Sonnet in a chat of a profile whose default is Haiku."""
    chat = await drive.send("builder", overrides={"model": SONNET})
    assert _flag(drive.claude.argvs[-1], "--model") == SONNET
    return chat["conversation_id"]


async def test_chat_pick_not_inherited_by_a_task_or_a_review(drive):
    """Criterion chat-pick-not-inherited, the task and review legs."""
    await _haiku_sonnet(drive)
    await drive.agent("checker", [{"runner_id": drive.runners["Claude Haiku"], "default": True}])
    await _chat_with_sonnet(drive)
    await drive.task("t-chat")
    await drive.send("builder", task_id="t-chat")
    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent="checker", origin="peer")
        conversation.runtime_overrides = {"model": SONNET}
        db.add(conversation)
        task = await db.get(Task, "t-chat")
        task.status = "completed"
        await db.commit()
    # The reviewer's own chat stores Sonnet too; the review still launches on its default.
    await drive.send("checker", review_task_id="t-chat", conversation_id=conversation.id)

    assert [_flag(a, "--model") for a in drive.claude.argvs] == [SONNET, HAIKU, HAIKU]


@pytest.mark.parametrize("origin", ["job", "peer"])
async def test_chat_pick_not_inherited_by_a_job_or_a_peer_message(drive, origin):
    """Criterion chat-pick-not-inherited, the job and peer-message legs: the conversation those
    open copies the chat's posture but never its model, and their runs launch on Haiku."""
    await _haiku_sonnet(drive)
    await _chat_with_sonnet(drive)
    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent="builder", origin=origin)
        db.add(conversation)
        await inherit_runtime_overrides(db, conversation)
        await db.commit()
        assert not (conversation.runtime_overrides or {}).get("model")

    # And a peer/job turn in a conversation that does store a model -- the operator's own chat --
    # launches on the default, since only the operator's turn is a chat's.
    async with async_session_factory() as db:
        stored = await get_conversation_by_id(db, conversation.id)
        stored.runtime_overrides = {"model": SONNET, "effort": "high"}
        await db.commit()
        with drive._stubs():
            result = await trigger_agent_directly(
                project_id="proj-test",
                agent="builder",
                message=f"from a {origin}",
                conversation_id=conversation.id,
                session=db,
                initiator="autonomous",
            )
            await asyncio.wait_for(await_background_runs(), timeout=60)

    argv = drive.claude.argvs[-1]
    assert (_flag(argv, "--model"), _flag(argv, "--effort")) == (HAIKU, None)
    assert (await _run(result.run_id)).model == HAIKU


async def test_a_chat_keeps_its_own_pick(drive):
    """The operator's own chat still runs what they picked in it (FR-9 bounds the pick)."""
    await _haiku_sonnet(drive)
    conversation_id = await _chat_with_sonnet(drive)
    await drive.send("builder", conversation_id=conversation_id)
    assert [_flag(a, "--model") for a in drive.claude.argvs] == [SONNET, SONNET]


# ------------------------------------------------------------------ FR-12: the run records it


async def test_run_shows_entry_on_codex(drive):
    """Criterion run-shows-entry: Codex gpt-6.1-sol with effort high, in the runs API and trace."""
    codex = await drive.runner("Codex Sol", "gpt-6.1-sol", cli="codex", flags=["--no-app-server"])
    await drive.agent("coder", [{"runner_id": codex, "effort": "high", "default": True}])

    started = await drive.send("coder")

    (argv,) = drive.codex.argvs
    assert "model_reasoning_effort=high" in argv
    resp = await drive.app.get(f"{PROJECT}/runs/{started['run_id']}", headers=drive.headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["runner_id"], body["model"], body["effort"]) == (codex, "gpt-6.1-sol", "high")
    assert (body["cli"], body["runner_name"]) == ("codex", "Codex Sol")
    assert body["status"] in ("completed", "failed", "started")
    attributes = (await _trace_root(drive, started["run_id"]))["attributes"]
    assert attributes["aw.runner.id"] == codex
    assert attributes["aw.runner.cli"] == "codex"
    assert attributes["gen_ai.request.model"] == "gpt-6.1-sol"
    assert attributes["aw.request.effort"] == "high"

    timeline = await drive.app.get(f"{PROJECT}/agents/coder/timeline", headers=drive.headers)
    facts = timeline.json()["runs"][started["run_id"]]
    assert (facts["runner_id"], facts["model"], facts["effort"]) == (codex, "gpt-6.1-sol", "high")


async def test_runs_route_answers_404_for_another_projects_run(drive):
    resp = await drive.app.get(f"{PROJECT}/runs/run-nope", headers=drive.headers)
    assert resp.status_code == 404


# ------------------------------------------------------------------ FR-13: one entry, as before


def _argv(context: str) -> List[str]:
    return [
        "claude",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        HAIKU,
        "--append-system-prompt-file",
        f"<tmp>/.agentweave/context/{context}.md",
        "--strict-mcp-config",
        "--setting-sources",
        "project,local",
        "--thinking-display",
        "summarized",
        "--mcp-config",
        "<mcp-config>",
        "--allowedTools",
        "mcp__agentweave__*",
        "Bash(aw-tool:*)",
        "PowerShell(aw-tool:*)",
        "--permission-prompt-tool",
        "mcp__agentweave__approve_tool_call",
        "--permission-mode",
        "manual",
        "-p",
        "<prompt>",
    ]


#: The argv each start was handed for `_single_entry_argvs`' setup on the code before this change,
#: captured at ad3e8c3 (this file's helper run against `git archive ad3e8c3 hub`) and put through
#: `_normalised`: the tool server's path and the prompt are this machine's and this turn's, so
#: they are compared by position only.
BASELINE: Dict[str, List[str]] = {
    "chat": _argv("solo"),
    "task": _argv("solo"),
    "review": _argv("solo-checker"),
    "job": _argv("solo"),
}


def _normalised(argv: List[str], tmp: str) -> List[str]:
    out: List[str] = []
    for index, value in enumerate(argv):
        previous = argv[index - 1] if index else None
        if previous == "--mcp-config":
            value = "<mcp-config>"
        elif previous == "-p":
            value = "<prompt>"
        else:
            value = value.replace(tmp, "<tmp>").replace("\\", "/")
        out.append(value)
    return out


async def _single_entry_argvs(drive: _Drive, tmp_path) -> Dict[str, List[str]]:
    runner = await drive.runner("Claude Haiku", HAIKU)
    await drive.agent("solo", [{"runner_id": runner, "default": True}])
    await drive.agent("solo-checker", [{"runner_id": runner, "default": True}])
    out: Dict[str, List[str]] = {}
    await drive.send("solo")
    out["chat"] = drive.claude.argvs[-1]
    await drive.task("t-solo", builder="solo", checker="solo-checker")
    await drive.send("solo", task_id="t-solo")
    out["task"] = drive.claude.argvs[-1]
    async with async_session_factory() as db:
        task = await db.get(Task, "t-solo")
        task.status = "completed"
        await db.commit()
    await drive.send("solo-checker", review_task_id="t-solo")
    out["review"] = drive.claude.argvs[-1]
    async with async_session_factory() as db:
        conversation = new_conversation(project_id="proj-test", agent="solo", origin="job")
        db.add(conversation)
        await inherit_runtime_overrides(db, conversation)
        await db.commit()
    await drive.send("solo", conversation_id=conversation.id)
    out["job"] = drive.claude.argvs[-1]
    return out


async def test_single_entry_launch_unchanged(drive, tmp_path):
    """Criterion single-entry-launch-unchanged: one entry, no overrides. GET agent shows it as the
    default, every run records it, and each argv is the flags the same setup was launched with
    before this change: `--model` the runner's, and no `--effort`."""
    argvs = await _single_entry_argvs(drive, tmp_path)
    runner = drive.runners["Claude Haiku"]
    roster = (await drive.app.get(f"{PROJECT}/agents", headers=drive.headers)).json()
    solo = next(a for a in roster if a["name"] == "solo")
    assert [(e["runner_id"], e["effort"], e["default"]) for e in solo["pool"]] == [
        (runner, None, True)
    ]
    async with async_session_factory() as db:
        runs = (await db.execute(select(Run).order_by(Run.started_at))).scalars().all()
    assert len(runs) == 4
    assert {(r.runner_id, r.model, r.effort) for r in runs} == {(runner, HAIKU, None)}
    for kind, argv in argvs.items():
        assert _flag(argv, "--model") == HAIKU, kind
        assert "--effort" not in argv, kind
    got = {kind: _normalised(argv, str(tmp_path)) for kind, argv in argvs.items()}
    assert got == BASELINE
