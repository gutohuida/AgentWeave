"""Tests for detecting a stale built UI bundle (task 3.20).

`hub/hub/static/ui` is a committed build artefact that nothing rebuilds
automatically in a source checkout. These tests exercise the git-history
comparison in isolation, using throwaway repos, rather than depending on
this repository's own commit history (which would make the test's outcome
depend on when this file happens to run).
"""

import os
import subprocess
from pathlib import Path

import pytest

from hub.main import _compute_ui_staleness_warning, _git_last_commit_iso


def _commit(path: Path, commit_date: str) -> None:
    """Initialize (if needed) a git repo at `path` and add one commit at `commit_date`."""
    path.mkdir(parents=True, exist_ok=True)
    if not (path / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    marker = commit_date.replace(":", "").replace("+", "-")
    (path / f"file-{marker}.txt").write_text("content")
    env = {**os.environ, "GIT_AUTHOR_DATE": commit_date, "GIT_COMMITTER_DATE": commit_date}
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", f"commit at {commit_date}"], cwd=path, env=env, check=True
    )


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="git not available",
)
class TestUiStalenessWarning:
    def test_warns_when_source_is_newer(self, tmp_path):
        ui_dist = tmp_path / "dist"
        ui_src = tmp_path / "src"
        _commit(ui_dist, "2026-01-01T00:00:00+00:00")
        _commit(ui_src, "2026-02-01T00:00:00+00:00")

        warning = _compute_ui_staleness_warning(ui_dist, ui_src)

        assert warning is not None
        assert "2026-01-01" in warning
        assert "2026-02-01" in warning

    def test_silent_when_dist_is_newer_or_equal(self, tmp_path):
        ui_dist = tmp_path / "dist"
        ui_src = tmp_path / "src"
        _commit(ui_src, "2026-01-01T00:00:00+00:00")
        _commit(ui_dist, "2026-02-01T00:00:00+00:00")

        assert _compute_ui_staleness_warning(ui_dist, ui_src) is None

    def test_silent_when_source_dir_absent(self, tmp_path):
        """No hub/ui/src means an installed package, not a source checkout — nothing to compare."""
        ui_dist = tmp_path / "dist"
        ui_src = tmp_path / "src"
        _commit(ui_dist, "2026-01-01T00:00:00+00:00")

        assert _compute_ui_staleness_warning(ui_dist, ui_src) is None

    def test_silent_when_dist_dir_absent(self, tmp_path):
        ui_dist = tmp_path / "dist"
        ui_src = tmp_path / "src"
        _commit(ui_src, "2026-01-01T00:00:00+00:00")

        assert _compute_ui_staleness_warning(ui_dist, ui_src) is None

    def test_git_last_commit_iso_returns_none_outside_a_repo(self, tmp_path):
        empty_dir = tmp_path / "not-a-repo"
        empty_dir.mkdir()

        assert _git_last_commit_iso(empty_dir) is None
