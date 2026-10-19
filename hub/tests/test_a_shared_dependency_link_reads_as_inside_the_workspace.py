"""F444: a worktree's shared dependency links do not make ordinary reads through them refused.

The Hub links `node_modules`, `.venv` and `venv` from the project checkout into every worktree
(`worktrees._symlink_shared_dependencies`). The shell judge resolved every such path outside the
workspace, so in a JavaScript worktree `ls node_modules`, `grep -r foo --exclude-dir=node_modules .`
and `ls node_*` were refused. A link the Hub made, to a directory of the same name, is the
workspace's own dependency directory; what lies under it reads as inside. A `..` out of it, a
differently named link, and any other link stay outside.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hub.mcp_server import _SHARED_DEPENDENCY_DIRS, _decide
from hub.worktrees import SHARED_DEPENDENCY_DIRS

_WINDOWS = os.name == "nt"


def _link(link: Path, target: Path) -> None:
    """A directory link made without privilege: a junction on Windows, a symlink elsewhere."""
    if _WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.fixture()
def worktree(tmp_path, monkeypatch):
    """A worktree whose shared dependency directories are linked the way the Hub links them."""
    checkout = tmp_path / "checkout"
    work = tmp_path / "work"
    work.mkdir()
    for name in ("node_modules", ".venv", "venv"):
        (checkout / name / "pkg").mkdir(parents=True)
        (checkout / name / "pkg" / "index.js").write_text("x")
        _link(work / name, checkout / name)
    (checkout / "src").mkdir()
    (checkout / "src" / "x").write_text("x")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(work))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return work


@pytest.mark.parametrize(
    "tool, command",
    [
        pytest.param("Bash", "ls node_modules", id="bare-name"),
        pytest.param("Bash", "ls node_modules/pkg", id="through-the-link"),
        pytest.param("Bash", "grep -r foo --exclude-dir=node_modules .", id="exclude-dir"),
        pytest.param("Bash", "grep foo *", id="star-glob"),
        pytest.param("Bash", "ls node_*", id="glob-naming-the-link"),
        pytest.param("Bash", "cat node_modules/pkg/*.js", id="glob-beneath-the-link"),
        pytest.param("Bash", "ls .venv venv", id="venv-names"),
        pytest.param("PowerShell", "Get-ChildItem node_modules", id="powershell"),
        pytest.param("Bash", "cat node_modules/pkg/../pkg/index.js", id="dotdot-stays-beneath"),
    ],
)
def test_a_read_through_a_shared_dependency_link_is_allowed(worktree, tool, command):
    decision = _decide(tool, {"command": command})
    assert decision["allow"] is True, decision["reason"]


def test_a_write_to_a_path_beneath_the_link_is_judged_as_inside(worktree):
    decision = _decide("Write", {"file_path": str(worktree / "node_modules" / "pkg" / "a.js")})
    assert decision["allow"] is True, decision["reason"]


@pytest.mark.parametrize(
    "tool, command",
    [
        pytest.param("Bash", "cp n node_modules/../src/x", id="dotdot-out-of-the-link"),
        pytest.param("Bash", "cp n node_modules/pkg/../../src/x", id="dotdot-two-out"),
        pytest.param("Bash", "ls node_modules/..", id="the-checkout-itself"),
    ],
)
def test_a_dotdot_out_of_a_shared_dependency_link_is_still_outside(worktree, tool, command):
    decision = _decide(tool, {"command": command})
    assert decision["allow"] is False, decision["reason"]
    assert "is outside your workspace" in decision["reason"]


def test_a_link_with_another_name_than_its_target_is_still_outside(tmp_path, monkeypatch):
    """Only the Hub's shape is exempt: `node_modules` pointing at a directory of another name is
    not the shared dependency directory."""
    work = tmp_path / "work"
    work.mkdir()
    (tmp_path / "elsewhere").mkdir()
    _link(work / "node_modules", tmp_path / "elsewhere")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(work))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    decision = _decide("Bash", {"command": "ls node_modules"})
    assert decision["allow"] is False, decision["reason"]


def test_a_link_with_another_name_in_the_workspace_is_still_outside(worktree, tmp_path):
    """The exemption is for the three known names, not for any link whose target repeats its name."""
    (tmp_path / "checkout" / "other").mkdir()
    _link(worktree / "other", tmp_path / "checkout" / "other")
    decision = _decide("Bash", {"command": "ls other"})
    assert decision["allow"] is False, decision["reason"]


def test_the_judge_restates_the_names_the_hub_links():
    assert _SHARED_DEPENDENCY_DIRS == SHARED_DEPENDENCY_DIRS
