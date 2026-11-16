"""Under WSL a Windows copy of a runner's CLI is not the runner (F1195).

WSL appends the Windows PATH, so an npm-installed `codex` shim under `/mnt/c/...` can come before
the Linux binary. The Hub launched it and every turn failed at once with `node: not found` (exit
127). On Linux, candidates under `/mnt/<drive>/` are skipped and the search goes on; when only a
Windows copy exists the provider is not runnable and the reason says so. Linux is simulated: a
`shutil.which` that honours `path=` over a fixed set of installed files, no WSL needed.
"""

from __future__ import annotations

import os

import pytest

from hub import binaries, pty_runner
from hub.runner_adapters import base

SHIM = "/mnt/c/Users/u/AppData/Roaming/npm/codex"
LINUX = "/home/u/.local/bin/codex"


@pytest.fixture
def path_with(monkeypatch):
    """Install `files` and put `directories` on PATH, in that order, as Linux sees them."""

    def install(directories, files, *, linux=True):
        monkeypatch.setenv("PATH", os.pathsep.join(directories))

        def which(name, mode=os.F_OK | os.X_OK, path=None):
            for directory in (path if path is not None else os.environ["PATH"]).split(os.pathsep):
                candidate = f"{directory}/{name}"
                if candidate in files:
                    return candidate
            return None

        monkeypatch.setattr("shutil.which", which)
        monkeypatch.setattr(binaries, "_linux", lambda: linux)
        binaries.forget()

    return install


def test_the_linux_binary_is_chosen_over_an_earlier_windows_shim(path_with):
    path_with(["/mnt/c/Users/u/AppData/Roaming/npm", "/home/u/.local/bin"], {SHIM, LINUX})
    assert binaries.which("codex") == LINUX
    assert pty_runner.resolve_executable(["codex", "app-server"]) == [LINUX, "app-server"]
    assert base.probe_binary("codex", None, "codex") == ("codex", True, None)


def test_only_a_windows_copy_is_not_runnable_and_says_why(path_with):
    path_with(["/mnt/c/Users/u/AppData/Roaming/npm", "/usr/bin"], {SHIM})
    assert binaries.which("codex") is None
    cli, present, reason = base.probe_binary("codex", None, "codex")
    assert not present
    assert SHIM in reason and "Windows" in reason and "inside WSL" in reason
    with pytest.raises(FileNotFoundError):
        pty_runner.resolve_executable(["codex", "app-server"])


def test_a_drive_letter_is_one_letter_not_any_mnt_directory(path_with):
    path_with(["/mnt/data/bin"], {"/mnt/data/bin/codex"})
    assert binaries.which("codex") == "/mnt/data/bin/codex"


def test_off_linux_nothing_is_skipped(path_with):
    path_with(["/mnt/c/bin"], {"/mnt/c/bin/codex"}, linux=False)
    assert binaries.which("codex") == "/mnt/c/bin/codex"


def test_a_pinned_executable_is_respected_as_given(path_with, tmp_path):
    path_with(["/usr/bin"], set())
    pinned = tmp_path / "codex"
    pinned.write_text("#!/bin/sh\n")
    pinned.chmod(0o755)
    assert base.probe_binary("codex", str(pinned), "codex")[1] is True
    assert pty_runner.resolve_executable([str(pinned), "x"]) == [str(pinned), "x"]
