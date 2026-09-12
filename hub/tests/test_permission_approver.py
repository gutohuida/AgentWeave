"""The Hub-answered permission approver.

Covers the decision logic, the wire shape Claude actually requires, and the argv that selects the
posture. The wire-shape test is the load-bearing one: every other assertion here can pass while a
correct "allow" is silently not honoured live (see `test_response_carries_no_structured_content`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from hub.mcp_server import _decide
from hub.model_catalog import WORKSPACE_PERMISSION_MODE, get_provider, render_control_args
from hub.runner_commands import (
    CLAUDE_PERMISSION_PROMPT_TOOL,
    DEFAULT_CLAUDE_PERMISSION_MODE,
    DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER,
    build_command,
)

MCP_SERVER = Path(__file__).resolve().parents[1] / "hub" / "mcp_server.py"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """An isolated workspace, with a sibling directory outside it."""
    ws = tmp_path / "work"
    (ws / "sub").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    # No run credential: _report_decision raises internally and must be swallowed. Every decision
    # assertion below therefore also exercises the "reporting failed" path (task 3.4).
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


# --- The decision -----------------------------------------------------------------------------


def test_a_path_inside_the_workspace_is_allowed(workspace):
    assert _decide("Write", {"file_path": str(workspace / "a.txt")})["allow"] is True
    assert _decide("Write", {"file_path": str(workspace / "sub" / "a.txt")})["allow"] is True


def test_a_relative_path_resolves_against_the_workspace(workspace):
    assert _decide("Write", {"file_path": "a.txt"})["allow"] is True


def test_a_path_outside_the_workspace_is_denied_with_the_path_named(workspace):
    outside = workspace.parent / "outside" / "a.txt"
    decision = _decide("Write", {"file_path": str(outside)})
    assert decision["allow"] is False
    assert "outside" in decision["reason"]


def test_relative_traversal_cannot_escape(workspace):
    escape = workspace / ".." / "outside" / "a.txt"
    assert _decide("Write", {"file_path": str(escape)})["allow"] is False


def test_a_sibling_sharing_a_prefix_is_not_inside(workspace):
    """`/work-other` starts with the characters of `/work` but is not beneath it. A string
    prefix comparison allows this; a component comparison does not."""
    sibling = str(workspace) + "-other"
    assert _decide("Write", {"file_path": os.path.join(sibling, "a.txt")})["allow"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privilege on Windows")
def test_a_symlink_cannot_escape(workspace):
    target = workspace.parent / "outside"
    link = workspace / "link"
    link.symlink_to(target, target_is_directory=True)
    assert _decide("Write", {"file_path": str(link / "a.txt")})["allow"] is False


def test_an_unestablished_workspace_denies(monkeypatch):
    monkeypatch.setenv("AW_WORKSPACE_DIR", "")
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    decision = _decide("Write", {"file_path": "a.txt"})
    assert decision["allow"] is False
    assert "could not be established" in decision["reason"]


def test_the_hubs_own_tools_are_always_allowed(monkeypatch):
    """Allowed even with no workspace at all — collaboration is not a filesystem decision."""
    monkeypatch.setenv("AW_WORKSPACE_DIR", "")
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    assert _decide("mcp__agentweave__send_message", {"to_agent": "b"})["allow"] is True


def test_a_call_with_no_path_argument_is_allowed(workspace):
    assert _decide("Grep", {"pattern": "x"})["allow"] is True


def test_a_shell_command_with_an_absolute_path_outside_is_denied(workspace):
    outside = str(workspace.parent / "outside").replace("\\", "/")
    decision = _decide("Bash", {"command": f"printf hi > {outside}/a.txt"})
    assert decision["allow"] is False


def test_a_shell_command_with_only_relative_paths_is_allowed(workspace):
    assert _decide("Bash", {"command": "printf hi > a.txt"})["allow"] is True


def test_a_decision_is_reached_even_when_reporting_fails(workspace, monkeypatch):
    """Reporting is observational. With the Hub unreachable, the answer is unchanged and no
    exception escapes — an unanswered request suspends a turn forever."""
    from hub import mcp_server

    def explode(*_args, **_kwargs):
        raise RuntimeError("hub is down")

    monkeypatch.setattr(mcp_server, "_hub_request", explode)
    allowed = json.loads(mcp_server.approve_tool_call("Write", {"file_path": "a.txt"}, "tu-1"))
    assert allowed["behavior"] == "allow"
    outside = str(workspace.parent / "outside" / "a.txt")
    denied = json.loads(mcp_server.approve_tool_call("Write", {"file_path": outside}, "tu-2"))
    assert denied["behavior"] == "deny"


# --- The decided table (a-url-is-not-a-path, design D2) ---------------------------------------
#
# Every row of D2, with its decided answer and, where D2 names one, its reason. The rows were
# pinned against the regex that read whole commands before the reader replaced it; the rows that
# moved are D2's, and no other. The ids are D2's labels, so a failure names its row.

_WINDOWS = os.sep == "\\"
_HUB = "http://127.0.0.1:8016"

_H1 = (
    'curl -s -X POST "$HUB_URL/api/v1/agent-actions/tasks" -H "Authorization: Bearer '
    '$AW_RUN_TOKEN" -H "Content-Type: application/json" -d \'{"title": "x"}\''
)
_H2 = (
    'curl.exe -s -X POST "$env:HUB_URL/api/v1/agent-actions/tasks" -H "Authorization: Bearer '
    '$env:AW_RUN_TOKEN"'
)
_H3 = "curl -s ${HUB_URL}/api/v1/agent-actions/tasks"
_H4 = "curl -s http://127.0.0.1:8016/api/v1/agent-actions/tasks"
# F301's S1_python_c, character for character (testbed/scratch/f301shapes/shapes.py).
_S1_PYTHON_C = (
    'python -c "import os,json,urllib.request; r=urllib.request.Request('
    "os.environ['HUB_URL']+'/api/v1/agent-actions/tasks', data=json.dumps({'title':'x'})"
    ".encode(), headers={'Authorization':'Bearer '+os.environ['AW_RUN_TOKEN'],"
    "'Content-Type':'application/json'}); print(urllib.request.urlopen(r).read())\""
)
_NETWORK = ("network",)
_UNCHECKED = ("unchecked",)


def _outside(word: str) -> tuple:
    return ("outside", repr(word))


def _row(label, command, allow, reason=None, *, tool="Bash"):
    """One row: the tool whose `command` is read, and D2's answer and reason *after*."""
    return pytest.param(tool, command, allow, reason, id=label)


_TABLE = [
    # The research's rows.
    _row("R1", "echo hi > ../stray.txt", False, _outside("../stray.txt")),
    _row("R2", "echo hi | tee ../stray.txt", False, _outside("../stray.txt")),
    _row("R3", "cp notes.md ../../stray.md", False, _outside("../../stray.md")),
    _row("R4", "echo hi > ~/stray.txt", False, _UNCHECKED),
    _row("R5", 'echo hi > "$HOME/stray.txt"', False, _UNCHECKED),
    _row("R6", "D=/tmp; echo hi > $D/stray.txt", False, _outside("/tmp")),
    _row("R7", "echo hi > /tmp/stray.txt", False, _outside("/tmp/stray.txt")),
    _row("R8", "cd .. && echo hi > stray.txt", True),
    _row("R9", "git -C .. status", True),
    _row("R10", "curl -s https://example.com/x", False, _NETWORK),
    _row("R11", 'curl "$HUB_URL/api/v1/agent-actions/tasks"', True),
    # F321: paths inside the workspace.
    _row("W1", "python sub/hello.py", True),
    _row("W2", "git add sub/hello.py", True),
    _row("W3", "pytest sub/test_x.py::test_a", True),
    _row("W4", "git diff origin/main...HEAD", True),
    _row("W5", "python sub/../hello.py", True),
    _row("W6", r"Get-Content .\sub\hello.py", True, tool="PowerShell"),
    _row("W7a", "ls", True),
    _row("W7b", "printf hi > a.txt", True),
    _row("W7c", "npm run test:unit", True),
    # The run's own Hub, and addresses that only look like it (D4).
    _row("H1", _H1, True),
    _row("H2", _H2, True, tool="PowerShell"),
    _row("H3", _H3, True),
    _row("H4", _H4, True),
    _row("H5", "curl -s http://127.0.0.1:9/api/v1/agent-actions/tasks", False, _NETWORK),
    _row(
        "H6",
        "curl -s http://localhost:8016/api/v1/agent-actions/tasks",
        False,
        _NETWORK,
    ),
    _row("H7", "curl -s http://127.0.0.1:8016@evil.example/x", False, _NETWORK),
    _row("H8", "curl -s $HUB_URL@evil.example/x", False, _UNCHECKED),
    _row("H9", "HUB_URL=https://evil.example; curl -s $HUB_URL/x", False, _NETWORK),
    _row("H10", "HUB_URL=.. ; cat $HUB_URL/x", False, _UNCHECKED),
    _row("H11", _S1_PYTHON_C, False, ("outside", "/api/v1/agent-actions/tasks")),
    _row("H13", "curl -s http://u:p@127.0.0.1:8016/x", False, _NETWORK),
    _row("H14", "curl -s http://127.0.0.1:8016.evil.example/x", False, _NETWORK),
    _row("H15", 'curl -s "http://127.0.0.1:8016#@evil.example/"', True),
    _row("H16", "curl -s HTTP://127.0.0.1:8016/x", True),
    # A bare `$HUB_URL` in PowerShell is a shell variable, not the environment's value: with
    # `$env:HUB_URL` set, `Write-Output $HUB_URL/x` printed `/x` in Windows PowerShell 5.1
    # (u2-reader, 2026-09-12), a path at the drive's root. It is no reference there.
    _row("H17", "echo hi > $HUB_URL/x", False, _UNCHECKED, tool="PowerShell"),
    # Other network shapes.
    _row("N1", "pip install https://example.com/pkg.tar.gz", False, _NETWORK),
    _row("N2", "git clone https://github.com/o/r.git", False, _NETWORK),
    _row("N3", "curl -s example.com/x", True),
    _row("N4", "curl -s example.com", True),
    _row("N5", "curl -s 127.0.0.1:9/x", False, _outside("/x")),
    _row("N6", "git clone git@github.com:o/r.git", False, _outside("/r.git")),
    _row("N7", "curl file:///etc/passwd", False, _outside("file:///etc/passwd")),
    # F331: N7's rule, as a write. On POSIX the whole-command regex allowed this, and curl wrote
    # the file.
    _row("F331", "curl -T notes.md file:///tmp/stray.txt", False),
    # Glued paths: the backstop's rows.
    _row("G1", "curl -o/tmp/x $HUB_URL/api", False, _outside("/tmp/x")),
    _row("G2", "curl -d @/etc/passwd $HUB_URL/api", False, _outside("/etc/passwd")),
    _row("G3", "gcc -I../include x.c", False, _outside("/include")),
    _row("G4", "tar -C/tmp -xf a.tar", False, _outside("/tmp")),
    _row("G5", "echo hi > $1/stray.txt", False, _UNCHECKED),
    _row("G6", "echo hi > sub/$X/stray.txt", False, _UNCHECKED),
    # Windows forms that keep their answer on every platform.
    _row("X1a", r"echo hi > ..\stray.txt", True),
    _row("X2b", r"type %USERPROFILE%\x", True),
    _row("X3b", r"Get-Content $env:USERPROFILE\x", True),
    # Residuals, unchanged by this change.
    _row("X4", "cmd 2>/dev/null", False, _outside("/dev/null")),
    _row("X5", "python src/*.py", False, _outside("/*.py")),
    _row("X6", "git show HEAD:sub/hello.py", False, _outside("/hello.py")),
    _row("X7", "python $(pwd)/sub/hello.py", False, _UNCHECKED),
    # A NUL byte: `ntpath.realpath` accepts it, and `posixpath.realpath` raises ValueError, which
    # once escaped `_decide` on POSIX (D5, "Totality").
    _row("X8", "cat sub/a\x00b", False),
    # What R1's reader let through, and what it refused (R2's rows).
    _row("E1", "echo hi > '.'./stray.txt", False, _outside("../stray.txt")),
    _row("E2", 'echo hi > .""./stray.txt', False, _outside("../stray.txt")),
    _row(
        "E4",
        "echo hi > $HUB_URL/../../../stray.txt",
        False,
        _outside("$HUB_URL/../../../stray.txt"),
    ),
    _row(
        "E5",
        'echo hi > "$HUB_URL/../../../stray.txt"',
        False,
        _outside("$HUB_URL/../../../stray.txt"),
    ),
    _row(
        "E6",
        "echo hi > http://127.0.0.1:8016/../../../stray.txt",
        False,
        _outside("http://127.0.0.1:8016/../../../stray.txt"),
    ),
    _row(
        "E6b",
        "cp a http://127.0.0.1:8016/x#/../../../../stray.txt",
        False,
        _outside("http://127.0.0.1:8016/x#/../../../../stray.txt"),
    ),
    _row("E7", 'curl "$HUB_URL"@evil.example', False, _UNCHECKED),
    _row("E8", 'curl "$HUB_URL"@evil.example/x', False),
    _row("E9", "echo hi > $(echo .)./stray.txt", False, _UNCHECKED),
    _row("E10", "echo hi > `echo .`./stray.txt", False),
    _row("E11", "sh -c \"echo hi > '.'./stray.txt\"", False, _outside("/stray.txt")),
    _row("E12", 'sh -c "echo hi > ../stray.txt"', False),
    _row("E13", "curl $HUB_URL/$X", False, _UNCHECKED),
    _row("E14", "echo hi > $HUB_URL/../../x", True),
    # The fixture's workspace directory is named `work`, so these name it.
    _row("E15", "cp notes.md ../work=y/z", False, _outside("../work=y/z")),
    _row("E16", 'echo hi > "../work y.txt"', False, _outside("../work y.txt")),
    _row("E17", "echo hi > ../work,y", False),
    _row("E18", "curl -o<root>=x $HUB_URL/api", False),
    _row("E19", "echo hi > '../work'\"\"x", False),
    # A `$HUB_URL` the shell will not expand is a directory name, one component where the Hub's URL
    # is three. Read as a reference, `/../..` climbs out of the URL and stays inside; bash climbs
    # out of `$HUB_URL` and the workspace both. Measured in Git Bash 5.2.37: each wrote its file in
    # the workspace's parent (u2-reader, 2026-09-12). R2's and R3's readers allowed both.
    _row("E20", "echo hi > '$HUB_URL'/../../stray.txt", False),
    _row("E21", "echo hi > \\$HUB_URL/../../stray.txt", False),
    _row("E22", 'echo hi > "\\$HUB_URL/../../stray.txt"', False),
    _row("S2", 'echo "$(cat /etc/x)"', False, _outside("/etc/x")),
    _row("S3", "echo `cat /etc/x`", False),
    # Bodies and messages that name a path (R2). J2 and J3 are forms of F300's own request.
    _row("J1", 'curl -d \'{"description": "update src/a.py"}\' $HUB_URL/x', True),
    _row("J2", _H1.replace('\'{"title": "x"}\'', '"{\\"title\\": \\"x\\"}"'), True),
    _row(
        "J3",
        _H1.replace('\'{"title": "x"}\'', '"{\\"title\\": \\"fix sub/hello.py\\"}"'),
        True,
    ),
    _row("J4", "git commit -m 'fix: sub/hello.py'", True),
    _row("J5", "python -c \"open('/etc/x','w')\"", False),
    _row("J6", 'sh -c "echo hi > /etc/x"', False),
    _row("J7", "git commit -m 'fix sub/hello.py, and sub/other.py'", True),
    _row("J8", "python sub/hello.py --out=sub/out.txt", True),
    _row(
        "H2p",
        _H2 + ' -H "Content-Type: application/json" -d "{`"title`": `"x`"}"',
        True,
        tool="PowerShell",
    ),
]

# Windows reads `\` as a separator, so these rows moved there. On POSIX, where `\` is an ordinary
# character, the same commands kept the answer they had, and so did R3's backstop rows Z1-Z3.
_BACKSLASH_ROWS = (
    [
        _row("X1b", r'echo hi > "..\stray.txt"', False, _outside(r"..\stray.txt")),
        _row(
            "X1c",
            r"echo hi > ..\stray.txt",
            False,
            _outside(r"..\stray.txt"),
            tool="PowerShell",
        ),
        _row("X2p", r"type %USERPROFILE%\x", False, _UNCHECKED, tool="PowerShell"),
        _row(
            "X3p",
            r"Get-Content $env:USERPROFILE\x",
            False,
            _UNCHECKED,
            tool="PowerShell",
        ),
        _row("E3", r"echo hi > .\./stray.txt", False),
        # The workspace, written in MSYS form: `os.path` on Windows reads `/c/...` as `C:\c\...`.
        _row("X9", "python <msys>/sub/hello.py", False),
        _row("Z1", r'sort -o"..\stray.txt" notes.md', False, _outside(r"\stray.txt")),
        _row("Z2", r'curl -o"..\out" http://127.0.0.1:8016/api', False, _outside(r"\out")),
        _row("Z3", r'gcc -I"sub\include" x.c', False, _outside(r"\include")),
    ]
    if _WINDOWS
    else [
        _row("X1b", r'echo hi > "..\stray.txt"', True),
        _row("X1c", r"echo hi > ..\stray.txt", True, tool="PowerShell"),
        _row("X2p", r"type %USERPROFILE%\x", True, tool="PowerShell"),
        _row("X3p", r"Get-Content $env:USERPROFILE\x", True, tool="PowerShell"),
        _row("Z1", r'sort -o"..\stray.txt" notes.md', True),
        _row("Z2", r'curl -o"..\out" http://127.0.0.1:8016/api', True),
        _row("Z3", r'gcc -I"sub\include" x.c', True),
    ]
)


@pytest.mark.parametrize("tool, command, allow, reason", _TABLE + _BACKSLASH_ROWS)
def test_the_decided_table(workspace, monkeypatch, tool, command, allow, reason):
    monkeypatch.setenv("HUB_URL", _HUB)
    root = os.path.realpath(workspace)
    command = command.replace("<root>", root.replace("\\", "/"))
    command = command.replace("<msys>", "/" + root[:1].lower() + root[2:].replace("\\", "/"))
    decision = _decide(tool, {"command": command})
    assert decision["allow"] is allow, decision["reason"]
    if reason == _NETWORK:
        assert "network address" in decision["reason"]
        assert "workspace" not in decision["reason"]
    elif reason == _UNCHECKED:
        assert "cannot be checked" in decision["reason"]
        assert "outside your workspace" not in decision["reason"]
    elif reason is not None:
        assert reason[1] in decision["reason"]
        assert "is outside your workspace" in decision["reason"]


def test_a_fetch_is_not_governed(workspace, monkeypatch):
    """N8. The rule governs shell command text only (D7). A change that brings fetch under it
    must flip this deliberately."""
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide("WebFetch", {"url": "https://example.com/x", "prompt": "p"})
    assert decision["allow"] is True


@pytest.mark.parametrize(
    "tool, command",
    [
        pytest.param("Bash", _H1, id="H1"),
        pytest.param("PowerShell", _H2, id="H2"),
        pytest.param("Bash", _H3, id="H3"),
        pytest.param("Bash", _H4, id="H4"),
    ],
)
def test_the_run_s_own_hub_is_nobody_s_without_hub_url(workspace, monkeypatch, tool, command):
    """H12. With `HUB_URL` unset in the approver, no address is the run's own Hub."""
    monkeypatch.delenv("HUB_URL", raising=False)
    assert _decide(tool, {"command": command})["allow"] is False


# --- What a refusal may say (D5) --------------------------------------------------------------


def test_the_restated_reason_cap_is_the_hub_s():
    """`mcp_server.py` may not import the Hub, so the cap is restated there (task 2.4). Pydantic 2
    keeps a field's `max_length` in its `.metadata` as `MaxLen`, not as an attribute."""
    # Unimportable only where the Hub's dependencies are stubbed; anywhere else, every API test
    # would fail beside this one.
    agent_actions = pytest.importorskip("hub.api.v1.agent_actions")
    from hub import mcp_server

    caps = [
        m.max_length
        for m in agent_actions.PermissionDecisionCreate.model_fields["reason"].metadata
        if hasattr(m, "max_length")
    ]
    assert caps == [mcp_server.MAX_REASON_CHARS]


def _longest_reasons(workspace):
    """A refusal of every kind, each quoting a word far past the bound."""
    long = "x" * 5000
    return {
        "outside": _decide("Bash", {"command": f"cat /{long}"}),
        "network": _decide("Bash", {"command": f"curl https://example.com/{long}"}),
        "unchecked": _decide("Bash", {"command": f"cat $HOME/{long}"}),
        "continues": _decide("Bash", {"command": f"cp a ../work={long}/z"}),
        "file tool": _decide("Write", {"file_path": str(workspace.parent / long)}),
        "unprintable": _decide("Bash", {"command": "cat /" + "\U000e0001" * 5000}),
    }


def test_no_refusal_is_longer_than_the_hub_records(workspace, monkeypatch):
    """The longest fixed wording plus a quotation bounded as rendered stays under the cap, so the
    Hub records every refusal rather than rejecting its report (D5)."""
    from hub import mcp_server

    monkeypatch.setenv("HUB_URL", _HUB)
    for kind, decision in _longest_reasons(workspace).items():
        assert decision["allow"] is False, kind
        assert len(decision["reason"]) <= mcp_server.MAX_REASON_CHARS, kind
        assert "…" in decision["reason"], kind


def test_a_long_url_is_refused_within_the_cap(workspace, monkeypatch):
    """A 1,200-character URL gave a 1,224-character reason under the whole-command regex, which the
    Hub rejects, so the refusal went unrecorded. The quotation is now bounded."""
    from hub import mcp_server

    monkeypatch.setenv("HUB_URL", _HUB)
    url = "https://example.com/" + "a" * (1200 - len("https://example.com/"))
    assert len(url) == 1200
    decision = _decide("Bash", {"command": f"curl -s {url}"})
    assert decision["allow"] is False
    assert decision["reason"].startswith("'https://example.com/aaa")
    assert len(decision["reason"]) <= mcp_server.MAX_REASON_CHARS


def test_the_bound_is_on_the_rendered_quotation_not_the_word(workspace, monkeypatch):
    """`repr` renders each U+E0001 as ten characters, so 200 characters of word can render as
    2,000. The bound applies after rendering (D5, row L1)."""
    from hub import mcp_server

    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide("Bash", {"command": "curl https://example.com/x" + "\U000e0001" * 400})
    assert decision["allow"] is False
    assert "network address" in decision["reason"]
    assert len(decision["reason"]) <= mcp_server.MAX_REASON_CHARS


@pytest.mark.parametrize(
    "tool, tool_input",
    [
        pytest.param("Bash", {"command": "cat sub/a\x00b"}, id="shell"),
        pytest.param("Bash", {"command": "cat /tmp/a\x00b"}, id="shell-absolute"),
        pytest.param("Bash", {"command": "curl file:///tmp/a%00b"}, id="file-url"),
        pytest.param("Write", {"file_path": "a\x00b"}, id="file-tool"),
    ],
)
def test_a_nul_byte_still_gets_a_decision(workspace, monkeypatch, tool, tool_input):
    """`posixpath.realpath` raises ValueError on a NUL byte, which once escaped `_decide` on Linux,
    CI's platform, although its docstring promises every input a decision (D5, task 2.5). Either
    answer is acceptable; raising is not."""
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide(tool, tool_input)
    assert decision["allow"] in (True, False)
    assert isinstance(decision["reason"], str)


@pytest.mark.parametrize(
    "command",
    [
        "echo 'unbalanced",
        'echo "unbalanced $(cat',
        "echo `unbalanced",
        "echo \\",
        "$(" * 50 + "cat /etc/x" + ")" * 50,
        "\x00\x01\x02 \\\\ '\" ` $ ${ $( %%",
    ],
)
@pytest.mark.parametrize("tool", ["Bash", "PowerShell", "Task"])
def test_the_reader_is_total(workspace, monkeypatch, tool, command):
    """No string makes the reader raise: an unbalanced quote runs to the end, and nesting past its
    bound falls back to reading the whole text (D1)."""
    monkeypatch.setenv("HUB_URL", _HUB)
    decision = _decide(tool, {"command": command})
    assert decision["allow"] in (True, False)


def test_a_path_nested_past_the_bound_is_still_read(workspace, monkeypatch):
    """Fifty nested substitutions exceed what is lexed; the whole-text fallback still sees
    `/etc/x`."""
    monkeypatch.setenv("HUB_URL", _HUB)
    command = "echo " + "$(" * 50 + "cat /etc/x" + ")" * 50
    decision = _decide("Bash", {"command": command})
    assert decision["allow"] is False
    assert "/etc/x" in decision["reason"]


# --- The wire shape ---------------------------------------------------------------------------


def _call_tool_over_stdio(
    arguments: dict, workspace_dir: str, env_overrides: dict | None = None
) -> dict:
    """Speak JSON-RPC to a real spawn of the MCP server and return the raw tools/call result.

    Asserting on the Python return value cannot see `structuredContent`, which is added by
    FastMCP during serialisation and is exactly what breaks the contract.
    """
    env = dict(os.environ)
    env["AW_WORKSPACE_DIR"] = workspace_dir
    env.pop("AW_RUN_TOKEN", None)
    env.update(env_overrides or {})
    proc = subprocess.Popen(
        [sys.executable, str(MCP_SERVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env=env,
    )

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def read_response():
        # stdin stays open throughout: closing it before the call is answered shuts the server
        # down mid-handshake and the tools/call response never arrives.
        while True:
            line = proc.stdout.readline()
            if not line:
                raise AssertionError("server closed stdout before responding")
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            }
        )
        read_response()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "approve_tool_call", "arguments": arguments},
            }
        )
        return read_response()["result"]
    finally:
        proc.kill()


def test_response_carries_no_structured_content():
    """FastMCP derives `structuredContent` from a return annotation. With it present, Claude
    does not honour an `allow` — the action is refused with no error anywhere, which is
    indistinguishable from a deny. Adding a return annotation to `approve_tool_call` is enough
    to reintroduce this, so it is asserted against the wire, not the Python value."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _call_tool_over_stdio(
            {
                "tool_name": "Write",
                "input": {"file_path": "a.txt", "content": "hi"},
                "tool_use_id": "toolu_wire",
            },
            workspace_dir=tmp,
        )
    assert "structuredContent" not in result
    assert result["content"][0]["type"] == "text"
    answer = json.loads(result["content"][0]["text"])
    assert answer["behavior"] == "allow"
    assert answer["updatedInput"] == {"file_path": "a.txt", "content": "hi"}


def _shell_answer_over_stdio(command: str) -> dict:
    """The answer Claude receives for one `Bash` command, on the default posture, in a real spawn
    whose environment names the run's own Hub."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _call_tool_over_stdio(
            {"tool_name": "Bash", "input": {"command": command}, "tool_use_id": "toolu_url"},
            workspace_dir=tmp,
            env_overrides={"HUB_URL": _HUB, "AW_PERMISSION_POSTURE": ""},
        )
    assert "structuredContent" not in result
    assert result.get("isError") in (False, None)
    return json.loads(result["content"][0]["text"])


def test_a_network_address_is_refused_on_the_wire():
    """The reason Claude is given names the URL as a network address, not as a path."""
    answer = _shell_answer_over_stdio("curl -s https://example.com/x")
    assert answer["behavior"] == "deny"
    assert answer["message"].startswith("Denied: 'https://example.com/x' is a network address")


def test_the_run_s_own_hub_is_allowed_on_the_wire():
    """The documented HTTP form reaches its own Hub through the real server, not only `_decide`."""
    answer = _shell_answer_over_stdio('curl -s "$HUB_URL/api/v1/agent-actions/tasks"')
    assert answer["behavior"] == "allow"
    assert answer["updatedInput"] == {"command": 'curl -s "$HUB_URL/api/v1/agent-actions/tasks"'}


def test_tool_use_id_is_accepted():
    """Claude always sends it. A signature omitting it fails every call with a validation error,
    which the model reports as a broken approval system rather than a refusal."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _call_tool_over_stdio(
            {"tool_name": "Write", "input": {"file_path": "a.txt"}, "tool_use_id": "toolu_x"},
            workspace_dir=tmp,
        )
    assert result.get("isError") in (False, None)


# --- The posture ------------------------------------------------------------------------------


def _claude_argv(**kwargs):
    return build_command(
        runner="claude", cli="claude", prompt="hi", mcp_command=["py", "s.py"], **kwargs
    )


def test_the_workspace_posture_emits_both_flags_exactly_once():
    argv = _claude_argv(control_overrides={"permission_mode": WORKSPACE_PERMISSION_MODE})
    assert argv.count("--permission-mode") == 1
    assert argv[argv.index("--permission-mode") + 1] == "manual"
    assert argv.count("--permission-prompt-tool") == 1
    assert argv[argv.index("--permission-prompt-tool") + 1] == CLAUDE_PERMISSION_PROMPT_TOOL


@pytest.mark.parametrize("posture", ["acceptEdits", "bypassPermissions"])
def test_postures_that_decide_nothing_emit_no_approver_flag(posture):
    """`manual` is excluded deliberately — since 2026-08-07 it routes to the operator through the
    same approver, and has its own test below."""
    argv = _claude_argv(control_overrides={"permission_mode": posture})
    assert "--permission-prompt-tool" not in argv
    assert argv[argv.index("--permission-mode") + 1] == posture


def test_the_default_posture_is_the_workspace_one_and_names_its_approver():
    """Changed 2026-08-13. The previous default accepted edits and still prompted for `Bash`,
    which headless nothing answers — an agent could write code and never run it. `workspace` is
    answered by the Hub against the run's own directory, so it is narrower for writes and permits
    the execution an agent needs to produce evidence about its own work."""
    argv = _claude_argv()
    assert DEFAULT_CLAUDE_PERMISSION_MODE == WORKSPACE_PERMISSION_MODE
    # `workspace` is this repo's name for it; Claude is told `manual` plus an approver.
    assert argv[argv.index("--permission-mode") + 1] == "manual"
    assert argv.count("--permission-prompt-tool") == 1
    assert argv[argv.index("--permission-prompt-tool") + 1] == CLAUDE_PERMISSION_PROMPT_TOOL


def test_the_default_falls_back_when_nothing_can_answer_it():
    """`workspace` without the Hub's server names an approver that is not there, and every call
    fails — exactly the failure the old default was introduced to end. A run that cannot be
    answered gets the posture that needs no answering."""
    argv = build_command(runner="claude", cli="claude", prompt="hi")
    assert argv[argv.index("--permission-mode") + 1] == (
        DEFAULT_CLAUDE_PERMISSION_MODE_WITHOUT_APPROVER
    )
    assert "--permission-prompt-tool" not in argv


def test_yolo_is_unaffected():
    argv = _claude_argv(yolo=True)
    assert "--dangerously-skip-permissions" in argv
    assert "--permission-prompt-tool" not in argv
    assert "--permission-mode" not in argv


def test_no_approver_is_named_when_no_mcp_server_is_configured():
    """Naming a tool that will not be there makes every call fail, which reads as a Hub bug."""
    argv = build_command(
        runner="claude",
        cli="claude",
        prompt="hi",
        control_overrides={"permission_mode": WORKSPACE_PERMISSION_MODE},
    )
    assert "--permission-prompt-tool" not in argv
    assert argv[argv.index("--permission-mode") + 1] == "manual"


def test_the_posture_is_labelled_by_what_it_permits():
    control = get_provider("claude").control("permission_mode")
    value = next(v for v in control.values if v.id == WORKSPACE_PERMISSION_MODE)
    assert value.label == "Workspace only"
    assert "manual" not in value.label.lower()


def test_the_catalog_default_still_accepts_edits():
    assert get_provider("claude").control("permission_mode").default == "acceptEdits"


def test_other_controls_still_render_through_their_own_template():
    """The per-value override must not disturb controls that do not use one."""
    assert render_control_args("claude", {"effort": "high"}) == ["--effort", "high"]


# --- The approver is not advertised -----------------------------------------------------------


def test_generated_context_does_not_advertise_the_approver():
    from hub.api.v1.agents import _tool_surface_lines

    text = "\n".join(_tool_surface_lines())
    assert "approve_tool_call" not in text
    assert "send_message" in text
    assert "create_job" in text


# --- The operator-answered posture ------------------------------------------------------------


def test_ask_me_also_routes_through_the_approver():
    """`manual` used to mean "ask" with nothing able to answer, so it refused everything."""
    argv = _claude_argv(control_overrides={"permission_mode": "manual"})
    assert argv[argv.index("--permission-mode") + 1] == "manual"
    assert argv[argv.index("--permission-prompt-tool") + 1] == CLAUDE_PERMISSION_PROMPT_TOOL


def test_the_two_approver_postures_are_spelled_the_same_on_the_command_line():
    """Both select `manual`; only AW_PERMISSION_POSTURE separates who answers."""
    workspace = _claude_argv(control_overrides={"permission_mode": WORKSPACE_PERMISSION_MODE})
    operator = _claude_argv(control_overrides={"permission_mode": "manual"})
    assert workspace == operator


def test_the_operator_posture_constant_agrees_across_the_two_modules():
    """`mcp_server` restates it rather than importing, to stay standalone-spawnable."""
    from hub import mcp_server, runner_commands

    assert mcp_server.OPERATOR_POSTURE == runner_commands.OPERATOR_POSTURE


def test_an_unreachable_hub_denies_rather_than_hanging(workspace, monkeypatch):
    """The operator cannot be asked if the request never lands, and a run that waits on an
    answer nobody recorded waits forever."""
    from hub import mcp_server

    monkeypatch.setenv("AW_PERMISSION_POSTURE", mcp_server.OPERATOR_POSTURE)
    monkeypatch.setattr(
        mcp_server, "_hub_request", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down"))
    )
    answer = json.loads(mcp_server.approve_tool_call("Write", {"file_path": "a.txt"}, "tu"))
    assert answer["behavior"] == "deny"
    assert "could not be asked" in answer["message"]


def test_an_unanswered_request_is_denied_when_the_wait_runs_out(workspace, monkeypatch):
    """Never returns nothing and never waits forever — an unanswered request suspends the turn.

    Task 6.5: the denial is only half of it. Giving up without telling the Hub is the defect this
    whole change exists to fix — the run stops waiting, the card does not, and the operator's
    approval is recorded against an action that never ran.
    """
    from hub import mcp_server

    monkeypatch.setenv("AW_PERMISSION_POSTURE", mcp_server.OPERATOR_POSTURE)
    monkeypatch.setattr(mcp_server, "OPERATOR_DECISION_TIMEOUT", 0.05)
    monkeypatch.setattr(mcp_server, "OPERATOR_POLL_SECONDS", 0.01)
    calls = []

    def hub(method, path, *_a, **_k):
        calls.append((method, path))
        if method == "POST" and path == "/permission-requests":
            return {"id": "perm-1", "status": "pending"}
        return {"id": "perm-1", "status": "pending"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    answer = json.loads(mcp_server.approve_tool_call("Write", {"file_path": "a.txt"}, "tu"))
    assert answer["behavior"] == "deny"
    assert "no operator answered" in answer["message"]
    assert ("POST", "/permission-requests/perm-1/expire") in calls


def test_the_denial_survives_a_hub_that_cannot_be_told_about_it(workspace, monkeypatch):
    """Task 6.4 — reporting the timeout is best-effort on exactly `_report_decision`'s terms.

    The decision is already made by the time the report goes out, so a Hub that is down must not
    turn it into an exception, a hang, or a different answer. The run's end sweeps what this
    fails to report (design D1), which is why it is allowed to fail at all.
    """
    from hub import mcp_server

    monkeypatch.setenv("AW_PERMISSION_POSTURE", mcp_server.OPERATOR_POSTURE)
    monkeypatch.setattr(mcp_server, "OPERATOR_DECISION_TIMEOUT", 0.05)
    monkeypatch.setattr(mcp_server, "OPERATOR_POLL_SECONDS", 0.01)

    def hub(method, path, *_a, **_k):
        if path.endswith("/expire"):
            raise RuntimeError("hub is down")
        return {"id": "perm-1", "status": "pending"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    started = time.monotonic()
    answer = json.loads(mcp_server.approve_tool_call("Write", {"file_path": "a.txt"}, "tu"))
    assert answer["behavior"] == "deny"
    assert "no operator answered" in answer["message"]
    # Undelayed: a failed report must not add a retry or a backoff to a turn already held open.
    assert time.monotonic() - started < 5


def test_an_expired_request_is_not_reported_to_the_agent_as_a_refusal(workspace, monkeypatch):
    """Nobody refused it. Before the sweep existed nothing could expire a Claude row, so this
    branch was unreachable; now that the run's end can close a request out from under a live
    poll, saying "the operator refused this action" would invent a person who was not there."""
    from hub import mcp_server

    monkeypatch.setenv("AW_PERMISSION_POSTURE", mcp_server.OPERATOR_POSTURE)
    monkeypatch.setattr(mcp_server, "OPERATOR_POLL_SECONDS", 0.01)

    def hub(method, path, *_a, **_k):
        if method == "POST":
            return {"id": "perm-1", "status": "pending"}
        return {"id": "perm-1", "status": "expired"}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    answer = json.loads(mcp_server.approve_tool_call("Write", {"file_path": "a.txt"}, "tu"))
    assert answer["behavior"] == "deny"
    assert "operator" not in answer["message"]
    assert "no longer open" in answer["message"]


@pytest.mark.parametrize(
    ("verdict", "behavior"), [("allowed", "allow"), ("denied", "deny"), ("expired", "deny")]
)
def test_the_operators_answer_is_returned_to_the_run(workspace, monkeypatch, verdict, behavior):
    from hub import mcp_server

    monkeypatch.setenv("AW_PERMISSION_POSTURE", mcp_server.OPERATOR_POSTURE)
    monkeypatch.setattr(mcp_server, "OPERATOR_POLL_SECONDS", 0.01)

    def hub(method, path, *_a, **_k):
        if method == "POST":
            return {"id": "perm-1", "status": "pending"}
        return {"id": "perm-1", "status": verdict}

    monkeypatch.setattr(mcp_server, "_hub_request", hub)
    answer = json.loads(mcp_server.approve_tool_call("Write", {"file_path": "a.txt"}, "tu"))
    assert answer["behavior"] == behavior


def test_the_hubs_own_tools_are_not_put_to_the_operator(workspace, monkeypatch):
    """Asking a human to approve each send_message would make collaboration unusable."""
    from hub import mcp_server

    monkeypatch.setenv("AW_PERMISSION_POSTURE", mcp_server.OPERATOR_POSTURE)

    def explode(*_a, **_k):
        raise AssertionError("the operator must not be asked about the Hub's own tools")

    monkeypatch.setattr(mcp_server, "_ask_operator", explode)
    monkeypatch.setattr(mcp_server, "_report_decision", lambda *a, **k: None)
    answer = json.loads(
        mcp_server.approve_tool_call("mcp__agentweave__send_message", {"to_agent": "b"}, "tu")
    )
    assert answer["behavior"] == "allow"


def test_the_workspace_posture_never_asks_the_operator(workspace, monkeypatch):
    from hub import mcp_server

    monkeypatch.delenv("AW_PERMISSION_POSTURE", raising=False)
    monkeypatch.setattr(
        mcp_server, "_ask_operator", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked"))
    )
    answer = json.loads(mcp_server.approve_tool_call("Write", {"file_path": "a.txt"}, "tu"))
    assert answer["behavior"] == "allow"


# --- Codex postures ---------------------------------------------------------------------------


def test_codex_offers_the_same_postures_by_the_same_names():
    """An operator should not have to learn two vocabularies for the same choice."""
    claude = get_provider("claude").control("permission_mode")
    codex = get_provider("codex").control("permission_mode")
    assert [v.id for v in codex.values] == [v.id for v in claude.values]
    assert [v.label for v in codex.values] == [v.label for v in claude.values]
    assert codex.default == "acceptEdits"


def test_the_codex_posture_reaches_no_command_line():
    """Codex approvals are answered over the app-server protocol, not selected by a flag."""
    assert render_control_args("codex", {"permission_mode": WORKSPACE_PERMISSION_MODE}) == []
    assert render_control_args("codex", {"permission_mode": "manual"}) == []


def test_codex_workspace_posture_allows_inside_and_denies_outside(tmp_path):
    from hub.codex_appserver import COMMAND_APPROVAL_METHOD, decide_approval

    ws = tmp_path / "work"
    ws.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    def decide(cwd):
        return decide_approval(
            COMMAND_APPROVAL_METHOD,
            {"command": "ls", "cwd": str(cwd)},
            yolo=False,
            own_server_name="agentweave",
            posture=WORKSPACE_PERMISSION_MODE,
            workspace=str(ws),
        )

    assert decide(ws)["decision"] == "accept"
    assert decide(outside)["decision"] == "decline"


def test_codex_workspace_posture_denies_when_the_boundary_is_unknown(tmp_path):
    from hub.codex_appserver import COMMAND_APPROVAL_METHOD, decide_approval

    decision = decide_approval(
        COMMAND_APPROVAL_METHOD,
        {"command": "ls", "cwd": str(tmp_path)},
        yolo=False,
        own_server_name="agentweave",
        posture=WORKSPACE_PERMISSION_MODE,
        workspace=None,
    )
    assert decision["decision"] == "decline"


def test_codex_operator_posture_asks_rather_than_deciding():
    from hub.codex_appserver import ASK_OPERATOR, COMMAND_APPROVAL_METHOD, decide_approval
    from hub.runner_commands import OPERATOR_POSTURE

    decision = decide_approval(
        COMMAND_APPROVAL_METHOD,
        {"command": "ls", "cwd": "/anywhere"},
        yolo=False,
        own_server_name="agentweave",
        posture=OPERATOR_POSTURE,
    )
    assert decision == ASK_OPERATOR
    # The sentinel must never be a valid protocol reply.
    assert decision["decision"] not in ("accept", "decline")


def test_codex_without_a_posture_behaves_exactly_as_before():
    from hub.codex_appserver import COMMAND_APPROVAL_METHOD, decide_approval

    params = {"command": "ls", "cwd": "/anywhere"}
    kw = {"own_server_name": "agentweave", "posture": None}
    assert decide_approval(COMMAND_APPROVAL_METHOD, params, yolo=True, **kw)["decision"] == "accept"
    assert (
        decide_approval(COMMAND_APPROVAL_METHOD, params, yolo=False, **kw)["decision"] == "decline"
    )


def test_codex_approval_subject_carries_what_the_operator_needs():
    from hub.codex_appserver import (
        COMMAND_APPROVAL_METHOD,
        FILE_CHANGE_APPROVAL_METHOD,
        approval_subject,
    )

    command = approval_subject(
        COMMAND_APPROVAL_METHOD, {"command": "rm -rf x", "cwd": "/w", "reason": "cleanup"}
    )
    assert command == {"command": "rm -rf x", "cwd": "/w", "reason": "cleanup"}

    # File-change approvals carry no per-file paths of their own; grantRoot is all the *request*
    # has. Unresolved, the subject is exactly what it always was.
    change = approval_subject(FILE_CHANGE_APPROVAL_METHOD, {"grantRoot": "/w", "reason": "edit"})
    assert change == {"grantRoot": "/w", "reason": "edit"}

    # But the item the approval names does carry them, and F107 is that the Hub held the item and
    # showed the operator the string "a file change" anyway.
    named = approval_subject(
        FILE_CHANGE_APPROVAL_METHOD,
        {"itemId": "item-1", "grantRoot": None, "reason": None},
        {
            "id": "item-1",
            "type": "fileChange",
            "changes": [{"path": "a.py", "diff": "a patch body"}],
        },
    )
    assert named == {"grantRoot": None, "reason": None, "paths": ["a.py"]}

    # Paths, not diffs. The card is one line read under a run's timeout; a patch body pasted into
    # it buries the filenames it exists to show, and the diff is already in the timeline.
    assert "diff" not in json.dumps(named)

    # A malformed item is not a path. Nothing here may raise: this runs while a turn is blocked.
    for junk in (None, {}, {"changes": "not-a-list"}, {"changes": [{"path": 1}, {}, None]}):
        assert "paths" not in approval_subject(FILE_CHANGE_APPROVAL_METHOD, {}, junk)


def test_codex_posture_mapping():
    from hub.api.v1.agent_trigger import _codex_posture
    from hub.runner_commands import OPERATOR_POSTURE

    assert _codex_posture("manual") == OPERATOR_POSTURE
    assert _codex_posture(WORKSPACE_PERMISSION_MODE) == WORKSPACE_PERMISSION_MODE
    assert _codex_posture("acceptEdits") is None
    assert _codex_posture(None) is None
