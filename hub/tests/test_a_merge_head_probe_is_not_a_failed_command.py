"""F791: `git rev-parse --verify --quiet MERGE_HEAD` exits 1 when no merge is in progress, which
is the normal case. The span recording that probe must not read as an error."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from hub import traces, worktrees


def _repo(path: Path) -> Path:
    path.mkdir()
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "f.txt").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "f.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "c"], cwd=path, check=True)
    return path


def _spans_of(probe, repo: Path):
    parent = traces.PendingSpan(
        project_id="p", name="work", operation="aw.work", start_time=datetime.now(timezone.utc)
    )
    token = traces.set_current(parent)
    try:
        result = probe(repo)
    finally:
        traces.reset_current(token)
    return result, [c for c in parent.children if c.operation == "aw.command"]


def test_no_merge_in_progress_is_an_answer_not_an_error(tmp_path):
    repo = _repo(tmp_path / "r")
    for probe in (worktrees._is_mid_merge, worktrees._merge_head):
        _, spans = _spans_of(probe, repo)
        [span] = spans
        assert span.attributes["process.exit.code"] == 1
        assert span.status == "ok", span.status_message


def test_a_real_failure_of_another_command_is_still_an_error(tmp_path):
    repo = _repo(tmp_path / "r")
    _, spans = _spans_of(
        lambda r: worktrees._run_git(r, "rev-parse", "--verify", "--quiet", "nope", check=False),
        repo,
    )
    [span] = spans
    assert span.status == "error"
