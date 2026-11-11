"""F1161, second half -- the arguments-file write a Codex spec turn asks for is the Hub's own.

Re-driven 2026-11-11 on real Codex 0.167.1: the prompt was fixed and the agent asked, exactly as
told, to run `Set-Content -Path '.agentweave/calls/1.json' ...` -- and was declined. On Windows the
`command` of `item/commandExecution/requestApproval` is not the command the model wrote but the
shell invocation wrapping it, Rust-debug-quoted (`format!("{:?} -Command {:?}", exe, cmd)`): every
backslash doubled and every `"` escaped. `_hub_own_call` judges a bare command and answered None.

The strings below are what a real `codex app-server` sent, captured verbatim from its approval
requests (testbed/scratch/f325probe/probe4.py), not composed from memory.
"""

import pytest

from hub import codex_appserver
from hub.codex_appserver import unwrap_shell_command
from tests.test_a_codex_app_server_spec_turn_keeps_no_write_tools import _command as _approval
from tests.test_a_codex_app_server_spec_turn_keeps_no_write_tools import _run, _session

#: Captured from real Codex 0.167.1 on Windows, the model asked for forward slashes.
WRAPPED_FORWARD = (
    r'"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '
    r'"Set-Content -Path '
    + "'.agentweave/calls/1.json'"
    + r" -Value '{\"a\": 1}' -Encoding utf8"
    + '"'
)
#: Captured likewise, the model asked for backslashes: they arrive doubled.
WRAPPED_BACKSLASH = (
    r'"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '
    r'"Set-Content -Path '
    + r"'.agentweave\\calls\\2.json'"
    + r" -Value '{\"a\": 1}' -Encoding utf8"
    + '"'
)
#: The `aw-tool` call in the same wrapper (the wrapper is Codex's for every command).
WRAPPED_CALL = (
    r'"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '
    r'"aw-tool submit_spec_document .agentweave/calls/1.json"'
)


def test_the_captured_wrappers_unwrap_to_what_the_model_wrote():
    assert unwrap_shell_command(WRAPPED_FORWARD) == (
        "PowerShell",
        "Set-Content -Path '.agentweave/calls/1.json' -Value '{\"a\": 1}' -Encoding utf8",
    )
    assert unwrap_shell_command(WRAPPED_BACKSLASH) == (
        "PowerShell",
        "Set-Content -Path '.agentweave\\calls\\2.json' -Value '{\"a\": 1}' -Encoding utf8",
    )
    assert unwrap_shell_command(WRAPPED_CALL) == (
        "PowerShell",
        "aw-tool submit_spec_document .agentweave/calls/1.json",
    )


@pytest.mark.parametrize(
    "command",
    [
        # Not the wrapper: left as it is, judged as before.
        "Set-Content -Path '.agentweave/calls/1.json' -Value '{}' -Encoding utf8",
        # Anything after the quoted command is not the wrapper.
        r'"C:\\Windows\\powershell.exe" -Command "aw-tool list_tasks"; Remove-Item x',
        # Another executable is not a PowerShell wrapper.
        r'"C:\\Windows\\System32\\cmd.exe" -Command "aw-tool list_tasks"',
        # An escape Rust's quoting never produces.
        r'"C:\\Windows\\powershell.exe" -Command "aw-tool \q"',
        # A second argument before -Command.
        r'"C:\\Windows\\powershell.exe" -NoProfile -Command "aw-tool list_tasks"',
    ],
)
def test_anything_but_exactly_the_wrapper_is_not_unwrapped(command):
    assert unwrap_shell_command(command) is None


@pytest.mark.parametrize("wrapped", [WRAPPED_FORWARD, WRAPPED_CALL])
async def test_a_spec_turn_accepts_the_real_wrapped_hub_own_call(monkeypatch, tmp_path, wrapped):
    (tmp_path / ".agentweave" / "calls").mkdir(parents=True)

    fake = await _run(
        monkeypatch,
        _session(_approval(wrapped, str(tmp_path))),
        posture=None,
        workspace=str(tmp_path),
        restrict=True,
    )

    assert fake.sent_responses == [(7, {"decision": "accept"})]


async def test_a_wrapped_write_outside_the_calls_root_is_still_declined(monkeypatch, tmp_path):
    """The control: unwrapping changes what is read, not the rule it is judged by."""
    (tmp_path / ".agentweave" / "calls").mkdir(parents=True)
    wrapped = (
        r'"C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command '
        r'"Set-Content -Path ' + "'NOTES.md'" + r" -Value 'x' -Encoding utf8" + '"'
    )

    fake = await _run(
        monkeypatch,
        _session(_approval(wrapped, str(tmp_path))),
        posture=None,
        workspace=str(tmp_path),
        restrict=True,
    )

    assert fake.sent_responses == [(7, {"decision": "decline"})]
    assert codex_appserver.unwrap_shell_command(wrapped) is not None
