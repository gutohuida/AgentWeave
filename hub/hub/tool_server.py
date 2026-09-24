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
        try:
            if self._target.read_bytes() == self._bytes:
                os.utime(self._target)
                return self._target
        except FileNotFoundError:
            pass
        directory = self._target.parent
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != "nt":
            os.chmod(self._root, 0o700)
        temp = directory / f"{_SERVER_NAME}.{os.getpid()}.tmp"
        try:
            temp.write_bytes(self._bytes)
            os.replace(temp, self._target)
        finally:
            temp.unlink(missing_ok=True)
        return self._target

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
