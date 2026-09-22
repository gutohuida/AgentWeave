"""Minimal driver for the trial Hub. Operator-side only: everything an operator can do.

Usage:  from aw import api, P
        api("GET", "/projects")
        api("POST", f"/projects/{P}/tasks", {"title": "..."})
"""

import json
import os
import ssl
import urllib.error
import urllib.request

# No default either (F138). The old one was `:8010`, the trial Hub -- so a script run with no
# environment at all drove the one instance a drive must not disturb. Name the Hub you started.
HUB = os.environ.get("AW_HUB", "")
# No default. This file is tracked in a public repository, so a key written here is a published
# key -- and one was, from the first commit of this file until 2026-09-07. Set AW_KEY in the
# environment instead; `require_key()` below refuses to build a request without one.
KEY = os.environ.get("AW_KEY", "")
P = os.environ.get("AW_PROJECT", "")

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def require_key():
    """Fail here, locally, rather than at the Hub with a 401. Returns the key.

    Raises `SystemExit` deliberately, not `RuntimeError`: this directory is full of scripts that
    wrap calls in a bare `except Exception`, and a configuration error that one of those can
    swallow is not the loud failure the comment above promises. `SystemExit` is a BaseException,
    so it survives them, and it prints its message without a traceback.
    """
    if not KEY:
        raise SystemExit(
            "AW_KEY is not set. Export the Hub's key before running a drive script:\n"
            "  export AW_KEY=$(cat ~/.agentweave/hub/profiles/trial/bootstrap-key.txt)\n"
            "Nothing is defaulted -- this file is tracked in a public repository."
        )
    return KEY


def require_hub():
    """Like `require_key()`: an unset AW_HUB stops the script here, loudly. Returns the URL."""
    if not HUB:
        raise SystemExit(
            "AW_HUB is not set. Point it at the Hub this drive started, e.g.\n"
            "  export AW_HUB=http://127.0.0.1:8031\n"
            "Nothing is defaulted -- :8000 is the operator's and :8010 is the trial Hub."
        )
    return HUB


def api(method, path, body=None, raw=False, timeout=60):
    """Call the Hub. Returns (status, parsed_or_text). Never raises on HTTP error.

    An unset AW_KEY or AW_HUB is not an HTTP error: `require_key()` and `require_hub()` stop the
    call before the request is built, so it never reaches the network.
    """
    key = require_key()
    url = require_hub() + ("/api/v1" + path if path.startswith("/") else path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + key)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            text = r.read().decode("utf-8", "replace")
            code = r.status
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        code = e.code
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"
    if raw:
        return code, text
    try:
        return code, json.loads(text)
    except ValueError:
        return code, text


def task_rows(body):
    """The rows of a `GET /tasks` answer, which is `{tasks, total, has_more}` since F202.

    A harness that reads the old bare array gets nothing useful from the object, and the shape the
    drives had written for it — `body if isinstance(body, list) else []` — turns that into an empty
    list. A drive then reports "no tasks" as a *verdict*, which is a harness telling a lie. So this
    raises on a shape it does not recognise rather than answering `[]`.
    """
    if isinstance(body, dict) and "tasks" in body:
        return body["tasks"]
    if isinstance(body, list):
        raise TypeError(
            "GET /tasks answered a bare array. Since F202 it answers "
            "{tasks, total, has_more} — this Hub is older than the harness."
        )
    raise TypeError(f"not a task-list answer: {body!r}")


def show(label, code, body, limit=1200):
    s = body if isinstance(body, str) else json.dumps(body, indent=1, default=str)
    print(f"--- {label}  [{code}]")
    print(s[:limit])
    if isinstance(s, str) and len(s) > limit:
        print(f"... ({len(s)} chars)")
