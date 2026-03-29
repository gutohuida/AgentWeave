"""Custom logging handlers and configuration for AgentWeave.

Provides two handlers that together replicate eventlog.py's dual-destination
behaviour (local JSONL file + Hub forwarding) while using Python's standard
logging infrastructure:

  JSONRotatingFileHandler  — writes structured JSON lines to events.jsonl
                             with automatic rotation (10 MB, 5 backups).
  HubHandler               — forwards INFO/WARNING/ERROR records to the Hub
                             when the HTTP transport is active.

Call _configure_logging() once at process startup (cli.py and watchdog.py).
"""

import json
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Any, Dict


class JSONRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """Writes one JSON object per line to a rotating log file.

    The JSON schema is identical to the legacy eventlog.py format so that
    get_events() and format_event() continue to work without changes::

        {"ts": "2026-03-28T10:00:00", "event": "msg_sent", "severity": "info", ...}

    ``severity`` is normalised: Python's "WARNING" becomes "warn" to stay
    compatible with the existing JSONL schema.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self.shouldRollover(record):
                self.doRollover()
            entry: Dict[str, Any] = {
                "ts": datetime.fromtimestamp(record.created).isoformat(timespec="seconds"),
                "event": getattr(record, "event", record.getMessage()),
                "severity": record.levelname.lower().replace("warning", "warn"),
            }
            extra_data = getattr(record, "data", {})
            if extra_data:
                entry.update(extra_data)
            self.stream.write(json.dumps(entry) + "\n")
            self.flush()
        except Exception:
            self.handleError(record)


class HubHandler(logging.Handler):
    """Forwards INFO/WARNING/ERROR records to the Hub when HTTP transport is active.

    Never raises — logging failures must never crash the caller.

    RECURSION GUARD: push_log() on HttpTransport swallows all exceptions
    silently and must NEVER call logger.* or log_event().  Violating this
    creates an infinite loop: HubHandler.emit → push_log → log_event →
    HubHandler.emit → ...
    """

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.INFO:
            return  # DEBUG stays local only
        try:
            from .transport import get_transport

            t = get_transport()
            severity = record.levelname.lower().replace("warning", "warn")
            agent = str(getattr(record, "data", {}).get("agent", "system"))
            t.push_log(
                getattr(record, "event", record.getMessage()),
                agent,
                getattr(record, "data", {}),
                severity,
            )
        except Exception:
            pass  # Never raise from a log handler


def _configure_logging() -> None:
    """Wire up all three logging handlers for the AgentWeave process.

    Must be called once at startup (cli.py main(), watchdog.py main()).
    Idempotent — subsequent calls are no-ops.

    Environment variables:
        AW_LOG_LEVEL  — stderr log level (default: WARNING).
                        Set to DEBUG or INFO to see developer-trace output.
        AW_LOG_FILE   — redirect stderr handler to a file instead of stderr.
    """
    root = logging.getLogger("agentweave")
    if root.handlers:
        return  # Already configured

    root.setLevel(logging.DEBUG)  # handlers control what actually emits

    # Ensure the log directory exists before opening the file handler
    from .constants import LOGS_DIR

    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    jsonl_path = LOGS_DIR / "events.jsonl"

    # Handler 1: JSONL rotating file — all levels (DEBUG+)
    try:
        file_handler = JSONRotatingFileHandler(
            jsonl_path,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)
    except OSError:
        pass  # Log dir unavailable; continue without file handler

    # Handler 2: Hub forwarding — INFO and above only
    hub_handler = HubHandler()
    hub_handler.setLevel(logging.INFO)
    root.addHandler(hub_handler)

    # Handler 3: stderr (or AW_LOG_FILE) — developer tracing
    level_name = os.environ.get("AW_LOG_LEVEL", "WARNING").upper()
    stderr_level = getattr(logging, level_name, logging.WARNING)
    log_file = os.environ.get("AW_LOG_FILE")
    if log_file:
        try:
            dev_handler: logging.Handler = logging.FileHandler(log_file, encoding="utf-8")
        except OSError:
            dev_handler = logging.StreamHandler()
    else:
        dev_handler = logging.StreamHandler()
    dev_handler.setLevel(stderr_level)
    fmt = logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    dev_handler.setFormatter(fmt)
    root.addHandler(dev_handler)
