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

HUB = os.environ.get("AW_HUB", "http://127.0.0.1:8010")
KEY = os.environ.get("AW_KEY", "aw_live_58ab7d84a1bf7b34eb2d1b424875bacd")
P = os.environ.get("AW_PROJECT", "")

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def api(method, path, body=None, raw=False, timeout=60):
    """Call the Hub. Returns (status, parsed_or_text). Never raises on HTTP error."""
    url = HUB + ("/api/v1" + path if path.startswith("/") else path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + KEY)
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


def show(label, code, body, limit=1200):
    s = body if isinstance(body, str) else json.dumps(body, indent=1, default=str)
    print(f"--- {label}  [{code}]")
    print(s[:limit])
    if isinstance(s, str) and len(s) > limit:
        print(f"... ({len(s)} chars)")
