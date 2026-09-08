"""The gate for `scripts/sync_skills.py`.

`.claude/skills/` is the source of truth; Kimi and Codex read copies of it. The copies are
untracked, so nothing in review ever shows they have gone stale -- and they had, silently, since
`a38caee`: five skills differed and `daily-review` was absent from both trees.

This test is the ratchet. It is deliberately **skip-when-absent**: both destinations are
machine-local and neither exists on a CI runner, so asserting on them unconditionally would just
be a permanently red build. It gates the machines that actually have the trees, which are the
machines where the trees can rot.
"""

from __future__ import annotations

import fnmatch
import hashlib
import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync_skills.py"


def _load_sync_module():
    """Import `scripts/sync_skills.py` by path -- `scripts/` is not a package.

    The test reads the script's own `SOURCE`, `IGNORED`, `find_skills` and `destinations` rather
    than restating them, so the gate cannot drift away from the thing it gates.
    """
    spec = importlib.util.spec_from_file_location("sync_skills", SYNC_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_skills = _load_sync_module()


def _fingerprint(root: Path, ignored: tuple[str, ...]) -> dict[str, str]:
    """Map every non-ignored file under `root` to a digest, keyed by POSIX-style relative path."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not any(fnmatch.fnmatch(d, p) for p in ignored)]
        for name in filenames:
            if any(fnmatch.fnmatch(name, p) for p in ignored):
                continue
            path = Path(dirpath) / name
            key = path.relative_to(root).as_posix()
            out[key] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


@pytest.mark.parametrize(
    ("label", "dest"), sync_skills.destinations(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_mirrored_skill_trees_match_the_source(label: str, dest: Path) -> None:
    if not dest.is_dir():
        pytest.skip(f"{label} tree not installed on this machine ({dest})")

    ignored = tuple(sync_skills.IGNORED)
    stale: list[str] = []
    for skill in sync_skills.find_skills(sync_skills.SOURCE, include_generated=False):
        mirror = dest / skill.name
        if not mirror.is_dir():
            stale.append(f"{skill.name}: absent from {label}")
            continue
        source_files = _fingerprint(skill, ignored)
        mirror_files = _fingerprint(mirror, ignored)
        for rel in sorted(set(source_files) | set(mirror_files)):
            if source_files.get(rel) != mirror_files.get(rel):
                stale.append(f"{skill.name}/{rel}")

    assert not stale, (
        f"{label} is stale against .claude/skills/ -- run `py -3.11 scripts/sync_skills.py`.\n"
        + "\n".join(f"  {entry}" for entry in stale)
    )
