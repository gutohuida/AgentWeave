"""Golden-argv tests for `hub.runner_adapters` (task 1.2).

`argv_golden.json` was captured by `fixtures/runner_adapters/capture_goldens.py` from today's
`hub.runner_commands.build_command`, before group 2 built the adapter package (task 1.1). This
file fails on `ModuleNotFoundError: hub.runner_adapters` until group 2 lands; that is correct
per tasks.md's ordering (goldens/tests first, group 2 second).

Each case is checked two ways (review 2: never `adapter.transport(flags)`, which sends a
no-flags Codex case to app-server and has no `build_launch`):
1. `runner_adapters.build_command(...)` with the golden's own kwargs — the compatibility
   signature D6 keeps.
2. `get_adapter(runner).stream_transport().build_launch(LaunchRequest(...))`, with `axes`
   derived from `mcp_command` by truthiness (design D6, review 8.1) the same way `build_command`
   derives them internally.
"""

import json
from pathlib import Path

import pytest

from hub.runner_adapters import AccessAxes, LaunchRequest, build_command, get_adapter

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "runner_adapters"
GOLDEN_PATH = FIXTURES_DIR / "argv_golden.json"

with open(GOLDEN_PATH, encoding="utf-8") as f:
    GOLDEN_CASES = json.load(f)


def _axes_for(runner: str, mcp_command) -> AccessAxes:
    """Reproduce `build_command`'s truthiness-derived axes (design D4/D6) for a stream
    transport: `mcp_command=[]` is falsy, same as `None` — no server, no approver, default
    posture (review 8.1's own case, task 1.1). Only Claude's stream transport has a live
    approver; Codex `exec` never does (design D4's fifth row)."""
    tool_surface = "mcp" if mcp_command else "none"
    plane = "mcp" if tool_surface == "mcp" else "cli"
    approvals = "mcp_permission_tool" if (runner == "claude" and tool_surface == "mcp") else "none"
    return AccessAxes(tool_surface=tool_surface, approvals=approvals, plane=plane)


def _resolve_context_path(tmp_dir: Path, which: str) -> Path:
    if which == "present":
        path = tmp_dir / "present-context.md"
        path.write_text("context", encoding="utf-8")
        return path
    return tmp_dir / "missing-context.md"


def _case_ids():
    return [case["id"] for case in GOLDEN_CASES]


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=_case_ids())
def test_build_command_matches_golden(case, tmp_path):
    inputs = case["input"]
    context_path = _resolve_context_path(tmp_path, inputs["context_file"])

    argv = build_command(
        runner=inputs["runner"],
        cli=inputs["cli"],
        prompt=inputs["prompt"],
        model=inputs["model"],
        context_file=context_path,
        session_id=inputs["session_id"],
        yolo=inputs["yolo"],
        mcp_command=inputs["mcp_command"],
        extra_flags=inputs["extra_flags"],
        control_overrides=inputs["control_overrides"],
        restrict_spec_writes=inputs["restrict_spec_writes"],
    )
    normalised = [arg.replace(str(context_path), "<CTX>") for arg in argv]
    assert normalised == case["argv"]


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=_case_ids())
def test_build_launch_matches_golden(case, tmp_path):
    inputs = case["input"]
    context_path = _resolve_context_path(tmp_path, inputs["context_file"])
    adapter = get_adapter(inputs["runner"])
    assert adapter is not None
    transport = adapter.stream_transport()
    assert transport is not None

    req = LaunchRequest(
        prompt=inputs["prompt"],
        model=inputs["model"],
        context_file=context_path,
        session_id=inputs["session_id"],
        yolo=inputs["yolo"],
        mcp_command=inputs["mcp_command"],
        extra_flags=inputs["extra_flags"],
        control_overrides=inputs["control_overrides"],
        restrict_spec_writes=inputs["restrict_spec_writes"],
        axes=_axes_for(inputs["runner"], inputs["mcp_command"]),
    )
    argv = transport.build_launch(req)
    normalised = [arg.replace(str(context_path), "<CTX>") for arg in argv]
    assert normalised == case["argv"]


def test_golden_file_has_enough_cases():
    assert len(GOLDEN_CASES) >= 90
