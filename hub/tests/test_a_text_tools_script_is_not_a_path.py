"""F696: under "Workspace only", a command that only reads was refused because a text tool's
script, pattern or delimiter was read as a path, and every `| while read` loop was refused by
F676's rule.

Measured in real turns (sweep 2026-10-18, group A): `pwd | sed 's/^/PWD=/'` refused as "'/' is
outside your workspace"; `cat README.md | while read l; do echo "$l"; done` refused by F676. The
exemption covers only an operand the tool reads as text, and a sed or awk script only when it
provably writes no file and runs no command -- so every hole F675, F676 and F737 closed stays
closed (the second half of this file).
"""

from __future__ import annotations

import pytest

from hub.mcp_server import _decide


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "work"
    ws.mkdir()
    (ws / "a.txt").write_text("x")
    monkeypatch.setenv("AW_WORKSPACE_DIR", str(ws))
    monkeypatch.delenv("AW_RUN_TOKEN", raising=False)
    return ws


@pytest.mark.parametrize(
    "command",
    [
        # The sweep's measured rows.
        "pwd | sed 's/^/PWD=/'",
        "git status --short | sed 's/^/  /'",
        "sed 's|/usr|x|' a.txt",
        "awk -F/ '{print $1}' a.txt",
        'cat a.txt | while read l; do echo "$l"; done',
        # The same shapes by other routes.
        "sed -n '/^start/,/^end/p' a.txt",
        "sed -e 's#/a#/b#g' -e '/^$/d' a.txt",
        "sed -i.bak 's/\\/old\\//\\/new\\//' a.txt",
        "awk -F, '{print \"/x\" $2}' a.txt",
        "cut -d/ -f2 a.txt",
        "tr '/' '_' < a.txt",
        "cat a.txt | while IFS= read -r line; do printf '%s\\n' \"$line\"; done",
    ],
)
def test_a_read_only_text_command_is_allowed(workspace, command):
    decision = _decide("Bash", {"command": command})
    assert decision["allow"] is True, decision


@pytest.mark.parametrize(
    "command",
    [
        # A script that writes, reads another file or runs a command is judged as before.
        "sed 's/a/b/w /tmp/x' a.txt",
        "sed '1r /etc/passwd' a.txt",
        "sed 'e rm -rf ..' a.txt",
        "sed -e 's|/usr|x|' -e '1r /etc/passwd' a.txt",
        "sed 's/a/b/w .claude/settings.local.json' a.txt",
        "awk '{print > \"/tmp/x\"}' a.txt",
        "awk 'BEGIN{system(\"rm -rf /\")}'",
        "awk 'BEGIN{ARGV[1]=\"/etc/passwd\"; ARGC=2} {print}'",
        # A file operand is still a path.
        "sed -i 's/a/b/' ../x",
        "sed -nf /etc/passwd a.txt",
        "sed --file=/etc/passwd a.txt",
        "awk -f /etc/prog a.txt",
        "cut -d/ -f2 /etc/passwd",
        "tr a b < /etc/passwd",
        # A script the shell changes is not plain text.
        'sed "s/$HOME/x/" a.txt',
        "sed s/a/$(cat p)/ a.txt",
    ],
)
def test_a_text_command_that_reaches_outside_is_still_refused(workspace, command):
    assert _decide("Bash", {"command": command})["allow"] is False


@pytest.mark.parametrize(
    "command",
    [
        'cat names.txt | while read f; do rm -rf "$f"; done',
        'cat names.txt | while read f; do echo x > "$f"; done',
        'cat names.txt | while read f; do echo $(rm "$f"); done',
        'cat names.txt | while read f; do echo "$f"; done | xargs rm',
        'cat names.txt | while read -d x f; do echo "$f"; done',
    ],
)
def test_a_while_loop_that_acts_on_what_it_read_is_still_refused(workspace, command):
    decision = _decide("Bash", {"command": command})
    assert decision["allow"] is False, decision
    assert "what another command outputs" in decision["reason"]
