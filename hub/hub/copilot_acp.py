"""GitHub Copilot CLI driven over ACP (`copilot.exe --acp --stdio`): approvals, event mapping, and
one turn (`a-copilot-agent-runs-over-acp`, design D3 and D5-D12, D17).

The model is `codex_appserver`: one process per turn, a pure judge answering every request the
runtime raises, a mapper into the closed `RunEvent` kinds, and a `run_turn` that returns a
`TurnOutcome`. ACP differs from Codex's app-server in three ways, and each one shapes this module:

1. **The prompt's response arrives last.** `session/prompt` answers `{stopReason, usage}` only
   after every `session/update` of the turn, so the prompt is a pending request whose
   notifications are delivered while it is awaited. `ACPProcess` hands each notification and each
   agent->client request to a handler from its read loop, in wire order; there is no separate
   notification queue to poll.
2. **Requests from the agent are ACP methods.** `session/request_permission` is answered with
   `{outcome: {outcome: "selected", optionId}}`, and only ever with `allow_once` or `reject_once`.
3. **Raw session events** (`github.com/copilot/sessionEvent`) arrive only when subscribed in
   `initialize`, and they are the only report of which MCP server a call belongs to. A request's
   `title` is the call's own `description` argument when it has one (CODE, `VDo`): the model
   writes it, so nothing here ever reads a title to decide whose tool a call is.

`decide_permission` is pure and total and runs in a worker thread (`asyncio.to_thread`): `_decide`
resolves paths with `os.path.realpath`, which blocks for ~21 s on an unreachable UNC path, and the
Hub process's event loop serves every project (review 2026-09-28, finding 7).

`run_turn` raises only **before** the prompt is written (spawn, handshake, version gate, session,
agent and posture options). After that it returns a `TurnOutcome`, failed or not, so the executor
takes its normal end: worktree snapshot, run-end evaluation, the status row (D12, R3).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
from collections import deque
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Deque,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from . import run_secrets
from .codex_appserver import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    DEFAULT_TURN_TIMEOUT_SECONDS,
    STDERR_TAIL_CHARS,
    STDERR_TAIL_LINES,
    AppServerError,
)
from .copilot_home import HUB_MCP_SERVER_NAME, MCP_CONFIG_NAME, agent_marker
from .copilot_probe import (
    AUTH_REQUIRED_CODE,
    COPILOT_MIN_VERSION_TEXT,
    CopilotProbe,
    not_signed_in_reason,
    resolve_copilot_executable,
    too_old_reason,
    version_supported,
)
from .copilot_usage import CopilotUsageLedger
from .model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE
from .pty_runner import terminate_process_tree
from .runner_commands import OPERATOR_POSTURE
from .runner_events import (
    ContextUsageSample,
    RunEvent,
    _truncate_utf8,
    diagnostic_event,
    error_event,
    redact_secrets,
    status_event,
    text_event,
    thinking_event,
    tool_result_event,
    tool_use_event,
)
from .subprocess_windows import no_console_kwargs

logger = logging.getLogger(__name__)

#: The minimum Copilot CLI, as the dotted text the version gate's sentence names (D12).
#: `copilot_probe.COPILOT_MIN_VERSION` is the same minimum as a tuple.
COPILOT_MIN_VERSION = COPILOT_MIN_VERSION_TEXT

#: The raw session events subscribed in `initialize` (D10). Slices 4 and 5 extend it by
#: concatenation; it is sent de-duplicated in first-seen order, so an overlap cannot double-subscribe.
COPILOT_RAW_EVENTS: Tuple[str, ...] = (
    "session.error",
    "session.warning",
    "session.info",
    "session.mcp_servers_loaded",
    "session.mcp_server_status_changed",
    "session.model_change",
    "session.auto_mode_resolved",
    "session.tools_updated",
    "permission.requested",
    "tool.execution_start",
    "tool.execution_complete",
    "session.mode_changed",
    "exit_plan_mode.requested",
    "assistant.usage",
    "session.usage_checkpoint",
    "session.compaction_complete",
    # Slice 5 group A (D1): the counts when a compaction's report was too large to relay, and
    # the subagent lifecycle (D6).
    "session.compaction_start",
    "subagent.started",
    "subagent.completed",
    "subagent.failed",
)

#: Opens the first prompt block of every turn (D5, review note 15). A resumed session holds
#: earlier turns' blocks, which may name another workspace or access path; this line says which
#: one counts. It also keeps the first block non-empty and not starting with `/`: Copilot runs a
#: one-block prompt starting with `/` as a slash command (`/allow-all`, `/permissions`, ...).
COPILOT_TURN_CONTEXT_HEAD = (
    "AgentWeave context for this turn. It supersedes the AgentWeave context of every earlier turn "
    "in this conversation."
)

#: Plan mode on specification turns (D9 item 2). Ships off (review 2026-09-28, finding 9): the
#: model leaves plan mode through `exit_plan_mode`, whose input request no ACP method answers.
#: Turning it on is a commit citing task 11.3's drive.
SPEC_TURN_USES_PLAN_MODE = False

#: Copilot's write tools except `create`, excluded on a specification turn (D3, D9 item 1). One
#: comma-joined argv word: `app.js`'s filter splits the value on commas. `create` stays, because a
#: spec turn told `shim` must write its args file; the handler refuses every other edit (item 1a).
#: `str_replace` dropped (F479): 1.0.88 does not know that tool name and logs an "Unknown tool
#: name in the tool excludedlist" diagnostic for it every spec turn; `str_replace_editor` is the
#: name 1.0.88 actually reports disabling, and stays excluded.
SPEC_TURN_EXCLUDED_TOOLS = ("apply_patch", "edit", "str_replace_editor")

MODE_URI_PREFIX = "https://agentclientprotocol.com/protocol/session-modes#"
AGENT_MODE = MODE_URI_PREFIX + "agent"
PLAN_MODE = MODE_URI_PREFIX + "plan"
AUTOPILOT_MODE = MODE_URI_PREFIX + "autopilot"

PERMISSION_METHOD = "session/request_permission"
RAW_EVENT_METHOD = "github.com/copilot/sessionEvent"

#: `session/load` of a session Copilot never persisted (VERIFIED, `r1-probe-load.log:10`).
SESSION_NOT_FOUND_CODE = -32002
METHOD_NOT_FOUND_CODE = -32601
INTERNAL_ERROR_CODE = -32603

#: How long a stop waits for the pending prompt to answer `cancelled` before the tree kill (D17).
CANCEL_GRACE_SECONDS = 10.0
#: `session/new`/`session/load` wait for Copilot to start the session's MCP servers.
SESSION_REQUEST_TIMEOUT_SECONDS = 120.0
#: How often a turn in flight checks `should_interrupt` while no notification arrives.
POLL_SECONDS = 0.25
#: One JSON-RPC line may carry a large tool output; asyncio's 64 KiB default would end the turn.
STDOUT_LINE_LIMIT = 16 * 1024 * 1024

#: Runner flags that make Copilot approve on its own account (review 2026-09-28, finding 10), with
#: whether each takes values. None of them shows as `allow_all`, so the posture step cannot see
#: them; they are removed unless the run is under Full access. A deny-list: a widening flag a later
#: Copilot adds is not caught (design, Risks).
COPILOT_WIDENING_FLAGS: Dict[str, str] = {
    "--yolo": "none",
    "--allow-all": "none",
    "--allow-all-tools": "none",
    "--allow-all-paths": "none",
    "--allow-all-urls": "none",
    "--allow-tool": "many",
    "--allow-url": "many",
    "--add-dir": "one",
    "--autopilot": "none",
    "--mode": "one",
    "--plan": "none",
    "--assisted-approval": "none",
    "--config-dir": "one",
    # Slice 5 D9a (F485): Copilot's built-in GitHub server loads read-only tools only, which it
    # runs without asking; these add tools that write, and `--additional-mcp-config` adds any
    # server. Only the runner's flags pass through here: the Hub's own `--additional-mcp-config`
    # is built after this, from `mcp_config`.
    "--enable-all-github-mcp-tools": "none",
    "--add-github-mcp-toolset": "one",
    "--add-github-mcp-tool": "one",
    "--additional-mcp-config": "one",
}

#: Why a removed flag was removed, where "it lets Copilot approve on its own account" is untrue:
#: these add tools rather than approve them (D9a).
_FLAG_REMOVAL_REASONS: Dict[str, str] = {
    "--enable-all-github-mcp-tools": "it adds GitHub tools that write, which only a run with Full "
    "access may have",
    "--add-github-mcp-toolset": "it adds GitHub tools that write, which only a run with Full "
    "access may have",
    "--add-github-mcp-tool": "it adds GitHub tools that write, which only a run with Full access "
    "may have",
    "--additional-mcp-config": "it adds MCP servers, which only a run with Full access may have",
}
#: Removed under every posture: it moves configuration out of the Hub-owned home (D4).
_ALWAYS_REMOVED_FLAGS = ("--config-dir",)

#: The tools the Hub's own MCP server serves. Restated rather than read from `mcp_server`, whose
#: import builds the FastMCP instance; `test_copilot_acp_decide.py` asserts the two agree. A call
#: counts as the Hub's own only for one of these names (review, finding 5).
HUB_MCP_TOOLS = frozenset(
    {
        "advance_spec_step",
        "amend_spec_document",
        "approve_tool_call",
        "archive_job",
        "ask_user",
        "create_flow",
        "create_job",
        "create_loop",
        "create_spec_document",
        "create_task",
        "decide_evidence",
        "get_answer",
        "get_task",
        "list_checkpoints",
        "list_evidence",
        "list_tasks",
        "read_checkpoint",
        "read_spec_document",
        "recall",
        "report_cannot_satisfy",
        "record_evidence",
        "rename_spec_document",
        "request_agent",
        "run_job",
        "set_spec_size",
        "send_message",
        "submit_checkpoint_notes",
        "submit_spec_document",
        "task_history",
        "toggle_job",
        "update_task",
    }
)

ALLOW = "ALLOW"
REJECT = "REJECT"
ASK_OPERATOR = "ASK_OPERATOR"

#: The operator card's `tool_name` for a Copilot request, by kind (D8, *Operator posture*). An MCP
#: request is labelled `<server>/<tool>` from `calls`, never from its title.
COPILOT_PERMISSION_LABELS: Dict[str, str] = {
    "execute": "a command",
    "edit": "a file change",
    "read": "a file read",
    "fetch": "a web address",
}
SHELL_UNKNOWN_LABEL = "a command in an unknown shell"
MCP_UNIDENTIFIED_LABEL = "an MCP tool Copilot did not identify"
OTHER_REQUEST_LABEL = "a Copilot request this Hub does not recognise"

_UNIDENTIFIED_REASON = "Copilot did not report which server this tool belongs to"

#: Copilot's own built-in GitHub MCP server (D9). The toggle disables `--disable-builtin-mcps`
#: for every built-in server Copilot ships, not only this one; the card label below still calls
#: out GitHub by name only when the reported server is exactly this.
GITHUB_MCP_SERVER_NAME = "github-mcp-server"
_GITHUB_MCP_REASON = (
    "the GitHub-tools toggle is on, and the operator decides a built-in MCP server's calls"
)


class CopilotACPError(AppServerError):
    """A Copilot ACP failure. An `AppServerError`, so the executor's pre-spawn `except`
    (`FileNotFoundError, AppServerError, asyncio.TimeoutError, OSError`) treats an expected "update
    your CLI" or "sign in" outcome as one, not as an abnormal crash (D12, R2).

    For a JSON-RPC error response it carries the error's `code` (so D7's `-32002` is read from
    `.code`, never parsed out of text) and its `data` (slice 4 reads structured quota fields there).
    """

    def __init__(
        self,
        message: Optional[str],
        *,
        code: Optional[int] = None,
        data: Any = None,
        method: Optional[str] = None,
        exit_code: Optional[int] = None,
        stderr_tail: str = "",
    ) -> None:
        self.code = code
        self.data = data
        super().__init__(
            message or "Copilot returned an error",
            exit_code=exit_code,
            method=method,
            stderr_tail=stderr_tail,
        )


# --- Postures -------------------------------------------------------------------------------------

_FULL = FULL_ACCESS_PERMISSION_MODE
_MANUAL = "manual"
_ACCEPT_EDITS = "acceptEdits"


def posture_for(permission_mode: Optional[str], *, yolo: bool = False) -> str:
    """The posture a Copilot run is judged under (D8's posture table). Copilot has no sandbox of
    its own to fall back on, so an unset mode is `workspace`, not Codex's "let the runtime decide".
    """
    if permission_mode is None or permission_mode == "":
        # The posture at rest, which the Permissions pill reads too (through
        # `CopilotAdapter.posture_at_rest`): Full access under `yolo`, else `workspace`.
        return _FULL if yolo else WORKSPACE_PERMISSION_MODE
    if permission_mode in (_MANUAL, OPERATOR_POSTURE):
        return _MANUAL
    if permission_mode == _ACCEPT_EDITS:
        return _ACCEPT_EDITS
    if permission_mode in (_FULL, "yolo"):
        return _FULL
    return WORKSPACE_PERMISSION_MODE


def _canonical_posture(posture: Optional[str]) -> str:
    """`decide_permission`'s own reading of its `posture` argument. Anything unrecognised is judged
    as `workspace`: an unknown posture is not an open one."""
    if posture in (_MANUAL, OPERATOR_POSTURE):
        return _MANUAL
    if posture == _ACCEPT_EDITS:
        return _ACCEPT_EDITS
    if posture in (_FULL, "yolo"):
        return _FULL
    return WORKSPACE_PERMISSION_MODE


# --- What Copilot reported about a call -----------------------------------------------------------


@dataclass(frozen=True)
class CallFacts:
    """Copilot's own report of one open tool call, from its raw `tool.execution_start` (or, when
    that was missed, its raw `permission.requested`). Keyed by `toolCallId` in the per-turn `calls`
    map, which holds open calls only: `tool.execution_complete` removes the entry, so a reused id
    whose start event was dropped finds nothing rather than a stale Hub-own entry (review, note 12).

    `mcp_source` and `mcp_transport` are the start event's `mcpConfigSource`/`mcpTransport`
    (captured, `turn_write_shell_mcp.jsonl`: `"user"`/`"stdio"` for the Hub's server). When present
    they must agree with the load-time condition too.
    """

    tool_name: Optional[str]
    mcp_server: Optional[str]
    mcp_tool: Optional[str]
    mcp_source: Optional[str] = None
    mcp_transport: Optional[str] = None


def _str_or_none(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def track_call(calls: Dict[str, CallFacts], event_type: str, data: Any) -> None:
    """Feed one raw event into `calls` (D8, *Identifying the MCP server*). Idempotent, so the turn
    and the mapper may both feed the same map. An event whose data was blanked (`{omitted:
    "too-large"}`) carries no id and changes nothing, which lands a later request on the refuse
    side."""
    if not isinstance(data, dict):
        return
    if event_type == "tool.execution_start":
        call_id = _str_or_none(data.get("toolCallId"))
        if call_id:
            calls[call_id] = CallFacts(
                tool_name=_str_or_none(data.get("toolName")),
                mcp_server=_str_or_none(data.get("mcpServerName")),
                mcp_tool=_str_or_none(data.get("mcpToolName")),
                mcp_source=_str_or_none(data.get("mcpConfigSource")),
                mcp_transport=_str_or_none(data.get("mcpTransport")),
            )
    elif event_type == "permission.requested":
        request = data.get("permissionRequest")
        if not isinstance(request, dict) or request.get("kind") != "mcp":
            return
        call_id = _str_or_none(request.get("toolCallId"))
        server = _str_or_none(request.get("serverName"))
        if not call_id or not server or call_id in calls:
            return
        # `toolName` here is `<server>-<tool>`; the bare name is the prompt request's `toolName`.
        prompt = data.get("promptRequest") if isinstance(data.get("promptRequest"), dict) else {}
        bare = _str_or_none(prompt.get("toolName"))
        full = _str_or_none(request.get("toolName")) or ""
        if bare is None and full.startswith(f"{server}-"):
            bare = full[len(server) + 1 :]
        calls[call_id] = CallFacts(tool_name=full or None, mcp_server=server, mcp_tool=bare)
    elif event_type == "tool.execution_complete":
        call_id = _str_or_none(data.get("toolCallId"))
        if call_id:
            calls.pop(call_id, None)


def track_servers(servers: Dict[str, List[Dict[str, Any]]], event_type: str, data: Any) -> None:
    """Feed one raw event into the per-turn `servers` map: name -> the entries the latest
    `session.mcp_servers_loaded` reported under that name (a list, so a second server claiming the
    same name is visible), with statuses updated by `session.mcp_server_status_changed`."""
    if not isinstance(data, dict):
        return
    if event_type == "session.mcp_servers_loaded":
        reported = data.get("servers")
        if not isinstance(reported, list):
            return
        servers.clear()
        for entry in reported:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                servers.setdefault(entry["name"], []).append(dict(entry))
    elif event_type == "session.mcp_server_status_changed":
        name = _str_or_none(data.get("name")) or _str_or_none(data.get("serverName"))
        status = data.get("status")
        if name and name in servers and isinstance(status, str):
            for entry in servers[name]:
                entry["status"] = status


def hub_server_unverified(
    servers: Optional[Mapping[str, Sequence[Mapping[str, Any]]]],
    facts: Optional[CallFacts] = None,
) -> Optional[str]:
    """Why the reported `agentweave` server cannot be taken as the Hub's own, or None when it can.

    A server name is a config key, not an identity: a repository agent's `mcp-servers`, a trusted
    folder's `.mcp.json` or a plugin can all claim `agentweave` (review, findings 5 and 6). So the
    turn's load report must name exactly one `agentweave`, from a source that is neither
    `workspace` nor `plugin`, over `stdio`. Copilot 1.0.88 reports the Hub's server with **no**
    `source` or `transport` at all (task 1.1's capture), so an absent value is accepted and only a
    present, wrong one refuses.
    """
    if not servers:
        return "Copilot sent no report of which MCP servers it loaded"
    entries = list(servers.get(HUB_MCP_SERVER_NAME) or ())
    if not entries:
        return f"Copilot's load report named no {HUB_MCP_SERVER_NAME!r} server"
    if len(entries) != 1:
        return f"Copilot's load report named {len(entries)} servers {HUB_MCP_SERVER_NAME!r}"
    entry = entries[0]
    sources = [entry.get("source"), facts.mcp_source if facts else None]
    transports = [entry.get("transport"), facts.mcp_transport if facts else None]
    for source in sources:
        if source in ("workspace", "plugin"):
            return f"its {HUB_MCP_SERVER_NAME!r} server came from a {source} configuration"
    for transport in transports:
        if transport is not None and transport != "stdio":
            return f"its {HUB_MCP_SERVER_NAME!r} server runs over {transport}, not stdio"
    return None


# --- The judge (D8) -------------------------------------------------------------------------------


def _tool_call(params: Mapping[str, Any]) -> Dict[str, Any]:
    tool_call = params.get("toolCall") if isinstance(params, Mapping) else None
    return tool_call if isinstance(tool_call, dict) else {}


def _raw_input(tool_call: Mapping[str, Any]) -> Dict[str, Any]:
    raw = tool_call.get("rawInput")
    return raw if isinstance(raw, dict) else {}


def _location_paths(tool_call: Mapping[str, Any]) -> List[str]:
    locations = tool_call.get("locations")
    if not isinstance(locations, list):
        return []
    return [
        loc["path"]
        for loc in locations
        if isinstance(loc, dict) and isinstance(loc.get("path"), str) and loc["path"]
    ]


def _facts_for(tool_call: Mapping[str, Any], calls: Mapping[str, CallFacts]) -> Optional[CallFacts]:
    call_id = tool_call.get("toolCallId")
    if not isinstance(call_id, str):
        return None
    facts = calls.get(call_id)
    return facts if isinstance(facts, CallFacts) else None


def _shell_key(facts: Optional[CallFacts]) -> str:
    """`_decide`'s dialect key for a command, from the call's real tool name (D8, R3). Any other
    name, or none known, is `"Shell"`: a key `_TOOL_DIALECTS` lacks, so the text is read in both
    dialects and refused if either refuses. It never earns slice 3's standing allow (conflict 1)."""
    name = (facts.tool_name or "").lower() if facts else ""
    if name == "powershell":
        return "PowerShell"
    if name == "bash":
        return "Bash"
    return "Shell"


def _is_mcp_request(kind: Optional[str]) -> bool:
    return kind == "other"


def normalise_request(
    params: Mapping[str, Any], calls: Mapping[str, CallFacts]
) -> List[Tuple[str, Dict[str, Any]]]:
    """Step 2 of D8: the request in `_decide`'s vocabulary, as `(tool_name, tool_input)` pairs.

    `("PowerShell"|"Bash"|"Shell", {"command": ...})` for a command or a URL raised by a
    non-`web_fetch` call; one `("Write", {"path": p})` per edited path; one `("Read", {"path": p})`
    per read path plus the whole unsplit string (`eNo` joins paths with `", "`, so one path holding
    `", "` must be judged whole as well); `("copilot-mcp:<server>/<tool>", args)` for a foreign MCP
    call. An empty list means there is nothing a judge could read, which step 4 refuses.
    """
    tool_call = _tool_call(params)
    kind = tool_call.get("kind")
    raw = _raw_input(tool_call)
    facts = _facts_for(tool_call, calls)
    if kind == "execute":
        command = raw.get("command")
        if not isinstance(command, str) or not command.strip():
            return []
        return [(_shell_key(facts), {"command": command})]
    if kind == "edit":
        paths: List[str] = []
        for path in [*_location_paths(tool_call), raw.get("fileName"), raw.get("path")]:
            if isinstance(path, str) and path and path not in paths:
                paths.append(path)
        return [("Write", {"path": p}) for p in paths]
    if kind == "read":
        joined = raw.get("path") if isinstance(raw.get("path"), str) else None
        locations = _location_paths(tool_call)
        candidates: List[str] = []
        for whole in [joined, *locations]:
            if not whole:
                continue
            for piece in [*whole.split(", "), whole]:
                piece = piece.strip()
                if piece and piece not in candidates:
                    candidates.append(piece)
        return [("Read", {"path": p}) for p in candidates]
    if kind == "fetch":
        url = raw.get("url")
        if not isinstance(url, str) or not url.strip():
            return []
        return [(_shell_key(facts), {"command": url})]
    if _is_mcp_request(kind) and facts is not None and facts.mcp_server:
        tool = facts.mcp_tool or facts.tool_name or "?"
        return [(f"copilot-mcp:{facts.mcp_server}/{tool}", dict(raw))]
    return []


def _standing_rules(
    pairs: List[Tuple[str, Dict[str, Any]]],
    *,
    kind: Optional[str],
    facts: Optional[CallFacts],
    posture: str,
    spec_turn: bool,
    workspace: str = "",
) -> Optional[Dict[str, Any]]:
    """Step 3 of D8: slice 3's `_hub_own_call` predicate and slice 5's `github-mcp-server` rule go
    here, each owned by its slice. Step 1 has already answered an MCP request whose server is not
    identified, so no rule here ever sees one (review, conflict 2).

    Slice 3 (`a-run-reaches-the-hub-without-mcp` D8, task 6.2): a shell request that is exactly one
    `aw-tool` invocation, or an `edit` whose every path is a `.json` file in the calls root, is the
    Hub's own -- allowed in every posture, before the spec-turn edit refusal (D16: the one write a
    spec turn keeps). An `edit` is allowed only when it names at least one path and every path
    passes; otherwise the whole request goes on to the judge, one answer to one request. Its own
    `try`: `decide_permission` turns any raise into a REJECT, and this rule may only allow or fall
    through (verification 2026-10-01, finding 5).
    """
    if kind in ("execute", "edit") and pairs and workspace:
        try:
            # Function-local, as `_judge`'s: importing `mcp_server` builds its FastMCP instance.
            from . import mcp_server

            if all(mcp_server._hub_own_call(t, i, workspace=workspace) for t, i in pairs):
                return _decision(ALLOW, "the Hub's own tools")
        except Exception:  # noqa: BLE001 -- fall through to the judge, never refuse here
            logger.warning("the Hub's own call-command check failed", exc_info=True)
    return None


def _decision(outcome: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {"outcome": outcome, "reason": reason, **extra}


def _judge(
    pairs: List[Tuple[str, Dict[str, Any]]], *, workspace: str, hub_url: str
) -> Dict[str, Any]:
    """Step 4's judge: every pair through `mcp_server._decide`; any refusal refuses the request."""
    # Function-local: importing `mcp_server` builds its FastMCP instance (as `agents.py` does).
    from . import mcp_server

    if not pairs:
        return _decision(REJECT, "the request names nothing this Hub could check")
    for tool_name, tool_input in pairs:
        verdict = mcp_server._decide(tool_name, tool_input, workspace=workspace, hub_url=hub_url)
        if not verdict.get("allow"):
            return _decision(REJECT, str(verdict.get("reason") or "refused by the workspace check"))
    return _decision(ALLOW, "inside your workspace")


def _decide_permission(
    params: Mapping[str, Any],
    *,
    posture: str,
    workspace: str,
    hub_url: str,
    calls: Mapping[str, CallFacts],
    spec_turn: bool,
    servers: Optional[Mapping[str, Sequence[Mapping[str, Any]]]],
    github_mcp: bool = False,
) -> Dict[str, Any]:
    tool_call = _tool_call(params)
    kind = tool_call.get("kind")
    raw = _raw_input(tool_call)
    facts = _facts_for(tool_call, calls)
    posture = _canonical_posture(posture)
    # A spec turn never answers ALLOW on Full access's account (open question 13, option (c)).
    judged = WORKSPACE_PERMISSION_MODE if (spec_turn and posture == _FULL) else posture

    # Step 1, identify. An MCP request whose server Copilot did not report is answered here, so no
    # server-specific rule ever sees it: a card under `manual`, the defensive allow under genuine
    # Full access, and a refusal everywhere else (D8, R3; review, conflict 2).
    identified_other_tool = facts is not None and (facts.mcp_server or facts.tool_name)
    if _is_mcp_request(kind) and not identified_other_tool:
        if judged == _MANUAL:
            return _decision(ASK_OPERATOR, _UNIDENTIFIED_REASON)
        if judged == _FULL:
            return _decision(ALLOW, "Full access")
        return _decision(REJECT, _UNIDENTIFIED_REASON)

    is_mcp = _is_mcp_request(kind) and facts is not None and bool(facts.mcp_server)
    hub_own = False
    unverified: Optional[str] = None
    if (
        is_mcp
        and facts is not None
        and facts.mcp_server == HUB_MCP_SERVER_NAME
        and facts.mcp_tool in HUB_MCP_TOOLS
    ):
        unverified = hub_server_unverified(servers, facts)
        hub_own = unverified is None
    extra: Dict[str, Any] = {"hub_server_unverified": unverified} if unverified else {}

    # D9: with the toggle on, a built-in MCP server other than `agentweave` is the operator's
    # call under `workspace` -- before `_judge`/`_decide` ever sees it (R2's "has no ground to
    # allow it" was wrong: `_decide` allows a GitHub tool's input by default). Under `manual`,
    # `full` and `acceptEdits` the postures below already answer the same way the rule asks for
    # (card, allow, refusal respectively), so this only changes the `workspace` fallback.
    github_rule = (
        github_mcp
        and is_mcp
        and not hub_own
        and facts is not None
        and bool(facts.mcp_server)
        and facts.mcp_server != HUB_MCP_SERVER_NAME
    )

    if kind == "fetch" and raw.get("requestSandboxBypass") is True:
        return _decision(
            REJECT, "a request to bypass Copilot's sandbox is not something this Hub grants"
        )

    # Step 2, normalise.
    pairs = normalise_request(params, calls)

    # Step 3, the slot slices 3 and 5 fill.
    standing = _standing_rules(
        pairs, kind=kind, facts=facts, posture=judged, spec_turn=spec_turn, workspace=workspace
    )
    if standing is not None:
        return {**standing, **extra}

    # D9 item 1a: on a spec turn every edit step 3 did not allow is refused, in every posture,
    # with no card under `manual`.
    if spec_turn and kind == "edit":
        return _decision(REJECT, "a specification turn writes no file", **extra)

    # Step 4, judge under the posture.
    if hub_own:
        return _decision(ALLOW, "the Hub's own tools")
    if judged == _MANUAL:
        return _decision(ASK_OPERATOR, "the operator answers under Ask me", **extra)
    if judged == _FULL:
        return _decision(ALLOW, "Full access", **extra)

    known_kind = kind in ("execute", "edit", "read", "fetch") or is_mcp
    if not known_kind:
        return _decision(REJECT, "not a request this Hub decides", **extra)

    if judged == _ACCEPT_EDITS:
        if kind in ("edit", "read"):
            return {**_judge(pairs, workspace=workspace, hub_url=hub_url), **extra}
        return _decision(
            REJECT, "Edit files allows file changes inside the workspace only", **extra
        )

    # `workspace`.
    if github_rule:
        return _decision(ASK_OPERATOR, _GITHUB_MCP_REASON, **extra)
    if kind == "fetch" and facts is not None and facts.tool_name == "web_fetch":
        # Claude's `WebFetch` parity: `_decide` reads no fetch URL.
        return _decision(ALLOW, "a web fetch", **extra)
    return {**_judge(pairs, workspace=workspace, hub_url=hub_url), **extra}


def decide_permission(
    params: Mapping[str, Any],
    *,
    posture: Optional[str],
    workspace: Optional[str],
    hub_url: Optional[str],
    calls: Mapping[str, CallFacts],
    spec_turn: bool = False,
    servers: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None,
    github_mcp: bool = False,
) -> Dict[str, Any]:
    """Decide one `session/request_permission` (D8). Pure and total: returns
    `{"outcome": ALLOW|REJECT|ASK_OPERATOR, "reason": str}`, plus `hub_server_unverified` when an
    `agentweave` call failed the load-time condition. Any exception while deciding is a REJECT, never
    silence: an unanswered request hangs the turn.

    Order (R3): identify -> normalise -> step 3 -> judge -> answer; the caller answers. `servers` is
    the turn's load report (`track_servers`); without one no call is the Hub's own. `workspace` and
    `hub_url` are the run's: an absent one refuses rather than reading the Hub process's own
    environment. Call it through `asyncio.to_thread` (review, finding 7). `github_mcp` is the
    agent's own toggle (D9): with it on, a request whose reported server is not `agentweave` is
    the operator's call under `workspace`.
    """
    try:
        return _decide_permission(
            params,
            posture=posture or WORKSPACE_PERMISSION_MODE,
            workspace=workspace or "",
            hub_url=hub_url or "",
            calls=calls or {},
            spec_turn=bool(spec_turn),
            servers=servers,
            github_mcp=bool(github_mcp),
        )
    except Exception as exc:  # noqa: BLE001 - a judge that raises must still answer
        logger.warning("Deciding a Copilot permission request failed: %s", exc, exc_info=True)
        return _decision(REJECT, f"this Hub could not decide the request ({type(exc).__name__})")


def workspace_verdict(
    params: Mapping[str, Any],
    workspace: Optional[str],
    *,
    hub_url: Optional[str] = None,
    calls: Optional[Mapping[str, CallFacts]] = None,
    servers: Optional[Mapping[str, Sequence[Mapping[str, Any]]]] = None,
    github_mcp: bool = False,
) -> Optional[Dict[str, Any]]:
    """What Workspace only would decide for this request, for an Ask me card
    (`an-ask-me-card-says-what-workspace-only-would-decide`): `{"allow": bool, "reason": str}`, or
    None on any failure. Never raises. Blocking like the judge: call it through `asyncio.to_thread`.

    D9 (R3): a two-valued `allow` cannot say "Workspace only would ask you too" -- so for a
    request D9's own rule sends to the operator (the toggle on, a reported server that is not
    `agentweave`), this returns `None` rather than computing `decide_permission`'s ASK_OPERATOR
    as a false `allow`.
    """
    try:
        tool_call = _tool_call(params)
        kind = tool_call.get("kind")
        facts = _facts_for(tool_call, calls or {})
        if (
            github_mcp
            and _is_mcp_request(kind)
            and facts is not None
            and bool(facts.mcp_server)
            and facts.mcp_server != HUB_MCP_SERVER_NAME
        ):
            return None
        decided = decide_permission(
            params,
            posture=WORKSPACE_PERMISSION_MODE,
            workspace=workspace,
            hub_url=hub_url,
            calls=calls or {},
            servers=servers,
            github_mcp=github_mcp,
        )
        verdict = {"allow": decided["outcome"] == ALLOW, "reason": decided["reason"]}
        if verdict["allow"] and _tool_call(params).get("kind") == "execute":
            # The judge read the command's text; it did not sandbox what the shell does (D5).
            verdict["reason"] = f"{verdict['reason']}; a shell command is read, not sandboxed"
        return verdict
    except Exception:  # noqa: BLE001 - a card detail must never fail the card
        return None


#: The card's `tool_name` column is `String(128)` (`db/models.py:1646`); either suffix below is
#: well inside it for any tool name Copilot's built-in servers have (D9).
_PERMISSION_LABEL_MAX_BYTES = 128


def permission_label(
    params: Mapping[str, Any], calls: Mapping[str, CallFacts], *, github_mcp: bool = False
) -> str:
    """The readable name of what a request asks for, for the operator card and a refusal row. An
    MCP request is `<server>/<tool>` from Copilot's own report, never its model-written title.

    D9 (review 2026-09-28, finding 4): with the toggle on, a reported server names which built-in
    MCP server the card's sentence is about -- GitHub by name only when the server is exactly
    `github-mcp-server`; any other reported server gets a sentence naming itself, never GitHub's.
    """
    tool_call = _tool_call(params)
    kind = tool_call.get("kind")
    facts = _facts_for(tool_call, calls)
    if _is_mcp_request(kind):
        if facts is not None and facts.mcp_server:
            tool = facts.mcp_tool or facts.tool_name or "?"
            server = facts.mcp_server
            if github_mcp and server != HUB_MCP_SERVER_NAME:
                if server == GITHUB_MCP_SERVER_NAME:
                    label = f"{server}/{tool} — acts on GitHub as you"
                else:
                    label = f"{server}/{tool} — a tool of MCP server {server}, not the Hub's"
                return _truncate_utf8(label, _PERMISSION_LABEL_MAX_BYTES)[0]
            return f"{server}/{tool}"
        if facts is not None and facts.tool_name:
            return facts.tool_name
        return MCP_UNIDENTIFIED_LABEL
    if kind == "execute" and _shell_key(facts) == "Shell":
        return SHELL_UNKNOWN_LABEL
    if isinstance(kind, str) and kind in COPILOT_PERMISSION_LABELS:
        return COPILOT_PERMISSION_LABELS[kind]
    return OTHER_REQUEST_LABEL


def permission_subject(
    params: Mapping[str, Any], calls: Mapping[str, CallFacts], *, github_mcp: bool = False
) -> Dict[str, Any]:
    """What a request asks about, in the shape the operator card and the refusal recorder read:
    `tool_name` is the readable label, `tool_input` the `rawInput` plus `locations`."""
    tool_call = _tool_call(params)
    raw = tool_call.get("rawInput")
    tool_input: Dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
    if raw is not None and not isinstance(raw, dict):
        tool_input["rawInput"] = raw
    locations = tool_call.get("locations")
    if isinstance(locations, list) and locations:
        tool_input["locations"] = locations
    return {
        "tool_name": permission_label(params, calls, github_mcp=github_mcp),
        "tool_input": tool_input,
        "kind": tool_call.get("kind"),
        "tool_call_id": tool_call.get("toolCallId"),
    }


def permission_answer(params: Mapping[str, Any], allowed: bool) -> Dict[str, Any]:
    """The `session/request_permission` result. Only `allow_once` or `reject_once`: `allow_always`
    would grant the rest of the session without asking the Hub again, and the judge is per
    request. An offer that lacks the wanted option is answered `cancelled`, which Copilot counts as
    a refusal, rather than with some other option."""
    wanted = "allow_once" if allowed else "reject_once"
    options = params.get("options") if isinstance(params, Mapping) else None
    for option in options if isinstance(options, list) else []:
        if isinstance(option, dict) and option.get("kind") == wanted:
            option_id = option.get("optionId")
            if isinstance(option_id, str) and option_id:
                return {"outcome": {"outcome": "selected", "optionId": option_id}}
    return {"outcome": {"outcome": "cancelled"}}


# --- The event mapper (D10) -----------------------------------------------------------------------

_KIND_LABELS = {
    "execute": "shell",
    "edit": "edit",
    "delete": "delete",
    "move": "move",
    "read": "read",
    "search": "search",
    "fetch": "fetch",
    "think": "think",
}
_KIND_CATEGORIES = {
    "execute": "command",
    "edit": "file_change",
    "delete": "file_change",
    "move": "file_change",
}
_TERMINAL_STATUSES = ("completed", "failed")
#: Updates that carry nothing for the timeline (D10, *Dropped*). They do not close a text block.
_DROPPED_UPDATES = (
    "user_message_chunk",
    "usage_update",
    "session_info_update",
    "current_mode_update",
    "config_option_update",
    "available_commands_update",
)
_NOTICE_PREFIXES = {"session.error": "Error", "session.warning": "Warning", "session.info": "Info"}
#: Statuses a server passes through on its way to `connected`; not a failure (unmeasured enum).
_TRANSIENT_SERVER_STATUSES = ("connected", "pending", "connecting", "starting")
#: The GitHub server's own statuses that mean it will not run (D9, R3): never `pending` (still
#: establishing) or `connected`. `stopped` is included because the schema says a managed policy
#: can pin it there.
_GITHUB_MCP_UNAVAILABLE_STATUSES = frozenset(
    {"failed", "needs-auth", "disabled", "stopped", "not_configured"}
)


@dataclass
class _Notice:
    """A raw `session.warning|info` waiting for the `Warning:`/`Info:` message block Copilot
    echoes it into. A `session.error` is not one: it is recorded when it arrives (slice 5 D5)."""

    event_type: str
    message: str
    data: Dict[str, Any]
    subagent: bool


def _is_subagent(params: Mapping[str, Any], data: Mapping[str, Any]) -> bool:
    """A subagent's event carries the envelope's `agentId` (absent for the root agent), or
    `data.agentId`/`data.parentToolCallId` (review, cross-slice finding 8)."""
    return bool(
        (isinstance(params, Mapping) and params.get("agentId"))
        or data.get("agentId")
        or data.get("parentToolCallId")
    )


def _subagent_id(params: Mapping[str, Any], data: Mapping[str, Any]) -> Optional[str]:
    """Which subagent an event is from, by the same three signals as `_is_subagent`."""
    for value in (
        params.get("agentId") if isinstance(params, Mapping) else None,
        data.get("agentId"),
        data.get("parentToolCallId"),
    ):
        if isinstance(value, str) and value:
            return value
    return None


#: A Copilot `errorType` that may name an error code (D5); anything else is `copilot.unknown`.
_ERROR_TYPE_RE = re.compile(r"^[a-z_]{1,32}$")

#: Root `errorType`s the same input cannot get past by being sent again: a refused credential
#: stays refused until the operator changes it, and a spent quota until it resets (F489).
UNRETRYABLE_ERROR_KINDS = frozenset({"authentication", "quota"})
_SUBAGENT_PHASES = {
    "subagent.started": "subagent_started",
    "subagent.completed": "subagent_completed",
    "subagent.failed": "subagent_failed",
}


def _count(value: Any) -> Optional[int]:
    """A reported count, or None: never a bool, never a string."""
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _compaction_facts(
    pre: Optional[int], post: Optional[int], limit: Optional[int], trigger: Any
) -> Dict[str, Any]:
    facts: Dict[str, Any] = {
        "pre_tokens": pre,
        "post_tokens": post,
        "token_limit": limit,
        "trigger": trigger if isinstance(trigger, str) and trigger else None,
    }
    if pre is not None and limit:
        facts["percent"] = round(pre / limit * 100, 2)
    return facts


def _content_text(content: Any) -> str:
    """The text of an ACP content list (`[{type: "content", content: {type: "text", text}}]`)."""
    if not isinstance(content, list):
        return ""
    parts: List[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        inner = item.get("content") if item.get("type") == "content" else item
        if isinstance(inner, dict) and inner.get("type") == "text":
            text = inner.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _diff_changes(content: Any) -> List[Dict[str, Any]]:
    if not isinstance(content, list):
        return []
    return [
        {"path": item.get("path"), "oldText": item.get("oldText"), "newText": item.get("newText")}
        for item in content
        if isinstance(item, dict) and item.get("type") == "diff"
    ]


class CopilotEventMapper:
    """Per-turn state turning armed ACP updates and raw session events into `RunEvent`s (D10).

    `on_session_update(update)` and `on_raw_event(type, data, params)` each return the events to
    emit; `flush()` closes the open text/thought block; `finish()` flushes at prompt completion and
    reports any raw warning or info Copilot never echoed. Arming is the caller's: this class maps whatever it
    is handed. `calls` may be the turn's shared map; feeding it here as well is idempotent.
    """

    def __init__(
        self,
        *,
        told_access_path: Optional[str] = None,
        requested_model: Optional[str] = None,
        calls: Optional[Dict[str, CallFacts]] = None,
        github_mcp: bool = False,
        review_agents: Sequence[str] = (),
    ) -> None:
        self.told_access_path = told_access_path
        self.requested_model = requested_model
        self.calls: Dict[str, CallFacts] = calls if calls is not None else {}
        #: The agent's own GitHub-tools toggle (D9): arms the GitHub-server-unavailable diagnostic.
        self.github_mcp = github_mcp
        #: The model Copilot actually ran, from the first raw event naming one.
        self.resolved_model: Optional[str] = None
        #: The root agent's first `session.error` message this turn; it fails the turn (D10, R3).
        self.root_error: Optional[str] = None
        #: That error's `errorType`, normalized as its `copilot.<kind>` event code is (F489).
        self.root_error_kind: Optional[str] = None
        self._message: List[str] = []
        self._thought: List[str] = []
        self._notices: List[_Notice] = []
        #: `"Error: " + message` of each `session.error` of this turn, root or subagent, whose
        #: echo chunk has not arrived yet (D5). Each one swallows at most one chunk.
        self._error_echoes: List[str] = []
        #: The turn's latest root `session.compaction_start`: the counts a compaction report too
        #: large to relay no longer carries (D4, *Omitted data*).
        self._compaction_start: Optional[Dict[str, Any]] = None
        #: The review agents this turn's context named (D8a); non-empty makes `finish()` report.
        self.review_agents: List[str] = [
            str(name) for name in review_agents if isinstance(name, str) and name
        ]
        #: Every subagent the turn reported, by its `task` call id, in first-seen order (D8a).
        self._subagents: Dict[str, Dict[str, Any]] = {}
        self._tools: Dict[str, str] = {}
        self._changes: Dict[str, List[Dict[str, Any]]] = {}
        self._last_plan: Optional[str] = None
        self._server_failure_reported = False
        self._github_mcp_failure_reported = False
        self._available_models: Optional[List[str]] = None

    # ACP session updates ---------------------------------------------------------------------

    def on_session_update(self, update: Mapping[str, Any]) -> List[RunEvent]:
        if not isinstance(update, Mapping):
            return []
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            text = self._chunk_text(update)
            if text in self._error_echoes:
                # Copilot's echo of a `session.error` already recorded as an error event when the
                # raw event arrived (D5): one fact, one record. Nothing is held, so the prose
                # around it is recorded as it is.
                self._error_echoes.remove(text)
                return []
            events = self._flush_thought()
            self._message.append(text)
            return events
        if kind == "agent_thought_chunk":
            events = self._flush_message()
            self._thought.append(self._chunk_text(update))
            return events
        if kind in _DROPPED_UPDATES:
            # `user_message_chunk` is the input the Hub already recorded, as Codex drops
            # `userMessage`; the rest carry no timeline content.
            return []
        if kind == "tool_call":
            return self.flush() + self._tool_call(update)
        if kind == "tool_call_update":
            return self.flush() + self._tool_call_update(update)
        if kind == "plan":
            return self.flush() + self._plan(update)
        return []

    @staticmethod
    def _chunk_text(update: Mapping[str, Any]) -> str:
        content = update.get("content")
        if isinstance(content, dict) and isinstance(content.get("text"), str):
            return content["text"]
        return ""

    def _label(self, update: Mapping[str, Any]) -> Tuple[str, str]:
        """`(tool, category)`. An MCP call is recognised first, from Copilot's own report in
        `calls`, never by its `kind`: that is guessed from the tool name by substring (`YDo`), so
        `agentweave-create_task` would read as a file edit (R3). Never the model-written title."""
        call_id = update.get("toolCallId")
        facts = self.calls.get(call_id) if isinstance(call_id, str) else None
        if facts is not None and facts.mcp_server:
            return f"{facts.mcp_server}-{facts.mcp_tool or facts.tool_name or '?'}", "mcp"
        kind = update.get("kind")
        if kind == "other" or kind not in _KIND_LABELS:
            name = facts.tool_name if facts is not None and facts.tool_name else "other"
            return name, "other"
        return _KIND_LABELS[kind], _KIND_CATEGORIES.get(kind, "other")

    def _tool_call(self, update: Mapping[str, Any]) -> List[RunEvent]:
        call_id = update.get("toolCallId")
        if not isinstance(call_id, str) or not call_id or call_id in self._tools:
            return []
        tool, category = self._label(update)
        self._tools[call_id] = tool
        changes = _diff_changes(update.get("content"))
        self._changes.setdefault(call_id, []).extend(changes)
        input_data: Dict[str, Any] = {
            "title": update.get("title"),
            "rawInput": update.get("rawInput"),
            "locations": update.get("locations"),
        }
        if changes:
            input_data["changes"] = changes
        title = update.get("title")
        events = [
            tool_use_event(
                tool=tool,
                category=category,
                input_data=input_data,
                call_id=call_id,
                summary=title if isinstance(title, str) and title else None,
            )
        ]
        if update.get("status") in _TERMINAL_STATUSES:
            events += self._tool_result(call_id, update)
        return events

    def _tool_call_update(self, update: Mapping[str, Any]) -> List[RunEvent]:
        call_id = update.get("toolCallId")
        if not isinstance(call_id, str) or not call_id:
            return []
        self._changes.setdefault(call_id, []).extend(_diff_changes(update.get("content")))
        if update.get("status") not in _TERMINAL_STATUSES:
            # Streamed partial output: only the terminal update carries the whole of it.
            return []
        return self._tool_result(call_id, update)

    def _tool_result(self, call_id: str, update: Mapping[str, Any]) -> List[RunEvent]:
        tool = self._tools.get(call_id) or self._label(update)[0]
        output = _content_text(update.get("content"))
        raw_output = update.get("rawOutput")
        if not output and isinstance(raw_output, dict):
            for key in ("content", "message"):
                value = raw_output.get(key)
                if isinstance(value, str) and value:
                    output = value
                    break
        return [
            tool_result_event(
                tool=tool,
                output=output,
                call_id=call_id,
                is_error=update.get("status") == "failed",
            )
        ]

    def _plan(self, update: Mapping[str, Any]) -> List[RunEvent]:
        entries = update.get("entries")
        steps = [
            str(entry.get("content"))
            for entry in (entries if isinstance(entries, list) else [])
            if isinstance(entry, dict) and entry.get("content")
        ]
        event = status_event("plan", summary="; ".join(steps) or "plan updated")
        if event.content == self._last_plan:
            return []
        self._last_plan = event.content
        return [event]

    # Text blocks -------------------------------------------------------------------------------

    def flush(self) -> List[RunEvent]:
        """Close the open thought and message blocks, one event each."""
        return self._flush_thought() + self._flush_message()

    def finish(self) -> List[RunEvent]:
        """At prompt completion: flush, then report every raw warning or info no block echoed.
        An error needs no such sweep: it was recorded when its raw event arrived (slice 5 D5)."""
        events = self.flush()
        for notice in self._notices:
            events.append(self._notice_event(notice))
        self._notices = []
        if self.review_agents:
            # Last, after the notices. A broken report loses the card, never the turn: a raise
            # here would escape `run_turn` and record a finished review as a failed run (D8a).
            try:
                events.append(self._review_agents_report())
            except Exception:  # noqa: BLE001
                logger.warning("Could not build the review agents report", exc_info=True)
            self.review_agents = []
        return events

    def _review_agents_report(self) -> RunEvent:
        """Which Copilot subagents this run reported, against the review agents its context named
        (D8a, F484). A fact beside the reviewer's own words, not a judgement of them: an asked
        agent counts as run only when its dispatch id matches and, where Copilot reported one,
        its type does too, so a repository's own agent of the same name does not."""
        ran = [dict(entry) for entry in self._subagents.values()]
        missing = [
            name
            for name in self.review_agents
            if not any(
                entry["agent_name"] == name and entry.get("agent_type") in (None, name)
                for entry in ran
            )
        ]
        asked = ", ".join(f"`{name}`" for name in self.review_agents)
        verb = "consult" if len(self.review_agents) == 1 else "consult each of"
        summary = f"This review was asked to {verb} {asked}; "
        if ran:
            summary += "in this run Copilot ran " + ", ".join(
                f"`{entry['agent_name']}` ({entry['outcome']}"
                + (f", {entry['model']}" if entry.get("model") else "")
                + ")"
                for entry in ran
            )
            summary += (
                "."
                if not missing
                else ("; " + ", ".join(f"`{name}`" for name in missing) + " did not run.")
            )
        else:
            summary += "Copilot ran no subagent in this run."
        return status_event(
            "review_agents_report",
            summary=summary,
            facts={"asked": list(self.review_agents), "ran": ran, "missing": missing},
        )

    def _flush_thought(self) -> List[RunEvent]:
        text = "".join(self._thought)
        self._thought = []
        return [thinking_event(text)] if text.strip() else []

    def _flush_message(self) -> List[RunEvent]:
        text = "".join(self._message)
        self._message = []
        return self._classify(text)

    def _classify(self, text: str) -> List[RunEvent]:
        """A message block is a Copilot notice only when a raw `session.warning|info` of this
        turn carries the text it holds: a model can write "Warning:" too (D10)."""
        if not text.strip():
            return []
        for notice in self._notices:
            needle = f"{_NOTICE_PREFIXES[notice.event_type]}: {notice.message}"
            at = text.find(needle)
            if at < 0:
                continue
            self._notices.remove(notice)
            return (
                self._classify(text[:at])
                + [self._notice_event(notice)]
                + self._classify(text[at + len(needle) :])
            )
        return [text_event(text.strip())]

    def _notice_event(self, notice: _Notice) -> RunEvent:
        if notice.event_type == "session.warning":
            kind = notice.data.get("warningType")
            severity = "warning"
        else:
            kind = notice.data.get("infoType")
            severity = "info"
        fallback = "warning" if severity == "warning" else "info"
        code = f"copilot.{kind if isinstance(kind, str) and kind else fallback}"
        return diagnostic_event(
            stream="copilot", severity=severity, summary=notice.message, code=code
        )

    # Raw session events -------------------------------------------------------------------------

    def on_raw_event(
        self, event_type: str, data: Any, params: Optional[Mapping[str, Any]] = None
    ) -> List[RunEvent]:
        data = data if isinstance(data, dict) else {}
        params = params if isinstance(params, Mapping) else {}
        track_call(self.calls, event_type, data)
        if event_type == "session.error":
            return self._after_open_blocks(self._session_error(data, params))
        if event_type in _NOTICE_PREFIXES:
            message = data.get("message")
            if not isinstance(message, str) or not message:
                return []
            subagent = _is_subagent(params, data)
            self._notices.append(_Notice(event_type, message, dict(data), subagent))
            return []
        if event_type == "session.compaction_start":
            if not _is_subagent(params, data):
                self._compaction_start = dict(data)
            return []
        if event_type == "session.compaction_complete":
            return self._after_open_blocks(self._compaction(data, params))
        if event_type in _SUBAGENT_PHASES:
            return self._after_open_blocks(self._subagent(event_type, data, params))
        if event_type in ("session.mcp_servers_loaded", "session.mcp_server_status_changed"):
            return self._server_status(event_type, data)
        if event_type in (
            "session.model_change",
            "session.auto_mode_resolved",
            "session.tools_updated",
        ):
            return self._model(event_type, data)
        return []

    def _after_open_blocks(self, events: List[RunEvent]) -> List[RunEvent]:
        """A card a raw event produces closes the open text and thought blocks first, so the
        timeline reads in the order things happened: the text was streamed before the raw event
        arrived (drive 7.2, 2026-10-04, found the `compacted` card ahead of the reply before it).
        A raw event that produces nothing leaves the blocks open."""
        return self.flush() + events if events else events

    def _session_error(self, data: Mapping[str, Any], params: Mapping[str, Any]) -> List[RunEvent]:
        """A `session.error` is one error event, recorded when it arrives (D5). Only the root
        agent's fails the turn; a subagent's names the subagent and the turn goes on."""
        message = data.get("message")
        if not isinstance(message, str) or not message:
            return []
        subagent_id = _subagent_id(params, data)
        error_type = data.get("errorType")
        kind = (
            error_type
            if isinstance(error_type, str) and _ERROR_TYPE_RE.match(error_type)
            else "unknown"
        )
        if subagent_id is None and self.root_error is None:
            self.root_error = message
            self.root_error_kind = kind
        self._error_echoes.append(f"Error: {message}")
        return [
            error_event(
                code=f"copilot.{kind}",
                message=message,
                facts={
                    "status_code": _count(data.get("statusCode")),
                    "error_code": data.get("errorCode"),
                    "remediation": data.get("remediation"),
                    "subagent_id": subagent_id,
                },
            )
        ]

    def _compaction(self, data: Mapping[str, Any], params: Mapping[str, Any]) -> List[RunEvent]:
        """Only the root agent's compaction is the conversation's (D4, R3)."""
        if _is_subagent(params, data):
            return []
        omitted = params.get("dataOmitted")
        if omitted == "too-large":
            # An oversized report carried a summary, which only a successful compaction has; its
            # counts come from the turn's latest root `compaction_start` (D4, *Omitted data*).
            start = self._compaction_start or {}
            facts = _compaction_facts(
                _count(start.get("currentTokens")),
                None,
                _count(start.get("tokenLimit")),
                start.get("trigger"),
            )
            return [
                status_event(
                    "compacted",
                    summary=(
                        "Copilot compacted this conversation; its report was too large to relay."
                    ),
                    facts=facts,
                )
            ]
        if omitted:
            return [
                diagnostic_event(
                    stream="copilot",
                    severity="warning",
                    summary="Copilot reported a compaction this Hub could not read.",
                    code="copilot.compaction_unreadable",
                    facts={"data_omitted": str(omitted)},
                )
            ]
        if data.get("success") is not True:
            error = data.get("error")
            return [
                diagnostic_event(
                    stream="copilot",
                    severity="warning",
                    summary=(
                        f"Copilot's compaction failed: {error}"
                        if isinstance(error, str) and error
                        else "Copilot's compaction failed; the conversation was not compacted."
                    ),
                    code="copilot.compaction_failed",
                    facts={"status_code": _count(data.get("statusCode"))},
                )
            ]
        pre = _count(data.get("preCompactionTokens"))
        post = _count(data.get("postCompactionTokens"))
        limit = _count(data.get("tokenLimit"))
        trigger = data.get("trigger")
        how = "as requested" if trigger == "manual" else "automatically"
        sizes = " → ".join(f"{n:,}" for n in (pre, post) if n is not None)
        if sizes and limit is not None:
            sizes += f" tokens of {limit:,}"
        elif sizes:
            sizes += " tokens"
        summary = f"Copilot compacted this conversation {how}" + (f" ({sizes})." if sizes else ".")
        return [
            status_event(
                "compacted", summary=summary, facts=_compaction_facts(pre, post, limit, trigger)
            )
        ]

    def _remember_subagent(
        self, event_type: str, call_id: str, data: Mapping[str, Any], params: Mapping[str, Any]
    ) -> None:
        """For the review agents report (D8a): the dispatch id (`agentName`), the type Copilot
        reported (on `subagent.started`), the subagent's own `agentId`, and how it ended."""
        entry = self._subagents.setdefault(
            call_id,
            {
                "agent_name": None,
                "agent_type": None,
                "agent_id": None,
                "outcome": "started",
                "model": None,
            },
        )
        for key, value in (
            ("agent_name", data.get("agentName")),
            ("agent_type", data.get("agentType")),
            ("agent_id", params.get("agentId") if isinstance(params, Mapping) else None),
            ("model", data.get("model")),
        ):
            if isinstance(value, str) and value:
                entry[key] = value
        if event_type == "subagent.completed":
            entry["outcome"] = "completed"
        elif event_type == "subagent.failed":
            entry["outcome"] = "failed"

    def _subagent(
        self, event_type: str, data: Mapping[str, Any], params: Optional[Mapping[str, Any]] = None
    ) -> List[RunEvent]:
        """A subagent's start, completion or failure, paired with its `task` call by `call_id`
        (D6). Never by position: a raw event can overtake the queued `tool_use`."""
        call_id = data.get("toolCallId")
        if not isinstance(call_id, str) or not call_id:
            return []
        self._remember_subagent(event_type, call_id, data, params)
        name = data.get("agentDisplayName") or data.get("agentName") or "A Copilot subagent"
        error = data.get("error")
        if event_type == "subagent.started":
            summary = f"{name} started"
        elif event_type == "subagent.completed":
            summary = f"{name} finished"
        else:
            summary = (
                f"{name} failed: {redact_secrets(error)}"
                if isinstance(error, str) and error
                else f"{name} failed"
            )
        return [
            status_event(
                _SUBAGENT_PHASES[event_type],
                summary=summary,
                facts={
                    "call_id": call_id,
                    "agent_name": data.get("agentName"),
                    "model": data.get("model"),
                    "total_tokens": _count(data.get("totalTokens")),
                    "duration_ms": _count(data.get("durationMs")),
                    "total_tool_calls": _count(data.get("totalToolCalls")),
                    "cancelled": (
                        data.get("cancelled") if isinstance(data.get("cancelled"), bool) else None
                    ),
                    "error": error if isinstance(error, str) and error else None,
                },
            )
        ]

    def _server_status(self, event_type: str, data: Mapping[str, Any]) -> List[RunEvent]:
        if event_type == "session.mcp_servers_loaded":
            reported = data.get("servers")
            entries = (
                [e for e in reported if isinstance(e, dict)] if isinstance(reported, list) else []
            )
        else:
            entries = [dict(data)]
        for entry in entries:
            name = entry.get("name") or entry.get("serverName")
            status = entry.get("status")
            if not isinstance(status, str):
                continue
            if name == GITHUB_MCP_SERVER_NAME and self.github_mcp:
                # D9, R3: only a status that means the server will not run, never `pending`
                # (still establishing) or `connected`; the toggle being off disables the server
                # on purpose, so nothing is reported then.
                if (
                    status not in _GITHUB_MCP_UNAVAILABLE_STATUSES
                    or self._github_mcp_failure_reported
                ):
                    continue
                self._github_mcp_failure_reported = True
                return [
                    diagnostic_event(
                        stream="copilot",
                        severity="warning",
                        summary=(
                            f"Copilot reported its built-in GitHub MCP server ({name}) as "
                            f"{status}; this agent's GitHub-tools toggle is on, but its GitHub "
                            "calls will not run."
                        ),
                        code="copilot.github_mcp_unavailable",
                        facts={"status": status},
                    )
                ]
            if name != HUB_MCP_SERVER_NAME:
                continue
            if status in _TRANSIENT_SERVER_STATUSES or self._server_failure_reported:
                continue
            self._server_failure_reported = True
            detail = entry.get("error") or entry.get("message") or status
            if self.told_access_path == "mcp":
                # The same sentence Codex's `map_mcp_server_failure` gives: true only of a run
                # that was told the MCP form (R3).
                return [
                    error_event(
                        code="copilot_mcp_server_failed",
                        message=(
                            f"The AgentWeave MCP server ({name}) failed to start, so this turn "
                            "had no AgentWeave tools -- no messages, evidence, task updates or "
                            f"questions: {detail}"
                        ),
                    )
                ]
            return [
                diagnostic_event(
                    stream="copilot",
                    severity="warning",
                    summary=(
                        f"Copilot reported the AgentWeave MCP server ({name}) as {status}; this "
                        "run was told to reach the Hub with `aw-tool`."
                    ),
                    code="copilot.mcp_server_unavailable",
                    facts={"status": status},
                )
            ]
        return []

    def _model(self, event_type: str, data: Mapping[str, Any]) -> List[RunEvent]:
        if event_type == "session.auto_mode_resolved":
            available = data.get("availableModels")
            if isinstance(available, list):
                self._available_models = [str(m) for m in available]
        field_name = {
            "session.model_change": "newModel",
            "session.auto_mode_resolved": "chosenModel",
            "session.tools_updated": "model",
        }[event_type]
        model = data.get(field_name)
        # `session.model_change` reports `newModel: "auto"` at startup (captured): the request,
        # not a resolution. Only a concrete model resolves it.
        if self.resolved_model is not None or not isinstance(model, str):
            return []
        if not model or model == "auto":
            return []
        self.resolved_model = model
        requested = self.requested_model
        if not requested or requested == "auto" or requested == model:
            return []
        summary = f"Copilot ran {model} instead of the requested {requested}"
        if self._available_models:
            summary += f"; this plan allows: [{', '.join(self._available_models)}]"
        return [
            diagnostic_event(
                stream="copilot",
                severity="info",
                summary=summary + ".",
                code="copilot.model_substituted",
                facts={"requested": requested, "resolved": model},
            )
        ]


def usage_sample(
    update: Mapping[str, Any], *, model: Optional[str]
) -> Optional[ContextUsageSample]:
    """`usage_update {used, size}` as the context meter's sample (D11). The window comes from the
    provider's report, never the catalog; a missing or non-positive `size` is `unavailable`."""
    used = update.get("used")
    size = update.get("size")
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None
    if isinstance(size, bool) or not isinstance(size, (int, float)) or size <= 0:
        return ContextUsageSample(
            status="unavailable",
            source="copilot_acp",
            basis=None,
            context_tokens=int(used),
            limit_tokens=None,
            model=model,
            breakdown=None,
        )
    return ContextUsageSample(
        status="measured",
        source="copilot_acp",
        basis="provider_context",
        context_tokens=int(used),
        limit_tokens=int(size),
        model=model,
        breakdown=None,
    )


# --- The process (D3, D17) ------------------------------------------------------------------------

NotificationHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]
ServerRequestHandler = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


@dataclass
class _Pending:
    method: str
    future: "asyncio.Future[Dict[str, Any]]"


class ACPProcess:
    """A JSON-RPC session over one `copilot.exe --acp --stdio` process's stdio.

    Like `AppServerProcess`: one process per turn, newline-delimited JSON decoded as UTF-8
    explicitly, stderr drained into a bounded tail, and every pending request failed when the
    process ends. Unlike it, the read loop delivers each notification and each agent->client
    request to a handler **in wire order**, awaiting it before reading the next message: a raw
    `tool.execution_start` must be in `calls` before the permission request it describes is judged,
    and a request is answered before the next message is read. So a request's response can be
    awaited while that request's notifications are delivered, which `session/prompt` needs.

    `request()` returns the response's `result`, and raises `CopilotACPError(code=, data=)` for a
    response holding `error`: nothing indexes `["result"]` of an error by accident.
    """

    def __init__(
        self,
        proc: "asyncio.subprocess.Process",
        *,
        on_notification: Optional[NotificationHandler] = None,
        on_server_request: Optional[ServerRequestHandler] = None,
    ) -> None:
        self._proc = proc
        self._on_notification = on_notification
        self._on_server_request = on_server_request
        self._next_id = 0
        self._pending: Dict[int, _Pending] = {}
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._stderr: Deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._write_lock = asyncio.Lock()
        self._closed = False

    @classmethod
    async def spawn(
        cls,
        cmd: List[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        on_notification: Optional[NotificationHandler] = None,
        on_server_request: Optional[ServerRequestHandler] = None,
    ) -> "ACPProcess":
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=STDOUT_LINE_LIMIT,
            # Its own process group on POSIX. `close()` ends the tree with
            # `terminate_process_tree`, which there kills the child's *group*; a child left in the
            # Hub's group would take the Hub down with it (measured under WSL, 2026-09-30: the test
            # runner was killed by the first `close()`). Windows walks the pid tree instead.
            **({} if os.name == "nt" else {"start_new_session": True}),
            **no_console_kwargs(),
        )
        session = cls(proc, on_notification=on_notification, on_server_request=on_server_request)
        loop = asyncio.get_running_loop()
        session._reader_task = loop.create_task(session._read_loop())
        session._stderr_task = loop.create_task(session._drain_stderr())
        return session

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid

    @property
    def returncode(self) -> Optional[int]:
        return self._proc.returncode

    def is_running(self) -> bool:
        return self._proc.returncode is None

    def stderr_tail(self, *, limit: int = STDERR_TAIL_CHARS) -> str:
        joined = " | ".join(line for line in self._stderr if line)
        if len(joined) <= limit:
            return joined
        return "…" + joined[-limit:]

    def process_ended_error(self, message: str, method: Optional[str] = None) -> AppServerError:
        return AppServerError(
            message, exit_code=self._proc.returncode, method=method, stderr_tail=self.stderr_tail()
        )

    async def _drain_stderr(self) -> None:
        stream = self._proc.stderr
        if stream is None:
            return
        try:
            while True:
                try:
                    raw = await stream.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    raw = await stream.read(65536)
                if not raw:
                    break
                self._stderr.append(raw.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - draining diagnostics must never raise into a turn
            logger.debug("copilot stderr drain ended early", exc_info=True)

    async def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        try:
            while True:
                try:
                    raw = await self._proc.stdout.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    logger.warning("copilot emitted a stdout line over %d bytes", STDOUT_LINE_LIMIT)
                    continue
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("copilot emitted a non-JSON stdout line: %r", line[:200])
                    continue
                if isinstance(msg, dict):
                    await self._dispatch(msg)
        except asyncio.CancelledError:
            pass
        finally:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(self._proc.wait()), timeout=1)
            self._fail_pending("copilot process ended")

    async def _dispatch(self, msg: Dict[str, Any]) -> None:
        msg_id = msg.get("id")
        method = msg.get("method")
        if method is None and msg_id is not None and ("result" in msg or "error" in msg):
            pending = self._pending.pop(msg_id, None)
            if pending is None or pending.future.done():
                return
            error = msg.get("error")
            if error is not None:
                error = error if isinstance(error, dict) else {"message": str(error)}
                pending.future.set_exception(
                    CopilotACPError(
                        error.get("message"),
                        code=error.get("code"),
                        data=error.get("data"),
                        method=pending.method,
                    )
                )
            else:
                result = msg.get("result")
                pending.future.set_result(result if isinstance(result, dict) else {})
            return
        if not isinstance(method, str):
            return
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if msg_id is None:
            if self._on_notification is not None:
                try:
                    await self._on_notification(method, params)
                except Exception:  # noqa: BLE001 - one bad notification must not end the turn
                    logger.warning("handling copilot notification %s failed", method, exc_info=True)
            return
        # An agent->client request. Always answered: silence would hang the turn.
        try:
            if self._on_server_request is None:
                raise CopilotACPError("Method not found", code=METHOD_NOT_FOUND_CODE)
            result = await self._on_server_request(method, params)
        except CopilotACPError as exc:
            await self._respond_error(msg_id, exc.code or INTERNAL_ERROR_CODE, str(exc))
            return
        except Exception as exc:  # noqa: BLE001 - answered with an error, never silence
            logger.warning("handling copilot request %s failed", method, exc_info=True)
            await self._respond_error(msg_id, INTERNAL_ERROR_CODE, type(exc).__name__)
            return
        await self._write({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _fail_pending(self, message: str) -> None:
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(self.process_ended_error(message, pending.method))
        self._pending.clear()

    async def _write(self, message: Dict[str, Any]) -> None:
        if self._proc.stdin is None:
            raise AppServerError("copilot stdin is not available")
        data = (json.dumps(message) + "\n").encode("utf-8")
        async with self._write_lock:
            self._proc.stdin.write(data)
            await self._proc.stdin.drain()

    async def _respond_error(self, request_id: Any, code: int, message: str) -> None:
        with contextlib.suppress(Exception):
            await self._write(
                {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
            )

    async def request(
        self,
        method: str,
        params: Dict[str, Any],
        *,
        timeout: Optional[float] = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        """Send a request and await its `result`. `timeout=None` waits as long as the process
        lives (the prompt); its notifications reach the handlers meanwhile."""
        if not self.is_running() or self._closed:
            raise self.process_ended_error("copilot process ended", method)
        self._next_id += 1
        msg_id = self._next_id
        future: "asyncio.Future[Dict[str, Any]]" = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = _Pending(method=method, future=future)
        try:
            await self._write({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def close(self, *, force: bool = False) -> None:
        """End the process **tree**, on every exit (D17): `copilot.exe` runs its shells as
        children, and a single-process kill would leave `powershell.exe` behind. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self.is_running() and self._proc.pid is not None:
            with contextlib.suppress(Exception):
                await asyncio.to_thread(terminate_process_tree, self._proc.pid, force)
        if self._proc.stdin is not None:
            with contextlib.suppress(Exception):
                self._proc.stdin.close()
        try:
            await asyncio.wait_for(self._proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                self._proc.kill()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._proc.wait(), timeout=5)
        for task in (self._reader_task, self._stderr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
        self._fail_pending("copilot process closed")


# --- Argv (D3) ------------------------------------------------------------------------------------


def strip_widening_flags(
    flags: Optional[Sequence[str]], *, full_access: bool
) -> Tuple[List[str], List[str]]:
    """Split runner flags into `(kept, removed)`, removed naming each flag once per occurrence.

    Both `--flag value` and `--flag=value` forms; a many-valued flag (`--allow-tool a b`) takes
    every following word up to the next `-` word. Under Full access only `--config-dir` goes."""
    kept: List[str] = []
    removed: List[str] = []
    words = [str(w) for w in (flags or [])]
    i = 0
    while i < len(words):
        word = words[i]
        name = word.split("=", 1)[0]
        arity = COPILOT_WIDENING_FLAGS.get(name)
        widening = arity is not None and (not full_access or name in _ALWAYS_REMOVED_FLAGS)
        if not widening:
            kept.append(word)
            i += 1
            continue
        removed.append(name)
        i += 1
        if "=" in word or arity == "none":
            continue
        if arity == "one":
            if i < len(words) and not words[i].startswith("-"):
                i += 1
            continue
        while i < len(words) and not words[i].startswith("-"):
            i += 1
    return kept, removed


def build_acp_argv(
    executable: Any,
    *,
    model: Optional[str] = None,
    control_overrides: Optional[Mapping[str, str]] = None,
    spec_turn: bool = False,
    runner_flags: Optional[Sequence[str]] = None,
    full_access: bool = False,
    mcp_config: Optional[str] = None,
    github_mcp: bool = False,
) -> List[str]:
    """The spawn argv of one Copilot turn (D3). `--agent` is never passed (it does not reach an
    ACP session, VERIFIED); the agent is selected over ACP instead (D6). `--model` is omitted for
    `auto`, Copilot's own default. Effort is a flag control, rendered from the raw controls
    (`render_control_args`), since the trigger builds no Copilot argv. Widening runner flags are
    removed unless the run is under Full access; a spec turn never is (D9). `github_mcp` is the
    agent's own toggle (D9): omits `--disable-builtin-mcps` so Copilot's built-in MCP servers
    (GitHub's among them) load."""
    from .model_catalog import render_control_args

    argv = [str(executable), "--acp", "--stdio", "--no-auto-update"]
    if not github_mcp:
        argv.append("--disable-builtin-mcps")
    if mcp_config:
        argv += ["--additional-mcp-config", f"@{mcp_config}"]
    if model and model != "auto":
        argv += ["--model", model]
    argv += render_control_args("copilot", dict(control_overrides or {}))
    if spec_turn:
        argv.append("--excluded-tools=" + ",".join(SPEC_TURN_EXCLUDED_TOOLS))
    kept, _removed = strip_widening_flags(runner_flags, full_access=full_access and not spec_turn)
    return argv + kept


# --- One turn -------------------------------------------------------------------------------------


@dataclass
class TurnOutcome:
    """Result of one `run_turn`, as `codex_appserver.TurnOutcome` with the session in place of
    the thread. Slice 4's usage lives inside `run_turn`, not here (D10, R3)."""

    session_id: Optional[str]
    status: str  # "completed" | "failed" | "interrupted"
    error: Optional[str] = None
    #: Copilot's own exit status where it ended; not written to `Run.exit_code`.
    exit_code: Optional[int] = None
    #: What Copilot last wrote to its error stream, for a failure that raised nothing.
    stderr_tail: Optional[str] = None
    #: `False` when the turn failed in a way the same input cannot fix on retry; `None` keeps
    #: the queue's ordinary retry (F489). Never `True`: nothing claims a retry will succeed.
    retryable: Optional[bool] = None
    #: The root `session.error`'s `errorType` that failed the turn, where one did.
    error_kind: Optional[str] = None


def _options_of(response: Mapping[str, Any]) -> Optional[List[Dict[str, Any]]]:
    options = response.get("configOptions") if isinstance(response, Mapping) else None
    return [o for o in options if isinstance(o, dict)] if isinstance(options, list) else None


def _option(options: Optional[List[Dict[str, Any]]], option_id: str) -> Optional[Dict[str, Any]]:
    for option in options or []:
        if option.get("id") == option_id:
            return option
    return None


def _selected_description(option: Mapping[str, Any]) -> Optional[str]:
    current = option.get("currentValue")
    for value in option.get("options") or []:
        if isinstance(value, dict) and value.get("value") == current:
            description = value.get("description")
            return description if isinstance(description, str) else None
    return None


def _loaded_mode(response: Mapping[str, Any], options: Optional[List[Dict[str, Any]]]) -> Any:
    modes = response.get("modes") if isinstance(response, Mapping) else None
    if isinstance(modes, dict) and modes.get("currentModeId"):
        return modes.get("currentModeId")
    mode = _option(options, "mode")
    return mode.get("currentValue") if mode else None


def _mode_name(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value:
        return None
    return value.rsplit("#", 1)[-1]


#: How long the `/mcp list` diagnostic prompt may take; measured answering in ~5 ms (D9).
MCP_LIST_TIMEOUT_SECONDS = 10.0
#: The longest quote of Copilot's own sentence about the Hub's server (D12).
MCP_LIST_QUOTE_BYTES = 300


def hub_server_reports(event_type: str, data: Mapping[str, Any]) -> List[str]:
    """The recognised statuses (`connected`, `failed`) Copilot reports for the Hub's server in one
    raw event (D1, R3). Any other string -- `pending`, whatever a policy block says -- is not a
    report; the mapper shows it as a diagnostic."""
    if event_type == "session.mcp_servers_loaded":
        reported = data.get("servers")
        entries = [e for e in reported if isinstance(e, dict)] if isinstance(reported, list) else []
    elif event_type == "session.mcp_server_status_changed":
        entries = [dict(data)]
    else:
        return []
    return [
        str(entry.get("status"))
        for entry in entries
        if (entry.get("name") or entry.get("serverName")) == HUB_MCP_SERVER_NAME
        and entry.get("status") in ("connected", "failed")
    ]


async def _mcp_list_quote(session: Any, session_id: str, state: Dict[str, Any]) -> Optional[str]:
    """Send one `/mcp list` slash prompt -- no model call -- and return Copilot's own line about
    the Hub's server, bounded, for the operator (D9, D12). Shown verbatim, never keyed on. The
    prompt is exactly one text block: a slash command that is not the prompt's first text goes
    to the model as ordinary text (R3). Never raises; None when nothing came back."""
    state["collect"] = []
    try:
        await session.request(
            "session/prompt",
            {"sessionId": session_id, "prompt": [{"type": "text", "text": "/mcp list"}]},
            timeout=MCP_LIST_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 -- a diagnostic, never a reason to stop the turn
        logger.warning("Copilot's /mcp list diagnostic failed", exc_info=True)
    finally:
        chunks = state.pop("collect", None) or []
    text = "".join(chunks).strip()
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if HUB_MCP_SERVER_NAME in line]
    quoted, _ = _truncate_utf8(lines[0] if lines else text, MCP_LIST_QUOTE_BYTES)
    return quoted


def _context_block(per_turn_context: Optional[str], tool_surface_context: Optional[str]) -> str:
    parts = [COPILOT_TURN_CONTEXT_HEAD]
    for part in (per_turn_context, tool_surface_context):
        if part and part.strip():
            parts.append(part)
    return "\n\n".join(parts)


def _record_probe(
    *, present: bool, authorized: bool, reason: Optional[str], cli: Optional[str] = None
) -> None:
    """Tell `CopilotProbe` what this turn learned (D12, R3). Never raises. A runner's pinned
    executable is passed on, so the verdict is filed under the executable that was actually run."""
    extra = {"cli_override": cli} if cli else {}
    try:
        CopilotProbe.record(present=present, authorized=authorized, reason=reason, **extra)
    except Exception:  # noqa: BLE001 - a verdict note must never fail the turn
        logger.debug("recording the Copilot verdict failed", exc_info=True)


async def run_turn(
    *,
    cwd: Optional[str],
    env: Optional[Dict[str, str]],
    prompt: str,
    model: Optional[str],
    resume_session_id: Optional[str],
    agent: str,
    per_turn_context: Optional[str] = None,
    tool_surface_context: Optional[str] = None,
    stable_context: Optional[str] = None,
    control_overrides: Optional[Mapping[str, str]] = None,
    told_access_path: Optional[str] = None,
    permission_mode: Optional[str] = None,
    workspace: Optional[str] = None,
    restrict_spec_writes: bool = False,
    extra_flags: Optional[Sequence[str]] = None,
    cli: Optional[str] = None,
    mcp_command: Optional[Sequence[str]] = None,
    yolo: bool = False,
    agent_config: Optional[Mapping[str, Any]] = None,
    on_event: "Callable[[RunEvent], Awaitable[None]]",
    on_usage: "Optional[Callable[[ContextUsageSample], Awaitable[None]]]" = None,
    on_accounting: "Optional[Callable[[Any], Awaitable[None]]]" = None,
    on_session: "Optional[Callable[[str], Awaitable[None]]]" = None,
    on_session_missing: "Optional[Callable[[str], Awaitable[None]]]" = None,
    should_interrupt: "Optional[Callable[[], bool]]" = None,
    request_approval: "Optional[Callable[[str, Dict[str, Any]], Awaitable[bool]]]" = None,
    on_refusal: "Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]]" = None,
    on_decision: "Optional[Callable[[str, Dict[str, Any], bool], Awaitable[None]]]" = None,
    turn_timeout: float = DEFAULT_TURN_TIMEOUT_SECONDS,
    await_mcp_announce: "Optional[Callable[[], Awaitable[bool]]]" = None,
    render_surface: (
        "Optional[Callable[[str, Optional[bool], Optional[str]], Awaitable[List[str]]]]"
    ) = None,
    on_mcp_status: "Optional[Callable[[str], Awaitable[Any]]]" = None,
) -> TurnOutcome:
    """Drive one Copilot turn over ACP and return how it ended.

    Order (D6-D9; § "Provided to slices 3-5" item 2): spawn -> `initialize` (raw-event subscription,
    version gate) -> `session/new` or `session/load` (a `-32002` load starts a new session) ->
    `on_session` -> agent selection, and the deselect on a marker failure -> the posture step
    (`set_mode` every turn; `allow_all` set on under Full access, else read and turned off) ->
    `session/prompt`. The mapper is disarmed until the prompt is written, so replayed history and
    anything else before it produce no event; the `calls`/`servers` maps are fed from spawn on.

    `env` is the run environment the trigger built (filtered, with `COPILOT_HOME`); it is passed
    as-is. `mcp_command`, when set, means the access path is MCP: the argv names the home's
    `agentweave-mcp.json`. `cli` is a runner's pinned executable. `on_accounting` is called exactly
    once on every return once a session exists, with this call's `CopilotUsageLedger` sample
    (`a-copilot-run-shows-its-credits` D2); a raise delivers none. `agent_config` is the agent's own
    config, filtered to the keys a turn reads (D9); `copilot_github_mcp` is read as `is True` (review
    2026-09-28, finding 14), since the trigger stores a raw `config` and a string `"false"` is
    truthy.

    Raises (`CopilotACPError`, `FileNotFoundError`, `OSError`, `asyncio.TimeoutError`) only before
    the prompt is written; returns a `TurnOutcome` for everything after (D12, R3). A stop sends
    `session/cancel`, waits up to 10 s for `cancelled`, and ends `interrupted` (D17).
    """
    posture = posture_for(permission_mode, yolo=yolo)
    spec_turn = bool(restrict_spec_writes)
    github_mcp = (agent_config or {}).get("copilot_github_mcp") is True
    session_cwd = cwd or workspace
    if not session_cwd:
        raise CopilotACPError("A Copilot turn needs a working directory for its session.")
    run_hub_url = (env or {}).get("HUB_URL")

    mcp_config: Optional[str] = None
    if mcp_command:
        home = (env or {}).get("COPILOT_HOME")
        if not home:
            raise CopilotACPError(
                "A Copilot run given the MCP form has no COPILOT_HOME to find its MCP config in."
            )
        mcp_config = os.path.join(home, MCP_CONFIG_NAME)

    full_flags = posture == _FULL and not spec_turn
    _kept, removed_flags = strip_widening_flags(extra_flags, full_access=full_flags)
    for flag in removed_flags:
        await on_event(
            diagnostic_event(
                stream="copilot",
                severity="warning",
                summary=(
                    f"The runner flag {flag} was not passed to Copilot: "
                    + _FLAG_REMOVAL_REASONS.get(
                        flag,
                        "it lets Copilot approve actions on its own account, which this run's "
                        "posture does not allow",
                    )
                    + "."
                ),
                code="copilot.runner_flag_removed",
                facts={"flag": flag},
            )
        )

    executable = resolve_copilot_executable(cli)
    argv = build_acp_argv(
        executable,
        model=model,
        control_overrides=control_overrides,
        spec_turn=spec_turn,
        runner_flags=extra_flags,
        full_access=full_flags,
        mcp_config=mcp_config,
        github_mcp=github_mcp,
    )

    calls: Dict[str, CallFacts] = {}
    servers: Dict[str, List[Dict[str, Any]]] = {}
    # One ledger per call, fed only armed events and the prompt's own answer (D2).
    ledger = CopilotUsageLedger()
    mapper = CopilotEventMapper(
        told_access_path=told_access_path,
        requested_model=model,
        calls=calls,
        github_mcp=github_mcp,
        review_agents=[
            name
            for name in ((agent_config or {}).get("review_agents") or [])
            if isinstance(name, str)
        ],
    )
    # Server reports that arrive before arming (a load can bring one) reach the mapper at arming.
    early_server_events: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []

    state: Dict[str, Any] = {
        "armed": False,
        "session_id": None,
        "session": None,
        "cancel_sent_at": None,
        "interrupted": False,
        "forced_failure": None,
        "judged_posture": posture,
        "unverified_reported": False,
    }

    async def emit(events: List[RunEvent]) -> None:
        for event in events:
            await on_event(event)

    async def send_cancel() -> None:
        if state["cancel_sent_at"] is not None or state["session"] is None:
            return
        state["cancel_sent_at"] = asyncio.get_running_loop().time()
        with contextlib.suppress(Exception):
            await state["session"].notify("session/cancel", {"sessionId": state["session_id"]})

    async def check_interrupt() -> None:
        if state["interrupted"] or should_interrupt is None:
            return
        try:
            stop = should_interrupt()
        except Exception:  # noqa: BLE001 - a broken stop check is not a stop
            return
        if stop:
            state["interrupted"] = True
            await send_cancel()

    async def fail_turn(event: RunEvent, message: str) -> None:
        if state["forced_failure"] is None:
            state["forced_failure"] = message
            await emit(mapper.flush() + [event])
        await send_cancel()

    async def _on_armed_raw_event(
        event_type: str, data: Dict[str, Any], params: Dict[str, Any]
    ) -> None:
        """Every armed raw event passes here, to the mapper and the usage ledger."""
        if event_type == "session.error":
            # Until a real quota refusal is captured, every payload is logged whole: D8's
            # recognition is confirmed or corrected from it (`a-copilot-run-shows-its-credits`
            # task 5.2; task 8.2 asks for the first one). Scrubbed of the run's registered values
            # before the cut (F488, D6); a scrub that raised logs no payload, never the raw one,
            # and must not stop the event reaching the mapper below.
            try:
                logged = json.dumps(
                    run_secrets.scrub((env or {}).get("AW_RUN_ID"), data), default=str
                )[:2000]
            except Exception:  # noqa: BLE001 - a log line never drops the error card
                logged = "<unavailable>"
            logger.warning(
                "Copilot session.error errorType=%r errorCode=%r statusCode=%r payload=%s",
                data.get("errorType"),
                data.get("errorCode"),
                data.get("statusCode"),
                logged,
            )
        try:
            ledger.observe_event(event_type, data)
        except Exception:  # noqa: BLE001 - telemetry never fails the turn (D11)
            logger.warning("Copilot usage ledger rejected a %s event", event_type, exc_info=True)
        await emit(mapper.on_raw_event(event_type, data, params))
        if event_type == "session.mode_changed":
            new_mode = next(
                (
                    data.get(k)
                    for k in ("newModeId", "modeId", "newMode", "mode", "currentModeId")
                    if data.get(k)
                ),
                None,
            )
            if _mode_name(new_mode) == "autopilot" and state["judged_posture"] != _FULL:
                message = (
                    "Copilot switched this session into autopilot, which approves every action "
                    "on its own; AgentWeave cancelled the turn."
                )
                await fail_turn(
                    error_event(code="copilot_posture_escalated", message=message), message
                )
        elif event_type == "exit_plan_mode.requested":
            message = (
                "Copilot asked to leave plan mode, which AgentWeave cannot answer over ACP; the "
                "turn was cancelled rather than left waiting."
            )
            await fail_turn(
                diagnostic_event(
                    stream="copilot",
                    severity="warning",
                    summary=message,
                    code="copilot.plan_mode_exit_unanswerable",
                ),
                message,
            )

    async def on_notification(method: str, params: Dict[str, Any]) -> None:
        if method == RAW_EVENT_METHOD:
            event_type = params.get("type")
            if not isinstance(event_type, str):
                return
            data = params.get("data") if isinstance(params.get("data"), dict) else {}
            # Fed unarmed, from spawn on: a permission request can only follow the prompt, so
            # nothing replayed can reach a decision.
            track_call(calls, event_type, data)
            track_servers(servers, event_type, data)
            # Copilot's own report about the Hub's server is a harness report
            # (`a-run-reaches-the-hub-without-mcp` D1), armed or not: `session.mcp_servers_loaded`
            # arrives with the first model prompt. Only for a run given the server.
            if on_mcp_status is not None and mcp_command:
                for reported in hub_server_reports(event_type, data):
                    try:
                        await on_mcp_status(reported)
                    except Exception:  # noqa: BLE001 -- a record never fails the turn
                        logger.warning("recording Copilot's MCP status failed", exc_info=True)
            if not state["armed"]:
                if event_type in (
                    "session.mcp_servers_loaded",
                    "session.mcp_server_status_changed",
                ):
                    early_server_events.append((event_type, data, params))
                return
            await _on_armed_raw_event(event_type, data, params)
        elif method == "session/update":
            if not state["armed"]:
                collected = state.get("collect")
                update = params.get("update")
                if (
                    collected is not None
                    and isinstance(update, dict)
                    and update.get("sessionUpdate") == "agent_message_chunk"
                ):
                    # The `/mcp list` reply (D9): read for its own diagnostic, never mapped.
                    content = update.get("content")
                    if isinstance(content, dict) and isinstance(content.get("text"), str):
                        collected.append(content["text"])
                return  # replayed history, available commands: dropped (D7)
            update = params.get("update")
            if not isinstance(update, dict):
                return
            if update.get("sessionUpdate") == "usage_update":
                sample = usage_sample(update, model=mapper.resolved_model or model)
                if sample is not None and on_usage is not None:
                    await on_usage(sample)
            else:
                await emit(mapper.on_session_update(update))
        if state["armed"]:
            await check_interrupt()

    async def judge(params: Dict[str, Any], posture_now: str) -> Dict[str, Any]:
        return await asyncio.to_thread(
            decide_permission,
            params,
            posture=posture_now,
            workspace=workspace,
            hub_url=run_hub_url,
            calls=dict(calls),
            spec_turn=spec_turn,
            servers={k: [dict(e) for e in v] for k, v in servers.items()},
            github_mcp=github_mcp,
        )

    async def answer_permission(params: Dict[str, Any]) -> Dict[str, Any]:
        """D8 step 5: every request gets exactly one answer, whichever step decided it, and every
        answer reaches the recorders."""
        subject = permission_subject(params, calls, github_mcp=github_mcp)
        asked_operator = False
        try:
            decided = await judge(params, state["judged_posture"])
            if decided.get("hub_server_unverified") and not state["unverified_reported"]:
                state["unverified_reported"] = True
                await on_event(
                    diagnostic_event(
                        stream="copilot",
                        severity="warning",
                        summary=(
                            "Copilot's agentweave server could not be confirmed as the Hub's own "
                            f"({decided['hub_server_unverified']}); its calls are judged as any "
                            "other server's this turn."
                        ),
                        code="copilot.hub_server_unverified",
                    )
                )
            outcome = decided.get("outcome")
            if outcome == ASK_OPERATOR:
                asked_operator = True
                allowed = False
                if request_approval is not None:
                    subject["workspace_verdict"] = await asyncio.to_thread(
                        workspace_verdict,
                        params,
                        workspace,
                        hub_url=run_hub_url,
                        calls=dict(calls),
                        servers={k: [dict(e) for e in v] for k, v in servers.items()},
                        github_mcp=github_mcp,
                    )
                    allowed = bool(await request_approval(PERMISSION_METHOD, subject))
            else:
                allowed = outcome == ALLOW
            subject["reason"] = decided.get("reason")
        except Exception:  # noqa: BLE001 - a client error while deciding answers reject_once
            logger.warning("answering a Copilot permission request failed", exc_info=True)
            allowed = False
        result = permission_answer(params, allowed)
        if on_decision is not None:
            with contextlib.suppress(Exception):
                await on_decision(PERMISSION_METHOD, subject, allowed)
        # A refusal this Hub made by itself. Not one the operator made: that is recorded through
        # the permission request they answered (as Codex).
        if not allowed and not asked_operator and on_refusal is not None:
            with contextlib.suppress(Exception):
                await on_refusal(PERMISSION_METHOD, subject)
        return result

    async def on_server_request(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == PERMISSION_METHOD:
            result = await answer_permission(params)
            if state["armed"]:
                await check_interrupt()
            return result
        # `fs/*`, `terminal/*` and `elicitation/create` are not advertised (design, Non-goals).
        raise CopilotACPError(f"Method not found: {method}", code=METHOD_NOT_FOUND_CODE)

    async def deliver_accounting(outcome: TurnOutcome, session_was_new: bool) -> TurnOutcome:
        """The one `on_accounting` call of a turn that has a session (D2)."""
        if on_accounting is not None:
            try:
                await on_accounting(ledger.finish(session_was_new=session_was_new))
            except Exception:  # noqa: BLE001 - a returned outcome is never turned into a raise
                logger.warning("recording a Copilot turn's usage failed", exc_info=True)
        return outcome

    session = await ACPProcess.spawn(
        argv,
        cwd=session_cwd,
        env=env,
        on_notification=on_notification,
        on_server_request=on_server_request,
    )
    state["session"] = session
    prompt_written = False
    close_forced = False
    try:
        init = await session.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "_meta": {
                        "github.com/copilot": {"events": list(dict.fromkeys(COPILOT_RAW_EVENTS))}
                    }
                },
            },
        )
        info = init.get("agentInfo") if isinstance(init.get("agentInfo"), dict) else {}
        version = info.get("version")
        if not version_supported(version):
            shown = version if isinstance(version, str) and version else "(unknown version)"
            _record_probe(present=True, authorized=False, reason=too_old_reason(shown), cli=cli)
            raise CopilotACPError(
                f"Copilot CLI {shown} is older than the supported {COPILOT_MIN_VERSION}. Update it "
                "with `copilot update` or npm."
            )

        new_params = {"cwd": session_cwd, "mcpServers": []}
        session_response: Dict[str, Any]
        session_id: Optional[str] = None
        # `session/new` was called, the `-32002` fallback included (D2, D4).
        session_was_new = False
        if resume_session_id:
            try:
                session_response = await session.request(
                    "session/load",
                    {"sessionId": resume_session_id, **new_params},
                    timeout=SESSION_REQUEST_TIMEOUT_SECONDS,
                )
                session_id = resume_session_id
            except CopilotACPError as exc:
                if exc.code != SESSION_NOT_FOUND_CODE:
                    raise
                # A session that never received a model prompt is not persisted (VERIFIED). The
                # old id named nothing that exists, so rebinding it is the stated exception to
                # the first-writer rule (D7).
                await on_event(
                    diagnostic_event(
                        stream="copilot",
                        severity="info",
                        summary=(
                            f"Copilot had no saved session {resume_session_id}; a new one was "
                            "started."
                        ),
                        code="copilot.session_missing",
                    )
                )
                if on_session_missing is not None:
                    await on_session_missing(resume_session_id)
        if session_id is None:
            try:
                session_response = await session.request(
                    "session/new", new_params, timeout=SESSION_REQUEST_TIMEOUT_SECONDS
                )
            except CopilotACPError as exc:
                if exc.code == AUTH_REQUIRED_CODE:
                    # Written before the raise: the executor re-drains at once, and without the
                    # verdict each retry would spend a delivery attempt (D12, R3).
                    _record_probe(
                        present=True, authorized=False, reason=not_signed_in_reason(), cli=cli
                    )
                raise
            session_id = _str_or_none(session_response.get("sessionId"))
            if session_id is None:
                raise CopilotACPError("Copilot's session/new answered no sessionId.")
            session_was_new = True
        _record_probe(present=True, authorized=True, reason=None, cli=cli)
        state["session_id"] = session_id
        if on_session is not None:
            await on_session(session_id)

        options = _options_of(session_response)
        loaded_mode = _loaded_mode(session_response, options)

        # D6: select the Hub's agent file, and prove it was the Hub's by its marker.
        failure: Optional[str] = None
        try:
            selected = await session.request(
                "session/set_config_option",
                {"sessionId": session_id, "configId": "agent", "value": agent},
            )
            options = _options_of(selected) or options
            agent_option = _option(_options_of(selected), "agent")
            if agent_option is None:
                failure = "no agent option was offered"
            elif agent_option.get("currentValue") != agent:
                failure = f"Copilot selected {agent_option.get('currentValue')!r}"
            elif _selected_description(agent_option) != agent_marker(agent):
                failure = f"the selected {agent!r} is not the file AgentWeave wrote"
        except CopilotACPError as exc:
            failure = f"Copilot refused to select it: {exc}"

        use_resource_block = False
        if failure is not None:
            use_resource_block = True
            agent_option = _option(options, "agent")
            if agent_option is not None and agent_option.get("currentValue"):
                # A repository agent of the same name must not stay selected: its body, tools and
                # MCP servers would apply (review 2026-09-28, finding 6).
                kept_message = (
                    f"Copilot kept a custom agent named {agent} that AgentWeave did not write "
                    "selected; this turn was not started."
                )
                try:
                    deselected = await session.request(
                        "session/set_config_option",
                        {"sessionId": session_id, "configId": "agent", "value": ""},
                    )
                except CopilotACPError as exc:
                    raise CopilotACPError(kept_message) from exc
                options = _options_of(deselected) or options
                after = _option(_options_of(deselected), "agent")
                if after is None or after.get("currentValue") != "":
                    raise CopilotACPError(kept_message)
                failure += "; the same-named agent AgentWeave did not write was deselected"
            await on_event(
                diagnostic_event(
                    stream="copilot",
                    severity="warning",
                    summary=(
                        f"Copilot did not select the AgentWeave agent file ({failure}); this "
                        "turn's context was sent with the prompt instead."
                    ),
                    code="copilot.agent_not_selected",
                )
            )

        # `a-run-reaches-the-hub-without-mcp` D9: the run tests itself before its first prompt.
        # Copilot started the servers it was given inside `session/new`, so the announce is due
        # now. The surface is decided from this run's own answer; the access notice and the tool
        # section are rendered for it; Plan mode below follows it. A run given no server does not
        # wait (nothing could announce) and is told the call command, untested.
        surface_texts: Optional[List[str]] = None
        if render_surface is not None:
            tested: Optional[bool] = None
            quote: Optional[str] = None
            if mcp_command and await_mcp_announce is not None:
                tested = bool(await await_mcp_announce())
                if not tested and should_interrupt is not None:
                    try:
                        stop_now = bool(should_interrupt())
                    except Exception:  # noqa: BLE001
                        stop_now = False
                    if stop_now:
                        # Ended during the wait: nothing was told and nothing tested (R3).
                        return await deliver_accounting(
                            TurnOutcome(session_id=session_id, status="interrupted"),
                            session_was_new,
                        )
                if not tested:
                    quote = await _mcp_list_quote(session, session_id, state)
            told_access_path = "mcp" if tested else "shim"
            # The mapper words its own MCP failure for what the run was actually told (D9, R3).
            mapper.told_access_path = told_access_path
            surface_texts = await render_surface(told_access_path, tested, quote)

        # D8's posture step, every turn. Step 1: always set the mode, whatever the load reported.
        plan = spec_turn and SPEC_TURN_USES_PLAN_MODE and told_access_path == "mcp"
        mode_uri = PLAN_MODE if plan else AGENT_MODE
        try:
            await session.request("session/set_mode", {"sessionId": session_id, "modeId": mode_uri})
        except CopilotACPError as exc:
            if plan:
                await on_event(
                    diagnostic_event(
                        stream="copilot",
                        severity="warning",
                        summary=(
                            f"Copilot refused plan mode for this specification turn ({exc}); "
                            "its file tools are still restricted."
                        ),
                        code="copilot.plan_mode_unavailable",
                    )
                )
            elif _mode_name(loaded_mode) in ("plan", "autopilot"):
                raise CopilotACPError(
                    f"Copilot kept this session in {_mode_name(loaded_mode)} mode; AgentWeave did "
                    "not start the turn."
                ) from exc
            else:
                logger.warning("Copilot refused session/set_mode #agent: %s", exc)

        allow_all = _option(options, "allow_all")
        if posture == _FULL and not spec_turn:
            # Step 2: Full access asks Copilot for allow-all, and never grants through the Hub
            # what Copilot (or its organisation's policy) withheld.
            withheld: Optional[str] = None
            if allow_all is None:
                withheld = "no allow-all option was offered"
            elif allow_all.get("currentValue") != "on":
                try:
                    turned = await session.request(
                        "session/set_config_option",
                        {"sessionId": session_id, "configId": "allow_all", "value": "on"},
                    )
                    after = _option(_options_of(turned), "allow_all")
                    if after is None or after.get("currentValue") != "on":
                        withheld = "allow-all did not read back on"
                except CopilotACPError as exc:
                    withheld = str(exc)
            if withheld is not None:
                state["judged_posture"] = WORKSPACE_PERMISSION_MODE
                await on_event(
                    diagnostic_event(
                        stream="copilot",
                        severity="warning",
                        summary=(
                            f"Copilot did not grant Full access ({withheld}); this run is "
                            "deciding each action against its workspace instead."
                        ),
                        code="copilot.full_access_withdrawn",
                    )
                )
        elif allow_all is not None and allow_all.get("currentValue") == "on":
            # Step 3: every other posture turns a persisted allow-all off and reads it back;
            # proceeding with it on would promise a judge that is never asked.
            kept_on = (
                "Copilot kept allow-all on for this session; AgentWeave did not start the turn, "
                "because no action would have been put to it."
            )
            try:
                turned = await session.request(
                    "session/set_config_option",
                    {"sessionId": session_id, "configId": "allow_all", "value": "off"},
                )
            except CopilotACPError as exc:
                raise CopilotACPError(kept_on) from exc
            after = _option(_options_of(turned), "allow_all")
            if after is not None and after.get("currentValue") == "on":
                raise CopilotACPError(kept_on)
        if spec_turn and posture == _FULL:
            state["judged_posture"] = WORKSPACE_PERMISSION_MODE

        blocks: List[Dict[str, Any]] = []
        if use_resource_block and stable_context:
            blocks.append(
                {
                    "type": "resource",
                    "resource": {
                        "uri": f"agentweave://context/{agent}/stable",
                        "mimeType": "text/markdown",
                        "text": stable_context,
                    },
                }
            )
        # For a run that tested itself, the notice and tool section rendered for the decided
        # surface replace the pre-spawn section, which may describe the other surface (D9).
        tools_text = (
            "\n\n".join(text for text in surface_texts if text)
            if surface_texts is not None
            else tool_surface_context
        )
        blocks.append({"type": "text", "text": _context_block(per_turn_context, tools_text)})
        # Always a block of its own: a message reading `/allow-all on` is text, not a command.
        blocks.append({"type": "text", "text": prompt})

        # Armed from the moment the prompt is written (D7).
        state["armed"] = True
        for event_type, data, params in early_server_events:
            await emit(mapper.on_raw_event(event_type, data, params))
        prompt_written = True
        outcome = await _await_prompt(
            session,
            session_id,
            blocks,
            state=state,
            mapper=mapper,
            ledger=ledger,
            emit=emit,
            check_interrupt=check_interrupt,
            send_cancel=send_cancel,
            turn_timeout=turn_timeout,
        )
        return await deliver_accounting(outcome, session_was_new)
    finally:
        if prompt_written:
            close_forced = bool(state.get("close_forced"))
        await session.close(force=close_forced)


async def _await_prompt(
    session: Any,
    session_id: str,
    blocks: List[Dict[str, Any]],
    *,
    state: Dict[str, Any],
    mapper: CopilotEventMapper,
    ledger: CopilotUsageLedger,
    emit: Callable[[List[RunEvent]], Awaitable[None]],
    check_interrupt: Callable[[], Awaitable[None]],
    send_cancel: Callable[[], Awaitable[None]],
    turn_timeout: float,
) -> TurnOutcome:
    """Send the prompt and wait for its response while its notifications are delivered. Every
    failure from here on is returned, not raised (D12, R3)."""
    loop = asyncio.get_running_loop()
    prompt_task = asyncio.ensure_future(
        session.request("session/prompt", {"sessionId": session_id, "prompt": blocks}, timeout=None)
    )
    deadline = loop.time() + turn_timeout
    timed_out = False
    try:
        while True:
            done, _ = await asyncio.wait({prompt_task}, timeout=POLL_SECONDS)
            if done:
                break
            await check_interrupt()
            now = loop.time()
            cancel_sent_at = state["cancel_sent_at"]
            if cancel_sent_at is not None and now - cancel_sent_at >= CANCEL_GRACE_SECONDS:
                break
            if now >= deadline:
                timed_out = True
                await send_cancel()
                break
    finally:
        if not prompt_task.done():
            prompt_task.cancel()
            with contextlib.suppress(BaseException):
                await prompt_task

    #: The prompt result, read in one place; its `usage` goes to the ledger (D2, D3).
    prompt_result: Optional[Dict[str, Any]] = None
    failure: Optional[str] = None
    if prompt_task.cancelled():
        if timed_out:
            failure = f"Copilot did not finish the turn within {int(turn_timeout)} s"
    else:
        exc = prompt_task.exception()
        if isinstance(exc, (AppServerError, asyncio.TimeoutError, OSError)):
            failure = str(exc) or type(exc).__name__
        elif exc is not None:
            logger.warning("Copilot's prompt ended with an unexpected error", exc_info=exc)
            failure = f"{type(exc).__name__}: {exc}"
        else:
            prompt_result = prompt_task.result()
        # D8: a JSON-RPC error's structured quota fields count as a refusal; never its message.
        if isinstance(exc, CopilotACPError):
            with contextlib.suppress(Exception):
                ledger.observe_prompt_error(exc.data)
    if isinstance(prompt_result, dict):
        with contextlib.suppress(Exception):
            ledger.observe_prompt_result(prompt_result.get("usage"))

    await emit(mapper.finish())

    stop_reason = (prompt_result or {}).get("stopReason")
    # A stop sent, a timeout, or a prompt that failed after it was written: a shell may still be
    # running, so the process tree is ended forcibly (D17).
    state["close_forced"] = bool(
        state["cancel_sent_at"] is not None or failure is not None or prompt_result is None
    )
    error_kind: Optional[str] = None
    if state["forced_failure"] is not None:
        status, error = "failed", state["forced_failure"]
    elif state["interrupted"] or stop_reason == "cancelled":
        status, error = "interrupted", None
    elif failure is not None:
        status, error = "failed", failure
    elif mapper.root_error is not None:
        status, error = "failed", mapper.root_error
        error_kind = mapper.root_error_kind
    elif ledger.refused:
        # D8: a quota refusal fails the turn whatever the stop reason, so its input is requeued.
        status, error = "failed", "Copilot refused the turn: the plan's quota is spent."
    else:
        status, error = "completed", None
    return TurnOutcome(
        session_id=session_id,
        status=status,
        error=error,
        exit_code=session.returncode,
        stderr_tail=session.stderr_tail() or None,
        retryable=False if error_kind in UNRETRYABLE_ERROR_KINDS else None,
        error_kind=error_kind,
    )
