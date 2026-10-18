"""What a runner reads from its workspace to configure itself, and a fingerprint of it (F675, F737).

An allow rule in a Claude settings file runs ahead of `--permission-prompt-tool` on the next turn,
and a hook runs with no permission check at all (research 2026-10-01 §1), so a write to one of
these paths is a write to the run's posture, not to its work. The workspace judge refuses the
writes it can read off a command's text (`mcp_server._runner_config`), but text cannot close the
class: `git apply`, a checkout, an archive extraction, a copy into the directory. So the Hub also
fingerprints these paths each time it launches a turn in a workspace
(`runner_config_guard.hold_if_changed`) and holds the turn for the operator when they changed.

Stdlib only. `mcp_server.py` is spawned standalone and restates `RUNNER_CONFIG_PATHS` as
`_RUNNER_CONFIG_PATHS`; `test_a_changed_runner_configuration_holds_the_next_turn.py` fails when the
two disagree, so the judge and the fingerprint always cover the same list.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Dict, List, Tuple

# A one-part entry or a directory covers everything beneath it. Instructions and skills
# (`CLAUDE.md`, `.claude/skills/`) are ordinary work, and are not here.
RUNNER_CONFIG_PATHS: Tuple[Tuple[str, ...], ...] = (
    (".claude", "settings.json"),
    (".claude", "settings.local.json"),
    (".claude", "hooks"),
    (".mcp.json",),
    (".codex",),
    (".github", "hooks"),
)

# A directory entry stops being enumerated past this many files; the count still changes the
# fingerprint, so a flood of new files is a change too.
_MAX_FILES_PER_ENTRY = 500
_CHUNK = 1 << 16

Fingerprint = Dict[str, str]


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(_CHUNK), b""):
                digest.update(chunk)
    except OSError as exc:
        # Unreadable is still a state: a file that appears and cannot be read is a change.
        return f"unreadable:{exc.errno}"
    return f"sha256:{digest.hexdigest()}"


def _key(parts: List[str]) -> str:
    return "/".join(os.path.normcase(part) for part in parts)


def fingerprint(root: str) -> Fingerprint:
    """`{relative path: content hash}` for every file under `root` that `RUNNER_CONFIG_PATHS`
    names. An absent path has no key. Total: anything that cannot be read is recorded as such
    rather than raised, because the caller decides whether a turn may start on this."""
    found: Fingerprint = {}
    for entry in RUNNER_CONFIG_PATHS:
        path = os.path.join(root, *entry)
        if os.path.isdir(path):
            count = 0
            for directory, subdirs, files in os.walk(path):
                subdirs.sort()
                for name in sorted(files):
                    count += 1
                    if count > _MAX_FILES_PER_ENTRY:
                        continue
                    full = os.path.join(directory, name)
                    relative = os.path.relpath(full, root).replace(os.sep, "/").split("/")
                    found[_key(relative)] = _hash_file(full)
            if count > _MAX_FILES_PER_ENTRY:
                found[_key([*entry, "..."])] = f"files:{count}"
        elif os.path.lexists(path):
            found[_key(list(entry))] = _hash_file(path)
    return found


def digest(print_: Fingerprint) -> str:
    """One stable value for a fingerprint, for comparing and for naming what was approved."""
    text = json.dumps(sorted(print_.items()), separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def changes(before: Fingerprint, after: Fingerprint) -> List[Tuple[str, str]]:
    """`[(path, "added" | "changed" | "removed")]`, sorted by path."""
    out: List[Tuple[str, str]] = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            out.append((path, "added"))
        elif path not in after:
            out.append((path, "removed"))
        elif before[path] != after[path]:
            out.append((path, "changed"))
    return out
