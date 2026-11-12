"""Which tracked files in a project's checkout hold exactly what the Hub last wrote (F1086, F1167).

The Hub writes tracked files into the project's main checkout as it works: `spec/index.json`, the
journey, document files, and the knowledge vault's `knowledge/` records. Left uncommitted, they made
every landing refuse the checkout as dirty, for work that was the Hub's own. F515 exempted document
files through `SpecDocument.content_digest`; this ledger covers every other file the Hub writes, by
recording the digest of each write, or `None` for a removal.

A file counts as the Hub's only while it still holds that write byte for byte (or, for a removal,
is still absent): an operator's hand edit changes the hash and counts as theirs. Exempting such a
file is safe for F515's reason: a merge that would overwrite it is refused by git and recorded.

The ledger lives at `.agentweave/hub-writes.json`, which is never tracked. Losing an update to it
(a crash between a write and its record, two processes racing) only makes a file count as dirty,
which is the safe direction.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import secrets
import threading
from pathlib import Path
from typing import Dict, Optional, Set

LEDGER = Path(".agentweave") / "hub-writes.json"

_locks: Dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(root: Path) -> threading.Lock:
    key = os.path.normcase(str(root))
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(root: Path) -> Dict[str, Optional[str]]:
    try:
        raw = json.loads((root / LEDGER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        k: v for k, v in raw.items() if isinstance(k, str) and (v is None or isinstance(v, str))
    }


def record(root: Path, relative: str | Path, data: Optional[bytes]) -> None:
    """Record that the Hub has just written *data* to *relative* (`None`: removed it).

    Never raises: a record that cannot be kept leaves the file counting as dirty.
    """
    try:
        root = Path(root)
        key = Path(relative).as_posix()
        value = None if data is None else _digest(data)
        with _lock(root):
            entries = _load(root)
            if key in entries and entries[key] == value:
                return
            entries[key] = value
            ledger = root / LEDGER
            ledger.parent.mkdir(parents=True, exist_ok=True)
            temporary = ledger.with_name(f".{ledger.name}.{secrets.token_hex(4)}.tmp")
            try:
                temporary.write_text(
                    json.dumps(entries, indent=0, sort_keys=True), encoding="utf-8", newline="\n"
                )
                os.replace(temporary, ledger)
            except OSError:
                with contextlib.suppress(OSError):
                    temporary.unlink()
    except Exception:  # noqa: BLE001 - see the docstring
        return


def record_file(root: Path, relative: str | Path) -> None:
    """Record the file at *relative* as it now is on disk: what the Hub has just written there."""
    try:
        data: Optional[bytes] = (Path(root) / relative).read_bytes()
    except FileNotFoundError:
        data = None
    except OSError:
        return
    record(root, relative, data)


def still_written(root: Path) -> Set[str]:
    """The recorded paths (`/`-separated, relative to *root*) that still hold the Hub's write."""
    root = Path(root)
    written: Set[str] = set()
    for key, value in _load(root).items():
        path = root / key
        try:
            data: Optional[bytes] = path.read_bytes()
        except FileNotFoundError:
            data = None
        except OSError:
            continue
        if (None if data is None else _digest(data)) == value:
            written.add(key)
    return written
