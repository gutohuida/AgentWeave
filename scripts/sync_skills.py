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
        shutil.copytree(skill, target)

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

    # Project-level: Kimi reads this; OpenCode reads it too (and .claude/skills directly).
    sync_to(skills, REPO_ROOT / ".agents" / "skills", "Kimi + OpenCode (project)", args.dry_run)

    # User-level: the only place Codex looks.
    codex_home = Path.home() / ".codex"
    if codex_home.is_dir():
        sync_to(skills, codex_home / "skills", "Codex (user-level)", args.dry_run)
    else:
        print(f"  -- Codex not detected ({codex_home} missing) -- skipped")

    print("\nDone. Start a new agent session to pick the skills up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
