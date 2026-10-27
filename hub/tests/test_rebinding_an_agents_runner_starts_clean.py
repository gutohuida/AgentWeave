"""Rebinding an agent's runner starts clean (F1023, F1024; slice J of the October-25 roadmap).

An agent moved between Claude and Copilot kept the conversation's provider session and its stored
model, so Copilot was asked to load a Claude session and run Claude's `haiku`, and after the rebind
back Claude failed the operator's turn twice on Copilot's session id before the queue gave up.

Every test enters through `PATCH /agents/{name}` (the rebind) and `POST /agent/trigger`, never the
executor, with the CLIs replaced by stubs that behave the way the real ones do where it matters:
the stub `claude` refuses `--resume` of a session it never created (`No conversation found with
session ID`), the stub Copilot answers a session it never created with `on_session_missing` (its
-32002 rescue), and each reports the model it ran on (a Copilot told `haiku` runs its default,
`claude-sonnet-5`), so a fix that passes only because a stub is more forgiving than the CLI cannot
pass here.

Also here: the ratchet that keeps `conversations.provider_session_id` from being assigned anywhere
but the one helper that records the session's CLI beside it.
"""

from __future__ import annotations

import ast
import asyncio
import json
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

import hub
from hub import model_catalog
from hub.conversations import get_conversation_by_id
from hub.copilot_acp import TurnOutcome
from hub.db.engine import async_session_factory
from hub.db.models import AgentOutput, Conversation, EventLog, InboundQueueEntry, Run, TurnUsage
from hub.runner_events import AccountingSample, text_event

from ._background_runs import await_background_runs

PROJECT = "/api/v1/projects/proj-test"
CROSSING = "runner.session_not_carried"
WITHHELD = "runner.model_withheld"


@pytest.fixture(autouse=True)
def _copilot_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    exe = tmp_path / "copilot.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("hub.copilot_probe.resolve_copilot_executable", lambda override: exe)
    return tmp_path


# ---------------------------------------------------------------------------
# The stub CLIs
# ---------------------------------------------------------------------------

#: What each stub Claude model name reports when asked for it by alias.
_CLAUDE_REPORTS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5"}


class _Claude:
    """A stub `claude`, spawned through `PtySession.spawn`."""

    def __init__(self) -> None:
        self.known: set = set()
        self.argvs: list = []
        self.count = 0

    def _result(self, session_id: str, model: str) -> str:
        return json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": session_id,
                "num_turns": 1,
                "total_cost_usd": 0.001,
                "usage": {"input_tokens": 3, "output_tokens": 5},
                "modelUsage": {
                    model: {
                        "inputTokens": 3,
                        "outputTokens": 5,
                        "cacheReadInputTokens": 0,
                        "cacheCreationInputTokens": 0,
                        "contextWindow": 1000000,
                        "costUSD": 0.001,
                    }
                },
            }
        )

    def spawn(self, *args, **kwargs):
        argv = list(args[0])
        self.argvs.append(argv)
        resume = argv[argv.index("--resume") + 1] if "--resume" in argv else None
        asked = argv[argv.index("--model") + 1] if "--model" in argv else None
        if resume is not None and resume not in self.known:
            lines = [
                json.dumps(
                    {
                        "type": "result",
                        "subtype": "error_during_execution",
                        "is_error": True,
                        "errors": [f"No conversation found with session ID: {resume}"],
                    }
                )
            ]
            code = 1
        else:
            if resume is None:
                self.count += 1
            session_id = resume or f"claude-sess-{self.count}"
            self.known.add(session_id)
            lines = [self._result(session_id, _CLAUDE_REPORTS.get(asked or "sonnet", asked))]
            code = 0
        session = MagicMock()
        session.pid = 4242
        remaining = iter([*lines, ""])
        session.read.side_effect = lambda *a, **k: next(remaining, "")
        session.wait.return_value = code
        return session


class _Codex:
    """A stub `codex exec`, spawned through `PipeSession.spawn`."""

    def __init__(self) -> None:
        self.argvs: list = []

    def spawn(self, *args, **kwargs):
        self.argvs.append(list(args[0]))
        lines = [
            '{"type":"thread.started","thread_id":"thread-codex-1"}\n',
            '{"type":"item.completed","item":{"id":"i1","type":"agent_message","text":"ok"}}\n',
            '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n',
        ]
        session = MagicMock()
        session.pid = 4243
        remaining = iter([*lines, ""])
        session.read.side_effect = lambda *a, **k: next(remaining, "")
        session.wait.return_value = 0
        return session


class _Copilot:
    """A stub Copilot over ACP: `copilot_acp.run_turn`, driving the executor's callbacks."""

    def __init__(self) -> None:
        self.known: set = set()
        self.count = 0
        self.fake = AsyncMock(side_effect=self._run)

    async def _run(self, **kwargs):
        resume = kwargs["resume_session_id"]
        if resume is not None and resume not in self.known:
            # Copilot's -32002: the saved session names nothing it has.
            await kwargs["on_session_missing"](resume)
            resume = None
        if resume is None:
            self.count += 1
        session_id = resume or f"cop-sess-{self.count}"
        self.known.add(session_id)
        await kwargs["on_session"](session_id)
        await kwargs["on_event"](text_event("hello from copilot"))
        asked = kwargs["model"]
        declared = model_catalog.get_provider("copilot").model(asked) if asked else None
        # A model Copilot does not offer is not an error to it: it runs its plan default.
        ran = asked if declared is not None and asked != "auto" else "claude-sonnet-5"
        await kwargs["on_accounting"](
            AccountingSample(
                source="copilot", model=ran, input_tokens=3, output_tokens=5, total_tokens=8
            )
        )
        return TurnOutcome(session_id=session_id, status="completed")

    @property
    def calls(self) -> list:
        return [call.kwargs for call in self.fake.call_args_list]


class _Drive:
    """One test's operator: agents, rebinding, and turns with every CLI stubbed."""

    def __init__(self, app, headers) -> None:
        self.app = app
        self.headers = headers
        self.claude = _Claude()
        self.codex = _Codex()
        self.copilot = _Copilot()

    def _stubs(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch("hub.api.v1.agent_trigger.PtySession.spawn", self.claude.spawn))
        stack.enter_context(patch("hub.api.v1.agent_trigger.PipeSession.spawn", self.codex.spawn))
        stack.enter_context(patch("hub.copilot_acp.run_turn", self.copilot.fake))
        stack.enter_context(
            patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/cli")
        )
        return stack

    async def agent(self, name: str) -> None:
        sync = await self.app.post(
            f"{PROJECT}/session/sync",
            json={"data": {"agents": {name: {"runner": "claude"}}}},
            headers=self.headers,
        )
        assert sync.status_code == 200, sync.text

    async def runner(self, name: str, cli: str, *, model=None, flags=None) -> str:
        payload = {"name": name, "cli": cli}
        if model:
            payload["model"] = model
        if flags:
            payload["flags"] = flags
        created = await self.app.post(f"{PROJECT}/runners", json=payload, headers=self.headers)
        assert created.status_code == 201, created.text
        return created.json()["id"]

    async def bind(self, agent: str, runner_id: str) -> None:
        bound = await self.app.patch(
            f"{PROJECT}/agents/{agent}", json={"runner_id": runner_id}, headers=self.headers
        )
        assert bound.status_code == 200, bound.text

    async def send(self, agent: str, conversation_id=None, message="hi", overrides=None) -> dict:
        body: dict = {"agent": agent, "message": message}
        if conversation_id is not None:
            body["conversation_id"] = conversation_id
        if overrides is not None:
            body["overrides"] = overrides
        with self._stubs():
            response = await self.app.post(
                f"{PROJECT}/agent/trigger", json=body, headers=self.headers
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "running", response.text
            await asyncio.wait_for(await_background_runs(), timeout=60)
        return response.json()

    async def message(self, recipient: str, content="hi") -> None:
        """The operator's message opening a new thread: no conversation named, so the Hub opens
        one and copies the agent's latest stored overrides into it."""
        with self._stubs():
            response = await self.app.post(
                f"{PROJECT}/messages",
                json={"to": recipient, "content": content, "start_new_thread": True},
                headers=self.headers,
            )
            assert response.status_code == 201, response.text
            await asyncio.wait_for(await_background_runs(), timeout=60)


@pytest.fixture
def drive(app, auth_headers):
    return _Drive(app, auth_headers)


async def _conversation(conversation_id: str) -> Conversation:
    async with async_session_factory() as db:
        conversation = await get_conversation_by_id(db, conversation_id)
    assert conversation is not None
    return conversation


async def _runs(conversation_id: str) -> list:
    async with async_session_factory() as db:
        return list(
            (
                await db.execute(
                    select(Run)
                    .where(Run.conversation_id == conversation_id)
                    .order_by(Run.started_at, Run.id)
                )
            )
            .scalars()
            .all()
        )


async def _diagnostics(conversation_id: str, code: str | None = None) -> list:
    async with async_session_factory() as db:
        rows = list(
            (
                await db.execute(
                    select(AgentOutput)
                    .where(
                        AgentOutput.conversation_id == conversation_id,
                        AgentOutput.kind == "diagnostic",
                    )
                    .order_by(AgentOutput.timestamp, AgentOutput.sequence)
                )
            )
            .scalars()
            .all()
        )
    return [r for r in rows if code is None or (r.payload or {}).get("code") == code]


async def _usage(run_id: str) -> TurnUsage:
    async with async_session_factory() as db:
        return (await db.execute(select(TurnUsage).where(TurnUsage.run_id == run_id))).scalar_one()


async def _run_started(run_id: str) -> dict:
    async with async_session_factory() as db:
        rows = (
            (await db.execute(select(EventLog).where(EventLog.event_type == "run_started")))
            .scalars()
            .all()
        )
    (event,) = [r for r in rows if (r.data or {}).get("run_id") == run_id]
    return event.data


async def _claude_then_copilot(drive: _Drive, agent: str = "a1", *, claude_model=None, **send):
    """The agent's first turn on Claude, then it is rebound to Copilot and sent one message in
    the same conversation. Returns (conversation id, the crossing turn's response, the runners)."""
    await drive.agent(agent)
    claude_runner = await drive.runner(f"{agent}-claude", "claude", model=claude_model)
    copilot_runner = await drive.runner(
        f"{agent}-copilot", "copilot", model=send.pop("copilot_model", None)
    )
    await drive.bind(agent, claude_runner)
    first = await drive.send(agent, overrides=send.pop("first_overrides", None))
    conversation_id = first["conversation_id"]
    assert (await _conversation(conversation_id)).provider_session_id == "claude-sess-1"
    await drive.bind(agent, copilot_runner)
    crossing = await drive.send(agent, conversation_id, **send)
    return conversation_id, crossing, (claude_runner, copilot_runner)


# ---------------------------------------------------------------------------
# a-session-is-resumed-only-by-its-cli
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_to_copilot_loads_no_claude_session(drive):
    conversation_id, crossing, _ = await _claude_then_copilot(drive)

    assert len(drive.copilot.calls) == 1
    assert drive.copilot.calls[0]["resume_session_id"] is None
    assert crossing["provider_session_id"] is None


@pytest.mark.asyncio
async def test_copilot_to_claude_carries_no_resume(drive):
    conversation_id, _, (claude_runner, _) = await _claude_then_copilot(drive)
    assert (await _conversation(conversation_id)).provider_session_id == "cop-sess-1"
    before = len(drive.claude.argvs)

    await drive.bind("a1", claude_runner)
    back = await drive.send("a1", conversation_id)

    spawned = drive.claude.argvs[before:]
    assert spawned, "the Claude turn after the rebind back never spawned"
    assert "--resume" not in spawned[0], spawned[0]
    runs = await _runs(conversation_id)
    assert runs[-1].id == back["run_id"] and runs[-1].status == "completed"


@pytest.mark.asyncio
async def test_codex_carries_no_foreign_resume(drive):
    await drive.agent("a1")
    claude_runner = await drive.runner("a1-claude", "claude")
    codex_runner = await drive.runner("a1-codex", "codex", flags=["--no-app-server"])
    await drive.bind("a1", claude_runner)
    first = await drive.send("a1")
    conversation_id = first["conversation_id"]
    assert (await _conversation(conversation_id)).provider_session_id == "claude-sess-1"

    await drive.bind("a1", codex_runner)
    await drive.send("a1", conversation_id)

    assert len(drive.codex.argvs) == 1
    assert "resume" not in drive.codex.argvs[0], drive.codex.argvs[0]
    assert "claude-sess-1" not in drive.codex.argvs[0]


# ---------------------------------------------------------------------------
# the-new-session-becomes-the-conversations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_session_binds_and_resumes(drive):
    conversation_id, crossing, _ = await _claude_then_copilot(drive)

    conversation = await _conversation(conversation_id)
    assert conversation.provider_session_id == "cop-sess-1"
    assert conversation.provider_session_cli == "copilot"
    (run,) = [r for r in await _runs(conversation_id) if r.id == crossing["run_id"]]
    assert run.status == "completed"
    assert not run.error or "binding conflict" not in run.error
    async with async_session_factory() as db:
        conflicts = (
            (
                await db.execute(
                    select(EventLog).where(EventLog.event_type == "conversation_binding_conflict")
                )
            )
            .scalars()
            .all()
        )
    assert conflicts == []

    await drive.send("a1", conversation_id)
    assert drive.copilot.calls[-1]["resume_session_id"] == "cop-sess-1"


# ---------------------------------------------------------------------------
# a-same-cli-session-is-kept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_cli_rebind_resumes(drive):
    await drive.agent("a1")
    first_runner = await drive.runner("a1-sonnet", "claude", model="sonnet")
    second_runner = await drive.runner("a1-haiku", "claude", model="haiku")
    await drive.bind("a1", first_runner)
    first = await drive.send("a1")
    conversation_id = first["conversation_id"]
    before = len(drive.claude.argvs)

    await drive.bind("a1", second_runner)
    await drive.send("a1", conversation_id)

    argv = drive.claude.argvs[before]
    assert argv[argv.index("--resume") + 1] == "claude-sess-1"
    assert argv[argv.index("--model") + 1] == "haiku"
    assert await _diagnostics(conversation_id, CROSSING) == []


@pytest.mark.asyncio
async def test_unknown_cli_resumes(drive):
    """A session whose CLI nobody recorded is resumed as before: the queue's give-up and Copilot's
    own rescue stay as the backstop."""
    await drive.agent("a1")
    copilot_runner = await drive.runner("a1-copilot", "copilot")
    await drive.bind("a1", copilot_runner)
    drive.copilot.known.add("typed-session-1")
    async with async_session_factory() as db:
        db.add(
            Conversation(
                id="conv-unknown-cli",
                project_id="proj-test",
                agent="a1",
                lifecycle="open",
                origin="operator",
                title="unknown cli",
                lineage_id="conv-unknown-cli",
                provider_session_id="typed-session-1",
            )
        )
        await db.commit()

    await drive.send("a1", "conv-unknown-cli")

    assert drive.copilot.calls[0]["resume_session_id"] == "typed-session-1"
    assert await _diagnostics("conv-unknown-cli", CROSSING) == []


# ---------------------------------------------------------------------------
# the-crossing-is-said
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crossing_notice_recorded_and_prompted(drive):
    conversation_id, crossing, _ = await _claude_then_copilot(drive)

    (notice,) = await _diagnostics(conversation_id, CROSSING)
    assert notice.run_id == crossing["run_id"]
    assert (notice.payload or {})["severity"] == "info"
    for word in ("a1", "claude", "copilot"):
        assert word in notice.content, notice.content
    # Before anything the runner emitted in that run.
    async with async_session_factory() as db:
        sequences = [
            row.sequence
            for row in (
                await db.execute(
                    select(AgentOutput).where(AgentOutput.run_id == crossing["run_id"])
                )
            )
            .scalars()
            .all()
            if row.id != notice.id
        ]
    assert sequences and notice.sequence < min(sequences)
    # And the agent is told the same sentence at the head of its prompt.
    assert drive.copilot.calls[0]["prompt"].startswith(notice.content)

    await drive.send("a1", conversation_id)
    assert len(await _diagnostics(conversation_id, CROSSING)) == 1
    assert notice.content not in drive.copilot.calls[1]["prompt"]


# ---------------------------------------------------------------------------
# a-foreign-model-is-withheld, a-withheld-model-is-said, the-recorded-model-is-what-ran
# ---------------------------------------------------------------------------


async def _haiku_crossing(drive: _Drive):
    return await _claude_then_copilot(
        drive,
        claude_model="haiku",
        copilot_model="claude-haiku-4.5",
        first_overrides={"model": "haiku"},
        # The composer sends the stored overrides back with every message.
        overrides={"model": "haiku"},
    )


@pytest.mark.asyncio
async def test_haiku_not_sent_to_copilot(drive):
    conversation_id, _, (claude_runner, _) = await _haiku_crossing(drive)

    assert drive.copilot.calls[0]["model"] == "claude-haiku-4.5"
    assert (await _conversation(conversation_id)).runtime_overrides == {"model": "haiku"}

    await drive.bind("a1", claude_runner)
    before = len(drive.claude.argvs)
    await drive.send("a1", conversation_id)
    argv = drive.claude.argvs[before]
    assert argv[argv.index("--model") + 1] == "haiku"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored", ["claude-sonnet-5", "a-model-no-cli-declares"], ids=["shared", "retired"]
)
async def test_shared_and_retired_models_applied(drive, stored):
    await drive.agent("a1")
    copilot_runner = await drive.runner("a1-copilot", "copilot", model="claude-haiku-4.5")
    await drive.bind("a1", copilot_runner)
    async with async_session_factory() as db:
        db.add(
            Conversation(
                id="conv-stored-model",
                project_id="proj-test",
                agent="a1",
                lifecycle="open",
                origin="operator",
                title="stored model",
                lineage_id="conv-stored-model",
                runtime_overrides={"model": stored},
            )
        )
        await db.commit()

    await drive.send("a1", "conv-stored-model")

    assert drive.copilot.calls[0]["model"] == stored
    assert await _diagnostics("conv-stored-model", WITHHELD) == []


@pytest.mark.asyncio
async def test_inherited_haiku_withheld_in_a_job(drive):
    """A message opening a new thread copies the agent's latest stored overrides into it, with no
    rebind in sight at the conversation: the launch still withholds what Copilot does not offer."""
    await drive.agent("a1")
    claude_runner = await drive.runner("a1-claude", "claude", model="haiku")
    copilot_runner = await drive.runner("a1-copilot", "copilot", model="claude-haiku-4.5")
    await drive.bind("a1", claude_runner)
    first = await drive.send("a1", overrides={"model": "haiku"})
    await drive.bind("a1", copilot_runner)

    await drive.message("a1")

    assert len(drive.copilot.calls) == 1
    assert drive.copilot.calls[0]["model"] == "claude-haiku-4.5"
    async with async_session_factory() as db:
        inherited = (
            (
                await db.execute(
                    select(Conversation).where(
                        Conversation.agent == "a1", Conversation.id != first["conversation_id"]
                    )
                )
            )
            .scalars()
            .one()
        )
    assert inherited.runtime_overrides == {"model": "haiku"}
    assert len(await _diagnostics(inherited.id, WITHHELD)) == 1


@pytest.mark.asyncio
async def test_withheld_said_once(drive):
    conversation_id, _, _ = await _haiku_crossing(drive)
    await drive.send("a1", conversation_id, overrides={"model": "haiku"})

    (said,) = await _diagnostics(conversation_id, WITHHELD)
    assert (said.payload or {})["severity"] == "info"
    for word in ("haiku", "copilot", "claude-haiku-4.5"):
        assert word in said.content, said.content


@pytest.mark.asyncio
async def test_recorded_model_is_what_ran(drive):
    conversation_id, crossing, _ = await _haiku_crossing(drive)

    assert (await _run_started(crossing["run_id"]))["model"] == "claude-haiku-4.5"
    timeline = await drive.app.get(f"{PROJECT}/agents/a1/timeline", headers=drive.headers)
    assert timeline.status_code == 200, timeline.text
    summaries = [e["summary"] for e in timeline.json()["events"]]
    assert "Run started (copilot, claude-haiku-4.5)" in summaries, summaries
    assert (await _usage(crossing["run_id"])).model == "claude-haiku-4.5"


# ---------------------------------------------------------------------------
# rebind-and-back-runs-clean: the acceptance drive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rebind_and_back_runs_clean(drive):
    await drive.agent("a1")
    claude_runner = await drive.runner("a1-claude", "claude", model="haiku")
    copilot_runner = await drive.runner("a1-copilot", "copilot", model="claude-haiku-4.5")
    await drive.bind("a1", claude_runner)
    first = await drive.send("a1", message="one", overrides={"model": "haiku"})
    conversation_id = first["conversation_id"]

    await drive.bind("a1", copilot_runner)
    await drive.send("a1", conversation_id, message="two", overrides={"model": "haiku"})
    await drive.bind("a1", claude_runner)
    await drive.send("a1", conversation_id, message="three", overrides={"model": "haiku"})

    runs = await _runs(conversation_id)
    assert [r.status for r in runs] == ["completed"] * 3, [(r.id, r.status, r.error) for r in runs]
    async with async_session_factory() as db:
        entries = (
            (
                await db.execute(
                    select(InboundQueueEntry)
                    .where(InboundQueueEntry.conversation_id == conversation_id)
                    .order_by(InboundQueueEntry.sequence)
                )
            )
            .scalars()
            .all()
        )
    assert len(entries) == 3
    assert all(e.delivery_attempts in (0, 1) for e in entries), [
        e.delivery_attempts for e in entries
    ]
    assert [e.delivered_in_run_id for e in entries] == [r.id for r in runs]
    assert [(await _usage(r.id)).model for r in runs] == [
        "claude-haiku-5-5",
        "claude-haiku-4.5",
        "claude-haiku-5-5",
    ]
    # The conversation ends on the session its last turn created, which the next turn resumes.
    final = await _conversation(conversation_id)
    assert final.provider_session_cli == "claude"
    assert final.provider_session_id == runs[-1].session_id


# ---------------------------------------------------------------------------
# The model rule, alone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cli, stored, applies",
    [
        ("copilot", "haiku", False),  # Claude's alias: Copilot does not declare it
        ("copilot", "claude-haiku-4.5", True),
        ("copilot", "claude-sonnet-5", True),  # declared by both
        ("claude", "claude-sonnet-5", True),
        ("claude", "haiku", True),  # an alias is a declared choice
        (
            "claude",
            "claude-haiku-4.5",
            False,
        ),  # Copilot's id for it: Claude's is claude-haiku-4-5-*
        ("codex", "haiku", False),
        ("copilot", "a-model-no-cli-declares", True),  # retired: stays where it is stored
        ("claude", "a-model-no-cli-declares", True),
    ],
)
def test_a_stored_model_applies_when_the_cli_declares_it_or_none_does(cli, stored, applies):
    assert model_catalog.model_applies_to_cli(cli, stored) is applies


# ---------------------------------------------------------------------------
# The ratchet: one writer of conversations.provider_session_id
# ---------------------------------------------------------------------------

_GUARDED = {"provider_session_id", "provider_session_cli"}
_HUB_PACKAGE = Path(hub.__file__).parent


def _direct_assignments() -> list:
    found = []
    for path in sorted(_HUB_PACKAGE.rglob("*.py")):
        relative = path.relative_to(_HUB_PACKAGE).as_posix()
        if relative.startswith(("static/", "migrations/")):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        helper_lines: set = set()
        if relative == "conversations.py":
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "set_provider_session":
                    helper_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and node.attr in _GUARDED
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and node.lineno not in helper_lines
            ):
                found.append(f"{relative}:{node.lineno}")
    return found


def test_a_conversations_session_is_assigned_only_through_the_helper():
    """`provider_session_id` and the CLI that owns it are written together, by
    `conversations.set_provider_session`, or the CLI is left stale beside a session it does not
    belong to (the state F1023 died of)."""
    assert _direct_assignments() == []


def test_the_ratchet_sees_an_assignment(tmp_path):
    """It must be able to fail: the scan finds a store of the guarded name in source it is shown."""
    source = "def f(c):\n    c.provider_session_id = 'x'\n"
    stores = [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store)
    ]
    assert [n.attr for n in stores] == ["provider_session_id"]
