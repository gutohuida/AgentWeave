"""build_command's control-override rendering (2026-08-04-hub-model-control-and-provisioning).

Table-driven from the catalog's own descriptors: each control renders the argv its ApplySpec
declares, and a resumed Codex invocation keeps its flags before `resume` — the same ordering
`--sandbox` already required.
"""

from hub.runner_commands import build_command


def test_claude_effort_renders_as_a_flag_before_the_prompt():
    command = build_command(
        runner="claude",
        cli="claude",
        prompt="hello",
        control_overrides={"effort": "high"},
    )
    assert "--effort" in command
    assert command[command.index("--effort") + 1] == "high"


def test_codex_effort_renders_as_a_config_override():
    command = build_command(
        runner="codex",
        cli="codex",
        prompt="hello",
        control_overrides={"effort": "high"},
    )
    config_values = [command[i + 1] for i, item in enumerate(command[:-1]) if item == "-c"]
    assert "model_reasoning_effort=high" in config_values


def test_codex_control_args_precede_resume_subcommand():
    command = build_command(
        runner="codex",
        cli="codex",
        prompt="hello",
        session_id="sess-123",
        control_overrides={"effort": "high"},
    )
    resume_index = command.index("resume")
    # Find the specific -c pair carrying the effort override.
    effort_pair_index = next(
        i
        for i, item in enumerate(command)
        if item == "-c" and command[i + 1] == "model_reasoning_effort=high"
    )
    assert effort_pair_index < resume_index


def test_claude_proxy_and_native_render_claude_controls():
    for runner in ("claude_proxy", "native"):
        command = build_command(
            runner=runner,
            cli="claude",
            prompt="hello",
            control_overrides={"effort": "max"},
        )
        assert "--effort" in command
        assert command[command.index("--effort") + 1] == "max"


def test_no_overrides_renders_no_extra_argv():
    baseline = build_command(runner="claude", cli="claude", prompt="hello")
    with_empty = build_command(runner="claude", cli="claude", prompt="hello", control_overrides={})
    assert baseline == with_empty


def test_model_selection_is_unaffected_by_control_overrides():
    command = build_command(
        runner="claude",
        cli="claude",
        prompt="hello",
        model="claude-opus-5",
        control_overrides={"effort": "high"},
    )
    assert "--model" in command
    assert command[command.index("--model") + 1] == "claude-opus-5"
    assert "--effort" in command
