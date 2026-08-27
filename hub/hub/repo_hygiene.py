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

#: What the Hub's own commit would otherwise sweep into the operator's history.
#:
#: This list used to be "only what the Hub creates", on the reasoning that a Rust project does not
#: want `__pycache__` ignored because AgentWeave happened to be written in Python. That reasoning
#: holds for a `.gitignore` the operator owns. It does not hold here, because
#: **`worktrees.snapshot_worktree` runs `git add -A`** — the Hub is the writer. An agent that leaves
#: bytecode or an installed dependency tree in its checkout gets it committed onto its branch by the
#: Hub, on its behalf, without either of them choosing to; observed reaching a real project's
#: `master` as two `.pyc` files, and caught by a reviewing agent rather than by us.
#:
#: So the test for anything added here is **"would the Hub's own commit sweep it in"**, not "is it an
#: artefact of the project's ecosystem". That keeps the list short and gives a rule for extending it.
#:
#: The second group deliberately matches `requirement_evidence.SKIP_DIRECTORIES`, which is canonical
#: and already answers the same question for footprint hashing. The two cannot share code — this
#: module imports nothing from the Hub so that `worktrees` can call it — so they are kept in step by
#: hand, and a test asserts they agree.
#:
#: An operator who genuinely wants one of these tracked can still `git add -f` it once; from then on
#: it is tracked and these rules no longer apply to it.
EXCLUDE_PATTERNS = [
    ".agentweave/worktrees/",
    # A reviewing agent's detached checkout of the code under review. Same reason as the line above
    # and the same failure if it is missing: `snapshot_worktree` runs `git add -A`, so an agent that
    # both writes and reviews would commit an entire second checkout onto its own branch.
    ".agentweave/reviews/",
    # A task's own checkout (`2026-08-27-work-is-isolated-per-task`, design D6). Same reason and
    # same failure as the two lines above: an agent holding a task commits from one of these, and
    # `snapshot_worktree`'s `git add -A` would sweep every *other* task's checkout onto its branch.
    ".agentweave/tasks/",
    ".agentweave/logs/",
    ".agentweave/evidence/",
    # Rewritten from the canonical context on every single turn (`agent_trigger`), so it is pure
    # regenerated output. It was found committed onto a real project's main branch.
    ".agentweave/context/",
    "__pycache__/",
    "*.pyc",
    "node_modules/",
    ".venv/",
    "dist/",
    "build/",
]


def seed_repo_excludes(root: Path) -> None:
    """Ensure *root*'s repository ignores the Hub's own working files. Never fatal.

    Idempotent, and self-updating: if the block is already present but its patterns have changed,
    the block is rewritten in place. Seeding once at registration is not enough — a project
    registered before a pattern existed is exactly the project whose agents have been committing it.

    Ignore rules are a convenience. A project that cannot receive them is still a project, and
    failing a registration or a turn over one would be a bad trade.

    **This does not untrack anything.** Git ignores untracked paths only, so a file an earlier
    snapshot already committed stays committed and stays modifiable. Undoing that would mean the Hub
    rewriting the operator's index over a mess it made — a second unasked-for change on top of the
    first. A repository the Hub has already dirtied stays that way until its owner says otherwise.
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
