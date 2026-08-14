"""What the Hub leaves in someone else's repository, and how it stays out of their history.

The Hub writes working files into a project it did not create: isolated worktrees, logs, captured
evidence, and the rendered turn context. Agents commit what they find. Without a rule telling git to
skip them, the first agent to run commits the Hub's own scaffolding and the operator inherits it in
their history having never chosen it.

**Why `.git/info/exclude` and not `.gitignore`.** The original seeding wrote a marked block into the
project's `.gitignore`, on the reasoning that the operator keeps one place to look. It could not
work, and two experiments say so plainly:

* An uncommitted root `.gitignore` **does not reach a linked worktree** — `git status` inside the
  worktree still reports `?? .agentweave/`. That is precisely where the damage happens, because a
  writing agent runs in its worktree and `snapshot_worktree` commits whatever is dirty there.
* `$GIT_COMMON_DIR/info/exclude` **is shared by every worktree**, so one write covers the primary
  checkout and every agent at once.

Making `.gitignore` work would have meant committing it — the Hub creating a commit in the
operator's repository, unasked, to fix a problem the Hub caused. `info/exclude` is repo-local, never
committed, and invisible in their diff, which is the right footprint for a tool's own artefacts.

This module deliberately imports nothing from the Hub. `worktrees` is dependency-free by design and
has to be able to call this without dragging in the database layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

#: Delimiters for the block this module owns. Everything outside them belongs to whoever wrote it and
#: is never reordered or removed. Having markers rather than blind appends is also what lets a later
#: release add a pattern and have it reach projects that were seeded by an earlier one.
EXCLUDE_BEGIN = "# AgentWeave — the Hub's own working files"
EXCLUDE_END = "# End AgentWeave"

#: Only what the Hub creates. Every entry is a directory this product puts in someone else's
#: repository; nothing about their language, their build, or their editor. A Rust project does not
#: want `__pycache__` ignored because AgentWeave happened to be written in Python.
EXCLUDE_PATTERNS = [
    ".agentweave/worktrees/",
    ".agentweave/logs/",
    ".agentweave/evidence/",
    # Rewritten from the canonical context on every single turn (`agent_trigger`), so it is pure
    # regenerated output. It was found committed onto a real project's main branch.
    ".agentweave/context/",
]


def seed_repo_excludes(root: Path) -> None:
    """Ensure *root*'s repository ignores the Hub's own working files. Never fatal.

    Idempotent, and self-updating: if the block is already present but its patterns have changed,
    the block is rewritten in place. Seeding once at registration is not enough — a project
    registered before a pattern existed is exactly the project whose agents have been committing it.

    Ignore rules are a convenience. A project that cannot receive them is still a project, and
    failing a registration or a turn over one would be a bad trade.
    """
    git_dir = root / ".git"
    if not git_dir.is_dir():
        # Either not a repository at all, or a linked worktree / submodule whose `.git` is a file.
        # In both cases this is not the place to write: the common directory is somewhere else, and
        # the primary checkout is where seeding is driven from.
        return

    block = "\n".join([EXCLUDE_BEGIN, *EXCLUDE_PATTERNS, EXCLUDE_END])
    info = git_dir / "info"
    target = info / "exclude"
    try:
        existing = target.read_text(encoding="utf-8") if target.is_file() else ""
        start = existing.find(EXCLUDE_BEGIN)
        end = existing.find(EXCLUDE_END)
        if start != -1 and end > start:
            updated = existing[:start] + block + existing[end + len(EXCLUDE_END) :]
            if updated == existing:
                return
        else:
            separator = "" if not existing or existing.endswith("\n") else "\n"
            updated = f"{existing}{separator}{block}\n"
        info.mkdir(parents=True, exist_ok=True)
        target.write_text(updated, encoding="utf-8")
    except OSError:
        logger.info("Could not seed ignore rules in %s; continuing.", root, exc_info=True)
