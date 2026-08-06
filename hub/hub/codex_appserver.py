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

from typing import Any, Dict, List, Optional

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

# Server->client methods this Hub must answer. Verified against
# `codex app-server generate-json-schema` (CLI 0.146.0) and a live protocol trace.
ELICITATION_METHOD = "mcpServer/elicitation/request"
COMMAND_APPROVAL_METHOD = "item/commandExecution/requestApproval"
FILE_CHANGE_APPROVAL_METHOD = "item/fileChange/requestApproval"
PERMISSIONS_APPROVAL_METHOD = "item/permissions/requestApproval"

_SANDBOX_APPROVAL_METHODS = (COMMAND_APPROVAL_METHOD, FILE_CHANGE_APPROVAL_METHOD)

# Full-access grant used only when `yolo` is set and Codex still asks (defensive: thread/start
# should already select a policy that avoids this under yolo, but every request must still get
# an answer per implications.md §2 — "silence becomes a deadlock").
_YOLO_PERMISSIONS_GRANT: Dict[str, Any] = {
    "fileSystem": {"entries": [{"access": "write", "path": {"type": "special", "value": {"kind": "root"}}}]},
    "network": {"enabled": True},
}


def decide_approval(
    method: str,
    params: Dict[str, Any],
    *,
    yolo: bool,
    own_server_name: str,
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
        return {"decision": "accept"} if yolo else {"decision": "decline"}

    if method == PERMISSIONS_APPROVAL_METHOD:
        return {"permissions": dict(_YOLO_PERMISSIONS_GRANT)} if yolo else {"permissions": {}}

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
                is_error=bool(exit_code),
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
                is_error=item.get("status") == "failed",
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

    if item_type in ("todoList", "planUpdate"):
        if is_start:
            return []
        entries = item.get("items") or item.get("plan") or []
        summary = (
            "; ".join(
                str(entry.get("text", entry)) if isinstance(entry, dict) else str(entry)
                for entry in entries
            )
            or "plan updated"
        )
        return [status_event("plan", summary=summary)]

    return []


def map_turn_failure(params: Dict[str, Any]) -> RunEvent:
    """Map a `turn/failed` notification's error to the standard error event."""
    error = params.get("error") or {}
    message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
    return error_event(code="codex_turn_failed", message=message or "turn failed")
