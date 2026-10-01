"""The ABCs and value types every runner adapter implements (design D1/D3).

Why an ABC and not a `typing.Protocol`: an adapter that leaves out a member has to fail when the
table is built, not when a run reaches the missing branch. An ABC refuses to instantiate with an
abstract member unimplemented; a `Protocol` is only checked by `mypy`, which runs over `src/` only
(CLAUDE.md), so it would give the Hub no check at all.

Why the transport is its own object, separate from the adapter: Codex has two transports, `exec`
(a stream) and `app-server` (an RPC peer), and a runner's flags pick between them. The members that
differ by *transport* (argv, parsing, spawn kind, post-run accounting, approval channel, instruction
channel) sit on the transport; the members that differ by *runner* sit on the adapter.

This module must not import `hub.db`, `hub.worker`, `hub.launchability` or `hub.api` — a run's
command line has to be buildable with no database connection (D1). `test_runner_adapters_imports.py`
checks that in a fresh interpreter.
"""

from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Awaitable,
    Callable,
    ClassVar,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypedDict,
)

from ..codex_appserver import TurnOutcome
from ..runner_parsing import AccountingSample, ParsedLine
from .one_shot import WorkerUsage


class LaunchVerdict(TypedDict):
    """Same keys as `launchability.probe_agent` returns today."""

    runner: str
    cli: Optional[str]
    present: bool
    authorized: bool
    runnable: bool
    reason: Optional[str]


def probe_binary(
    binary: str, cli_override: Optional[str], name: str
) -> Tuple[str, bool, Optional[str]]:
    """(cli, present, reason) for the binary a run would spawn (design D14).

    Shared by `RunnerAdapter.launchability` and `launchability.probe_agent`'s legacy path, so a
    pinned-override check and a PATH lookup cannot drift between them. `cli_override`, when set, is
    checked as a file directly; otherwise `binary` (falling back to `name` when falsy, exactly as
    the legacy table's `LEGACY_RUNNER_CLI.get(runner) or name` does) is looked up on PATH. Calls
    `shutil.which`/`os.path.isfile` through the module attribute, never a `from shutil import
    which` — the ~220 test patches that used to target `hub.launchability.shutil.which` now target
    `hub.runner_adapters.base.shutil.which` instead (design D6, review 4; moved by task 3.2).
    """
    cli = str(cli_override) if cli_override else (binary or name)
    if cli_override:
        present = os.path.isfile(cli_override) and os.access(cli_override, os.X_OK)
        reason = (
            None if present else f"Pinned runner CLI {cli_override!r} is not an executable file."
        )
    else:
        present = shutil.which(cli) is not None
        reason = None if present else f"Runner CLI {cli!r} was not found in PATH."
    return cli, present, reason


@dataclass(frozen=True)
class AccessAxes:
    """Three independent axes of what a run can reach and who answers it (design D4)."""

    tool_surface: Literal["mcp", "none"]  # axis 1: is the Hub's MCP server injected
    approvals: Literal["mcp_permission_tool", "rpc", "none"]  # axis 2: how the Hub answers calls
    plane: Literal["mcp", "cli"]  # axis 3: what the run is *given* to reach the plane


@dataclass(frozen=True)
class LaunchRequest:
    """Today's `build_command` parameters, plus the resolved `axes` (design D3/D6)."""

    prompt: str
    axes: AccessAxes
    model: Optional[str] = None
    context_file: Optional[Path] = None
    session_id: Optional[str] = None
    yolo: bool = False
    mcp_command: Optional[List[str]] = None
    extra_flags: Optional[List[str]] = None
    control_overrides: Optional[Dict[str, str]] = None
    restrict_spec_writes: bool = False


@dataclass(frozen=True)
class RpcTurnRequest:
    """One Codex app-server (or, later, ACP) turn's inputs (design D3).

    `env` is `repr=False`: it carries the run's tokens, and a dataclass `repr` in a log line would
    print them (consistency pass, 2026-09-28).
    """

    cli: str
    cwd: str
    env: Optional[Dict[str, str]] = field(repr=False)
    prompt: str
    model: Optional[str]
    resume_session_id: Optional[str]
    yolo: bool
    mcp_command: Optional[List[str]]
    config_overrides: Optional[Dict[str, Any]]
    permission_mode: Optional[str]
    workspace: Optional[str]
    extra_flags: Optional[List[str]]
    restrict_spec_writes: bool


@dataclass(frozen=True)
class RpcCallbacks:
    """What an `RpcTransport.run_turn` reports back to its caller (design D3)."""

    on_event: Callable[..., Awaitable[None]]
    on_usage: Callable[..., Awaitable[None]]
    on_accounting: Callable[..., Awaitable[None]]
    on_session: Callable[[str], Awaitable[None]]
    should_interrupt: Callable[[], bool]
    request_approval: Callable[..., Awaitable[bool]]
    on_refusal: Callable[..., Awaitable[None]]


class StreamTransport(ABC):
    """A process whose stdout is parsed line by line (design D3)."""

    kind: ClassVar[Literal["stream"]] = "stream"
    spawn_kind: ClassVar[Literal["pty", "pipe"]]
    instruction_channel: ClassVar[Optional[str]] = None
    context_window_source: ClassVar[Literal["reported", "catalog"]]

    @abstractmethod
    def build_launch(self, req: LaunchRequest) -> List[str]:
        """The full argv, in today's argv positions — including `inject_mcp`'s fragment and the
        `instruction_channel` flag. Raises only `runner_commands.UnsupportedRunnerError`."""

    @abstractmethod
    def inject_mcp(self, mcp_command: List[str], *, yolo: bool) -> List[str]:
        """The argv fragment that starts the Hub's tool server, with `mcp_env_names` reaching it.
        `build_launch` calls it."""

    @abstractmethod
    def approval_channel(self, tool_surface: str) -> Literal["mcp_permission_tool", "rpc", "none"]:
        """Axis 2 for this transport (design D4)."""

    @abstractmethod
    def map_events(self, line: str, *, model: Optional[str]) -> ParsedLine:
        """One line of stdout (ANSI already stripped) to events, usage, accounting and session id.
        Must not raise."""

    @abstractmethod
    def usage_from(
        self, *, session_id: str, env: Optional[Dict[str, str]], model: Optional[str]
    ) -> Optional[AccountingSample]:
        """Accounting read after the process exits, merged over per-line accounting. Called only
        when a session id is known."""

    # `stop`: a stream is stopped by killing its process tree — generic, so no transport member
    # exists for it (design D3).


class RpcTransport(ABC):
    """A JSON-RPC peer the Hub drives (design D3). Has no `inject_mcp` in this slice (review 9):
    it would have no caller until an ACP transport reads it, and nothing exists without a caller.
    """

    kind: ClassVar[Literal["rpc"]] = "rpc"
    instruction_channel: ClassVar[Optional[str]] = None
    context_window_source: ClassVar[Literal["reported", "catalog"]]

    def approval_channel(self, tool_surface: str) -> Literal["rpc"]:
        """The Hub answers every server->client request; this does not depend on the tool
        surface."""
        return "rpc"

    @abstractmethod
    def posture_for(self, permission_mode: Optional[str]) -> Optional[str]:
        """Maps the operator's chosen posture onto what this transport's decision function
        reads."""

    @abstractmethod
    def permission_card_label(self, method: str, subject: Mapping[str, Any]) -> str:
        """The `tool_name` an ask-me card shows."""

    @abstractmethod
    def refusal_label(self, method: str, subject: Mapping[str, Any]) -> str:
        """The `tool_name` a `permission_denied` event carries."""

    def workspace_verdict(
        self, method: str, subject: Mapping[str, Any], workspace: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """What "Workspace only" would decide for a request put to the operator, shown on the
        card. Must not raise (`None` on failure). Base default is `None`; a transport that can
        compute one (Codex app-server's `workspace_verdict`) overrides it."""
        return None

    @abstractmethod
    async def run_turn(self, req: RpcTurnRequest, cb: RpcCallbacks) -> TurnOutcome:
        """Spawn the peer, start or resume, send the prompt, answer every request, and map every
        notification onto `cb.on_event`/`on_usage`/`on_accounting`. Call `cb.on_session(id)`
        before the first `on_event`. Honour `cb.should_interrupt()` within one poll interval and
        leave no process behind. Raises only `FileNotFoundError`, `OSError`,
        `asyncio.TimeoutError`, or `AppServerError`."""


class RunnerAdapter(ABC):
    """One runner CLI's behaviour, named by the twelve-member brief (design D1/D3)."""

    name: ClassVar[str]
    binary: ClassVar[str]
    display_name: ClassVar[str]
    catalog_provider: ClassVar[str]
    transport_sentinels: ClassVar[Tuple[str, ...]] = ()
    mcp_tool_prefix: ClassVar[Optional[str]] = None
    host_tool_note: ClassVar[Optional[str]] = None
    mcp_env_names: ClassVar[Optional[Tuple[str, ...]]] = None
    write_tool_kinds: ClassVar[Mapping[str, str]]
    one_shot_takes_schema: ClassVar[bool] = False

    @abstractmethod
    def launchability(self, agent: str, config: Mapping[str, Any]) -> LaunchVerdict:
        """Is the binary present, and is the harness authorised? Must not raise."""

    @abstractmethod
    def collaboration(
        self, flags: Optional[Sequence[str]], *, yolo: bool
    ) -> Tuple[bool, Optional[str]]:
        """Can a triggered run collaborate? Called only for a bound, runnable agent whose Hub
        address is known. `flags` are the runner's **raw** flags, sentinels included; `None` means
        no flags (`Runner.flags` is nullable). Must not raise."""

    @abstractmethod
    def guard_env(
        self, proc_env: Optional[Dict[str, str]], config: Mapping[str, Any]
    ) -> Optional[Dict[str, str]]:
        """Strips ambient variables that would silently redirect this harness's auth or endpoint.
        Runs last in `resolve_agent_env`, over the same `config` that function received. Must not
        raise."""

    @abstractmethod
    def transport(self, flags: Optional[Sequence[str]]) -> StreamTransport | RpcTransport:
        """The transport a run with these **raw** flags uses. `None` means no flags."""

    @abstractmethod
    def stream_transport(self) -> Optional[StreamTransport]:
        """This runner's stream transport, whatever its flags select, or `None` if it has none
        (review 2). Only `build_command` reads it — a no-flags Codex call must still build `exec`
        argv, which `transport(flags)` would send to app-server. The trigger's executor choice
        stays `transport(raw_flags).kind`."""

    @abstractmethod
    def posture_at_rest(self, axes: AccessAxes, *, yolo: bool) -> str:
        """The posture a run gets when no override states one. Reads `axes.approvals`, not the
        tool surface (design D4)."""

    @abstractmethod
    def one_shot(
        self,
        purpose: Literal["worker", "title"],
        *,
        model: Optional[str],
        prompt: str,
        output_schema_path: Optional[str] = None,
    ) -> List[str]:
        """A no-tools, one-prompt invocation's argv. Receives `prompt` **raw** and neutralises it
        itself with `file_mentions.neutralise_file_mentions`, as today's builders do. Raises only
        `FileNotFoundError`, when the executable cannot be resolved — in this slice neither adapter
        raises it."""

    @abstractmethod
    def parse_one_shot(self, stdout: str) -> Tuple[Optional[str], WorkerUsage, Optional[str]]:
        """The worker envelope: (answer text, usage, error)."""
