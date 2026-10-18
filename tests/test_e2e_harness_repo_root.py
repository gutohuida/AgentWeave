"""F749: `e2e.py hub-up` runs the Hub of the checkout the script sits in, not always the main one."""

from __future__ import annotations

import importlib.util
import pathlib
import shutil

import pytest

E2E = pathlib.Path(__file__).resolve().parents[1] / ".claude" / "skills" / "e2e-loop" / "e2e.py"


def _load(path: pathlib.Path, monkeypatch, repo_root: str | None = None):
    # Never let a test overwrite the operator's record of the Hub they are driving.
    monkeypatch.setenv("AW_E2E_STATE", str(path.parent / "e2e-current.json"))
    if repo_root is None:
        monkeypatch.delenv("AW_REPO_ROOT", raising=False)
    else:
        monkeypatch.setenv("AW_REPO_ROOT", repo_root)
    spec = importlib.util.spec_from_file_location("e2e_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checkout(tmp_path: pathlib.Path) -> pathlib.Path:
    """A stand-in worktree: its own copy of the script and a `hub/` directory."""
    root = tmp_path / "worktree"
    (root / "hub").mkdir(parents=True)
    target = root / ".claude" / "skills" / "e2e-loop"
    target.mkdir(parents=True)
    shutil.copy(E2E, target / "e2e.py")
    return root


def test_a_script_in_a_worktree_drives_that_worktrees_hub(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    module = _load(root / ".claude" / "skills" / "e2e-loop" / "e2e.py", monkeypatch)
    assert root == module.REPO


def test_the_override_still_wins(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    other = tmp_path / "elsewhere"
    module = _load(
        root / ".claude" / "skills" / "e2e-loop" / "e2e.py", monkeypatch, repo_root=str(other)
    )
    assert other == module.REPO


def test_hub_up_refuses_a_checkout_with_no_hub_directory(tmp_path, monkeypatch):
    root = _checkout(tmp_path)
    shutil.rmtree(root / "hub")
    module = _load(root / ".claude" / "skills" / "e2e-loop" / "e2e.py", monkeypatch)
    with pytest.raises(SystemExit) as refused:
        module.cmd_hub_up("f749-profile", 59999)
    assert "hub" in str(refused.value)
    assert str(root) in str(refused.value)
