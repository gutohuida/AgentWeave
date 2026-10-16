"""`a-call-mode-turn-starts-with-an-empty-calls-directory` (F663, F664; decision fix-D6).

A call-mode turn in an isolated workspace finds `.agentweave/calls/` empty, so a new conversation
cannot collide with an earlier turn's arguments file; a shared workspace keeps its files; both
call-mode texts ask for a new name per call. The end-to-end check is
`scripts/drive/d1016_f663_calls_dir_clean.py` (a Haiku `Write` refused the earlier turn's file).
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import hub.api.v1.agent_trigger as agent_trigger
from hub import worktrees
from hub.api.v1.agents import _tool_surface_lines
from hub.launchability import access_path_notice

from ._background_runs import await_background_runs as _await_background_run
from .test_agent_trigger import _REAL_RESOLVE_AGENT_WORKSPACE, _fake_pty, _init_repo, _link_dir

NEW_NAME = "new file name for each call"
_RESULT = ['{"type":"result","subtype":"success","is_error":false,"session_id":"s"}\n']


def _calls(work: Path) -> Path:
    return work / ".agentweave" / "calls"


def _stock(work: Path, outside: Path) -> None:
    calls = _calls(work)
    calls.mkdir(parents=True)
    (calls / "1.json").write_text('{"title": "stale"}', encoding="utf-8")
    (calls / "old").mkdir()
    (calls / "old" / "2.json").write_text("{}", encoding="utf-8")
    outside.mkdir()
    (outside / "keep.json").write_text("{}", encoding="utf-8")
    _link_dir(calls / "linked", outside)


def test_an_isolated_turn_starts_with_nothing_from_an_earlier_one(tmp_path):
    work, outside = tmp_path / "work", tmp_path / "outside"
    _stock(work, outside)

    agent_trigger.prepare_calls_dir(str(work), empty=True)

    assert _calls(work).is_dir()
    assert list(_calls(work).iterdir()) == []
    # The link went as a link: what it pointed at is untouched.
    assert (outside / "keep.json").is_file()


def test_a_shared_workspace_keeps_its_files(tmp_path):
    work, outside = tmp_path / "work", tmp_path / "outside"
    _stock(work, outside)

    agent_trigger.prepare_calls_dir(str(work), empty=False)

    assert sorted(p.name for p in _calls(work).iterdir()) == ["1.json", "linked", "old"]


def test_the_caller_must_say_whether_to_empty(tmp_path):
    with pytest.raises(TypeError):
        agent_trigger.prepare_calls_dir(str(tmp_path))  # type: ignore[call-arg]


def test_an_entry_that_cannot_be_removed_is_a_warning_not_a_refusal(tmp_path, caplog):
    work = tmp_path / "work"
    calls = _calls(work)
    calls.mkdir(parents=True)
    for name in ("held.json", "free.json"):
        (calls / name).write_text("{}", encoding="utf-8")
    real_unlink = os.unlink

    def unlink(path, *args, **kwargs):
        if str(path).endswith("held.json"):
            raise PermissionError(32, "in use", str(path))
        return real_unlink(path, *args, **kwargs)

    with caplog.at_level("WARNING"), patch("hub.api.v1.agent_trigger.os.unlink", unlink):
        agent_trigger.prepare_calls_dir(str(work), empty=True)

    assert sorted(p.name for p in calls.iterdir()) == ["held.json"]
    assert any("held.json" in record.getMessage() for record in caplog.records)


def test_both_call_mode_texts_ask_for_a_new_name_per_call():
    assert NEW_NAME in access_path_notice("shim")
    assert NEW_NAME in "\n".join(_tool_surface_lines(runner="claude", access_path="shim"))
    # The MCP form names no file at all.
    assert NEW_NAME not in access_path_notice("mcp")


async def _turn(app, auth_headers, agent):
    fake_spawn = _fake_pty(list(_RESULT))
    with patch("hub.api.v1.agent_trigger.PtySession.spawn", fake_spawn):  # noqa: SIM117
        with patch("hub.runner_adapters.base.shutil.which", return_value="/usr/bin/claude"):
            response = await app.post(
                "/api/v1/projects/proj-test/agent/trigger",
                json={"agent": agent, "message": "go"},
                headers=auth_headers,
            )
            assert response.status_code == 200, response.text
            await _await_background_run()
    return Path(fake_spawn.call_args.kwargs["cwd"])


@pytest.mark.asyncio
async def test_the_trigger_empties_an_agents_own_worktree_and_not_the_project_directory(
    app, auth_headers, bind_runner, bind_project_workspace, tmp_path, monkeypatch
):
    repo = _init_repo(tmp_path / "repo")
    await bind_project_workspace(repo)
    monkeypatch.setattr(worktrees, "resolve_agent_workspace", _REAL_RESOLVE_AGENT_WORKSPACE)
    sync = await app.post(
        "/api/v1/projects/proj-test/session/sync",
        json={
            "data": {
                "agents": {
                    "reader": {"runner": "claude", "read_only": True},
                    "writer": {"runner": "claude"},
                }
            }
        },
        headers=auth_headers,
    )
    assert sync.status_code == 200
    await bind_runner("reader", cli="claude")
    await bind_runner("writer", cli="claude")

    worktree = _REAL_RESOLVE_AGENT_WORKSPACE(repo, "writer", {"runner": "claude"})
    assert worktree != repo
    _calls(worktree).mkdir(parents=True, exist_ok=True)
    (_calls(worktree) / "1.json").write_text('{"title": "stale"}', encoding="utf-8")
    _calls(repo).mkdir(parents=True, exist_ok=True)
    (_calls(repo) / "1.json").write_text('{"title": "in flight"}', encoding="utf-8")

    assert await _turn(app, auth_headers, "writer") == worktree
    assert list(_calls(worktree).iterdir()) == []

    assert await _turn(app, auth_headers, "reader") == repo
    assert (_calls(repo) / "1.json").read_text(encoding="utf-8") == '{"title": "in flight"}'
