"""F464: `_where` refuses a UNC or device path before `os.path.realpath` can open a connection.

`realpath` on a UNC path (`//host/share/x`) makes the platform contact `host` (21 s measured for an
unreachable one), so the judge decides on the spelling alone. The decision is the same one it
reached afterwards: the path is outside the workspace.
"""

import os

import pytest

from hub import mcp_server

UNC_SPELLINGS = [
    r"\\10.255.255.1\share\x",
    "//10.255.255.1/share/x",
    r"\\?\UNC\10.255.255.1\share\x",
    r"\\.\pipe\x",
    "//?/C:/x",
]


@pytest.fixture
def no_realpath(monkeypatch):
    def fail(path, *args, **kwargs):
        raise AssertionError(f"realpath was called for {path!r}: that opens the network")

    monkeypatch.setattr(os.path, "realpath", fail)
    monkeypatch.setattr(mcp_server, "_DRIVE_LETTERS", True)


@pytest.mark.parametrize("spelling", UNC_SPELLINGS)
def test_a_unc_path_is_refused_without_resolving_it(no_realpath, tmp_path, spelling):
    why = mcp_server._where(spelling, str(tmp_path))
    assert why is not None and why.startswith(mcp_server._OUTSIDE), why


def test_a_path_with_one_leading_separator_is_still_resolved(tmp_path, monkeypatch):
    """Only a doubled separator is a network spelling; a lone `/x` is the current drive."""
    monkeypatch.setattr(mcp_server, "_DRIVE_LETTERS", True)
    seen = []
    real = os.path.realpath

    def spy(path, *args, **kwargs):
        seen.append(path)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os.path, "realpath", spy)
    mcp_server._where("/x", str(tmp_path))
    assert seen


@pytest.mark.skipif(os.sep != "\\", reason="a UNC root is a Windows path")
def test_a_workspace_that_is_itself_a_unc_path_keeps_its_own_files(monkeypatch):
    """A path under a UNC workspace root is judged by the old route, not refused on spelling."""
    monkeypatch.setattr(mcp_server, "_DRIVE_LETTERS", True)
    root = r"\\server\share\work"
    monkeypatch.setattr(os.path, "realpath", lambda p, *a, **k: p)
    assert mcp_server._where(root + r"\sub\f.txt", root) is None


@pytest.fixture
def guarded_realpath(monkeypatch):
    """The real `realpath`, except that it fails the test for any network spelling."""
    real = os.path.realpath

    def guard(path, *args, **kwargs):
        if str(path)[:2] in ("//", "\\\\", "/\\", "\\/"):
            raise AssertionError(f"realpath was called for {path!r}: that opens the network")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os.path, "realpath", guard)
    monkeypatch.setattr(mcp_server, "_DRIVE_LETTERS", True)


@pytest.mark.parametrize("tool, key", [("Edit", "file_path"), ("Write", "path")])
@pytest.mark.parametrize("spelling", UNC_SPELLINGS)
def test_a_decision_on_a_file_tool_never_resolves_a_network_path(
    guarded_realpath, tmp_path, tool, key, spelling
):
    """The first stop is the Hub-own-call rule, which resolved the path before `_where` ever ran."""
    verdict = mcp_server._decide(tool, {key: spelling}, workspace=str(tmp_path))
    assert verdict["allow"] is False, verdict


def test_the_call_arguments_file_is_not_read_from_a_network_path(
    guarded_realpath, tmp_path, monkeypatch
):
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(tmp_path))
    with pytest.raises(mcp_server._CallUsageError):
        mcp_server._read_call_args(r"\\10.255.255.1\share\x.json")
