"""F756: a path with two glob components is judged where its links take it.

`ls up*/../*` was allowed with `up` a link to a directory outside the workspace, though it lists
that directory's parent; `ls up*/..` and `ls up/../*` were refused. The glob walk
(`_glob_links`) stopped at the first sign of a second glob-holding component, and the literal
reading of `up*/../*` is `<workspace>/up*/../*`, which is inside. The walk now goes on: a glob
component after the first is matched against the directory the branch has reached.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hub.mcp_server import _decide

_WINDOWS = os.name == "nt"


def _link(link: Path, target: Path) -> None:
    """A directory link made without privilege: a junction on Windows, a symlink elsewhere."""
    if _WINDOWS:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    work = tmp_path / "work"
    (work / "sub" / "deep").mkdir(parents=True)
    (work / "sub" / "deep" / "f.py").write_text("x")
    (work / "sub" / "g.py").write_text("x")
    (work / "top.txt").write_text("x")
    outside = tmp_path / "outside"
    (outside / "inner").mkdir(parents=True)
    _link(work / "up", outside / "inner")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(work))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return work


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("ls up*/../*", id="the-finding"),
        pytest.param("ls up*/../*/x", id="a-literal-after-the-second-glob"),
        pytest.param("cp n up*/../*", id="a-write-form"),
        pytest.param("ls *p/../*", id="glob-first-component-ends-in-p"),
        pytest.param("ls up*/../*/..", id="and-back-again"),
        pytest.param("ls sub*/../*", id="the-second-glob-matches-the-link-itself"),
        pytest.param("ls */*", id="the-first-glob-matches-the-link-itself"),
        pytest.param("ls up/../*", id="control-literal-link-then-glob"),
        pytest.param("ls up*/..", id="control-one-glob"),
    ],
)
def test_a_glob_path_that_leaves_through_a_link_is_refused(workspace, command):
    decision = _decide("Bash", {"command": command})
    assert decision["allow"] is False, decision["reason"]


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("ls sub*/../t*", id="a-real-directory-then-dotdot-then-glob"),
        pytest.param("ls s*/*", id="two-globs-no-dotdot-no-link-in-sight"),
        pytest.param("ls s*/d*/*.py", id="three-globs-in-the-workspace"),
        pytest.param("cat sub/*/f.p*", id="globs-beneath-a-real-directory"),
        pytest.param("ls sub*/deep*/../*.py", id="dotdot-stays-inside"),
        pytest.param("ls nomatch*/../*", id="the-first-glob-matches-nothing"),
    ],
)
def test_a_glob_path_that_stays_inside_is_allowed(workspace, command):
    decision = _decide("Bash", {"command": command})
    assert decision["allow"] is True, decision["reason"]
