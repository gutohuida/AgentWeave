"""F682: a vault piece is up to 50,000 characters and Windows caps a command line at 32,767.

The Claude worker passed its prompt after `-p`, so the 50k piece failed `WinError 206` and its
facts were silently lost. The prompt now travels on stdin; these spawn a real process.
"""

from __future__ import annotations

import subprocess
import sys

from hub import distillation
from hub.conversation_titles import build_title_command
from hub.runner_adapters.one_shot import OneShotCommand, stdin_of
from hub.worker import _run_worker_process, build_worker_command

WINDOWS_COMMAND_LINE_CAP = 32_767
PIECE = "line of a long handbook\n" * (distillation.PIECE_CHARS // 24 + 1)


def test_a_claude_worker_prompt_as_long_as_a_vault_piece_stays_off_the_command_line():
    assert len(PIECE) >= distillation.PIECE_CHARS
    for cmd in (
        build_worker_command(cli="claude", model="claude-haiku-4-5-20251001", prompt=PIECE),
        build_worker_command(cli="claude", model=None, prompt=PIECE, reading=True),
        build_title_command(cli="claude", model=None, prompt=PIECE),
    ):
        assert cmd is not None
        assert len(subprocess.list2cmdline(cmd)) < WINDOWS_COMMAND_LINE_CAP
        assert cmd[-1] == "-p"
        assert stdin_of(cmd) == PIECE


def test_the_spawn_writes_the_whole_prompt_to_stdin_and_closes_it():
    # A real child process that reads stdin to end-of-file: a pipe left open would hang it.
    cmd = OneShotCommand(
        [sys.executable, "-c", "import sys; print(len(sys.stdin.read()))"], stdin=PIECE
    )
    spawn = _run_worker_process(cmd, None, 60)
    assert spawn.outcome == "ok", spawn.error
    assert spawn.stdout.strip() == str(len(PIECE))


def test_a_plain_argv_still_spawns_with_stdin_closed():
    spawn = _run_worker_process(
        [sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], None, 60
    )
    assert spawn.outcome == "ok", spawn.error
    assert spawn.stdout.strip() == "''"
