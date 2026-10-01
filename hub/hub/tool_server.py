"""The tool server an agent's turn loads is the one this Hub loaded at start.

`mcp_server.py` is spawned by the runner CLI on every turn, and it imports nothing from its
own directory, so a byte-for-byte copy is the same program. `ToolServerPin` reads the source
once, when the Hub imports this module, and hands every turn a content-addressed copy under
the Hub user's home. An edit to the checkout's `mcp_server.py` reaches a Hub's agents on that
Hub's next restart, like every other Hub file. Design:
`openspec/changes/an-agents-tool-server-is-the-one-its-hub-loaded/design.md`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_SERVER_NAME = "mcp_server.py"


def pin_root() -> Path:
    """`~/.agentweave/hub/tool-server`, read at call time so a patched home is honoured."""
    return Path.home() / ".agentweave" / "hub" / "tool-server"


class ToolServerPin:
    def __init__(self, source: Path, root: Optional[Path] = None) -> None:
        self._bytes = source.read_bytes()
        self.digest = hashlib.sha256(self._bytes).hexdigest()[:16]
        self._root = root if root is not None else pin_root()
        self._target = self._root / self.digest / _SERVER_NAME

    def path(self) -> Path:
        """The verified pinned copy; rewritten if missing or altered. Raises `OSError`."""
        self._write_verified(self._target, self._bytes)
        if os.name != "nt":
            os.chmod(self._root, 0o700)
        return self._target

    def launcher_dir(self) -> Path:
        """The `aw-tool` launchers for this pin and this interpreter; verified like `path()`.

        `a-run-reaches-the-hub-without-mcp`, design D5. A run without the tool-protocol surface
        reaches the Hub by running this pin in call mode, and this directory goes first on every
        run's `PATH`. Two files: `aw-tool.cmd` (Windows, CRLF) and `aw-tool` (POSIX sh, which Git
        Bash on Windows runs too). Both embed the interpreter's path, so the directory is keyed by
        it as well as by the digest: two Hubs with the same server bytes and different Pythons
        must not rewrite each other's launcher. Both pass `-I -S`, so no `PYTHON*` variable and no
        site-packages `.pth` file can change what an auto-approved command runs; call mode needs
        only the stdlib. Pruned with the digest directory. Raises `OSError`.
        """
        server = self.path()
        exe = sys.executable
        directory = self._target.parent / "bin" / hashlib.sha256(exe.encode()).hexdigest()[:8]
        cmd = f'@"{exe}" -I -S "{server}" --call %*\r\n'
        posix_exe, posix_server = exe.replace("\\", "/"), str(server).replace("\\", "/")
        sh = f'#!/bin/sh\nexec "{posix_exe}" -I -S "{posix_server}" --call "$@"\n'
        self._write_verified(directory / "aw-tool.cmd", cmd.encode("utf-8"))
        self._write_verified(directory / "aw-tool", sh.encode("utf-8"), mode=0o700)
        return directory

    @staticmethod
    def _write_verified(target: Path, data: bytes, mode: Optional[int] = None) -> None:
        """Leave *target* alone if it holds *data* (touching it, so pruning sees it in use);
        otherwise write it atomically. Raises `OSError`."""
        try:
            if target.read_bytes() == data:
                os.utime(target)
                return
        except FileNotFoundError:
            pass
        directory = target.parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = directory / f"{target.name}.{os.getpid()}.tmp"
        try:
            temp.write_bytes(data)
            if mode is not None and os.name != "nt":
                os.chmod(temp, mode)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def prune_stale(self, max_age: timedelta = timedelta(days=7)) -> List[Path]:
        """Remove sibling digest directories untouched for `max_age`; never this pin's own."""
        removed: List[Path] = []
        cutoff = time.time() - max_age.total_seconds()
        try:
            siblings = [p for p in self._root.iterdir() if p.is_dir()]
        except OSError as exc:
            logger.warning("Could not list the tool-server pins under %s: %s", self._root, exc)
            return removed
        for directory in siblings:
            if directory == self._target.parent:
                continue
            try:
                if (directory / _SERVER_NAME).stat().st_mtime >= cutoff:
                    continue
                shutil.rmtree(directory)
                removed.append(directory)
            except OSError as exc:
                logger.warning("Could not prune the stale tool server %s: %s", directory, exc)
        return removed


PIN = ToolServerPin(Path(__file__).parent / _SERVER_NAME)


def pinned_server_path() -> Path:
    return PIN.path()
