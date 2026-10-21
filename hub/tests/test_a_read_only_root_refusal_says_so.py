"""F794: a shell or write call on a path inside a root granted for reading only is refused in words
that name the read grant, not as "is outside your workspace" (the words for an ungranted path)."""

import json

from hub import mcp_server


def _decide(tool, tool_input, root, access, workspace):
    grants = json.dumps({"roots": [{"path": str(root), "access": access}], "hosts": []})
    return mcp_server._decide(tool, tool_input, workspace=str(workspace), grants=grants)


def test_a_shell_command_on_a_read_root_says_the_root_is_read_only(tmp_path):
    work = tmp_path / "work"
    ro = tmp_path / "ro"
    work.mkdir()
    ro.mkdir()
    target = str(ro / "notes.txt")
    decided = _decide("Bash", {"command": f"cat '{target}'"}, ro, "read", work)
    assert decided["allow"] is False
    assert "granted for reading only" in decided["reason"]
    assert "file-reading tool" in decided["reason"]
    assert "outside your workspace" not in decided["reason"]


def test_a_write_on_a_read_root_says_the_root_is_read_only(tmp_path):
    work = tmp_path / "work"
    ro = tmp_path / "ro"
    work.mkdir()
    ro.mkdir()
    decided = _decide("Write", {"file_path": str(ro / "w.txt"), "content": "x"}, ro, "read", work)
    assert decided["allow"] is False
    assert "granted for reading only" in decided["reason"]


def test_a_read_tool_on_a_read_root_is_still_allowed(tmp_path):
    work = tmp_path / "work"
    ro = tmp_path / "ro"
    work.mkdir()
    ro.mkdir()
    assert _decide("Read", {"file_path": str(ro / "n.txt")}, ro, "read", work)["allow"] is True


def test_an_ungranted_path_is_still_outside_the_workspace(tmp_path):
    work = tmp_path / "work"
    ro = tmp_path / "ro"
    other = tmp_path / "other"
    for d in (work, ro, other):
        d.mkdir()
    decided = _decide("Bash", {"command": f"cat '{other / 'x.txt'}'"}, ro, "read", work)
    assert decided["allow"] is False
    assert "outside your workspace" in decided["reason"]
    assert "reading only" not in decided["reason"]
