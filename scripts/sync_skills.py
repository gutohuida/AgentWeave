#!/usr/bin/env python3
"""Mirror this repo's hand-written dev skills out to the agents that can't read `.claude/skills/`.

`.claude/skills/` is the tracked source of truth. The other agents look elsewhere:

    Claude Code   .claude/skills/                      <- source, nothing to do
    OpenCode      .claude/skills/, .agents/skills/     <- already reads the source
    Kimi          .agents/skills/                      <- needs a copy
    Codex         ~/.codex/skills/ ONLY                <- needs a copy; it has no
                                                          project-level discovery at all

Codex is the reason this script exists rather than a `.gitignore` tweak: no arrangement of
files inside the repo can reach it, so a skill only gets there by being installed per-machine.

Usage:
    python scripts/sync_skills.py [--dry-run] [--include-generated]

The sync is **additive**. It overwrites the skills it owns and never deletes anything else at
the destination, so generated `aw-*` skills already sitting in `.agents/skills/` are left
alone. Re-run it after editing anything under `.claude/skills/`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / ".claude" / "skills"

# Kimi reads the project tree; OpenCode reads it too (and `.claude/skills/` directly).
KIMI_DEST = REPO_ROOT / ".agents" / "skills"
# The only place Codex looks. `~/.codex` existing is how we detect Codex is installed at all.
CODEX_HOME = Path.home() / ".codex"
CODEX_DEST = CODEX_HOME / "skills"

# Byte-compiled leftovers are not skill content. `e2e-loop` acquires a `__pycache__` the moment
# anything imports `e2e.py`, and copying it makes every destination differ from the source again
# the next time a `.pyc` is regenerated -- which would make the gate in tests/test_skill_sync.py
# flap rather than catch anything.
IGNORED = ("__pycache__", "*.pyc")


def destinations() -> list[tuple[str, Path]]:
    """Every tree this script mirrors into, as (label, path).

    `tests/test_skill_sync.py` reads this so the gate cannot drift from the sync. Both paths are
    untracked and machine-local -- neither exists on a CI runner, which is why the test skips a
    destination it cannot find rather than failing on it.
    """
    return [("Kimi + OpenCode (project)", KIMI_DEST), ("Codex (user-level)", CODEX_DEST)]


def find_skills(source: Path, include_generated: bool) -> list[Path]:
    """Return the skill directories to mirror, newest-convention first."""
    skills = sorted(d for d in source.iterdir() if d.is_dir() and (d / "SKILL.md").is_file())
    if include_generated:
        return skills
    # AGENTS.md: "no generated aw-* skills" at the repo root -- they are AgentWeave's product
    # surface, not this repo's dev tooling. Propagating them to Kimi is how Kimi ends up seeing
    # only the skills it is told never to invoke. Pass --include-generated to override.
    return [d for d in skills if not d.name.startswith("aw-")]


def sync_to(skills: list[Path], dest: Path, label: str, dry_run: bool) -> int:
    if dry_run:
        print(f"  [dry-run] {label} -> {dest}")
    else:
        dest.mkdir(parents=True, exist_ok=True)

    for skill in skills:
        target = dest / skill.name
        if dry_run:
            print(f"      would copy {skill.name}")
            continue
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(skill, target, ignore=shutil.ignore_patterns(*IGNORED))

    if not dry_run:
        print(f"  OK {label} -> {dest} ({len(skills)} skills)")
    return len(skills)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, change nothing")
    parser.add_argument(
        "--include-generated",
        action="store_true",
        help="also mirror aw-* skills (off by default; see AGENTS.md)",
    )
    args = parser.parse_args()

    if not SOURCE.is_dir():
        print(f"No source skills directory: {SOURCE}", file=sys.stderr)
        return 1

    skills = find_skills(SOURCE, args.include_generated)
    if not skills:
        print(f"No skills found in {SOURCE}", file=sys.stderr)
        return 1

    print(f"Syncing {len(skills)} skills from {SOURCE}:")
    for skill in skills:
        print(f"  - {skill.name}")
    print()

    for label, dest in destinations():
        if dest == CODEX_DEST and not CODEX_HOME.is_dir():
            print(f"  -- Codex not detected ({CODEX_HOME} missing) -- skipped")
            continue
        sync_to(skills, dest, label, args.dry_run)

    print("\nDone. Start a new agent session to pick the skills up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
