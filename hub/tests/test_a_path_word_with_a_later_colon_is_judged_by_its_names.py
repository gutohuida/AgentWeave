"""F446: a plain path word with a colon in a later component is judged by its names, not refused.

On a drive-letter host `ntpath.realpath` reads any component whose second character is `:` as a
drive and drops everything before it, so `rg foo src/a:1` landed outside the workspace. Rule 5 now
divides such a word at its colons (the way `_judge_whole_value` does) and judges each name.
"""

from __future__ import annotations

import sys

import pytest

from hub.mcp_server import _decide

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="only a drive-letter host misreads `a:` as a drive"
)


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    (ws / "src").mkdir(parents=True)
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


def _allowed(workspace, command: str) -> bool:
    return _decide("Bash", {"command": command}, workspace=str(workspace))["allow"]


@pytest.mark.parametrize(
    "command",
    [
        "rg foo src/a:1",
        "rg foo src/a:b",
        "rg foo a/b:1/x",
        "rg foo src/x:y/z",
        "rg foo src/ab:1",
        "rg foo src/a:12:3",
    ],
)
def test_a_line_reference_after_a_directory_is_inside(workspace, command):
    assert _allowed(workspace, command)


@pytest.mark.parametrize(
    "command",
    [
        "rg foo src/a:../../x",  # the part after the colon climbs out
        "rg foo src/a:/..",  # the part after the colon is rooted
        "rg foo src/Z:../../../x",
        "rg foo ../a:1",  # the part before the colon climbs out
        "rg foo ../../etc/a:1",
    ],
)
def test_a_colon_does_not_hide_a_path_that_leaves_the_workspace(workspace, command):
    assert not _allowed(workspace, command)
