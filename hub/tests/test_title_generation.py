"""Model-generated titles are an opt-in upgrade over truncation, and never more than that.

The spawn is faked throughout — these tests are about when it happens, what it may overwrite,
and what happens when it doesn't work. That a real `claude`/`codex` invocation prints a usable
title is a live check (tasks 11.9), not something a mock can establish.
"""

import pytest

import hub.conversation_titles as conversation_titles
from hub.conversation_titles import build_title_command, title_from_output
from hub.db.engine import async_session_factory
from hub.db.models import Conversation, Project

# ---------------------------------------------------------------------------
# The pure pieces
# ---------------------------------------------------------------------------


def test_claude_command_is_a_one_shot_prompt() -> None:
    cmd = build_title_command(cli="claude", model="claude-opus-5", prompt="P")
    assert cmd == ["claude", "--model", "claude-opus-5", "-p", "P"]
    # None of an agent turn's apparatus: no streaming JSON, no MCP server, no permission mode.
    assert "--output-format" not in cmd
    assert "--mcp-config" not in cmd
    assert "--permission-mode" not in cmd


def test_codex_command_is_a_one_shot_prompt() -> None:
    cmd = build_title_command(cli="codex", model=None, prompt="P")
    assert cmd == ["codex", "exec", "--skip-git-repo-check", "P"]


def test_an_unsupported_cli_builds_nothing() -> None:
    """Refused rather than guessed, the same line `runner_commands.build_command` holds."""
    assert build_title_command(cli="kimi", model=None, prompt="P") is None


def test_the_last_line_is_the_title() -> None:
    """Codex prints progress ahead of its answer; Claude prints only the answer."""
    assert title_from_output("thinking...\nreading files\nFix the checkout flake") == (
        "Fix the checkout flake"
    )


def test_quotes_and_a_trailing_period_are_stripped() -> None:
    assert title_from_output('"Fix the checkout flake."') == "Fix the checkout flake"


def test_empty_output_yields_no_title() -> None:
    assert title_from_output("") == ""
    assert title_from_output("   \n\n  ") == ""


def test_an_over_long_generated_title_is_still_truncated() -> None:
    """The model was asked for 8 words. The stored length is enforced regardless."""
    from hub.db.models import CONVERSATION_TITLE_MAX_LENGTH

    generated = " ".join(["word"] * 200)
    assert len(title_from_output(generated)) <= CONVERSATION_TITLE_MAX_LENGTH


# ---------------------------------------------------------------------------
# When it runs
# ---------------------------------------------------------------------------


async def _sync_agent(app, auth_headers, agent="offline"):
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {agent: {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200, sync.text


async def _conversation(
    app, auth_headers, bind_runner=None, message="Investigate the flaky checkout test"
):
    """Open a conversation, then bind the runner the titler will use.

    Order matters for speed, not correctness: `trigger_agent_directly` refuses to spawn an
    agent with no bound runner, so triggering first keeps the suite from launching a real
    `claude` that is not installed and waiting on it in teardown.
    """
    created = await app.post(
        "/api/v1/projects/proj-test/agent/trigger",
        json={"agent": "offline", "message": message},
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    if bind_runner is not None:
        await bind_runner("offline", cli="claude")
    return created.json()["conversation_id"]


async def _set_mode(mode: str, runner_id=None) -> None:
    async with async_session_factory() as session:
        project = await session.get(Project, "proj-test")
        project.conversation_title_mode = mode
        project.conversation_title_runner_id = runner_id
        await session.commit()


async def _title(conversation_id: str):
    async with async_session_factory() as session:
        conversation = await session.get(Conversation, conversation_id)
        return conversation.title, conversation.title_set_by_operator


def _fake_spawn(monkeypatch, output: str, calls=None):
    def _run(cmd, cwd):
        if calls is not None:
            calls.append(cmd)
        return output

    monkeypatch.setattr(conversation_titles, "_run_titler", _run)


@pytest.mark.asyncio
async def test_generation_is_off_by_default(app, auth_headers, bind_runner, monkeypatch) -> None:
    """A migration must not start spending the operator's tokens."""
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers, bind_runner)
    calls = []
    _fake_spawn(monkeypatch, "Generated title", calls)

    assert (
        await conversation_titles.generate_conversation_title(
            project_id="proj-test", conversation_id=conversation_id
        )
        is None
    )
    assert calls == [], "nothing may be spawned while the setting is off"
    assert (await _title(conversation_id))[0] == "Investigate the flaky checkout test"


@pytest.mark.asyncio
async def test_generation_replaces_the_truncated_title(
    app, auth_headers, bind_runner, monkeypatch
) -> None:
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers, bind_runner)
    await _set_mode("generate")
    calls = []
    _fake_spawn(monkeypatch, "Checkout flake investigation", calls)

    result = await conversation_titles.generate_conversation_title(
        project_id="proj-test", conversation_id=conversation_id
    )

    assert result == "Checkout flake investigation"
    assert (await _title(conversation_id)) == ("Checkout flake investigation", False)
    assert calls and calls[0][0] == "claude"


@pytest.mark.asyncio
async def test_an_operator_title_is_never_replaced(
    app, auth_headers, bind_runner, monkeypatch
) -> None:
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers, bind_runner)
    renamed = await app.patch(
        f"/api/v1/projects/proj-test/agent/offline/conversations/{conversation_id}",
        json={"title": "Mine"},
        headers=auth_headers,
    )
    assert renamed.status_code == 200, renamed.text
    await _set_mode("generate")
    calls = []
    _fake_spawn(monkeypatch, "Something the model preferred", calls)

    assert (
        await conversation_titles.generate_conversation_title(
            project_id="proj-test", conversation_id=conversation_id
        )
        is None
    )
    assert calls == [], "an operator's title is not even worth spawning for"
    assert (await _title(conversation_id)) == ("Mine", True)


@pytest.mark.asyncio
async def test_a_failed_spawn_leaves_the_truncated_title(
    app, auth_headers, bind_runner, monkeypatch
) -> None:
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers, bind_runner)
    await _set_mode("generate")
    _fake_spawn(monkeypatch, "")  # what `_run_titler` returns for a crash, non-zero exit, timeout

    assert (
        await conversation_titles.generate_conversation_title(
            project_id="proj-test", conversation_id=conversation_id
        )
        is None
    )
    assert (await _title(conversation_id))[0] == "Investigate the flaky checkout test"


def test_an_unsupported_cli_is_unreachable_today_and_still_guarded() -> None:
    """`ck_runners_cli` and the runner API both refuse anything but claude/codex, so the
    titler's own check cannot fire from a stored row. It is kept for the day a third CLI is
    wired in, and covered where it can be exercised: the command builder returns nothing."""
    assert "kimi" not in conversation_titles._SUPPORTED_CLIS
    assert build_title_command(cli="kimi", model=None, prompt="P") is None


@pytest.mark.asyncio
async def test_an_agent_with_no_runner_is_a_no_op(app, auth_headers, monkeypatch) -> None:
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={"data": {"agents": {"offline": {"runner": "manual"}}}},
        headers=auth_headers,
    )
    assert sync.status_code == 200
    conversation_id = await _conversation(app, auth_headers)
    await _set_mode("generate")
    calls = []
    _fake_spawn(monkeypatch, "Never used", calls)

    assert (
        await conversation_titles.generate_conversation_title(
            project_id="proj-test", conversation_id=conversation_id
        )
        is None
    )
    assert calls == []


@pytest.mark.asyncio
async def test_a_rename_during_generation_wins(app, auth_headers, bind_runner, monkeypatch) -> None:
    """The model thinks for seconds. The operator can rename inside that window."""
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers, bind_runner)
    await _set_mode("generate")

    def _run_and_rename(cmd, cwd):
        import asyncio

        async def _rename():
            async with async_session_factory() as session:
                conversation = await session.get(Conversation, conversation_id)
                conversation.title = "Mine"
                conversation.title_set_by_operator = True
                await session.commit()

        asyncio.run(_rename())
        return "Something the model preferred"

    monkeypatch.setattr(conversation_titles, "_run_titler", _run_and_rename)

    assert (
        await conversation_titles.generate_conversation_title(
            project_id="proj-test", conversation_id=conversation_id
        )
        is None
    )
    assert (await _title(conversation_id)) == ("Mine", True)


@pytest.mark.asyncio
async def test_titling_writes_no_run_row(app, auth_headers, bind_runner, monkeypatch) -> None:
    """A `Run` under the agent's name would make it look busy: `turn_scheduler.schedule_agent`
    and `trigger_agent_directly` both gate on a running run for that agent."""
    from sqlalchemy import select

    from hub.db.models import Run

    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers, bind_runner)
    await _set_mode("generate")
    _fake_spawn(monkeypatch, "Checkout flake investigation")

    async with async_session_factory() as session:
        before = len((await session.execute(select(Run.id))).scalars().all())

    await conversation_titles.generate_conversation_title(
        project_id="proj-test", conversation_id=conversation_id
    )

    async with async_session_factory() as session:
        after = len((await session.execute(select(Run.id))).scalars().all())
    assert after == before


@pytest.mark.asyncio
async def test_titling_adds_no_timeline_entry(app, auth_headers, bind_runner, monkeypatch) -> None:
    """The exchange with the titler is not part of the conversation it names."""
    await _sync_agent(app, auth_headers)
    conversation_id = await _conversation(app, auth_headers, bind_runner)
    await _set_mode("generate")
    _fake_spawn(monkeypatch, "Checkout flake investigation")

    before = await app.get(
        f"/api/v1/projects/proj-test/agent/offline/chat/{conversation_id}", headers=auth_headers
    )
    await conversation_titles.generate_conversation_title(
        project_id="proj-test", conversation_id=conversation_id
    )
    after = await app.get(
        f"/api/v1/projects/proj-test/agent/offline/chat/{conversation_id}", headers=auth_headers
    )

    assert len(after.json()["entries"]) == len(before.json()["entries"])


@pytest.mark.asyncio
async def test_the_wrapper_swallows_everything(app, auth_headers, monkeypatch) -> None:
    """`maybe_generate_title` runs on a completed run. It must never turn one into a failure."""

    async def _explode(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(conversation_titles, "generate_conversation_title", _explode)
    await conversation_titles.maybe_generate_title(
        project_id="proj-test", conversation_id="conv-anything"
    )
    await conversation_titles.maybe_generate_title(project_id="proj-test", conversation_id=None)


@pytest.mark.asyncio
async def test_the_setting_round_trips_through_the_operator_api(
    app, auth_headers, bind_runner
) -> None:
    await _sync_agent(app, auth_headers)
    # Safe to bind before anything else here: this test never triggers a run.
    await bind_runner("offline", cli="claude")
    runners = await app.get("/api/v1/projects/proj-test/runners", headers=auth_headers)
    runner_id = runners.json()[0]["id"]

    current = await app.get("/api/v1/projects/proj-test/settings", headers=auth_headers)
    assert current.status_code == 200, current.text
    assert current.json()["conversation_title_mode"] == "truncate"

    body = {
        **current.json(),
        "conversation_title_mode": "generate",
        "conversation_title_runner_id": runner_id,
    }
    updated = await app.put("/api/v1/projects/proj-test/settings", json=body, headers=auth_headers)
    assert updated.status_code == 200, updated.text

    reread = await app.get("/api/v1/projects/proj-test/settings", headers=auth_headers)
    assert reread.json()["conversation_title_mode"] == "generate"
    assert reread.json()["conversation_title_runner_id"] == runner_id


@pytest.mark.asyncio
async def test_a_runner_from_another_project_is_rejected(app, auth_headers) -> None:
    current = await app.get("/api/v1/projects/proj-test/settings", headers=auth_headers)
    body = {
        **current.json(),
        "conversation_title_mode": "generate",
        "conversation_title_runner_id": "runner-does-not-exist",
    }
    rejected = await app.put("/api/v1/projects/proj-test/settings", json=body, headers=auth_headers)
    assert rejected.status_code == 400
    assert "Unknown runner" in rejected.json()["detail"]
