"""Per-runner-CLI adapters (design `each-runner-cli-is-one-adapter`, D1).

`ADAPTERS` carries `"claude"` and `"codex"` for this slice ("this change touches no Copilot
code", design D1) -- `get_adapter`, `build_command` (design D6) and `resolve_access_axes` (design
D4) are all generic over `ADAPTERS`'s contents, so a later slice's `CopilotAdapter` is one more
row, not a shape change.

Nothing in this package may import `hub.db`, `hub.worker`, `hub.launchability` or `hub.api` (D1):
a run's command line has to be buildable without a database connection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from ..runner_commands import UnsupportedRunnerError
from .base import AccessAxes, LaunchRequest, RunnerAdapter
from .claude import ClaudeAdapter
from .codex import CodexAdapter

ADAPTERS: Mapping[str, RunnerAdapter] = {
    "claude": ClaudeAdapter(),
    "codex": CodexAdapter(),
}


def get_adapter(cli: str) -> Optional[RunnerAdapter]:
    """The adapter for *cli* (a `Runner.cli` value), or `None` when there isn't one."""
    return ADAPTERS.get(cli)


def resolve_access_axes(
    adapter: RunnerAdapter, *, hub_client: Optional[str], flags: Optional[Sequence[str]]
) -> AccessAxes:
    """The three axes a run gets (design D4). `flags` are the runner's **raw** flags — the
    sentinel strip happens after this, not before (design D3, `transport`)."""
    tool_surface = "none" if hub_client == "cli" else "mcp"
    transport = adapter.transport(flags)
    return AccessAxes(
        tool_surface=tool_surface,
        approvals=transport.approval_channel(tool_surface),
        plane="mcp" if tool_surface == "mcp" else "cli",
    )


def build_command(
    *,
    runner: str,
    cli: str,
    prompt: str,
    model: Optional[str] = None,
    context_file: Optional[Path] = None,
    session_id: Optional[str] = None,
    yolo: bool = False,
    mcp_command: Optional[List[str]] = None,
    extra_flags: Optional[List[str]] = None,
    control_overrides: Optional[Dict[str, str]] = None,
    restrict_spec_writes: bool = False,
) -> List[str]:
    """Build one turn's full CLI invocation (design D6). Keeps `build_command`'s today's
    signature, including `cli` — unused here, because no golden case's `cli` ever differs from
    the adapter's own `binary` literal, so each transport resolves its own binary internally.

    The axes are derived from `mcp_command` by **truthiness**, not `is not None` (review 8.1):
    `mcp_command=[]` must mean no server, no approver, same as `None` — an `is not None` test
    would give an empty list the approver axis with no server to answer it.
    """
    del cli
    adapter = get_adapter(runner)
    if adapter is None:
        raise UnsupportedRunnerError(
            f"runner {runner!r} is not yet supported for direct Hub spawn "
            f"(supported: {', '.join(ADAPTERS)})"
        )
    transport = adapter.stream_transport()
    if transport is None:
        raise UnsupportedRunnerError(f"runner {runner!r} has no stream transport")
    tool_surface = "mcp" if mcp_command else "none"
    axes = AccessAxes(
        tool_surface=tool_surface,
        approvals=transport.approval_channel(tool_surface),
        plane="mcp" if tool_surface == "mcp" else "cli",
    )
    req = LaunchRequest(
        prompt=prompt,
        axes=axes,
        model=model,
        context_file=context_file,
        session_id=session_id,
        yolo=yolo,
        mcp_command=mcp_command,
        extra_flags=extra_flags,
        control_overrides=control_overrides,
        restrict_spec_writes=restrict_spec_writes,
    )
    return transport.build_launch(req)
