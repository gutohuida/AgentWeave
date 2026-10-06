"""`aw-tool --help <tool>` prints a tool's whole description, and the shim notice says so.

Slice 1b of the same-file-tasks change: `--list` keeps only the first line of each description, so
a planner on the aw-tool path never saw `depends_on` or `files` on `submit_spec_document`.
"""

from __future__ import annotations

import inspect
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Tuple

import pytest

from hub import mcp_server
from hub.launchability import access_path_notice


def _call(capsys: pytest.CaptureFixture[str], *argv: str) -> Tuple[int, Dict[str, Any]]:
    code = mcp_server.call_main(list(argv))
    out = capsys.readouterr().out.strip().splitlines()
    return code, json.loads(out[-1])


def test_help_tool_prints_the_whole_description(capsys):
    code, envelope = _call(capsys, "--help", "submit_spec_document")
    assert code == 0
    assert envelope["ok"] is True
    description = envelope["result"]["description"]
    assert description == inspect.getdoc(mcp_server._CALLABLE_TOOLS["submit_spec_document"])
    assert "depends_on" in description and "files" in description
    # More than the listing's one line: that is the point.
    first_line = description.split("\n", 1)[0]
    assert description != first_line


def test_help_unknown_tool_is_a_usage_error_naming_it(capsys):
    code, envelope = _call(capsys, "--help", "not_a_tool")
    assert code == 64
    assert envelope["ok"] is False
    assert envelope["error"]["kind"] == "usage"
    assert "not_a_tool" in envelope["error"]["detail"]


def test_help_alone_and_list_are_unchanged(capsys):
    code, envelope = _call(capsys, "--help")
    assert code == 0
    assert envelope == {"ok": True, "result": {"usage": mcp_server._CALL_HELP}}

    code, envelope = _call(capsys, "--list")
    assert code == 0
    tools = envelope["result"]["tools"]
    assert [t["name"] for t in tools] == sorted(mcp_server._CALLABLE_TOOLS)
    for entry in tools:
        assert set(entry) == {"name", "parameters", "required", "summary"}
        assert "\n" not in entry["summary"]
    assert envelope["result"] == json.loads(json.dumps(mcp_server._call_listing()))


def test_shim_notice_names_help(capsys):
    notice = access_path_notice("shim")
    assert "--help <tool>" in notice
    assert "only the first line" in notice
    assert "--list" in notice


def test_no_migration_file_differs_from_master():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "diff", "--name-status", "master", "--", "hub/hub/migrations/versions"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"no master to compare with: {result.stderr.strip()}")
    assert result.stdout.strip() == ""
