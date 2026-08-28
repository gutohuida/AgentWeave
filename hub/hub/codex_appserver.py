"""Codex `app-server` JSON-RPC protocol: approval decisions and event mapping.

`codex exec` (`runner_commands._build_codex_command`, `runner_parsing.parse_codex_line`) is a
one-shot subprocess whose `--json` stdout is parsed passively. `app-server` is a persistent
JSON-RPC peer: the Hub is a *counterparty* that must answer every server-to-client request, or
the turn hangs indefinitely rather than failing (see
`openspec/changes/2026-08-06-agent-messaging-delivery/implications-codex-appserver.md` §2). This
module holds the two pieces of that contract that are pure functions and therefore need to be
exactly right and unit-tested: which answer the Hub gives to a server request
(`decide_approval`), and how a thread item maps onto the Hub's existing `RunEvent`/timeline model
(`map_item_to_events`, mirroring `runner_parsing.parse_codex_line`'s item handling but for
app-server's differently-shaped, camelCase item taxonomy).

Every shape below was measured against a live `codex app-server` (CLI 0.146.0, Windows), not
inferred from the schema alone — schema and reality disagree on response shapes for the same
concept in this protocol (see Decision 1a's follow-up verification in `design.md`): the request
method `item/commandExecution/requestApproval` accepts `{"decision": "accept"|"decline"}`
(`CommandExecutionRequestApprovalResponse`), not `{"decision": "approved"}`
(`ExecCommandApprovalResponse`) — an older/differently-versioned shape the schema also exports
under a different method name. Guessing the wrong one on a security boundary is not acceptable;
this was confirmed live: a real out-of-workspace write attempt, declined with
`{"decision": "decline"}`, produced no file, no protocol error, and a normal turn continuation.

`codex app-server` is `[experimental]`; keep exec alive until this is proven equivalent (task
2.8). Method names, `_meta` keys, and approval shapes can change without a major version.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from collections import deque
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional

from .model_catalog import FULL_ACCESS_PERMISSION_MODE, WORKSPACE_PERMISSION_MODE
from .pty_runner import resolve_executable
from .runner_commands import OPERATOR_POSTURE
from .runner_events import (
    AccountingSample,
    ContextUsageSample,
    RunEvent,
    error_event,
    status_event,
    text_event,
    thinking_event,
    tool_result_event,
    tool_use_event,
)
from .subprocess_windows import no_console_kwargs

# Transport sentinels. Both may appear in a bound Runner's `flags` list; neither is a real
# `codex` CLI argument, so the caller strips them before `flags` reaches argv.
#
# app-server is now the DEFAULT for codex, not an opt-in
# (`2026-08-06-hub-collaboration-and-conversation-fixes`). It was introduced as an opt-in, which
# meant every codex agent an operator could actually create through the Add-agent dialog — that
# path sets no flags — ran on `codex exec`. `exec` is non-interactive and has no
# `--ask-for-approval` flag at all, so approvals resolve by policy: deny everything, which kills
# every AgentWeave MCP tool call, or bypass the sandbox entirely. The Hub was configuring a tool
# surface its agents could enumerate but never invoke, which `agent-tool-surface` already forbids.
#
# APP_SERVER_OPT_IN_FLAG is retained because runners created before this change may carry it, and
# because it remains a harmless explicit way to state the default.
APP_SERVER_OPT_IN_FLAG = "--app-server"

# Selects the legacy `exec` transport. `codex app-server` is labelled [experimental] by the Codex
# CLI itself, so the escape hatch stays — but it must be asked for, since it is known to break
# collaboration.
APP_SERVER_OPT_OUT_FLAG = "--no-app-server"

# Both sentinels, for callers that need to strip them from argv.
TRANSPORT_SENTINELS = (APP_SERVER_OPT_IN_FLAG, APP_SERVER_OPT_OUT_FLAG)


def uses_app_server(runner_cli: str, flags: Optional[List[str]]) -> bool:
    """Whether a codex run with these runner flags uses the app-server transport.

    Single source of truth for the decision, so the transport actually selected and the
    collaboration-readiness reported to the operator cannot disagree.
    """
    if runner_cli != "codex":
        return False
    return APP_SERVER_OPT_OUT_FLAG not in (flags or [])


# Server->client methods this Hub must answer. Verified against
# `codex app-server generate-json-schema` (CLI 0.146.0) and a live protocol trace.
ELICITATION_METHOD = "mcpServer/elicitation/request"
COMMAND_APPROVAL_METHOD = "item/commandExecution/requestApproval"
FILE_CHANGE_APPROVAL_METHOD = "item/fileChange/requestApproval"
PERMISSIONS_APPROVAL_METHOD = "item/permissions/requestApproval"

_SANDBOX_APPROVAL_METHODS = (COMMAND_APPROVAL_METHOD, FILE_CHANGE_APPROVAL_METHOD)

# Returned by `decide_approval` when only a human can answer. Never a valid protocol reply --
# `run_turn` replaces it with a real decision before responding, and responding with this
# would be a protocol error rather than a silent mistake.
ASK_OPERATOR: Dict[str, Any] = {"decision": "__ask_operator__"}

# Shared by commandExecution's and fileChange's `status` fields (schema:
# CommandExecutionStatus / PatchApplyStatus — both "inProgress"/"completed"/"failed"/
# "declined"). A refused approval reports "declined", not "failed" — verified against the
# installed CLI's own schema (`codex app-server generate-json-schema`), not assumed.
_FAILED_ITEM_STATUSES = ("failed", "declined")

# Full-access grant, used when the run is under the "Full access" posture (or its older `yolo`
# spelling) and Codex still asks (defensive: thread/start should already select a policy that
# avoids this, but every request must still get an answer per implications.md §2 — "silence
# becomes a deadlock").
_YOLO_PERMISSIONS_GRANT: Dict[str, Any] = {
    "fileSystem": {
        "entries": [{"access": "write", "path": {"type": "special", "value": {"kind": "root"}}}]
    },
    "network": {"enabled": True},
}


def approval_subject(method: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """What a sandbox approval is asking about, in the shape the operator card renders.

    Codex's two sandbox approvals carry different evidence, and the difference is real rather
    than incidental. A command approval names the command, its cwd, and Codex's own reason. A
    file-change approval names only the root it wants granted — the individual paths are not in
    the request (verified against `codex app-server generate-json-schema`, CLI 0.146.0), so a
    workspace check on this method is necessarily coarser than Claude's per-path one.
    """
    if method == COMMAND_APPROVAL_METHOD:
        cwd = params.get("cwd")
        return {
            "command": params.get("command"),
            "cwd": cwd if isinstance(cwd, str) else (cwd or {}).get("value"),
            "reason": params.get("reason"),
        }
    return {"grantRoot": params.get("grantRoot"), "reason": params.get("reason")}


#: What a refused request is called where the operator reads it.
#:
#: The timeline renders "{agent} refused {tool_name}", so a JSON-RPC method name there reads as
#: noise in a place the operator is trying to understand why their agent stopped. These are the
#: names Claude's own refusals already use, so a refusal reads the same whichever runtime decided
#: it.
_REFUSAL_LABELS = {
    COMMAND_APPROVAL_METHOD: "Bash",
    FILE_CHANGE_APPROVAL_METHOD: "Write",
    ELICITATION_METHOD: "a prompt from one of its own tools",
}


def approval_label(method: str) -> str:
    """The refused action, named for a reader rather than for the protocol."""
    return _REFUSAL_LABELS.get(method, method)


def _within(path: Optional[str], workspace: Optional[str]) -> bool:
    """True when *path* is the workspace or beneath it, comparing resolved components.

    Absent either side is not "inside": an unknown boundary is not an open one.
    """
    if not path or not workspace:
        return False
    try:
        root = os.path.realpath(workspace)
        target = os.path.realpath(path)
        shared = os.path.commonpath([root, target])
    except (OSError, ValueError):  # unresolvable, or different drives on Windows
        return False
    return os.path.normcase(shared) == os.path.normcase(root)


def _thread_policy(*, yolo: bool, posture: Optional[str]) -> "tuple[str, str]":
    """The `sandbox` / `approvalPolicy` a thread starts under, for a given posture.

    This is what decides whether Codex asks at all. `decide_approval` only ever sees requests the
    thread policy caused: measured live, `workspace-write` + `on-request` let a codex agent create
    a file inside its worktree without raising a single approval, so an operator who selected
    "Ask me" saw nothing and the agent simply proceeded.

    "Ask me" therefore starts `read-only` + `untrusted`, the strictest pair the schema offers
    (`AskForApproval`: untrusted | on-request | never; `SandboxMode`: read-only | workspace-write |
    danger-full-access), so effectively every effectful action becomes a request the operator
    answers. The other postures keep the pairing they already had.

    The "Full access" branch below was unreachable until 2026-08-28: `_codex_posture` mapped that
    posture to `None`, so a thread reached this function indistinguishable from the default one
    and got `workspace-write`. `yolo` covered it for an agent-*default* posture only, because
    setting that reconciles the legacy flag — so the same choice behaved one way from the agent
    dialog and the opposite way from the composer. `yolo` is now the older spelling of this
    posture rather than the only one that works.
    """
    if yolo and posture is None:
        return "danger-full-access", "never"
    if posture == OPERATOR_POSTURE:
        return "read-only", "untrusted"
    if posture == FULL_ACCESS_PERMISSION_MODE:
        return "danger-full-access", "never"
    return "workspace-write", "on-request"


def decide_approval(
    method: str,
    params: Dict[str, Any],
    *,
    yolo: bool,
    own_server_name: str,
    posture: Optional[str] = None,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide the Hub's answer to one server->client request.

    Pure and total: every method maps to a decision, including ones this Hub does not
    recognise. The safe default for anything unrecognised is deny — never approve, never
    nothing (implications.md §2 and §7.2: an unanswered request hangs the turn forever, and a
    protocol addition should degrade to deny-and-continue rather than break).

    Approving a `mcpServer/elicitation/request` requires *both* conditions — tool-call kind
    and the Hub's own registered server name — never either alone (implications.md §3): a
    request naming a different MCP server than the one the Hub installed must never be
    approved just because it *looks* like a tool call.
    """
    if method == ELICITATION_METHOD:
        meta = params.get("_meta") or {}
        is_tool_call = meta.get("codex_approval_kind") == "mcp_tool_call"
        is_own_server = params.get("serverName") == own_server_name
        if is_tool_call and is_own_server:
            return {"action": "accept"}
        return {"action": "decline"}

    if method in _SANDBOX_APPROVAL_METHODS:
        # Command/file-change approvals are not tool-surface concerns (implications.md §3):
        # they follow the operator's selected sandbox, never the elicitation decision above.
        if posture == OPERATOR_POSTURE:
            # Answered outside this function — it is pure and cannot wait on a human. The caller
            # turns this into a real accept/decline and must never pass it back to Codex.
            return dict(ASK_OPERATOR)
        if posture == WORKSPACE_PERMISSION_MODE:
            subject = approval_subject(method, params)
            inside = _within(subject.get("cwd") or subject.get("grantRoot"), workspace)
            return {"decision": "accept"} if inside else {"decision": "decline"}
        # "Full access" accepts, on its own terms rather than on `yolo`'s. A thread under this
        # posture starts `danger-full-access`/`never` and should raise nothing at all, so this is
        # the defensive half of the same rule the thread policy states — and it must not be left
        # to `yolo`, which only the agent-default route sets. The ordering the operator was
        # offered has to hold: whatever "Workspace only" accepts, "Full access" accepts too.
        if posture == FULL_ACCESS_PERMISSION_MODE:
            return {"decision": "accept"}
        return {"decision": "accept"} if yolo else {"decision": "decline"}

    if method == PERMISSIONS_APPROVAL_METHOD:
        if yolo or posture == FULL_ACCESS_PERMISSION_MODE:
            return {"permissions": dict(_YOLO_PERMISSIONS_GRANT)}
        return {"permissions": {}}

    # Unrecognised server->client request: deny-and-continue rather than hang or approve
    # something this Hub has never seen the shape of.
    return {"decision": "decline"}


def _codex_usage_sample_from_token_usage(
    token_usage: Dict[str, Any], *, source: str, model: Optional[str]
) -> Optional[ContextUsageSample]:
    """Map `thread/tokenUsage/updated`'s payload to the canonical context-usage sample.

    Unlike `codex exec`, app-server self-reports `modelContextWindow` directly on this
    notification — a genuine, measured provider self-report (design's context-window
    resolution order: provider report > catalog > unknown), not a catalog lookup. `last`
    (rather than `total`) is the non-cumulative per-request delta app-server computes
    server-side, avoiding `exec`'s rollout-file cumulative-delta estimation entirely.
    """
    last = token_usage.get("last")
    if not isinstance(last, dict):
        return None
    input_tokens = last.get("inputTokens")
    if input_tokens is None:
        return None
    cached = last.get("cachedInputTokens") or 0
    cache_write = last.get("cacheWriteInputTokens") or 0
    output_tokens = last.get("outputTokens") or 0
    reasoning_tokens = last.get("reasoningOutputTokens") or 0
    context_tokens = int(input_tokens) + int(output_tokens)
    breakdown = {
        "input_tokens": int(input_tokens),
        "cached_input_tokens": int(cached),
        "cache_creation_tokens": int(cache_write),
        "output_tokens": int(output_tokens),
        "reasoning_tokens": int(reasoning_tokens),
    }
    limit = token_usage.get("modelContextWindow")
    if isinstance(limit, bool) or not isinstance(limit, (int, float)) or limit <= 0:
        return ContextUsageSample(
            status="unavailable",
            source=source,
            basis=None,
            context_tokens=context_tokens,
            limit_tokens=None,
            model=model,
            breakdown=breakdown,
        )
    return ContextUsageSample(
        status="measured",
        source=source,
        basis="provider_context",
        context_tokens=context_tokens,
        limit_tokens=int(limit),
        model=model,
        breakdown=breakdown,
    )


def _accounting_from_token_usage(
    token_usage: Dict[str, Any], *, source: str, model: Optional[str]
) -> Optional[AccountingSample]:
    last = token_usage.get("last")
    if not isinstance(last, dict):
        return None
    return AccountingSample(
        source=source,
        input_tokens=last.get("inputTokens"),
        output_tokens=last.get("outputTokens"),
        total_tokens=last.get("totalTokens"),
        cache_read_tokens=last.get("cachedInputTokens"),
        cache_write_tokens=last.get("cacheWriteInputTokens"),
        reasoning_tokens=last.get("reasoningOutputTokens"),
        model=model,
    )


def map_token_usage_notification(
    params: Dict[str, Any], *, model: Optional[str], source: str = "codex_appserver"
) -> Dict[str, Any]:
    """Map a `thread/tokenUsage/updated` notification to `(usage, accounting)`."""
    token_usage = params.get("tokenUsage") or {}
    return {
        "usage": _codex_usage_sample_from_token_usage(token_usage, source=source, model=model),
        "accounting": _accounting_from_token_usage(token_usage, source=source, model=model),
    }


def _file_change_summary(changes: Any) -> str:
    if not isinstance(changes, list):
        return "file changes"
    paths = [c.get("path", "?") for c in changes if isinstance(c, dict)]
    return ", ".join(paths) if paths else "file changes"


def map_item_to_events(item: Dict[str, Any], *, is_start: bool) -> List[RunEvent]:
    """Map one `item/started` or `item/completed` notification's `item` to `RunEvent`s.

    Mirrors `runner_parsing.parse_codex_line`'s item handling so the two transports produce
    the same timeline shape (task 2.5) — but app-server's item taxonomy is camelCase with
    different field names (`commandExecution` not `command_execution`, `aggregatedOutput` not
    `aggregated_output`, etc.), measured live rather than assumed from `exec`'s snake_case
    shapes or from the schema alone.
    """
    item_type = item.get("type", "")
    call_id = item.get("id")

    if item_type == "userMessage":
        # Already recorded as the queue entry that started this turn; not re-emitted here.
        return []

    if item_type == "agentMessage":
        if is_start:
            return []
        text = str(item.get("text") or "").strip()
        return [text_event(text)] if text else []

    if item_type == "reasoning":
        if is_start:
            return []
        summary = item.get("summary")
        content = item.get("content")
        parts = [p for p in (summary if isinstance(summary, list) else []) if isinstance(p, str)]
        parts += [p for p in (content if isinstance(content, list) else []) if isinstance(p, str)]
        text = " ".join(parts).strip()
        return [thinking_event(text)] if text else []

    if item_type == "commandExecution":
        if is_start:
            return [
                tool_use_event(
                    tool="shell",
                    category="command",
                    input_data={"command": item.get("command", "")},
                    call_id=call_id,
                )
            ]
        exit_code = item.get("exitCode")
        return [
            tool_result_event(
                tool="shell",
                output=item.get("aggregatedOutput", ""),
                call_id=call_id,
                # `status` (schema: CommandExecutionStatus — "inProgress"/"completed"/"failed"/
                # "declined") is checked alongside `exitCode` rather than instead of it: a
                # declined command never runs, so `exitCode` is null and `bool(None)` alone
                # would silently report a refused command as a successful one — the same class
                # of bug live-verified and fixed below for `fileChange` (task 2.14's breach
                # test caught it there first).
                is_error=item.get("status") in _FAILED_ITEM_STATUSES or bool(exit_code),
            )
        ]

    if item_type == "fileChange":
        summary = _file_change_summary(item.get("changes"))
        if is_start:
            return [
                tool_use_event(
                    tool="apply_patch",
                    category="file_change",
                    input_data={"changes": item.get("changes", [])},
                    summary=summary,
                    call_id=call_id,
                )
            ]
        return [
            tool_result_event(
                tool="apply_patch",
                output=summary,
                summary=summary,
                call_id=call_id,
                # `status` (schema: PatchApplyStatus) is "declined" for a refused write, not
                # "failed" — live-verified 2026-08-06 via task 2.14's breach test: a real
                # out-of-workspace `apply_patch` attempt, declined via `decide_approval`,
                # reported `is_error: false` under the original `== "failed"` check, which
                # would have shown a refused sandbox-escape attempt as a successful tool call
                # in the operator-facing timeline.
                is_error=item.get("status") in _FAILED_ITEM_STATUSES,
            )
        ]

    if item_type == "mcpToolCall":
        server = item.get("server", "?")
        tool_label = f"{server}.{item.get('tool', '?')}"
        if is_start:
            return [
                tool_use_event(
                    tool=tool_label,
                    category="mcp",
                    input_data=item.get("arguments", {}),
                    call_id=call_id,
                )
            ]
        error = item.get("error")
        if error:
            message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            return [
                tool_result_event(
                    tool=tool_label,
                    output=message,
                    summary=f"{tool_label}: {message}",
                    call_id=call_id,
                    is_error=True,
                )
            ]
        result = item.get("result")
        is_failed = item.get("status") == "failed"
        output = result if result is not None else ("failed" if is_failed else "completed")
        return [
            tool_result_event(tool=tool_label, output=output, call_id=call_id, is_error=is_failed)
        ]

    if item_type == "webSearch":
        query = str(item.get("query") or "")
        if is_start:
            return [
                tool_use_event(
                    tool="web_search",
                    category="web_search",
                    input_data={"query": query},
                    call_id=call_id,
                )
            ]
        return [tool_result_event(tool="web_search", output=query, call_id=call_id)]

    # There is no plan *item* branch here on purpose. This function used to carry one for
    # `("todoList", "planUpdate")`, which `ThreadItem` has never had: under app-server the plan
    # arrives as its own `turn/plan/updated` notification, handled in `run_turn`'s loop via
    # `map_plan_update` (F102). `exec`'s item-shaped plan stays in `runner_parsing`, where it
    # belongs.
    return []


def map_plan_update(params: Dict[str, Any]) -> RunEvent:
    """Map a `turn/plan/updated` notification to the same plan status event `exec` produces.

    The two transports are meant to produce one timeline shape (task 2.5), and `exec`'s
    `todo_list`/`plan_update` items render as `status_event("plan", summary="step; step")`.
    Step statuses (`pending | inProgress | completed`) are deliberately not rendered here, for
    that parity — which also means two updates that differ only by a status produce an identical
    summary, and `run_turn` emits the second one not at all.
    """
    steps = params.get("plan") or []
    summary = (
        "; ".join(
            str(step.get("step", step)) if isinstance(step, dict) else str(step) for step in steps
        )
        or "plan updated"
    )
    return status_event("plan", summary=summary)


def map_mcp_server_failure(params: Dict[str, Any], *, own_server_name: str) -> RunEvent:
    """Map a failed `mcpServer/startupStatus/updated` to the standard error event.

    Names which server it was, because the consequence differs entirely: the Hub's own server
    failing means this turn has no collaboration surface, while another one failing is the
    operator's own Codex configuration and costs this Hub nothing.
    """
    name = params.get("name") or "unknown"
    detail = params.get("error") or "no reason given"
    reason = params.get("failureReason")
    if reason:
        detail = f"{detail} ({reason})"
    if name == own_server_name:
        message = (
            f"The AgentWeave MCP server ({name}) failed to start, so this turn had no "
            f"AgentWeave tools -- no messages, evidence, task updates or questions: {detail}"
        )
    else:
        message = f"MCP server {name!r} failed to start: {detail}"
    return error_event(code="codex_mcp_server_failed", message=message)


def _turn_error_message(carrier: Dict[str, Any]) -> str:
    """The human-readable message out of anything carrying a `TurnError` under `error`.

    Two shapes carry one: the `Turn` inside a `turn/completed` whose status is `failed`, and a
    `turn/failed` notification's own params. Both are read here so a failure reported either way
    reaches `TurnOutcome.error` identically.
    """
    error = carrier.get("error") or {}
    message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
    return message or "turn failed"


def map_turn_failure(carrier: Dict[str, Any]) -> RunEvent:
    """Map a failed turn's error to the standard error event. See `_turn_error_message`."""
    return error_event(code="codex_turn_failed", message=_turn_error_message(carrier))


logger = logging.getLogger(__name__)

# No protocol-level turn timeout exists (implications.md §2) — the Hub enforces its own so a
# stuck app-server cannot wedge an agent forever (task 2.7).
DEFAULT_TURN_TIMEOUT_SECONDS = 600.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0


#: How much of the child's error stream is kept for a failure report. Bounded twice — by lines,
#: so a crash loop cannot grow the buffer without limit, and by characters when rendered, so one
#: enormous line cannot fill an event payload.
STDERR_TAIL_LINES = 200
STDERR_TAIL_CHARS = 2000


def readable_exit_code(exit_code: Optional[int]) -> Optional[int]:
    """The exit status as a person would act on it.

    Windows reports a forced termination as `0xFFFFFFFF`, which arrives here unsigned:
    `4294967295`. That reads as corruption, and an operator seeing it has no reason to connect it
    to the process they just killed — measured on 2026-08-14, where a run's error said
    `exit 4294967295` and nobody could tell what had happened. `-1` says "something killed this".

    Only what is *displayed* changes. `AppServerError.exit_code` and `TurnOutcome.exit_code` keep
    the platform's own value: a diagnostic that quietly rewrites its input is a worse diagnostic,
    and the raw number is what a bug report should carry.
    """
    if exit_code is None or exit_code < 2**31:
        return exit_code
    return exit_code - 2**32


class AppServerError(RuntimeError):
    """Transport-level app-server failure: spawn, protocol violation, or timeout.

    Carries the exit status, the request in flight, and what the child last complained about.
    "The process ended" is true of every one of these failures and distinguishes none of them: a
    crash, a missing binary, a rejected credential and an unresumable thread all read identically,
    so diagnosing one meant inferring the cause from which other agents still worked.

    The facts are composed into the message rather than only attached, so that every existing
    reader of `str(exc)` — `Run.error`, the `run_failed` payload, an abandoned queue entry's
    reason — reports them without being changed.
    """

    def __init__(
        self,
        message: str,
        *,
        exit_code: Optional[int] = None,
        method: Optional[str] = None,
        stderr_tail: str = "",
    ) -> None:
        self.exit_code = exit_code
        self.method = method
        self.stderr_tail = stderr_tail
        detail = message
        if exit_code is not None:
            detail += f" (exit {readable_exit_code(exit_code)})"
        if method:
            detail += f" during {method}"
        if stderr_tail:
            detail += f": {stderr_tail}"
        super().__init__(detail)


def mcp_server_config(mcp_command: List[str], *, env_vars: List[str]) -> Dict[str, Any]:
    """Build the `config.mcp_servers.<name>` entry `thread/start`/`thread/resume` accept.

    Verified live: `thread/start`'s `config` param (schema: passthrough object,
    `additionalProperties: true`) registers a per-turn MCP server exactly like `codex exec`'s
    `-c mcp_servers.<name>.*` does — a throwaway one-tool server registered this way reached
    `mcpServer/startupStatus/updated` status `"ready"`. `env_vars` lists names only, mirroring
    `_build_codex_command`: Codex resolves values from its own environment, so secrets are
    never embedded in this config object.
    """
    return {"command": mcp_command[0], "args": mcp_command[1:], "env_vars": env_vars}


@dataclass
class _Pending:
    """One in-flight client->server request: what was asked, and where the answer goes."""

    method: str
    future: "asyncio.Future[Dict[str, Any]]"


class AppServerProcess:
    """A bidirectional JSON-RPC session over one `codex app-server` subprocess's stdio.

    One process per turn (implications-codex-appserver.md §1's "per-turn process"
    recommendation, task 2.1) — spawned, driven through `initialize` and one turn, then
    closed. Not reused across turns or shared between agents; a long-lived per-agent process
    is an explicit follow-on with its own evidence, not attempted here.

    Framing is newline-delimited JSON, decoded as UTF-8 explicitly — `subprocess`/`asyncio`
    default to the platform locale encoding when not told otherwise, which is CP-1252 on
    Windows and silently mangles the smart quotes and em dashes Codex's own text routinely
    contains. `pty_runner.PipeSession` already guards against exactly this; this class does
    the same rather than repeating the mistake made (and caught) while probing this protocol
    live — see `testbed/scratch/probe_appserver_mcp_config.py`'s `UnicodeDecodeError`.
    """

    def __init__(self, proc: "asyncio.subprocess.Process") -> None:
        self._proc = proc
        self._next_id = 0
        # Method and future together, so the request in flight when the process dies is still
        # knowable. Holding only the future discarded the one fact that distinguishes an
        # unresumable thread from a failed spawn.
        self._pending: Dict[int, _Pending] = {}
        self._notifications: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._stderr: Deque[str] = deque(maxlen=STDERR_TAIL_LINES)
        self._closed = False

    @classmethod
    async def spawn(
        cls,
        cmd: List[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> "AppServerProcess":
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **no_console_kwargs(),
        )
        session = cls(proc)
        loop = asyncio.get_running_loop()
        session._reader_task = loop.create_task(session._read_loop())
        # `stderr` has been piped since this class was written and read by nothing. That is not
        # merely a lost diagnostic: an undrained pipe fills, and the child then blocks writing to
        # it — so the process being diagnosed can be hung by the diagnosis going uncollected.
        session._stderr_task = loop.create_task(session._drain_stderr())
        return session

    async def _drain_stderr(self) -> None:
        """Keep the child's error stream moving, retaining a bounded tail of it."""
        stream = self._proc.stderr
        if stream is None:
            return
        try:
            while True:
                try:
                    raw = await stream.readline()
                except (ValueError, asyncio.LimitOverrunError):
                    # One pathological line longer than the stream limit. Take what is there and
                    # keep draining rather than abandoning the pipe and re-creating the block.
                    raw = await stream.read(65536)
                if not raw:
                    break
                self._stderr.append(raw.decode("utf-8", errors="replace").rstrip())
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001 - draining diagnostics must never raise into a turn
            logger.debug("codex app-server stderr drain ended early", exc_info=True)

    def stderr_tail(self, *, limit: int = STDERR_TAIL_CHARS) -> str:
        """The end of what the child wrote to its error stream, bounded for an event payload."""
        joined = " | ".join(line for line in self._stderr if line)
        if len(joined) <= limit:
            return joined
        return "…" + joined[-limit:]

    @property
    def returncode(self) -> Optional[int]:
        return self._proc.returncode

    def process_ended_error(self, message: str, method: Optional[str] = None) -> AppServerError:
        return AppServerError(
            message,
            exit_code=self._proc.returncode,
            method=method,
            stderr_tail=self.stderr_tail(),
        )

    async def _read_loop(self) -> None:
        assert self._proc.stdout is not None
        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning(
                        "codex app-server emitted a non-JSON stdout line: %r", line[:200]
                    )
                    continue
                msg_id = msg.get("id")
                if msg_id is not None and ("result" in msg or "error" in msg):
                    pending = self._pending.pop(msg_id, None)
                    if pending is not None and not pending.future.done():
                        pending.future.set_result(msg)
                else:
                    await self._notifications.put(msg)
        except asyncio.CancelledError:
            pass
        finally:
            # Reap before reporting. Losing stdout means the process is going, but `returncode` is
            # only populated once it has been waited on — so without this the exit status is
            # racily `None` exactly when it is most wanted. Bounded, and suppressed wholesale
            # because this runs on the cancellation path too, where awaiting re-raises.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(asyncio.shield(self._proc.wait()), timeout=1)
            # Unblock any still-pending request rather than hanging it forever — the process
            # is gone, so no response is ever coming (task 2.7: process death mid-turn).
            for pending in self._pending.values():
                if not pending.future.done():
                    pending.future.set_exception(
                        self.process_ended_error("app-server process ended", pending.method)
                    )
            self._pending.clear()

    async def _write(self, message: Dict[str, Any]) -> None:
        if self._proc.stdin is None:
            raise AppServerError("app-server stdin is not available")
        data = (json.dumps(message) + "\n").encode("utf-8")
        self._proc.stdin.write(data)
        await self._proc.stdin.drain()

    async def request(
        self,
        method: str,
        params: Dict[str, Any],
        *,
        timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> Dict[str, Any]:
        """Send a client->server request and await its response."""
        self._next_id += 1
        msg_id = self._next_id
        future: "asyncio.Future[Dict[str, Any]]" = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = _Pending(method=method, future=future)
        try:
            await self._write({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(msg_id, None)

    async def notify(self, method: str, params: Dict[str, Any]) -> None:
        """Send a client->server notification (no response expected)."""
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def respond(self, request_id: Any, result: Dict[str, Any]) -> None:
        """Answer one server->client request (an approval/elicitation decision)."""
        await self._write({"jsonrpc": "2.0", "id": request_id, "result": result})

    async def next_notification(self, *, timeout: Optional[float] = None) -> Dict[str, Any]:
        """Return the next server->client notification or unsolicited request.

        A message with both ``id`` and ``method`` and no ``result``/``error`` is a
        server->client *request* (an approval/elicitation) — the caller distinguishes it from
        a plain notification by checking for ``"id"`` in the returned dict, and must answer it
        via :meth:`respond` (see implications.md §2: every request must be answered).
        """
        if timeout is None:
            return await self._notifications.get()
        return await asyncio.wait_for(self._notifications.get(), timeout=timeout)

    @property
    def pid(self) -> Optional[int]:
        return self._proc.pid

    def is_running(self) -> bool:
        return self._proc.returncode is None

    async def close(self, *, force: bool = False) -> None:
        """Terminate the process and stop the reader task. Idempotent."""
        if self._closed:
            return
        self._closed = True
        if self._reader_task is not None:
            self._reader_task.cancel()
        if self._stderr_task is not None:
            self._stderr_task.cancel()
        if self._proc.stdin is not None:
            with contextlib.suppress(Exception):
                self._proc.stdin.close()
        if self.is_running():
            if force:
                self._proc.kill()
            else:
                self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()


@dataclass
class TurnOutcome:
    """Result of one `run_turn` call — the app-server equivalent of `PipeSession`'s
    (exit_code, session_id) pair that `_execute_run` reads after its read loop ends."""

    thread_id: Optional[str]
    status: str  # "completed" | "failed" | "interrupted"
    error: Optional[str] = None
    #: The app-server's own exit status where it ended. Reported alongside the failure rather than
    #: written to `Run.exit_code`, whose synthetic 0/1 the output panel reads to detect a handoff.
    exit_code: Optional[int] = None
    #: What the app-server last wrote to its error stream. A turn that fails without raising —
    #: `turn/failed`, or a process that died and was noticed by the read loop — carries no
    #: `AppServerError`, so this is the only route by which the child's own complaint reaches the
    #: operator. It was empty on all four real failures of 2026-08-14 for exactly that reason.
    stderr_tail: Optional[str] = None


async def run_turn(
    *,
    cli: str,
    cwd: Optional[str],
    env: Optional[Dict[str, str]],
    prompt: str,
    model: Optional[str],
    resume_thread_id: Optional[str],
    yolo: bool,
    mcp_command: Optional[List[str]],
    config_overrides: Optional[Dict[str, Any]] = None,
    own_server_name: str = "agentweave",
    on_event: "Callable[[RunEvent], Awaitable[None]]",
    on_usage: "Optional[Callable[[ContextUsageSample], Awaitable[None]]]" = None,
    on_accounting: "Optional[Callable[[AccountingSample], Awaitable[None]]]" = None,
    on_thread_started: "Optional[Callable[[str], Awaitable[None]]]" = None,
    should_interrupt: "Optional[Callable[[], bool]]" = None,
    turn_timeout: float = DEFAULT_TURN_TIMEOUT_SECONDS,
    posture: Optional[str] = None,
    workspace: Optional[str] = None,
    request_approval: "Optional[Callable[[str, Dict[str, Any]], Awaitable[bool]]]" = None,
    on_refusal: "Optional[Callable[[str, Dict[str, Any]], Awaitable[None]]]" = None,
) -> TurnOutcome:
    """Drive one Codex turn over `app-server`: spawn, initialize, start-or-resume a thread,
    start a turn, answer every server request, map every item/usage notification to the
    Hub's existing model via the callbacks, and return when the turn ends.

    Per-turn process (task 2.1's recommendation): this spawns fresh and closes at the end,
    never reused across turns. `resume_thread_id`, when given, is a `Run.session_id` recorded
    by either transport — `codex exec`'s session ID and `app-server`'s `threadId` are the same
    identifier space (design.md Decision 1a, verified 2026-08-06), so no translation is needed.

    `on_thread_started`, when given, fires once with the thread's id right after
    `thread/start`/`thread/resume` responds and strictly before `turn/start` — so a caller
    that binds session identity to durable state (e.g. `Conversation.provider_session_id`)
    can do so before any `on_event` call for this turn, never after.

    The protocol supplies no turn-level timeout (implications.md §2) — `turn_timeout` is the
    Hub's own, and a process that dies mid-turn (crash, `close()` from a stop request) fails
    the turn immediately rather than waiting out the full budget (task 2.7).
    """
    resolved = resolve_executable([cli, "app-server"])
    session = await AppServerProcess.spawn(resolved, cwd=cwd, env=env)
    interrupted = False
    try:
        await session.request(
            "initialize",
            {"clientInfo": {"name": "agentweave-hub", "title": "AgentWeave Hub", "version": "0"}},
        )
        await session.notify("initialized", {})

        sandbox_mode, approval_policy = _thread_policy(yolo=yolo, posture=posture)
        thread_params: Dict[str, Any] = {
            "cwd": cwd,
            "sandbox": sandbox_mode,
            "approvalPolicy": approval_policy,
        }
        if model:
            thread_params["model"] = model
        # `config` is the app-server's `config.toml`-override map, and it carries two unrelated
        # things: the MCP server this Hub injects, and whatever `-c KEY=VALUE` pairs the run's
        # controls render (`model_reasoning_effort` today). It used to exist only when there was
        # an MCP command, which is why every config-style control silently vanished on this
        # transport -- argv is unused here, so `-c` never reached the provider at all.
        config: Dict[str, Any] = dict(config_overrides or {})
        if mcp_command:
            config["mcp_servers"] = {
                own_server_name: mcp_server_config(
                    mcp_command,
                    env_vars=[
                        "AW_RUN_TOKEN",
                        "AW_AGENT_IDENTITY",
                        "AW_RUN_ID",
                        "AW_TURN_DEPTH",
                        "HUB_URL",
                    ],
                )
            }
        if config:
            thread_params["config"] = config

        if resume_thread_id:
            start_response = await session.request(
                "thread/resume", {**thread_params, "threadId": resume_thread_id}
            )
        else:
            start_response = await session.request("thread/start", thread_params)
        thread_id = start_response["result"]["thread"]["id"]
        if on_thread_started is not None:
            # Fires before `turn/start` — every subsequent `on_event` call in the loop
            # below can rely on the caller already knowing this turn's session identity,
            # matching the `exec` path's guarantee that session_id is resolved before that
            # line's own events are recorded.
            await on_thread_started(thread_id)

        turn_response = await session.request(
            "turn/start",
            {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]},
        )
        turn_id = turn_response["result"]["turn"]["id"]

        deadline = asyncio.get_running_loop().time() + turn_timeout
        status = "failed"
        error: Optional[str] = None
        # The app-server repeats each startup-status transition -- measured live, every
        # `starting`, `ready` and `failed` arrived twice -- so one failing server would
        # otherwise tell the operator the same thing twice. Reported once per server per turn.
        reported_mcp_failures: set = set()
        #: The last plan rendered this turn. A plan is re-sent whenever any step's status moves,
        #: and statuses are not part of the rendered summary (see `map_plan_update`), so an
        #: unchanged summary carries nothing new and is not repeated at the operator.
        last_plan_summary: Optional[str] = None

        while True:
            if should_interrupt is not None and should_interrupt() and not interrupted:
                interrupted = True
                # Best-effort: if interrupt itself can't be delivered, the deadline/process-
                # death checks below still guarantee this loop ends.
                with contextlib.suppress(AppServerError, asyncio.TimeoutError):
                    await session.request(
                        "turn/interrupt", {"threadId": thread_id, "turnId": turn_id}, timeout=10
                    )

            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                status, error = "failed", "turn timed out with no turn/completed notification"
                break
            if not session.is_running():
                # The common path, and the one whose bare string used to reach `Run.error` and the
                # operator's timeline. Composed through the same error so it names the exit status
                # and what the child complained about on its way out.
                status, error = "failed", str(
                    session.process_ended_error(
                        "app-server process ended before the turn completed"
                    )
                )
                break

            try:
                msg = await session.next_notification(timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                continue

            msg_id = msg.get("id")
            method = msg.get("method")
            if (
                msg_id is not None
                and method is not None
                and "result" not in msg
                and "error" not in msg
            ):
                # A server->client request (approval/elicitation) — must always be answered
                # (implications.md §2: an unanswered request hangs the turn indefinitely).
                decision = decide_approval(
                    method,
                    msg.get("params") or {},
                    yolo=yolo,
                    own_server_name=own_server_name,
                    posture=posture,
                    workspace=workspace,
                )
                asked_operator = decision == ASK_OPERATOR
                if asked_operator:
                    # The sentinel is not a protocol reply; it must be resolved into a real one
                    # before it can be sent. With no answerer wired, decline -- every request
                    # still gets an answer (implications.md 2: silence is a deadlock).
                    allowed = False
                    if request_approval is not None:
                        subject = approval_subject(method, msg.get("params") or {})
                        allowed = await request_approval(method, subject)
                    decision = {"decision": "accept" if allowed else "decline"}
                # Report a refusal this runtime decided by itself. `decide_approval` stays pure --
                # its purity is what makes it testable as a table -- so the reporting lives here,
                # where the decision is final.
                #
                # Not when the operator was asked: that path already records the refusal through
                # the permission request they answered, and telling them twice that one action was
                # refused is worse than the silence this fixes. Refusals only, for the reason
                # `record_permission_decision` gives -- an event per allowed action buries them.
                if (
                    on_refusal is not None
                    and not asked_operator
                    and isinstance(decision, dict)
                    and decision.get("decision") == "decline"
                ):
                    await on_refusal(method, approval_subject(method, msg.get("params") or {}))
                await session.respond(msg_id, decision)
                continue

            params = msg.get("params") or {}
            if method in ("item/started", "item/completed"):
                item = params.get("item") or {}
                for event in map_item_to_events(item, is_start=(method == "item/started")):
                    await on_event(event)
            elif method == "thread/tokenUsage/updated":
                mapped = map_token_usage_notification(params, model=model)
                if on_usage is not None and mapped["usage"] is not None:
                    await on_usage(mapped["usage"])
                if on_accounting is not None and mapped["accounting"] is not None:
                    await on_accounting(mapped["accounting"])
            elif method == "turn/completed":
                # `turn/completed` is not "the turn succeeded" — it is "the turn ended", and the
                # `Turn` it carries says how (`TurnStatus`: completed | interrupted | failed |
                # inProgress, with `error` "only populated when the Turn's status is failed").
                # Reading the method name alone reported every provider-side failure — a 400, a
                # rate limit, an expired credential — as a completed run with no output and no
                # error at all. Measured live 2026-08-28 against CLI 0.146.0 (F100).
                turn = params.get("turn") or {}
                turn_status = turn.get("status")
                if turn_status == "failed":
                    await on_event(map_turn_failure(turn))
                    error = _turn_error_message(turn)
                    status = "failed"
                elif interrupted or turn_status == "interrupted":
                    # Either this Hub asked for the interrupt, or the turn was stopped by
                    # something else entirely — both are interruptions, not completions.
                    status = "interrupted"
                else:
                    status = "completed"
                break
            elif method == "turn/failed":
                # Kept for version drift only: `turn/failed` is absent from the
                # `ServerNotification` schema of CLI 0.146.0, which has exactly `turn/started`,
                # `turn/completed` and `turn/moderationMetadata`. The branch above is the live
                # failure path; this one must never be mistaken for it again.
                await on_event(map_turn_failure(params))
                error = _turn_error_message(params)
                status = "failed"
                break
            elif method == "turn/plan/updated":
                # The agent's plan. It reaches the timeline on `exec` as a `todo_list`/
                # `plan_update` *item*; under app-server it is a notification of its own, and
                # `map_item_to_events` still carried a branch for `("todoList", "planUpdate")`
                # item types no CLI sends -- so the plan was invisible on the default transport
                # while the code that was supposed to show it looked present (F102). Same dead
                # -branch shape as F100's `turn/failed`.
                plan_event = map_plan_update(params)
                if plan_event.content != last_plan_summary:
                    last_plan_summary = plan_event.content
                    await on_event(plan_event)
            elif (
                method == "mcpServer/startupStatus/updated"
                and params.get("status") == "failed"
                and params.get("name") not in reported_mcp_failures
            ):
                # `McpServerStartupState` is starting | ready | failed | cancelled, and this
                # notification used to be dropped wholesale as carrying "no timeline-relevant
                # content". For the Hub's own server that is exactly backwards: if `agentweave`
                # fails to start, the agent holds no collaboration tools at all -- it cannot send
                # a message, record evidence, complete a task or ask a question -- and the turn
                # otherwise runs, completes, and reports nothing wrong (F101, measured live
                # 2026-08-28: the agent answered "Unavailable" and the run finalised `completed`
                # with `Run.error` NULL).
                #
                # The turn is not failed over it. A model with no tools can still be useful, and
                # the operator is the one to decide -- but they can only decide if they are told,
                # so this reaches the timeline as an error rather than being inferred later from
                # a turn that mysteriously recorded nothing. `cancelled` is deliberately not
                # reported: a failing server passes through it on its way to `failed`, so it
                # would only report the same failure twice.
                reported_mcp_failures.add(params.get("name"))
                await on_event(map_mcp_server_failure(params, own_server_name=own_server_name))
            # Anything else carries no timeline-relevant content for this pass. The list is
            # MEASURED, not remembered (2026-08-28, CLI 0.146.0, one turn that planned, wrote a
            # file and ran a command): thread/started, thread/status/changed,
            # thread/tokenUsage/updated, turn/started, turn/diff/updated,
            # item/agentMessage/delta, item/commandExecution/outputDelta,
            # account/rateLimits/updated, remoteControl/status/changed, and a non-failed
            # mcpServer/startupStatus/updated. `turn/diff/updated` was absent from the version of
            # this list written from memory, and neither delta notification is a parity gap --
            # `exec` does not stream partial text either, so both transports show a message when
            # it completes.

        return TurnOutcome(
            thread_id=thread_id,
            status=status,
            error=error,
            exit_code=session.returncode,
            # Empty where the child said nothing, which is the ordinary case; `None` rather than
            # `""` so an absent fact reads as absent in the payload.
            stderr_tail=session.stderr_tail() or None,
        )
    finally:
        await session.close(force=interrupted)
