"""F4 — a turn triggered with a specification document open loses file-write tools.

`openspec/changes/2026-08-17-authoring-rigor-and-scope` design D6/tasks 5.1/5.3. Two runner
branches, both needing the restriction applied *unconditionally* — including under `yolo=True`,
which is exactly the case round 2 of that change's spec review found unaddressed, so it is the one
most worth a regression test here.
"""

from hub.runner_adapters import build_command


def test_claude_gets_disallowed_tools_when_spec_document_is_open():
    command = build_command(
        runner="claude", cli="claude", prompt="hello", restrict_spec_writes=True
    )
    assert "--disallowedTools" in command
    assert command[command.index("--disallowedTools") + 1] == "Edit,MultiEdit,Write,NotebookEdit"


def test_claude_restriction_holds_under_yolo():
    command = build_command(
        runner="claude",
        cli="claude",
        prompt="hello",
        yolo=True,
        restrict_spec_writes=True,
    )
    assert "--disallowedTools" in command
    assert command[command.index("--disallowedTools") + 1] == "Edit,MultiEdit,Write,NotebookEdit"
    assert "--dangerously-skip-permissions" in command  # yolo's own flag is untouched


def test_claude_restriction_coexists_with_the_mcp_allowed_tools_flag():
    """`--disallowedTools` and `--allowedTools mcp__agentweave__*` must both be present — confirmed
    against the real Claude CLI's own --help (both are documented, independent options)."""
    command = build_command(
        runner="claude",
        cli="claude",
        prompt="hello",
        mcp_command=["python", "mcp_server.py"],
        restrict_spec_writes=True,
    )
    assert "--disallowedTools" in command
    assert "--allowedTools" in command
    assert command[command.index("--allowedTools") + 1] == "mcp__agentweave__*"


def test_claude_command_is_unaffected_when_no_document_is_open():
    with_flag = build_command(runner="claude", cli="claude", prompt="hello")
    assert "--disallowedTools" not in with_flag


def test_codex_gets_sandbox_read_only_when_spec_document_is_open():
    command = build_command(runner="codex", cli="codex", prompt="hello", restrict_spec_writes=True)
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "read-only"


def test_codex_restriction_replaces_the_yolo_branch_rather_than_layering_on_it():
    command = build_command(
        runner="codex",
        cli="codex",
        prompt="hello",
        yolo=True,
        restrict_spec_writes=True,
    )
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert "--dangerously-bypass-approvals-and-sandbox" not in command


def test_codex_command_is_unaffected_when_no_document_is_open():
    command = build_command(runner="codex", cli="codex", prompt="hello")
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"


def test_codex_yolo_without_restriction_is_unchanged_from_before_this_change():
    command = build_command(runner="codex", cli="codex", prompt="hello", yolo=True)
    assert "--dangerously-bypass-approvals-and-sandbox" in command
    assert "--sandbox" not in command


# --- `a-run-reaches-the-hub-without-mcp` task 1.15 (Claude half), design D16 ---------------------


def _disallowed(command):
    return command[command.index("--disallowedTools") + 1]


def test_a_spec_turn_told_the_call_command_keeps_write_for_its_args_file():
    """D16: the args-file write is the one write a spec turn told `aw-tool` keeps, or it could not
    call `submit_spec_document`. Claude's rules have no negation, so `Write` stays whole; the other
    three are still removed, and a run told MCP keeps today's four."""
    for yolo in (False, True):
        shim = build_command(
            runner="claude",
            cli="claude",
            prompt="hello",
            yolo=yolo,
            restrict_spec_writes=True,
            described_access_path="shim",
        )
        assert _disallowed(shim) == "Edit,MultiEdit,NotebookEdit"
        told_mcp = build_command(
            runner="claude",
            cli="claude",
            prompt="hello",
            yolo=yolo,
            restrict_spec_writes=True,
            described_access_path="mcp",
        )
        assert _disallowed(told_mcp) == "Edit,MultiEdit,Write,NotebookEdit"
        default = build_command(
            runner="claude", cli="claude", prompt="hello", yolo=yolo, restrict_spec_writes=True
        )
        assert _disallowed(default) == "Edit,MultiEdit,Write,NotebookEdit"
