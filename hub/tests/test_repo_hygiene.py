"""The rules the Hub writes into someone else's repository.

`test_evidence_footprint_root.py` covers seeding through registration and through workspace
resolution — the product paths. These are the unit-level properties of the writer itself: that it is
additive, idempotent, self-updating, and that git actually agrees with the result.

The last of those is the one that matters. An assertion that the file contains a pattern is an
assertion about a string; the defect this module was rewritten for passed exactly that kind of
assertion while the product was broken.
"""

import subprocess
from pathlib import Path

from hub import repo_hygiene, requirement_evidence


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=30)


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "master")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "user.name", "test")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")
    return path


def excludes(repo: Path) -> str:
    target = repo / ".git" / "info" / "exclude"
    return target.read_text(encoding="utf-8") if target.is_file() else ""


def test_seeding_writes_the_block(tmp_path):
    repo = init_repo(tmp_path / "repo")
    repo_hygiene.seed_repo_excludes(repo)

    written = excludes(repo)
    assert repo_hygiene.EXCLUDE_BEGIN in written
    assert repo_hygiene.EXCLUDE_END in written
    for pattern in repo_hygiene.EXCLUDE_PATTERNS:
        assert pattern in written


def test_git_agrees_about_the_hubs_own_files(tmp_path):
    """The claim is about `git status`, not about the contents of a file."""
    repo = init_repo(tmp_path / "repo")
    repo_hygiene.seed_repo_excludes(repo)

    for relative in (
        ".agentweave/worktrees/builder/x",
        ".agentweave/logs/events.jsonl",
        ".agentweave/evidence/e",
        ".agentweave/context/builder.md",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")

    assert git(repo, "status", "--porcelain").stdout.strip() == ""


def test_the_hubs_own_commit_does_not_sweep_in_build_artefacts(tmp_path):
    """`snapshot_worktree` runs `git add -A`, so whatever is lying there becomes the Hub's commit.

    Found live: two `__pycache__/*.pyc` files rode an agent's branch onto a real project's `master`,
    and the reviewing agent caught it rather than we did.
    """
    repo = init_repo(tmp_path / "repo")
    repo_hygiene.seed_repo_excludes(repo)

    for relative in (
        "__pycache__/late_fees.cpython-311.pyc",
        "stray.pyc",
        "node_modules/left-pad/index.js",
        ".venv/pyvenv.cfg",
        "dist/bundle.js",
        "build/output.o",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")

    assert git(repo, "status", "--porcelain").stdout.strip() == ""

    # And the thing the operator would actually do about it still works.
    git(repo, "add", "-f", "dist/bundle.js")
    assert "dist/bundle.js" in git(repo, "diff", "--cached", "--name-only").stdout


def test_the_artefact_patterns_agree_with_the_canonical_list(tmp_path):
    """`requirement_evidence.SKIP_DIRECTORIES` answers the same question for footprint hashing.

    The two cannot share code — this module imports nothing from the Hub, so `worktrees` can call it
    without pulling in the database layer — so they are kept in step by hand and asserted here.
    """
    directories = {
        pattern.rstrip("/")
        for pattern in repo_hygiene.EXCLUDE_PATTERNS
        if pattern.endswith("/") and not pattern.startswith(".agentweave/")
    }
    canonical = requirement_evidence.SKIP_DIRECTORIES - {".git", ".agentweave"}
    assert directories == canonical


def test_seeding_is_idempotent(tmp_path):
    repo = init_repo(tmp_path / "repo")
    repo_hygiene.seed_repo_excludes(repo)
    first = excludes(repo)
    repo_hygiene.seed_repo_excludes(repo)

    assert excludes(repo) == first
    assert excludes(repo).count(repo_hygiene.EXCLUDE_BEGIN) == 1


def test_a_changed_pattern_set_reaches_an_already_seeded_project(tmp_path, monkeypatch):
    """A blind "already seeded, skip" strands every project on the patterns it first received.

    Those are the projects with the problem: their agents have already been committing.
    """
    repo = init_repo(tmp_path / "repo")
    monkeypatch.setattr(repo_hygiene, "EXCLUDE_PATTERNS", [".agentweave/worktrees/"])
    repo_hygiene.seed_repo_excludes(repo)
    assert "*.pyc" not in excludes(repo)

    monkeypatch.setattr(repo_hygiene, "EXCLUDE_PATTERNS", [".agentweave/worktrees/", "*.pyc"])
    repo_hygiene.seed_repo_excludes(repo)

    written = excludes(repo)
    assert "*.pyc" in written
    assert written.count(repo_hygiene.EXCLUDE_BEGIN) == 1


def test_what_the_operator_wrote_is_never_touched(tmp_path):
    repo = init_repo(tmp_path / "repo")
    target = repo / ".git" / "info" / "exclude"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# mine\nsecret.txt\n", encoding="utf-8")

    repo_hygiene.seed_repo_excludes(repo)
    written = excludes(repo)
    assert written.startswith("# mine\nsecret.txt\n")

    # Including when the block is rewritten around them.
    repo_hygiene.seed_repo_excludes(repo)
    assert excludes(repo).startswith("# mine\nsecret.txt\n")


def test_lines_after_the_block_survive_a_rewrite(tmp_path, monkeypatch):
    repo = init_repo(tmp_path / "repo")
    target = repo / ".git" / "info" / "exclude"
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(repo_hygiene, "EXCLUDE_PATTERNS", [".agentweave/worktrees/"])
    repo_hygiene.seed_repo_excludes(repo)
    target.write_text(excludes(repo) + "# after\ntrailing.txt\n", encoding="utf-8")

    monkeypatch.setattr(repo_hygiene, "EXCLUDE_PATTERNS", [".agentweave/worktrees/", "*.pyc"])
    repo_hygiene.seed_repo_excludes(repo)

    written = excludes(repo)
    assert written.endswith("# after\ntrailing.txt\n")
    assert "*.pyc" in written


def test_seeding_does_not_untrack_what_is_already_committed(tmp_path):
    """Ignore rules govern untracked paths. A file an earlier snapshot committed stays committed.

    Stated as a test because the alternative — the Hub rewriting the operator's index to clean up
    after itself — is a second unasked-for change on top of the first, and someone will eventually
    propose it as a fix.
    """
    repo = init_repo(tmp_path / "repo")
    cached = repo / "__pycache__" / "already.pyc"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text("x\n", encoding="utf-8")
    git(repo, "add", "-f", "__pycache__/already.pyc")
    git(repo, "commit", "-q", "-m", "the mess the Hub already made")

    repo_hygiene.seed_repo_excludes(repo)

    assert "__pycache__/already.pyc" in git(repo, "ls-files").stdout


def test_a_directory_that_is_not_a_repository_is_left_alone(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    repo_hygiene.seed_repo_excludes(plain)
    assert not (plain / ".git").exists()


def test_a_linked_worktree_is_not_a_seeding_target(tmp_path):
    """A worktree's `.git` is a file. Its common directory is elsewhere, and that is where the
    rules already are — seeding from here would write to the wrong place or nowhere."""
    repo = init_repo(tmp_path / "repo")
    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), "-b", "feature")
    assert (worktree / ".git").is_file()

    repo_hygiene.seed_repo_excludes(worktree)

    assert not (worktree / ".git" / "info").exists()


def test_an_unwritable_target_is_not_fatal(tmp_path, monkeypatch):
    repo = init_repo(tmp_path / "repo")

    def refuse(*args, **kwargs):
        raise OSError("nope")

    monkeypatch.setattr(Path, "write_text", refuse)
    repo_hygiene.seed_repo_excludes(repo)  # must not raise
