"""`ToolServerPin`: a turn's tool server is the copy the Hub read at start."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

import pytest

import hub as hub_package
from hub.tool_server import ToolServerPin

DAY = 86400


def _source(tmp_path: Path, content: bytes) -> Path:
    source = tmp_path / "src" / "mcp_server.py"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(content)
    return source


def test_path_serves_the_bytes_read_at_construction(tmp_path):
    source = _source(tmp_path, b"A")
    pin = ToolServerPin(source, root=tmp_path / "root")
    source.write_bytes(b"B")
    assert pin.path().read_bytes() == b"A"


def test_a_deleted_or_altered_target_is_restored(tmp_path):
    pin = ToolServerPin(_source(tmp_path, b"A"), root=tmp_path / "root")
    target = pin.path()
    target.unlink()
    assert pin.path().read_bytes() == b"A"
    target.write_bytes(b"C")
    assert pin.path().read_bytes() == b"A"


def test_different_sources_pin_to_different_paths_outside_the_repo(tmp_path):
    first = ToolServerPin(_source(tmp_path, b"A"), root=tmp_path / "root")
    second = ToolServerPin(_source(tmp_path, b"B"), root=tmp_path / "root")
    assert first.path() != second.path()
    repo = Path(hub_package.__file__).resolve().parents[1]
    for pin in (first, second):
        assert repo not in pin.path().resolve().parents


def test_default_root_is_under_home_not_temp(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    pin = ToolServerPin(_source(tmp_path, b"A"))
    target = pin.path()
    expected = tmp_path / "home" / ".agentweave" / "hub" / "tool-server" / pin.digest
    assert target == expected / "mcp_server.py"
    if os.name != "nt":
        assert (target.parents[1].stat().st_mode & 0o777) == 0o700


def test_prune_stale_removes_only_old_sibling_directories(tmp_path):
    root = tmp_path / "root"
    pin = ToolServerPin(_source(tmp_path, b"A"), root=root)
    target = pin.path()
    for name, age in (("old", 8), ("recent", 1)):
        server = root / name / "mcp_server.py"
        server.parent.mkdir(parents=True)
        server.write_bytes(b"x")
        stamp = time.time() - age * DAY
        os.utime(server, (stamp, stamp))
    stamp = time.time() - 8 * DAY
    os.utime(target, (stamp, stamp))
    removed = pin.prune_stale()
    assert removed == [root / "old"]
    assert (root / "recent").exists()
    assert target.parent.exists()


def test_path_refreshes_an_aged_target_and_prune_survives_oserror(tmp_path, monkeypatch):
    root = tmp_path / "root"
    pin = ToolServerPin(_source(tmp_path, b"A"), root=root)
    target = pin.path()
    stamp = time.time() - 8 * DAY
    os.utime(target, (stamp, stamp))
    pin.path()
    assert time.time() - target.stat().st_mtime < DAY
    old = root / "old" / "mcp_server.py"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"x")
    os.utime(old, (stamp, stamp))

    def boom(*args, **kwargs):
        raise OSError("busy")

    monkeypatch.setattr(shutil, "rmtree", boom)
    assert pin.prune_stale() == []


def test_an_unwritable_target_raises_instead_of_returning_the_source(tmp_path, monkeypatch):
    source = _source(tmp_path, b"A")
    pin = ToolServerPin(source, root=tmp_path / "root")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        pin.path()


# --- `a-run-reaches-the-hub-without-mcp` D5: the `aw-tool` launchers beside the pin ---------------


def _exe_dir_name() -> str:
    import hashlib
    import sys

    return hashlib.sha256(sys.executable.encode()).hexdigest()[:8]


def test_launchers_sit_under_the_digest_and_this_interpreter(tmp_path):
    import sys

    pin = ToolServerPin(_source(tmp_path, b"A"), root=tmp_path / "root")
    directory = pin.launcher_dir()
    server = pin.path()

    assert directory == tmp_path / "root" / pin.digest / "bin" / _exe_dir_name()
    cmd = (directory / "aw-tool.cmd").read_bytes()
    assert cmd == f'@"{sys.executable}" -I -S "{server}" --call %*\r\n'.encode()
    sh = (directory / "aw-tool").read_bytes().decode()
    assert sh.startswith("#!/bin/sh\n")
    assert "\r" not in sh
    exe = sys.executable.replace("\\", "/")
    assert f'exec "{exe}" -I -S "{str(server).replace(chr(92), "/")}" --call "$@"' in sh
    if os.name != "nt":
        assert os.access(directory / "aw-tool", os.X_OK)


def test_launchers_are_rewritten_when_altered_or_deleted(tmp_path):
    pin = ToolServerPin(_source(tmp_path, b"A"), root=tmp_path / "root")
    directory = pin.launcher_dir()
    good_cmd = (directory / "aw-tool.cmd").read_bytes()
    good_sh = (directory / "aw-tool").read_bytes()

    (directory / "aw-tool.cmd").write_bytes(b"@echo hijacked\r\n")
    (directory / "aw-tool").unlink()
    pin.launcher_dir()

    assert (directory / "aw-tool.cmd").read_bytes() == good_cmd
    assert (directory / "aw-tool").read_bytes() == good_sh


def test_prune_takes_a_stale_digests_launchers_with_it(tmp_path):
    root = tmp_path / "root"
    pin = ToolServerPin(_source(tmp_path, b"A"), root=root)
    old = ToolServerPin(_source(tmp_path, b"OLD"), root=root)
    old_launchers = old.launcher_dir()
    stamp = time.time() - 8 * DAY
    os.utime(old.path(), (stamp, stamp))
    pin.path()

    assert pin.prune_stale() == [root / old.digest]
    assert not old_launchers.exists()


def test_the_launcher_runs_the_pin_isolated(tmp_path):
    """Test 1.3's third case, through the launcher itself: `-I -S` means a `json.py` on
    `PYTHONPATH` cannot change what the auto-approved program runs (design D5, R3)."""
    import json
    import subprocess

    import hub.mcp_server as mcp_server

    pin = ToolServerPin(Path(mcp_server.__file__), root=tmp_path / "root")
    directory = pin.launcher_dir()
    poison = tmp_path / "poison"
    poison.mkdir()
    (poison / "json.py").write_text("raise RuntimeError('poisoned json')\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("AW_", "PYTHON"))}
    env["PYTHONPATH"] = str(poison)
    launcher = directory / ("aw-tool.cmd" if os.name == "nt" else "aw-tool")

    proc = subprocess.run(
        [str(launcher), "--list"], capture_output=True, text=True, env=env, cwd=tmp_path, timeout=60
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1])["ok"] is True
