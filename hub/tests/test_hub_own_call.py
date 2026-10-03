"""The approver recognises the Hub's own call command, exactly (`a-run-reaches-the-hub-without-mcp`, D8).

`_hub_own_call` gives standing -- allowed in every posture, no operator card -- to exactly three
things: the Hub's MCP tools (as before), one shell invocation of the `aw-tool` call command, and
a write of a `.json` file inside `<workspace>/.agentweave/calls/`. "Exactly" is a character
allow-list, not a list of refused syntax. A near miss is never denied by this rule: it falls
through to today's decision (the `workspace` judge, or the card under "Ask me").

Each row asserts the predicate and that `_decide` and `approve_tool_call` agree with it; under
the operator posture `_ask_operator` is patched and whether it was asked is the assertion.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from hub import mcp_server
from hub.mcp_server import _decide, _hub_own_call

OWN = "the Hub's own tools"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    (ws / ".agentweave" / "calls").mkdir(parents=True)
    (ws / ".claude").mkdir()
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)  # reporting fails, and is swallowed
    return ws


@pytest.fixture()
def asked(monkeypatch):
    """Under the operator posture: records each card `approve_tool_call` would open."""
    calls = []

    def fake_ask(tool_name, tool_input, tool_use_id):
        calls.append((tool_name, tool_input))
        return {"allow": False, "reason": "the operator was asked"}

    monkeypatch.setenv("AW_PERMISSION_POSTURE", mcp_server.OPERATOR_POSTURE)
    monkeypatch.setattr(mcp_server, "_ask_operator", fake_ask)
    return calls


def _approve(tool_name, tool_input):
    return json.loads(mcp_server.approve_tool_call(tool_name, tool_input, "tu"))


def _link_dir(link: Path, target: Path) -> None:
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], check=True, capture_output=True
        )
    else:
        link.symlink_to(target, target_is_directory=True)


def _shell(command):
    return ("PowerShell" if os.name == "nt" else "Bash"), {"command": command}


ALLOWED = [
    ("Bash", {"command": "aw-tool create_task .agentweave/calls/1.json"}),
    ("PowerShell", {"command": "aw-tool create_task .agentweave/calls/1.json"}),
    pytest.param(
        "PowerShell",
        {"command": "aw-tool.cmd create_task .agentweave\\calls\\1.json"},
        # A backslash separates paths only on Windows. On POSIX that word is one file name outside
        # the calls root, and the shim reads it the same way, so both refuse it there.
        marks=pytest.mark.skipif(os.name != "nt", reason="backslash paths are Windows paths"),
    ),
    ("PowerShell", {"command": "AW-TOOL list_tasks"}),
    ("PowerShell", {"command": "AW-TOOL.CMD --list"}),
    ("Bash", {"command": "aw-tool list_tasks"}),
    ("Bash", {"command": "aw-tool --list"}),
    ("PowerShell", {"command": "aw-tool --help"}),
    ("mcp__agentweave__send_message", {"to_agent": "x"}),
]


def _writes(ws: Path):
    return [
        ("Write", {"file_path": str(ws / ".agentweave" / "calls" / "x.json")}),
        ("Write", {"path": str(ws / ".agentweave" / "calls" / "x.json")}),  # slice 2's shape
        ("Write", {"file_path": ".agentweave/calls/x.json"}),
        ("Edit", {"file_path": str(ws / ".agentweave" / "calls" / "x.json"), "old_string": "a"}),
        ("MultiEdit", {"file_path": str(ws / ".agentweave" / "calls" / "x.json")}),
    ]


@pytest.mark.parametrize("tool_name, tool_input", ALLOWED)
def test_the_call_command_has_standing_in_every_posture(workspace, asked, tool_name, tool_input):
    assert _hub_own_call(tool_name, tool_input) == OWN
    assert _decide(tool_name, tool_input) == {"allow": True, "reason": OWN}
    assert _approve(tool_name, tool_input)["behavior"] == "allow"
    assert asked == []


def test_an_args_file_write_has_standing_in_every_posture(workspace, asked):
    for tool_name, tool_input in _writes(workspace):
        assert _hub_own_call(tool_name, tool_input) == OWN, (tool_name, tool_input)
        assert _decide(tool_name, tool_input)["reason"] == OWN
        assert _approve(tool_name, tool_input)["behavior"] == "allow"
    assert asked == []


def test_a_caller_in_the_hub_process_passes_the_workspace(workspace, monkeypatch):
    """Slice 2's ACP handler runs in the Hub, whose environment names no workspace."""
    monkeypatch.delenv("AW_WORKSPACE_DIR")
    assert _hub_own_call(*_shell("aw-tool list_tasks")) is None  # no workspace known, no standing
    tool_name, tool_input = "PowerShell", {
        "command": "aw-tool create_task .agentweave/calls/1.json"
    }
    assert _hub_own_call(tool_name, tool_input, workspace=str(workspace)) == OWN
    write = ("Write", {"path": str(workspace / ".agentweave" / "calls" / "1.json")})
    assert _hub_own_call(*write, workspace=str(workspace)) == OWN
    assert _hub_own_call(*write) is None


def test_the_write_tools_are_the_hubs_own_list_restated():
    from hub.workspace_writes import CLAUDE_WRITE_TOOLS

    assert mcp_server._HUB_OWN_WRITE_TOOLS == CLAUDE_WRITE_TOOLS


FALL_THROUGH = [
    # a second command, a pipe, a redirection
    ("Bash", "aw-tool create_task .agentweave/calls/1.json; rm x"),
    ("Bash", "aw-tool create_task .agentweave/calls/1.json | cat"),
    ("Bash", "aw-tool create_task .agentweave/calls/1.json > out"),
    ("PowerShell", "aw-tool create_task .agentweave/calls/1.json; rm x"),
    # PowerShell grouping, script blocks, arrays, quotes: the character allow-list (R2)
    ("PowerShell", "aw-tool list_tasks (.agentweave/calls/1.json)"),
    ("PowerShell", "aw-tool create_task {x}"),
    ("PowerShell", "aw-tool create_task .agentweave/calls/1.json,x"),
    ("PowerShell", "aw-tool 'create_task' .agentweave/calls/1.json"),
    # substitutions and variables
    ("Bash", "aw-tool create_task $(echo x)"),
    ("PowerShell", "aw-tool create_task $env:X"),
    ("PowerShell", "aw-tool create_task %X%"),
    # a path to a launcher is not the launcher
    ("Bash", "./aw-tool list_tasks"),
    ("PowerShell", "C:\\x\\aw-tool.cmd list_tasks"),
    # not a callable tool
    ("Bash", "aw-tool approve_tool_call .agentweave/calls/1.json"),
    ("Bash", "aw-tool nosuch"),
    # the path must be a plain relative .json inside the calls root
    ("Bash", "aw-tool create_task ../calls/1.json"),
    ("Bash", "aw-tool create_task .agentweave/calls/../../x.json"),
    ("Bash", "aw-tool create_task .agentweave/calls/1.txt"),
    ("PowerShell", "aw-tool create_task C:\\w\\.agentweave\\calls\\1.json"),
    ("Bash", "aw-tool create_task /tmp/.agentweave/calls/1.json"),
    ("Bash", "aw-tool create_task .agentweave/calls/1.json .agentweave/calls/2.json"),
    ("Bash", "aw-tool --list .agentweave/calls/1.json"),
    ("PowerShell", "& aw-tool list_tasks"),
    # bash names are exact
    ("Bash", "aw-tool.cmd list_tasks"),
    ("Bash", "Aw-tool list_tasks"),
    # R3: ASCII only, and no leading `-` on the path word
    ("Bash", "aw-tool \u2013list"),
    ("Bash", "aw-tool list_tasks .agentweave/calls/\uff41.json"),
    ("PowerShell", "aw-tool create_task -x.agentweave/calls/1.json"),
    ("Bash", "aw-tool\u00a0list_tasks"),
    ("Bash", "aw-tool\tlist_tasks"),
]


@pytest.mark.parametrize("tool_name, command", FALL_THROUGH)
def test_a_near_miss_falls_through_to_the_card(workspace, asked, tool_name, command):
    assert _hub_own_call(tool_name, {"command": command}) is None
    assert _decide(tool_name, {"command": command}).get("reason") != OWN
    _approve(tool_name, {"command": command})
    assert len(asked) == 1


@pytest.mark.parametrize(
    "tool_name, tool_input",
    [
        ("mcp__other__run", {"command": "aw-tool list_tasks", "target": "x"}),  # foreign tool (R3)
        ("Shell", {"command": "aw-tool list_tasks"}),  # slice 2's unnamed shell never gets standing
        ("Write", {"file_path": ".agentweave/calls/x.py"}),
        ("Write", {"content": "{}"}),  # declares no path
        ("Write", {"path": ""}),
        ("Write", {"file_path": ".agentweave/calls/x.json", "command": "aw-tool list_tasks"}),
        ("Read", {"file_path": ".agentweave/calls/x.json"}),  # not a write tool
    ],
)
def test_other_tools_and_shapes_fall_through(workspace, asked, tool_name, tool_input):
    assert _hub_own_call(tool_name, tool_input) is None
    _approve(tool_name, tool_input)
    assert len(asked) == 1


def test_a_symlinked_file_under_calls_that_points_out_falls_through(workspace, asked, tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    link = workspace / ".agentweave" / "calls" / "out.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks need a privilege here")
    assert _hub_own_call("Write", {"file_path": str(link)}) is None


# --- the calls-root rule (review fix 1, blocking): a linked calls directory holds nothing ---------


def test_a_junctioned_calls_directory_gives_no_standing(tmp_path, monkeypatch, asked):
    ws = tmp_path / "work"
    (ws / ".claude").mkdir(parents=True)
    (ws / ".agentweave").mkdir()
    _link_dir(ws / ".agentweave" / "calls", ws / ".claude")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    settings = ws / ".agentweave" / "calls" / "settings.json"

    for tool_name, tool_input in (
        ("Write", {"file_path": str(settings)}),
        ("Write", {"path": str(settings)}),
        ("Bash", {"command": "aw-tool create_task .agentweave/calls/settings.json"}),
        ("PowerShell", {"command": "aw-tool create_task .agentweave/calls/settings.json"}),
    ):
        assert _hub_own_call(tool_name, tool_input) is None, (tool_name, tool_input)
        _approve(tool_name, tool_input)
    assert len(asked) == 4


def test_a_junctioned_agentweave_directory_gives_no_standing(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "calls").mkdir(parents=True)
    ws.mkdir()
    _link_dir(ws / ".agentweave", elsewhere)
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))

    assert (
        _hub_own_call("Write", {"file_path": str(ws / ".agentweave" / "calls" / "1.json")}) is None
    )
    assert _hub_own_call(*_shell("aw-tool create_task .agentweave/calls/1.json")) is None


def test_a_workspace_reached_through_a_junction_keeps_its_standing(tmp_path, monkeypatch):
    real = tmp_path / "real-ws"
    (real / ".agentweave" / "calls").mkdir(parents=True)
    linked = tmp_path / "linked-ws"
    _link_dir(linked, real)
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(linked))

    assert _hub_own_call(*_shell("aw-tool create_task .agentweave/calls/1.json")) == OWN
    assert _hub_own_call("Write", {"file_path": str(linked / ".agentweave/calls/1.json")}) == OWN


@pytest.mark.skipif(os.name != "nt", reason="case-insensitive paths")
def test_a_differently_cased_calls_path_is_the_same_directory_on_windows(workspace):
    command = "aw-tool create_task .AgentWeave/Calls/1.json"
    assert _hub_own_call("PowerShell", {"command": command}) == OWN


def test_the_predicate_is_total(workspace, monkeypatch, asked):
    """D8 (R3): a raising predicate would turn a fall-through into a refusal."""

    def boom(*args, **kwargs):
        raise OSError("realpath failed")

    monkeypatch.setattr(os.path, "realpath", boom)
    command = {"command": "aw-tool create_task .agentweave/calls/1.json"}
    assert _hub_own_call("Bash", command) is None
    assert _hub_own_call("Write", {"file_path": ".agentweave/calls/1.json"}) is None
    _decide("Bash", command)  # does not raise
    _approve("Bash", command)  # does not raise
    assert len(asked) == 1


# --- case 4: an arguments file written from PowerShell (`an-arguments-file-written-from-
# powershell-is-the-hubs-own`, design D2). The notice's fallback route for case 3's write. ---------

P = "'.agentweave/calls/r.json'"
V = """'{"path":"spec/x.html"}'"""
WRITE_9_10 = f"Set-Content -Path {P} -Value {V} -Encoding utf8"
_PARTS = {"-Path": P, "-Value": V, "-Encoding": "utf8"}
_ORDERS = [
    ("-Path", "-Value", "-Encoding"),
    ("-Path", "-Encoding", "-Value"),
    ("-Value", "-Path", "-Encoding"),
    ("-Value", "-Encoding", "-Path"),
    ("-Encoding", "-Path", "-Value"),
    ("-Encoding", "-Value", "-Path"),
]


def _ps(text):
    return "PowerShell", {"command": text}


def _without_case_4(monkeypatch, tool_name, tool_input):
    """`_decide`'s answer with the new predicate patched off: today's answer."""
    with monkeypatch.context() as m:
        m.setattr(mcp_server, "_hub_own_powershell_write", lambda *a, **k: False)
        return _decide(tool_name, tool_input)


STANDING = [
    WRITE_9_10,
    f"Set-Content -LiteralPath {P} -Value {V} -Encoding utf8",
    f"Set-Content -Path .agentweave/calls/r.json -Value {V} -Encoding utf8",
    *["Set-Content " + " ".join(f"{name} {_PARTS[name]}" for name in order) for order in _ORDERS],
    f"set-content -PATH {P} -value {V} -encoding UTF8",
    f"Set-Content -Path {P} -Value {V} -Encoding 'utf8'",
    f"  Set-Content   -Path  {P}   -Value {V}  -Encoding utf8  ",
    pytest.param(
        f"Set-Content -Path '.agentweave\\calls\\r.json' -Value {V} -Encoding utf8",
        marks=pytest.mark.skipif(os.name != "nt", reason="backslash paths are Windows paths"),
    ),
]


@pytest.mark.parametrize("command", STANDING)
def test_a_powershell_args_file_write_has_standing_in_every_posture(workspace, asked, command):
    """Task 1.1. Before the fix, `_decide` refused the 9.10 form (`'/x.html' is outside your
    workspace`): `test_the_9_10_form_is_refused_by_the_judge_alone` keeps that measurable."""
    assert _hub_own_call(*_ps(command)) == OWN
    assert _decide(*_ps(command)) == {"allow": True, "reason": OWN}
    assert _approve(*_ps(command))["behavior"] == "allow"
    assert asked == []


def test_the_9_10_form_is_refused_by_the_judge_alone(workspace, monkeypatch):
    """What case 4 overrode, until `the-shell-judge-reads-a-word-whole` (design D2) stopped rule 6
    reading an embedded `/` as an absolute tail. Before that change `_decide` refused the 9.10 form
    ('/x.html' is outside your workspace'); now the literal's `/x.html` fragment is read as the
    relative piece it actually is (`spec/x.html`, inside), so this exact literal is no longer
    refused on its own. Case 4 still gives the command standing for every other row in STANDING."""
    answer = _without_case_4(monkeypatch, *_ps(WRITE_9_10))
    assert answer["allow"] is True, answer


@pytest.mark.parametrize(
    "literal",
    [
        "'../x'",
        "'/etc/x'",
        "'C:\\x'",
        "'https://example.com/x'",
        "'a; rm x'",
        "'$(Write-Output x)'",
        "'$env:X'",
        "'a`b'",
        "'it''s'",
        "'line1\nline2'",
        """'{"a":"b/c"}'""",
        "' -Path x -Encoding utf8 '",
        "''",
    ],
)
def test_the_literal_is_not_read(workspace, asked, literal):
    """Task 1.2. PowerShell writes a single-quoted literal verbatim; nothing in it is a path,
    an address or a command."""
    command = f"Set-Content -Path {P} -Value {literal} -Encoding utf8"
    assert _hub_own_call(*_ps(command)) == OWN
    assert _approve(*_ps(command))["behavior"] == "allow"
    assert asked == []


@pytest.mark.parametrize("quote", ["\u2018", "\u2019", "\u201a", "\u201b"])
def test_a_typographic_quote_is_not_one_literal(workspace, monkeypatch, quote):
    """Task 1.3. Measured on 5.1 (R3): each of these closes the literal, and the form below ran
    its second command."""
    command = (
        f"Set-Content -Path {P} -Value 'a{quote}; Set-Content pwned.txt x; Write-Output {quote}' "
        "-Encoding utf8"
    )
    assert _hub_own_call(*_ps(command)) is None
    assert _decide(*_ps(command)) == _without_case_4(monkeypatch, *_ps(command))


@pytest.mark.parametrize("char", ["\x00", "\x1b", "\x7f", "\x01", "\x0b", "\x0c"])
def test_a_control_character_in_the_literal_is_not_one_literal(workspace, char):
    command = f"Set-Content -Path {P} -Value 'a{char}b' -Encoding utf8"
    assert _hub_own_call(*_ps(command)) is None


@pytest.mark.parametrize(
    "value",
    [
        "'say \u201chi\u201d \u201e'",  # typographic double quotes are content in a '...' literal
        "'{\n  \"a\": 1\n}'",
        "'{\r\n  \"a\": 1\r\n}'",
        "'{\t\"a\": 1}'",
    ],
)
def test_content_a_literal_may_hold(workspace, value):
    command = f"Set-Content -Path {P} -Value {value} -Encoding utf8"
    assert _hub_own_call(*_ps(command)) == OWN


NEAR_MISSES = [
    f"Set-Content -Path {P} -Val {V} -Encoding utf8",
    f"Set-Content -Path {P} -Value {V} -Enc utf8",
    f"Set-Content -Pa {P} -Value {V} -Encoding utf8",
    f"Set-Content {P} -Value {V} -Encoding utf8",
    f"Set-Content -Path {P} {V} -Encoding utf8",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8 -Force",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8 -NoNewline",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8 -Stream x",
    f'Set-Content -Path {P} -Value "{{}}" -Encoding utf8',
    f"Set-Content -Path {P} -Value 'a','b' -Encoding utf8",
    f"Set-Content -Path {P} -Value @'\n{{}}\n'@ -Encoding utf8",
    f"Set-Content -Path {P} -Value $x -Encoding utf8",
    f"Set-Content -Path {P} -Value ('a') -Encoding utf8",
    f"Set-Content -Path {P} -Value 'a'(Write-Output x) -Encoding utf8",
    f"Set-Content -Path {P} -Value 'a'b -Encoding utf8",
    f"Set-Content -Path {P} -Value 'a'$x -Encoding utf8",
    f"Set-Content -Path {P} -Value 'a' ,'b' -Encoding utf8",
    f"Set-Content -Path {P} -Value:'a' -Encoding utf8",
    f"Set-Content -PSPath {P} -Value {V} -Encoding utf8",
    f"Set-Content --% -Path {P} -Value {V} -Encoding utf8",
    f"Set-Content \u2013Path {P} -Value {V} -Encoding utf8",
    f"Set-Content -Path {P} \u2014Value {V} -Encoding utf8",
    f"Set-Content -Path {P} -Value {V} \u2015Encoding utf8",
    f"Set-Content\t-Path {P} -Value {V} -Encoding utf8",
    f"Set-Content -Path\u00a0{P} -Value {V} -Encoding utf8",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8NoBOM",
    f"Set-Content -Path {P} -Value {V} -Encoding Unicode",
    f"Set-Content -Path {P} -Path {P} -Value {V} -Encoding utf8",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8; aw-tool list_tasks",
    f"& Set-Content -Path {P} -Value {V} -Encoding utf8",
    f"Set-Content -Path '../calls/r.json' -Value {V} -Encoding utf8",
    f"Set-Content -Path '.agentweave/calls/../r.json' -Value {V} -Encoding utf8",
    f"Set-Content -Path '/tmp/r.json' -Value {V} -Encoding utf8",
    f"Set-Content -Path '.agentweave/calls/*.json' -Value {V} -Encoding utf8",
    f"Set-Content -Path '.agentweave/calls/r.txt' -Value {V} -Encoding utf8",
    f"Set-Content -Path '-r.json' -Value {V} -Encoding utf8",
    f"Set-Content -Path 'r.json' -Value {V} -Encoding utf8",
    f"Add-Content -Path {P} -Value {V} -Encoding utf8",
    f"Out-File -Path {P} -Value {V} -Encoding utf8",
    # Text joined to any other part: each ran code on 5.1 (review).
    f"Set-Content -Path {P}(Write-Output x) -Value {V} -Encoding utf8",
    f"Set-Content -Path {P}$x -Value {V} -Encoding utf8",
    f"Set-Content -Path {P} -Value {V} -Encoding 'utf8'(Write-Output x)",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8(Write-Output x)",
    f"Set-Content -Path .agentweave/calls/$(Write-Output x).json -Value {V} -Encoding utf8",
    f"Set-Content -Path .agentweave/calls/a(b).json -Value {V} -Encoding utf8",
    f'Set-Content -Path ".agentweave/calls/r.json" -Value {V} -Encoding utf8',
    f"Set-Content -Path(Write-Output x) -Value {V} -Encoding utf8",
    f"Set-Content -Path {P} -Value$(Write-Output x) -Encoding utf8",
    f"Set-Content(Write-Output x) -Path {P} -Value {V} -Encoding utf8",
    # Further gaps (review).
    f"Set-Content -Path {P} -Value {V} -Encoding utf8 | Out-Null",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8 > x.txt",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8 # c",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8\nWrite-Output x",
    f"Set-Content -Path {P} -Value {V} -Encoding utf8\r\nWrite-Output x",
    f"Set-Content -Path {P} -Encoding utf8 -Value {V}\nWrite-Output x",
    f"Set-Content -Path {P} -Value {V} -Encoding:utf8",
    f"Set-Content -Path {P} -LiteralPath {P} -Value {V} -Encoding utf8",
    f"Set-Content -Path {P},'x.txt' -Value {V} -Encoding utf8",
    f"Set-Content -Value 'a -Encoding utf8' -Path {P}",
    f"Set-Content -Path {P} -Value 'unterminated -Encoding utf8",
    f"Set-Content -Path {P} -Value {V} -Encoding",
    # A quoted part joined straight to the next parameter: only the "space or end after every
    # part" rule refuses these, since the next word is itself a valid parameter name.
    f"Set-Content -Path {P} -Value {V}-Encoding utf8",
    f"Set-Content -Path {P}-Value {V} -Encoding utf8",
    f"Set-Content -Encoding 'utf8'-Path {P} -Value {V}",
]


@pytest.mark.parametrize("command", NEAR_MISSES)
def test_a_near_miss_of_the_write_falls_through(workspace, asked, monkeypatch, command):
    """Task 1.4: never refused by this rule, and decided exactly as without it."""
    assert _hub_own_call(*_ps(command)) is None
    assert _decide(*_ps(command)) == _without_case_4(monkeypatch, *_ps(command))
    _approve(*_ps(command))
    assert len(asked) == 1


@pytest.mark.parametrize("tool_name", ["Bash", "Shell"])
def test_the_write_has_standing_only_in_powershell(workspace, tool_name):
    """Task 1.5."""
    assert _hub_own_call(tool_name, {"command": WRITE_9_10}) is None


def test_a_junctioned_calls_directory_gives_the_write_no_standing(tmp_path, monkeypatch, asked):
    """Task 1.6, on the existing junction fixture's shape."""
    ws = tmp_path / "work"
    (ws / ".claude").mkdir(parents=True)
    (ws / ".agentweave").mkdir()
    _link_dir(ws / ".agentweave" / "calls", ws / ".claude")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    assert _hub_own_call(*_ps(WRITE_9_10)) is None
    _approve(*_ps(WRITE_9_10))
    assert len(asked) == 1


def test_the_write_predicate_is_total(workspace, monkeypatch, asked):
    """Task 1.9: a raise inside case 4 is a fall-through, never a refusal."""

    def boom(*args, **kwargs):
        raise OSError("realpath failed")

    monkeypatch.setattr(os.path, "realpath", boom)
    assert _hub_own_call(*_ps(WRITE_9_10)) is None
    _decide(*_ps(WRITE_9_10))  # does not raise
    _approve(*_ps(WRITE_9_10))  # does not raise
    assert len(asked) == 1


NOTICE_FORM = "Set-Content -Path '.agentweave/calls/<file>.json' -Value '<json>' -Encoding utf8"


def _notices():
    from hub.api.v1.agents import _tool_surface_lines
    from hub.launchability import access_path_notice

    try:
        mcp_server._decode_args_file(b"\x81\x8d\x8f\x90\x9d\xff")
    except mcp_server._CallUsageError as exc:
        decode_error = str(exc)
    else:  # pragma: no cover -- the bytes decode nowhere this suite runs
        raise AssertionError("the bytes decoded")
    return {
        "preamble": "\n".join(_tool_surface_lines(runner="claude", access_path="shim")),
        "notice": access_path_notice("shim"),
        "decode error": decode_error,
    }


@pytest.mark.parametrize("site", ["preamble", "notice", "decode error"])
def test_each_notice_spells_the_write_out_and_the_filled_form_has_standing(workspace, site):
    """Task 1.10 (design D5): what the run is told is what the grammar accepts."""
    text = _notices()[site]
    assert NOTICE_FORM in text, text
    filled = NOTICE_FORM.replace("<file>", "1").replace("<json>", '{"title":"x"}')
    assert _hub_own_call(*_ps(filled)) == OWN
