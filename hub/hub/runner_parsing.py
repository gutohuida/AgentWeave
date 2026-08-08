"""JSONL output parsing for Hub-spawned Claude Code and Codex CLI runs.

Event shapes are verified against real
`claude --output-format stream-json` / `codex exec --json` output on this machine.

Session-ID extraction is the data-driven strategy the CLI's `_extract_jsonl_session_id`
uses: for Claude, the first JSONL line carrying a top-level `session_id` field (live-
verified: every event type — `system`, `rate_limit_event`, `assistant`, `result` — carries
it); for Codex, the `thread_id` field specifically on a `thread.started` event.

Context-window limits: Claude's own `result` event reports each model's actual context
window directly (`modelUsage.<model>.contextWindow`) — live-verified against Sonnet 5
(1,000,000) and Haiku 4.5 (200,000). This is used directly instead of porting the CLI's
`CLAUDE_CONTEXT_LIMITS` substring table, which is stale (has no entry for Sonnet 5's actual
1M window and silently falls back to a wrong 200K default) — self-reported beats hardcoded,
and matches the T3-derived principle in design.md: "the meter never computes context itself
— it renders the newest event the provider emitted."

Codex has no equivalent self-report in `turn.completed`, so its context window is resolved
against `model_catalog.model_context_window` (2026-08-04-hub-model-control-and-provisioning),
which replaces the two-entry `CODEX_MODEL_CONTEXT_LIMITS` table and its `128000` default that
this module previously fell back to for every unrecognised model — the mechanism behind the
live symptom that change fixed: an agent on an uncatalogued model reporting >100% of a window
that was never actually its own. A model the catalog does not recognise now reports usage as
unknown (`status="unavailable"`, no `limit_tokens`) rather than substituting that default.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .model_catalog import model_context_window
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


@dataclass
class ParsedLine:
    events: List[RunEvent] = field(default_factory=list)
    usage: Optional[ContextUsageSample] = None
    accounting: Optional[AccountingSample] = None
    session_id: Optional[str] = None


def _token_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(value)


def _first_token(mapping: Dict[str, Any], *keys: str) -> Optional[int]:
    for key in keys:
        value = _token_int(mapping.get(key))
        if value is not None:
            return value
    return None


def _accounting_from_dimensions(
    dimensions: Dict[str, Any],
    *,
    source: str,
    model: Optional[str] = None,
    cost_usd: Any = None,
    allowance: Optional[Dict[str, Any]] = None,
    cache_is_separate_input: bool = False,
) -> Optional[AccountingSample]:
    fresh_input = _first_token(dimensions, "input_tokens", "inputTokens", "input")
    output = _first_token(dimensions, "output_tokens", "outputTokens", "output")
    cache_read = _first_token(
        dimensions,
        "cache_read_input_tokens",
        "cacheReadInputTokens",
        "cached_input_tokens",
        "cache_read_tokens",
    )
    cache_write = _first_token(
        dimensions,
        "cache_creation_input_tokens",
        "cacheCreationInputTokens",
        "cache_write_input_tokens",
        "cache_write_tokens",
    )
    reasoning = _first_token(dimensions, "reasoning_output_tokens", "reasoningTokens", "reasoning")
    reported_total = _first_token(dimensions, "total_tokens", "totalTokens", "total")
    if fresh_input is None and output is None and reported_total is None:
        if allowance is None and cost_usd is None:
            return None
        normalized_input = None
        total = None
    else:
        normalized_input = fresh_input
        if cache_is_separate_input and fresh_input is not None:
            normalized_input += (cache_read or 0) + (cache_write or 0)
        total = reported_total
        if total is None:
            total = (normalized_input or 0) + (output or 0)
    cost_micros = None
    if isinstance(cost_usd, (int, float)) and not isinstance(cost_usd, bool) and cost_usd >= 0:
        cost_micros = round(float(cost_usd) * 1_000_000)
    return AccountingSample(
        source=source,
        input_tokens=normalized_input,
        output_tokens=output,
        total_tokens=total,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        reasoning_tokens=reasoning,
        model=model,
        api_equivalent_usd_micros=cost_micros,
        allowance=allowance,
    )


def _claude_model_accounting(
    model_usage: Dict[str, Any], *, source: str, cost_usd: Any
) -> Optional[AccountingSample]:
    samples = [
        _accounting_from_dimensions(
            entry,
            source=source,
            model=model_name,
            cache_is_separate_input=True,
        )
        for model_name, entry in model_usage.items()
        if isinstance(entry, dict)
    ]
    measured = [
        sample for sample in samples if sample is not None and sample.total_tokens is not None
    ]
    if not measured:
        return _accounting_from_dimensions({}, source=source, cost_usd=cost_usd)
    best_model = max(measured, key=lambda sample: sample.total_tokens or 0).model
    cost_micros = (
        round(float(cost_usd) * 1_000_000)
        if isinstance(cost_usd, (int, float)) and not isinstance(cost_usd, bool) and cost_usd >= 0
        else None
    )
    return AccountingSample(
        source=source,
        input_tokens=sum(sample.input_tokens or 0 for sample in measured),
        output_tokens=sum(sample.output_tokens or 0 for sample in measured),
        total_tokens=sum(sample.total_tokens or 0 for sample in measured),
        cache_read_tokens=sum(sample.cache_read_tokens or 0 for sample in measured),
        cache_write_tokens=sum(sample.cache_write_tokens or 0 for sample in measured),
        reasoning_tokens=sum(sample.reasoning_tokens or 0 for sample in measured),
        model=best_model,
        api_equivalent_usd_micros=cost_micros,
    )


def _claude_tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(part for part in parts if part)
    return ""


def _claude_result_error_message(data: Dict[str, Any], subtype: str) -> str:
    result = data.get("result")
    if isinstance(result, str) and result.strip():
        return result.strip()
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        if error:
            return str(error)
    elif isinstance(error, str) and error.strip():
        return error.strip()
    errors = data.get("errors")
    if isinstance(errors, list):
        messages = [str(item).strip() for item in errors if str(item).strip()]
        if messages:
            return "; ".join(messages)
    return f"Claude run failed ({subtype or 'unknown error'})"


def _claude_usage_sample(
    usage: Dict[str, Any], *, source: str, model: Optional[str] = None
) -> Optional[ContextUsageSample]:
    """One context-window reading from a Claude `assistant` message's usage block.

    Carries the model the message names, which is what lets the recording path resolve a context
    window from the catalog. Claude reports the window only in its end-of-turn `result` message,
    so without the model this sample can never yield a percentage on its own — and waiting for
    the two to meet is exactly the collision this change removes.
    """
    input_tokens = usage.get("input_tokens")
    if input_tokens is None:
        return None
    cache_read = usage.get("cache_read_input_tokens") or 0
    cache_creation = usage.get("cache_creation_input_tokens") or 0
    context_tokens = int(input_tokens) + int(cache_read) + int(cache_creation)
    return ContextUsageSample(
        status="measured",
        source=source,
        basis="latest_request_input",
        context_tokens=context_tokens,
        model=model,
        breakdown={
            "input_tokens": int(input_tokens),
            "cache_read_tokens": int(cache_read),
            "cache_creation_tokens": int(cache_creation),
        },
    )


def parse_claude_line(line: str, *, source: str = "claude") -> ParsedLine:
    """Parse one JSONL line from `claude --output-format stream-json`."""
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except Exception:
        stripped = line.strip()
        if stripped:
            return ParsedLine(events=[text_event(stripped)])
        return ParsedLine()

    session_id = data.get("session_id") if isinstance(data.get("session_id"), str) else None
    msg_type = data.get("type", "")

    if msg_type == "assistant":
        message = data.get("message", {})
        content = message.get("content", data.get("content", []))
        events: List[RunEvent] = []
        if isinstance(content, str):
            if content.strip():
                events.append(text_event(content.strip()))
        else:
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")
                if block_type == "thinking":
                    thinking = block.get("thinking", "").strip()
                    if thinking:
                        events.append(thinking_event(thinking))
                elif block_type == "text":
                    text = block.get("text", "").strip()
                    if text:
                        events.append(text_event(text))
                elif block_type == "tool_use":
                    events.append(
                        tool_use_event(
                            tool=block.get("name", "unknown"),
                            category="tool",
                            input_data=block.get("input", {}),
                            call_id=block.get("id"),
                        )
                    )
        usage = message.get("usage") if isinstance(message, dict) else None
        reported_model = message.get("model") if isinstance(message, dict) else None
        usage_sample = (
            _claude_usage_sample(
                usage,
                source=source,
                model=reported_model if isinstance(reported_model, str) else None,
            )
            if usage
            else None
        )
        if usage_sample is not None:
            usage_sample.session_id = session_id
        return ParsedLine(events=events, usage=usage_sample, session_id=session_id)

    if msg_type == "user":
        message = data.get("message", {})
        content = message.get("content", []) if isinstance(message, dict) else []
        events = []
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_result":
                    continue
                events.append(
                    tool_result_event(
                        tool="tool",
                        output=_claude_tool_result_text(block.get("content")),
                        call_id=block.get("tool_use_id"),
                        is_error=bool(block.get("is_error")),
                    )
                )
        return ParsedLine(events=events, session_id=session_id)

    if msg_type == "result":
        subtype = data.get("subtype", "")
        usage_sample = None
        model_usage = data.get("modelUsage")
        if isinstance(model_usage, dict):
            # Self-reported context window per model — see module docstring. Pick the
            # entry with the largest contextWindow (the primary model, not a cheap
            # auxiliary one Claude Code may also report, e.g. haiku for subagent calls).
            best_model, best_entry = None, None
            for model_name, entry in model_usage.items():
                if not isinstance(entry, dict):
                    continue
                if best_entry is None or (entry.get("contextWindow") or 0) > (
                    best_entry.get("contextWindow") or 0
                ):
                    best_model, best_entry = model_name, entry
            if best_entry is not None:
                limit_tokens = best_entry.get("contextWindow")
                usage_sample = ContextUsageSample(
                    status="measured",
                    source=source,
                    basis="latest_request_input",
                    limit_tokens=int(limit_tokens) if limit_tokens else None,
                    model=best_model,
                    session_id=session_id,
                )
        accounting = None
        result_usage = data.get("usage")
        if isinstance(result_usage, dict):
            accounting = _accounting_from_dimensions(
                result_usage,
                source=source,
                model=usage_sample.model if usage_sample is not None else None,
                cost_usd=data.get("total_cost_usd"),
                cache_is_separate_input=True,
            )
        if accounting is None and isinstance(model_usage, dict):
            accounting = _claude_model_accounting(
                model_usage, source=source, cost_usd=data.get("total_cost_usd")
            )
        if data.get("is_error") is True or str(subtype).startswith("error"):
            event = error_event(
                code="claude_result_error",
                message=_claude_result_error_message(data, str(subtype)),
            )
        else:
            cost = data.get("total_cost_usd")
            summary = f"Completed (cost: ${cost:.4f})" if cost is not None else "Completed"
            event = status_event("completed", summary=summary)
        return ParsedLine(
            events=[event],
            usage=usage_sample,
            accounting=accounting,
            session_id=session_id,
        )

    if msg_type == "rate_limit_event":
        allowance = data.get("rate_limit_info") or data.get("rate_limit")
        accounting = None
        if isinstance(allowance, dict):
            accounting = AccountingSample(source=source, allowance=allowance)
        return ParsedLine(accounting=accounting, session_id=session_id)

    return ParsedLine(session_id=session_id)


def _codex_file_change_summary(changes: Any) -> str:
    if not isinstance(changes, list):
        return "file changes"
    paths = [c.get("path", "?") for c in changes if isinstance(c, dict)]
    return ", ".join(paths) if paths else "file changes"


def _codex_usage_sample(
    usage: Dict[str, Any], *, source: str, model: Optional[str]
) -> Optional[ContextUsageSample]:
    input_tokens = usage.get("input_tokens")
    if input_tokens is None:
        return None
    cached = usage.get("cached_input_tokens") or 0
    cache_write = usage.get("cache_write_input_tokens") or 0
    output_tokens = usage.get("output_tokens") or 0
    reasoning_tokens = usage.get("reasoning_output_tokens") or 0
    context_tokens = int(input_tokens) + int(output_tokens)
    breakdown = {
        "input_tokens": int(input_tokens),
        "cached_input_tokens": int(cached),
        "cache_creation_tokens": int(cache_write),
        "output_tokens": int(output_tokens),
        "reasoning_tokens": int(reasoning_tokens),
    }
    # Resolution order (design.md): provider self-report (none for Codex — see module
    # docstring) -> catalog -> unknown. A model the catalog does not declare a window for
    # reports usage as unknown rather than substituting a default that does not describe it.
    limit = model_context_window("codex", model) if model else None
    if limit is None:
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
        status="estimated",
        source=source,
        basis="cumulative_delta",
        context_tokens=context_tokens,
        limit_tokens=limit,
        model=model,
        breakdown=breakdown,
    )


def parse_codex_line(
    line: str, *, source: str = "codex", model: Optional[str] = None
) -> ParsedLine:
    """Parse one JSONL line from `codex exec --json`."""
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
    except Exception:
        stripped = line.strip()
        if stripped:
            return ParsedLine(events=[text_event(stripped)])
        return ParsedLine()

    msg_type = data.get("type", "")

    if msg_type == "thread.started":
        thread_id = data.get("thread_id")
        return ParsedLine(session_id=thread_id if isinstance(thread_id, str) else None)

    if msg_type in ("item.started", "item.completed"):
        item = data.get("item", {})
        item_type = item.get("type", "")
        call_id = item.get("id")
        is_start = msg_type == "item.started"

        if item_type == "agent_message":
            if is_start:
                return ParsedLine()
            text = item.get("text", "").strip()
            return ParsedLine(events=[text_event(text)] if text else [])

        if item_type == "reasoning":
            if is_start:
                return ParsedLine()
            text = str(item.get("text") or item.get("summary") or "").strip()
            return ParsedLine(events=[thinking_event(text)] if text else [])

        if item_type == "command_execution":
            if is_start:
                return ParsedLine(
                    events=[
                        tool_use_event(
                            tool="shell",
                            category="command",
                            input_data={"command": item.get("command", "")},
                            call_id=call_id,
                        )
                    ]
                )
            exit_code = item.get("exit_code")
            return ParsedLine(
                events=[
                    tool_result_event(
                        tool="shell",
                        output=item.get("aggregated_output", ""),
                        call_id=call_id,
                        is_error=bool(exit_code),
                    )
                ]
            )

        if item_type == "file_change":
            summary = _codex_file_change_summary(item.get("changes"))
            if is_start:
                return ParsedLine(
                    events=[
                        tool_use_event(
                            tool="apply_patch",
                            category="file_change",
                            input_data={"changes": item.get("changes", [])},
                            summary=summary,
                            call_id=call_id,
                        )
                    ]
                )
            return ParsedLine(
                events=[
                    tool_result_event(
                        tool="apply_patch",
                        output=summary,
                        summary=summary,
                        call_id=call_id,
                        is_error=item.get("status") == "failed",
                    )
                ]
            )

        if item_type == "mcp_tool_call":
            server = item.get("server", "?")
            tool_label = f"{server}.{item.get('tool', '?')}"
            if is_start:
                return ParsedLine(
                    events=[
                        tool_use_event(
                            tool=tool_label,
                            category="mcp",
                            input_data=item.get("arguments", {}),
                            call_id=call_id,
                        )
                    ]
                )
            error = item.get("error")
            if error:
                message = (
                    error.get("message", str(error)) if isinstance(error, dict) else str(error)
                )
                return ParsedLine(
                    events=[
                        tool_result_event(
                            tool=tool_label,
                            output=message,
                            summary=f"{tool_label}: {message}",
                            call_id=call_id,
                            is_error=True,
                        )
                    ]
                )
            return ParsedLine(
                events=[tool_result_event(tool=tool_label, output="completed", call_id=call_id)]
            )

        if item_type == "web_search":
            query = str(item.get("query") or item.get("text") or "")
            if is_start:
                return ParsedLine(
                    events=[
                        tool_use_event(
                            tool="web_search",
                            category="web_search",
                            input_data={"query": query},
                            call_id=call_id,
                        )
                    ]
                )
            return ParsedLine(
                events=[tool_result_event(tool="web_search", output=query, call_id=call_id)]
            )

        if item_type in ("todo_list", "plan_update"):
            if is_start:
                return ParsedLine()
            entries = item.get("items") or item.get("plan") or []
            summary = (
                "; ".join(
                    str(entry.get("text", entry)) if isinstance(entry, dict) else str(entry)
                    for entry in entries
                )
                or "plan updated"
            )
            return ParsedLine(events=[status_event("plan", summary=summary)])

        return ParsedLine()

    if msg_type == "turn.completed":
        usage = data.get("usage") or {}
        usage_sample = _codex_usage_sample(usage, source=source, model=model) if usage else None
        accounting = (
            _accounting_from_dimensions(usage, source=source, model=model)
            if isinstance(usage, dict)
            else None
        )
        return ParsedLine(usage=usage_sample, accounting=accounting)

    if msg_type == "event_msg":
        payload = data.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "token_count":
            info = payload.get("info")
            if isinstance(info, dict):
                last_usage = info.get("last_token_usage")
                if isinstance(last_usage, dict):
                    return ParsedLine(
                        accounting=_accounting_from_dimensions(
                            last_usage, source=f"{source}_token_count", model=model
                        )
                    )

    if msg_type == "turn.failed":
        error = data.get("error") or {}
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        return ParsedLine(
            events=[error_event(code="codex_turn_failed", message=message or "turn failed")]
        )

    if msg_type == "error":
        message = str(data.get("message", "unknown error"))
        return ParsedLine(events=[error_event(code="codex_error", message=message)])

    return ParsedLine()


def parse_opencode_line(
    line: str, *, source: str = "opencode", model: Optional[str] = None
) -> ParsedLine:
    """Parse accounting and context telemetry from OpenCode JSON step events.

    The Hub does not directly launch OpenCode yet; keeping normalization here makes the
    runner-neutral accounting contract available when that execution adapter lands.
    """
    try:
        data = json.loads(line)
        if not isinstance(data, dict):
            return ParsedLine()
    except Exception:
        return ParsedLine()
    if data.get("type") != "step_finish":
        return ParsedLine()
    part = data.get("part")
    if not isinstance(part, dict):
        return ParsedLine()
    tokens = part.get("tokens")
    if not isinstance(tokens, dict):
        return ParsedLine()
    accounting = _accounting_from_dimensions(
        tokens,
        source=source,
        model=model,
        cost_usd=part.get("cost"),
    )
    usage = None
    total = _first_token(tokens, "total")
    if total is not None:
        reasoning = _first_token(tokens, "reasoning") or 0
        cache = tokens.get("cache") if isinstance(tokens.get("cache"), dict) else {}
        usage = ContextUsageSample(
            status="measured",
            source=source,
            basis="provider_context",
            context_tokens=max(0, total - reasoning),
            model=model,
            breakdown={
                "input_tokens": _first_token(tokens, "input") or 0,
                "output_tokens": _first_token(tokens, "output") or 0,
                "cache_read_tokens": _first_token(cache, "read") or 0,
                "cache_creation_tokens": _first_token(cache, "write") or 0,
                "reasoning_tokens": reasoning,
            },
        )
    if accounting is not None and isinstance(tokens.get("cache"), dict):
        cache = tokens["cache"]
        accounting.cache_read_tokens = _first_token(cache, "read")
        accounting.cache_write_tokens = _first_token(cache, "write")
    return ParsedLine(usage=usage, accounting=accounting)


def read_codex_rollout_accounting(
    session_id: str, *, codex_home: Optional[Path] = None, model: Optional[str] = None
) -> Optional[AccountingSample]:
    """Read the latest request delta from a Codex session rollout.

    Codex stdout can be cumulative for resumed sessions. Its persisted token-count event
    carries `last_token_usage`, which is the exact turn boundary needed for accounting.
    """
    home = codex_home or Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    sessions_dir = home / "sessions"
    if not sessions_dir.is_dir():
        return None
    matches = sorted(
        sessions_dir.rglob(f"rollout-*-{session_id}.jsonl"),
        key=lambda path: path.stat().st_mtime,
    )
    if not matches:
        return None
    latest_usage: Optional[Dict[str, Any]] = None
    try:
        with matches[-1].open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict) or record.get("type") != "event_msg":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict) or payload.get("type") != "token_count":
                    continue
                info = payload.get("info")
                if isinstance(info, dict) and isinstance(info.get("last_token_usage"), dict):
                    latest_usage = info["last_token_usage"]
    except OSError:
        return None
    if latest_usage is None:
        return None
    return _accounting_from_dimensions(latest_usage, source="codex_token_count", model=model)
