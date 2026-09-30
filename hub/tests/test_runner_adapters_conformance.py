"""Conformance tests for `hub.runner_adapters`'s own exports (task 1.5).

No golden capture, unlike 1.1-1.4: these five checks are assertions over the future
module's own exports (`ADAPTERS`, `write_tool_kinds`, `instruction_channel`,
`context_window_source`) against today's real registries (`RUNNER_CLIS`, `CATALOG`,
`workspace_writes.WRITE_TOOLS`) and today's parsers -- nothing needs recording ahead of group 2
landing. This file fails on `ModuleNotFoundError: hub.runner_adapters` until group 2 lands;
that is correct per tasks.md's ordering (goldens/tests first, group 2 second).

**Filed as F471** (`scripts/drive/FINDINGS.md`) while writing this: `RUNNER_CLIS` and `CATALOG`
are already 3-wide (`claude`, `codex`, `copilot` -- migration 0112, `a-copilot-agent-runs-over-acp`,
archived 2026-09-30) although this slice's `ADAPTERS` (design D1) is explicitly 2-wide
(`{"claude": ClaudeAdapter(), "codex": CodexAdapter()}` -- "this change touches no Copilot
code"). Checks (a) and (c) are written here exactly as tasks.md states them, against today's
real registries -- not a hand-shrunk copy of them -- so once group 2 finishes building a
2-member `ADAPTERS` these fail as an assertion, not a collection error, which is group 2/3's
signal to resolve a drift design.md (its R1-R3 passes predate migration 0112) never saw.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import sqlalchemy as sa

from hub.codex_appserver import map_token_usage_notification
from hub.db.models import RUNNER_CLIS, Runner
from hub.model_catalog import CATALOG, model_context_window
from hub.runner_adapters import ADAPTERS, AccessAxes, LaunchRequest, get_adapter
from hub.workspace_writes import WRITE_TOOLS, written_paths

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "runner_adapters"
CLAUDE_STREAM_JSONL = FIXTURES_DIR / "claude_stream.jsonl"
CODEX_EXEC_JSONL = FIXTURES_DIR / "codex_exec.jsonl"


def _ck_runners_cli_clis() -> tuple:
    """The CLI names parsed from `ck_runners_cli`'s own SQL text (task 1.5(a))."""
    constraint = next(
        c
        for c in Runner.__table__.constraints
        if isinstance(c, sa.CheckConstraint) and c.name == "ck_runners_cli"
    )
    return tuple(re.findall(r"'([^']+)'", str(constraint.sqltext)))


# --- (a) tuple(ADAPTERS) == RUNNER_CLIS == tuple(CATALOG) == the constraint's own CLIs --------


def test_adapters_matches_registries_in_order():
    assert tuple(ADAPTERS) == RUNNER_CLIS
    assert tuple(ADAPTERS) == tuple(CATALOG)
    assert tuple(ADAPTERS) == _ck_runners_cli_clis()


@pytest.mark.parametrize("cli", list(ADAPTERS))
def test_catalog_provider_equals_name(cli):
    adapter = get_adapter(cli)
    assert adapter.catalog_provider == adapter.name == cli


# --- (b) GET /runners/launchability-by-provider's key order follows ADAPTERS ------------------


@pytest.mark.asyncio
async def test_launchability_by_provider_key_order_matches_adapters(app, auth_headers):
    resp = await app.get(
        "/api/v1/projects/proj-test/runners/launchability-by-provider", headers=auth_headers
    )
    assert resp.status_code == 200
    assert list(resp.json()["providers"]) == list(ADAPTERS)


# --- (c) the union of write_tool_kinds is WRITE_TOOLS, disjoint, and extracts a real path -----


def test_write_tool_kinds_union_equals_write_tools_and_is_disjoint():
    seen = {}
    for cli, adapter in ADAPTERS.items():
        for tool in adapter.write_tool_kinds:
            assert tool not in seen, f"{tool!r} declared by both {seen.get(tool)!r} and {cli!r}"
            seen[tool] = cli
    assert set(seen) == WRITE_TOOLS


_WELL_FORMED_INPUT = {
    "Write": {"file_path": "/tmp/a.txt"},
    "Edit": {"file_path": "/tmp/a.txt"},
    "MultiEdit": {"file_path": "/tmp/a.txt"},
    "NotebookEdit": {"notebook_path": "/tmp/a.ipynb"},
    "apply_patch": {"changes": [{"path": "a.py", "diff": "patch"}]},
}


@pytest.mark.parametrize("cli", list(ADAPTERS))
def test_written_paths_extracts_a_path_for_every_declared_kind(cli):
    adapter = get_adapter(cli)
    for tool in adapter.write_tool_kinds:
        assert written_paths(tool, _WELL_FORMED_INPUT[tool]) != ()


# --- (d) instruction_channel agrees with argv; the RPC transport has none (F325) --------------


def _build_launch(adapter, *, context_present: bool, tmp_path: Path):
    transport = adapter.stream_transport()
    context_file = tmp_path / ("present.md" if context_present else "missing.md")
    if context_present:
        context_file.write_text("context", encoding="utf-8")
    req = LaunchRequest(
        prompt="hi",
        model=None,
        context_file=context_file,
        session_id=None,
        yolo=False,
        mcp_command=None,
        extra_flags=None,
        control_overrides=None,
        restrict_spec_writes=False,
        axes=AccessAxes(tool_surface="none", approvals="none", plane="cli"),
    )
    return transport, transport.build_launch(req), str(context_file)


@pytest.mark.parametrize("context_present", [True, False])
@pytest.mark.parametrize("cli", list(ADAPTERS))
def test_instruction_channel_agrees_with_argv(cli, context_present, tmp_path):
    adapter = get_adapter(cli)
    transport, argv, context_path = _build_launch(
        adapter, context_present=context_present, tmp_path=tmp_path
    )
    flag_present = any(context_path in arg for arg in argv)
    should_be_present = transport.instruction_channel is not None and context_present
    assert flag_present == should_be_present


def test_codex_app_server_transport_has_no_instruction_channel():
    from hub.runner_adapters.codex import CodexAppServerTransport

    assert CodexAppServerTransport().instruction_channel is None


# --- (e) context_window_source holds against each transport's recorded usage (design D13) -----


def test_claude_stream_transport_context_window_is_reported():
    transport = get_adapter("claude").stream_transport()
    assert transport.context_window_source == "reported"

    # line 5 of claude_stream.jsonl: a "result" event with modelUsage[model].contextWindow.
    line = CLAUDE_STREAM_JSONL.read_text(encoding="utf-8").splitlines()[4]
    parsed = transport.map_events(line, model=None)
    assert parsed.usage.limit_tokens == 1_000_000  # the payload's own, largest-window entry


def test_codex_exec_transport_context_window_is_catalog():
    transport = get_adapter("codex").stream_transport()
    assert transport.context_window_source == "catalog"

    # line 6 of codex_exec.jsonl: a "turn.completed" event with a usage dict but no window.
    line = CODEX_EXEC_JSONL.read_text(encoding="utf-8").splitlines()[5]
    parsed = transport.map_events(line, model="gpt-5.5")
    assert parsed.usage.limit_tokens == model_context_window("codex", "gpt-5.5")

    unknown = transport.map_events(line, model="no-such-model")
    assert unknown.usage.status == "unavailable"
    assert unknown.usage.limit_tokens is None


def test_codex_app_server_transport_context_window_is_reported():
    from hub.runner_adapters.codex import CodexAppServerTransport

    assert CodexAppServerTransport().context_window_source == "reported"

    params = {
        "tokenUsage": {
            "last": {"inputTokens": 100, "outputTokens": 10},
            "modelContextWindow": 258_400,
        }
    }
    mapped = map_token_usage_notification(params, model="gpt-5.6-luna")
    assert mapped["usage"].limit_tokens == 258_400
