"""A turn whose prompt is too long for a command line still launches (the mender's briefs).

Since 2026-11-18 every mender turn on the operator's Hub failed to spawn with "The filename or
extension is too long": its stall brief embedded the project checkout's whole `git status`
(758 lines), and a Claude turn passes its prompt as `-p <prompt>`, which Windows caps at 32,767
characters for the whole command line.
"""

from __future__ import annotations

import subprocess

from hub.api.v1.agent_trigger import PROMPT_ARGV_LIMIT, spill_long_prompt
from hub.runner_commands import _build_claude_command
from hub.stalls import STATUS_LINES_SHOWN, _capped_status

WINDOWS_COMMAND_LINE_LIMIT = 32_767


def _claude_cmd(prompt: str, context_file) -> list:
    return _build_claude_command(
        cli="claude",
        prompt=prompt,
        model="claude-sonnet-5-5",
        context_file=context_file,
        session_id=None,
        yolo=False,
        approvals="mcp_permission_tool",
        mcp_command=["python", "mcp_server.py"],
    )


def test_an_oversize_prompt_goes_to_a_file_and_the_command_line_fits(tmp_path):
    context_file = tmp_path / ".agentweave" / "context" / "mender.md"
    prompt = "## The project's checkout\n" + " M spec/changes/x/spec.json\n" * 1_400
    assert len(prompt) > WINDOWS_COMMAND_LINE_LIMIT

    cmd = spill_long_prompt(_claude_cmd(prompt, context_file), prompt, context_file)

    assert len(subprocess.list2cmdline(cmd)) < WINDOWS_COMMAND_LINE_LIMIT
    assert cmd[-2] == "-p"
    input_file = context_file.with_name("mender.input.md")
    assert str(input_file) in cmd[-1]
    assert input_file.read_text(encoding="utf-8") == prompt


def test_a_prompt_that_fits_stays_on_the_command_line(tmp_path):
    context_file = tmp_path / "mender.md"
    prompt = "x" * PROMPT_ARGV_LIMIT
    cmd = _claude_cmd(prompt, context_file)

    assert spill_long_prompt(cmd, prompt, context_file) == cmd
    assert not (tmp_path / "mender.input.md").exists()


def test_the_brief_shows_a_bounded_slice_of_a_dirty_checkout():
    status = "\n".join(f"?? knowledge/facts/fct-{i:04d}.json" for i in range(758))

    shown = _capped_status(status)

    assert len(shown.splitlines()) == STATUS_LINES_SHOWN + 1
    assert "718 more" in shown
    assert _capped_status("") == "(clean)"
    assert _capped_status(" M a.py") == " M a.py"
