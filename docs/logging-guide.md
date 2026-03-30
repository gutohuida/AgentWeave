# AgentWeave Logging Guide

A complete specification for adding structured logging and developer tracing to every module
in the CLI package (`src/agentweave/`) and the Hub server (`hub/hub/`).

---

## 1. Two-Channel Architecture

AgentWeave uses **two separate logging channels** that serve different purposes:

| Channel | API | Destination (offline) | Destination (Hub connected) | Who reads it |
|---------|-----|-----------------------|-----------------------------|--------------|
| **Structured events** | `log_event()` from `eventlog.py` | `.agentweave/logs/events.jsonl` | Local file **+** Hub `/api/v1/logs` | `agentweave log`, Hub UI, human operators |
| **Developer tracing** | Python `logging` module | stderr or `AW_LOG_FILE` | stderr or `AW_LOG_FILE` only — **never Hub** | Developers debugging a running process |

These are not interchangeable. Use each channel for its intended purpose:

- **`log_event()`** — every observable business event: message sent, task created, lock
  timeout, transport error, watchdog spawn, agent exit. These events are the audit trail.
  They are always written locally and forwarded to the Hub when the HTTP transport is active.

- **`logger.*`** — fine-grained developer tracing: every function entry, every file read,
  every poll iteration. These never leave the local process. They are off by default
  (`AW_LOG_LEVEL=WARNING`) and surfaced only when a developer is investigating a problem.

### How dual-destination works

`log_event()` in `src/agentweave/eventlog.py`:

1. Always appends a JSON line to `.agentweave/logs/events.jsonl` (swallows exceptions — never
   crashes the caller).
2. If `severity` ∈ `{INFO, WARN, ERROR}` and `get_transport()` returns an HTTP transport,
   also calls `transport.push_log(event, agent, data, severity)` to POST to Hub `/api/v1/logs`.
3. `DEBUG` events are **local-only** — they are never pushed to the Hub (too noisy).

```
                        ┌─────────────────────────────────┐
log_event("x", WARN)    │  .agentweave/logs/events.jsonl  │  ← always (offline + online)
        │               └─────────────────────────────────┘
        │
        └── severity ≥ INFO and transport == http
                        ┌─────────────────────────────────┐
                        │  Hub  POST /api/v1/logs         │  ← only when HTTP transport
                        └─────────────────────────────────┘
```

---

## 2. Is `eventlog.py` the Right Foundation?

Before adding ~90 new `log_event()` calls across the codebase, it is worth asking whether
`eventlog.py` is a solid base to build on — or whether Python's standard `logging` library
would serve better.

### What `eventlog.py` does well

- **Zero configuration** — works before `basicConfig()` has been called; safe to call at
  module import time.
- **Dual-destination built-in** — writes locally and pushes to Hub transparently.
- **JSONL format** — `agentweave log` and `get_events()` depend on this file; the format
  is intentional and used by humans and machines alike.
- **Never crashes callers** — all exceptions are swallowed, which is correct for a logging
  side-channel.

### Where it falls short

| Problem | Impact |
|---------|--------|
| **No log rotation** | `events.jsonl` grows forever with no size limit |
| **No logger hierarchy** | Cannot silence a specific noisy subsystem (e.g. `transport.git`) without touching code |
| **`get_transport()` called on every WARN/ERROR** | Creates a new transport instance per event — expensive for `GitTransport` |
| **No `exc_info` capture** | Exceptions are stored as `str(e)` — stack traces are lost |
| **Severity mismatch** | Uses `"warn"` instead of `"warning"` — out of step with every Python tool and log aggregator |
| **`format_event()` does not scale** | Every new event name needs a new `if ev == "..."` branch to render in `agentweave log` |
| **Two parallel systems** | Adding `logger.debug()` everywhere (which this guide requires for tracing) means two separate logging systems running side by side — confusing to maintain |
| **Reinvented wheel** | Handler/filter/formatter/rotation infrastructure that Python provides for free has to be rebuilt manually |

### Recommendation: migrate to Python's `logging` + two custom handlers

Replace `log_event()` with Python's standard `logging` module and two lightweight custom
handlers that replicate `eventlog.py`'s behaviour while adding everything it lacks:

**Handler 1 — `JSONRotatingFileHandler`** (replaces the file-write block in `log_event()`):

```python
# src/agentweave/logging_handlers.py
import json
import logging
import logging.handlers
from datetime import datetime


class JSONRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Writes one JSON object per line to a rotating log file."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                "event": getattr(record, "event", record.getMessage()),
                "severity": record.levelname.lower().replace("warning", "warn"),
                **getattr(record, "data", {}),
            }
            # RotatingFileHandler manages the file and rotation
            self.stream.write(json.dumps(entry) + "\n")
            self.flush()
            self.doRollover() if self.shouldRollover(record) else None
        except Exception:
            self.handleError(record)
```

**Handler 2 — `HubHandler`** (replaces the `push_log()` side-effect in `log_event()`):

```python
class HubHandler(logging.Handler):
    """Forwards INFO/WARN/ERROR records to the Hub when HTTP transport is active.

    Never raises — logging failures must never crash the caller.
    push_log() itself must not log; see §4 recursion guard.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.INFO:
            return  # DEBUG stays local
        try:
            from .transport import get_transport
            t = get_transport()
            if t.get_transport_type() == "http":
                agent = getattr(record, "data", {}).get("agent", "system")
                severity = record.levelname.lower().replace("warning", "warn")
                t.push_log(
                    getattr(record, "event", record.getMessage()),
                    str(agent),
                    getattr(record, "data", {}),
                    severity,
                )
        except Exception:
            pass  # Never raise from a log handler
```

**Configuration** (`cli.py` and `watchdog.py`):

```python
import logging
import logging.handlers
import os
from pathlib import Path

def _configure_logging(log_dir: Path) -> None:
    root = logging.getLogger("agentweave")
    root.setLevel(logging.DEBUG)  # handlers control what actually emits

    # Handler 1: JSONL file (structured events + developer tracing)
    jsonl_path = log_dir / "events.jsonl"
    file_handler = JSONRotatingFileHandler(
        jsonl_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)

    # Handler 2: Hub forwarding (INFO+ only)
    hub_handler = HubHandler()
    hub_handler.setLevel(logging.INFO)

    # Handler 3: stderr for developer tracing (respects AW_LOG_LEVEL)
    level_name = os.environ.get("AW_LOG_LEVEL", "WARNING").upper()
    stderr_handler = logging.StreamHandler()
    stderr_handler.setLevel(getattr(logging, level_name, logging.WARNING))

    root.addHandler(file_handler)
    root.addHandler(hub_handler)
    root.addHandler(stderr_handler)
```

**Call sites** — callers use one unified API instead of two:

```python
# Before (two separate calls for different purposes):
log_event("msg_sent", severity=INFO, msg_id=mid, **{"from": sender}, to=recipient)
logger.debug("[Messaging] send_message %s → %s", sender, recipient)

# After (one call, handler routing is automatic):
logger.info(
    "msg_sent",
    extra={"event": "msg_sent", "data": {"msg_id": mid, "from": sender, "to": recipient}},
)
logger.debug("[Messaging] send_message %s → %s", sender, recipient)
# ↑ same logger, DEBUG goes to file only, INFO goes to file + Hub
```

### Migration plan — what stays, what changes

| Component | Keep? | Notes |
|-----------|-------|-------|
| `events.jsonl` file format | **Yes** | `agentweave log` depends on it; `JSONRotatingFileHandler` writes the same format |
| `get_events()` | **Yes** | Reads JSONL — no changes needed |
| `format_event()` | **Yes** | Renders CLI output — no changes needed |
| `write_heartbeat()` / `get_heartbeat_age()` | **Yes** | Unrelated to logging |
| `log_event()` function | **Remove** | Replaced by `logger.*` calls |
| Severity constants (`WARN`, `INFO`, etc.) | **Remove** | Use `logging.WARNING`, `logging.INFO`, etc. |
| `_PUSH_MIN_SEVERITY` set | **Remove** | Logic moves into `HubHandler.emit()` |
| The Hub push side-effect in `log_event()` | **Remove** | Logic moves into `HubHandler.emit()` |

### Current state vs future state

The rest of this document is written against **current state** (`log_event()` + `logger.*`)
because that is what exists today. When the migration above is done:

- Every `log_event("event_name", severity=X, ...)` call becomes
  `logger.levelname("event_name", extra={"event": "event_name", "data": {...}})`
- Every `logger.DEBUG` call stays as-is
- The import `from .eventlog import log_event, WARN, ERROR` is replaced by
  `import logging; logger = logging.getLogger(__name__)`

---

## 3. Infrastructure Gaps to Fix Before Adding Log Points

The following gaps must be addressed before logging can be added consistently.

### Gap 1 — `push_log()` not declared in `BaseTransport`

`log_event()` calls `t.push_log(...)` with a `# type: ignore[attr-defined]` annotation
because `push_log()` is only implemented on `HttpTransport`. `LocalTransport` and
`GitTransport` do not have it. This is a latent `AttributeError` if the transport check
ever silently fails.

**Fix**: Add `push_log()` to `BaseTransport` as a no-op default, exactly like `push_session()`
was added:

```python
# src/agentweave/transport/base.py
def push_log(
    self,
    event_type: str,
    agent: str,
    data: Optional[Dict[str, Any]],
    severity: str,
) -> None:
    """Push a log event to the backend (no-op on non-HTTP transports)."""
    return
```

Then remove the `# type: ignore` from `eventlog.py` and call `t.push_log()` unconditionally
(non-HTTP transports simply return immediately).

### Gap 2 — Python `logging` is not configured anywhere

The CLI package and watchdog subprocess never call `logging.basicConfig()`. As a result,
`logger.debug(...)` calls throughout the codebase are silently discarded with no handler
warning.

**Fix**: Add `_configure_logging()` to `cli.py` and `watchdog.py` (see §4.2 below).

### Gap 3 — `eventlog.py` has no formatter for most new event types

`format_event()` in `eventlog.py` formats known event types (`msg_sent`, `task_status`, etc.)
and falls back to a generic repr for everything else. As new event names are added, add a
matching `if ev == "new_event_name":` branch to `format_event()` so that `agentweave log`
renders them cleanly.

---

## 4. Setting Up Each Channel

### 4.1 Structured events — `log_event()`

`log_event()` is already implemented. Import it wherever needed:

```python
from .eventlog import log_event, DEBUG, INFO, WARN, ERROR
```

Severity constants (defined in `eventlog.py`):

| Constant | String | Pushed to Hub? | Use when |
|----------|--------|----------------|----------|
| `DEBUG` | `"debug"` | No | Very fine-grained, high-frequency events |
| `INFO` | `"info"` | Yes | Observable lifecycle milestones |
| `WARN` | `"warn"` | Yes | Recoverable anomalies, skipped operations |
| `ERROR` | `"error"` | Yes | Failures that prevent an operation from completing |

> `CRITICAL` does not exist in `eventlog.py`. Use `ERROR` for the most severe events.
> Python's `logging.CRITICAL` is available for Hub startup failures (see §6).

### 4.2 Developer tracing — Python `logging`

Add to `src/agentweave/cli.py`:

```python
import logging
import os

def _configure_logging() -> None:
    level_name = os.environ.get("AW_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    log_file = os.environ.get("AW_LOG_FILE")
    handler: logging.Handler = (
        logging.FileHandler(log_file) if log_file else logging.StreamHandler()
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=[handler],
    )
```

Call `_configure_logging()` at the very top of `main()`, before `args = parser.parse_args()`.

Also call it at the top of `watchdog.main()` — the watchdog is a separate subprocess and
inherits env vars but not the parent's logging configuration.

Each module declares its own logger at module level:

```python
import logging
logger = logging.getLogger(__name__)
# agentweave.cli, agentweave.session, agentweave.transport.git, agentweave.watchdog, …
```

### 4.3 Hub server — Python `logging` only

The Hub server receives `log_event()` payloads from the CLI via `POST /api/v1/logs`.
It does **not** call `log_event()` itself. For its own internal tracing it uses Python's
`logging` module, integrated with uvicorn:

```python
import logging
logger = logging.getLogger(__name__)
# hub.main, hub.auth, hub.api.v1.messages, hub.mcp_server, …
```

Control verbosity via `.env`:

```
UVICORN_LOG_LEVEL=info    # controls uvicorn + all hub.* loggers
```

---

## 5. Existing Event Names (already emitted)

These events are already called in the codebase. Do not duplicate them — extend, not replace.

| Event name | Emitted from | Severity |
|------------|-------------|----------|
| `msg_sent` | `messaging.py` | INFO |
| `msg_read` | `messaging.py` | INFO |
| `msg_detected` | `watchdog.py` | INFO |
| `task_created` | `task.py` | INFO |
| `task_status` | `task.py` | INFO |
| `watchdog_started` | `watchdog.py` | INFO |
| `watchdog_stopped` | `watchdog.py` | INFO |
| `watchdog_ping` | `watchdog.py` | INFO |
| `ping_skipped` | `watchdog.py` | INFO |
| `transport_error` | `transport/http.py` | WARN |
| `watchdog_poll_error` | `watchdog.py` | WARN |
| `watchdog_heartbeat_failed` | `watchdog.py` | WARN |
| `watchdog_stderr_drain_failed` | `watchdog.py` | WARN |
| `watchdog_kimi_no_sessions_dir` | `watchdog.py` | WARN |
| `watchdog_kimi_session_already_set` | `watchdog.py` | INFO |
| `watchdog_kimi_session_error` | `watchdog.py` | WARN |
| `watchdog_kimi_session_not_found` | `watchdog.py` | WARN |
| `watchdog_agent_exit` | `watchdog.py` | WARN |
| `watchdog_spawn_failed` | `watchdog.py` | ERROR |
| `watchdog_subprocess_error` | `watchdog.py` | ERROR |
| `watchdog_kimi_session_fallback` | `watchdog.py` | INFO |
| `direct_trigger_executing` | `watchdog.py` | INFO |

---

## 6. CLI Package — New Log Points

### 6.1 `cli.py`

> Use `log_event()` for all business events. Use `logger.*` only for DEBUG-level internal
> tracing that is too noisy for the event log.

```python
from .eventlog import log_event, DEBUG, INFO, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

#### `cmd_init()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `logger.DEBUG` | `"cmd_init entry: project=%s principal=%s"` | — | Tracing |
| `log_event(WARN)` | `"init_blocked"` | `path=".agentweave"` | Directory already exists |
| `log_event(WARN)` | `"init_file_removed"` | `path=".agentweave"` | File replaced by dir |
| `log_event(ERROR)` | `"init_file_remove_failed"` | `error=str(e)` | Cannot create dir |
| `log_event(WARN)` | `"template_missing"` | `template=name` | Non-fatal skip |
| `log_event(INFO)` | `"session_created"` | `session_id`, `mode`, `principal`, `agents` | Session lifecycle |
| `log_event(ERROR)` | `"init_failed"` | `error=str(e)` | ValueError from session.create() |

#### `cmd_status()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"no_session"` | `command="status"` | Misconfiguration |
| `log_event(WARN)` | `"watchdog_stale_pid"` | `pid=N` | Process dead, file left behind |
| `log_event(WARN)` | `"watchdog_heartbeat_stale"` | `age_s=N` | Daemon may have crashed |

#### `cmd_quick()` / `cmd_delegate()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"no_session"` | `command="quick"` | Blocked |
| `log_event(ERROR)` | `"task_validation_failed"` | `errors=[…]` | Data integrity |
| `log_event(ERROR)` | `"lock_timeout"` | `resource="task"` | Concurrency failure |
| `log_event(INFO)` | `"task_assigned"` | `task_id`, `assignee`, `title` | Delegation milestone |
| `log_event(WARN)` | `"message_validation_failed"` | `errors=[…]` | Message not sent |
| `log_event(ERROR)` | `"cmd_quick_failed"` | `error=str(e)` | Unhandled exception |

#### `cmd_task_create()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"task_validation_failed"` | `errors=[…]` | Data integrity |
| `log_event(ERROR)` | `"lock_timeout"` | `resource="task"` | Concurrency failure |
| `log_event(ERROR)` | `"cmd_task_create_failed"` | `error=str(e)` | Unhandled exception |

#### `cmd_task_update()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"lock_timeout"` | `resource=task_id` | Concurrency failure |
| `log_event(ERROR)` | `"task_not_found"` | `task_id` | Missing data |
| `log_event(ERROR)` | `"task_validation_failed"` | `task_id`, `errors=[…]` | Post-update data check |

> Note: `task_status` events are already emitted by `task.py`. Do not duplicate here.

#### `cmd_msg_send()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"message_validation_failed"` | `errors=[…]` | Data integrity |
| `log_event(ERROR)` | `"cmd_msg_send_failed"` | `error=str(e)` | Unhandled exception |

> Note: `msg_sent` is already emitted by `messaging.py`. Do not duplicate here.

#### `cmd_start()` / `cmd_stop()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(WARN)` | `"watchdog_already_running"` | `pid=N` | Duplicate launch attempt |
| `log_event(WARN)` | `"watchdog_stale_pid_cleaned"` | `pid=N` | Process cleanup |
| `log_event(INFO)` | `"watchdog_spawned"` | `pid=N`, `log_file=path` | Process lifecycle |
| `log_event(ERROR)` | `"watchdog_pid_corrupt"` | `path=str` | File corruption |
| `log_event(INFO)` | `"watchdog_terminated"` | `pid=N` | Process lifecycle |
| `log_event(WARN)` | `"watchdog_already_gone"` | `pid=N` | Stale PID cleaned |

#### `cmd_transport_setup()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"transport_setup_failed"` | `type="git"`, `reason="not a git repo"` | Prerequisite missing |
| `log_event(ERROR)` | `"transport_setup_failed"` | `type="git"`, `error=str(e)` | Branch push failed |
| `log_event(WARN)` | `"transport_setup_missing_params"` | `type="http"` | Input incomplete |
| `log_event(ERROR)` | `"transport_setup_failed"` | `type="http"`, `error=str(e)` | Connectivity check failed |
| `log_event(INFO)` | `"transport_configured"` | `type=str` | Setup complete |
| `log_event(ERROR)` | `"transport_setup_failed"` | `type="unknown"`, `value=str` | Bad input |

#### `cmd_transport_pull()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(INFO)` | `"transport_pull"` | `type=str`, `messages=N` | Pull result |

#### `cmd_hub_heartbeat()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"heartbeat_failed"` | `agent=str`, `error=str(e)` | Connectivity lost |

#### `cmd_reply()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"reply_failed"` | `question_id=str`, `status=N` | API failure |
| `log_event(INFO)` | `"reply_submitted"` | `question_id=str` | Human interaction confirmed |

#### `cmd_yolo()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"yolo_invalid_args"` | `reason="both flags"` | Input error |
| `log_event(ERROR)` | `"yolo_agent_not_found"` | `agent=str` | Input error |
| `log_event(INFO)` | `"yolo_mode_changed"` | `agent=str`, `enabled=bool` | Config change |

#### `cmd_sync_context()`

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(WARN)` | `"sync_agent_skipped"` | `agent=str`, `reason="not in session"` | Input mismatch |
| `log_event(WARN)` | `"sync_no_agents"` | — | Edge case |
| `log_event(ERROR)` | `"template_missing"` | `template=str` | Missing asset |
| `log_event(INFO)` | `"sync_complete"` | `written=N`, `skipped=N` | Summary |

---

### 6.2 `session.py`

```python
from .eventlog import log_event, DEBUG, INFO, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `logger.DEBUG` | `"Session.load()"` | — | Tracing |
| `log_event(INFO)` | `"session_loaded"` | `session_id`, `mode`, `principal` | Lifecycle |
| `log_event(WARN)` | `"session_file_missing"` | — | Expected on first init |
| `log_event(ERROR)` | `"session_save_failed"` | `error=str(e)` | Data loss risk |
| `log_event(WARN)` | `"session_validation_failed"` | `field=str`, `value=str` | Bad principal/mode/agent name |
| `log_event(WARN)` | `"hub_push_failed"` | `method="push_session"`, `error=str(e)` | Silenced exception visibility |

---

### 6.3 `task.py`

```python
from .eventlog import log_event, DEBUG, INFO, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

> `task_created` and `task_status` are already emitted. Add only the gaps below.

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(WARN)` | `"task_id_rejected"` | `task_id=str` | **Security** — possible path traversal |
| `log_event(WARN)` | `"task_not_found"` | `task_id=str` | Missing data |
| `log_event(ERROR)` | `"task_save_failed"` | `task_id=str`, `error=str(e)` | Data loss risk |
| `log_event(WARN)` | `"task_move_skipped"` | `task_id=str`, `reason="not in active dir"` | Unexpected state |
| `log_event(WARN)` | `"task_invalid_priority"` | `task_id=str`, `priority=str` | Data correction |
| `log_event(WARN)` | `"task_load_error"` | `path=str`, `error=str(e)` | list_all() partial failure |

---

### 6.4 `messaging.py`

```python
from .eventlog import log_event, DEBUG, INFO, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

> `msg_sent` and `msg_read` are already emitted. Add only the gaps below.

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(WARN)` | `"message_not_found"` | `msg_id=str` | Missing data |
| `log_event(ERROR)` | `"message_save_failed"` | `msg_id=str`, `error=str(e)` | Data loss risk |
| `log_event(WARN)` | `"message_archive_skipped"` | `msg_id=str`, `reason="not in pending"` | Race condition |
| `log_event(ERROR)` | `"message_send_failed"` | `msg_id=str`, `from=str`, `to=str` | Delivery failure |
| `log_event(WARN)` | `"message_invalid_type"` | `msg_id=str`, `type=str` | Data correction |
| `log_event(WARN)` | `"message_load_error"` | `path=str`, `error=str(e)` | get_outbox() partial failure |

---

### 6.5 `transport/config.py`

```python
from ..eventlog import log_event, INFO, WARN
import logging
logger = logging.getLogger(__name__)
```

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(INFO)` | `"transport_init"` | `type="local"` | Explicit fallback confirmation |
| `log_event(INFO)` | `"transport_init"` | `type="git"`, `remote=str`, `branch=str`, `cluster=str` | Init milestone |
| `log_event(INFO)` | `"transport_init"` | `type="http"`, `url=str` | Init milestone (redact key) |
| `log_event(WARN)` | `"transport_type_unknown"` | `type=str` | Config error, fell back to local |
| `logger.DEBUG` | `"TransportConfig: checking %s"` | path | Tracing config discovery |

---

### 6.6 `transport/local.py`

```python
from ..eventlog import log_event, DEBUG, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(ERROR)` | `"message_save_failed"` | `msg_id=str`, `error=str(e)` | Delivery failure |
| `log_event(WARN)` | `"message_archive_skipped"` | `msg_id=str`, `reason="not in pending"` | Race condition |
| `log_event(ERROR)` | `"message_archive_cleanup_failed"` | `msg_id=str`, `error=str(e)` | Filesystem issue — may cause duplicates |
| `log_event(ERROR)` | `"task_save_failed"` | `task_id=str`, `error=str(e)` | Task not available to assignee |
| `logger.DEBUG` | `"[LocalTransport] send_message %s → %s"` | — | Tracing |
| `logger.DEBUG` | `"[LocalTransport] get_pending: %d messages for %s"` | — | Tracing |

---

### 6.7 `transport/git.py`

```python
from ..eventlog import log_event, DEBUG, INFO, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `logger.DEBUG` | `"[GitTransport] git %s"` | — | Every git plumbing call |
| `log_event(ERROR)` | `"git_command_failed"` | `cmd=str`, `rc=N`, `stderr=str` | Any non-zero git exit |
| `log_event(WARN)` | `"git_fetch_failed"` | `rc=N` | Connectivity / branch gone |
| `log_event(ERROR)` | `"git_invalid_json"` | `path=str`, `error=str(e)` | Data corruption on remote |
| `logger.DEBUG` | `"[GitTransport] push attempt %d/3: %s"` | — | Retry tracing |
| `log_event(WARN)` | `"git_push_conflict"` | `attempt=N` | Non-fast-forward, retrying |
| `log_event(ERROR)` | `"git_push_failed"` | `path=str`, `attempts=3` | **Message/task lost** — all retries exhausted |
| `log_event(ERROR)` | `"git_seen_set_save_failed"` | `agent=str`, `error=str(e)` | Dedup tracking lost — may cause duplicate delivery |
| `log_event(INFO)` | `"msg_sent"` | `msg_id=str`, `from=str`, `to=str` | Reuse existing event name |
| `log_event(ERROR)` | `"message_send_failed"` | `from=str`, `to=str`, `error=str(e)` | Delivery failure |
| `log_event(WARN)` | `"message_not_found"` | `msg_id=str`, `reason="not on remote"` | May be expired |
| `log_event(ERROR)` | `"task_save_failed"` | `assignee=str`, `error=str(e)` | Task not assigned |

---

### 6.8 `transport/http.py`

```python
import logging
logger = logging.getLogger(__name__)
```

> **Critical rule**: `push_log()` must **never** call `log_event()` or `logger.*`.
> Doing so would create an infinite loop: `log_event → push_log → log_event → …`.
> Silently swallow all exceptions inside `push_log()` with a bare `except Exception: pass`.
> The same applies to anything called from inside `push_log()`.

Other methods may use `log_event()` normally (they already do — `transport_error` is emitted
from `push_session()`). Extend this pattern:

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `logger.DEBUG` | `"[HttpTransport] %s /api/v1%s"` | method, path | Every API call |
| `logger.DEBUG` | `"[HttpTransport] %s /api/v1%s → %d"` | method, path, status | Response |
| `log_event(ERROR)` | `"transport_error"` | `method="send_message"`, `error=str(e)` | Delivery failure |
| `log_event(ERROR)` | `"transport_error"` | `method="send_task"`, `error=str(e)` | Task not assigned |
| `log_event(WARN)` | `"transport_error"` | `method="ask_question"`, `error=str(e)` | Human interaction failed |
| `logger.DEBUG` | `"[HttpTransport] push_log — NO logging here"` | — | **Do not add** |

---

### 6.9 `watchdog.py`

```python
from .eventlog import log_event, DEBUG, INFO, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

> Many events are already emitted — see §5 for the full list. Add only the gaps below.

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(INFO)` | `"agent_spawned"` | `agent=str`, `pid=N` | Subprocess lifecycle |
| `log_event(INFO)` | `"agent_exited"` | `agent=str`, `exit_code=N`, `output_lines=N` | Subprocess lifecycle |
| `log_event(WARN)` | `"session_file_corrupt"` | `agent=str`, `error=str(e)` | Data corruption |
| `log_event(ERROR)` | `"session_save_failed"` | `agent=str`, `error=str(e)` | Session persistence lost |
| `log_event(WARN)` | `"hub_output_post_failed"` | `agent=str`, `error=str(e)` | Streaming to Hub lost |
| `log_event(INFO)` | `"new_messages_detected"` | `count=N`, `transport=str` | Detection result |
| `log_event(INFO)` | `"new_tasks_detected"` | `count=N`, `transport=str` | Detection result |
| `logger.DEBUG` | `"[Watchdog] poll cycle: transport=%s"` | — | Tracing |
| `logger.DEBUG` | `"[Watchdog] running: %s"` | cmd | Every subprocess launch |
| `logger.DEBUG` | `"[Watchdog] session ID extracted: %s"` | id | Parsing trace |

---

### 6.10 `locking.py`

```python
from .eventlog import log_event, DEBUG, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `logger.DEBUG` | `"[Lock] acquiring: %s (timeout=%s)"` | name, timeout | Tracing |
| `logger.DEBUG` | `"[Lock] acquired: %s"` | name | Tracing |
| `log_event(WARN)` | `"lock_stale"` | `resource=str`, `age_s=N` | Stale lock cleaned |
| `log_event(WARN)` | `"lock_stale_read_error"` | `resource=str`, `error=str(e)` | Lock file unreadable |
| `logger.DEBUG` | `"[Lock] retry %d for %s"` | attempt, name | Contention tracing |
| `log_event(ERROR)` | `"lock_timeout"` | `resource=str`, `timeout_s=N` | Deadlock risk |
| `log_event(ERROR)` | `"lock_release_failed"` | `resource=str`, `error=str(e)` | Resource leak |
| `log_event(ERROR)` | `"lock_wait_timeout"` | `resource=str`, `waited_s=N` | Caller permanently blocked |

---

### 6.11 `validator.py`

```python
from .eventlog import log_event, WARN
import logging
logger = logging.getLogger(__name__)
```

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(WARN)` | `"validation_failed"` | `entity="task"`, `field=str`, `value=str` | Data integrity |
| `log_event(WARN)` | `"validation_failed"` | `entity="message"`, `field=str`, `value=str` | Data integrity |
| `log_event(WARN)` | `"validation_failed"` | `entity="session"`, `field=str`, `value=str` | Data integrity |
| `logger.DEBUG` | `"[Validator] sanitize_string: %d → %d chars"` | original, truncated | Tracing |

---

### 6.12 `utils.py`

```python
from .eventlog import log_event, WARN, ERROR
import logging
logger = logging.getLogger(__name__)
```

| Level | Event / logger call | Fields | Why |
|-------|---------------------|--------|-----|
| `log_event(WARN)` | `"dir_file_conflict"` | `path=str` | File replaced by directory |
| `log_event(ERROR)` | `"dir_create_failed"` | `path=str`, `error=str(e)` | Permission issue — will cascade |
| `log_event(ERROR)` | `"json_read_failed"` | `path=str`, `error=str(e)` | File corruption or access denied |
| `log_event(ERROR)` | `"json_write_failed"` | `path=str`, `error=str(e)` | Disk full or permission denied |
| `logger.DEBUG` | `"[Utils] load_json: not found %s"` | path | Expected on first run (DEBUG so it doesn't spam) |
| `logger.DEBUG` | `"[Utils] save_json: %s"` | path | Tracing |

---

## 7. Hub Server Logging Points

The Hub is the backend. It receives `log_event()` payloads from CLI via `POST /api/v1/logs`
and stores them in the `EventLog` table. For its own internal observability it uses Python's
`logging` module only — no `log_event()` calls.

### 7.1 `main.py` + `db/engine.py` + `config.py` — Startup

```python
import logging
logger = logging.getLogger(__name__)
```

| File | Level | Message | Why |
|------|-------|---------|-----|
| `config.py` | `INFO` | `"Settings loaded: port=%d, db=%s, project=%s"` | Startup config visible |
| `db/engine.py` | `INFO` | `"Database ready: %s"` | Critical startup milestone |
| `db/engine.py` | `CRITICAL` | `"Failed to create database tables: %s"` | Server cannot serve requests |
| `db/engine.py` | `INFO` | `"Bootstrap: creating project '%s'"` | New install |
| `db/engine.py` | `INFO` | `"Bootstrap: API key created"` | Security event |
| `db/engine.py` | `ERROR` | `"Bootstrap commit failed: %s"` | Init incomplete |
| `main.py` | `INFO` | `"UI dist found at %s, serving SPA"` | Mode detection |
| `main.py` | `INFO` | `"UI dist not found, API-only mode"` | Mode detection |
| `main.py` | `CRITICAL` | `"Failed to start server on port %d: %s"` | Process cannot start |

---

### 7.2 `auth.py`

| Level | Message | Why |
|-------|---------|-----|
| `WARNING` | `"Auth: no API key in request"` | Missing credentials |
| `WARNING` | `"Auth: malformed key format"` | Wrong key prefix |
| `WARNING` | `"Auth: invalid or revoked key (%.8s...)"` | Security event — redact key |
| `DEBUG` | `"Auth: OK for project '%s'"` | Request tracing |
| `ERROR` | `"Auth: DB error fetching project: %s"` | Infrastructure failure |

---

### 7.3 REST API endpoints

For all REST endpoints, the pattern is:
- `DEBUG` for query parameters and result counts (too noisy for INFO)
- `INFO` for state-changing operations: message created, task updated, question answered
- `WARNING` for 404s and invalid input
- `ERROR` for unexpected DB or SSE failures

#### `api/v1/messages.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"Message created: id=%s, from=%s, to=%s"` | Lifecycle |
| `WARNING` | `"Message not found for read: %s"` | Bad request |
| `INFO` | `"Message %s marked read"` | Lifecycle |
| `WARNING` | `"Invalid message timestamp, using now(): %s"` | Data correction |
| `DEBUG` | `"List messages: %d results (project=%s, agent=%s)"` | Query |

#### `api/v1/tasks.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"Task created: id=%s, title=%s, assignee=%s"` | Lifecycle |
| `WARNING` | `"Task not found: %s"` | Bad request |
| `INFO` | `"Task %s updated: status=%s"` | State transition |
| `WARNING` | `"Invalid task timestamp, using default: %s"` | Data correction |
| `DEBUG` | `"List tasks: %d results (project=%s, status=%s)"` | Query |

#### `api/v1/questions.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"Question created: from=%s, blocking=%s"` | Human interaction event |
| `WARNING` | `"Question not found: %s"` | Bad request |
| `INFO` | `"Question %s answered"` | Human interaction confirmed |
| `INFO` | `"Reply message created: id=%s → %s"` | Message lifecycle |

#### `api/v1/agents.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"Heartbeat: agent=%s, status=%s"` | Agent monitoring |
| `INFO` | `"Agent output: agent=%s, len=%d"` | Activity event |
| `DEBUG` | `"Timeline for %s: %d events"` | Query result |
| `DEBUG` | `"Agent list: %d agents"` | Query result |

#### `api/v1/agent_trigger.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"Trigger received: agent=%s, mode=%s"` | Operation start |
| `WARNING` | `"Invalid session_mode '%s'"` | Input error |
| `INFO` | `"Trigger message created: id=%s"` | Lifecycle |

#### `api/v1/session_sync.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"Session config %s: %d agents"` | created/updated + agent count |

#### `api/v1/logs.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"CLI log event received: type=%s, agent=%s, severity=%s"` | CLI→Hub bridge |
| `WARNING` | `"Invalid 'since' filter ignored: %s"` | Filter skipped |

#### `api/v1/events.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"SSE client connected: project=%s"` | Connection tracking |
| `INFO` | `"SSE client disconnected: project=%s"` | Connection tracking |
| `ERROR` | `"SSE generator error: %s"` | Stream failure |

---

### 7.4 `sse.py`

| Level | Message | Why |
|-------|---------|-----|
| `DEBUG` | `"SSE subscribed: project=%s (total=%d)"` | Connection count |
| `WARNING` | `"SSE unsubscribe: queue not found for project=%s"` | Cleanup issue |
| `DEBUG` | `"SSE broadcast: project=%s, type=%s, subscribers=%d"` | Fan-out |
| `WARNING` | `"SSE queue full: project=%s, dropping '%s' event"` | **Event loss** — operator attention needed |

---

### 7.5 `mcp_server.py`

| Level | Message | Why |
|-------|---------|-----|
| `INFO` | `"AgentWeave Hub MCP server starting (10 tools)"` | Startup |
| `DEBUG` | `"[MCP] %s %s"` | Every Hub API call |
| `ERROR` | `"[MCP] HTTP %d for %s: %s"` | API failure |
| `INFO` | `"[MCP] send_message: %s → %s"` | Tool invoked |
| `WARNING` | `"[MCP] send_message failed: %s"` | Tool error |
| `INFO` | `"[MCP] create_task: '%s', assignee=%s"` | Tool invoked |
| `WARNING` | `"[MCP] create_task failed: %s"` | Tool error |
| `INFO` | `"[MCP] update_task: %s → %s"` | State transition |
| `WARNING` | `"[MCP] update_task failed: %s"` | Tool error |
| `INFO` | `"[MCP] ask_user: from=%s, blocking=%s"` | Human interaction |
| `WARNING` | `"[MCP] ask_user failed: %s"` | Tool error |
| `DEBUG` | `"[MCP] get_answer: question=%s, answered=%s"` | Polling |
| `WARNING` | `"[MCP] get_answer failed: %s"` | Tool error |
| `WARNING` | `"[MCP] %s failed: %s"` | Generic fallback for get_inbox, mark_read, list_tasks, get_task, get_status |

---

### 7.6 `utils.py` (Hub)

| Level | Message | Why |
|-------|---------|-----|
| `DEBUG` | `"Persisting event: type=%s, agent=%s, severity=%s"` | DB write |
| `ERROR` | `"Failed to persist event: %s"` | Data loss — event not stored |

---

## 8. Revision History

| Version | Change |
|---------|--------|
| v1 | Initial draft — incorrectly used Python `logging` as the primary mechanism throughout |
| v2 | Corrected to use `log_event()` as primary channel; identified `push_log()` gap in `BaseTransport`; fixed severity constant names (`WARN` not `WARNING`); separated Hub server from CLI logging; listed existing event names |
| v3 | Added §2: honest assessment of `eventlog.py` weaknesses, recommendation to migrate to Python `logging` + `JSONRotatingFileHandler` + `HubHandler`, migration plan table, before/after call-site examples; expanded existing event name table with all watchdog events |

---

## 9. Log Point Count Summary

| Module | `log_event()` calls | `logger.*` calls | Total |
|--------|---------------------|------------------|-------|
| cli.py | 30 | 5 | 35 |
| session.py | 5 | 1 | 6 |
| task.py | 6 | 0 | 6 |
| messaging.py | 6 | 0 | 6 |
| transport/config.py | 4 | 1 | 5 |
| transport/local.py | 4 | 2 | 6 |
| transport/git.py | 10 | 2 | 12 |
| transport/http.py | 3 | 2 | 5 |
| watchdog.py | 9 | 3 | 12 |
| locking.py | 5 | 2 | 7 |
| validator.py | 3 | 1 | 4 |
| utils.py (CLI) | 4 | 2 | 6 |
| **CLI subtotal** | **89** | **21** | **110** |
| main.py + db/ + config.py | 0 | 9 | 9 |
| auth.py | 0 | 5 | 5 |
| REST endpoints (7 files) | 0 | 25 | 25 |
| sse.py | 0 | 4 | 4 |
| mcp_server.py | 0 | 14 | 14 |
| utils.py (Hub) | 0 | 2 | 2 |
| **Hub subtotal** | **0** | **59** | **59** |
| **Grand total** | **89** | **80** | **169** |

> Hub rows show 0 for `log_event()` because the Hub *stores* those events, it does not
> emit them. CLI `log_event()` calls reach the Hub automatically via `push_log()` when
> the HTTP transport is active.
>
> After the §2 migration: all 89 `log_event()` calls become `logger.*` calls with structured
> `extra=` data. The total count stays the same; the column split disappears.
